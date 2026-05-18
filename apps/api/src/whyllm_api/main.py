"""FastAPI application factory.

The lifespan context manager handles startup/shutdown of:
- SQLAlchemy async engine (connection pool warm-up)
- Redis async connection pool

All routes are registered via sub-routers to keep this file lean.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import orjson
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse


# ── Application logging ───────────────────────────────────────────────────────
# uvicorn configures only its own loggers (uvicorn, uvicorn.access, uvicorn.error)
# — application loggers inherit a root that has no handler, so log.info() calls
# from our code would vanish. Wire up whyllm_api.* with a stdout handler so
# `docker compose logs api` surfaces every hop of every request.
#
# Set WHYLLM_LOG_LEVEL=DEBUG to see DEBUG lines (span queued, cache hits).
# Set WHYLLM_LOG_SQL=1 to keep SQLAlchemy's per-statement echo on.

_APP_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s :: %(message)s"
_level_name = os.environ.get("WHYLLM_LOG_LEVEL", "INFO").upper()
_app_level = getattr(logging, _level_name, logging.INFO)

_root_app_logger = logging.getLogger("whyllm_api")
if not _root_app_logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(_APP_LOG_FORMAT))
    _root_app_logger.addHandler(_h)
_root_app_logger.setLevel(_app_level)
_root_app_logger.propagate = False

# Quiet SQLAlchemy's per-statement INFO chatter by default — it drowns out
# the proxy/auth/upstream/span lines the operator actually wants to see.
# Flip WHYLLM_LOG_SQL=1 to restore it for SQL debugging.
if os.environ.get("WHYLLM_LOG_SQL", "").lower() not in ("1", "true", "yes"):
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

from whyllm_api.config import get_settings
from whyllm_api.database import close_engine, get_engine
from whyllm_api.health import router as health_router
from whyllm_api.proxy.client import close_proxy_client, init_proxy_client
from whyllm_api.redis_client import close_redis, get_redis
from whyllm_api.routes.ingest import router as ingest_router
from whyllm_api.routes.auth import router as auth_router
from whyllm_api.routes.metrics import router as metrics_router
from whyllm_api.routes.spans import router as spans_router
from whyllm_api.routes.cost import router as cost_router
from whyllm_api.routes.insights import router as insights_router
from whyllm_api.routes.proxy import router as proxy_router
from whyllm_api.routes.admin import router as admin_router
from whyllm_api.routes.projects import router as projects_router
from whyllm_api.routes.settings import router as settings_router
from whyllm_api.services.cost import CostEngine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — runs once on startup, once on shutdown.

    Startup:
      - Pre-connect the DB pool so the first real request is not slow.
      - Verify Redis is reachable and log the result.
      - Load model pricing into the CostEngine and start the refresh loop.

    Shutdown:
      - Stop the CostEngine background task.
      - Drain and dispose the DB connection pool.
      - Close the Redis connection pool gracefully.
    """
    settings = get_settings()

    # ---- Startup --------------------------------------------------------------
    # Warm up DB pool: acquire + immediately release one connection.
    try:
        async with get_engine().connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        print(f"[startup] DB pool ready — {settings.database_url.split('@')[-1]}")
    except Exception as exc:
        # Don't crash on startup — /ready will surface the problem
        print(f"[startup] WARNING: DB pool warm-up failed: {exc}")

    # Verify Redis
    try:
        await get_redis().ping()
        print(f"[startup] Redis ready — {settings.redis_url}")
    except Exception as exc:
        print(f"[startup] WARNING: Redis ping failed: {exc}")

    # Initialize shared httpx proxy client pool
    await init_proxy_client()
    print("[startup] Proxy client pool initialized")

    # Start CostEngine — loads pricing from DB and begins 5-min refresh loop
    cost_engine = CostEngine()
    await cost_engine.start()
    app.state.cost_engine = cost_engine
    print(f"[startup] CostEngine ready — {cost_engine.model_count} pricing entries")

    print(f"[startup] whyllm API v{settings.api_version} — {settings.environment}")

    # Re-assert SQL log level after the engine is created (echo=True would
    # otherwise have reset sqlalchemy.engine to INFO during lazy init).
    if os.environ.get("WHYLLM_LOG_SQL", "").lower() not in ("1", "true", "yes"):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

    yield  # ← application runs here

    # ---- Shutdown -------------------------------------------------------------
    await cost_engine.stop()
    await close_proxy_client()
    await close_engine()
    await close_redis()
    print("[shutdown] Connections closed.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="whyllm API",
        description="Production observability platform for LLM calls.",
        version=settings.api_version,
        # Use orjson for ~2× faster JSON serialization
        default_response_class=ORJSONResponse,
        # Disable auto-generated docs in production (enable behind auth later)
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    # ---- CORS -----------------------------------------------------------------
    # Origins come from CORS_ORIGINS env var (comma-separated).
    # Defaults to localhost in dev; set to https://whyllm.vercel.app in prod.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # ---- Routers --------------------------------------------------------------
    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(auth_router)
    app.include_router(metrics_router)
    app.include_router(proxy_router)
    app.include_router(spans_router)
    app.include_router(cost_router)
    app.include_router(insights_router)
    app.include_router(admin_router)
    app.include_router(projects_router)
    app.include_router(settings_router)

    return app


# Module-level app instance used by uvicorn
app = create_app()
