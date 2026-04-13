"""Settings + cost endpoint tests.

Tests cover:
  - GET/POST/DELETE /v1/projects/:id/api-keys
  - GET/POST/DELETE /v1/projects/:id/budgets
  - GET/POST/PATCH/DELETE/test /v1/projects/:id/alerts
  - GET /v1/projects/:id/cost/breakdown
"""

from __future__ import annotations

import os
import uuid

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://llmdawg:llmdawg@localhost:5433/llmdawg",
)
_DSN = _TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")


@pytest_asyncio.fixture(scope="module")
async def settings_client():
    from llmdawg_api.main import create_app
    from llmdawg_api.services.cost import CostEngine

    app = create_app()
    ce = CostEngine()
    ce._seed_from_json()
    app.state.cost_engine = ce

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(scope="module")
def settings_auth(settings_client):
    """Create user + org + project via psycopg2, return (headers, project_id)."""
    from llmdawg_api.services.auth_service import create_access_token, hash_password

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    project_id = uuid.uuid4()
    email = f"settings-{uuid.uuid4().hex[:8]}@example.com"

    conn = psycopg2.connect(_DSN)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (str(org_id), "Settings Org", f"settings-org-{org_id.hex[:8]}"),
        )
        cur.execute(
            "INSERT INTO users (id, email, hashed_password, name) VALUES (%s, %s, %s, %s)",
            (str(user_id), email, hash_password("pass123"), "Settings User"),
        )
        cur.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (%s, %s, 'owner')",
            (str(org_id), str(user_id)),
        )
        cur.execute(
            "INSERT INTO projects (id, org_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(project_id), str(org_id), "Settings Project", f"settings-proj-{project_id.hex[:8]}"),
        )
    conn.commit()
    conn.close()

    token = create_access_token(user_id, org_id, email)
    headers = {"Authorization": f"Bearer {token}"}
    return headers, project_id


# ── TestApiKeys ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestApiKeys:
    """API key CRUD."""

    async def test_list_empty(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/api-keys", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_create_returns_raw_key(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/api-keys",
            json={"name": "Test Key", "environment": "production"},
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert "raw_key" in data
        assert data["raw_key"].startswith("ld-prod_")
        assert "key_prefix" in data
        assert data["key_prefix"] == data["raw_key"][:12]

    async def test_raw_key_not_in_list(self, settings_client, settings_auth):
        """After creation, listing must not expose the raw key."""
        headers, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/api-keys", headers=headers)
        assert r.status_code == 200
        for key in r.json():
            assert "raw_key" not in key

    async def test_create_dev_key(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/api-keys",
            json={"name": "Dev Key", "environment": "development"},
            headers=headers,
        )
        assert r.status_code == 201
        assert r.json()["raw_key"].startswith("ld-dev_")

    async def test_delete_key(self, settings_client, settings_auth):
        headers, pid = settings_auth
        # Create
        create = await settings_client.post(
            f"/v1/projects/{pid}/api-keys",
            json={"name": "To Delete", "environment": "staging"},
            headers=headers,
        )
        key_id = create.json()["id"]
        # Delete
        r = await settings_client.delete(
            f"/v1/projects/{pid}/api-keys/{key_id}", headers=headers
        )
        assert r.status_code == 204
        # Not in list
        keys = await settings_client.get(f"/v1/projects/{pid}/api-keys", headers=headers)
        assert all(k["id"] != key_id for k in keys.json())

    async def test_delete_unknown_key_returns_404(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.delete(
            f"/v1/projects/{pid}/api-keys/{uuid.uuid4()}", headers=headers
        )
        assert r.status_code == 404

    async def test_requires_auth(self, settings_client, settings_auth):
        _, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/api-keys")
        assert r.status_code == 401


# ── TestBudgets ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBudgets:
    """Budget CRUD."""

    async def test_list_empty(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/budgets", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_create_daily_budget(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/budgets",
            json={"amount_usd": "10.00", "period": "daily", "action": "alert"},
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert float(data["amount_usd"]) == 10.0
        assert data["period"] == "daily"
        assert data["action"] == "alert"
        assert data["is_active"] is True

    async def test_create_block_budget(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/budgets",
            json={"amount_usd": "50.00", "period": "monthly", "action": "block"},
            headers=headers,
        )
        assert r.status_code == 201
        assert r.json()["action"] == "block"

    async def test_budget_appears_in_list(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/budgets", headers=headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    async def test_delete_budget(self, settings_client, settings_auth):
        headers, pid = settings_auth
        create = await settings_client.post(
            f"/v1/projects/{pid}/budgets",
            json={"amount_usd": "5.00", "period": "weekly"},
            headers=headers,
        )
        budget_id = create.json()["id"]
        r = await settings_client.delete(
            f"/v1/projects/{pid}/budgets/{budget_id}", headers=headers
        )
        assert r.status_code == 204

    async def test_negative_amount_rejected(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/budgets",
            json={"amount_usd": "-1.00", "period": "daily"},
            headers=headers,
        )
        assert r.status_code == 422

    async def test_invalid_period_rejected(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/budgets",
            json={"amount_usd": "10.00", "period": "hourly"},
            headers=headers,
        )
        assert r.status_code == 422


# ── TestAlerts ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAlerts:
    """Alert CRUD + toggle + test fire."""

    async def test_list_empty(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/alerts", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_create_alert(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/alerts",
            json={
                "name": "High Cost",
                "metric": "cost_usd",
                "condition": "gt",
                "threshold": "10.00",
                "window_minutes": 60,
                "channels": [{"type": "webhook", "target": "https://example.com/hook"}],
            },
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "High Cost"
        assert data["metric"] == "cost_usd"
        assert data["condition"] == "gt"
        assert float(data["threshold"]) == 10.0
        assert len(data["channels"]) == 1
        assert data["is_active"] is True

    async def test_alert_in_list(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/alerts", headers=headers)
        assert len(r.json()) >= 1

    async def test_toggle_alert(self, settings_client, settings_auth):
        headers, pid = settings_auth
        create = await settings_client.post(
            f"/v1/projects/{pid}/alerts",
            json={
                "name": "Toggle Test",
                "metric": "error_rate",
                "condition": "gt",
                "threshold": "0.1",
            },
            headers=headers,
        )
        alert_id = create.json()["id"]
        r = await settings_client.patch(
            f"/v1/projects/{pid}/alerts/{alert_id}",
            json={"is_active": False},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    async def test_delete_alert(self, settings_client, settings_auth):
        headers, pid = settings_auth
        create = await settings_client.post(
            f"/v1/projects/{pid}/alerts",
            json={"name": "Delete Me", "metric": "latency_p95", "condition": "gt", "threshold": "5000"},
            headers=headers,
        )
        alert_id = create.json()["id"]
        r = await settings_client.delete(
            f"/v1/projects/{pid}/alerts/{alert_id}", headers=headers
        )
        assert r.status_code == 204

    async def test_test_alert_returns_204(self, settings_client, settings_auth):
        """test endpoint should return 204 even with no webhook channels (nothing to fire)."""
        headers, pid = settings_auth
        create = await settings_client.post(
            f"/v1/projects/{pid}/alerts",
            json={"name": "Fire Test", "metric": "cost_usd", "condition": "gt", "threshold": "100"},
            headers=headers,
        )
        alert_id = create.json()["id"]
        r = await settings_client.post(
            f"/v1/projects/{pid}/alerts/{alert_id}/test", headers=headers
        )
        assert r.status_code == 204

    async def test_invalid_metric_rejected(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.post(
            f"/v1/projects/{pid}/alerts",
            json={"name": "Bad", "metric": "cpu_usage", "condition": "gt", "threshold": "0.9"},
            headers=headers,
        )
        assert r.status_code == 422

    async def test_requires_auth(self, settings_client, settings_auth):
        _, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/alerts")
        assert r.status_code == 401


# ── TestCostBreakdown ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestCostBreakdown:
    """Cost breakdown endpoint."""

    async def test_returns_breakdown_shape(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(
            f"/v1/projects/{pid}/cost/breakdown?window=24h", headers=headers
        )
        assert r.status_code == 200
        data = r.json()
        assert "total_cost_usd" in data
        assert "items" in data
        assert "top_users" in data
        assert "since" in data
        assert data["window"] == "24h"

    async def test_empty_project_returns_zeros(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(
            f"/v1/projects/{pid}/cost/breakdown?window=1h", headers=headers
        )
        assert r.status_code == 200
        assert float(r.json()["total_cost_usd"]) == 0.0
        assert r.json()["items"] == []

    async def test_invalid_window_rejected(self, settings_client, settings_auth):
        headers, pid = settings_auth
        r = await settings_client.get(
            f"/v1/projects/{pid}/cost/breakdown?window=99d", headers=headers
        )
        assert r.status_code == 422

    async def test_requires_auth(self, settings_client, settings_auth):
        _, pid = settings_auth
        r = await settings_client.get(f"/v1/projects/{pid}/cost/breakdown")
        assert r.status_code == 401
