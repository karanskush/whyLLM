"""Tests for the OpenAI monkey-patch wrapper."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from whyllm.wrappers.openai_wrapper import (
    _build_span,
    _build_stream_span,
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
) -> Any:
    return SimpleNamespace(
        id="chatcmpl-abc123",
        model=model,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        ),
    )


def _make_chunk(content: str | None = None, finish_reason: str | None = None) -> Any:
    delta = SimpleNamespace(content=content)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None)


def _make_usage_chunk(input_tokens: int, output_tokens: int) -> Any:
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        ),
    )


# ── _build_span ────────────────────────────────────────────────────────────────

class TestBuildSpan:
    def test_basic_fields(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response()
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert span["provider"] == "openai"
        assert span["model"] == "gpt-4o"
        assert span["source"] == "python-sdk"
        assert span["status"] == "success"
        assert "span_id" in span

    def test_token_counts(self):
        now = datetime.now(tz=timezone.utc)
        resp = _make_response(input_tokens=20, output_tokens=8)
        span = _build_span({"model": "gpt-4o", "messages": []}, resp, now, now)
        assert span["input_tokens"] == 20
        assert span["output_tokens"] == 8

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


# ── wrap_openai integration ────────────────────────────────────────────────────

class TestWrapOpenAI:
    def _make_client(self, response: Any) -> Any:
        mock_create = MagicMock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=mock_create)
            )
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
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
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
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
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
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
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
