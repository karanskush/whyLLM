"""Schema smoke tests — runs against the live Docker DB (localhost:5433).

Uses NullPool so every connect() is a fresh connection — no asyncpg
'another operation in progress' from connection pool recycling.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

# --------------------------------------------------------------------------
# Test engine fixture — NullPool guarantees a fresh connection per acquire
# --------------------------------------------------------------------------
_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://whyllm:whyllm@localhost:5433/whyllm",
)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine(_TEST_DB_URL, poolclass=NullPool, echo=False)
    yield eng
    await eng.dispose()


# --------------------------------------------------------------------------
# Helpers — fully materialized inside the async-with before returning
# --------------------------------------------------------------------------

async def _fetchall(engine: AsyncEngine, sql: str) -> list[Any]:
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        return result.fetchall()


async def _fetchone(engine: AsyncEngine, sql: str) -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        return result.fetchone()


async def _scalar(engine: AsyncEngine, sql: str) -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        return result.scalar()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_tables_exist(engine: AsyncEngine) -> None:
    expected = {
        "organizations", "users", "org_members", "projects",
        "api_keys", "model_pricing", "traces", "spans",
        "cost_budgets", "alerts", "alert_events", "insights",
    }
    rows = await _fetchall(engine, """
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename != 'alembic_version'
    """)
    found = {row[0] for row in rows}
    found = {t for t in found if not (t.startswith("spans_") and len(t) > 5)}
    assert expected == found, f"Missing: {expected - found}  Extra: {found - expected}"


@pytest.mark.asyncio
async def test_spans_is_partitioned(engine: AsyncEngine) -> None:
    row = await _fetchone(engine, """
        SELECT relkind FROM pg_class
        WHERE relname = 'spans'
          AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    """)
    assert row is not None, "spans table not found in pg_class"
    # asyncpg may return relkind as bytes or str depending on the pg_class column type
    relkind = row[0].decode() if isinstance(row[0], bytes) else row[0]
    assert relkind == "p", f"spans.relkind = {relkind!r}, expected 'p' (partitioned)"


@pytest.mark.asyncio
async def test_spans_partitions_exist(engine: AsyncEngine) -> None:
    rows = await _fetchall(engine, """
        SELECT relname FROM pg_class
        WHERE relname LIKE 'spans_2026_%' AND relkind = 'r'
        ORDER BY relname
    """)
    partitions = [r[0] for r in rows]
    assert len(partitions) == 3, f"Expected 3 partitions, found: {partitions}"
    assert "spans_2026_04" in partitions
    assert "spans_2026_05" in partitions
    assert "spans_2026_06" in partitions


@pytest.mark.asyncio
async def test_spans_all_indexes_exist(engine: AsyncEngine) -> None:
    rows = await _fetchall(engine, "SELECT indexname FROM pg_indexes WHERE tablename = 'spans'")
    found = {r[0] for r in rows}
    required = {
        "idx_spans_project_created",
        "idx_spans_project_model",
        "idx_spans_project_user",
        "idx_spans_project_status",
        "idx_spans_trace",
        "idx_spans_tags",
    }
    assert required.issubset(found), f"Missing indexes: {required - found}"


@pytest.mark.asyncio
async def test_spans_generated_column(engine: AsyncEngine) -> None:
    row = await _fetchone(engine, """
        SELECT is_generated, generation_expression
        FROM information_schema.columns
        WHERE table_name = 'spans' AND column_name = 'total_tokens'
    """)
    assert row is not None, "total_tokens column not found in information_schema"
    assert row[0] == "ALWAYS", f"Expected ALWAYS generated, got {row[0]!r}"


@pytest.mark.asyncio
async def test_spans_composite_pk(engine: AsyncEngine) -> None:
    """PK must include created_at (PostgreSQL partition key requirement)."""
    rows = await _fetchall(engine, """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'spans'::regclass AND i.indisprimary
        ORDER BY a.attname
    """)
    pk_cols = {r[0] for r in rows}
    assert "id" in pk_cols
    assert "created_at" in pk_cols, "created_at must be in spans PK (partition key constraint)"


@pytest.mark.asyncio
async def test_updated_at_trigger_fires(engine: AsyncEngine) -> None:
    """BEFORE UPDATE trigger on organizations must advance updated_at."""
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO organizations (name, slug) VALUES ('TriggerTest', 'trigger-test')"
        ))
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_sleep(0.015)"))
        await conn.execute(text(
            "UPDATE organizations SET name = 'Updated' WHERE slug = 'trigger-test'"
        ))
    row = await _fetchone(engine, """
        SELECT updated_at > created_at
        FROM organizations WHERE slug = 'trigger-test'
    """)
    assert row is not None
    assert row[0] is True, "updated_at trigger did not advance the timestamp"
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM organizations WHERE slug = 'trigger-test'"))


@pytest.mark.asyncio
async def test_updated_at_triggers_all_tables(engine: AsyncEngine) -> None:
    rows = await _fetchall(engine, """
        SELECT trigger_name FROM information_schema.triggers
        WHERE trigger_schema = 'public'
        ORDER BY trigger_name
    """)
    found = {r[0] for r in rows}
    expected = {
        "trg_organizations_updated_at",
        "trg_users_updated_at",
        "trg_projects_updated_at",
    }
    assert expected == found, f"Trigger mismatch. Found: {found}"


@pytest.mark.asyncio
async def test_model_pricing_seed_count(engine: AsyncEngine) -> None:
    count = await _scalar(engine, "SELECT COUNT(*) FROM model_pricing")
    assert count == 9, f"Expected 9 seed rows, found {count}"


@pytest.mark.asyncio
async def test_model_pricing_gpt4o_accuracy(engine: AsyncEngine) -> None:
    """gpt-4o: $2.50 / $10.00 / $1.25 per 1M → per 1K"""
    row = await _fetchone(engine, """
        SELECT input_cost_per_1k_tokens,
               output_cost_per_1k_tokens,
               cached_input_cost_per_1k_tokens
        FROM model_pricing
        WHERE provider = 'openai' AND model = 'gpt-4o'
    """)
    assert row is not None
    assert float(row[0]) == pytest.approx(0.0025,   rel=1e-6)
    assert float(row[1]) == pytest.approx(0.01,     rel=1e-6)
    assert float(row[2]) == pytest.approx(0.00125,  rel=1e-6)


@pytest.mark.asyncio
async def test_model_pricing_all_providers(engine: AsyncEngine) -> None:
    rows = await _fetchall(engine, """
        SELECT DISTINCT provider FROM model_pricing ORDER BY provider
    """)
    assert [r[0] for r in rows] == ["anthropic", "google", "openai"]


@pytest.mark.asyncio
async def test_alembic_at_head(engine: AsyncEngine) -> None:
    """The DB revision must match the latest migration on disk.

    Resolves the head dynamically from the migration scripts so this test
    never goes stale when a new migration is added.
    """
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    api_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()

    version = await _scalar(engine, "SELECT version_num FROM alembic_version")
    assert version == head, f"DB at {version!r}, migrations head is {head!r}"


@pytest.mark.asyncio
async def test_traces_indexes_exist(engine: AsyncEngine) -> None:
    rows = await _fetchall(engine, """
        SELECT indexname FROM pg_indexes WHERE tablename = 'traces'
    """)
    found = {r[0] for r in rows}
    assert "idx_traces_project_created" in found
    assert "idx_traces_project_user_created" in found


@pytest.mark.asyncio
async def test_foreign_keys_enforce_cascade(engine: AsyncEngine) -> None:
    """org_members.org_id FK must specify ON DELETE CASCADE."""
    rows = await _fetchall(engine, """
        SELECT rc.delete_rule
        FROM information_schema.referential_constraints rc
        JOIN information_schema.table_constraints tc
          ON rc.constraint_name = tc.constraint_name
        WHERE tc.table_name = 'org_members'
          AND tc.constraint_type = 'FOREIGN KEY'
    """)
    # Both FKs (org_id and user_id) must be CASCADE
    rules = {r[0] for r in rows}
    assert rules == {"CASCADE"}, f"Expected all CASCADE, found: {rules}"
