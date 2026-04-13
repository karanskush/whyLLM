"""Ingest pipeline integration tests.

Covers:
  - API key authentication (valid / invalid / missing / expired)
  - POST /v1/ingest/span — happy path, cost estimation, queue verification
  - POST /v1/ingest/batch — multi-span, partial success
  - Rate limiting (Redis INCR window)
  - Idempotency (X-Idempotency-Key header + body field)
  - Schema validation (provider normalisation, tags limit, payload truncation,
    timing auto-compute, status enum)
  - CostEngine unit tests (estimate, unknown model, refresh)

All tests run against the live Docker stack (localhost:5433 + localhost:6379).
A real org/project/api_key row is created in a session-scoped fixture and
torn down after all tests complete.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt as _bcrypt_lib
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# ── App + DB ──────────────────────────────────────────────────────────────────

import os

from llmdawg_api.main import create_app

_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://llmdawg:llmdawg@localhost:5433/llmdawg",
)
_TEST_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncEngine:
    eng = create_async_engine(_TEST_DB_URL, poolclass=NullPool, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def test_ids(engine: AsyncEngine):
    """Create a minimal org/project/api_key for the whole test session.

    Returns a dict with keys: org_id, project_id, key_id, raw_key, key_prefix.
    Cleans up after all tests finish.
    """
    org_id = uuid.uuid4()
    project_id = uuid.uuid4()
    key_id = uuid.uuid4()
    raw_key = "ld-test_" + uuid.uuid4().hex[:24]  # 32-char key
    key_prefix = raw_key[:12]
    key_hash = _bcrypt_lib.hashpw(raw_key.encode(), _bcrypt_lib.gensalt()).decode()

    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"
        ), {"id": str(org_id), "name": "TestOrg", "slug": f"test-org-{org_id.hex[:8]}"})
        await conn.execute(text(
            "INSERT INTO projects (id, org_id, name, slug) VALUES (:id, :org_id, :name, :slug)"
        ), {"id": str(project_id), "org_id": str(org_id), "name": "TestProject", "slug": f"test-proj-{project_id.hex[:8]}"})
        await conn.execute(text(
            "INSERT INTO api_keys (id, project_id, name, key_hash, key_prefix, is_active) "
            "VALUES (:id, :project_id, :name, :key_hash, :key_prefix, TRUE)"
        ), {
            "id": str(key_id),
            "project_id": str(project_id),
            "name": "TestKey",
            "key_hash": key_hash,
            "key_prefix": key_prefix,
        })

    yield {
        "org_id": org_id,
        "project_id": project_id,
        "key_id": key_id,
        "raw_key": raw_key,
        "key_prefix": key_prefix,
    }

    # Teardown — delete in reverse FK order
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM api_keys WHERE id = :id"), {"id": str(key_id)})
        await conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": str(project_id)})
        await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": str(org_id)})


@pytest_asyncio.fixture(scope="session")
async def client(test_ids):
    """Session-scoped ASGI test client wrapping the full FastAPI app.

    Key constraint: session-scoped async fixtures run in a DIFFERENT event
    loop from the tests (pytest-asyncio 0.24.0 behaviour). Any asyncpg
    connections created here would be bound to the fixture's loop and fail
    when tests try to use them.

    Workaround: only perform file I/O (no network) in the fixture. We seed
    the CostEngine from prices.json so cost estimates work. The DB engine is
    created lazily on the first HTTP request (in the test's event loop).
    httpx ASGITransport does NOT trigger the ASGI lifespan — we set app.state
    manually instead.
    """
    from llmdawg_api.services.cost import CostEngine

    app = create_app()

    # Seed CostEngine from file — no DB/Redis connections here
    cost_engine = CostEngine()
    cost_engine._seed_from_json()
    app.state.cost_engine = cost_engine

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def redis_client():
    """Direct Redis connection for test assertions."""
    import redis.asyncio as aioredis
    r = aioredis.from_url(_TEST_REDIS_URL, decode_responses=True)
    yield r
    # Python 3.9 asyncio may raise on wait_closed() during session-loop teardown
    try:
        await r.aclose()
    except Exception:
        pass


# ── Helper ────────────────────────────────────────────────────────────────────

def _auth(raw_key: str) -> dict[str, str]:
    return {"X-LLMDawg-Key": raw_key}


def _span_body(**overrides: Any) -> dict[str, Any]:
    base = {
        "provider": "openai",
        "model": "gpt-4o",
        "status": "success",
        "input_tokens": 100,
        "output_tokens": 50,
    }
    base.update(overrides)
    return base


# ── API key authentication ────────────────────────────────────────────────────

class TestApiKeyAuth:
    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/ingest/span", json=_span_body())
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_invalid_key_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers={"X-LLMDawg-Key": "ld-fake_totally_not_a_real_key_abc"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_valid_key_authenticates(self, client: AsyncClient, test_ids: dict) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_expired_key_returns_401(
        self, client: AsyncClient, engine: AsyncEngine, test_ids: dict
    ) -> None:
        """A key with expires_at in the past must be rejected."""
        expired_key_id = uuid.uuid4()
        raw_key = "ld-exp0_" + uuid.uuid4().hex[:24]
        key_hash = _bcrypt_lib.hashpw(raw_key.encode(), _bcrypt_lib.gensalt()).decode()
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)

        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO api_keys (id, project_id, name, key_hash, key_prefix, is_active, expires_at) "
                "VALUES (:id, :project_id, :name, :key_hash, :key_prefix, TRUE, :expires_at)"
            ), {
                "id": str(expired_key_id),
                "project_id": str(test_ids["project_id"]),
                "name": "ExpiredKey",
                "key_hash": key_hash,
                "key_prefix": raw_key[:12],
                "expires_at": past,
            })

        try:
            resp = await client.post(
                "/v1/ingest/span",
                json=_span_body(),
                headers={"X-LLMDawg-Key": raw_key},
            )
            assert resp.status_code == 401
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM api_keys WHERE id = :id"), {"id": str(expired_key_id)})

    @pytest.mark.asyncio
    async def test_inactive_key_returns_401(
        self, client: AsyncClient, engine: AsyncEngine, test_ids: dict
    ) -> None:
        inactive_key_id = uuid.uuid4()
        raw_key = "ld-inac_" + uuid.uuid4().hex[:24]
        key_hash = _bcrypt_lib.hashpw(raw_key.encode(), _bcrypt_lib.gensalt()).decode()

        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO api_keys (id, project_id, name, key_hash, key_prefix, is_active) "
                "VALUES (:id, :project_id, :name, :key_hash, :key_prefix, FALSE)"
            ), {
                "id": str(inactive_key_id),
                "project_id": str(test_ids["project_id"]),
                "name": "InactiveKey",
                "key_hash": key_hash,
                "key_prefix": raw_key[:12],
            })

        try:
            resp = await client.post(
                "/v1/ingest/span",
                json=_span_body(),
                headers={"X-LLMDawg-Key": raw_key},
            )
            assert resp.status_code == 401
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM api_keys WHERE id = :id"), {"id": str(inactive_key_id)})

    @pytest.mark.asyncio
    async def test_redis_cache_is_warmed_on_second_request(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        """After a DB hit, the key should be cached in Redis."""
        raw_key = test_ids["raw_key"]
        # Clear the cache for this key first
        cache_key = "apikey:" + hashlib.sha256(raw_key.encode()).hexdigest()[:32]
        await redis_client.delete(cache_key)

        # First request — DB hit
        r1 = await client.post("/v1/ingest/span", json=_span_body(), headers=_auth(raw_key))
        assert r1.status_code == 200

        # Allow the fire-and-forget task to complete
        await asyncio.sleep(0.1)

        # Cache must now exist
        cached = await redis_client.get(cache_key)
        assert cached is not None, "Redis cache was not populated after DB hit"
        data = json.loads(cached)
        assert data["project_id"] == str(test_ids["project_id"])


# ── Single span ingest ────────────────────────────────────────────────────────

class TestIngestSpan:
    @pytest.mark.asyncio
    async def test_happy_path_returns_span_id(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "span_id" in body
        assert body["queued"] is True
        # cost_usd must be a float (gpt-4o has known pricing)
        assert isinstance(body["cost_usd"], float)
        assert body["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_span_is_queued_in_redis(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        """After a successful ingest, one item must be on the Redis queue."""
        # Drain queue first so we can count new items
        await redis_client.delete("ingest_queue")

        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        span_id = resp.json()["span_id"]

        queue_len = await redis_client.llen("ingest_queue")
        assert queue_len == 1, f"Expected 1 item in queue, got {queue_len}"

        # Verify the queued payload contains the right span_id
        raw = await redis_client.lindex("ingest_queue", 0)
        payload = json.loads(raw)
        assert payload["span_id"] == span_id
        assert payload["project_id"] == str(test_ids["project_id"])
        assert payload["org_id"] == str(test_ids["org_id"])
        assert payload["provider"] == "openai"
        assert payload["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_unknown_model_cost_is_null(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(provider="custom_llm", model="not-a-real-model"),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        assert resp.json()["cost_usd"] is None

    @pytest.mark.asyncio
    async def test_missing_tokens_cost_is_null(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json={"provider": "openai", "model": "gpt-4o", "status": "success"},
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        assert resp.json()["cost_usd"] is None

    @pytest.mark.asyncio
    async def test_error_span_accepted(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json={
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "status": "error",
                "error_type": "RateLimitError",
                "error_message": "Too many requests",
            },
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_latency_auto_computed_from_timestamps(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        await redis_client.delete("ingest_queue")
        started = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        ended = datetime(2026, 4, 10, 12, 0, 1, 500_000, tzinfo=timezone.utc)  # +1.5s
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(started_at=started.isoformat(), ended_at=ended.isoformat()),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        raw = await redis_client.lindex("ingest_queue", 0)
        payload = json.loads(raw)
        assert payload["latency_ms"] == 1500

    @pytest.mark.asyncio
    async def test_explicit_latency_not_overridden(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        await redis_client.delete("ingest_queue")
        started = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        ended = datetime(2026, 4, 10, 12, 0, 1, tzinfo=timezone.utc)  # +1s
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(
                started_at=started.isoformat(),
                ended_at=ended.isoformat(),
                latency_ms=999,  # explicit — should be kept
            ),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        raw = await redis_client.lindex("ingest_queue", 0)
        payload = json.loads(raw)
        assert payload["latency_ms"] == 999

    @pytest.mark.asyncio
    async def test_provider_lowercased(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        await redis_client.delete("ingest_queue")
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(provider="OpenAI"),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        raw = await redis_client.lindex("ingest_queue", 0)
        payload = json.loads(raw)
        assert payload["provider"] == "openai"


# ── Schema validation ─────────────────────────────────────────────────────────

class TestSchemaValidation:
    @pytest.mark.asyncio
    async def test_invalid_status_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(status="pending"),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ended_before_started_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(
                started_at="2026-04-10T12:00:01Z",
                ended_at="2026-04-10T12:00:00Z",
            ),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tags_over_20_keys_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        big_tags = {f"key_{i}": f"val_{i}" for i in range(21)}
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(tags=big_tags),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tags_exactly_20_keys_accepted(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        tags_20 = {f"key_{i}": f"val_{i}" for i in range(20)}
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(tags=tags_20),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_payload_over_50kb_truncated(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        await redis_client.delete("ingest_queue")
        big_request = {"data": "x" * 60_000}  # ~60 KB
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(request=big_request),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        # The queued payload should have the truncation sentinel
        raw = await redis_client.lindex("ingest_queue", 0)
        payload = json.loads(raw)
        assert payload["request"] is not None
        assert payload["request"].get("_truncated") is True

    @pytest.mark.asyncio
    async def test_negative_tokens_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(input_tokens=-1),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_fields_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json={"provider": "openai"},  # missing model and status
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_kind_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(kind="webhook"),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422


# ── Idempotency ───────────────────────────────────────────────────────────────

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_header_key_returns_same_span_id(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        idem_key = f"test-idem-{uuid.uuid4().hex}"
        # Clear any stale state
        await redis_client.delete(f"idem:{test_ids['project_id']}")

        r1 = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers={**_auth(test_ids["raw_key"]), "X-Idempotency-Key": idem_key},
        )
        assert r1.status_code == 200
        span_id_1 = r1.json()["span_id"]
        queued_1 = r1.json()["queued"]
        assert queued_1 is True

        # Allow fire-and-forget record to complete
        await asyncio.sleep(0.1)

        r2 = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers={**_auth(test_ids["raw_key"]), "X-Idempotency-Key": idem_key},
        )
        assert r2.status_code == 200
        span_id_2 = r2.json()["span_id"]
        assert span_id_1 == span_id_2, "Duplicate idempotency key must return the same span_id"
        assert r2.json()["queued"] is False

    @pytest.mark.asyncio
    async def test_different_idempotency_keys_get_different_span_ids(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        r1 = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers={**_auth(test_ids["raw_key"]), "X-Idempotency-Key": f"key-a-{uuid.uuid4().hex}"},
        )
        r2 = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers={**_auth(test_ids["raw_key"]), "X-Idempotency-Key": f"key-b-{uuid.uuid4().hex}"},
        )
        assert r1.json()["span_id"] != r2.json()["span_id"]

    @pytest.mark.asyncio
    async def test_body_idempotency_key_works(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        idem_key = f"body-idem-{uuid.uuid4().hex}"
        await redis_client.delete(f"idem:{test_ids['project_id']}")

        r1 = await client.post(
            "/v1/ingest/span",
            json=_span_body(idempotency_key=idem_key),
            headers=_auth(test_ids["raw_key"]),
        )
        assert r1.status_code == 200
        await asyncio.sleep(0.1)

        r2 = await client.post(
            "/v1/ingest/span",
            json=_span_body(idempotency_key=idem_key),
            headers=_auth(test_ids["raw_key"]),
        )
        assert r2.status_code == 200
        assert r1.json()["span_id"] == r2.json()["span_id"]


# ── Batch ingest ──────────────────────────────────────────────────────────────

class TestBatchIngest:
    @pytest.mark.asyncio
    async def test_batch_all_valid(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        await redis_client.delete("ingest_queue")
        spans = [_span_body(model="gpt-4o-mini") for _ in range(5)]
        resp = await client.post(
            "/v1/ingest/batch",
            json={"spans": spans},
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 5
        assert body["rejected"] == 0
        assert len(body["span_ids"]) == 5
        assert body["errors"] == []

        # Queue should contain 5 items
        queue_len = await redis_client.llen("ingest_queue")
        assert queue_len == 5

    @pytest.mark.asyncio
    async def test_batch_empty_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        resp = await client.post(
            "/v1/ingest/batch",
            json={"spans": []},
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_over_100_rejected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        spans = [_span_body() for _ in range(101)]
        resp = await client.post(
            "/v1/ingest/batch",
            json={"spans": spans},
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_missing_auth_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/v1/ingest/batch",
            json={"spans": [_span_body()]},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_batch_queue_payload_structure(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        await redis_client.delete("ingest_queue")
        resp = await client.post(
            "/v1/ingest/batch",
            json={"spans": [_span_body(user_id="user-abc", session_id="sess-xyz")]},
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        raw = await redis_client.lindex("ingest_queue", 0)
        payload = json.loads(raw)
        assert payload["user_id"] == "user-abc"
        assert payload["session_id"] == "sess-xyz"
        assert payload["project_id"] == str(test_ids["project_id"])
        assert payload["org_id"] == str(test_ids["org_id"])
        assert "ingested_at" in payload

    @pytest.mark.asyncio
    async def test_batch_mixed_providers(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        spans = [
            _span_body(provider="openai", model="gpt-4o"),
            _span_body(provider="Anthropic", model="claude-sonnet-4-6"),  # uppercase
            _span_body(provider="google", model="gemini-1.5-flash"),
        ]
        resp = await client.post(
            "/v1/ingest/batch",
            json={"spans": spans},
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 3


# ── Rate limiting ─────────────────────────────────────────────────────────────

class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_allows_normal_traffic(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        """10 sequential requests should all succeed."""
        for _ in range(10):
            resp = await client.post(
                "/v1/ingest/span",
                json=_span_body(),
                headers=_auth(test_ids["raw_key"]),
            )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(
        self, client: AsyncClient, test_ids: dict, redis_client
    ) -> None:
        """Manually set the counter above the limit and verify 429."""
        # Use a different project to avoid polluting other tests
        project_id = test_ids["project_id"]
        window = int(datetime.now(tz=timezone.utc).timestamp()) // 60
        rl_key = f"rl:{project_id}:{window}"

        # Set counter just above the limit
        await redis_client.set(rl_key, 1001, ex=61)

        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"]["error"] == "rate_limit_exceeded"
        assert "retry_after" in body["detail"]
        assert resp.headers.get("Retry-After") is not None

        # Clean up so subsequent tests aren't rate-limited
        await redis_client.delete(rl_key)


# ── CostEngine unit tests ─────────────────────────────────────────────────────

class TestCostEngine:
    @pytest.mark.asyncio
    async def test_estimate_known_model(self) -> None:
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()
        # Seed directly without DB
        engine._prices = {
            ("openai", "gpt-4o"): (
                Decimal("0.00250000"),   # per 1K input
                Decimal("0.01000000"),   # per 1K output
                Decimal("0.00125000"),   # per 1K cached
            )
        }
        engine._loaded = True

        cost = engine.estimate("openai", "gpt-4o", 1000, 500, 0)
        assert cost is not None
        # 1000 * 0.0025/1K + 500 * 0.01/1K = 0.0025 + 0.005 = 0.0075
        assert cost == Decimal("0.00750000")

    @pytest.mark.asyncio
    async def test_estimate_with_cached_tokens(self) -> None:
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()
        engine._prices = {
            ("openai", "gpt-4o"): (
                Decimal("0.00250000"),
                Decimal("0.01000000"),
                Decimal("0.00125000"),
            )
        }
        engine._loaded = True

        # 500 input + 200 cached + 100 output
        cost = engine.estimate("openai", "gpt-4o", 500, 100, 200)
        assert cost is not None
        expected = (
            Decimal("0.00250000") * 500 / 1000
            + Decimal("0.01000000") * 100 / 1000
            + Decimal("0.00125000") * 200 / 1000
        ).quantize(Decimal("0.00000001"))
        assert cost == expected

    @pytest.mark.asyncio
    async def test_estimate_unknown_model_returns_none(self) -> None:
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()
        engine._prices = {}
        engine._loaded = True

        cost = engine.estimate("custom", "my-model", 100, 50, 0)
        assert cost is None

    @pytest.mark.asyncio
    async def test_unknown_model_warning_logged_once(self) -> None:
        """Unknown model warning should only log once per unique (provider, model)."""
        import logging
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()
        engine._prices = {}
        engine._loaded = True

        with patch("llmdawg_api.services.cost.log") as mock_log:
            engine.estimate("x", "y", 10, 10, 0)
            engine.estimate("x", "y", 10, 10, 0)  # second call — should NOT log again
            engine.estimate("x", "y", 10, 10, 0)  # third call
            # Warning should appear only once
            warning_calls = [
                c for c in mock_log.warning.call_args_list
                if "unknown model" in str(c).lower()
            ]
            assert len(warning_calls) == 1

    @pytest.mark.asyncio
    async def test_model_count_property(self) -> None:
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()
        engine._prices = {
            ("openai", "gpt-4o"): (Decimal("0.0025"), Decimal("0.01"), Decimal("0.00125")),
            ("anthropic", "claude-sonnet-4-6"): (Decimal("0.003"), Decimal("0.015"), Decimal("0.0003")),
        }
        assert engine.model_count == 2

    @pytest.mark.asyncio
    async def test_seed_from_json_on_db_failure(self) -> None:
        """When DB is unavailable, _seed_from_json must load prices as fallback."""
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()

        # Call _seed_from_json directly — it reads from packages/cost-tables/prices.json
        engine._seed_from_json()
        assert engine.is_loaded, "prices.json seed should have loaded prices"
        assert engine.model_count > 0, f"Expected >0 pricing entries, got {engine.model_count}"
        # Spot-check that gpt-4o is in there
        cost = engine.estimate("openai", "gpt-4o", 1000, 500, 0)
        assert cost is not None
        assert cost > 0

    @pytest.mark.asyncio
    async def test_refresh_loop_cancels_cleanly(self) -> None:
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()
        engine._prices = {}
        engine._loaded = True

        # Start the loop (will sleep for 5 min — immediately cancel)
        task = asyncio.create_task(engine._refresh_loop())
        await asyncio.sleep(0)  # let event loop schedule the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # expected

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        """CostEngine.start() + stop() must not raise."""
        from llmdawg_api.services.cost import CostEngine

        engine = CostEngine()
        await engine.start()
        assert engine.is_loaded
        await engine.stop()


# ── Health check still works ──────────────────────────────────────────────────

class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_still_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_ready_still_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/ready")
        assert resp.status_code == 200


# ── Cost estimation accuracy via live endpoint ────────────────────────────────

class TestCostAccuracy:
    @pytest.mark.asyncio
    async def test_gpt4o_cost_matches_expected(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        """
        gpt-4o: $0.0025/$0.01 per 1K tokens
        100 input + 50 output = 0.00025 + 0.0005 = 0.00075 USD
        """
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(provider="openai", model="gpt-4o", input_tokens=100, output_tokens=50),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        cost = resp.json()["cost_usd"]
        assert cost is not None
        assert abs(cost - 0.00075) < 1e-7, f"Expected ~0.00075, got {cost}"

    @pytest.mark.asyncio
    async def test_claude_sonnet_cost(
        self, client: AsyncClient, test_ids: dict
    ) -> None:
        """
        claude-sonnet-4-6: $0.003/$0.015 per 1K tokens
        200 input + 100 output = 0.0006 + 0.0015 = 0.0021 USD
        """
        resp = await client.post(
            "/v1/ingest/span",
            json=_span_body(
                provider="anthropic",
                model="claude-sonnet-4-6",
                input_tokens=200,
                output_tokens=100,
            ),
            headers=_auth(test_ids["raw_key"]),
        )
        assert resp.status_code == 200
        cost = resp.json()["cost_usd"]
        assert cost is not None
        assert abs(cost - 0.0021) < 1e-7, f"Expected ~0.0021, got {cost}"
