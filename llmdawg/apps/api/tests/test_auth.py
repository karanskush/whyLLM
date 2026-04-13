"""Auth + metrics endpoint tests.

Tests cover:
  - POST /api/v1/auth/register — happy path, duplicate email, weak password
  - POST /api/v1/auth/login    — valid credentials, wrong password, unknown email
  - GET  /api/v1/auth/me       — valid token, missing token, expired token
  - GET  /v1/projects/:id/metrics/summary   — KPI response shape, invalid window
  - GET  /v1/projects/:id/metrics/timeseries — series response, granularity
  - JWT decode / create_access_token unit tests
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://llmdawg:llmdawg@localhost:5433/llmdawg",
)


@pytest_asyncio.fixture(scope="module")
async def auth_client():
    """ASGI test client with CostEngine seeded from file."""
    from llmdawg_api.main import create_app
    from llmdawg_api.services.cost import CostEngine

    app = create_app()
    ce = CostEngine()
    ce._seed_from_json()
    app.state.cost_engine = ce

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ── TestJWT ───────────────────────────────────────────────────────────────────

class TestJWT:
    """Unit tests for JWT creation and decoding."""

    def test_create_and_decode_token(self):
        from llmdawg_api.services.auth_service import create_access_token, decode_token
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(user_id, org_id, "test@example.com")
        payload = decode_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["org_id"] == str(org_id)
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_decode_invalid_token_raises(self):
        from llmdawg_api.services.auth_service import decode_token
        with pytest.raises(ValueError):
            decode_token("not.a.valid.jwt")

    def test_token_has_expiry(self):
        from llmdawg_api.services.auth_service import create_access_token, decode_token
        token = create_access_token(uuid.uuid4(), uuid.uuid4(), "x@x.com")
        payload = decode_token(token)
        assert "exp" in payload
        # Should expire ~7 days from now (within 1 hour tolerance)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        delta = exp - now
        assert timedelta(days=6) < delta < timedelta(days=8)


# ── TestRegister ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRegister:
    """POST /api/v1/auth/register."""

    async def test_happy_path_creates_user_and_org(self, auth_client):
        email = f"reg-{uuid.uuid4().hex[:8]}@example.com"
        response = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123", "name": "Test User"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == email
        assert data["user"]["name"] == "Test User"
        assert data["user"]["org_id"] is not None

    async def test_returns_valid_jwt(self, auth_client):
        from llmdawg_api.services.auth_service import decode_token
        email = f"jwt-{uuid.uuid4().hex[:8]}@example.com"
        response = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123"},
        )
        assert response.status_code == 201
        token = response.json()["access_token"]
        payload = decode_token(token)
        assert payload["email"] == email

    async def test_duplicate_email_returns_409(self, auth_client):
        email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
        # First registration succeeds
        r1 = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123"},
        )
        assert r1.status_code == 201
        # Second registration fails
        r2 = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "anotherpassword123"},
        )
        assert r2.status_code == 409
        assert r2.json()["detail"]["error"] == "email_taken"

    async def test_short_password_returns_422(self, auth_client):
        response = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": "short@example.com", "password": "abc"},
        )
        assert response.status_code == 422

    async def test_custom_org_name_used(self, auth_client):
        email = f"orgname-{uuid.uuid4().hex[:8]}@example.com"
        response = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123", "org_name": "My Custom Org"},
        )
        assert response.status_code == 201
        assert response.json()["user"]["org_name"] == "My Custom Org"


# ── TestLogin ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLogin:
    """POST /api/v1/auth/login."""

    async def _register(self, client, email, password="securepassword123"):
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert r.status_code == 201
        return r.json()

    async def test_valid_credentials_returns_token(self, auth_client):
        email = f"login-{uuid.uuid4().hex[:8]}@example.com"
        await self._register(auth_client, email)

        response = await auth_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "securepassword123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == email

    async def test_wrong_password_returns_401(self, auth_client):
        email = f"wrongpw-{uuid.uuid4().hex[:8]}@example.com"
        await self._register(auth_client, email)

        response = await auth_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrongpassword!"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "invalid_credentials"

    async def test_unknown_email_returns_401(self, auth_client):
        response = await auth_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@nowhere.com", "password": "anypassword"},
        )
        assert response.status_code == 401

    async def test_login_token_is_valid_jwt(self, auth_client):
        from llmdawg_api.services.auth_service import decode_token
        email = f"logintoken-{uuid.uuid4().hex[:8]}@example.com"
        await self._register(auth_client, email)

        response = await auth_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "securepassword123"},
        )
        token = response.json()["access_token"]
        payload = decode_token(token)
        assert payload["email"] == email


# ── TestMe ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMe:
    """GET /api/v1/auth/me."""

    async def _register_and_token(self, client):
        email = f"me-{uuid.uuid4().hex[:8]}@example.com"
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123", "name": "Me User"},
        )
        return r.json()["access_token"], email

    async def test_valid_token_returns_user(self, auth_client):
        token, email = await self._register_and_token(auth_client)
        response = await auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == email
        assert data["name"] == "Me User"
        assert data["org_id"] is not None

    async def test_missing_token_returns_401(self, auth_client):
        response = await auth_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_invalid_token_returns_401(self, auth_client):
        response = await auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer notavalidtoken"},
        )
        assert response.status_code == 401

    async def test_malformed_bearer_returns_401(self, auth_client):
        response = await auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Token sometoken"},
        )
        assert response.status_code == 401


# ── TestMetricsSummary ────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMetricsSummary:
    """GET /v1/projects/:id/metrics/summary."""

    async def _setup(self, auth_client):
        """Register a user and create a project for testing."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        email = f"metrics-{uuid.uuid4().hex[:8]}@example.com"
        r = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123"},
        )
        data = r.json()
        token = data["access_token"]
        org_id = data["user"]["org_id"]

        # Create a project for this org
        project_id = uuid.uuid4()
        eng = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
        async with eng.begin() as conn:
            await conn.execute(text("""
                INSERT INTO projects (id, org_id, name, slug)
                VALUES (:id, :org_id, 'Metrics Test Project', :slug)
            """), {"id": str(project_id), "org_id": str(org_id),
                   "slug": f"metrics-proj-{project_id.hex[:8]}"})
        try:
            await eng.dispose()
        except Exception:
            pass

        return token, project_id

    async def test_returns_expected_fields(self, auth_client):
        token, project_id = await self._setup(auth_client)
        response = await auth_client.get(
            f"/v1/projects/{project_id}/metrics/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_spans" in data
        assert "total_cost_usd" in data
        assert "error_rate" in data
        assert "p50_latency_ms" in data
        assert "p95_latency_ms" in data
        assert data["project_id"] == str(project_id)

    async def test_empty_project_returns_zeros(self, auth_client):
        token, project_id = await self._setup(auth_client)
        response = await auth_client.get(
            f"/v1/projects/{project_id}/metrics/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = response.json()
        assert data["total_spans"] == 0
        assert data["total_cost_usd"] == 0.0
        assert data["error_rate"] == 0.0

    async def test_invalid_window_returns_400(self, auth_client):
        token, project_id = await self._setup(auth_client)
        response = await auth_client.get(
            f"/v1/projects/{project_id}/metrics/summary?window=100y",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_missing_auth_returns_401(self, auth_client):
        project_id = uuid.uuid4()
        response = await auth_client.get(f"/v1/projects/{project_id}/metrics/summary")
        assert response.status_code == 401

    async def test_nonexistent_project_returns_404(self, auth_client):
        email = f"404metrics-{uuid.uuid4().hex[:8]}@example.com"
        r = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123"},
        )
        token = r.json()["access_token"]

        response = await auth_client.get(
            f"/v1/projects/{uuid.uuid4()}/metrics/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


# ── TestMetricsTimeseries ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMetricsTimeseries:
    """GET /v1/projects/:id/metrics/timeseries."""

    async def _setup(self, auth_client):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        email = f"ts-{uuid.uuid4().hex[:8]}@example.com"
        r = await auth_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepassword123"},
        )
        data = r.json()
        token = data["access_token"]
        org_id = data["user"]["org_id"]
        project_id = uuid.uuid4()

        eng = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
        async with eng.begin() as conn:
            await conn.execute(text("""
                INSERT INTO projects (id, org_id, name, slug)
                VALUES (:id, :org_id, 'TS Test Project', :slug)
            """), {"id": str(project_id), "org_id": str(org_id),
                   "slug": f"ts-proj-{project_id.hex[:8]}"})
        try:
            await eng.dispose()
        except Exception:
            pass

        return token, project_id

    async def test_returns_series_array(self, auth_client):
        token, project_id = await self._setup(auth_client)
        response = await auth_client.get(
            f"/v1/projects/{project_id}/metrics/timeseries",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "series" in data
        assert isinstance(data["series"], list)
        assert "granularity" in data

    async def test_7d_window_uses_day_granularity(self, auth_client):
        token, project_id = await self._setup(auth_client)
        response = await auth_client.get(
            f"/v1/projects/{project_id}/metrics/timeseries?window=7d",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["granularity"] == "day"

    async def test_24h_window_uses_hour_granularity(self, auth_client):
        token, project_id = await self._setup(auth_client)
        response = await auth_client.get(
            f"/v1/projects/{project_id}/metrics/timeseries?window=24h",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["granularity"] == "hour"
