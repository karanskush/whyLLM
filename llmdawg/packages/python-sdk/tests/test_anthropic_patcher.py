"""Tests for the Anthropic monkey-patch wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from whyllm.wrappers.anthropic_wrapper import (
    _build_span,
    _build_stream_span,
    wrap_anthropic,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_sender() -> MagicMock:
    sender = MagicMock()
    sender.enqueue = MagicMock(return_value=True)
    return sender


def _make_response(
    content: str = "Hello from Claude!",
    stop_reason: str = "end_turn",
    model: str = "claude-3-5-sonnet-20241022",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Any:
    return SimpleNamespace(
        id="msg-abc123",
        model=model,
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="text", text=content)
        ],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def _make_message_start_event(input_tokens: int = 10) -> Any:
    return SimpleNamespace(
        type="message_start",
        message=SimpleNamespace(
            id="msg-123",
            usage=SimpleNamespace(input_tokens=input_tokens),
        ),
    )


def _make_content_delta_event(text: str) -> Any:
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _make_message_delta_event(
    stop_reason: str = "end_turn", output_tokens: int = 5
) -> Any:
    return SimpleNamespace(
        type="message_delta",
        delta=SimpleNamespace(stop_reason=stop_reason),
        usage=SimpleNamespace(output_tokens=output_tokens),
    )


# ── _build_span ────────────────────────────────────────────────────────────────

class TestBuildSpan:
    def test_basic_fields(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span({"model": "claude-3-5-sonnet-20241022", "messages": []}, resp, now, now)
        assert span["provider"] == "anthropic"
        assert span["model"] == "claude-3-5-sonnet-20241022"
        assert span["source"] == "python-sdk"
        assert span["status"] == "success"
        assert "span_id" in span

    def test_token_counts_use_anthropic_field_names(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(input_tokens=25, output_tokens=12)
        span = _build_span({"model": "claude-3-5-sonnet-20241022", "messages": []}, resp, now, now)
        assert span["input_tokens"] == 25
        assert span["output_tokens"] == 12

    def test_text_content_extracted(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(content="Hello, world!")
        span = _build_span({"model": "claude-3-5-sonnet-20241022", "messages": []}, resp, now, now)
        assert span["response"]["content"] == "Hello, world!"

    def test_stop_reason_in_response(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(stop_reason="max_tokens")
        span = _build_span({"model": "claude-3-5-sonnet-20241022", "messages": []}, resp, now, now)
        assert span["response"]["stop_reason"] == "max_tokens"
        assert span["status"] == "success"  # max_tokens still maps to success

    def test_error_span(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_span(
            {"model": "claude-3-5-sonnet-20241022", "messages": []},
            None, now, now,
            error=ConnectionError("refused"),
        )
        assert span["status"] == "error"
        assert span["error_type"] == "ConnectionError"
        assert "refused" in span["error_message"]

    def test_ttft_included(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span(
            {"model": "claude-3-5-sonnet-20241022", "messages": []},
            resp, now, now, ttft_ms=80,
        )
        assert span["ttft_ms"] == 80


# ── _build_stream_span ─────────────────────────────────────────────────────────

class TestBuildStreamSpan:
    def test_content_accumulated_from_deltas(self):
        now = datetime.now(tz=timezone.utc)
        events = [
            _make_message_start_event(input_tokens=10),
            _make_content_delta_event("Hello"),
            _make_content_delta_event(", Claude!"),
            _make_message_delta_event(stop_reason="end_turn", output_tokens=6),
        ]
        span = _build_stream_span(
            {"model": "claude-3-5-sonnet-20241022", "messages": []},
            events, now, now, ttft_ms=60,
        )
        assert span["response"]["content"] == "Hello, Claude!"
        assert span["response"]["stop_reason"] == "end_turn"
        assert span["input_tokens"] == 10
        assert span["output_tokens"] == 6

    def test_error_stream_span(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_stream_span(
            {"model": "claude-3-5-sonnet-20241022", "messages": []},
            [], now, now, ttft_ms=None,
            error=RuntimeError("stream broke"),
        )
        assert span["status"] == "error"
        assert span["error_type"] == "RuntimeError"

    def test_empty_events_returns_valid_span(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_stream_span(
            {"model": "claude-3-5-sonnet-20241022", "messages": []},
            [], now, now, ttft_ms=None,
        )
        assert span["response"]["content"] == ""
        assert span["status"] == "success"  # None stop_reason → success


# ── wrap_anthropic integration ─────────────────────────────────────────────────

class TestWrapAnthropic:
    def _make_client(self, response: Any) -> Any:
        mock_create = MagicMock(return_value=response)
        return SimpleNamespace(messages=SimpleNamespace(create=mock_create))

    def test_patched_create_returns_response(self):
        sender = _mock_sender()
        resp = _make_response()
        client = self._make_client(resp)
        wrap_anthropic(client, sender)
        result = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100,
        )
        assert result is resp

    def test_span_enqueued_on_success(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        wrap_anthropic(client, sender)
        client.messages.create(
            model="claude-3-5-sonnet-20241022", messages=[], max_tokens=100
        )
        sender.enqueue.assert_called_once()
        span = sender.enqueue.call_args[0][0]
        assert span["status"] == "success"
        assert span["provider"] == "anthropic"

    def test_span_enqueued_on_exception(self):
        sender = _mock_sender()
        mock_create = MagicMock(side_effect=TimeoutError("upstream timeout"))
        client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
        wrap_anthropic(client, sender)
        with pytest.raises(TimeoutError):
            client.messages.create(
                model="claude-3-5-sonnet-20241022", messages=[], max_tokens=100
            )
        span = sender.enqueue.call_args[0][0]
        assert span["status"] == "error"
        assert span["error_type"] == "TimeoutError"

    def test_original_exception_reraises(self):
        sender = _mock_sender()
        mock_create = MagicMock(side_effect=PermissionError("no auth"))
        client = SimpleNamespace(messages=SimpleNamespace(create=mock_create))
        wrap_anthropic(client, sender)
        with pytest.raises(PermissionError, match="no auth"):
            client.messages.create(
                model="claude-3-5-sonnet-20241022", messages=[], max_tokens=10
            )

    def test_wrap_returns_same_client(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        returned = wrap_anthropic(client, sender)
        assert returned is client

    def test_unique_span_ids(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        wrap_anthropic(client, sender)
        client.messages.create(model="claude-3-5-sonnet-20241022", messages=[], max_tokens=10)
        client.messages.create(model="claude-3-5-sonnet-20241022", messages=[], max_tokens=10)
        ids = [call[0][0]["span_id"] for call in sender.enqueue.call_args_list]
        assert ids[0] != ids[1]


# ── streaming integration ──────────────────────────────────────────────────────

class TestAnthropicStreamWrapping:
    def _make_stream_client(self, events: list[Any]) -> Any:
        class FakeStream:
            def __init__(self, items):
                self._iter = iter(items)

            def __iter__(self):
                return self

            def __next__(self):
                return next(self._iter)

        mock_create = MagicMock(return_value=FakeStream(events))
        return SimpleNamespace(messages=SimpleNamespace(create=mock_create))

    def test_stream_span_enqueued_after_iteration(self):
        sender = _mock_sender()
        events = [
            _make_message_start_event(10),
            _make_content_delta_event("Hi"),
            _make_message_delta_event("end_turn", 3),
        ]
        client = self._make_stream_client(events)
        wrap_anthropic(client, sender)
        stream = client.messages.create(
            model="claude-3-5-sonnet-20241022", messages=[], max_tokens=50, stream=True
        )
        assert not sender.enqueue.called
        list(stream)
        sender.enqueue.assert_called_once()
        span = sender.enqueue.call_args[0][0]
        assert span["response"]["content"] == "Hi"

    def test_stream_span_finish_not_called_twice(self):
        """_finish() should be idempotent — only enqueue once."""
        sender = _mock_sender()
        events = [_make_content_delta_event("x")]
        client = self._make_stream_client(events)
        wrap_anthropic(client, sender)
        stream = client.messages.create(
            model="claude-3-5-sonnet-20241022", messages=[], max_tokens=10, stream=True
        )
        list(stream)
        # Call context manager __exit__ as well — should not double-enqueue
        stream.__exit__(None, None, None)
        assert sender.enqueue.call_count == 1
