"""Health and readiness endpoints.

GET /health  — liveness probe: is the process running?
GET /ready   — readiness probe: can the process serve traffic?
             Checks DB connectivity (simple SELECT 1) and Redis (PING).
"""

import time
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from whyllm_api.config import get_settings
from whyllm_api.database import get_engine
from whyllm_api.redis_client import get_redis

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness check — always returns 200 if the process is running."""
    settings = get_settings()
    return {"status": "ok", "version": settings.api_version}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness check — returns 200 only when DB and Redis are reachable.

    Returns 503 (via raised exception) if either dependency is down.
    Kubernetes / Docker health checks should call this endpoint.
    """
    checks: dict[str, Any] = {}
    overall_ok = True

    # ---- Database check -------------------------------------------------------
    db_start = time.perf_counter()
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - db_start) * 1000, 2),
        }
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        overall_ok = False

    # ---- Redis check ----------------------------------------------------------
    redis_start = time.perf_counter()
    try:
        pong = await get_redis().ping()
        checks["redis"] = {
            "status": "ok" if pong else "error",
            "latency_ms": round((time.perf_counter() - redis_start) * 1000, 2),
        }
        if not pong:
            overall_ok = False
    except Exception as exc:
        checks["redis"] = {"status": "error", "detail": str(exc)}
        overall_ok = False

    payload: dict[str, Any] = {
        "status": "ok" if overall_ok else "degraded",
        "checks": checks,
    }

    if not overall_ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=payload)

    return payload
