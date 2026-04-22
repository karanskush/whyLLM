"""Spans API endpoint tests.

Tests cover:
  - GET  /v1/projects/:id/spans     — list, cursor pagination, all filters, auth
  - GET  /v1/spans/:span_id         — detail, sibling spans, project access
  - POST /v1/spans/:span_id/feedback — valid feedback, invalid feedback, auth

All tests run against the real DB (integration). The fixture registers a user,
creates an org/project, and seeds spans directly via SQL so test state is
deterministic and isolated.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://whyllm:whyllm@localhost:5433/whyllm",
)


# ── Shared fixture ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def spans_client():
    """ASGI test client; CostEngine seeded from static JSON (no DB needed)."""
    from whyllm_api.main import create_app
    from whyllm_api.services.cost import CostEngine

    app = create_app()
    ce = CostEngine()
    ce._seed_from_json()
    app.state.cost_engine = ce

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers():
    """Create a test user via psycopg2 (sync) and return Bearer headers.

    Using psycopg2 avoids making an HTTP request in a module-scoped async fixture
    which would create the global SQLAlchemy engine in the fixture's event loop
    instead of the test's loop, causing 'Future attached to different loop' errors.
    """
    import psycopg2
    from whyllm_api.services.auth_service import create_access_token, hash_password

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    email = f"spans-{uuid.uuid4().hex[:8]}@example.com"
    slug = f"spans-org-{org_id.hex[:8]}"

    dsn = _TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO organizations (id, name, slug) VALUES (%s, %s, %s)",
            (str(org_id), "Spans Test Org", slug),
        )
        cur.execute(
            "INSERT INTO users (id, email, hashed_password, name) VALUES (%s, %s, %s, %s)",
            (str(user_id), email, hash_password("securepassword123"), "Spans Tester"),
        )
        cur.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (%s, %s, 'owner')",
            (str(org_id), str(user_id)),
        )
    conn.commit()
    conn.close()

    token = create_access_token(user_id, org_id, email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def project_id(auth_headers):
    """Create a project using psycopg2 (sync) to avoid event-loop conflicts."""
    import psycopg2
    from whyllm_api.services.auth_service import decode_token

    token = auth_headers["Authorization"].split(" ")[1]
    org_id = decode_token(token)["org_id"]

    pid = uuid.uuid4()
    slug = f"test-project-{pid.hex[:8]}"

    # Use sync psycopg2 so we don't touch the SQLAlchemy async engine/pool in fixtures
    dsn = _TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, org_id, name, slug, created_at) VALUES (%s, %s, 'Test Project', %s, NOW())",
            (str(pid), org_id, slug),
        )
    conn.commit()
    conn.close()
    return pid


@pytest.fixture(scope="module")
def seeded_spans(project_id, auth_headers):
    """Insert 5 deterministic spans using sync psycopg2 to avoid event-loop conflicts."""
    import psycopg2
    from whyllm_api.services.auth_service import decode_token

    token = auth_headers["Authorization"].split(" ")[1]
    org_id = decode_token(token)["org_id"]

    dsn = _TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")

    # Use current month so the partitioned spans table has a matching partition.
    now = datetime.now(tz=timezone.utc)

    def _ts(offset_minutes: int) -> datetime:
        from datetime import timedelta
        return now.replace(second=0, microsecond=0) - timedelta(minutes=offset_minutes)

    trace_id = uuid.uuid4()
    spans = [
        {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "org_id": org_id,
            "trace_id": str(trace_id),
            "provider": "openai",
            "model": "gpt-4o",
            "status": "success",
            "kind": "llm",
            "environment": "development",
            "source": "sdk",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": "0.001500",
            "latency_ms": 800,
            "hallucination_score": "0.10",
            "created_at": _ts(40),
            "started_at": _ts(40),
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "org_id": org_id,
            "trace_id": str(trace_id),
            "provider": "openai",
            "model": "gpt-4o-mini",
            "status": "success",
            "kind": "llm",
            "environment": "development",
            "source": "sdk",
            "input_tokens": 50,
            "output_tokens": 20,
            "cost_usd": "0.000300",
            "latency_ms": 400,
            "hallucination_score": "0.05",
            "created_at": _ts(30),
            "started_at": _ts(30),
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "org_id": org_id,
            "trace_id": None,
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "status": "error",
            "kind": "llm",
            "environment": "production",
            "source": "proxy",
            "input_tokens": 200,
            "output_tokens": 0,
            "cost_usd": "0.000600",
            "latency_ms": 200,
            "hallucination_score": None,
            "created_at": _ts(20),
            "started_at": _ts(20),
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "org_id": org_id,
            "trace_id": None,
            "provider": "openai",
            "model": "gpt-4o",
            "status": "success",
            "kind": "llm",
            "environment": "production",
            "source": "sdk",
            "input_tokens": 300,
            "output_tokens": 150,
            "cost_usd": "0.004500",
            "latency_ms": 1200,
            "hallucination_score": "0.45",  # above 0.3 threshold
            "created_at": _ts(10),
            "started_at": _ts(10),
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "org_id": org_id,
            "trace_id": None,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "status": "success",
            "kind": "llm",
            "environment": "development",
            "source": "sdk",
            "input_tokens": 80,
            "output_tokens": 40,
            "cost_usd": "0.000600",
            "latency_ms": 600,
            "hallucination_score": "0.25",
            "created_at": _ts(5),
            "started_at": _ts(5),
        },
    ]

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    with conn.cursor() as cur:
        for s in spans:
            cur.execute(
                """
                INSERT INTO spans (
                    id, project_id, org_id, trace_id, provider, model, status, kind,
                    environment, source, input_tokens, output_tokens,
                    cost_usd, latency_ms, hallucination_score,
                    created_at, started_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (id, created_at) DO NOTHING
                """,
                (
                    s["id"], s["project_id"], s["org_id"], s["trace_id"],
                    s["provider"], s["model"], s["status"], s["kind"],
                    s["environment"], s["source"], s["input_tokens"], s["output_tokens"],
                    s["cost_usd"], s["latency_ms"], s["hallucination_score"],
                    s["created_at"], s["started_at"],
                ),
            )
    conn.commit()
    conn.close()

    return spans, trace_id


# ── Cursor helpers ─────────────────────────────────────────────────────────────

def _make_cursor(ts: str, span_id: str) -> str:
    payload = json.dumps({"ts": ts, "id": span_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


# ── TestListSpans ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestListSpans:
    """GET /v1/projects/{project_id}/spans"""

    async def test_returns_spans_for_project(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "has_more" in data
        assert "total_hint" in data
        assert len(data["items"]) >= 5

    async def test_response_shape(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(f"/v1/projects/{project_id}/spans", headers=auth_headers)
        item = r.json()["items"][0]
        assert "id" in item
        assert "model" in item
        assert "provider" in item
        assert "status" in item
        assert "cost_usd" in item
        assert "latency_ms" in item

    async def test_filter_by_model(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"model": "gpt-4o"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(i["model"] == "gpt-4o" for i in items)
        assert len(items) >= 2

    async def test_filter_by_provider(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"provider": "anthropic"},
            headers=auth_headers,
        )
        items = r.json()["items"]
        assert all(i["provider"] == "anthropic" for i in items)
        assert len(items) >= 1

    async def test_filter_by_status(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"status": "error"},
            headers=auth_headers,
        )
        items = r.json()["items"]
        assert all(i["status"] == "error" for i in items)
        assert len(items) >= 1

    async def test_filter_by_environment(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"environment": "production"},
            headers=auth_headers,
        )
        items = r.json()["items"]
        assert all(i["environment"] == "production" for i in items)
        assert len(items) >= 2

    async def test_filter_has_hallucination_true(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"has_hallucination": "true"},
            headers=auth_headers,
        )
        items = r.json()["items"]
        assert len(items) >= 1
        # hallucination_score > 0.3 for all returned items
        for item in items:
            if item["hallucination_score"] is not None:
                assert float(item["hallucination_score"]) > 0.3

    async def test_filter_has_hallucination_false(self, spans_client, auth_headers, project_id, seeded_spans):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"has_hallucination": "false"},
            headers=auth_headers,
        )
        items = r.json()["items"]
        assert len(items) >= 1
        for item in items:
            if item["hallucination_score"] is not None:
                assert float(item["hallucination_score"]) <= 0.3

    async def test_cursor_pagination(self, spans_client, auth_headers, project_id, seeded_spans):
        # Fetch first page with limit=2
        r1 = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"limit": 2},
            headers=auth_headers,
        )
        assert r1.status_code == 200
        data1 = r1.json()
        assert len(data1["items"]) == 2
        assert data1["has_more"] is True
        assert data1["next_cursor"] is not None

        # Fetch second page
        r2 = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"limit": 2, "cursor": data1["next_cursor"]},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        # No overlap between pages
        ids1 = {i["id"] for i in data1["items"]}
        ids2 = {i["id"] for i in data2["items"]}
        assert ids1.isdisjoint(ids2)

    async def test_invalid_cursor_returns_400(self, spans_client, auth_headers, project_id):
        r = await spans_client.get(
            f"/v1/projects/{project_id}/spans",
            params={"cursor": "not_valid_base64!!"},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "invalid_cursor"

    async def test_requires_auth(self, spans_client, project_id):
        r = await spans_client.get(f"/v1/projects/{project_id}/spans")
        assert r.status_code == 401

    async def test_wrong_project_returns_403(self, spans_client, auth_headers):
        fake_project = uuid.uuid4()
        # Register another user who owns this project
        r = await spans_client.get(
            f"/v1/projects/{fake_project}/spans",
            headers=auth_headers,
        )
        # Either 403 (exists, no access) or 404 (project doesn't exist)
        assert r.status_code in (403, 404)


# ── TestSpanDetail ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSpanDetail:
    """GET /v1/spans/{span_id}"""

    async def test_returns_span_detail(self, spans_client, auth_headers, seeded_spans):
        spans, trace_id = seeded_spans
        span_id = spans[0]["id"]

        r = await spans_client.get(f"/v1/spans/{span_id}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == span_id
        assert data["model"] == "gpt-4o"
        assert data["provider"] == "openai"

    async def test_detail_includes_siblings(self, spans_client, auth_headers, seeded_spans):
        """Span 0 and span 1 share a trace_id — they should be each other's siblings."""
        spans, trace_id = seeded_spans
        span_id = spans[0]["id"]

        r = await spans_client.get(f"/v1/spans/{span_id}", headers=auth_headers)
        data = r.json()
        assert "siblings" in data
        sibling_ids = {s["id"] for s in data["siblings"]}
        # span[1] has the same trace_id and should appear
        assert spans[1]["id"] in sibling_ids
        # span itself should NOT be in siblings
        assert span_id not in sibling_ids

    async def test_detail_response_shape(self, spans_client, auth_headers, seeded_spans):
        spans, _ = seeded_spans
        r = await spans_client.get(f"/v1/spans/{spans[0]['id']}", headers=auth_headers)
        data = r.json()
        for field in ("id", "model", "provider", "status", "tags",
                      "hallucination_score", "siblings", "created_at"):
            assert field in data

    async def test_no_siblings_when_no_trace(self, spans_client, auth_headers, seeded_spans):
        """Span 2 has no trace_id — siblings list must be empty."""
        spans, _ = seeded_spans
        span_id = spans[2]["id"]  # trace_id = None

        r = await spans_client.get(f"/v1/spans/{span_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["siblings"] == []

    async def test_unknown_span_returns_404(self, spans_client, auth_headers):
        fake_id = uuid.uuid4()
        r = await spans_client.get(f"/v1/spans/{fake_id}", headers=auth_headers)
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "span_not_found"

    async def test_requires_auth(self, spans_client, seeded_spans):
        spans, _ = seeded_spans
        r = await spans_client.get(f"/v1/spans/{spans[0]['id']}")
        assert r.status_code == 401


# ── TestSpanFeedback ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSpanFeedback:
    """POST /v1/spans/{span_id}/feedback"""

    async def test_positive_feedback_returns_204(self, spans_client, auth_headers, seeded_spans):
        spans, _ = seeded_spans
        r = await spans_client.post(
            f"/v1/spans/{spans[0]['id']}/feedback",
            json={"feedback": "positive"},
            headers=auth_headers,
        )
        assert r.status_code == 204

    async def test_negative_feedback_returns_204(self, spans_client, auth_headers, seeded_spans):
        spans, _ = seeded_spans
        r = await spans_client.post(
            f"/v1/spans/{spans[1]['id']}/feedback",
            json={"feedback": "negative"},
            headers=auth_headers,
        )
        assert r.status_code == 204

    async def test_flagged_feedback_returns_204(self, spans_client, auth_headers, seeded_spans):
        spans, _ = seeded_spans
        r = await spans_client.post(
            f"/v1/spans/{spans[2]['id']}/feedback",
            json={"feedback": "flagged", "note": "This response was totally wrong"},
            headers=auth_headers,
        )
        assert r.status_code == 204

    async def test_invalid_feedback_returns_400(self, spans_client, auth_headers, seeded_spans):
        spans, _ = seeded_spans
        r = await spans_client.post(
            f"/v1/spans/{spans[0]['id']}/feedback",
            json={"feedback": "thumbsup"},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "invalid_feedback"

    async def test_unknown_span_returns_404(self, spans_client, auth_headers):
        r = await spans_client.post(
            f"/v1/spans/{uuid.uuid4()}/feedback",
            json={"feedback": "positive"},
            headers=auth_headers,
        )
        assert r.status_code == 404

    async def test_requires_auth(self, spans_client, seeded_spans):
        spans, _ = seeded_spans
        r = await spans_client.post(
            f"/v1/spans/{spans[0]['id']}/feedback",
            json={"feedback": "positive"},
        )
        assert r.status_code == 401


# ── TestCursorHelpers ──────────────────────────────────────────────────────────

class TestCursorHelpers:
    """Unit tests for encode_cursor / decode_cursor."""

    def test_roundtrip(self):
        from whyllm_api.schemas.spans import decode_cursor, encode_cursor

        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        span_id = uuid.uuid4()
        cursor = encode_cursor(ts, span_id)
        decoded_ts, decoded_id = decode_cursor(cursor)
        assert decoded_ts == ts
        assert decoded_id == span_id

    def test_invalid_cursor_raises_value_error(self):
        from whyllm_api.schemas.spans import decode_cursor

        with pytest.raises(ValueError):
            decode_cursor("aaaabbbbcccc")

    def test_missing_ts_field_raises(self):
        from whyllm_api.schemas.spans import decode_cursor

        payload = json.dumps({"id": str(uuid.uuid4())})
        cursor = base64.urlsafe_b64encode(payload.encode()).decode()
        with pytest.raises(ValueError):
            decode_cursor(cursor)

    def test_missing_id_field_raises(self):
        from whyllm_api.schemas.spans import decode_cursor

        payload = json.dumps({"ts": "2024-06-01T12:00:00+00:00"})
        cursor = base64.urlsafe_b64encode(payload.encode()).decode()
        with pytest.raises(ValueError):
            decode_cursor(cursor)
