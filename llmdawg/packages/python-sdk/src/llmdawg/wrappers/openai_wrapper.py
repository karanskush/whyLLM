"""OpenAI client patcher — monkey-patches chat.completions.create and
embeddings.create in-place.

Captures:
  - Full request kwargs (tools, response_format, seed, top_p, etc.)
  - Full response (tool_calls, content, function results)
  - Cached tokens (prompt_tokens_details.cached_tokens)
  - Streaming token counts (injects stream_options.include_usage)
  - TTFT for streaming calls
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

# OpenAI finish_reason → LLMDawg status
_STATUS_MAP = {
    "stop": "success",
    "length": "success",
    "tool_calls": "success",
    "content_filter": "error",
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
    # Pydantic model or dataclass-like object
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


def _extract_cached_tokens(usage: Any) -> int:
    """Extract cached prompt tokens from OpenAI's usage object."""
    if usage is None:
        return 0
    # OpenAI returns usage.prompt_tokens_details.cached_tokens
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
        if cached is not None:
            return int(cached)
    return 0


def _extract_tool_calls(choices: list[Any]) -> list[dict[str, Any]] | None:
    """Extract tool_calls from the first choice's message."""
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    if message is None:
        return None
    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return None
    return [_safe_serialize(tc) for tc in tool_calls]


def _build_full_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Capture the full request kwargs, not just model/messages."""
    req: dict[str, Any] = {}
    for key, val in kwargs.items():
        if key == "stream":
            continue  # tracked separately
        req[key] = _safe_serialize(val)
    return req


# ── Chat completions span builders ──────────────────────────────────────────

def _build_span(
    request_kwargs: dict[str, Any],
    response: Any,
    started_at: datetime,
    ended_at: datetime,
    ttft_ms: int | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    """Build a span dict from OpenAI request/response objects."""
    model = request_kwargs.get("model", "unknown")
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)

    span: dict[str, Any] = {
        "span_id": str(uuid.uuid4()),
        "provider": "openai",
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
            span["input_tokens"] = getattr(usage, "prompt_tokens", None)
            span["output_tokens"] = getattr(usage, "completion_tokens", None)
            span["cached_tokens"] = _extract_cached_tokens(usage)

        choices = getattr(response, "choices", [])
        finish_reason = choices[0].finish_reason if choices else None
        span["status"] = _STATUS_MAP.get(finish_reason, "success")

        # Build rich response payload
        resp: dict[str, Any] = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", model),
            "finish_reason": finish_reason,
        }

        if choices:
            message = getattr(choices[0], "message", None)
            if message:
                resp["content"] = getattr(message, "content", None)
                # Capture tool calls
                tool_calls = _extract_tool_calls(choices)
                if tool_calls:
                    resp["tool_calls"] = tool_calls
                # Capture refusal (safety)
                refusal = getattr(message, "refusal", None)
                if refusal:
                    resp["refusal"] = refusal

        span["response"] = resp

    return span


def _build_stream_span(
    request_kwargs: dict[str, Any],
    chunks: list[Any],
    started_at: datetime,
    ended_at: datetime,
    ttft_ms: int | None,
    error: Exception | None = None,
) -> dict[str, Any]:
    """Build a span from accumulated SSE chunks."""
    model = request_kwargs.get("model", "unknown")
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)

    # Accumulate content and tool calls from delta chunks
    content_parts: list[str] = []
    tool_call_parts: dict[int, dict[str, Any]] = {}  # index → {id, type, name, arguments}
    finish_reason = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int = 0

    for chunk in chunks:
        choices = getattr(chunk, "choices", [])
        if choices:
            delta = getattr(choices[0], "delta", None)
            if delta:
                # Text content
                if getattr(delta, "content", None):
                    content_parts.append(delta.content)
                # Tool call deltas
                tc_list = getattr(delta, "tool_calls", None)
                if tc_list:
                    for tc in tc_list:
                        idx = getattr(tc, "index", 0)
                        if idx not in tool_call_parts:
                            tool_call_parts[idx] = {
                                "id": getattr(tc, "id", None),
                                "type": getattr(tc, "type", "function"),
                                "function": {"name": "", "arguments": ""},
                            }
                        fn = getattr(tc, "function", None)
                        if fn:
                            name = getattr(fn, "name", None)
                            if name:
                                tool_call_parts[idx]["function"]["name"] = name
                            args = getattr(fn, "arguments", None)
                            if args:
                                tool_call_parts[idx]["function"]["arguments"] += args
                        # Backfill id if it arrives later
                        tc_id = getattr(tc, "id", None)
                        if tc_id and not tool_call_parts[idx]["id"]:
                            tool_call_parts[idx]["id"] = tc_id

            fr = getattr(choices[0], "finish_reason", None)
            if fr:
                finish_reason = fr

        # Usage may appear in the final chunk (stream_options.include_usage)
        usage = getattr(chunk, "usage", None)
        if usage:
            input_tokens = getattr(usage, "prompt_tokens", None)
            output_tokens = getattr(usage, "completion_tokens", None)
            cached_tokens = _extract_cached_tokens(usage)

    span: dict[str, Any] = {
        "span_id": str(uuid.uuid4()),
        "provider": "openai",
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

    span["status"] = _STATUS_MAP.get(finish_reason, "success")
    span["input_tokens"] = input_tokens
    span["output_tokens"] = output_tokens
    span["cached_tokens"] = cached_tokens

    resp: dict[str, Any] = {
        "finish_reason": finish_reason,
        "content": "".join(content_parts),
    }
    if tool_call_parts:
        resp["tool_calls"] = [tool_call_parts[i] for i in sorted(tool_call_parts)]
    span["response"] = resp

    return span


# ── Embeddings span builder ─────────────────────────────────────────────────

def _build_embedding_span(
    request_kwargs: dict[str, Any],
    response: Any,
    started_at: datetime,
    ended_at: datetime,
    error: Exception | None = None,
) -> dict[str, Any]:
    """Build a span from an embeddings API call."""
    model = request_kwargs.get("model", "unknown")
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)

    span: dict[str, Any] = {
        "span_id": str(uuid.uuid4()),
        "provider": "openai",
        "model": model,
        "kind": "retrieval",
        "source": "python-sdk",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "latency_ms": latency_ms,
        "request": _build_full_request(request_kwargs),
    }

    # Merge application context
    span.update(get_context())

    if error is not None:
        span["status"] = "error"
        span["error_type"] = type(error).__name__
        span["error_message"] = str(error)[:1000]
        return span

    span["status"] = "success"

    if response is not None:
        usage = getattr(response, "usage", None)
        if usage:
            span["input_tokens"] = getattr(usage, "prompt_tokens", None) or getattr(usage, "total_tokens", None)
            span["output_tokens"] = 0  # embeddings don't produce output tokens

        data = getattr(response, "data", [])
        span["response"] = {
            "model": getattr(response, "model", model),
            "embedding_count": len(data),
            "dimensions": len(data[0].embedding) if data and hasattr(data[0], "embedding") else None,
        }

    return span


# ── Patchers ─────────────────────────────────────────────────────────────────

def wrap_openai(client: Any, sender: "SpanSender") -> Any:
    """Monkey-patch chat.completions.create and embeddings.create. Returns client."""

    # ── Patch chat.completions.create ────────────────────────────────────────
    orig_chat_create = client.chat.completions.create

    @functools.wraps(orig_chat_create)
    def patched_chat_create(*args: Any, **kwargs: Any) -> Any:
        started_at = datetime.now(tz=timezone.utc)
        t0 = time.perf_counter()
        stream = kwargs.get("stream", False)

        # Inject stream_options to get token counts in streaming responses
        if stream:
            so = kwargs.get("stream_options") or {}
            if not so.get("include_usage"):
                kwargs["stream_options"] = {**so, "include_usage": True}

        try:
            if stream:
                return _wrap_stream(
                    orig_chat_create(*args, **kwargs),
                    kwargs,
                    started_at,
                    t0,
                    sender,
                )
            response = orig_chat_create(*args, **kwargs)
            ended_at = datetime.now(tz=timezone.utc)
            try:
                span = _build_span(kwargs, response, started_at, ended_at)
                sender.enqueue(span)
            except Exception as exc:
                log.debug("OpenAI span build failed: %s", exc)
            return response
        except Exception as exc:
            ended_at = datetime.now(tz=timezone.utc)
            try:
                span = _build_span(kwargs, None, started_at, ended_at, error=exc)
                sender.enqueue(span)
            except Exception:
                pass
            raise  # always re-raise

    client.chat.completions.create = patched_chat_create

    # ── Patch embeddings.create ──────────────────────────────────────────────
    if hasattr(client, "embeddings") and hasattr(client.embeddings, "create"):
        orig_embed_create = client.embeddings.create

        @functools.wraps(orig_embed_create)
        def patched_embed_create(*args: Any, **kwargs: Any) -> Any:
            started_at = datetime.now(tz=timezone.utc)
            try:
                response = orig_embed_create(*args, **kwargs)
                ended_at = datetime.now(tz=timezone.utc)
                try:
                    span = _build_embedding_span(kwargs, response, started_at, ended_at)
                    sender.enqueue(span)
                except Exception as exc:
                    log.debug("OpenAI embedding span build failed: %s", exc)
                return response
            except Exception as exc:
                ended_at = datetime.now(tz=timezone.utc)
                try:
                    span = _build_embedding_span(kwargs, None, started_at, ended_at, error=exc)
                    sender.enqueue(span)
                except Exception:
                    pass
                raise

        client.embeddings.create = patched_embed_create

    return client


# ── Stream wrapper ───────────────────────────────────────────────────────────

class _TrackedStream:
    """Wraps an OpenAI Stream, records ttft + accumulates chunks for tracing."""

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
        self._chunks: list[Any] = []
        self._ttft_ms: int | None = None
        self._error: Exception | None = None
        self._finished = False

    def __iter__(self) -> "_TrackedStream":
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._stream.__iter__() if not hasattr(self._stream, "__next__") else self._stream)
            if self._ttft_ms is None:
                self._ttft_ms = int((time.perf_counter() - self._t0) * 1000)
            self._chunks.append(chunk)
            return chunk
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
                self._kwargs, self._chunks, self._started_at,
                ended_at, self._ttft_ms, self._error,
            )
            self._sender.enqueue(span)
        except Exception as exc:
            log.debug("OpenAI stream span build failed: %s", exc)

    # Forward context manager protocol
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
