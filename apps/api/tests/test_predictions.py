"""Prediction engine tests — store, cost_forecast, rate_limit, drift, engine.

Integration tests: each seeds spans / budgets into the live Docker DB, runs a
Tier-2 analyser, and asserts the `insights` it produces. Every test gets a
fresh project_id so seeded rows never collide; teardown deletes the project,
which cascades spans / insights / budgets via the FK.

Mirrors the NullPool + async_sessionmaker pattern used by TestWorkerIntegration
in test_worker.py.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://whyllm:whyllm@localhost:5433/whyllm",
)

_SPAN_COLUMNS = (
    "id, project_id, org_id, created_at, started_at, provider, model, status, "
    "kind, environment, source, input_tokens, output_tokens, cost_usd, "
    "latency_ms, ttft_ms, hallucination_score, error_type, timings, response"
)
_SPAN_PLACEHOLDERS = (
    ":id, :project_id, :org_id, :created_at, :started_at, :provider, :model, "
    ":status, :kind, :environment, :source, :input_tokens, :output_tokens, "
    ":cost_usd, :latency_ms, :ttft_ms, :hallucination_score, :error_type, "
    "CAST(:timings AS jsonb), CAST(:response AS jsonb)"
)


# ── Fixture: a throwaway project on the live DB ───────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def db():
    """Yield a NullPool engine + session factory + a freshly created project.

    Teardown deletes the project (cascades spans / insights / budgets) and the
    organization, then disposes the engine.
    """
    engine = create_async_engine(_DB_URL, poolclass=NullPool)
    org_id = uuid.uuid4()
    project_id = uuid.uuid4()

    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO organizations (id, name, slug) "
                "VALUES (:id, 'Pred Test Org', :slug)"
            ),
            {"id": str(org_id), "slug": f"pred-{org_id.hex[:8]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO projects (id, org_id, name, slug) "
                "VALUES (:id, :org, 'Pred Test Project', :slug)"
            ),
            {"id": str(project_id), "org": str(org_id), "slug": f"predp-{project_id.hex[:8]}"},
        )
        await conn.commit()

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield {
            "engine": engine,
            "factory": factory,
            "project_id": project_id,
            "org_id": org_id,
        }
    finally:
        async with engine.connect() as conn:
            await conn.execute(
                text("DELETE FROM projects WHERE id = :id"), {"id": str(project_id)}
            )
            await conn.execute(
                text("DELETE FROM organizations WHERE id = :id"), {"id": str(org_id)}
            )
            await conn.commit()
        await engine.dispose()


# ── Seeding helpers ───────────────────────────────────────────────────────────

async def _seed_spans(
    conn,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    n: int,
    created_at: datetime,
    provider: str = "openai",
    model: str = "gpt-4o",
    status: str = "success",
    input_tokens: Optional[int] = 100,
    output_tokens: Optional[int] = 50,
    cost_usd: Optional[str] = None,
    latency_ms: Optional[int] = 500,
    ttft_ms: Optional[int] = None,
    hallucination_score: Optional[str] = None,
    error_type: Optional[str] = None,
    timings: Optional[dict[str, Any]] = None,
) -> None:
    """Bulk-insert `n` identical spans (one executemany)."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "org_id": str(org_id),
            "created_at": created_at,
            "started_at": created_at,
            "provider": provider,
            "model": model,
            "status": status,
            "kind": "llm_call",
            "environment": "production",
            "source": "proxy",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "ttft_ms": ttft_ms,
            "hallucination_score": hallucination_score,
            "error_type": error_type,
            "timings": json.dumps(timings) if timings is not None else None,
            "response": None,
        }
        for _ in range(n)
    ]
    await conn.execute(
        text(
            f"INSERT INTO spans ({_SPAN_COLUMNS}) VALUES ({_SPAN_PLACEHOLDERS})"
        ),
        rows,
    )


async def _insights(engine, project_id: uuid.UUID, dedup_key: Optional[str] = None) -> list:
    """Return insight rows for a project, optionally filtered by dedup_key."""
    sql = "SELECT type, severity, status, dedup_key, title, detail FROM insights WHERE project_id = :p"
    params: dict[str, Any] = {"p": str(project_id)}
    if dedup_key is not None:
        sql += " AND dedup_key = :d"
        params["d"] = dedup_key
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).fetchall()


# ── store ─────────────────────────────────────────────────────────────────────

async def test_store_upsert_is_idempotent_and_resolves(db):
    """upsert_insight on the same dedup_key updates one row; resolve_unlisted
    closes a key the latest run did not re-emit."""
    from whyllm_api.services.predictions.store import resolve_unlisted, upsert_insight

    pid, oid, factory = db["project_id"], db["org_id"], db["factory"]

    async with factory() as s:
        await upsert_insight(
            s, project_id=pid, org_id=oid, type="cost_forecast", dedup_key="k1",
            severity="info", title="First", summary="S1", detail={"v": 1},
        )
        await s.commit()
    async with factory() as s:
        await upsert_insight(
            s, project_id=pid, org_id=oid, type="cost_forecast", dedup_key="k1",
            severity="warning", title="Second", summary="S2", detail={"v": 2},
        )
        await s.commit()

    rows = await _insights(db["engine"], pid, "k1")
    assert len(rows) == 1, "upsert must not duplicate the (project, dedup_key) row"
    assert rows[0].severity == "warning"
    assert rows[0].title == "Second"
    assert rows[0].detail == {"v": 2}

    # k1 was not re-emitted this run -> it should resolve.
    async with factory() as s:
        await resolve_unlisted(s, pid, [], ["cost_forecast"])
        await s.commit()
    assert (await _insights(db["engine"], pid, "k1"))[0].status == "resolved"


async def test_store_resolve_keeps_active_keys_open(db):
    """resolve_unlisted must leave a still-active dedup_key open."""
    from whyllm_api.services.predictions.store import resolve_unlisted, upsert_insight

    pid, oid, factory = db["project_id"], db["org_id"], db["factory"]
    async with factory() as s:
        await upsert_insight(
            s, project_id=pid, org_id=oid, type="model_drift", dedup_key="keep",
            severity="info", title="Keep", summary="S", detail={},
        )
        await s.commit()
    async with factory() as s:
        await resolve_unlisted(s, pid, ["keep"], ["model_drift"])
        await s.commit()
    assert (await _insights(db["engine"], pid, "keep"))[0].status == "open"


# ── cost_forecast ─────────────────────────────────────────────────────────────

async def test_cost_forecast_flags_budget_overrun(db):
    """Spend that projects past a monthly budget produces a cost_forecast insight."""
    from whyllm_api.services.predictions import cost_forecast

    pid, oid = db["project_id"], db["org_id"]
    now = datetime.now(tz=timezone.utc)

    async with db["engine"].connect() as conn:
        # $5 of spend on each of 5 distinct days this month.
        for offset in (1, 3, 5, 8, 12):
            await _seed_spans(
                conn, pid, oid, n=1, created_at=now - timedelta(days=offset),
                cost_usd="5.00000000",
            )
        # A tight $10 monthly budget — projection will blow past it.
        await conn.execute(
            text(
                "INSERT INTO cost_budgets (project_id, scope, amount_usd, period, action, is_active) "
                "VALUES (:p, 'project', 10, 'monthly', 'alert', true)"
            ),
            {"p": str(pid)},
        )
        await conn.commit()

    async with db["factory"]() as s:
        emitted = await cost_forecast.analyze(s, pid, oid)
        await s.commit()

    assert "cost_forecast:monthly" in emitted
    rows = await _insights(db["engine"], pid, "cost_forecast:monthly")
    assert len(rows) == 1
    assert rows[0].type == "cost_forecast"
    assert rows[0].severity in ("warning", "critical")
    assert rows[0].detail["budget_usd"] == 10
    assert rows[0].detail["projected_month_usd"] > 10


async def test_cost_forecast_silent_when_under_budget(db):
    """The same spend under a generous budget produces no monthly insight."""
    from whyllm_api.services.predictions import cost_forecast

    pid, oid = db["project_id"], db["org_id"]
    now = datetime.now(tz=timezone.utc)

    async with db["engine"].connect() as conn:
        for offset in (1, 3, 5, 8, 12):
            await _seed_spans(
                conn, pid, oid, n=1, created_at=now - timedelta(days=offset),
                cost_usd="5.00000000",
            )
        await conn.execute(
            text(
                "INSERT INTO cost_budgets (project_id, scope, amount_usd, period, action, is_active) "
                "VALUES (:p, 'project', 100000, 'monthly', 'alert', true)"
            ),
            {"p": str(pid)},
        )
        await conn.commit()

    async with db["factory"]() as s:
        emitted = await cost_forecast.analyze(s, pid, oid)
        await s.commit()

    assert "cost_forecast:monthly" not in emitted
    assert await _insights(db["engine"], pid, "cost_forecast:monthly") == []


# ── rate_limit ────────────────────────────────────────────────────────────────

async def test_rate_limit_detects_throttling(db):
    """Provider rate-limit 429s in the window produce a throttled insight."""
    from whyllm_api.services.predictions import rate_limit

    pid, oid = db["project_id"], db["org_id"]
    now = datetime.now(tz=timezone.utc)
    recent = now - timedelta(minutes=20)

    async with db["engine"].connect() as conn:
        await _seed_spans(conn, pid, oid, n=22, created_at=recent, status="success")
        await _seed_spans(
            conn, pid, oid, n=3, created_at=recent,
            status="error", error_type="rate_limit_exceeded",
        )
        await conn.commit()

    async with db["factory"]() as s:
        emitted = await rate_limit.analyze(s, pid, oid)
        await s.commit()

    assert "rate_limit_eta:throttled" in emitted
    rows = await _insights(db["engine"], pid, "rate_limit_eta:throttled")
    assert len(rows) == 1
    assert rows[0].type == "rate_limit_eta"
    assert rows[0].detail["throttled_calls"] == 3


async def test_rate_limit_forecasts_low_headroom(db):
    """Low remaining token headroom (from span.timings) produces an ETA insight."""
    from whyllm_api.services.predictions import rate_limit

    pid, oid = db["project_id"], db["org_id"]
    now = datetime.now(tz=timezone.utc)

    async with db["engine"].connect() as conn:
        await _seed_spans(
            conn, pid, oid, n=25, created_at=now - timedelta(minutes=15),
            input_tokens=100, output_tokens=50,
            timings={"rate_limit_remaining_tokens": 500, "rate_limit_limit_tokens": 100000},
        )
        await conn.commit()

    async with db["factory"]() as s:
        emitted = await rate_limit.analyze(s, pid, oid)
        await s.commit()

    assert "rate_limit_eta:headroom" in emitted
    rows = await _insights(db["engine"], pid, "rate_limit_eta:headroom")
    assert len(rows) == 1
    assert rows[0].detail["remaining_tokens"] == 500
    assert rows[0].detail["headroom_pct"] < 15


# ── drift ─────────────────────────────────────────────────────────────────────

async def test_drift_detects_latency_regression(db):
    """A latency jump in the recent window vs the baseline produces a drift insight."""
    from whyllm_api.services.predictions import drift

    pid, oid = db["project_id"], db["org_id"]
    now = datetime.now(tz=timezone.utc)
    model = "gpt-4o-drifttest"

    async with db["engine"].connect() as conn:
        # Baseline: 60 fast calls 4 days ago.
        await _seed_spans(
            conn, pid, oid, n=60, created_at=now - timedelta(days=4),
            model=model, latency_ms=200,
        )
        # Recent: 60 slow calls 2 hours ago — +200% latency.
        await _seed_spans(
            conn, pid, oid, n=60, created_at=now - timedelta(hours=2),
            model=model, latency_ms=600,
        )
        await conn.commit()

    async with db["factory"]() as s:
        emitted = await drift.analyze(s, pid, oid)
        await s.commit()

    dedup = f"model_drift:{model}"
    assert dedup in emitted
    rows = await _insights(db["engine"], pid, dedup)
    assert len(rows) == 1
    assert rows[0].type == "model_drift"
    assert any("latency" in shift for shift in rows[0].detail["shifts"])


async def test_drift_silent_without_enough_samples(db):
    """Below the per-window sample floor, drift stays silent."""
    from whyllm_api.services.predictions import drift

    pid, oid = db["project_id"], db["org_id"]
    now = datetime.now(tz=timezone.utc)
    model = "gpt-4o-tinytest"

    async with db["engine"].connect() as conn:
        await _seed_spans(
            conn, pid, oid, n=10, created_at=now - timedelta(days=4),
            model=model, latency_ms=200,
        )
        await _seed_spans(
            conn, pid, oid, n=10, created_at=now - timedelta(hours=2),
            model=model, latency_ms=600,
        )
        await conn.commit()

    async with db["factory"]() as s:
        emitted = await drift.analyze(s, pid, oid)
        await s.commit()

    assert emitted == []


# ── engine orchestrator ───────────────────────────────────────────────────────

async def test_engine_runs_all_analysers_for_project(db):
    """run_predictions_for_project drives every analyser and persists insights."""
    from unittest.mock import patch

    from whyllm_api.services.predictions import engine as pred_engine

    pid, oid = db["project_id"], db["org_id"]
    now = datetime.now(tz=timezone.utc)
    model = "gpt-4o-enginetest"

    async with db["engine"].connect() as conn:
        # Drift scenario — guarantees at least one insight.
        await _seed_spans(
            conn, pid, oid, n=60, created_at=now - timedelta(days=4),
            model=model, latency_ms=200,
        )
        await _seed_spans(
            conn, pid, oid, n=60, created_at=now - timedelta(hours=2),
            model=model, latency_ms=600,
        )
        await conn.commit()

    # The engine resolves its sessions via get_session_factory — point it at
    # the test engine so it writes to the same throwaway project.
    with patch(
        "whyllm_api.services.predictions.engine.get_session_factory",
        return_value=db["factory"],
    ):
        total = await pred_engine.run_predictions_for_project(pid, oid)

    assert total >= 1
    drift_rows = await _insights(db["engine"], pid, f"model_drift:{model}")
    assert len(drift_rows) == 1
