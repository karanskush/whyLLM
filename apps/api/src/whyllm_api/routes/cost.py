"""Cost analytics routes.

GET /v1/projects/:id/cost/breakdown — per-model cost breakdown with top users
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from whyllm_api.database import get_session_factory
from whyllm_api.models.user import User
from whyllm_api.routes.spans import _check_project_access
from whyllm_api.schemas.settings import CostBreakdownItem, CostBreakdownResponse
from whyllm_api.services.auth_service import get_current_user

router = APIRouter(tags=["cost"])

_WINDOWS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get("/v1/projects/{project_id}/cost/breakdown", response_model=CostBreakdownResponse)
async def cost_breakdown(
    project_id: uuid.UUID,
    window: str = Query(default="24h", pattern="^(1h|6h|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
) -> CostBreakdownResponse:
    """Cost breakdown by model/provider for a project."""
    await _check_project_access(project_id, current_user)

    delta = _WINDOWS[window]
    since = datetime.now(tz=timezone.utc) - delta

    factory = get_session_factory()
    async with factory() as session:
        # Per-model breakdown
        result = await session.execute(
            text("""
                SELECT
                    model,
                    provider,
                    COUNT(*)::int                          AS span_count,
                    COALESCE(SUM(cost_usd), 0)             AS total_cost_usd,
                    COALESCE(SUM(input_tokens), 0)::int    AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)::int   AS output_tokens
                FROM spans
                WHERE project_id = :project_id
                  AND created_at >= :since
                GROUP BY model, provider
                ORDER BY total_cost_usd DESC
                LIMIT 50
            """),
            {"project_id": str(project_id), "since": since},
        )
        rows = result.fetchall()

        # Total cost
        total_result = await session.execute(
            text("""
                SELECT COALESCE(SUM(cost_usd), 0)
                FROM spans
                WHERE project_id = :project_id AND created_at >= :since
            """),
            {"project_id": str(project_id), "since": since},
        )
        total_cost = Decimal(str(total_result.scalar() or 0))

        # Top users by cost
        user_result = await session.execute(
            text("""
                SELECT
                    COALESCE(user_id, '(anonymous)')  AS user_id,
                    COUNT(*)::int                     AS span_count,
                    COALESCE(SUM(cost_usd), 0)        AS cost_usd
                FROM spans
                WHERE project_id = :project_id
                  AND created_at >= :since
                GROUP BY user_id
                ORDER BY cost_usd DESC
                LIMIT 10
            """),
            {"project_id": str(project_id), "since": since},
        )
        top_users = [
            {"user_id": r[0], "span_count": r[1], "cost_usd": float(r[2])}
            for r in user_result.fetchall()
        ]

    items = []
    for row in rows:
        row_cost = Decimal(str(row[3]))
        pct = float(row_cost / total_cost * 100) if total_cost else 0.0
        items.append(CostBreakdownItem(
            model=row[0],
            provider=row[1],
            span_count=row[2],
            total_cost_usd=row_cost,
            input_tokens=row[4],
            output_tokens=row[5],
            pct_of_total=round(pct, 2),
        ))

    return CostBreakdownResponse(
        project_id=project_id,
        window=window,
        since=since,
        total_cost_usd=total_cost,
        items=items,
        top_users=top_users,
    )
