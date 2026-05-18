"""Cost-overrun forecasting — Tier 2.

Projects month-to-date spend forward at the recent daily burn rate and
compares it against active monthly cost budgets. Also flags week-over-week
spend acceleration even when no budget is set, so the signal is useful on
day one.
"""

from __future__ import annotations

import calendar
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from whyllm_api.services.predictions.store import upsert_insight

log = logging.getLogger(__name__)

# Don't forecast on noise — need a few days of recorded spend.
_MIN_DAYS_DATA = 3
# Only project the month once it's a few days in (early-month is too noisy).
_MIN_DAY_OF_MONTH = 3
# Week-over-week growth that's worth surfacing on its own.
_ACCEL_THRESHOLD = 0.40  # +40%


async def analyze(
    session: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> list[str]:
    """Emit cost insights for a project. Returns the dedup_keys emitted."""
    emitted: list[str] = []
    now = datetime.now(tz=timezone.utc)

    # ── Daily spend, last 30 days ───────────────────────────────────────────
    rows = (
        await session.execute(
            text(
                """
                SELECT date_trunc('day', created_at) AS d,
                       COALESCE(SUM(cost_usd), 0)     AS spend
                FROM spans
                WHERE project_id = :pid AND created_at >= :since
                GROUP BY 1 ORDER BY 1
                """
            ),
            {"pid": str(project_id), "since": now - timedelta(days=30)},
        )
    ).fetchall()

    if len(rows) < _MIN_DAYS_DATA:
        return emitted

    daily = {r[0].date(): float(r[1]) for r in rows}

    # ── Month-to-date + linear projection ──────────────────────────────────
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day_of_month = now.day
    elapsed_frac = (now - month_start).total_seconds() / (days_in_month * 86400)
    mtd = sum(v for d, v in daily.items() if d >= month_start.date())
    projected_month = mtd / elapsed_frac if elapsed_frac > 0 else mtd

    # Daily burn rate from the last 7 recorded days.
    recent = [daily.get((now - timedelta(days=i)).date(), 0.0) for i in range(1, 8)]
    daily_rate = (
        sum(recent) / 7 if any(recent) else mtd / max(day_of_month, 1)
    )

    # ── Active monthly budgets ──────────────────────────────────────────────
    if day_of_month >= _MIN_DAY_OF_MONTH and mtd > 0:
        budget_rows = (
            await session.execute(
                text(
                    """
                    SELECT amount_usd, action FROM cost_budgets
                    WHERE project_id = :pid
                      AND period = 'monthly'
                      AND is_active = true
                    ORDER BY amount_usd ASC
                    """
                ),
                {"pid": str(project_id)},
            )
        ).fetchall()

        for amount, action in budget_rows:
            budget = float(amount)
            if budget <= 0 or projected_month <= budget:
                continue  # no budget, or on track — nothing to flag

            overrun = projected_month - budget
            # Day-of-month the cumulative spend crosses the budget.
            predicted_for = None
            if daily_rate > 0:
                remaining_to_budget = budget - mtd
                if remaining_to_budget <= 0:
                    cross_day = day_of_month
                else:
                    cross_day = min(
                        days_in_month,
                        day_of_month + int(remaining_to_budget / daily_rate),
                    )
                predicted_for = month_start + timedelta(days=cross_day - 1)

            pct = projected_month / budget * 100
            severity = (
                "critical"
                if action == "block" or projected_month > budget * 1.25
                else "warning"
            )
            summary = (
                f"At the current burn rate (~${daily_rate:,.2f}/day) this project "
                f"is on track to spend ~${projected_month:,.0f} this month — "
                f"{pct:.0f}% of the ${budget:,.0f} budget"
            )
            if predicted_for is not None:
                summary += f", crossing it around {predicted_for:%b} {predicted_for.day}."
            else:
                summary += "."

            dedup = "cost_forecast:monthly"
            await upsert_insight(
                session,
                project_id=project_id,
                org_id=org_id,
                type="cost_forecast",
                dedup_key=dedup,
                severity=severity,
                title=f"Projected to exceed monthly budget by ${overrun:,.0f}",
                summary=summary,
                detail={
                    "month_to_date_usd": round(mtd, 2),
                    "projected_month_usd": round(projected_month, 2),
                    "budget_usd": budget,
                    "budget_action": action,
                    "daily_burn_usd": round(daily_rate, 2),
                    "overrun_usd": round(overrun, 2),
                    "pct_of_budget": round(pct, 1),
                },
                # Confidence grows as the month progresses.
                confidence=min(0.95, 0.40 + elapsed_frac * 0.5),
                predicted_for=predicted_for,
            )
            emitted.append(dedup)
            break  # one monthly-budget insight is enough (tightest budget wins)

    # ── Spend acceleration (no budget required) ─────────────────────────────
    last7 = sum(
        daily.get((now - timedelta(days=i)).date(), 0.0) for i in range(1, 8)
    )
    prev7 = sum(
        daily.get((now - timedelta(days=i)).date(), 0.0) for i in range(8, 15)
    )
    if prev7 > 1.0 and last7 > prev7 * (1 + _ACCEL_THRESHOLD):
        growth = (last7 / prev7 - 1) * 100
        dedup = "cost_forecast:acceleration"
        await upsert_insight(
            session,
            project_id=project_id,
            org_id=org_id,
            type="cost_forecast",
            dedup_key=dedup,
            severity="info",
            title=f"LLM spend up {growth:.0f}% week-over-week",
            summary=(
                f"This project spent ${last7:,.2f} in the last 7 days vs "
                f"${prev7:,.2f} the week before — a {growth:.0f}% increase. "
                f"Worth checking which model or endpoint is driving it."
            ),
            detail={
                "last_7d_usd": round(last7, 2),
                "prev_7d_usd": round(prev7, 2),
                "growth_pct": round(growth, 1),
            },
            confidence=0.8,
        )
        emitted.append(dedup)

    return emitted
