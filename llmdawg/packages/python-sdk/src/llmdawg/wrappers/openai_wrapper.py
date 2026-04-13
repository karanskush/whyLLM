"""OpenAI client patcher — monkey-patches chat.completions.create in-place."""

from __future__ import annotations

import functools
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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
        "source": "python-sdk",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "latency_ms": latency_ms,
        "request": {
            "model": model,
            "messages": request_kwargs.get("messages", []),
            "temperature": request_kwargs.get("temperature"),
            "max_tokens": request_kwargs.get("max_tokens"),
        },
    }

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

        choices = getattr(response, "choices", [])
        finish_reason = choices[0].finish_reason if choices else None
        span["status"] = _STATUS_MAP.get(finish_reason, "success")

        span["response"] = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", model),
            "finish_reason": finish_reason,
            "content": choices[0].message.content if choices else None,
        }

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

    # Accumulate content from delta chunks
    content_parts: list[str] = []
    finish_reason = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    for chunk in chunks:
        choices = getattr(chunk, "choices", [])
        if choices:
            delta = getattr(choices[0], "delta", None)
            if delta and getattr(delta, "content", None):
                content_parts.append(delta.content)
            fr = getattr(choices[0], "finish_reason", None)
            if fr:
                finish_reason = fr
        # usage may appear in the final chunk (stream_options={"include_usage": True})
        usage = getattr(chunk, "usage", None)
        if usage:
            input_tokens = getattr(usage, "prompt_tokens", None)
            output_tokens = getattr(usage, "completion_tokens", None)

    span: dict[str, Any] = {
        "span_id": str(uuid.uuid4()),
        "provider": "openai",
        "model": model,
        "source": "python-sdk",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "latency_ms": latency_ms,
        "request": {
            "model": model,
            "messages": request_kwargs.get("messages", []),
            "stream": True,
        },
    }

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
    span["response"] = {
        "finish_reason": finish_reason,
        "content": "".join(content_parts),
    }
    return span


def wrap_openai(client: Any, sender: "SpanSender") -> Any:
    """Monkey-patch client.chat.completions.create in-place. Returns client."""
    orig_create = client.chat.completions.create

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

    client.chat.completions.create = patched_create
    return client


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
