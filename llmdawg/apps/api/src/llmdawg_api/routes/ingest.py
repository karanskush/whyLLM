"""Ingest routes — POST /v1/ingest/span and POST /v1/ingest/batch.

Performance contract:
  - Zero synchronous DB I/O on the happy path (Redis queue only).
  - p99 target: < 50ms end-to-end.
  - Falls back to direct PostgreSQL write if Redis is unavailable, with a
    500ms timeout to avoid cascading latency.

Rate limiting (per project):
  - 1 000 requests/minute checked via Redis INCR + EXPIRE.
  - Returns HTTP 429 with Retry-After header on breach.

Idempotency:
  - Optional X-Idempotency-Key header (or idempotency_key in body).
  - Tracked in Redis set "seen_spans:{project_id}" with 24h TTL using SADD.
  - Duplicate keys return the original span_id with queued=false.

Queue format:
  - LPUSH ingest_queue <json_bytes>
  - JSON payload includes all span fields + project_id + org_id + key_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import orjson
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import ORJSONResponse

from llmdawg_api.middleware.api_key_auth import KeyContext, verify_api_key
from llmdawg_api.schemas.ingest import (
    BatchIngest,
    BatchIngestResponse,
    IngestError,
    IngestResponse,
    SpanIngest,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])

# ── Constants ─────────────────────────────────────────────────────────────────

_RATE_LIMIT_RPM = 1_000          # requests per minute per project
_RATE_LIMIT_WINDOW = 60          # seconds
_IDEMPOTENCY_TTL = 86_400        # 24 hours in seconds
_QUEUE_KEY = "ingest_queue"
_REDIS_FALLBACK_TIMEOUT = 0.5    # seconds — if Redis is down, wait this long for DB write


# ── Rate limiting ─────────────────────────────────────────────────────────────

async def _check_rate_limit(project_id: uuid.UUID, count: int = 1) -> None:
    """Raise HTTP 429 if the project has exceeded _RATE_LIMIT_RPM requests/minute."""
    from llmdawg_api.redis_client import get_redis

    key = f"rl:{project_id}:{int(datetime.now(tz=timezone.utc).timestamp()) // _RATE_LIMIT_WINDOW}"
    try:
        redis = get_redis()
        current = await redis.incrby(key, count)
        if current == count:
            # First request in this window — set expiry
            await redis.expire(key, _RATE_LIMIT_WINDOW + 1)
        if current > _RATE_LIMIT_RPM:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit of {_RATE_LIMIT_RPM} req/min exceeded",
                    "retry_after": _RATE_LIMIT_WINDOW,
                },
                headers={"Retry-After": str(_RATE_LIMIT_WINDOW)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Redis failure is non-fatal for rate limiting — allow the request through
        log.warning("Rate limit check failed (allowing request): %s", exc)


# ── Idempotency ───────────────────────────────────────────────────────────────

async def _check_idempotency(
    project_id: uuid.UUID, idempotency_key: str
) -> Optional[uuid.UUID]:
    """Return a previously-seen span_id if this key was already processed, else None."""
    from llmdawg_api.redis_client import get_redis

    hash_key = f"idem:{project_id}"
    try:
        redis = get_redis()
        existing = await redis.hget(hash_key, idempotency_key)
        if existing:
            return uuid.UUID(existing.decode() if isinstance(existing, bytes) else existing)
    except Exception as exc:
        log.warning("Idempotency check failed (allowing request): %s", exc)
    return None


async def _record_idempotency(
    project_id: uuid.UUID, idempotency_key: str, span_id: uuid.UUID
) -> None:
    """Record the span_id for this idempotency key (fire-and-forget)."""
    from llmdawg_api.redis_client import get_redis

    hash_key = f"idem:{project_id}"
    try:
        redis = get_redis()
        await redis.hset(hash_key, idempotency_key, str(span_id))
        await redis.expire(hash_key, _IDEMPOTENCY_TTL)
    except Exception as exc:
        log.warning("Idempotency record failed (non-critical): %s", exc)


# ── Queue helpers ─────────────────────────────────────────────────────────────

def _build_queue_payload(
    span: SpanIngest,
    span_id: uuid.UUID,
    ctx: KeyContext,
    cost_usd: Optional[Decimal],
) -> bytes:
    """Serialise a span into the queue format consumed by the background worker."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        # Identity
        "span_id": str(span_id),
        "project_id": str(ctx.project_id),
        "org_id": str(ctx.org_id),
        "key_id": str(ctx.key_id),
        # Span fields
        "name": span.name,
        "kind": span.kind,
        "environment": span.environment,
        "provider": span.provider,
        "model": span.model,
        "status": span.status,
        "user_id": span.user_id,
        "session_id": span.session_id,
        "tags": span.tags,
        "trace_id": str(span.trace_id) if span.trace_id else None,
        "parent_span_id": str(span.parent_span_id) if span.parent_span_id else None,
        "input_tokens": span.input_tokens,
        "output_tokens": span.output_tokens,
        "cached_tokens": span.cached_tokens,
        "cost_usd": str(cost_usd) if cost_usd is not None else None,
        "latency_ms": span.latency_ms,
        "ttft_ms": span.ttft_ms,
        "error_type": span.error_type,
        "error_message": span.error_message,
        "started_at": span.started_at.isoformat() if span.started_at else None,
        "ended_at": span.ended_at.isoformat() if span.ended_at else None,
        "request": span.request,
        "response": span.response,
        "source": span.source,
        "sdk_version": span.sdk_version,
        # Server-side timestamps
        "ingested_at": now.isoformat(),
    }
    return orjson.dumps(payload)


async def _enqueue(payload: bytes) -> bool:
    """Push one item onto the Redis ingest queue. Returns True on success."""
    from llmdawg_api.redis_client import get_redis

    try:
        await get_redis().lpush(_QUEUE_KEY, payload)
        return True
    except Exception as exc:
        log.warning("Redis enqueue failed: %s", exc)
        return False


async def _fallback_db_write(payload_bytes: bytes) -> bool:
    """Last-resort: write the span directly to PostgreSQL (500ms timeout).

    This runs only when Redis is unavailable. The worker will NOT double-write
    items that came through this path because they bypass the queue entirely.
    """
    try:
        data = orjson.loads(payload_bytes)
        from llmdawg_api.database import get_session_factory
        from llmdawg_api.models.span import Span
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        factory = get_session_factory()

        def _parse_decimal(v: Optional[str]) -> Optional[Decimal]:
            return Decimal(v) if v is not None else None

        def _parse_uuid(v: Optional[str]) -> Optional[uuid.UUID]:
            return uuid.UUID(v) if v else None

        def _parse_dt(v: Optional[str]) -> Optional[datetime]:
            return datetime.fromisoformat(v) if v else None

        span_id = uuid.UUID(data["span_id"])
        # Provide created_at explicitly so the partition key is known
        created_at = datetime.now(tz=timezone.utc)

        async def _write() -> None:
            async with factory() as session:
                stmt = pg_insert(Span).values(
                    id=span_id,
                    created_at=created_at,
                    project_id=uuid.UUID(data["project_id"]),
                    org_id=uuid.UUID(data["org_id"]),
                    name=data.get("name"),
                    kind=data.get("kind", "llm_call"),
                    environment=data.get("environment", "production"),
                    provider=data["provider"],
                    model=data["model"],
                    status=data["status"],
                    user_id=data.get("user_id"),
                    session_id=data.get("session_id"),
                    tags=data.get("tags", {}),
                    trace_id=_parse_uuid(data.get("trace_id")),
                    parent_span_id=_parse_uuid(data.get("parent_span_id")),
                    input_tokens=data.get("input_tokens"),
                    output_tokens=data.get("output_tokens"),
                    cached_tokens=data.get("cached_tokens", 0),
                    cost_usd=_parse_decimal(data.get("cost_usd")),
                    latency_ms=data.get("latency_ms"),
                    ttft_ms=data.get("ttft_ms"),
                    error_type=data.get("error_type"),
                    error_message=data.get("error_message"),
                    started_at=_parse_dt(data.get("started_at")),
                    ended_at=_parse_dt(data.get("ended_at")),
                    request=data.get("request"),
                    response=data.get("response"),
                    source=data.get("source", "api"),
                    sdk_version=data.get("sdk_version"),
                ).on_conflict_do_nothing(index_elements=["id", "created_at"])
                await session.execute(stmt)
                await session.commit()

        await asyncio.wait_for(_write(), timeout=_FALLBACK_TIMEOUT)
        return True
    except asyncio.TimeoutError:
        log.error("Fallback DB write timed out (span lost)")
        return False
    except Exception as exc:
        log.error("Fallback DB write failed: %s", exc)
        return False


_FALLBACK_TIMEOUT = _REDIS_FALLBACK_TIMEOUT


# ── Route: POST /v1/ingest/span ───────────────────────────────────────────────

@router.post("/span", response_model=IngestResponse, status_code=200)
async def ingest_span(
    request: Request,
    body: SpanIngest,
    ctx: KeyContext = Depends(verify_api_key),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
) -> ORJSONResponse:
    """Ingest a single LLM span.

    Returns immediately after queuing to Redis — the background worker
    persists the span to PostgreSQL asynchronously.
    """
    # ── Rate limit ────────────────────────────────────────────────────────────
    await _check_rate_limit(ctx.project_id)

    # ── Idempotency ───────────────────────────────────────────────────────────
    idem_key = x_idempotency_key or body.idempotency_key
    if idem_key:
        existing_id = await _check_idempotency(ctx.project_id, idem_key)
        if existing_id:
            return ORJSONResponse(
                {"span_id": str(existing_id), "queued": False, "cost_usd": None}
            )

    # ── Cost estimation ───────────────────────────────────────────────────────
    cost_usd: Optional[Decimal] = None
    try:
        cost_engine = request.app.state.cost_engine
        if body.input_tokens is not None and body.output_tokens is not None:
            cost_usd = cost_engine.estimate(
                body.provider,
                body.model,
                body.input_tokens,
                body.output_tokens,
                body.cached_tokens,
            )
    except Exception as exc:
        log.debug("Cost estimation failed (non-critical): %s", exc)

    # ── Assign span ID ────────────────────────────────────────────────────────
    span_id = uuid.uuid4()

    # ── Enqueue ───────────────────────────────────────────────────────────────
    payload = _build_queue_payload(body, span_id, ctx, cost_usd)
    queued = await _enqueue(payload)
    if not queued:
        # Redis is down — attempt synchronous DB write as fallback
        queued = await _fallback_db_write(payload)
        if not queued:
            raise HTTPException(
                status_code=503,
                detail={"error": "storage_unavailable", "message": "Both Redis and DB are unavailable"},
            )

    # ── Record idempotency (fire-and-forget) ──────────────────────────────────
    if idem_key:
        asyncio.create_task(_record_idempotency(ctx.project_id, idem_key, span_id))

    return ORJSONResponse({
        "span_id": str(span_id),
        "queued": queued,
        "cost_usd": float(cost_usd) if cost_usd is not None else None,
    })


# ── Route: POST /v1/ingest/batch ──────────────────────────────────────────────

@router.post("/batch", response_model=BatchIngestResponse, status_code=200)
async def ingest_batch(
    request: Request,
    body: BatchIngest,
    ctx: KeyContext = Depends(verify_api_key),
) -> ORJSONResponse:
    """Ingest up to 100 LLM spans in a single request.

    Partial success is allowed: each span is validated independently and
    rejected spans are reported in the `errors` array.
    """
    n = len(body.spans)

    # ── Rate limit (count all spans in one increment) ─────────────────────────
    await _check_rate_limit(ctx.project_id, count=n)

    # ── Cost engine ref ───────────────────────────────────────────────────────
    cost_engine = None
    try:
        cost_engine = request.app.state.cost_engine
    except AttributeError:
        pass

    # ── Process each span ─────────────────────────────────────────────────────
    span_ids: list[uuid.UUID] = []
    errors: list[IngestError] = []
    queue_payloads: list[bytes] = []

    for i, span in enumerate(body.spans):
        try:
            cost_usd: Optional[Decimal] = None
            if (
                cost_engine
                and span.input_tokens is not None
                and span.output_tokens is not None
            ):
                cost_usd = cost_engine.estimate(
                    span.provider, span.model,
                    span.input_tokens, span.output_tokens, span.cached_tokens,
                )

            span_id = uuid.uuid4()
            queue_payloads.append(_build_queue_payload(span, span_id, ctx, cost_usd))
            span_ids.append(span_id)
        except Exception as exc:
            errors.append(IngestError(index=i, error=str(exc)))

    # ── Bulk-enqueue accepted spans ───────────────────────────────────────────
    if queue_payloads:
        try:
            from llmdawg_api.redis_client import get_redis
            await get_redis().lpush(_QUEUE_KEY, *queue_payloads)
        except Exception as exc:
            log.warning("Batch Redis enqueue failed, falling back to DB: %s", exc)
            # Fall back to individual DB writes
            written_ids: list[uuid.UUID] = []
            db_errors: list[IngestError] = []
            for idx, (payload, span_id) in enumerate(zip(queue_payloads, span_ids)):
                ok = await _fallback_db_write(payload)
                if ok:
                    written_ids.append(span_id)
                else:
                    # Find the original index from the accepted spans
                    db_errors.append(IngestError(index=idx, error="storage_write_failed"))
            span_ids = written_ids
            errors.extend(db_errors)

    return ORJSONResponse({
        "accepted": len(span_ids),
        "rejected": len(errors),
        "span_ids": [str(sid) for sid in span_ids],
        "errors": [{"index": e.index, "error": e.error} for e in errors],
    })
