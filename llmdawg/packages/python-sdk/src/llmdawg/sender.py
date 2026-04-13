"""SpanSender — thread-safe background span queue.

Design goals:
- Never raises in caller code
- Non-blocking enqueue (drops if full)
- Flushes on clean shutdown via atexit
- Batches up to 50 spans per HTTP request
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llmdawg.client import LLMDawgClient

log = logging.getLogger(__name__)

_BATCH_SIZE = 50
_FLUSH_INTERVAL = 1.0  # seconds between drain cycles


class SpanSender:
    """Thread-safe non-blocking span queue with background flush loop."""

    def __init__(
        self,
        client: "LLMDawgClient",
        max_queue: int = 1_000,
        flush_interval: float = _FLUSH_INTERVAL,
    ) -> None:
        self._client = client
        self._flush_interval = flush_interval
        self._queue: deque[dict[str, Any]] = deque(maxlen=max_queue)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._flushed = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="llmdawg-sender")
        self._thread.start()
        atexit.register(self.flush)

    # ── Public API ────────────────────────────────────────────────────────────

    def enqueue(self, span: dict[str, Any]) -> bool:
        """Add span to queue. Returns False if dropped (queue full)."""
        try:
            prev_len = len(self._queue)
            self._queue.append(span)
            # deque with maxlen silently drops from the LEFT when full
            return len(self._queue) > prev_len or prev_len == 0
        except Exception:
            return False

    def flush(self, timeout: float = 5.0) -> None:
        """Block until the queue is drained or timeout expires."""
        try:
            deadline = time.monotonic() + timeout
            while self._queue and time.monotonic() < deadline:
                self._drain_once()
                time.sleep(0.05)
        except Exception:
            pass

    def stop(self) -> None:
        """Signal the background thread to stop after draining."""
        self._stop_event.set()
        self._thread.join(timeout=6.0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._drain_once()
            except Exception as exc:
                log.debug("SpanSender drain error: %s", exc)
            self._stop_event.wait(timeout=self._flush_interval)
        # Final drain on shutdown
        try:
            self._drain_once()
        except Exception:
            pass

    def _drain_once(self) -> None:
        """Send up to _BATCH_SIZE spans in one POST /v1/ingest/batch call."""
        if not self._queue:
            return

        batch: list[dict[str, Any]] = []
        with self._lock:
            while self._queue and len(batch) < _BATCH_SIZE:
                batch.append(self._queue.popleft())

        if not batch:
            return

        try:
            self._client.ingest_batch(batch)
        except Exception as exc:
            log.debug("SpanSender batch send failed (retry once): %s", exc)
            # Retry once
            try:
                self._client.ingest_batch(batch)
            except Exception as exc2:
                log.debug("SpanSender batch retry failed, dropping %d spans: %s", len(batch), exc2)
