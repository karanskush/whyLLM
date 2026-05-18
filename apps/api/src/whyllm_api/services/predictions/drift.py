"""Model drift detection — Tier 2.

Compares a recent 24h window against a lagged 7-day baseline, per model, and
flags meaningful shifts in latency, error rate, or hallucination score — the
silent provider-side changes that otherwise surface only as user complaints.

A changed `system_fingerprint` corroborates a drift call but never triggers
one on its own: fingerprints are not unique per build, so they are evidence,
not a signal.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from whyllm_api.services.predictions.store import upsert_insight

log = logging.getLogger(__name__)

_MIN_SAMPLES = 50       # per window, per model — below this it's noise
_LATENCY_SHIFT = 0.30   # +30% relative latency
_HALLUC_SHIFT = 0.15    # +0.15 absolute hallucination score (0-1 scale)
_ERROR_SHIFT = 0.10     # +10 percentage points error rate


async def analyze(
    session: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> list[str]:
    """Emit drift insights for a project. Returns the dedup_keys emitted."""
    emitted: list[str] = []
    now = datetime.now(tz=timezone.utc)
    recent_start = now - timedelta(hours=24)
    baseline_start = now - timedelta(days=8)

    rows = (
        await session.execute(
            text(
                """
                WITH windowed AS (
                    SELECT
                        model,
                        CASE WHEN created_at >= :recent_start
                             THEN 'recent' ELSE 'baseline' END AS w,
                        latency_ms, status, hallucination_score
                    FROM spans
                    WHERE project_id = :pid
                      AND created_at >= :baseline_start
                      AND model <> 'unknown'
                )
                SELECT
                    model, w,
                    COUNT(*)::int                                          AS n,
                    AVG(latency_ms)::float                                  AS avg_latency,
                    AVG(CASE WHEN status = 'error' THEN 1.0 ELSE 0.0 END)::float
                                                                            AS error_rate,
                    AVG(hallucination_score)::float                         AS avg_halluc
                FROM windowed
                GROUP BY model, w
                """
            ),
            {
                "pid": str(project_id),
                "recent_start": recent_start,
                "baseline_start": baseline_start,
            },
        )
    ).fetchall()

    by_model: dict[str, dict[str, dict]] = {}
    for model, w, n, avg_latency, error_rate, avg_halluc in rows:
        by_model.setdefault(model, {})[w] = {
            "n": n,
            "avg_latency": avg_latency,
            "error_rate": error_rate,
            "avg_halluc": avg_halluc,
        }

    for model, windows in by_model.items():
        base = windows.get("baseline")
        recent = windows.get("recent")
        if not base or not recent:
            continue
        if base["n"] < _MIN_SAMPLES or recent["n"] < _MIN_SAMPLES:
            continue

        shifts: list[str] = []
        severity = "info"

        bl, rl = base["avg_latency"], recent["avg_latency"]
        if bl and rl and rl > bl * (1 + _LATENCY_SHIFT):
            shifts.append(
                f"latency +{(rl / bl - 1) * 100:.0f}% ({bl:.0f}ms -> {rl:.0f}ms)"
            )
            severity = "warning"

        be, re_ = base["error_rate"] or 0.0, recent["error_rate"] or 0.0
        if re_ - be >= _ERROR_SHIFT:
            shifts.append(
                f"error rate +{(re_ - be) * 100:.0f}pp "
                f"({be * 100:.0f}% -> {re_ * 100:.0f}%)"
            )
            severity = "warning"

        bh, rh = base["avg_halluc"], recent["avg_halluc"]
        if bh is not None and rh is not None and rh - bh >= _HALLUC_SHIFT:
            shifts.append(
                f"hallucination score +{rh - bh:.2f} ({bh:.2f} -> {rh:.2f})"
            )
            severity = "critical"

        if not shifts:
            continue

        # ── Fingerprint corroboration ───────────────────────────────────────
        fp_rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        CASE WHEN created_at >= :recent_start
                             THEN 'recent' ELSE 'baseline' END AS w,
                        response->>'system_fingerprint'        AS fp
                    FROM spans
                    WHERE project_id = :pid
                      AND model = :model
                      AND created_at >= :baseline_start
                      AND response->>'system_fingerprint' IS NOT NULL
                    GROUP BY 1, 2
                    """
                ),
                {
                    "pid": str(project_id),
                    "model": model,
                    "recent_start": recent_start,
                    "baseline_start": baseline_start,
                },
            )
        ).fetchall()
        base_fps = {r[1] for r in fp_rows if r[0] == "baseline"}
        recent_fps = {r[1] for r in fp_rows if r[0] == "recent"}
        new_fps = sorted(recent_fps - base_fps)
        fp_note = ""
        if new_fps:
            fp_note = (
                f" A new provider build fingerprint appeared "
                f"({', '.join(new_fps)}) — the provider likely changed the "
                f"model under you."
            )

        dedup = f"model_drift:{model}"
        await upsert_insight(
            session,
            project_id=project_id,
            org_id=org_id,
            type="model_drift",
            dedup_key=dedup,
            severity=severity,
            title=f"'{model}' may have drifted",
            summary=(
                f"Model '{model}' shows {len(shifts)} behavioural shift(s) in the "
                f"last 24h vs the 7-day baseline: {'; '.join(shifts)}." + fp_note
            ),
            detail={
                "model": model,
                "shifts": shifts,
                "baseline": {
                    k: base[k]
                    for k in ("n", "avg_latency", "error_rate", "avg_halluc")
                },
                "recent": {
                    k: recent[k]
                    for k in ("n", "avg_latency", "error_rate", "avg_halluc")
                },
                "new_fingerprints": new_fps,
            },
            confidence=0.75 if new_fps else 0.6,
        )
        emitted.append(dedup)

    return emitted
