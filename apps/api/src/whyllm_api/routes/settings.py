"""Settings routes — API keys, budgets, alerts.

API Keys:
  GET    /v1/projects/:id/api-keys
  POST   /v1/projects/:id/api-keys
  DELETE /v1/projects/:id/api-keys/:key_id

Budgets:
  GET    /v1/projects/:id/budgets
  POST   /v1/projects/:id/budgets
  DELETE /v1/projects/:id/budgets/:budget_id

Alerts:
  GET    /v1/projects/:id/alerts
  POST   /v1/projects/:id/alerts
  PATCH  /v1/projects/:id/alerts/:alert_id
  DELETE /v1/projects/:id/alerts/:alert_id
  POST   /v1/projects/:id/alerts/:alert_id/test
"""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text

from whyllm_api.database import get_session_factory
from whyllm_api.models.user import User
from whyllm_api.routes.spans import _check_project_access
from whyllm_api.schemas.settings import (
    AlertCreate,
    AlertResponse,
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    BudgetCreate,
    BudgetResponse,
)
from whyllm_api.services.auth_service import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])


def _generate_api_key(environment: str) -> tuple[str, str, str]:
    """Return (raw_key, key_hash, key_prefix). raw_key is NEVER stored."""
    import bcrypt as _bcrypt

    env_short = {"production": "prod", "staging": "stg", "development": "dev"}.get(
        environment, "prod"
    )
    token = secrets.token_urlsafe(24)
    raw_key = f"wl-{env_short}_{token}"
    key_prefix = raw_key[:12]
    key_hash = _bcrypt.hashpw(raw_key.encode(), _bcrypt.gensalt()).decode()
    return raw_key, key_hash, key_prefix


# ── API Keys ───────────────────────────────────────────────────────────────────

@router.get("/v1/projects/{project_id}/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> list[ApiKeyResponse]:
    await _check_project_access(project_id, current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT id, project_id, name, key_prefix, is_active,
                       created_at, last_used_at, expires_at
                FROM api_keys
                WHERE project_id = :project_id
                ORDER BY created_at DESC
            """),
            {"project_id": str(project_id)},
        )
        rows = result.fetchall()

    return [
        ApiKeyResponse(
            id=r[0], project_id=r[1], name=r[2], key_prefix=r[3],
            environment=_env_from_prefix(r[3]), is_active=r[4],
            created_at=r[5], last_used_at=r[6], expires_at=r[7],
        )
        for r in rows
    ]


def _env_from_prefix(prefix: str) -> str:
    if "-prod_" in prefix:
        return "production"
    if "-stg_" in prefix:
        return "staging"
    return "development"


@router.post("/v1/projects/{project_id}/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    project_id: uuid.UUID,
    body: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreatedResponse:
    await _check_project_access(project_id, current_user)

    raw_key, key_hash, key_prefix = _generate_api_key(body.environment)
    key_id = uuid.uuid4()

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO api_keys (id, project_id, name, key_hash, key_prefix, expires_at)
                VALUES (:id, :project_id, :name, :key_hash, :key_prefix, :expires_at)
            """),
            {
                "id": str(key_id),
                "project_id": str(project_id),
                "name": body.name,
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "expires_at": body.expires_at,
            },
        )
        await session.commit()

    return ApiKeyCreatedResponse(
        id=key_id,
        project_id=project_id,
        name=body.name,
        key_prefix=key_prefix,
        environment=body.environment,
        is_active=True,
        created_at=__import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc),
        last_used_at=None,
        expires_at=body.expires_at,
        raw_key=raw_key,
    )


@router.delete("/v1/projects/{project_id}/api-keys/{key_id}", status_code=204, response_class=Response)
async def delete_api_key(
    project_id: uuid.UUID,
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> Response:
    await _check_project_access(project_id, current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("DELETE FROM api_keys WHERE id = :id AND project_id = :project_id"),
            {"id": str(key_id), "project_id": str(project_id)},
        )
        await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": "api_key_not_found"})
    return Response(status_code=204)


# ── Budgets ────────────────────────────────────────────────────────────────────

@router.get("/v1/projects/{project_id}/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> list[BudgetResponse]:
    await _check_project_access(project_id, current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT id, project_id, scope, scope_value, amount_usd,
                       period, action, is_active, created_at
                FROM cost_budgets
                WHERE project_id = :project_id
                ORDER BY created_at DESC
            """),
            {"project_id": str(project_id)},
        )
        rows = result.fetchall()

    return [
        BudgetResponse(
            id=r[0], project_id=r[1], scope=r[2], scope_value=r[3],
            amount_usd=r[4], period=r[5], action=r[6],
            is_active=r[7], created_at=r[8],
        )
        for r in rows
    ]


@router.post("/v1/projects/{project_id}/budgets", response_model=BudgetResponse, status_code=201)
async def create_budget(
    project_id: uuid.UUID,
    body: BudgetCreate,
    current_user: User = Depends(get_current_user),
) -> BudgetResponse:
    await _check_project_access(project_id, current_user)

    budget_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO cost_budgets
                    (id, project_id, scope, scope_value, amount_usd, period, action)
                VALUES
                    (:id, :project_id, :scope, :scope_value, :amount_usd, :period, :action)
            """),
            {
                "id": str(budget_id),
                "project_id": str(project_id),
                "scope": body.scope,
                "scope_value": body.scope_value,
                "amount_usd": float(body.amount_usd),
                "period": body.period,
                "action": body.action,
            },
        )
        await session.commit()

    import datetime as _dt
    return BudgetResponse(
        id=budget_id, project_id=project_id, scope=body.scope,
        scope_value=body.scope_value, amount_usd=body.amount_usd,
        period=body.period, action=body.action, is_active=True,
        created_at=_dt.datetime.now(tz=_dt.timezone.utc),
    )


@router.delete("/v1/projects/{project_id}/budgets/{budget_id}", status_code=204, response_class=Response)
async def delete_budget(
    project_id: uuid.UUID,
    budget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> Response:
    await _check_project_access(project_id, current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("DELETE FROM cost_budgets WHERE id = :id AND project_id = :project_id"),
            {"id": str(budget_id), "project_id": str(project_id)},
        )
        await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": "budget_not_found"})
    return Response(status_code=204)


# ── Alerts ─────────────────────────────────────────────────────────────────────

@router.get("/v1/projects/{project_id}/alerts", response_model=list[AlertResponse])
async def list_alerts(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> list[AlertResponse]:
    await _check_project_access(project_id, current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT id, project_id, name, metric, condition, threshold,
                       window_minutes, channels, is_active,
                       last_triggered_at, created_at
                FROM alerts
                WHERE project_id = :project_id
                ORDER BY created_at DESC
            """),
            {"project_id": str(project_id)},
        )
        rows = result.fetchall()

    return [
        AlertResponse(
            id=r[0], project_id=r[1], name=r[2], metric=r[3],
            condition=r[4], threshold=r[5], window_minutes=r[6],
            channels=r[7] or [], is_active=r[8],
            last_triggered_at=r[9], created_at=r[10],
        )
        for r in rows
    ]


@router.post("/v1/projects/{project_id}/alerts", response_model=AlertResponse, status_code=201)
async def create_alert(
    project_id: uuid.UUID,
    body: AlertCreate,
    current_user: User = Depends(get_current_user),
) -> AlertResponse:
    await _check_project_access(project_id, current_user)

    alert_id = uuid.uuid4()
    import json as _json
    channels_json = _json.dumps([c.model_dump() for c in body.channels])

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO alerts
                    (id, project_id, name, metric, condition, threshold,
                     window_minutes, channels)
                VALUES
                    (:id, :project_id, :name, :metric, :condition, :threshold,
                     :window_minutes, CAST(:channels AS jsonb))
            """),
            {
                "id": str(alert_id),
                "project_id": str(project_id),
                "name": body.name,
                "metric": body.metric,
                "condition": body.condition,
                "threshold": float(body.threshold),
                "window_minutes": body.window_minutes,
                "channels": channels_json,
            },
        )
        await session.commit()

    import datetime as _dt
    return AlertResponse(
        id=alert_id, project_id=project_id, name=body.name,
        metric=body.metric, condition=body.condition,
        threshold=body.threshold, window_minutes=body.window_minutes,
        channels=[c.model_dump() for c in body.channels],
        is_active=True, last_triggered_at=None,
        created_at=_dt.datetime.now(tz=_dt.timezone.utc),
    )


@router.patch("/v1/projects/{project_id}/alerts/{alert_id}", response_model=AlertResponse)
async def toggle_alert(
    project_id: uuid.UUID,
    alert_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
) -> AlertResponse:
    """Toggle is_active on an alert. Body: {"is_active": bool}"""
    await _check_project_access(project_id, current_user)

    is_active = body.get("is_active")
    if not isinstance(is_active, bool):
        raise HTTPException(status_code=400, detail={"error": "is_active_required"})

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                UPDATE alerts SET is_active = :is_active
                WHERE id = :id AND project_id = :project_id
                RETURNING id, project_id, name, metric, condition, threshold,
                          window_minutes, channels, is_active,
                          last_triggered_at, created_at
            """),
            {"is_active": is_active, "id": str(alert_id), "project_id": str(project_id)},
        )
        row = result.fetchone()
        await session.commit()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "alert_not_found"})

    return AlertResponse(
        id=row[0], project_id=row[1], name=row[2], metric=row[3],
        condition=row[4], threshold=row[5], window_minutes=row[6],
        channels=row[7] or [], is_active=row[8],
        last_triggered_at=row[9], created_at=row[10],
    )


@router.delete("/v1/projects/{project_id}/alerts/{alert_id}", status_code=204, response_class=Response)
async def delete_alert(
    project_id: uuid.UUID,
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> Response:
    await _check_project_access(project_id, current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("DELETE FROM alerts WHERE id = :id AND project_id = :project_id"),
            {"id": str(alert_id), "project_id": str(project_id)},
        )
        await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": "alert_not_found"})
    return Response(status_code=204)


@router.post("/v1/projects/{project_id}/alerts/{alert_id}/test", status_code=204, response_class=Response)
async def test_alert(
    project_id: uuid.UUID,
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Send a test notification to all channels configured on the alert."""
    await _check_project_access(project_id, current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT channels FROM alerts WHERE id = :id AND project_id = :project_id"),
            {"id": str(alert_id), "project_id": str(project_id)},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "alert_not_found"})

    channels = row[0] or []
    for channel in channels:
        _fire_test_notification(channel)

    return Response(status_code=204)


def _fire_test_notification(channel: dict) -> None:
    """Best-effort test ping — logs failures, never raises."""
    try:
        import httpx as _httpx
        ch_type = channel.get("type")
        target = channel.get("target", "")
        if ch_type == "webhook":
            _httpx.post(target, json={"type": "test", "message": "whyllm alert test"}, timeout=5.0)
        elif ch_type == "slack":
            _httpx.post(target, json={"text": "whyllm alert test ping"}, timeout=5.0)
        # email: would use SMTP/SendGrid — skip in dev
    except Exception as exc:
        log.warning("Test notification failed for channel %s: %s", channel, exc)
