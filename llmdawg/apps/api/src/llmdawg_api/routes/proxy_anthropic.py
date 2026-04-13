"""Anthropic proxy — forwards /anthropic/v1/* to api.anthropic.com.

Usage:
    # In the SDK or client code:
    client = anthropic.Anthropic(
        api_key="sk-ant-...",                      # your own Anthropic key
        base_url="http://localhost:8000/anthropic",
        default_headers={"X-LLMDawg-Key": "ld-proj-xxx"},
    )
    # LLMDawg never stores your Anthropic key — it is passed through as-is.

Differences from the OpenAI proxy:
- Auth header: x-api-key instead of Authorization
- Required header: anthropic-version: 2023-06-01
- Token fields: input_tokens / output_tokens (not prompt_tokens / completion_tokens)
- Streaming format: different event types (message_start, content_block_delta, etc.)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from llmdawg_api.middleware.api_key_auth import KeyContext, verify_api_key
from llmdawg_api.proxy.client import get_proxy_client
from llmdawg_api.proxy.utils import (
    check_budget,
    enqueue_proxy_span,
    parse_anthropic_sse,
    strip_proxy_headers,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/anthropic", tags=["proxy-anthropic"])

_ANTHROPIC_BASE = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"


@router.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_anthropic(
    path: str,
    request: Request,
    ctx: KeyContext = Depends(verify_api_key),
) -> Response:
    """Forward any Anthropic API request through the LLMDawg proxy."""
    if not request.headers.get("x-api-key"):
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key", "message": "x-api-key header with your Anthropic key is required"},
        )

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

    await check_budget(ctx.project_id)

    # x-api-key passes through from the caller; ensure anthropic-version is set
    headers = strip_proxy_headers(request.headers)
    headers.setdefault("anthropic-version", _ANTHROPIC_VERSION)
    headers["Content-Type"] = "application/json"

    upstream_url = f"{_ANTHROPIC_BASE}/v1/{path}"
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
    client = get_proxy_client()
    try:
        upstream = await client.request(method, url, headers=headers, content=body)
    except Exception as exc:
        log.warning("Anthropic proxy upstream error: %s", exc)
        raise HTTPException(status_code=502, detail={"error": "upstream_error", "message": str(exc)})

    latency_ms = int((time.perf_counter() - started_at) * 1000)

    if upstream.status_code == 200:
        try:
            resp_json = upstream.json()
            usage = resp_json.get("usage") or {}
            asyncio.create_task(enqueue_proxy_span(
                {
                    "span_id": span_id,
                    "provider": "anthropic",
                    "model": resp_json.get("model", model),
                    "status": "success",
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "latency_ms": latency_ms,
                    "request": request_body,
                    "response": resp_json,
                },
                ctx,
            ))
        except Exception as exc:
            log.debug("Failed to enqueue proxy span: %s", exc)

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
            pass
        except Exception as exc:
            log.warning("Anthropic stream proxy error: %s", exc)
            return

        asyncio.create_task(enqueue_proxy_span(
            {
                "span_id": span_id,
                **parse_anthropic_sse(accumulated, model, started_at, ttft_ms),
                "request": request_body,
            },
            ctx,
        ))

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"X-LLMDawg-Span-Id": span_id},
    )
