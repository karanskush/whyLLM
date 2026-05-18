"""Rate-limit exhaustion forecasting — Tier 2.

Reads the provider rate-limit headers the proxy already captures into
`span.timings` (remaining + limit tokens), plus any rate-limit 429s in the
window, and predicts throttling before it cascades into user-facing failures.

Two signals:
  1. throttled — the project is already hitting provider 429s.
  2. headroom  — remaining token quota is low, or projected to run out soon
                 at the current burn rate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from whyllm_api.services.predictions.store import upsert_insight

log = logging.getLogger(__name__)

_WINDOW = timedelta(hours=1)
_MIN_SPANS = 20
# Flag when remaining headroom is this fraction of the limit or less.
_HEADROOM_FLOOR = 0.15
# Or when exhaustion is projected within this many minutes.
_ETA_THRESHOLD_MIN = 30


async def analyze(
    session: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> list[str]:
    """Emit rate-limit insights for a project. Returns the dedup_keys emitted."""
    emitted: list[str] = []
    now = datetime.now(tz=timezone.utc)
    since = now - _WINDOW

    row = (
        await session.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (
                        WHERE status = 'error'
                          AND (error_type ILIKE '%rate%'
                               OR error_type ILIKE '%429%'
                               OR error_type ILIKE '%limit%')
                    )::int AS throttled,
                    MIN((timings->>'rate_limit_remaining_tokens')::numeric)
                        AS min_remaining_tokens,
                    MAX((timings->>'rate_limit_limit_tokens')::numeric)
                        AS limit_tokens,
                    COALESCE(SUM(total_tokens), 0)::bigint AS tokens_used
                FROM spans
                WHERE project_id = :pid AND created_at >= :since
                """
            ),
            {"pid": str(project_id), "since": since},
        )
    ).fetchone()

    if not row or row[0] < _MIN_SPANS:
        return emitted

    total, throttled, min_remaining, limit_tokens, tokens_used = row

    # ── Signal 1: already being throttled ───────────────────────────────────
    if throttled and throttled > 0:
        rate = throttled / total * 100
        dedup = "rate_limit_eta:throttled"
        await upsert_insight(
            session,
            project_id=project_id,
            org_id=org_id,
            type="rate_limit_eta",
            dedup_key=dedup,
            severity="critical" if rate > 5 else "warning",
            title=f"Provider rate limits hit on {throttled} call(s) in the last hour",
            summary=(
                f"{throttled} of {total} calls ({rate:.1f}%) failed with provider "
                f"rate-limit errors in the last hour — requests are being throttled. "
                f"Raise the provider quota, spread traffic, or add a fallback model."
            ),
            detail={
                "throttled_calls": throttled,
                "total_calls": total,
                "throttle_rate_pct": round(rate, 2),
                "window": "1h",
            },
            confidence=0.95,
        )
        emitted.append(dedup)

    # ── Signal 2: headroom forecast ─────────────────────────────────────────
    if min_remaining is not None and limit_tokens and float(limit_tokens) > 0:
        remaining = float(min_remaining)
        limit = float(limit_tokens)
        headroom = remaining / limit
        rate_per_min = float(tokens_used) / (_WINDOW.total_seconds() / 60)
        eta_min = remaining / rate_per_min if rate_per_min > 0 else None

        if headroom <= _HEADROOM_FLOOR or (
            eta_min is not None and eta_min <= _ETA_THRESHOLD_MIN
        ):
            dedup = "rate_limit_eta:headroom"
            eta_txt = f"~{eta_min:.0f} min" if eta_min is not None else "soon"
            await upsert_insight(
                session,
                project_id=project_id,
                org_id=org_id,
                type="rate_limit_eta",
                dedup_key=dedup,
                severity="critical" if headroom <= 0.05 else "warning",
                title=(
                    f"Approaching the provider token rate limit "
                    f"({headroom * 100:.0f}% headroom left)"
                ),
                summary=(
                    f"At the current burn rate (~{rate_per_min:,.0f} tokens/min) "
                    f"this project will exhaust its provider token quota in "
                    f"{eta_txt}. Lowest remaining headroom this hour: "
                    f"{remaining:,.0f} / {limit:,.0f} tokens."
                ),
                detail={
                    "remaining_tokens": int(remaining),
                    "limit_tokens": int(limit),
                    "headroom_pct": round(headroom * 100, 1),
                    "burn_tokens_per_min": round(rate_per_min, 1),
                    "eta_minutes": round(eta_min, 1) if eta_min is not None else None,
                },
                confidence=0.7,
                predicted_for=(
                    now + timedelta(minutes=eta_min) if eta_min is not None else None
                ),
            )
            emitted.append(dedup)

    return emitted
