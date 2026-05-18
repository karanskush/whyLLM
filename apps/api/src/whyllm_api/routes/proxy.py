"""Unified LLM proxy — forwards /proxy/* to the project's configured upstream.

Replaces the separate proxy_openai / proxy_azure / proxy_anthropic routes.
Provider is inferred from the upstream base URL at onboarding and stored on
the project row; the proxy just swaps the host and forwards verbatim.

Usage (whatever the customer's SDK expects — the version / path shape rides
on the request, we never touch it):

    # OpenAI customer:
    client = OpenAI(
        api_key="sk-their-key",                           # pass-through
        base_url="http://localhost:8000/proxy/v1",
        default_headers={"X-whyllm-Key": "wl-prod_xxx"},
    )

    # Azure customer:
    client = AzureOpenAI(
        azure_endpoint="http://localhost:8000/proxy",
        api_key="their-azure-key",                        # pass-through
        api_version="2024-10-21",                         # pass-through
        default_headers={"X-whyllm-Key": "wl-prod_xxx"},
    )

    # Anthropic customer:
    client = Anthropic(
        api_key="sk-ant-their-key",                       # pass-through
        base_url="http://localhost:8000/proxy",
        default_headers={"X-whyllm-Key": "wl-prod_xxx"},
    )

whyllm never stores the customer's provider key — it passes through in whichever
header the customer's SDK already set (Authorization, api-key, x-api-key).

Span lifecycle guarantee
------------------------
*Every* request produces a span — success, upstream 4xx/5xx, connection error,
or mid-stream failure. The span's `status` / `error_type` / `error_message`
fields tell the full story. Observability is never a silent cliff.

Optional request headers the customer may set for richer traces (stripped
before forwarding to upstream):
  X-whyllm-User-Id     → span.user_id
  X-whyllm-Session-Id  → span.session_id
  X-whyllm-Trace-Id    → span.trace_id          (UUID)
  X-whyllm-Parent-Id   → span.parent_span_id    (UUID)
  X-whyllm-Name        → span.name
  X-whyllm-Tags        → span.tags              (JSON or "k=v,k=v")
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import text

from whyllm_api.database import get_session_factory
from whyllm_api.middleware.api_key_auth import KeyContext, verify_api_key
from whyllm_api.proxy.client import get_proxy_client
from whyllm_api.proxy.utils import (
    check_budget,
    enqueue_proxy_span,
    parse_anthropic_sse,
    parse_openai_sse,
    strip_proxy_headers,
)
from whyllm_api.redis_client import get_redis

log = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy", tags=["proxy"])

_UPSTREAM_CACHE_TTL = 60  # seconds — short TTL so PATCH takes effect quickly
_ANTHROPIC_VERSION = "2023-06-01"

# Cap stored error bodies so we don't shove 5MB error HTML into JSONB
_MAX_ERROR_BODY = 2048


# ── Provider inference ────────────────────────────────────────────────────────

def infer_provider(base_url: str) -> str:
    """Classify the upstream provider from its hostname.

    Falls back to 'custom' for self-hosted / OpenAI-compatible endpoints.
    """
    host = (urlparse(base_url).hostname or "").lower()
    if host.endswith(".openai.azure.com"):
        return "azure"
    if host == "api.openai.com":
        return "openai"
    if host == "api.anthropic.com":
        return "anthropic"
    if "bedrock" in host and host.endswith(".amazonaws.com"):
        return "bedrock"
    return "custom"


# ── Upstream lookup ───────────────────────────────────────────────────────────

async def _load_upstream(project_id: uuid.UUID) -> tuple[str, str]:
    """Return (base_url, provider) for the project. 60s Redis cache."""
    pid8 = str(project_id)[:8]
    cache_key = f"upstream:{project_id}"
    try:
        cached = await get_redis().get(cache_key)
        if cached:
            data = json.loads(cached)
            log.debug(
                "upstream: cache hit [proj=%s] %s @ %s",
                pid8, data["provider"], data["base_url"],
            )
            return data["base_url"], data["provider"]
    except Exception as exc:
        log.warning("Upstream cache read failed: %s", exc)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT upstream_base_url, upstream_provider
                FROM projects
                WHERE id = :id
            """),
            {"id": str(project_id)},
        )
        row = result.fetchone()

    if not row or not row[0]:
        log.info("upstream: not configured [proj=%s] -> 424", pid8)
        raise HTTPException(
            status_code=424,
            detail={
                "error": "upstream_not_configured",
                "message": (
                    "This project has no upstream LLM endpoint configured. "
                    "Set one in the whyllm dashboard under Settings → Upstream."
                ),
            },
        )

    base_url, provider = row[0], row[1] or infer_provider(row[0])
    log.info("upstream: db resolved [proj=%s] %s @ %s", pid8, provider, base_url)
    try:
        await get_redis().setex(
            cache_key,
            _UPSTREAM_CACHE_TTL,
            json.dumps({"base_url": base_url, "provider": provider}),
        )
    except Exception as exc:
        log.warning("Upstream cache write failed: %s", exc)

    return base_url, provider


async def invalidate_upstream_cache(project_id: uuid.UUID) -> None:
    """Drop the cached upstream for a project after a PATCH."""
    try:
        await get_redis().delete(f"upstream:{project_id}")
    except Exception as exc:
        log.debug("Upstream cache invalidate failed (non-critical): %s", exc)


# ── Customer-supplied span metadata ───────────────────────────────────────────

def _parse_tags(raw: Optional[str]) -> dict[str, Any]:
    """Accept tags as a JSON object or a `k=v,k=v` string."""
    if not raw:
        return {}
    raw = raw.strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            k = k.strip()
            if k:
                out[k] = v.strip()
    return out


def _uuid_or_none(s: Optional[str]) -> Optional[str]:
    """Return a canonical UUID string, or None if the input isn't a UUID."""
    if not s:
        return None
    try:
        return str(uuid.UUID(s))
    except (ValueError, AttributeError, TypeError):
        return None


def _extract_span_meta(request: Request) -> dict[str, Any]:
    """Pull X-whyllm-* span metadata out of incoming headers."""
    h = request.headers
    return {
        "user_id": h.get("x-whyllm-user-id"),
        "session_id": h.get("x-whyllm-session-id"),
        "trace_id": _uuid_or_none(h.get("x-whyllm-trace-id")),
        "parent_span_id": _uuid_or_none(h.get("x-whyllm-parent-id")),
        "name": h.get("x-whyllm-name"),
        "tags": _parse_tags(h.get("x-whyllm-tags")),
    }


# ── Route ─────────────────────────────────────────────────────────────────────

@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(
    full_path: str,
    request: Request,
    ctx: KeyContext = Depends(verify_api_key),
) -> Response:
    # ── Timing ───────────────────────────────────────────────────────────────
    # request_at: function entry (proxy's pre-forward work starts here)
    # started_at: right before httpx dispatch — latency_ms and ttft_ms are
    #   measured from this point so they represent *upstream* time only.
    # proxy_overhead_ms = (started_at - request_at) captures the whyllm tax.
    request_at = time.perf_counter()
    started_at_dt = datetime.now(tz=timezone.utc)

    base_url, provider = await _load_upstream(ctx.project_id)

    body = await request.body()
    body_json: dict[str, Any] = {}
    if body:
        try:
            body_json = orjson.loads(body)
        except Exception:
            pass

    model = body_json.get("model") or _model_from_path(full_path, provider) or "unknown"
    is_stream = bool(body_json.get("stream", False))
    span_id = str(uuid.uuid4())
    span_meta = _extract_span_meta(request)

    log.info(
        "proxy: %s /proxy/%s [proj=%s][span=%s][env=%s] provider=%s model=%s stream=%s body=%dB",
        request.method, full_path, str(ctx.project_id)[:8], span_id[:8],
        ctx.environment, provider, model, is_stream, len(body),
    )

    # Budget gate — raises 429 if exceeded. No span enqueued: the call never
    # happened, so there's no trace to record.
    await check_budget(ctx.project_id)

    headers = strip_proxy_headers(request.headers)
    headers["Content-Type"] = "application/json"
    if provider == "anthropic":
        headers.setdefault("anthropic-version", _ANTHROPIC_VERSION)

    upstream_url = f"{base_url.rstrip('/')}/{full_path.lstrip('/')}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    # Latency clock starts now — everything before this is proxy overhead.
    started_at = time.perf_counter()
    proxy_overhead_ms = int((started_at - request_at) * 1000)

    span_base: dict[str, Any] = {
        "span_id": span_id,
        "provider": provider,
        "model": model,
        "kind": "llm_call",
        "environment": ctx.environment,
        "started_at": started_at_dt.isoformat(),
        "proxy_overhead_ms": proxy_overhead_ms,
        "request": body_json or None,
        **span_meta,
    }
    # Default span.name to the derived endpoint label so the /dashboard/traces
    # groups "chat.completions" / "embeddings" / "messages" even when the
    # caller hasn't explicitly set X-whyllm-Name.
    if not span_base.get("name"):
        span_base["name"] = _endpoint_from_path(full_path)

    if is_stream:
        return await _stream_response(
            upstream_url, request.method, headers, body,
            ctx, provider, started_at, span_base,
        )
    return await _non_stream_response(
        upstream_url, request.method, headers, body,
        ctx, provider, started_at, span_base,
    )


def _model_from_path(full_path: str, provider: str) -> Optional[str]:
    """Azure encodes the deployment name in the URL path — extract it."""
    if provider != "azure":
        return None
    parts = full_path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "openai" and parts[1] == "deployments":
        return parts[2]
    return None


def _endpoint_from_path(full_path: str) -> str:
    """Normalize an upstream URL path into a stable endpoint label.

    This becomes ``span.name`` when the caller didn't supply X-whyllm-Name, and
    the dashboard groups spans by it so all hits of the same endpoint cluster.

    Examples:
        /v1/chat/completions                                 -> chat.completions
        /v1/embeddings                                       -> embeddings
        /v1/messages                                         -> messages
        /openai/deployments/gpt-5-mini/chat/completions      -> chat.completions
        /openai/deployments/text-embedding-3-small/embeddings -> embeddings
    """
    parts = full_path.strip("/").split("/")
    # Strip leading version prefix (v1, v2, v2beta, ...)
    if parts and parts[0] and parts[0][0] == "v" and parts[0][1:2].isdigit():
        parts = parts[1:]
    # Azure encodes the deployment in the path — skip /openai/deployments/<dep>/
    if len(parts) >= 3 and parts[0] == "openai" and parts[1] == "deployments":
        parts = parts[3:]
    if not parts:
        return "unknown"
    return ".".join(parts)


# ── Response handlers ─────────────────────────────────────────────────────────

async def _non_stream_response(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes,
    ctx: KeyContext,
    provider: str,
    started_at: float,
    span_base: dict[str, Any],
) -> Response:
    span_id = span_base["span_id"]
    client = get_proxy_client()

    log.info("proxy: forward %s %s [span=%s]", method, url, span_id[:8])

    # ── Upstream request, catching any transport error ───────────────────────
    try:
        upstream = await client.request(method, url, headers=headers, content=body)
    except httpx.HTTPError as exc:
        # Connection refused, DNS failure, read timeout, TLS handshake fail…
        # Emit an error span then surface 502 to the caller.
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        log.warning(
            "proxy: transport error [span=%s] %s: %s (latency=%dms)",
            span_id[:8], exc.__class__.__name__, exc, latency_ms,
        )
        asyncio.create_task(enqueue_proxy_span(
            {
                **span_base,
                "status": "error",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc)[:_MAX_ERROR_BODY],
                "latency_ms": latency_ms,
                "ended_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            ctx,
        ))
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_error", "message": str(exc)},
            headers={"X-whyllm-Span-Id": span_id},
        )

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    ended_at_dt = datetime.now(tz=timezone.utc)

    # Try to parse JSON once — used by both success and error paths.
    resp_json: Optional[dict[str, Any]] = None
    try:
        resp_json = upstream.json()
    except Exception:
        pass

    provider_timings = _extract_provider_timings(upstream.headers, provider)

    if 200 <= upstream.status_code < 300:
        usage = (resp_json or {}).get("usage") or {}
        # OpenAI/Azure: prompt_tokens/completion_tokens. Anthropic: input_tokens/output_tokens.
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        # Non-streaming: provider_processing covers the whole upstream round
        # trip server-side, so network ≈ latency − provider_processing.
        ppm = provider_timings.get("provider_processing_ms")
        if ppm is not None:
            provider_timings["network_rtt_ms"] = max(0, latency_ms - int(ppm))
        log.info(
            "proxy: response %d [span=%s] overhead=%sms latency=%dms provider=%sms tokens=%s/%s model=%s",
            upstream.status_code, span_id[:8],
            span_base.get("proxy_overhead_ms"), latency_ms,
            ppm if ppm is not None else "—",
            input_tokens, output_tokens,
            (resp_json or {}).get("model", span_base["model"]),
        )
        asyncio.create_task(enqueue_proxy_span(
            {
                **span_base,
                "model": (resp_json or {}).get("model", span_base["model"]),
                "status": "success",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
                "ended_at": ended_at_dt.isoformat(),
                "response": resp_json,
                "timings": provider_timings or None,
            },
            ctx,
        ))
    else:
        # Upstream returned 4xx/5xx — still a trace, just a failed one.
        err_type, err_msg = _extract_upstream_error(resp_json, upstream.content, upstream.status_code)
        log.info(
            "proxy: response %d [span=%s] latency=%dms err=%s",
            upstream.status_code, span_id[:8], latency_ms, err_type,
        )
        asyncio.create_task(enqueue_proxy_span(
            {
                **span_base,
                "status": "error",
                "error_type": err_type,
                "error_message": err_msg,
                "latency_ms": latency_ms,
                "ended_at": ended_at_dt.isoformat(),
                "response": resp_json,
                "timings": provider_timings or None,
            },
            ctx,
        ))

    # Pass the upstream response through unchanged (plus our span-id header).
    passthrough_headers = dict(upstream.headers)
    passthrough_headers["X-whyllm-Span-Id"] = span_id
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=passthrough_headers,
        media_type=upstream.headers.get("content-type"),
    )


async def _stream_response(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes,
    ctx: KeyContext,
    provider: str,
    started_at: float,
    span_base: dict[str, Any],
) -> Response:
    """Open the upstream stream.

    If the upstream's initial response is an error (non-2xx), fully drain it
    and return a *non-streaming* Response with the error payload — that's what
    real providers do, and wrapping a JSON error in StreamingResponse confuses
    client SDKs. Otherwise return a StreamingResponse that pipes chunks
    through and enqueues a span when the stream finishes or the client drops.
    """
    span_id = span_base["span_id"]
    client = get_proxy_client()

    log.info("proxy: forward (stream) %s %s [span=%s]", method, url, span_id[:8])

    # Open the stream manually so we can inspect status before deciding how
    # to wrap the response. The context manager is closed either here (on
    # error short-circuit) or from inside the generator (on stream completion).
    stream_cm = client.stream(method, url, headers=headers, content=body)
    try:
        upstream = await stream_cm.__aenter__()
    except httpx.HTTPError as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        log.warning(
            "proxy: stream transport error [span=%s] %s: %s (latency=%dms)",
            span_id[:8], exc.__class__.__name__, exc, latency_ms,
        )
        asyncio.create_task(enqueue_proxy_span(
            {
                **span_base,
                "status": "error",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc)[:_MAX_ERROR_BODY],
                "latency_ms": latency_ms,
                "ended_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            ctx,
        ))
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_error", "message": str(exc)},
            headers={"X-whyllm-Span-Id": span_id},
        )

    # ── Error short-circuit: drain the body, return as non-streaming ────────
    if upstream.status_code >= 400:
        try:
            err_bytes = b""
            async for chunk in upstream.aiter_bytes():
                err_bytes += chunk
        finally:
            await stream_cm.__aexit__(None, None, None)

        try:
            err_json = orjson.loads(err_bytes) if err_bytes else None
        except Exception:
            err_json = None
        error_type, error_message = _extract_upstream_error(
            err_json, err_bytes, upstream.status_code,
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        log.info(
            "proxy: stream→error %d [span=%s] latency=%dms err=%s",
            upstream.status_code, span_id[:8], latency_ms, error_type,
        )
        err_provider_timings = _extract_provider_timings(upstream.headers, provider)
        asyncio.create_task(enqueue_proxy_span(
            {
                **span_base,
                "status": "error",
                "error_type": error_type,
                "error_message": error_message,
                "latency_ms": latency_ms,
                "ended_at": datetime.now(tz=timezone.utc).isoformat(),
                "response": err_json,
                "timings": err_provider_timings or None,
            },
            ctx,
        ))
        passthrough_headers = dict(upstream.headers)
        passthrough_headers["X-whyllm-Span-Id"] = span_id
        return Response(
            content=err_bytes,
            status_code=upstream.status_code,
            headers=passthrough_headers,
            media_type=upstream.headers.get("content-type"),
        )

    # ── Normal streaming path ───────────────────────────────────────────────
    accumulated: list[bytes] = []
    chunk_arrivals_ms: list[int] = []
    chunk_sizes: list[int] = []
    ttft_ms: Optional[int] = None
    # Provider headers are already in hand here (before the body streams) —
    # snapshot processing_ms and request_id now.
    provider_timings = _extract_provider_timings(upstream.headers, provider)
    # Anthropic SSE is its own format; everything else uses OpenAI-style SSE.
    parse = parse_anthropic_sse if provider == "anthropic" else parse_openai_sse

    async def generator():
        nonlocal ttft_ms
        status: str = "success"
        error_type: Optional[str] = None
        error_message: Optional[str] = None

        try:
            async for chunk in upstream.aiter_bytes():
                if chunk:
                    now_ms = int((time.perf_counter() - started_at) * 1000)
                    if ttft_ms is None:
                        ttft_ms = now_ms
                    chunk_arrivals_ms.append(now_ms)
                    chunk_sizes.append(len(chunk))
                    accumulated.append(chunk)
                    yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            status = "cancelled"
        except httpx.HTTPError as exc:
            status = "error"
            error_type = exc.__class__.__name__
            error_message = str(exc)[:_MAX_ERROR_BODY]
            log.warning("Proxy stream error (%s): %s", provider, exc)
        except Exception as exc:
            status = "error"
            error_type = exc.__class__.__name__
            error_message = str(exc)[:_MAX_ERROR_BODY]
            log.warning("Proxy stream unexpected error (%s): %s", provider, exc)
        finally:
            try:
                await stream_cm.__aexit__(None, None, None)
            except Exception as exc:
                log.debug("Stream close failed: %s", exc)

            ended_at_dt = datetime.now(tz=timezone.utc)
            latency_ms = int((time.perf_counter() - started_at) * 1000)

            # Merge provider timings with derived stream-rhythm stats.
            # For streaming: provider_processing_ms covers server-side *prefill*
            # (headers flush before body stream), so:
            #   network_rtt ≈ ttft − provider_processing
            #   generation  ≈ latency − ttft
            full_timings: dict[str, Any] = dict(provider_timings)
            rhythm = _analyse_chunk_timings(chunk_arrivals_ms, chunk_sizes)
            full_timings.update(rhythm)
            ppm = full_timings.get("provider_processing_ms")
            if ppm is not None and ttft_ms is not None:
                full_timings["network_rtt_ms"] = max(0, ttft_ms - int(ppm))
            if status == "error" or (status == "cancelled" and not accumulated):
                log.info(
                    "proxy: stream complete [span=%s] status=%s ttft=%sms latency=%dms provider=%sms chunks=%d stalls=%d%s",
                    span_id[:8], status, ttft_ms, latency_ms,
                    ppm if ppm is not None else "—",
                    len(chunk_arrivals_ms),
                    full_timings.get("stall_count", 0),
                    f" err={error_type}" if error_type else "",
                )
                asyncio.create_task(enqueue_proxy_span(
                    {
                        **span_base,
                        "status": status,
                        "error_type": error_type,
                        "error_message": error_message,
                        "latency_ms": latency_ms,
                        "ttft_ms": ttft_ms,
                        "ended_at": ended_at_dt.isoformat(),
                        "timings": full_timings or None,
                    },
                    ctx,
                ))
            else:
                parsed = parse(accumulated, span_base["model"], started_at, ttft_ms)
                parsed["provider"] = provider
                log.info(
                    "proxy: stream complete [span=%s] status=%s ttft=%sms latency=%dms provider=%sms chunks=%d stalls=%d tokens=%s/%s",
                    span_id[:8], parsed.get("status"), ttft_ms, latency_ms,
                    ppm if ppm is not None else "—",
                    len(chunk_arrivals_ms),
                    full_timings.get("stall_count", 0),
                    parsed.get("input_tokens"), parsed.get("output_tokens"),
                )
                asyncio.create_task(enqueue_proxy_span(
                    {
                        **span_base,
                        **parsed,
                        "ended_at": ended_at_dt.isoformat(),
                        "timings": full_timings or None,
                    },
                    ctx,
                ))

    return StreamingResponse(
        generator(),
        media_type=upstream.headers.get("content-type", "text/event-stream"),
        headers={"X-whyllm-Span-Id": span_id},
    )


# ── Upstream timing extraction ────────────────────────────────────────────────

# Providers quietly emit their own processing time in response headers. We parse
# and store these so the dashboard can isolate *network RTT* from *provider
# server-side time* — a breakdown the customer's SDK never surfaces.

_DUR_RE = re.compile(r"dur\s*=\s*([0-9.]+)", re.IGNORECASE)


def _parse_server_timing(raw: str) -> Optional[float]:
    """Pull a total ms value out of a W3C Server-Timing header.

    Prefers a metric named "total"; otherwise returns the largest dur seen.
    Format: ``name;param=value;dur=N, name2;dur=N2, ...``
    """
    best: Optional[float] = None
    prefer_total: Optional[float] = None
    for metric in raw.split(","):
        parts = [p.strip() for p in metric.split(";") if p.strip()]
        if not parts:
            continue
        name = parts[0].lower()
        dur: Optional[float] = None
        for p in parts[1:]:
            m = _DUR_RE.fullmatch(p)
            if m:
                try:
                    dur = float(m.group(1))
                except ValueError:
                    dur = None
                break
        if dur is None:
            continue
        if name == "total":
            prefer_total = dur
        if best is None or dur > best:
            best = dur
    return prefer_total if prefer_total is not None else best


def _extract_provider_timings(
    headers: Any, provider: str,
) -> dict[str, Any]:
    """Pull provider-reported timing and identifiers out of upstream headers.

    Returns a dict — empty if nothing useful found. Never raises.
    """
    out: dict[str, Any] = {}
    try:
        h = {k.lower(): v for k, v in headers.items()}
    except Exception:
        return out

    # Server-side processing time as the provider measures it.
    for key in (
        "openai-processing-ms",           # OpenAI direct
        "x-ms-azure-processing-ms",       # Azure OpenAI via APIM
        "apim-request-total-time-ms",     # Azure APIM fallback
    ):
        v = h.get(key)
        if v:
            try:
                out["provider_processing_ms"] = int(float(v))
                break
            except (TypeError, ValueError):
                pass

    # W3C Server-Timing fallback (Cloudflare / generic edges emit this)
    if "provider_processing_ms" not in out:
        st = h.get("server-timing")
        if st:
            v = _parse_server_timing(st)
            if v is not None:
                out["provider_processing_ms"] = int(v)

    # Request correlation id (invaluable for provider support tickets)
    req_id = (
        h.get("x-request-id")
        or h.get("request-id")
        or h.get("apim-request-id")
        or h.get("openai-request-id")
    )
    if req_id:
        out["provider_request_id"] = str(req_id)[:128]

    # Region hints (Azure / Cloudflare)
    region = h.get("x-ms-region") or h.get("cf-ray")
    if region:
        out["provider_region"] = str(region)[:64]

    # Rate-limit remaining token — surfaces budget pressure in the UI
    rl_tokens = h.get("x-ratelimit-remaining-tokens") or h.get(
        "anthropic-ratelimit-tokens-remaining"
    )
    if rl_tokens:
        try:
            out["rate_limit_remaining_tokens"] = int(float(rl_tokens))
        except (TypeError, ValueError):
            pass
    rl_requests = h.get("x-ratelimit-remaining-requests") or h.get(
        "anthropic-ratelimit-requests-remaining"
    )
    if rl_requests:
        try:
            out["rate_limit_remaining_requests"] = int(float(rl_requests))
        except (TypeError, ValueError):
            pass

    # Rate-limit *ceilings* and reset windows — paired with the "remaining"
    # values above, these let the prediction engine forecast exhaustion
    # (services/predictions/rate_limit.py) instead of just reporting it.
    rl_limit_tokens = h.get("x-ratelimit-limit-tokens") or h.get(
        "anthropic-ratelimit-tokens-limit"
    )
    if rl_limit_tokens:
        try:
            out["rate_limit_limit_tokens"] = int(float(rl_limit_tokens))
        except (TypeError, ValueError):
            pass
    rl_limit_requests = h.get("x-ratelimit-limit-requests") or h.get(
        "anthropic-ratelimit-requests-limit"
    )
    if rl_limit_requests:
        try:
            out["rate_limit_limit_requests"] = int(float(rl_limit_requests))
        except (TypeError, ValueError):
            pass
    # Reset windows are provider-formatted durations (e.g. "6m0s", "1.5s") —
    # stored verbatim, parsed downstream only if needed.
    rl_reset = h.get("x-ratelimit-reset-tokens") or h.get(
        "anthropic-ratelimit-tokens-reset"
    )
    if rl_reset:
        out["rate_limit_reset_tokens"] = str(rl_reset)[:32]

    if provider:
        out["provider"] = provider
    return out


# ── Streaming rhythm analysis ─────────────────────────────────────────────────

_STALL_THRESHOLD_MS = 500           # gap > this = "the model paused"
_TIMELINE_MAX_POINTS = 120          # downsample target for the sparkline


def _percentile(sorted_vals: list[int], p: float) -> int:
    """Nearest-rank percentile on an already-sorted list of ints."""
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def _analyse_chunk_timings(
    arrivals_ms: list[int],
    chunk_sizes: list[int],
) -> dict[str, Any]:
    """Derive jitter, stalls, and a downsampled timeline from raw chunk arrivals.

    `arrivals_ms` is absolute ms-from-forward for each non-empty chunk. Returns
    a dict that's JSON-safe and bounded in size (≤ _TIMELINE_MAX_POINTS entries).
    """
    n = len(arrivals_ms)
    if n == 0:
        return {}

    out: dict[str, Any] = {
        "chunk_count": n,
        "first_chunk_ms": arrivals_ms[0],
        "last_chunk_ms": arrivals_ms[-1],
    }

    if n >= 2:
        gaps = [arrivals_ms[i] - arrivals_ms[i - 1] for i in range(1, n)]
        gaps_sorted = sorted(gaps)
        out["inter_chunk_p50_ms"] = _percentile(gaps_sorted, 0.50)
        out["inter_chunk_p95_ms"] = _percentile(gaps_sorted, 0.95)
        out["inter_chunk_max_ms"] = gaps_sorted[-1]

        stalls: list[dict[str, int]] = []
        stall_total_ms = 0
        for i, g in enumerate(gaps, start=1):
            if g >= _STALL_THRESHOLD_MS:
                stalls.append({"at_ms": arrivals_ms[i - 1], "duration_ms": g})
                stall_total_ms += g
        if stalls:
            out["stalls"] = stalls[:20]        # cap to keep JSONB compact
            out["stall_count"] = len(stalls)
            out["stall_total_ms"] = stall_total_ms

    # Downsampled timeline for a sparkline — bucket chunks into ≤ MAX points.
    if n <= _TIMELINE_MAX_POINTS:
        timeline = [[arrivals_ms[i], chunk_sizes[i]] for i in range(n)]
    else:
        bucket = (n + _TIMELINE_MAX_POINTS - 1) // _TIMELINE_MAX_POINTS
        timeline = []
        for i in range(0, n, bucket):
            window = arrivals_ms[i : i + bucket]
            window_sizes = chunk_sizes[i : i + bucket]
            timeline.append([window[-1], sum(window_sizes)])
    out["timeline"] = timeline
    return out


# ── Upstream error extraction ─────────────────────────────────────────────────

def _extract_upstream_error(
    resp_json: Optional[dict[str, Any]],
    content: bytes,
    status_code: int,
) -> tuple[str, str]:
    """Best-effort parse of the upstream's error body into (type, message)."""
    default_type = f"upstream_{status_code}"

    if isinstance(resp_json, dict):
        err = resp_json.get("error")
        # OpenAI / Azure: {"error": {"type": "...", "message": "..."}}
        if isinstance(err, dict):
            return (
                str(err.get("type") or err.get("code") or default_type),
                str(err.get("message") or "")[:_MAX_ERROR_BODY],
            )
        # Anthropic: {"type": "error", "error": {"type": "...", "message": "..."}}
        if resp_json.get("type") == "error":
            return default_type, str(err or resp_json)[:_MAX_ERROR_BODY]
        # Bedrock / custom: {"message": "..."}
        if "message" in resp_json:
            return default_type, str(resp_json["message"])[:_MAX_ERROR_BODY]

    # Fall back to raw body (truncated)
    try:
        msg = content.decode("utf-8", errors="replace")[:_MAX_ERROR_BODY]
    except Exception:
        msg = f"(non-text body, {len(content)} bytes)"
    return default_type, msg
