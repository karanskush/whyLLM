"""Seed a demo scenario that triggers all three prediction-engine insight types.

Backdates spans + a monthly budget into an existing project so the prediction
engine produces a ``cost_forecast``, a ``rate_limit_eta``, and a ``model_drift``
insight immediately — useful for exercising the Insights dashboard without
waiting days for real traffic to accumulate.

Usage (inside the API or worker container)::

    python -m whyllm_api.scripts.seed_demo_insights --project-id <uuid>

Re-running is safe: demo spans are tagged ``{"demo_seed": true}`` and cleared
at the start of every run. A demo monthly budget is only added if the project
has none. Pass ``--no-sweep`` to skip running the engine afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from whyllm_api.database import get_session_factory

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed_demo_insights")

_SPAN_COLS = (
    "id, project_id, org_id, created_at, started_at, provider, model, status, "
    "kind, environment, source, input_tokens, output_tokens, cost_usd, "
    "latency_ms, error_type, timings, tags"
)
_SPAN_VALS = (
    ":id, :project_id, :org_id, :created_at, :started_at, :provider, :model, "
    ":status, :kind, :environment, :source, :input_tokens, :output_tokens, "
    ":cost_usd, :latency_ms, :error_type, CAST(:timings AS jsonb), "
    """CAST('{"demo_seed": true}' AS jsonb)"""
)


def _spans(project_id, org_id, *, n, created_at, **cols):
    """Build `n` span param dicts for one executemany insert."""
    row = {
        "project_id": str(project_id),
        "org_id": str(org_id),
        "kind": "llm_call",
        "environment": "production",
        "source": "proxy",
        "provider": cols.get("provider", "openai"),
        "model": cols.get("model", "gpt-4o"),
        "status": cols.get("status", "success"),
        "input_tokens": cols.get("input_tokens", 1200),
        "output_tokens": cols.get("output_tokens", 600),
        "cost_usd": cols.get("cost_usd"),
        "latency_ms": cols.get("latency_ms", 800),
        "error_type": cols.get("error_type"),
        "timings": json.dumps(cols["timings"]) if cols.get("timings") else None,
        "created_at": created_at,
        "started_at": created_at,
    }
    return [{**row, "id": str(uuid.uuid4())} for _ in range(n)]


async def seed(project_id: uuid.UUID, run_sweep: bool) -> None:
    factory = get_session_factory()
    now = datetime.now(tz=timezone.utc)

    async with factory() as session:
        # ── Resolve the owning org ──────────────────────────────────────────
        row = (
            await session.execute(
                text("SELECT org_id FROM projects WHERE id = :id"),
                {"id": str(project_id)},
            )
        ).fetchone()
        if not row:
            raise SystemExit(f"Project {project_id} not found.")
        org_id = row[0]

        # ── Clear any previous demo spans (idempotent re-runs) ──────────────
        await session.execute(
            text("DELETE FROM spans WHERE project_id = :p AND tags->>'demo_seed' = 'true'"),
            {"p": str(project_id)},
        )

        batches: list[list[dict]] = []

        # ── Scenario 1: cost_forecast — spend across 5 days this month ───────
        for offset in (1, 3, 5, 8, 12):
            batches.append(
                _spans(
                    project_id, org_id, n=1,
                    created_at=now - timedelta(days=offset),
                    cost_usd="8.00000000",
                )
            )

        # ── Scenario 2: rate_limit_eta — 25 recent calls, low headroom + 429s ┐
        batches.append(
            _spans(
                project_id, org_id, n=21,
                created_at=now - timedelta(minutes=18),
                timings={
                    "rate_limit_remaining_tokens": 800,
                    "rate_limit_limit_tokens": 120000,
                },
            )
        )
        batches.append(
            _spans(
                project_id, org_id, n=4,
                created_at=now - timedelta(minutes=12),
                status="error", error_type="rate_limit_exceeded",
            )
        )

        # ── Scenario 3: model_drift — latency regression vs 7-day baseline ──┐
        batches.append(
            _spans(
                project_id, org_id, n=60,
                created_at=now - timedelta(days=4),
                model="gpt-4o-demo", latency_ms=210,
            )
        )
        batches.append(
            _spans(
                project_id, org_id, n=60,
                created_at=now - timedelta(hours=2),
                model="gpt-4o-demo", latency_ms=720,
            )
        )

        total = 0
        for batch in batches:
            await session.execute(
                text(f"INSERT INTO spans ({_SPAN_COLS}) VALUES ({_SPAN_VALS})"),
                batch,
            )
            total += len(batch)

        # ── A tight monthly budget so the cost projection has something to ──
        #    breach. Only added if the project has none — real budgets are
        #    left untouched.
        existing = (
            await session.execute(
                text(
                    "SELECT count(*) FROM cost_budgets "
                    "WHERE project_id = :p AND period = 'monthly' AND is_active = true"
                ),
                {"p": str(project_id)},
            )
        ).scalar()
        budget_note = "kept existing monthly budget"
        if not existing:
            await session.execute(
                text(
                    "INSERT INTO cost_budgets "
                    "(project_id, scope, amount_usd, period, action, is_active) "
                    "VALUES (:p, 'project', 25, 'monthly', 'alert', true)"
                ),
                {"p": str(project_id)},
            )
            budget_note = "added a $25/mo demo budget"

        await session.commit()

    log.info("Seeded %d demo spans into project %s (%s).", total, project_id, budget_note)

    # ── Run the engine now so insights appear without the 15-min wait ───────
    if run_sweep:
        from whyllm_api.services.predictions.engine import run_predictions_for_project

        count = await run_predictions_for_project(project_id, org_id)
        log.info("Prediction sweep complete — %d active insight(s).", count)
        log.info("Open the Insights tab in the dashboard to see them.")
    else:
        log.info("Skipped sweep. Trigger it with run_predictions_for_project().")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-id", required=True, help="UUID of the project to seed into"
    )
    parser.add_argument(
        "--no-sweep", action="store_true", help="skip running the prediction engine"
    )
    args = parser.parse_args()

    try:
        project_id = uuid.UUID(args.project_id)
    except ValueError:
        raise SystemExit(f"Invalid --project-id: {args.project_id!r}")

    asyncio.run(seed(project_id, run_sweep=not args.no_sweep))


if __name__ == "__main__":
    main()
