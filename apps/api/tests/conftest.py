"""Session-wide test configuration.

Sets DATABASE_URL and REDIS_URL so that pydantic-settings does not fall back
to port 5432 (which is a different PostgreSQL container).

Provides a session-scoped event_loop so that:
  - All async fixtures (engine, test_ids, client, redis_client) share ONE loop.
  - All async test functions run in the same loop.
  - asyncpg connections created during lifespan are reusable across tests.

Must run before any module imports whyllm_api so that the lru_cache on
get_settings() captures the right values.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

import pytest

# ── Ensure src/ is on sys.path for all test modules ──────────────────────────
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ── Override env vars before any app module is imported ──────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://whyllm:whyllm@localhost:5433/whyllm")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-min-32-chars-long!!")
os.environ.setdefault("ENVIRONMENT", "development")

# ── Isolate the suite onto a dedicated Redis logical DB ──────────────────────
# `make test-api` runs after `make up`, so a live `worker` container is BRPOP-ing
# `ingest_queue` on db 0. If the suite shared that DB, the worker would drain
# spans the ingest tests enqueue before they could assert on the queue. Force
# the suite onto db 15 — the app-under-test, the redis_client fixture and the
# in-process worker tests all read REDIS_URL, so they stay mutually consistent
# while staying invisible to the real worker.
_redis_url = os.environ["REDIS_URL"]
if re.search(r"/\d+$", _redis_url):
    os.environ["REDIS_URL"] = re.sub(r"/\d+$", "/15", _redis_url)
else:
    os.environ["REDIS_URL"] = _redis_url.rstrip("/") + "/15"

# Bust the lru_cache on get_settings if it was already called
try:
    from whyllm_api.config import get_settings
    get_settings.cache_clear()
except Exception:
    pass


# ── Session-scoped event loop ─────────────────────────────────────────────────
# pytest-asyncio >= 0.21 deprecated the event_loop fixture override, but it
# still works and is the only reliable way to share one loop across ALL async
# tests AND fixtures in a session (required for asyncpg connection pools).
@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ── Module-scoped singleton reset ─────────────────────────────────────────────
# DB and Redis singletons are module-level globals. When test_health.py
# initialises them (via the app's /ready endpoint), they get bound to whatever
# loop was active at that point. The module fixture below tears them down after
# each test module so they are recreated fresh in the next module — preventing
# "Future attached to a different loop" errors when test ordering varies.
@pytest.fixture(scope="module", autouse=True)
async def reset_singletons_after_module():
    """Yield to let the module run, then dispose DB/Redis singletons."""
    yield
    # Teardown — runs after the last test in this module
    try:
        from whyllm_api.database import close_engine
        await close_engine()
    except Exception:
        pass
    try:
        from whyllm_api.redis_client import close_redis
        await close_redis()
    except Exception:
        pass
