"""Prediction engine — orchestrator + scheduler.

`run_predictions_for_project` runs the three Tier-2 analysers for one project,
each in its own transaction (so one failure can't poison the others), then
resolves insights whose condition the latest run no longer reproduces.

`PredictionScheduler` runs the whole sweep on an interval from inside the
ingest worker process — no extra service to deploy. Set the cadence with
WHYLLM_PREDICTION_INTERVAL_SEC (default 900 = 15 minutes).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from whyllm_api.database import get_session_factory
from whyllm_api.services.predictions import cost_forecast, drift, rate_limit
from whyllm_api.services.predictions.store import resolve_unlisted

log = logging.getLogger(__name__)

# type name -> analyser. Each analyser owns one insight `type`.
_ANALYSERS = {
    "cost_forecast": cost_forecast.analyze,
    "rate_limit_eta": rate_limit.analyze,
    "model_drift": drift.analyze,
}

_DEFAULT_INTERVAL_SEC = 900   # 15 minutes
_INITIAL_DELAY_SEC = 60       # let the worker settle before the first sweep


async def run_predictions_for_project(
    project_id: uuid.UUID, org_id: uuid.UUID
) -> int:
    """Run every analyser for one project. Returns the count of insights emitted.

    Each analyser runs in its own session/transaction: a failure is logged and
    skipped without aborting the others or wrongly resolving live insights.
    """
    factory = get_session_factory()
    emitted_by_type: dict[str, list[str] | None] = {}

    for type_name, fn in _ANALYSERS.items():
        try:
            async with factory() as session:
                keys = await fn(session, project_id, org_id)
                await session.commit()
            emitted_by_type[type_name] = keys or []
        except Exception as exc:
            # None = "ran unreliably" — don't resolve this type's insights.
            emitted_by_type[type_name] = None
            log.warning(
                "predictions: %s failed [proj=%s]: %s",
                type_name, str(project_id)[:8], exc,
            )

    # Resolve insights the latest run no longer re-emits — only for analysers
    # that succeeded (a failed run must not silently close real insights).
    for type_name, keys in emitted_by_type.items():
        if keys is None:
            continue
        try:
            async with factory() as session:
                await resolve_unlisted(session, project_id, keys, [type_name])
                await session.commit()
        except Exception as exc:
            log.warning(
                "predictions: resolve %s failed [proj=%s]: %s",
                type_name, str(project_id)[:8], exc,
            )

    total = sum(len(v) for v in emitted_by_type.values() if v)
    if total:
        log.info(
            "predictions: [proj=%s] %d active insight(s)",
            str(project_id)[:8], total,
        )
    return total


async def run_all_projects() -> None:
    """Sweep every project with span activity in the last 30 days."""
    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT project_id, org_id
                    FROM spans
                    WHERE created_at >= :since
                    """
                ),
                {"since": datetime.now(tz=timezone.utc) - timedelta(days=30)},
            )
        ).fetchall()

    log.info("predictions: sweep starting — %d project(s)", len(rows))
    for project_id, org_id in rows:
        try:
            await run_predictions_for_project(project_id, org_id)
        except Exception as exc:
            log.warning(
                "predictions: project sweep failed [proj=%s]: %s",
                str(project_id)[:8], exc,
            )
    log.info("predictions: sweep complete")


class PredictionScheduler:
    """Periodic Tier-2 sweep — lives inside the ingest worker process."""

    def __init__(self, interval_sec: int | None = None) -> None:
        self._interval = interval_sec or int(
            os.environ.get("WHYLLM_PREDICTION_INTERVAL_SEC", _DEFAULT_INTERVAL_SEC)
        )
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(
            self._loop(), name="prediction-scheduler"
        )
        log.info(
            "PredictionScheduler started — interval=%ds", self._interval
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("PredictionScheduler stopped.")

    async def _loop(self) -> None:
        # Initial settle delay — bail early if shutdown beats it.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=_INITIAL_DELAY_SEC)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                await run_all_projects()
            except Exception as exc:
                log.error("PredictionScheduler sweep error: %s", exc)
            # Sleep until the next sweep, or wake immediately on shutdown.
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                return
            except asyncio.TimeoutError:
                continue
