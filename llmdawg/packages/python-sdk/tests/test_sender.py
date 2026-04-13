"""Tests for SpanSender — background flush queue."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from llmdawg.sender import SpanSender


def _make_sender(max_queue: int = 100) -> tuple[SpanSender, MagicMock]:
    """Return a SpanSender wired to a mock LLMDawgClient."""
    mock_client = MagicMock()
    mock_client.ingest_batch = MagicMock(return_value=None)
    sender = SpanSender(mock_client, max_queue=max_queue, flush_interval=60.0)
    return sender, mock_client


def _span(n: int = 0) -> dict[str, Any]:
    return {"span_id": f"test-{n}", "provider": "openai", "model": "gpt-4o"}


class TestEnqueue:
    def test_enqueue_returns_true_on_success(self):
        sender, _ = _make_sender()
        assert sender.enqueue(_span()) is True

    def test_enqueue_adds_to_queue(self):
        sender, _ = _make_sender()
        sender.enqueue(_span(1))
        sender.enqueue(_span(2))
        assert len(sender._queue) == 2

    def test_queue_drops_oldest_when_full(self):
        sender, _ = _make_sender(max_queue=3)
        for i in range(5):
            sender.enqueue(_span(i))
        # deque(maxlen=3) keeps last 3
        assert len(sender._queue) == 3
        ids = [s["span_id"] for s in sender._queue]
        assert "test-2" in ids
        assert "test-3" in ids
        assert "test-4" in ids

    def test_enqueue_never_raises(self):
        sender, _ = _make_sender()
        # Pass a non-serialisable object — should not raise
        sender.enqueue({"data": object()})  # type: ignore[arg-type]


class TestFlush:
    def test_flush_drains_queue(self):
        sender, mock_client = _make_sender()
        for i in range(10):
            sender.enqueue(_span(i))
        sender.flush(timeout=3.0)
        assert len(sender._queue) == 0

    def test_flush_calls_ingest_batch(self):
        sender, mock_client = _make_sender()
        for i in range(5):
            sender.enqueue(_span(i))
        sender.flush(timeout=3.0)
        assert mock_client.ingest_batch.called

    def test_flush_batches_up_to_50(self):
        sender, mock_client = _make_sender(max_queue=200)
        for i in range(60):
            sender.enqueue(_span(i))
        sender.flush(timeout=3.0)
        # Should have been called at least twice (60 spans / 50 per batch)
        assert mock_client.ingest_batch.call_count >= 2
        # First batch ≤ 50 spans
        first_call_args = mock_client.ingest_batch.call_args_list[0]
        assert len(first_call_args[0][0]) <= 50

    def test_flush_on_empty_queue_is_noop(self):
        sender, mock_client = _make_sender()
        sender.flush(timeout=1.0)
        assert not mock_client.ingest_batch.called

    def test_flush_safe_to_call_multiple_times(self):
        sender, mock_client = _make_sender()
        sender.enqueue(_span())
        sender.flush(timeout=2.0)
        sender.flush(timeout=2.0)  # second call on empty queue — no error


class TestRetry:
    def test_retries_once_on_failure(self):
        sender, mock_client = _make_sender()
        mock_client.ingest_batch.side_effect = [Exception("network error"), None]
        sender.enqueue(_span())
        sender.flush(timeout=3.0)
        assert mock_client.ingest_batch.call_count == 2

    def test_drops_after_two_failures(self):
        sender, mock_client = _make_sender()
        mock_client.ingest_batch.side_effect = Exception("always fails")
        sender.enqueue(_span())
        # Should not raise even when both attempts fail
        sender.flush(timeout=3.0)
        assert mock_client.ingest_batch.call_count == 2


class TestBackgroundThread:
    def test_thread_is_daemon(self):
        sender, _ = _make_sender()
        assert sender._thread.daemon is True

    def test_thread_drains_without_manual_flush(self):
        sender, mock_client = _make_sender(max_queue=100)
        sender_with_fast_interval = SpanSender(
            mock_client, max_queue=100, flush_interval=0.1
        )
        sender_with_fast_interval.enqueue(_span())
        time.sleep(0.5)  # let background thread run
        assert mock_client.ingest_batch.called

    def test_stop_drains_remaining_spans(self):
        mock_client = MagicMock()
        mock_client.ingest_batch = MagicMock(return_value=None)
        sender = SpanSender(mock_client, max_queue=100, flush_interval=60.0)
        for i in range(5):
            sender.enqueue(_span(i))
        sender.stop()
        assert mock_client.ingest_batch.called
