"""Metrics routes — summary, timeseries, and live SSE feed.

GET  /v1/projects/:id/metrics/summary     — KPI snapshot (24h default)
GET  /v1/projects/:id/metrics/timeseries  — hourly cost+count over a time window
GET  /v1/projects/:id/metrics/live        — SSE stream of real-time span events

All endpoints require Authorization: Bearer <jwt> and verify org membership.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from whyllm_api.database import get_session_factory
from whyllm_api.models.user import User
from whyllm_api.redis_client import get_redis
from whyllm_api.services.auth_service import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/projects", tags=["metrics"])

_VALID_WINDOWS = {"1h", "6h", "24h", "7d", "30d"}


def _window_to_delta(window: str) -> timedelta:
    mapping = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    return mapping.get(window, timedelta(hours=24))


async def _check_project_access(
    project_id: uuid.UUID,
    user: User,
) -> None:
    """Raise 403/404 if user is not a member of the project's org."""
    from sqlalchemy import select
    from whyllm_api.models.org_member import OrgMember
    from whyllm_api.models.project import Project

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Project.org_id)
            .where(Project.id == project_id)
        )
        row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    org_id = row[0]

    async with factory() as session:
        result = await session.execute(
            select(OrgMember.id)
            .where(OrgMember.org_id == org_id, OrgMember.user_id == user.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail={"error": "forbidden"})


@router.get("/{project_id}/metrics/summary")
async def metrics_summary(
    project_id: uuid.UUID,
    window: str = Query(default="24h"),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return KPI snapshot for the project over the given time window."""
    if window not in _VALID_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_window", "message": f"window must be one of {sorted(_VALID_WINDOWS)}"},
        )

    await _check_project_access(project_id, current_user)

    since = datetime.now(tz=timezone.utc) - _window_to_delta(window)
    factory = get_session_factory()

    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT
                    COUNT(*)                                                AS total_spans,
                    COALESCE(SUM(cost_usd), 0)                             AS total_cost_usd,
                    COUNT(*) FILTER (WHERE status = 'error')               AS error_count,
                    CASE WHEN COUNT(*) > 0
                         THEN COUNT(*) FILTER (WHERE status = 'error')::float / COUNT(*)
                         ELSE 0
                    END                                                    AS error_rate,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency,
                    AVG(hallucination_score)::numeric(6,4)                 AS avg_hallucination_score
                FROM spans
                WHERE project_id = :project_id
                  AND created_at >= :since
            """),
            {"project_id": str(project_id), "since": since},
        )
        row = result.fetchone()

    return {
        "project_id": str(project_id),
        "window": window,
        "since": since.isoformat(),
        "total_spans": int(row[0]) if row else 0,
        "total_cost_usd": float(row[1]) if row and row[1] else 0.0,
        "error_count": int(row[2]) if row else 0,
        "error_rate": float(row[3]) if row and row[3] else 0.0,
        "p50_latency_ms": float(row[4]) if row and row[4] else None,
        "p95_latency_ms": float(row[5]) if row and row[5] else None,
        "avg_hallucination_score": float(row[6]) if row and row[6] else None,
    }


@router.get("/{project_id}/metrics/timeseries")
async def metrics_timeseries(
    project_id: uuid.UUID,
    window: str = Query(default="24h"),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return hourly cost and span count time series."""
    if window not in _VALID_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_window", "message": f"window must be one of {sorted(_VALID_WINDOWS)}"},
        )

    await _check_project_access(project_id, current_user)

    since = datetime.now(tz=timezone.utc) - _window_to_delta(window)
    # Use hour buckets for short windows, day buckets for longer ones
    trunc = "hour" if window in {"1h", "6h", "24h"} else "day"
    factory = get_session_factory()

    async with factory() as session:
        result = await session.execute(
            text(f"""
                SELECT
                    DATE_TRUNC('{trunc}', created_at AT TIME ZONE 'UTC') AS bucket,
                    model,
                    COALESCE(SUM(cost_usd), 0)  AS cost_usd,
                    COUNT(*)                    AS span_count
                FROM spans
                WHERE project_id = :project_id
                  AND created_at >= :since
                GROUP BY bucket, model
                ORDER BY bucket ASC
            """),
            {"project_id": str(project_id), "since": since},
        )
        rows = result.fetchall()

    series = [
        {
            "bucket": row[0].isoformat() if row[0] else None,
            "model": row[1],
            "cost_usd": float(row[2]),
            "span_count": int(row[3]),
        }
        for row in rows
    ]

    return {
        "project_id": str(project_id),
        "window": window,
        "granularity": trunc,
        "series": series,
    }


@router.get("/{project_id}/metrics/live")
async def metrics_live(
    project_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE stream of real-time span events for the project.

    Clients should listen with EventSource. Each event is a JSON object
    with fields: span_id, model, status, cost_usd, latency_ms.

    A heartbeat comment (`: heartbeat`) is sent every ~15 messages to
    keep the connection alive through proxies and load balancers.
    """
    await _check_project_access(project_id, current_user)
    channel = f"project:{project_id}:spans"

    async def event_stream():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(channel)
        heartbeat_counter = 0
        try:
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message.get("type") == "message":
                    data = message.get("data", "")
                    yield f"data: {data}\n\n"
                    heartbeat_counter += 1
                    if heartbeat_counter % 15 == 0:
                        yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
