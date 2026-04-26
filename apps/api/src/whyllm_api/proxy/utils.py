"""Shared utilities for proxy routes.

Covers:
- Header stripping (remove whyllm-internal + hop-by-hop headers)
- Budget gate (Redis-first, <5ms, blocks request with HTTP 429 if over budget)
- Span enqueue (writes directly to Redis ingest_queue — no HTTP roundtrip)
- SSE stream parsing for OpenAI and Anthropic response formats
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
from fastapi import HTTPException

from whyllm_api.database import get_session_factory
from whyllm_api.middleware.api_key_auth import KeyContext
from whyllm_api.redis_client import get_redis

log = logging.getLogger(__name__)

# ── Header stripping ──────────────────────────────────────────────────────────

# whyllm-specific request headers that must not reach upstream providers
_WHYLLM_PREFIXES = ("x-whyllm-",)

# Hop-by-hop and content-framing headers that must be stripped on forwarding
_STRIP_HEADERS = frozenset(
    {"host", "content-length", "transfer-encoding", "connection",
     "keep-alive", "proxy-authenticate", "proxy-authorization",
     "te", "trailer", "upgrade"}
)


def strip_proxy_headers(headers: Any) -> dict[str, str]:
    """Return a clean header dict suitable for forwarding to an upstream provider."""
    result: dict[str, str] = {}
    for k, v in headers.items():
        kl = k.lower()
        if kl in _STRIP_HEADERS:
            continue
        if any(kl.startswith(prefix) for prefix in _WHYLLM_PREFIXES):
            continue
        result[k] = v
    return result


# ── Budget gate ───────────────────────────────────────────────────────────────

async def check_budget(project_id: uuid.UUID) -> None:
    """Raise HTTP 429 if the project has an active blocking budget that's exceeded.

    Fast path: only queries the DB when Redis shows non-zero spend.
    Adds < 5ms in the common case (single Redis GET).
    """
    key = f"budget:{project_id}:daily"
    try:
        spent_str = await get_redis().get(key)
        if not spent_str:
            # No spend recorded yet — budget not exceeded
            return

        spent = float(spent_str)
        if spent <= 0:
            return

        from sqlalchemy import text

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text("""
                    SELECT amount_usd FROM cost_budgets
                    WHERE project_id = :project_id
                      AND period = 'daily'
                      AND action = 'block'
                      AND is_active = true
                    ORDER BY amount_usd ASC
                    LIMIT 1
                """),
                {"project_id": str(project_id)},
            )
            row = result.fetchone()

        if row and spent >= float(row[0]):
            log.info(
                "budget: blocked [proj=%s] spent=$%.2f limit=$%.2f",
                str(project_id)[:8], spent, float(row[0]),
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "budget_exceeded",
                    "message": "Daily budget limit reached for this project.",
                    "spent_usd": spent,
                    "limit_usd": float(row[0]),
                },
                headers={"Retry-After": "3600"},
            )

    except HTTPException:
        raise
    except Exception as exc:
        # Budget gate failure is non-fatal — don't block the request
        log.warning("Budget gate check failed (non-critical): %s", exc)


# ── Span enqueue ──────────────────────────────────────────────────────────────

async def enqueue_proxy_span(span_data: dict[str, Any], ctx: KeyContext) -> None:
    """Write a proxy-captured span directly to the ingest Redis queue.

    Never raises — a failed enqueue is logged and silently dropped.
    """
    try:
        payload = orjson.dumps({
            **span_data,
            "project_id": str(ctx.project_id),
            "org_id": str(ctx.org_id),
            "key_id": str(ctx.key_id),
            "source": "proxy",
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
        })
        await get_redis().lpush("ingest_queue", payload)
        log.debug(
            "span: queued [span=%s] provider=%s status=%s",
            str(span_data.get("span_id"))[:8],
            span_data.get("provider"),
            span_data.get("status"),
        )
    except Exception as exc:
        log.warning("Proxy span enqueue failed: %s", exc)


# ── OpenAI SSE parser ─────────────────────────────────────────────────────────

def parse_openai_sse(
    chunks: list[bytes],
    model: str,
    started_at: float,
    ttft_ms: Optional[int],
) -> dict[str, Any]:
    """Parse accumulated OpenAI SSE chunks into a span payload dict."""
    content_parts: list[str] = []
    finish_reason: Optional[str] = None
    usage: dict[str, int] = {}

    for chunk in chunks:
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except Exception:
                continue

            choices = obj.get("choices") or []
            for choice in choices:
                delta = choice.get("delta") or {}
                c = delta.get("content")
                if c:
                    content_parts.append(c)
                fr = choice.get("finish_reason")
                if fr:
                    finish_reason = fr

            # Usage may appear in the last chunk
            u = obj.get("usage")
            if u:
                usage = u

    content = "".join(content_parts)
    latency_ms = int((time.perf_counter() - started_at) * 1000)

    return {
        "provider": "openai",
        "model": model,
        "status": "success" if finish_reason else "cancelled",
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms,
        "response": {
            "choices": [{
                "message": {"content": content, "role": "assistant"},
                "finish_reason": finish_reason,
            }],
            "usage": usage,
        } if content or finish_reason else None,
    }


# ── Anthropic SSE parser ──────────────────────────────────────────────────────

def parse_anthropic_sse(
    chunks: list[bytes],
    model: str,
    started_at: float,
    ttft_ms: Optional[int],
) -> dict[str, Any]:
    """Parse accumulated Anthropic SSE chunks into a span payload dict."""
    content_parts: list[str] = []
    stop_reason: Optional[str] = None
    usage: dict[str, int] = {}

    for chunk in chunks:
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            try:
                obj = json.loads(data)
            except Exception:
                continue

            event_type = obj.get("type", "")

            if event_type == "content_block_delta":
                delta = obj.get("delta") or {}
                text = delta.get("text", "")
                if text:
                    content_parts.append(text)

            elif event_type == "message_delta":
                delta = obj.get("delta") or {}
                sr = delta.get("stop_reason")
                if sr:
                    stop_reason = sr
                u = obj.get("usage") or {}
                if u:
                    usage.update(u)

            elif event_type == "message_start":
                msg = obj.get("message") or {}
                u = msg.get("usage") or {}
                if u:
                    usage.update(u)

    content = "".join(content_parts)
    latency_ms = int((time.perf_counter() - started_at) * 1000)

    return {
        "provider": "anthropic",
        "model": model,
        "status": "success" if stop_reason else "cancelled",
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms,
        "response": {
            "content": [{"type": "text", "text": content}],
            "usage": usage,
            "stop_reason": stop_reason,
        } if content or stop_reason else None,
    }
