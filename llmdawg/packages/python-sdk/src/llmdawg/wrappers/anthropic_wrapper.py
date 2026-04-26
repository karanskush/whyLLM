"""Anthropic client patcher — monkey-patches messages.create in-place.

Captures:
  - Full request kwargs (system prompt, tools, tool_choice, metadata, etc.)
  - Full response (tool_use blocks, text content, stop_reason)
  - Cache tokens (cache_read_input_tokens, cache_creation_input_tokens)
  - Streaming: full system prompt preserved, TTFT, accumulated content
  - Application context (user_id, session_id, tags, trace_id)
"""

from __future__ import annotations

import functools
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from llmdawg.context import get_context

if TYPE_CHECKING:
    from llmdawg.sender import SpanSender

log = logging.getLogger(__name__)

# Anthropic stop_reason → LLMDawg status
_STATUS_MAP = {
    "end_turn": "success",
    "max_tokens": "success",
    "tool_use": "success",
    "stop_sequence": "success",
    None: "success",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_serialize(obj: Any) -> Any:
    """Best-effort conversion of an object to a JSON-safe dict."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return {k: _safe_serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
        except Exception:
            pass
    return str(obj)


def _extract_cache_tokens(usage: Any) -> int:
    """Extract total cached tokens from Anthropic's usage object.

    Anthropic reports cache_read_input_tokens (tokens read from cache)
    and cache_creation_input_tokens (tokens written to cache). Both
    represent cache-priced tokens.
    """
    if usage is None:
        return 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return cache_read + cache_create


def _extract_content_blocks(content_list: Any) -> dict[str, Any]:
    """Parse all content blocks (text + tool_use) into structured output."""
    if not content_list:
        return {"content": None, "tool_calls": None}

    texts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in content_list:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", None)
            if text:
                texts.append(text)
        elif block_type == "tool_use":
            tool_calls.append({
                "id": getattr(block, "id", None),
                "name": getattr(block, "name", None),
                "input": _safe_serialize(getattr(block, "input", None)),
            })

    return {
        "content": "".join(texts) if texts else None,
        "tool_calls": tool_calls if tool_calls else None,
    }


def _build_full_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Capture the full request kwargs."""
    req: dict[str, Any] = {}
    for key, val in kwargs.items():
        if key == "stream":
            continue
        req[key] = _safe_serialize(val)
    return req


# ── Span builders ───────────────────────────────────────────────────────────

def _build_span(
    request_kwargs: dict[str, Any],
    response: Any,
    started_at: datetime,
    ended_at: datetime,
    ttft_ms: int | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    """Build a span dict from Anthropic request/response objects."""
    model = request_kwargs.get("model", "unknown")
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)

    span: dict[str, Any] = {
        "span_id": str(uuid.uuid4()),
        "provider": "anthropic",
        "model": model,
        "kind": "llm_call",
        "source": "python-sdk",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "latency_ms": latency_ms,
        "request": _build_full_request(request_kwargs),
    }

    # Merge application context
    span.update(get_context())

    if ttft_ms is not None:
        span["ttft_ms"] = ttft_ms

    if error is not None:
        span["status"] = "error"
        span["error_type"] = type(error).__name__
        span["error_message"] = str(error)[:1000]
        return span

    if response is not None:
        usage = getattr(response, "usage", None)
        if usage:
            span["input_tokens"] = getattr(usage, "input_tokens", None)
            span["output_tokens"] = getattr(usage, "output_tokens", None)
            span["cached_tokens"] = _extract_cache_tokens(usage)

        stop_reason = getattr(response, "stop_reason", None)
        span["status"] = _STATUS_MAP.get(stop_reason, "success")

        # Parse all content blocks (text + tool_use)
        content_list = getattr(response, "content", [])
        parsed = _extract_content_blocks(content_list)

        resp: dict[str, Any] = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", model),
            "stop_reason": stop_reason,
            "content": parsed["content"],
        }
        if parsed["tool_calls"]:
            resp["tool_calls"] = parsed["tool_calls"]
        span["response"] = resp

    return span


def _build_stream_span(
    request_kwargs: dict[str, Any],
    events: list[Any],
    started_at: datetime,
    ended_at: datetime,
    ttft_ms: int | None,
    error: Exception | None = None,
) -> dict[str, Any]:
    """Build a span from accumulated Anthropic SSE events."""
    model = request_kwargs.get("model", "unknown")
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)

    content_parts: list[str] = []
    tool_call_blocks: dict[int, dict[str, Any]] = {}  # block index → tool_call
    current_block_index: int = 0
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int = 0
    response_id: str | None = None

    for event in events:
        event_type = getattr(event, "type", None)

        if event_type == "message_start":
            msg = getattr(event, "message", None)
            if msg:
                response_id = getattr(msg, "id", None)
                usage = getattr(msg, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "input_tokens", None)
                    cached_tokens = _extract_cache_tokens(usage)

        elif event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            idx = getattr(event, "index", current_block_index)
            if block and getattr(block, "type", None) == "tool_use":
                tool_call_blocks[idx] = {
                    "id": getattr(block, "id", None),
                    "name": getattr(block, "name", None),
                    "input": "",
                }
            current_block_index = idx

        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            idx = getattr(event, "index", current_block_index)
            if delta:
                delta_type = getattr(delta, "type", None)
                if delta_type == "text_delta":
                    text = getattr(delta, "text", None)
                    if text:
                        content_parts.append(text)
                elif delta_type == "input_json_delta":
                    # Tool use input arrives as incremental JSON
                    partial = getattr(delta, "partial_json", None)
                    if partial and idx in tool_call_blocks:
                        tool_call_blocks[idx]["input"] += partial

        elif event_type == "message_delta":
            delta = getattr(event, "delta", None)
            if delta:
                sr = getattr(delta, "stop_reason", None)
                if sr:
                    stop_reason = sr
            usage = getattr(event, "usage", None)
            if usage:
                output_tokens = getattr(usage, "output_tokens", None)

    span: dict[str, Any] = {
        "span_id": str(uuid.uuid4()),
        "provider": "anthropic",
        "model": model,
        "kind": "llm_call",
        "source": "python-sdk",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "latency_ms": latency_ms,
        "request": _build_full_request(request_kwargs),
    }

    # Merge application context
    span.update(get_context())

    if ttft_ms is not None:
        span["ttft_ms"] = ttft_ms

    if error is not None:
        span["status"] = "error"
        span["error_type"] = type(error).__name__
        span["error_message"] = str(error)[:1000]
        return span

    span["status"] = _STATUS_MAP.get(stop_reason, "success")
    span["input_tokens"] = input_tokens
    span["output_tokens"] = output_tokens
    span["cached_tokens"] = cached_tokens

    resp: dict[str, Any] = {
        "id": response_id,
        "stop_reason": stop_reason,
        "content": "".join(content_parts),
    }
    if tool_call_blocks:
        # Parse accumulated JSON strings for tool inputs
        tool_calls = []
        for idx in sorted(tool_call_blocks):
            tc = tool_call_blocks[idx]
            input_val = tc["input"]
            # Try to parse the accumulated JSON
            import json
            try:
                input_val = json.loads(input_val) if input_val else {}
            except (json.JSONDecodeError, TypeError):
                pass  # keep as string
            tool_calls.append({
                "id": tc["id"],
                "name": tc["name"],
                "input": input_val,
            })
        resp["tool_calls"] = tool_calls

    span["response"] = resp
    return span


# ── Patcher ──────────────────────────────────────────────────────────────────

def wrap_anthropic(client: Any, sender: "SpanSender") -> Any:
    """Monkey-patch client.messages.create in-place. Returns client."""
    orig_create = client.messages.create

    @functools.wraps(orig_create)
    def patched_create(*args: Any, **kwargs: Any) -> Any:
        started_at = datetime.now(tz=timezone.utc)
        t0 = time.perf_counter()
        stream = kwargs.get("stream", False)

        try:
            if stream:
                return _wrap_stream(
                    orig_create(*args, **kwargs),
                    kwargs,
                    started_at,
                    t0,
                    sender,
                )
            response = orig_create(*args, **kwargs)
            ended_at = datetime.now(tz=timezone.utc)
            try:
                span = _build_span(kwargs, response, started_at, ended_at)
                sender.enqueue(span)
            except Exception as exc:
                log.debug("Anthropic span build failed: %s", exc)
            return response
        except Exception as exc:
            ended_at = datetime.now(tz=timezone.utc)
            try:
                span = _build_span(kwargs, None, started_at, ended_at, error=exc)
                sender.enqueue(span)
            except Exception:
                pass
            raise  # always re-raise

    client.messages.create = patched_create
    return client


# ── Stream wrapper ───────────────────────────────────────────────────────────

class _TrackedStream:
    """Wraps an Anthropic Stream, records ttft + accumulates events for tracing."""

    def __init__(
        self,
        stream: Any,
        request_kwargs: dict[str, Any],
        started_at: datetime,
        t0: float,
        sender: "SpanSender",
    ) -> None:
        self._stream = stream
        self._kwargs = request_kwargs
        self._started_at = started_at
        self._t0 = t0
        self._sender = sender
        self._events: list[Any] = []
        self._ttft_ms: int | None = None
        self._error: Exception | None = None
        self._finished = False

    def __iter__(self) -> "_TrackedStream":
        return self

    def __next__(self) -> Any:
        try:
            event = next(
                self._stream.__iter__()
                if not hasattr(self._stream, "__next__")
                else self._stream
            )
            if self._ttft_ms is None:
                self._ttft_ms = int((time.perf_counter() - self._t0) * 1000)
            self._events.append(event)
            return event
        except StopIteration:
            self._finish()
            raise
        except Exception as exc:
            self._error = exc
            self._finish()
            raise

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            ended_at = datetime.now(tz=timezone.utc)
            span = _build_stream_span(
                self._kwargs,
                self._events,
                self._started_at,
                ended_at,
                self._ttft_ms,
                self._error,
            )
            self._sender.enqueue(span)
        except Exception as exc:
            log.debug("Anthropic stream span build failed: %s", exc)

    def __enter__(self) -> "_TrackedStream":
        return self

    def __exit__(self, *args: Any) -> None:
        self._finish()
        if hasattr(self._stream, "__exit__"):
            self._stream.__exit__(*args)


def _wrap_stream(
    stream: Any,
    request_kwargs: dict[str, Any],
    started_at: datetime,
    t0: float,
    sender: "SpanSender",
) -> "_TrackedStream":
    return _TrackedStream(stream, request_kwargs, started_at, t0, sender)
