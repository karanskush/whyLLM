"""IngestWorker — async BRPOP consumer for the whyllm ingest queue.

Architecture:
  - Connects to Redis, BRPOP from "ingest_queue" (same format the API pushes to).
  - Processes up to `concurrency` spans concurrently via asyncio.Semaphore.
  - Per-span pipeline: parse → cost → hallucination → upsert span → upsert trace
    → publish live event.
  - On failure: exponential backoff retry (1s, 2s, 4s), then dead_letter_queue.
  - Graceful shutdown: drains in-flight tasks on SIGTERM before exiting.
  - Metrics stored in Redis counters: worker:spans_processed, worker:spans_failed.

Start:
    python -m whyllm_api.worker
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import orjson
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Lazy imports resolved at runtime — imported here so they are patchable in tests
from whyllm_api.database import get_session_factory  # noqa: E402
from whyllm_api.redis_client import get_redis  # noqa: E402

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_QUEUE_KEY = "ingest_queue"
_DLQ_KEY = "dead_letter_queue"
_METRICS_PROCESSED = "worker:spans_processed"
_METRICS_FAILED = "worker:spans_failed"
_REQUIRED_FIELDS = {"span_id", "project_id", "org_id", "provider", "model", "status"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except (ValueError, TypeError):
        return None


def _parse_uuid(v: Optional[str]) -> Optional[uuid.UUID]:
    if not v:
        return None
    try:
        return uuid.UUID(v)
    except (ValueError, TypeError):
        return None


def _parse_decimal(v: Optional[str]) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


# ── Main worker class ─────────────────────────────────────────────────────────

class IngestWorker:
    """Asyncio BRPOP consumer.

    Lifecycle:
        worker = IngestWorker()
        await worker.start()
        await worker.shutdown_event.wait()   # block until SIGTERM
        await worker.stop()
    """

    def __init__(
        self,
        concurrency: int = 50,
        max_retries: int = 3,
        brpop_timeout: int = 5,
    ) -> None:
        self._concurrency = concurrency
        self._max_retries = max_retries
        self._brpop_timeout = brpop_timeout

        self._semaphore: asyncio.Semaphore
        self._consumer_task: Optional[asyncio.Task[None]] = None
        self._in_flight: set[asyncio.Task[None]] = set()
        self.shutdown_event = asyncio.Event()

        # Injected during start() — kept as instance attrs for testability
        self._redis: Any = None
        self._cost_engine: Any = None
        # Tier-2 prediction sweep — runs in-process alongside ingest.
        self._prediction_scheduler: Any = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize dependencies and start consuming."""
        from whyllm_api.services.cost import CostEngine

        self._redis = get_redis()
        self._semaphore = asyncio.Semaphore(self._concurrency)

        # CostEngine: load pricing from DB (or fallback to prices.json)
        self._cost_engine = CostEngine()
        await self._cost_engine.start()

        # Register SIGTERM / SIGINT handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._handle_signal)
            except (NotImplementedError, ValueError):
                # Windows / test environments don't support add_signal_handler
                pass

        self._consumer_task = asyncio.create_task(
            self._consumer_loop(), name="ingest-worker-consumer"
        )

        # Start the Tier-2 prediction engine sweep. It shares this process
        # but runs on its own slow interval, so it never competes with the
        # ingest hot path. Failure to start is non-fatal — ingest goes on.
        try:
            from whyllm_api.services.predictions.engine import PredictionScheduler

            self._prediction_scheduler = PredictionScheduler()
            await self._prediction_scheduler.start()
        except Exception as exc:
            log.warning("PredictionScheduler failed to start (non-critical): %s", exc)

        log.info(
            "IngestWorker started — concurrency=%d retries=%d",
            self._concurrency, self._max_retries,
        )

    async def stop(self) -> None:
        """Signal shutdown and wait for all in-flight tasks to complete."""
        self.shutdown_event.set()

        # Stop the prediction sweep first — it's the lowest priority.
        if self._prediction_scheduler is not None:
            try:
                await self._prediction_scheduler.stop()
            except Exception as exc:
                log.warning("PredictionScheduler stop failed: %s", exc)

        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # Drain in-flight tasks
        if self._in_flight:
            log.info("Draining %d in-flight tasks...", len(self._in_flight))
            await asyncio.gather(*self._in_flight, return_exceptions=True)

        if self._cost_engine:
            await self._cost_engine.stop()

        log.info("IngestWorker stopped.")

    def _handle_signal(self) -> None:
        log.info("Shutdown signal received")
        self.shutdown_event.set()

    # ── Consumer loop ─────────────────────────────────────────────────────────

    async def _consumer_loop(self) -> None:
        """Block on BRPOP and dispatch each item to the processing pool."""
        while not self.shutdown_event.is_set():
            try:
                # BRPOP blocks up to brpop_timeout seconds
                item = await self._redis.brpop(_QUEUE_KEY, timeout=self._brpop_timeout)
                if item is None:
                    # Timeout — yield to event loop so shutdown_event can be checked
                    await asyncio.sleep(0)
                    continue
                # item = (queue_name, value) in redis-py
                raw = item[1] if isinstance(item, (list, tuple)) else item
                task = asyncio.create_task(
                    self._process_with_semaphore(raw),
                    name="ingest-span",
                )
                self._in_flight.add(task)
                task.add_done_callback(self._in_flight.discard)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Consumer loop error: %s", exc)
                await asyncio.sleep(1)  # back off on unexpected errors

    async def _process_with_semaphore(self, raw: bytes) -> None:
        async with self._semaphore:
            await self._process_one(raw)

    # ── Per-span processing pipeline ──────────────────────────────────────────

    async def _process_one(self, raw: bytes, attempt: int = 0) -> None:
        """Full processing pipeline for one span. Retries with backoff."""
        try:
            await self._pipeline(raw)
            await self._redis.incr(_METRICS_PROCESSED)
        except Exception as exc:
            if attempt < self._max_retries:
                backoff = 2 ** attempt  # 1, 2, 4 seconds
                log.warning(
                    "Span processing failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, self._max_retries, backoff, exc,
                )
                await asyncio.sleep(backoff)
                await self._process_one(raw, attempt + 1)
            else:
                log.error(
                    "Span moved to dead_letter_queue after %d attempts: %s",
                    self._max_retries, exc,
                )
                try:
                    await self._redis.lpush(_DLQ_KEY, raw)
                    await self._redis.incr(_METRICS_FAILED)
                except Exception as dlq_exc:
                    log.error("Failed to push to dead_letter_queue: %s", dlq_exc)

    async def _pipeline(self, raw: bytes) -> None:
        # ── Step 1: Parse ────────────────────────────────────────────────────
        try:
            data: dict[str, Any] = orjson.loads(raw)
        except Exception as exc:
            # Unparseable — straight to DLQ, no retry
            log.error("Cannot parse span payload (dead-lettering): %s", exc)
            await self._redis.lpush(_DLQ_KEY, raw)
            return

        missing = _REQUIRED_FIELDS - data.keys()
        if missing:
            log.error("Span missing required fields %s (dead-lettering)", missing)
            await self._redis.lpush(_DLQ_KEY, raw)
            return

        span_id_str: str = data["span_id"]
        project_id_str: str = data["project_id"]
        org_id_str: str = data["org_id"]
        provider: str = data["provider"]
        model: str = data["model"]
        status: str = data["status"]

        log.info(
            "worker: received [span=%s][proj=%s] provider=%s model=%s status=%s source=%s",
            span_id_str[:8], project_id_str[:8],
            provider, model, status, data.get("source"),
        )

        # Canonicalize model for storage so dashboards group across dated
        # snapshots (raw provider-returned id stays preserved in data["response"]).
        if self._cost_engine is not None:
            _, model = self._cost_engine.canonicalize(provider, model)
            data["model"] = model

        try:
            span_id = uuid.UUID(span_id_str)
            project_id = uuid.UUID(project_id_str)
            org_id = uuid.UUID(org_id_str)
        except (ValueError, AttributeError) as exc:
            log.error("Invalid UUID in span payload (dead-lettering): %s", exc)
            await self._redis.lpush(_DLQ_KEY, raw)
            return

        input_tokens: Optional[int] = data.get("input_tokens")
        output_tokens: Optional[int] = data.get("output_tokens")
        cached_tokens: int = data.get("cached_tokens") or 0

        # ── Step 2: Re-compute cost ──────────────────────────────────────────
        cost_usd: Optional[Decimal] = None
        if input_tokens is not None and output_tokens is not None:
            cost_usd = self._cost_engine.estimate(
                provider, model, input_tokens, output_tokens, cached_tokens
            )
        else:
            # Keep the estimate from ingest time if we can't recompute
            cost_usd = _parse_decimal(data.get("cost_usd"))

        # ── Step 3: Hallucination score ──────────────────────────────────────
        hall_score: Optional[Decimal] = None
        hall_flags: Optional[dict[str, Any]] = None

        if status == "success" and data.get("response") is not None:
            try:
                from whyllm_api.services.hallucination import HallucinationScorer
                scorer = HallucinationScorer()
                hall_score, hall_flags = scorer.score(
                    data["response"],
                    data.get("request"),
                    input_tokens,
                )
            except Exception as exc:
                log.debug("Hallucination scoring failed (non-critical): %s", exc)

        # ── Step 4: Upsert span ──────────────────────────────────────────────
        # Use ingested_at as created_at if available, else now
        created_at = _parse_dt(data.get("ingested_at")) or datetime.now(tz=timezone.utc)

        await self._upsert_span(
            span_id=span_id,
            created_at=created_at,
            project_id=project_id,
            org_id=org_id,
            data=data,
            cost_usd=cost_usd,
            hall_score=hall_score,
            hall_flags=hall_flags,
        )
        log.info(
            "worker: stored [span=%s] cost=$%s tokens=%s/%s latency=%sms hall=%s",
            span_id_str[:8],
            f"{cost_usd:.5f}" if cost_usd is not None else "—",
            input_tokens, output_tokens, data.get("latency_ms"),
            f"{hall_score:.2f}" if hall_score is not None else "—",
        )

        # ── Step 5: Trace aggregation ────────────────────────────────────────
        trace_id = _parse_uuid(data.get("trace_id"))
        if trace_id:
            await self._upsert_trace(
                trace_id=trace_id,
                project_id=project_id,
                org_id=org_id,
                data=data,
                cost_usd=cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                status=status,
                created_at=created_at,
            )

        # ── Step 6: Publish live event ───────────────────────────────────────
        channel = f"project:{project_id}:spans"
        summary = orjson.dumps({
            "span_id": span_id_str,
            "model": model,
            "provider": provider,
            "status": status,
            "cost_usd": str(cost_usd) if cost_usd is not None else None,
            "latency_ms": data.get("latency_ms"),
            "hallucination_score": str(hall_score) if hall_score is not None else None,
            "created_at": created_at.isoformat(),
        })
        try:
            await self._redis.publish(channel, summary)
        except Exception as exc:
            log.debug("Live event publish failed (non-critical): %s", exc)

    async def _upsert_span(
        self,
        span_id: uuid.UUID,
        created_at: datetime,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        data: dict[str, Any],
        cost_usd: Optional[Decimal],
        hall_score: Optional[Decimal],
        hall_flags: Optional[dict[str, Any]],
    ) -> None:
        from whyllm_api.models.span import Span

        # NOTE: total_tokens is GENERATED ALWAYS AS STORED — never include it
        values: dict[str, Any] = {
            "id": span_id,
            "created_at": created_at,
            "project_id": project_id,
            "org_id": org_id,
            "name": data.get("name"),
            "kind": data.get("kind") or "llm_call",
            "environment": data.get("environment") or "production",
            "provider": data["provider"],
            "model": data["model"],
            "status": data["status"],
            "user_id": data.get("user_id"),
            "session_id": data.get("session_id"),
            "tags": data.get("tags") or {},
            "trace_id": _parse_uuid(data.get("trace_id")),
            "parent_span_id": _parse_uuid(data.get("parent_span_id")),
            "input_tokens": data.get("input_tokens"),
            "output_tokens": data.get("output_tokens"),
            "cached_tokens": data.get("cached_tokens") or 0,
            "cost_usd": cost_usd,
            "latency_ms": data.get("latency_ms"),
            "ttft_ms": data.get("ttft_ms"),
            "proxy_overhead_ms": data.get("proxy_overhead_ms"),
            "timings": data.get("timings"),
            "error_type": data.get("error_type"),
            "error_message": data.get("error_message"),
            "request": data.get("request"),
            "response": data.get("response"),
            "hallucination_score": hall_score,
            "hallucination_flags": hall_flags if hall_flags else None,
            "source": data.get("source") or "api",
            "sdk_version": data.get("sdk_version"),
            "started_at": _parse_dt(data.get("started_at")),
            "ended_at": _parse_dt(data.get("ended_at")),
        }

        stmt = (
            pg_insert(Span)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["id", "created_at"],
                set_={
                    # Update quality fields if the worker re-processes
                    "cost_usd": cost_usd,
                    "hallucination_score": hall_score,
                    "hallucination_flags": hall_flags if hall_flags else None,
                },
            )
        )

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def _upsert_trace(
        self,
        trace_id: uuid.UUID,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        data: dict[str, Any],
        cost_usd: Optional[Decimal],
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        cached_tokens: int,
        status: str,
        created_at: datetime,
    ) -> None:
        from sqlalchemy import text

        tokens_delta = (
            (input_tokens or 0) + (output_tokens or 0) + cached_tokens
        )
        cost_delta = float(cost_usd) if cost_usd is not None else 0.0
        started_at = _parse_dt(data.get("started_at")) or created_at
        ended_at = _parse_dt(data.get("ended_at")) or created_at

        sql = text("""
            INSERT INTO traces (
                id, project_id, org_id, name, environment,
                user_id, session_id, tags, status,
                total_cost_usd, total_tokens, span_count,
                started_at, ended_at, created_at
            ) VALUES (
                :trace_id, :project_id, :org_id, :name, :environment,
                :user_id, :session_id, CAST(:tags AS jsonb), :status,
                :cost_delta, :tokens_delta, 1,
                :started_at, :ended_at, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                span_count      = traces.span_count + 1,
                total_cost_usd  = COALESCE(traces.total_cost_usd, 0) + :cost_delta,
                total_tokens    = COALESCE(traces.total_tokens, 0) + :tokens_delta,
                status          = CASE
                                    WHEN :status = 'error' THEN 'error'
                                    WHEN traces.status = 'error' THEN 'error'
                                    WHEN :status = 'timeout' THEN 'timeout'
                                    ELSE traces.status
                                  END,
                started_at      = LEAST(traces.started_at, :started_at),
                ended_at        = GREATEST(traces.ended_at, :ended_at)
        """)

        import json
        params = {
            "trace_id": str(trace_id),
            "project_id": str(project_id),
            "org_id": str(org_id),
            "name": data.get("name"),
            "environment": data.get("environment") or "production",
            "user_id": data.get("user_id"),
            "session_id": data.get("session_id"),
            "tags": json.dumps(data.get("tags") or {}),
            "status": status if status in ("success", "error", "timeout", "cancelled") else "running",
            "cost_delta": cost_delta,
            "tokens_delta": tokens_delta,
            "started_at": started_at,
            "ended_at": ended_at,
        }

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(sql, params)
            await session.commit()


# ── Module entry point ────────────────────────────────────────────────────────

async def run_worker() -> None:
    """Run the worker until SIGTERM or SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log.info("Starting whyllm IngestWorker…")

    worker = IngestWorker()
    await worker.start()

    try:
        await worker.shutdown_event.wait()
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
