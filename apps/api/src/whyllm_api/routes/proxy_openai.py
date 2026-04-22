"""OpenAI proxy — forwards /openai/v1/* to api.openai.com.

Usage:
    # In the SDK or client code:
    client = OpenAI(
        api_key="sk-...",                          # your own OpenAI key
        base_url="http://localhost:8000/openai",
        default_headers={"X-whyllm-Key": "ld-proj-xxx"},
    )
    # whyllm never stores your OpenAI key — it is passed through as-is.

Features:
- Forwards all HTTP methods (GET, POST, DELETE, PATCH, PUT)
- Strips whyllm-internal and hop-by-hop headers before forwarding
- Passes the caller's Authorization header through to OpenAI unchanged
- Non-streaming: captures full response, enqueues span, returns to client
- Streaming: zero-buffer forwarding (chunks yielded immediately), then
  parses accumulated SSE in a background task to build the span
- Budget gate: checks Redis spend key before forwarding (< 5ms overhead)
- On upstream 4xx/5xx: passes response through unchanged (no retry)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from whyllm_api.middleware.api_key_auth import KeyContext, verify_api_key
from whyllm_api.proxy.client import get_proxy_client
from whyllm_api.proxy.utils import (
    check_budget,
    enqueue_proxy_span,
    parse_openai_sse,
    strip_proxy_headers,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/openai", tags=["proxy-openai"])

_OPENAI_BASE = "https://api.openai.com"


@router.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_openai(
    path: str,
    request: Request,
    ctx: KeyContext = Depends(verify_api_key),
) -> Response:
    """Forward any OpenAI API request through the whyllm proxy."""
    if not request.headers.get("authorization"):
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key", "message": "Authorization header with your OpenAI key is required"},
        )

    # Parse request body
    body = await request.body()
    body_json: dict[str, Any] = {}
    if body:
        try:
            body_json = orjson.loads(body)
        except Exception:
            pass

    model = body_json.get("model", "unknown")
    is_stream = bool(body_json.get("stream", False))
    started_at = time.perf_counter()

    # Budget gate — raises 429 if exceeded
    await check_budget(ctx.project_id)

    # Build forwarding headers — Authorization passes through from the caller
    headers = strip_proxy_headers(request.headers)
    headers["Content-Type"] = "application/json"

    upstream_url = f"{_OPENAI_BASE}/v1/{path}"
    span_id = str(uuid.uuid4())

    if is_stream:
        return await _stream_response(
            upstream_url, request.method, headers, body,
            ctx, model, started_at, span_id, body_json,
        )
    return await _non_stream_response(
        upstream_url, request.method, headers, body,
        ctx, model, started_at, span_id, body_json,
    )


async def _non_stream_response(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes,
    ctx: KeyContext,
    model: str,
    started_at: float,
    span_id: str,
    request_body: dict[str, Any],
) -> Response:
    """Forward a non-streaming request and capture the full response."""
    client = get_proxy_client()
    try:
        upstream = await client.request(method, url, headers=headers, content=body)
    except Exception as exc:
        log.warning("OpenAI proxy upstream error: %s", exc)
        raise HTTPException(status_code=502, detail={"error": "upstream_error", "message": str(exc)})

    latency_ms = int((time.perf_counter() - started_at) * 1000)

    # Build span from the response if it looks like a chat completions response
    if upstream.status_code == 200:
        try:
            resp_json = upstream.json()
            usage = resp_json.get("usage") or {}
            asyncio.create_task(enqueue_proxy_span(
                {
                    "span_id": span_id,
                    "provider": "openai",
                    "model": resp_json.get("model", model),
                    "status": "success",
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "latency_ms": latency_ms,
                    "request": request_body,
                    "response": resp_json,
                },
                ctx,
            ))
        except Exception as exc:
            log.debug("Failed to enqueue proxy span: %s", exc)

    # Pass through the upstream response unchanged
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


async def _stream_response(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes,
    ctx: KeyContext,
    model: str,
    started_at: float,
    span_id: str,
    request_body: dict[str, Any],
) -> StreamingResponse:
    """Forward a streaming request, yielding chunks immediately to the client."""
    client = get_proxy_client()
    accumulated: list[bytes] = []
    ttft_ms: Optional[int] = None

    async def generator():
        nonlocal ttft_ms
        try:
            async with client.stream(method, url, headers=headers, content=body) as upstream:
                async for chunk in upstream.aiter_bytes():
                    if chunk:
                        if ttft_ms is None:
                            ttft_ms = int((time.perf_counter() - started_at) * 1000)
                        accumulated.append(chunk)
                        yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected — still enqueue partial span
            pass
        except Exception as exc:
            log.warning("OpenAI stream proxy error: %s", exc)
            return

        # Parse and enqueue span in background after stream completes
        asyncio.create_task(enqueue_proxy_span(
            {
                "span_id": span_id,
                **parse_openai_sse(accumulated, model, started_at, ttft_ms),
                "request": request_body,
            },
            ctx,
        ))

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"X-whyllm-Span-Id": span_id},
    )
