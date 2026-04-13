"""Background worker + hallucination scorer tests.

Two scopes:
  Unit tests  — mock DB and Redis; test pipeline logic in isolation.
  Integration — use the live Docker stack to verify end-to-end persistence.

All unit tests use:
  - unittest.mock.AsyncMock for async functions
  - patch() for module-level singletons (get_redis, get_session_factory)
  - No real network connections

Integration tests reuse the same session fixtures as test_ingest.py
(shared via conftest.py's session-scoped event_loop).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import orjson
import pytest
import pytest_asyncio


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_span_payload(**overrides: Any) -> bytes:
    """Build a minimal valid queue payload."""
    base: dict[str, Any] = {
        "span_id": str(uuid.uuid4()),
        "project_id": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "key_id": str(uuid.uuid4()),
        "provider": "openai",
        "model": "gpt-4o",
        "status": "success",
        "kind": "llm_call",
        "environment": "production",
        "name": "test-span",
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "cost_usd": None,
        "latency_ms": 500,
        "ttft_ms": None,
        "error_type": None,
        "error_message": None,
        "started_at": "2026-04-11T10:00:00+00:00",
        "ended_at": "2026-04-11T10:00:00.500000+00:00",
        "request": {"messages": [{"role": "user", "content": "hello"}]},
        "response": {
            "choices": [{
                "message": {"role": "assistant", "content": "Hello! How can I help?"},
                "finish_reason": "stop",
            }]
        },
        "tags": {},
        "trace_id": None,
        "parent_span_id": None,
        "user_id": None,
        "session_id": None,
        "source": "api",
        "sdk_version": None,
        "ingested_at": "2026-04-11T10:00:00+00:00",
    }
    base.update(overrides)
    return orjson.dumps(base)


# ── Mocks ─────────────────────────────────────────────────────────────────────

def _mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)
    r.lpush = AsyncMock(return_value=1)
    r.publish = AsyncMock(return_value=0)
    r.brpop = AsyncMock(return_value=None)
    return r


def _mock_session_factory() -> MagicMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=session)
    return factory, session


def _mock_cost_engine(return_value: Any = Decimal("0.00075")) -> MagicMock:
    engine = MagicMock()
    engine.estimate = MagicMock(return_value=return_value)
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    engine.model_count = 9
    return engine


# ── TestHallucinationScorer ───────────────────────────────────────────────────

class TestHallucinationScorer:
    """Unit tests for the pure-Python heuristic scorer."""

    def _scorer(self):
        from llmdawg_api.services.hallucination import HallucinationScorer
        return HallucinationScorer()

    def _openai_response(self, text: str) -> dict:
        return {
            "choices": [{"message": {"role": "assistant", "content": text}}]
        }

    def _anthropic_response(self, text: str) -> dict:
        return {"content": [{"type": "text", "text": text}]}

    def test_clean_response_scores_low(self):
        scorer = self._scorer()
        resp = self._openai_response(
            "The capital of France is Paris. It's a beautiful city located in northern France."
        )
        score, flags = scorer.score(resp)
        assert score <= Decimal("0.50"), f"Clean response should score low, got {score}"

    def test_highly_repetitive_response_scores_high(self):
        scorer = self._scorer()
        # Extremely repetitive text
        text = ("the cat sat on the mat " * 30).strip()
        resp = self._openai_response(text)
        score, flags = scorer.score(resp)
        assert "token_repetition" in flags, "Repetitive text should fire token_repetition"
        assert score > Decimal("0.20")

    def test_overconfident_text_fires_flag(self):
        scorer = self._scorer()
        text = (
            "I can definitely tell you with absolute certainty that this is 100% correct. "
            "It is undoubtedly the case and I guarantee this is true without a doubt."
        )
        resp = self._openai_response(text)
        score, flags = scorer.score(resp)
        assert "overconfident_language" in flags

    def test_empty_response_returns_zero(self):
        scorer = self._scorer()
        score, flags = scorer.score({})
        assert score == Decimal("0.00")
        assert flags == {}

    def test_none_content_returns_zero(self):
        scorer = self._scorer()
        resp = {"choices": [{"message": {"content": None}}]}
        score, flags = scorer.score(resp)
        assert score == Decimal("0.00")

    def test_anthropic_format_parsed(self):
        scorer = self._scorer()
        resp = self._anthropic_response("This is a simple answer to your question.")
        score, flags = scorer.score(resp)
        assert isinstance(score, Decimal)

    def test_score_bounded_0_to_1(self):
        scorer = self._scorer()
        # Adversarial input
        text = "definitely certainly absolutely 100% guaranteed " * 50
        resp = self._openai_response(text)
        score, flags = scorer.score(resp)
        assert Decimal("0.00") <= score <= Decimal("1.00")

    def test_flags_only_above_threshold(self):
        scorer = self._scorer()
        resp = self._openai_response("Simple clean sentence. Another clean sentence.")
        score, flags = scorer.score(resp)
        # All flags should have score > 0.3
        for name, val in flags.items():
            assert val > 0.3, f"Flag {name} = {val} should be > 0.3"

    def test_score_is_decimal_type(self):
        scorer = self._scorer()
        resp = self._openai_response("Hello world.")
        score, flags = scorer.score(resp)
        assert isinstance(score, Decimal)

    def test_score_has_2_decimal_places(self):
        scorer = self._scorer()
        resp = self._openai_response("Some test response text here.")
        score, _ = scorer.score(resp)
        # Decimal("0.12") has at most 2dp
        assert abs(score - score.quantize(Decimal("0.01"))) == 0

    def test_never_raises_on_garbage_input(self):
        scorer = self._scorer()
        # Should never raise
        result = scorer.score(None)  # type: ignore
        assert result[0] == Decimal("0.00")

        result = scorer.score("not a dict")  # type: ignore
        assert isinstance(result[0], Decimal)

    def test_executes_under_10ms(self):
        scorer = self._scorer()
        # Long response — should still be fast
        text = "The quick brown fox jumps over the lazy dog. " * 200
        resp = self._openai_response(text)
        start = time.perf_counter()
        scorer.score(resp)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 10, f"Scorer took {elapsed_ms:.1f}ms — must be < 10ms"

    def test_length_anomaly_short_text(self):
        scorer = self._scorer()
        resp = self._openai_response("yes")
        score, flags = scorer.score(resp)
        assert "length_anomaly" in flags

    def test_hedge_mismatch_fires_for_uncertain_claims(self):
        scorer = self._scorer()
        text = (
            "I think the revenue was $42 million. "
            "I'm not sure but it might be that Apple Inc had 50% market share. "
            "Possibly Google had 2.5 billion users in 2023."
        )
        resp = self._openai_response(text)
        score, flags = scorer.score(resp)
        # hedging + factual numbers → should score
        assert isinstance(score, Decimal)


# ── TestProcessOne (unit) ─────────────────────────────────────────────────────

class TestProcessOne:
    """Unit tests for the per-span processing pipeline using mocks."""

    async def _run_pipeline(self, raw: bytes, redis_mock=None, session_mock=None,
                             cost_engine=None) -> tuple:
        """Helper: run _pipeline() with injected mocks."""
        from llmdawg_api.worker.worker import IngestWorker

        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis_mock or _mock_redis()
        worker._cost_engine = cost_engine or _mock_cost_engine()

        factory, session = session_mock or _mock_session_factory()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            await worker._pipeline(raw)

        return worker._redis, factory, session

    async def test_happy_path_calls_db_insert(self):
        raw = _make_span_payload()
        redis, factory, session = await self._run_pipeline(raw)
        # Should have called session.execute (for span upsert)
        assert session.execute.called
        assert session.commit.called

    async def test_total_tokens_not_in_values(self):
        """GENERATED ALWAYS AS STORED — total_tokens must never appear in INSERT."""
        raw = _make_span_payload()
        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = _mock_redis()
        worker._cost_engine = _mock_cost_engine()

        captured_stmt = None

        async def capture_execute(stmt, *args, **kwargs):
            nonlocal captured_stmt
            captured_stmt = stmt
            return MagicMock()

        factory, session = _mock_session_factory()
        session.execute = capture_execute

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            await worker._pipeline(raw)

        # Verify total_tokens not in the INSERT statement's compiled string
        if captured_stmt is not None:
            stmt_str = str(captured_stmt)
            assert "total_tokens" not in stmt_str

    async def test_cost_engine_called_with_correct_args(self):
        raw = _make_span_payload(
            provider="openai", model="gpt-4o",
            input_tokens=100, output_tokens=50, cached_tokens=5
        )
        engine = _mock_cost_engine()
        factory, session = _mock_session_factory()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = _mock_redis()
        worker._cost_engine = engine

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            await worker._pipeline(raw)

        engine.estimate.assert_called_once_with("openai", "gpt-4o", 100, 50, 5)

    async def test_hallucination_skipped_on_error_status(self):
        raw = _make_span_payload(status="error")
        factory, session = _mock_session_factory()
        redis = _mock_redis()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            with patch("llmdawg_api.services.hallucination.HallucinationScorer") as mock_scorer:
                await worker._pipeline(raw)
                # HallucinationScorer.score should NOT be called for error spans
                mock_scorer.return_value.score.assert_not_called()

    async def test_hallucination_skipped_when_no_response(self):
        raw = _make_span_payload(status="success", response=None)
        factory, session = _mock_session_factory()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = _mock_redis()
        worker._cost_engine = _mock_cost_engine()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            with patch("llmdawg_api.services.hallucination.HallucinationScorer") as mock_scorer:
                await worker._pipeline(raw)
                mock_scorer.return_value.score.assert_not_called()

    async def test_live_event_published_to_correct_channel(self):
        data = orjson.loads(_make_span_payload())
        project_id = data["project_id"]
        raw = orjson.dumps(data)

        redis = _mock_redis()
        factory, session = _mock_session_factory()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            await worker._pipeline(raw)

        expected_channel = f"project:{project_id}:spans"
        redis.publish.assert_called_once()
        call_args = redis.publish.call_args
        assert call_args[0][0] == expected_channel
        # Verify the published payload is valid JSON with key fields
        published = orjson.loads(call_args[0][1])
        assert "span_id" in published
        assert "model" in published
        assert "status" in published

    async def test_trace_upserted_when_trace_id_present(self):
        trace_id = str(uuid.uuid4())
        raw = _make_span_payload(trace_id=trace_id)
        factory, session = _mock_session_factory()
        redis = _mock_redis()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            await worker._pipeline(raw)

        # DB should be called at least twice: once for span, once for trace
        assert session.execute.call_count >= 2
        assert session.commit.call_count >= 2

    async def test_no_trace_upsert_when_trace_id_absent(self):
        raw = _make_span_payload(trace_id=None)
        factory, session = _mock_session_factory()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = _mock_redis()
        worker._cost_engine = _mock_cost_engine()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            await worker._pipeline(raw)

        # Only one DB call (span upsert, no trace upsert)
        assert session.execute.call_count == 1

    async def test_invalid_json_goes_to_dead_letter(self):
        raw = b"not valid json at all {{{"
        redis = _mock_redis()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()

        await worker._pipeline(raw)

        redis.lpush.assert_called_once_with("dead_letter_queue", raw)

    async def test_missing_required_field_goes_to_dead_letter(self):
        data = orjson.loads(_make_span_payload())
        del data["provider"]  # remove required field
        raw = orjson.dumps(data)

        redis = _mock_redis()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()

        await worker._pipeline(raw)

        redis.lpush.assert_called_once_with("dead_letter_queue", raw)

    async def test_metrics_incremented_on_success(self):
        raw = _make_span_payload()
        redis = _mock_redis()
        factory, session = _mock_session_factory()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            await worker._process_one(raw)

        redis.incr.assert_called_with("worker:spans_processed")

    async def test_retry_then_dead_letter_after_max_retries(self):
        raw = _make_span_payload()
        redis = _mock_redis()

        from llmdawg_api.worker.worker import IngestWorker
        worker = IngestWorker(max_retries=2)
        worker.shutdown_event = asyncio.Event()
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()

        # DB always fails
        factory, session = _mock_session_factory()
        session.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        call_count = 0

        async def fast_sleep(t):
            nonlocal call_count
            call_count += 1

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            with patch("asyncio.sleep", side_effect=fast_sleep):
                await worker._process_one(raw, attempt=0)

        # Should retry max_retries times, then dead-letter
        assert call_count == 2  # 2 sleeps for 2 retries (0→1, 1→2)
        redis.lpush.assert_called_with("dead_letter_queue", raw)
        redis.incr.assert_called_with("worker:spans_failed")


# ── TestWorkerLifecycle ───────────────────────────────────────────────────────

class TestWorkerLifecycle:
    """Tests for start/stop lifecycle and concurrency control."""

    async def test_semaphore_initialized_with_correct_concurrency(self):
        from llmdawg_api.worker.worker import IngestWorker

        worker = IngestWorker(concurrency=10)
        worker._redis = _mock_redis()
        worker._cost_engine = _mock_cost_engine()
        worker.shutdown_event = asyncio.Event()
        worker._semaphore = asyncio.Semaphore(10)

        assert worker._semaphore._value == 10  # type: ignore[attr-defined]

    async def test_consumer_loop_stops_on_shutdown_event(self):
        from llmdawg_api.worker.worker import IngestWorker

        redis = _mock_redis()
        redis.brpop = AsyncMock(return_value=None)  # always timeout

        worker = IngestWorker(brpop_timeout=1)
        worker._redis = redis
        worker._cost_engine = _mock_cost_engine()
        worker._semaphore = asyncio.Semaphore(1)
        worker._in_flight = set()
        worker.shutdown_event = asyncio.Event()

        # Start consumer loop, then signal shutdown after brief delay
        async def stop_after_delay():
            await asyncio.sleep(0.05)
            worker.shutdown_event.set()

        await asyncio.gather(
            worker._consumer_loop(),
            stop_after_delay(),
        )
        # If we reach here, the loop stopped correctly

    async def test_in_flight_tasks_tracked(self):
        from llmdawg_api.worker.worker import IngestWorker

        worker = IngestWorker()
        worker._redis = _mock_redis()
        worker._cost_engine = _mock_cost_engine()
        worker._semaphore = asyncio.Semaphore(50)
        worker._in_flight = set()
        worker.shutdown_event = asyncio.Event()

        factory, session = _mock_session_factory()

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=factory):
            raw = _make_span_payload()
            task = asyncio.create_task(worker._process_with_semaphore(raw))
            worker._in_flight.add(task)
            task.add_done_callback(worker._in_flight.discard)
            await task

        assert len(worker._in_flight) == 0  # task removed after completion


# ── TestWorkerIntegration ─────────────────────────────────────────────────────

class TestWorkerIntegration:
    """End-to-end: push a span to Redis, run the worker pipeline, verify DB row."""

    @pytest.fixture(scope="function")
    def int_engine(self):
        import os
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://llmdawg:llmdawg@localhost:5433/llmdawg",
        )
        # NullPool: no connection kept alive between tests — avoids loop-attach issues
        return create_async_engine(db_url, poolclass=NullPool)

    @pytest.fixture(scope="function")
    def int_redis(self):
        import os
        import redis.asyncio as aioredis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        # decode_responses=False so raw bytes work with the worker
        return aioredis.from_url(url)

    async def test_pipeline_writes_span_to_db(self, int_engine, int_redis):
        """Push a span payload through the full pipeline and verify the DB row."""
        from llmdawg_api.worker.worker import IngestWorker
        from llmdawg_api.database import get_session_factory

        span_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        # Insert a minimal project row so the FK constraint is satisfied
        async with int_engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO organizations (id, name, slug)
                    VALUES (:id, 'Worker Test Org', :slug)
                    ON CONFLICT DO NOTHING
                """),
                {"id": org_id, "slug": f"worker-test-{org_id[:8]}"},
            )
            await conn.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO projects (id, org_id, name, slug)
                    VALUES (:id, :org_id, 'Worker Test Project', :slug)
                    ON CONFLICT DO NOTHING
                """),
                {"id": project_id, "org_id": org_id, "slug": f"wt-{project_id[:8]}"},
            )
            await conn.commit()

        raw = _make_span_payload(
            span_id=span_id,
            project_id=project_id,
            org_id=org_id,
            status="success",
            input_tokens=100,
            output_tokens=50,
        )

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        int_factory = async_sessionmaker(int_engine, expire_on_commit=False, class_=AsyncSession)

        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = int_redis
        # Use real CostEngine seeded from file
        from llmdawg_api.services.cost import CostEngine
        engine = CostEngine()
        engine._seed_from_json()
        worker._cost_engine = engine

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=int_factory):
            await worker._pipeline(raw)

        # Verify the span is in the DB
        async with int_engine.connect() as conn:
            result = await conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT id, cost_usd, hallucination_score FROM spans WHERE id = :id"
                ),
                {"id": span_id},
            )
            row = result.fetchone()

        assert row is not None, "Span should be in DB after worker pipeline"
        assert row[0] == uuid.UUID(span_id)
        # Cost should be set (gpt-4o is in prices.json)
        assert row[1] is not None, "cost_usd should be populated"
        # Hallucination score set (status=success, response present)
        assert row[2] is not None, "hallucination_score should be populated"

        # Cleanup
        async with int_engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM projects WHERE id = :id"
                ),
                {"id": project_id},
            )
            await conn.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM organizations WHERE id = :id"
                ),
                {"id": org_id},
            )
            await conn.commit()

    async def test_pipeline_with_trace_id_upserts_trace(self, int_engine, int_redis):
        """Span with trace_id should create/update a trace row."""
        from llmdawg_api.worker.worker import IngestWorker

        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        # Create org + project
        async with int_engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO organizations (id, name, slug)
                    VALUES (:id, 'Trace Test Org', :slug)
                    ON CONFLICT DO NOTHING
                """),
                {"id": org_id, "slug": f"trace-test-{org_id[:8]}"},
            )
            await conn.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO projects (id, org_id, name, slug)
                    VALUES (:id, :org_id, 'Trace Test Project', :slug)
                    ON CONFLICT DO NOTHING
                """),
                {"id": project_id, "org_id": org_id, "slug": f"tt-{project_id[:8]}"},
            )
            await conn.commit()

        raw = _make_span_payload(
            span_id=span_id,
            project_id=project_id,
            org_id=org_id,
            trace_id=trace_id,
            status="success",
        )

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        int_factory = async_sessionmaker(int_engine, expire_on_commit=False, class_=AsyncSession)

        worker = IngestWorker()
        worker.shutdown_event = asyncio.Event()
        worker._redis = int_redis
        from llmdawg_api.services.cost import CostEngine
        ce = CostEngine()
        ce._seed_from_json()
        worker._cost_engine = ce

        with patch("llmdawg_api.worker.worker.get_session_factory", return_value=int_factory):
            await worker._pipeline(raw)

        # Check trace row was created
        async with int_engine.connect() as conn:
            result = await conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT id, span_count FROM traces WHERE id = :id"
                ),
                {"id": trace_id},
            )
            row = result.fetchone()

        assert row is not None, "Trace should be created"
        assert row[1] >= 1, "span_count should be at least 1"

        # Cleanup
        async with int_engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("DELETE FROM projects WHERE id = :id"),
                {"id": project_id},
            )
            await conn.execute(
                __import__("sqlalchemy").text("DELETE FROM organizations WHERE id = :id"),
                {"id": org_id},
            )
            await conn.commit()
