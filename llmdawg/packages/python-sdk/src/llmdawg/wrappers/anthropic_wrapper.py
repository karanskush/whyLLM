"""Anthropic client patcher — monkey-patches messages.create in-place."""

from __future__ import annotations

import functools
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

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
        "source": "python-sdk",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "latency_ms": latency_ms,
        "request": {
            "model": model,
            "messages": request_kwargs.get("messages", []),
            "max_tokens": request_kwargs.get("max_tokens"),
            "system": request_kwargs.get("system"),
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
            span["input_tokens"] = getattr(usage, "input_tokens", None)
            span["output_tokens"] = getattr(usage, "output_tokens", None)

        stop_reason = getattr(response, "stop_reason", None)
        span["status"] = _STATUS_MAP.get(stop_reason, "success")

        # Extract text content from the content list
        content_text: str | None = None
        content_list = getattr(response, "content", [])
        if content_list:
            texts = [
                getattr(block, "text", None)
                for block in content_list
                if getattr(block, "type", None) == "text"
            ]
            content_text = "".join(t for t in texts if t)

        span["response"] = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", model),
            "stop_reason": stop_reason,
            "content": content_text,
        }

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
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
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

        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta and getattr(delta, "type", None) == "text_delta":
                text = getattr(delta, "text", None)
                if text:
                    content_parts.append(text)

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

    span["status"] = _STATUS_MAP.get(stop_reason, "success")
    span["input_tokens"] = input_tokens
    span["output_tokens"] = output_tokens
    span["response"] = {
        "id": response_id,
        "stop_reason": stop_reason,
        "content": "".join(content_parts),
    }
    return span


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
