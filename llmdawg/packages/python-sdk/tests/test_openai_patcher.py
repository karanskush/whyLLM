"""Tests for the OpenAI monkey-patch wrapper."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from llmdawg.wrappers.openai_wrapper import (
    _build_span,
    _build_stream_span,
    _build_embedding_span,
    _extract_cached_tokens,
    wrap_openai,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_sender() -> MagicMock:
    sender = MagicMock()
    sender.enqueue = MagicMock(return_value=True)
    return sender


def _make_response(
    content: str = "Hello!",
    finish_reason: str = "stop",
    model: str = "gpt-4o",
    input_tokens: int = 10,
    output_tokens: int = 5,
    cached_tokens: int = 0,
    tool_calls: Any = None,
) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls, refusal=None)
    usage_kwargs: dict[str, Any] = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
    }
    if cached_tokens > 0:
        usage_kwargs["prompt_tokens_details"] = SimpleNamespace(cached_tokens=cached_tokens)
    else:
        usage_kwargs["prompt_tokens_details"] = None
    return SimpleNamespace(
        id="chatcmpl-abc123",
        model=model,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=message,
            )
        ],
        usage=SimpleNamespace(**usage_kwargs),
    )


def _make_tool_call_response() -> Any:
    """Response where the model calls a function."""
    tool_call = SimpleNamespace(
        id="call_abc123",
        type="function",
        function=SimpleNamespace(
            name="get_weather",
            arguments='{"location": "NYC"}',
        ),
    )
    message = SimpleNamespace(content=None, tool_calls=[tool_call], refusal=None)
    return SimpleNamespace(
        id="chatcmpl-tc123",
        model="gpt-4o",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=message,
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=50,
            completion_tokens=20,
            prompt_tokens_details=None,
        ),
    )


def _make_chunk(content: str | None = None, finish_reason: str | None = None) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None)


def _make_tool_call_chunk(
    index: int = 0,
    tc_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
    finish_reason: str | None = None,
) -> Any:
    """Build a streaming chunk with a tool call delta."""
    fn = SimpleNamespace(name=name, arguments=arguments)
    tc = SimpleNamespace(index=index, id=tc_id, type="function" if tc_id else None, function=fn)
    delta = SimpleNamespace(content=None, tool_calls=[tc])
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None)


def _make_usage_chunk(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> Any:
    details = SimpleNamespace(cached_tokens=cached_tokens) if cached_tokens else None
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            prompt_tokens_details=details,
        ),
    )


def _make_embedding_response(
    model: str = "text-embedding-3-small",
    input_tokens: int = 8,
    dimensions: int = 1536,
    count: int = 1,
) -> Any:
    data = [SimpleNamespace(embedding=[0.1] * dimensions) for _ in range(count)]
    return SimpleNamespace(
        model=model,
        data=data,
        usage=SimpleNamespace(prompt_tokens=input_tokens, total_tokens=input_tokens),
    )


# ── _extract_cached_tokens ───────────────────────────────────────────────────

class TestExtractCachedTokens:
    def test_returns_zero_when_no_details(self):
        usage = SimpleNamespace(prompt_tokens_details=None)
        assert _extract_cached_tokens(usage) == 0

    def test_returns_cached_count(self):
        usage = SimpleNamespace(
            prompt_tokens_details=SimpleNamespace(cached_tokens=42)
        )
        assert _extract_cached_tokens(usage) == 42

    def test_returns_zero_when_none_usage(self):
        assert _extract_cached_tokens(None) == 0


# ── _build_span ────────────────────────────────────────────────────────────────

class TestBuildSpan:
    def test_basic_fields(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert span["provider"] == "openai"
        assert span["model"] == "gpt-4o"
        assert span["source"] == "python-sdk"
        assert span["kind"] == "llm_call"
        assert span["status"] == "success"
        assert "span_id" in span

    def test_token_counts(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(input_tokens=20, output_tokens=8)
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert span["input_tokens"] == 20
        assert span["output_tokens"] == 8

    def test_cached_tokens_extracted(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(cached_tokens=100)
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert span["cached_tokens"] == 100

    def test_content_filter_maps_to_error(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(finish_reason="content_filter")
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert span["status"] == "error"

    def test_error_span_no_response(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_span(
            {"model": "gpt-4o", "messages": []},
            None, now, now,
            error=ValueError("boom"),
        )
        assert span["status"] == "error"
        assert span["error_type"] == "ValueError"
        assert "boom" in span["error_message"]
        assert "response" not in span

    def test_latency_ms_computed(self):
        from datetime import timedelta
        started = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ended = started + timedelta(milliseconds=250)
        resp = _make_response()
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, started, ended)
        assert span["latency_ms"] == 250

    def test_ttft_ms_included_when_provided(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span(
            {"model": "gpt-4o", "messages": []}, resp, now, now, ttft_ms=120
        )
        assert span["ttft_ms"] == 120

    def test_ttft_ms_absent_when_not_provided(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert "ttft_ms" not in span

    def test_tool_calls_captured(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_tool_call_response()
        span = _build_span(
            {"model": "gpt-4o", "messages": [], "tools": [{"type": "function"}]},
            resp, now, now,
        )
        assert span["status"] == "success"
        assert span["response"]["content"] is None
        assert span["response"]["tool_calls"] is not None
        assert len(span["response"]["tool_calls"]) == 1

    def test_full_request_kwargs_captured(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        kwargs = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.7,
            "top_p": 0.9,
            "seed": 42,
            "tools": [{"type": "function", "function": {"name": "test"}}],
            "response_format": {"type": "json_object"},
        }
        span = _build_span(kwargs, resp, now, now)
        assert span["request"]["temperature"] == 0.7
        assert span["request"]["top_p"] == 0.9
        assert span["request"]["seed"] == 42
        assert span["request"]["tools"] is not None
        assert span["request"]["response_format"] == {"type": "json_object"}


# ── _build_stream_span ─────────────────────────────────────────────────────────

class TestBuildStreamSpan:
    def test_accumulates_content(self):
        now = datetime.now(tz=timezone.utc)
        chunks = [
            _make_chunk("Hello"),
            _make_chunk(", "),
            _make_chunk("world!"),
            _make_chunk(finish_reason="stop"),
        ]
        span = _build_stream_span(
            {"model": "gpt-4o", "messages": []}, chunks, now, now, ttft_ms=50
        )
        assert span["response"]["content"] == "Hello, world!"
        assert span["response"]["finish_reason"] == "stop"

    def test_usage_from_final_chunk(self):
        now = datetime.now(tz=timezone.utc)
        chunks = [
            _make_chunk("hi"),
            _make_chunk(finish_reason="stop"),
            _make_usage_chunk(15, 7),
        ]
        span = _build_stream_span(
            {"model": "gpt-4o", "messages": []}, chunks, now, now, ttft_ms=30
        )
        assert span["input_tokens"] == 15
        assert span["output_tokens"] == 7

    def test_cached_tokens_from_stream_usage(self):
        now = datetime.now(tz=timezone.utc)
        chunks = [
            _make_chunk("hi"),
            _make_chunk(finish_reason="stop"),
            _make_usage_chunk(15, 7, cached_tokens=10),
        ]
        span = _build_stream_span(
            {"model": "gpt-4o", "messages": []}, chunks, now, now, ttft_ms=30
        )
        assert span["cached_tokens"] == 10

    def test_tool_calls_accumulated_from_deltas(self):
        now = datetime.now(tz=timezone.utc)
        chunks = [
            _make_tool_call_chunk(index=0, tc_id="call_1", name="get_weather", arguments='{"loc'),
            _make_tool_call_chunk(index=0, arguments='ation": "NYC"}'),
            _make_chunk(finish_reason="tool_calls"),
            _make_usage_chunk(20, 10),
        ]
        span = _build_stream_span(
            {"model": "gpt-4o", "messages": []}, chunks, now, now, ttft_ms=50
        )
        assert span["status"] == "success"
        assert len(span["response"]["tool_calls"]) == 1
        tc = span["response"]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["function"]["name"] == "get_weather"
        assert tc["function"]["arguments"] == '{"location": "NYC"}'


# ── _build_embedding_span ──────────────────────────────────────────────────────

class TestBuildEmbeddingSpan:
    def test_basic_fields(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_embedding_response()
        span = _build_embedding_span(
            {"model": "text-embedding-3-small", "input": "hello"},
            resp, now, now,
        )
        assert span["provider"] == "openai"
        assert span["kind"] == "retrieval"
        assert span["status"] == "success"
        assert span["input_tokens"] == 8
        assert span["output_tokens"] == 0
        assert span["response"]["embedding_count"] == 1
        assert span["response"]["dimensions"] == 1536

    def test_error_span(self):
        now = datetime.now(tz=timezone.utc)
        span = _build_embedding_span(
            {"model": "text-embedding-3-small", "input": "hello"},
            None, now, now, error=RuntimeError("quota exceeded"),
        )
        assert span["status"] == "error"
        assert span["error_type"] == "RuntimeError"


# ── wrap_openai integration ────────────────────────────────────────────────────

class TestWrapOpenAI:
    def _make_client(self, response: Any) -> Any:
        mock_create = MagicMock(return_value=response)
        mock_embed_create = MagicMock(return_value=_make_embedding_response())
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=mock_create)
            ),
            embeddings=SimpleNamespace(create=mock_embed_create),
        )
        return client

    def test_patched_create_returns_response(self):
        sender = _mock_sender()
        resp = _make_response()
        client = self._make_client(resp)
        wrap_openai(client, sender)
        result = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
        )
        assert result is resp

    def test_span_enqueued_on_success(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        wrap_openai(client, sender)
        client.chat.completions.create(model="gpt-4o", messages=[])
        sender.enqueue.assert_called_once()
        span = sender.enqueue.call_args[0][0]
        assert span["status"] == "success"
        assert span["provider"] == "openai"

    def test_span_enqueued_on_exception(self):
        sender = _mock_sender()
        mock_create = MagicMock(side_effect=RuntimeError("API error"))
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create)),
            embeddings=SimpleNamespace(create=MagicMock()),
        )
        wrap_openai(client, sender)
        with pytest.raises(RuntimeError, match="API error"):
            client.chat.completions.create(model="gpt-4o", messages=[])
        sender.enqueue.assert_called_once()
        span = sender.enqueue.call_args[0][0]
        assert span["status"] == "error"
        assert span["error_type"] == "RuntimeError"

    def test_original_exception_reraises(self):
        sender = _mock_sender()
        mock_create = MagicMock(side_effect=ValueError("do not swallow"))
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create)),
            embeddings=SimpleNamespace(create=MagicMock()),
        )
        wrap_openai(client, sender)
        with pytest.raises(ValueError, match="do not swallow"):
            client.chat.completions.create(model="gpt-4o", messages=[])

    def test_wrap_returns_same_client(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        returned = wrap_openai(client, sender)
        assert returned is client

    def test_span_has_unique_span_ids(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        wrap_openai(client, sender)
        client.chat.completions.create(model="gpt-4o", messages=[])
        client.chat.completions.create(model="gpt-4o", messages=[])
        calls = [call[0][0] for call in sender.enqueue.call_args_list]
        ids = [c["span_id"] for c in calls]
        assert ids[0] != ids[1]

    def test_stream_options_injected(self):
        """wrap_openai should inject stream_options.include_usage=True for streaming."""
        sender = _mock_sender()
        chunks = [_make_chunk("hi"), _make_chunk(finish_reason="stop")]

        class FakeStream:
            def __init__(self, items):
                self._iter = iter(items)
            def __iter__(self):
                return self
            def __next__(self):
                return next(self._iter)

        captured_kwargs: dict[str, Any] = {}

        def capturing_create(*args: Any, **kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return FakeStream(chunks)

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=capturing_create)),
            embeddings=SimpleNamespace(create=MagicMock()),
        )
        wrap_openai(client, sender)
        stream = client.chat.completions.create(model="gpt-4o", messages=[], stream=True)
        list(stream)
        assert captured_kwargs.get("stream_options", {}).get("include_usage") is True

    def test_embeddings_patched(self):
        sender = _mock_sender()
        client = self._make_client(_make_response())
        wrap_openai(client, sender)
        client.embeddings.create(model="text-embedding-3-small", input="hello")
        # Should have 1 embedding span enqueued
        assert sender.enqueue.call_count == 1
        span = sender.enqueue.call_args[0][0]
        assert span["kind"] == "retrieval"
        assert span["provider"] == "openai"


# ── streaming integration ──────────────────────────────────────────────────────

class TestStreamWrapping:
    def _make_stream_client(self, chunks: list[Any]) -> Any:
        class FakeStream:
            def __init__(self, items):
                self._iter = iter(items)

            def __iter__(self):
                return self

            def __next__(self):
                return next(self._iter)

        mock_create = MagicMock(return_value=FakeStream(chunks))
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create)),
            embeddings=SimpleNamespace(create=MagicMock()),
        )
        return client

    def test_stream_span_enqueued_after_iteration(self):
        sender = _mock_sender()
        chunks = [_make_chunk("Hello"), _make_chunk(finish_reason="stop")]
        client = self._make_stream_client(chunks)
        wrap_openai(client, sender)

        stream = client.chat.completions.create(model="gpt-4o", messages=[], stream=True)
        assert not sender.enqueue.called  # not yet — must iterate
        list(stream)
        sender.enqueue.assert_called_once()
        span = sender.enqueue.call_args[0][0]
        assert span["response"]["content"] == "Hello"

    def test_stream_span_records_ttft(self):
        sender = _mock_sender()
        chunks = [_make_chunk("Hi"), _make_chunk(finish_reason="stop")]
        client = self._make_stream_client(chunks)
        wrap_openai(client, sender)
        list(client.chat.completions.create(model="gpt-4o", messages=[], stream=True))
        span = sender.enqueue.call_args[0][0]
        assert span.get("ttft_ms") is not None
        assert span["ttft_ms"] >= 0

    def test_stream_finish_idempotent(self):
        sender = _mock_sender()
        chunks = [_make_chunk("x"), _make_chunk(finish_reason="stop")]
        client = self._make_stream_client(chunks)
        wrap_openai(client, sender)
        stream = client.chat.completions.create(model="gpt-4o", messages=[], stream=True)
        list(stream)
        stream.__exit__(None, None, None)
        assert sender.enqueue.call_count == 1


# ── context integration ──────────────────────────────────────────────────────

class TestContextIntegration:
    def test_user_and_session_attached(self):
        from llmdawg.context import set_user, set_session

        sender = _mock_sender()
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()

        set_user("user-42")
        set_session("sess-abc")
        try:
            span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
            assert span["user_id"] == "user-42"
            assert span["session_id"] == "sess-abc"
        finally:
            set_user(None)
            set_session(None)

    def test_trace_context_attached(self):
        from llmdawg.context import trace

        sender = _mock_sender()
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()

        with trace(name="test-trace", user_id="u-1", tags={"env": "test"}) as tid:
            span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
            assert span["trace_id"] == tid
            assert span["user_id"] == "u-1"
            assert span["name"] == "test-trace"
            assert span["tags"]["env"] == "test"

    def test_context_cleaned_after_trace(self):
        from llmdawg.context import trace, _trace_id

        with trace(name="inner"):
            pass

        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert "trace_id" not in span
        assert "name" not in span
