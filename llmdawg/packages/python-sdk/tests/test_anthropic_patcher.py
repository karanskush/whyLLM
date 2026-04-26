"""Tests for the Anthropic monkey-patch wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from llmdawg.wrappers.anthropic_wrapper import (
    _build_span,
    _build_stream_span,
    _extract_cache_tokens,
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
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 10,
    output_tokens: int = 5,
    cache_read: int = 0,
    cache_create: int = 0,
    tool_use_blocks: list[Any] | None = None,
) -> Any:
    content_blocks = [SimpleNamespace(type="text", text=content)]
    if tool_use_blocks:
        content_blocks.extend(tool_use_blocks)

    usage_kwargs: dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if cache_read:
        usage_kwargs["cache_read_input_tokens"] = cache_read
    if cache_create:
        usage_kwargs["cache_creation_input_tokens"] = cache_create

    return SimpleNamespace(
        id="msg-abc123",
        model=model,
        stop_reason=stop_reason,
        content=content_blocks,
        usage=SimpleNamespace(**usage_kwargs),
    )


def _make_tool_use_block(
    tool_id: str = "toolu_123",
    name: str = "get_weather",
    tool_input: dict[str, Any] | None = None,
) -> Any:
    return SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name=name,
        input=tool_input or {"location": "NYC"},
    )


def _make_message_start_event(
    input_tokens: int = 10,
    cache_read: int = 0,
    cache_create: int = 0,
) -> Any:
    usage_kwargs: dict[str, Any] = {"input_tokens": input_tokens}
    if cache_read:
        usage_kwargs["cache_read_input_tokens"] = cache_read
    if cache_create:
        usage_kwargs["cache_creation_input_tokens"] = cache_create
    return SimpleNamespace(
        type="message_start",
        message=SimpleNamespace(
            id="msg-123",
            usage=SimpleNamespace(**usage_kwargs),
        ),
    )


def _make_content_delta_event(text: str) -> Any:
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
        index=0,
    )


def _make_tool_use_start_event(
    index: int = 1,
    tool_id: str = "toolu_abc",
    name: str = "get_weather",
) -> Any:
    return SimpleNamespace(
        type="content_block_start",
        index=index,
        content_block=SimpleNamespace(type="tool_use", id=tool_id, name=name),
    )


def _make_tool_input_delta_event(index: int = 1, partial_json: str = "") -> Any:
    return SimpleNamespace(
        type="content_block_delta",
        index=index,
        delta=SimpleNamespace(type="input_json_delta", partial_json=partial_json),
    )


def _make_message_delta_event(
    stop_reason: str = "end_turn", output_tokens: int = 5
) -> Any:
    return SimpleNamespace(
        type="message_delta",
        delta=SimpleNamespace(stop_reason=stop_reason),
        usage=SimpleNamespace(output_tokens=output_tokens),
    )


# ── _extract_cache_tokens ───────────────────────────────────────────────────

class TestExtractCacheTokens:
    def test_returns_zero_when_no_cache(self):
        usage = SimpleNamespace()
        assert _extract_cache_tokens(usage) == 0

    def test_returns_cache_read(self):
        usage = SimpleNamespace(cache_read_input_tokens=50, cache_creation_input_tokens=0)
        assert _extract_cache_tokens(usage) == 50

    def test_returns_cache_create(self):
        usage = SimpleNamespace(cache_read_input_tokens=0, cache_creation_input_tokens=30)
        assert _extract_cache_tokens(usage) == 30

    def test_returns_sum(self):
        usage = SimpleNamespace(cache_read_input_tokens=50, cache_creation_input_tokens=30)
        assert _extract_cache_tokens(usage) == 80

    def test_returns_zero_when_none(self):
        assert _extract_cache_tokens(None) == 0


# ── _build_span ────────────────────────────────────────────────────────────────

class TestBuildSpan:
    def test_basic_fields(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
        assert span["provider"] == "anthropic"
        assert span["model"] == "claude-sonnet-4-6"
        assert span["source"] == "python-sdk"
        assert span["kind"] == "llm_call"
        assert span["status"] == "success"
        assert "span_id" in span

    def test_token_counts_use_anthropic_field_names(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(input_tokens=25, output_tokens=12)
        span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
        assert span["input_tokens"] == 25
        assert span["output_tokens"] == 12

    def test_cached_tokens_extracted(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(cache_read=100, cache_create=50)
        span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
        assert span["cached_tokens"] == 150

    def test_text_content_extracted(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(content="Hello, world!")
        span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
        assert span["response"]["content"] == "Hello, world!"

    def test_tool_use_blocks_captured(self):
        now = datetime.now(tz=timezone.utc)
        tool_block = _make_tool_use_block()
        resp = _make_response(stop_reason="tool_use", tool_use_blocks=[tool_block])
        span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
        assert span["status"] == "success"
        assert span["response"]["tool_calls"] is not None
        assert len(span["response"]["tool_calls"]) == 1
        tc = span["response"]["tool_calls"][0]
        assert tc["name"] == "get_weather"
        assert tc["input"]["location"] == "NYC"

    def test_stop_reason_in_response(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(stop_reason="max_tokens")
        span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
        assert span["response"]["stop_reason"] == "max_tokens"
        assert span["status"] == "success"

    def test_error_span(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_span(
            {"model": "claude-sonnet-4-6", "messages": []},
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
            {"model": "claude-sonnet-4-6", "messages": []},
            resp, now, now, ttft_ms=80,
        )
        assert span["ttft_ms"] == 80

    def test_full_request_kwargs_captured(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        kwargs = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1024,
            "system": "You are helpful.",
            "tools": [{"name": "test", "description": "a test tool"}],
            "temperature": 0.5,
        }
        span = _build_span(kwargs, resp, now, now)
        assert span["request"]["system"] == "You are helpful."
        assert span["request"]["tools"] is not None
        assert span["request"]["temperature"] == 0.5
        assert span["request"]["max_tokens"] == 1024


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
            {"model": "claude-sonnet-4-6", "messages": []},
            events, now, now, ttft_ms=60,
        )
        assert span["response"]["content"] == "Hello, Claude!"
        assert span["response"]["stop_reason"] == "end_turn"
        assert span["input_tokens"] == 10
        assert span["output_tokens"] == 6

    def test_cached_tokens_from_stream(self):
        now = datetime.now(tz=timezone.utc)
        events = [
            _make_message_start_event(input_tokens=50, cache_read=40),
            _make_content_delta_event("hi"),
            _make_message_delta_event("end_turn", 5),
        ]
        span = _build_stream_span(
            {"model": "claude-sonnet-4-6", "messages": []},
            events, now, now, ttft_ms=30,
        )
        assert span["cached_tokens"] == 40

    def test_tool_use_accumulated_from_stream(self):
        now = datetime.now(tz=timezone.utc)
        events = [
            _make_message_start_event(input_tokens=20),
            _make_tool_use_start_event(index=0, tool_id="toolu_abc", name="get_weather"),
            _make_tool_input_delta_event(index=0, partial_json='{"locat'),
            _make_tool_input_delta_event(index=0, partial_json='ion": "NYC"}'),
            _make_message_delta_event(stop_reason="tool_use", output_tokens=15),
        ]
        span = _build_stream_span(
            {"model": "claude-sonnet-4-6", "messages": []},
            events, now, now, ttft_ms=50,
        )
        assert span["status"] == "success"
        assert "tool_calls" in span["response"]
        assert len(span["response"]["tool_calls"]) == 1
        tc = span["response"]["tool_calls"][0]
        assert tc["name"] == "get_weather"
        assert tc["input"]["location"] == "NYC"

    def test_system_prompt_preserved_in_stream_request(self):
        now = datetime.now(tz=timezone.utc)
        events = [
            _make_message_start_event(10),
            _make_content_delta_event("hi"),
            _make_message_delta_event("end_turn", 3),
        ]
        kwargs = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hello"}],
            "system": "You are a helpful assistant.",
            "max_tokens": 1024,
        }
        span = _build_stream_span(kwargs, events, now, now, ttft_ms=30)
        assert span["request"]["system"] == "You are a helpful assistant."
        assert span["request"]["max_tokens"] == 1024

    def test_error_stream_span(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_stream_span(
            {"model": "claude-sonnet-4-6", "messages": []},
            [], now, now, ttft_ms=None,
            error=RuntimeError("stream broke"),
        )
        assert span["status"] == "error"
        assert span["error_type"] == "RuntimeError"

    def test_empty_events_returns_valid_span(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_stream_span(
            {"model": "claude-sonnet-4-6", "messages": []},
            [], now, now, ttft_ms=None,
        )
        assert span["response"]["content"] == ""
        assert span["status"] == "success"


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
            model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100,
        )
        assert result is resp

    def test_span_enqueued_on_success(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        wrap_anthropic(client, sender)
        client.messages.create(
            model="claude-sonnet-4-6", messages=[], max_tokens=100
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
                model="claude-sonnet-4-6", messages=[], max_tokens=100
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
                model="claude-sonnet-4-6", messages=[], max_tokens=10
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
        client.messages.create(model="claude-sonnet-4-6", messages=[], max_tokens=10)
        client.messages.create(model="claude-sonnet-4-6", messages=[], max_tokens=10)
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
            model="claude-sonnet-4-6", messages=[], max_tokens=50, stream=True
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
            model="claude-sonnet-4-6", messages=[], max_tokens=10, stream=True
        )
        list(stream)
        # Call context manager __exit__ as well — should not double-enqueue
        stream.__exit__(None, None, None)
        assert sender.enqueue.call_count == 1


# ── context integration ──────────────────────────────────────────────────────

class TestAnthropicContextIntegration:
    def test_user_attached(self):
        from llmdawg.context import set_user

        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        set_user("user-99")
        try:
            span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
            assert span["user_id"] == "user-99"
        finally:
            set_user(None)

    def test_trace_context(self):
        from llmdawg.context import trace

        now = datetime.now(tz=timezone.utc)
        resp = _make_response()

        with trace(name="anthropic-trace", tags={"provider": "anthropic"}) as tid:
            span = _build_span({"model": "claude-sonnet-4-6", "messages": []}, resp, now, now)
            assert span["trace_id"] == tid
            assert span["tags"]["provider"] == "anthropic"
