"""Insights API — predictive signals from the prediction engine.

GET   /v1/projects/:id/insights   — list insights (filter by status / type)
PATCH /v1/insights/:insight_id    — acknowledge or resolve an insight

Insights are generated server-side by the Tier-2 prediction engine
(services/predictions/); these routes only read them and let an operator
change their status. There is no create endpoint — the engine owns creation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from whyllm_api.database import get_session_factory
from whyllm_api.models.user import User
from whyllm_api.routes.spans import _check_project_access
from whyllm_api.services.auth_service import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["insights"])

_VALID_STATUSES = ("open", "acknowledged", "resolved")


@router.get("/v1/projects/{project_id}/insights")
async def list_insights(
    project_id: uuid.UUID,
    status: str = Query(
        default="open", pattern="^(open|acknowledged|resolved|all)$"
    ),
    type: Optional[str] = Query(
        default=None, pattern="^(cost_forecast|rate_limit_eta|model_drift)$"
    ),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List a project's insights, severity-ordered (critical first)."""
    await _check_project_access(project_id, current_user)

    clauses = ["project_id = :pid"]
    params: dict = {"pid": str(project_id)}
    if status != "all":
        clauses.append("status = :status")
        params["status"] = status
    if type:
        clauses.append("type = :type")
        params["type"] = type
    where = " AND ".join(clauses)

    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT id, type, severity, status, title, summary, detail,
                           confidence::float AS confidence,
                           predicted_for, created_at, updated_at
                    FROM insights
                    WHERE {where}
                    ORDER BY
                        CASE severity
                            WHEN 'critical' THEN 0
                            WHEN 'warning'  THEN 1
                            ELSE 2
                        END,
                        updated_at DESC
                    LIMIT 200
                    """
                ),
                params,
            )
        ).mappings().all()

    return {"insights": [dict(r) for r in rows], "count": len(rows)}


class InsightStatusUpdate(BaseModel):
    status: str  # acknowledged | resolved | open


@router.patch("/v1/insights/{insight_id}")
async def update_insight(
    insight_id: uuid.UUID,
    body: InsightStatusUpdate,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Acknowledge or resolve an insight (or re-open it)."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_status", "allowed": list(_VALID_STATUSES)},
        )

    factory = get_session_factory()
    async with factory() as session:
        row = (
            await session.execute(
                text("SELECT project_id FROM insights WHERE id = :id"),
                {"id": str(insight_id)},
            )
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404, detail={"error": "insight_not_found"}
        )

    # Authorize against the owning project before mutating.
    await _check_project_access(row[0], current_user)

    async with factory() as session:
        await session.execute(
            text(
                "UPDATE insights SET status = :status, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"status": body.status, "id": str(insight_id)},
        )
        await session.commit()

    return {"id": str(insight_id), "status": body.status}
