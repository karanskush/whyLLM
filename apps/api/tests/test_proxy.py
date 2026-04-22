"""Proxy route tests — OpenAI and Anthropic forwarding.

Uses a mocked httpx client (not respx) to avoid transport patching issues with
the long-lived proxy client singleton. Each test replaces get_proxy_client()
with a mock that returns preconfigured httpx.Response objects.

Test classes:
  TestProxyOpenAI        — non-streaming, headers, 4xx passthrough, budget, auth, enqueue
  TestProxyAnthropic     — mirrors OpenAI (different auth header + token field names)
  TestBudgetGate         — below budget passes, at/over budget blocked, Redis failure
  TestHeaderStripping    — whyllm and hop-by-hop headers not forwarded
  TestProxyUtils         — unit tests for SSE parsers and enqueue_proxy_span
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt as _bcrypt_lib
import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Fixtures ─────────────────────��────────────────────────────────────────────

_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://whyllm:whyllm@localhost:5433/whyllm",
)

_OPENAI_KEY = "sk-test-openai-key"
_ANTHROPIC_KEY = "sk-ant-test-key"


@pytest_asyncio.fixture(scope="module")
async def proxy_db_ids():
    """Create a real org/project/api_key for proxy tests."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    eng = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    org_id = uuid.uuid4()
    project_id = uuid.uuid4()
    key_id = uuid.uuid4()
    raw_key = "ld-test_" + uuid.uuid4().hex[:24]
    key_prefix = raw_key[:12]
    key_hash = _bcrypt_lib.hashpw(raw_key.encode(), _bcrypt_lib.gensalt()).decode()

    async with eng.begin() as conn:
        await conn.execute(text(
            "INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"
        ), {"id": str(org_id), "name": "ProxyTestOrg", "slug": f"proxy-org-{org_id.hex[:8]}"})
        await conn.execute(text(
            "INSERT INTO projects (id, org_id, name, slug) VALUES (:id, :org_id, :name, :slug)"
        ), {"id": str(project_id), "org_id": str(org_id), "name": "ProxyTestProject",
            "slug": f"proxy-proj-{project_id.hex[:8]}"})
        await conn.execute(text(
            "INSERT INTO api_keys (id, project_id, name, key_hash, key_prefix, is_active) "
            "VALUES (:id, :project_id, :name, :key_hash, :key_prefix, TRUE)"
        ), {"id": str(key_id), "project_id": str(project_id), "name": "ProxyTestKey",
            "key_hash": key_hash, "key_prefix": key_prefix})

    yield {"org_id": org_id, "project_id": project_id, "key_id": key_id,
           "raw_key": raw_key, "key_prefix": key_prefix}

    async with eng.begin() as conn:
        await conn.execute(text("DELETE FROM api_keys WHERE id = :id"), {"id": str(key_id)})
        await conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": str(project_id)})
        await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": str(org_id)})
    try:
        await eng.dispose()
    except Exception:
        pass


@pytest_asyncio.fixture(scope="module")
async def proxy_client(proxy_db_ids):
    """Module-scoped ASGI test client."""
    from whyllm_api.main import create_app
    from whyllm_api.services.cost import CostEngine

    app = create_app()
    cost_engine = CostEngine()
    cost_engine._seed_from_json()
    app.state.cost_engine = cost_engine

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ── Mock helpers ──────────────────────��──────────────────────────────���────────

def _mock_redis_no_budget():
    """Redis mock: no budget spend → budget gate passes immediately."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.lpush = AsyncMock(return_value=1)
    return r


def _mock_proxy_client_for(response: httpx.Response) -> MagicMock:
    """Return a mock httpx client that returns `response` on any request()."""
    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=response)
    return mock_client


def _openai_chat_response(model="gpt-4o", content="Hello!") -> dict:
    return {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _anthropic_chat_response(model="claude-3-5-sonnet-20241022", content="Hello!") -> dict:
    return {
        "id": "msg_abc123",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": content}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _openai_stream_chunks(content="Hi", model="gpt-4o") -> list[bytes]:
    return [
        f'data: {{"id":"cmp1","object":"chat.completion.chunk","model":"{model}",'
        f'"choices":[{{"index":0,"delta":{{"role":"assistant","content":""}},"finish_reason":null}}]}}\n\n'.encode(),
        f'data: {{"id":"cmp1","object":"chat.completion.chunk","model":"{model}",'
        f'"choices":[{{"index":0,"delta":{{"content":"{content}"}},"finish_reason":null}}]}}\n\n'.encode(),
        f'data: {{"id":"cmp1","object":"chat.completion.chunk","model":"{model}",'
        f'"choices":[{{"index":0,"delta":{{}},"finish_reason":"stop"}}],'
        f'"usage":{{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}}}\n\n'.encode(),
        b"data: [DONE]\n\n",
    ]


def _anthropic_stream_chunks(content="Hi", model="claude-3-5-sonnet-20241022") -> list[bytes]:
    return [
        f'event: message_start\ndata: {{"type":"message_start","message":{{"id":"msg1","type":"message","role":"assistant","model":"{model}","content":[],"stop_reason":null,"usage":{{"input_tokens":10,"output_tokens":0}}}}}}\n\n'.encode(),
        f'event: content_block_delta\ndata: {{"type":"content_block_delta","index":0,"delta":{{"type":"text_delta","text":"{content}"}}}}\n\n'.encode(),
        b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":5}}\n\n',
        b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
    ]


# ── TestProxyOpenAI ──────────────────────────────────��────────────────────────

@pytest.mark.asyncio
class TestProxyOpenAI:
    """OpenAI proxy: forwarding, auth, headers, errors, budget."""

    async def test_non_streaming_forward(self, proxy_client, proxy_db_ids):
        """Happy path: POST forwards to OpenAI and returns response."""
        raw_key = proxy_db_ids["raw_key"]
        upstream_resp = httpx.Response(200, json=_openai_chat_response())
        mock_client = _mock_proxy_client_for(upstream_resp)

        with patch("whyllm_api.routes.proxy_openai.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=_mock_redis_no_budget()):

            response = await proxy_client.post(
                "/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "Authorization": f"Bearer {_OPENAI_KEY}"},
            )

        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "Hello!"

    async def test_upstream_401_passed_through(self, proxy_client, proxy_db_ids):
        """Upstream 4xx responses are returned to client unchanged."""
        raw_key = proxy_db_ids["raw_key"]
        upstream_resp = httpx.Response(401, json={"error": {"message": "Invalid API key"}})
        mock_client = _mock_proxy_client_for(upstream_resp)

        with patch("whyllm_api.routes.proxy_openai.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=_mock_redis_no_budget()):

            response = await proxy_client.post(
                "/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "Authorization": f"Bearer {_OPENAI_KEY}"},
            )

        assert response.status_code == 401

    async def test_missing_whyllm_key_returns_401(self, proxy_client):
        """Missing X-whyllm-Key header returns 401 before forwarding."""
        response = await proxy_client.post(
            "/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401

    async def test_missing_authorization_returns_401(self, proxy_client, proxy_db_ids):
        """Missing Authorization header returns 401 — user must pass their own OpenAI key."""
        raw_key = proxy_db_ids["raw_key"]

        response = await proxy_client.post(
            "/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-whyllm-Key": raw_key},
        )

        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "missing_api_key"

    async def test_span_enqueued_after_success(self, proxy_client, proxy_db_ids):
        """Successful proxy response enqueues a span with correct fields."""
        raw_key = proxy_db_ids["raw_key"]
        upstream_resp = httpx.Response(200, json=_openai_chat_response())
        mock_client = _mock_proxy_client_for(upstream_resp)

        enqueued: list[bytes] = []
        r = _mock_redis_no_budget()

        async def capture_lpush(queue, payload):
            enqueued.append(payload)
            return 1

        r.lpush = capture_lpush

        with patch("whyllm_api.routes.proxy_openai.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=r):

            response = await proxy_client.post(
                "/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "Authorization": f"Bearer {_OPENAI_KEY}"},
            )
            # Sleep inside patch context so background task sees the mock
            await asyncio.sleep(0.1)

        assert response.status_code == 200
        assert len(enqueued) >= 1
        span = json.loads(enqueued[0])
        assert span["provider"] == "openai"
        assert span["status"] == "success"
        assert span["source"] == "proxy"
        assert span["input_tokens"] == 10
        assert span["output_tokens"] == 5

    async def test_whyllm_headers_not_forwarded(self, proxy_client, proxy_db_ids):
        """X-whyllm-* headers must not reach the upstream provider."""
        raw_key = proxy_db_ids["raw_key"]
        captured_headers: dict[str, str] = {}

        async def capture_request(method, url, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return httpx.Response(200, json=_openai_chat_response())

        mock_client = MagicMock()
        mock_client.request = capture_request

        with patch("whyllm_api.routes.proxy_openai.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=_mock_redis_no_budget()):

            await proxy_client.post(
                "/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                headers={
                    "X-whyllm-Key": raw_key,
                    "X-whyllm-Custom": "should-be-stripped",
                    "Authorization": f"Bearer {_OPENAI_KEY}",
                },
            )

        lower_keys = {k.lower() for k in captured_headers}
        assert "x-whyllm-key" not in lower_keys
        assert "x-whyllm-custom" not in lower_keys
        # User's own key passes through unchanged (headers may be lowercased in transit)
        auth = captured_headers.get("Authorization") or captured_headers.get("authorization")
        assert auth == f"Bearer {_OPENAI_KEY}"

    async def test_budget_gate_blocks_over_limit(self, proxy_client, proxy_db_ids):
        """Request is blocked with 429 when project is over budget."""
        raw_key = proxy_db_ids["raw_key"]

        r = AsyncMock()
        r.get = AsyncMock(return_value="10.00")  # $10 spent

        session = AsyncMock()
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value=5.0)  # $5 limit
        result = MagicMock()
        result.fetchone = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        with patch("whyllm_api.proxy.utils.get_redis", return_value=r), \
             patch("whyllm_api.proxy.utils.get_session_factory",
                   return_value=MagicMock(return_value=session)):

            response = await proxy_client.post(
                "/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "Authorization": f"Bearer {_OPENAI_KEY}"},
            )

        assert response.status_code == 429
        assert response.json()["detail"]["error"] == "budget_exceeded"

    async def test_get_request_forwarded(self, proxy_client, proxy_db_ids):
        """GET requests (e.g. /models) are also forwarded."""
        raw_key = proxy_db_ids["raw_key"]
        upstream_resp = httpx.Response(200, json={"object": "list", "data": []})
        mock_client = _mock_proxy_client_for(upstream_resp)

        with patch("whyllm_api.routes.proxy_openai.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=_mock_redis_no_budget()):

            response = await proxy_client.get(
                "/openai/v1/models",
                headers={"X-whyllm-Key": raw_key, "Authorization": f"Bearer {_OPENAI_KEY}"},
            )

        assert response.status_code == 200


# ── TestProxyAnthropic ────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestProxyAnthropic:
    """Anthropic proxy: auth header, token fields, forwarding."""

    async def test_non_streaming_forward(self, proxy_client, proxy_db_ids):
        """POST /anthropic/v1/messages returns Anthropic response."""
        raw_key = proxy_db_ids["raw_key"]
        upstream_resp = httpx.Response(200, json=_anthropic_chat_response())
        mock_client = _mock_proxy_client_for(upstream_resp)

        with patch("whyllm_api.routes.proxy_anthropic.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=_mock_redis_no_budget()):

            response = await proxy_client.post(
                "/anthropic/v1/messages",
                json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "x-api-key": _ANTHROPIC_KEY},
            )

        assert response.status_code == 200
        assert response.json()["content"][0]["text"] == "Hello!"

    async def test_anthropic_auth_header_passthrough(self, proxy_client, proxy_db_ids):
        """User's x-api-key passes through unchanged; anthropic-version is set."""
        raw_key = proxy_db_ids["raw_key"]
        captured_headers: dict[str, str] = {}

        async def capture_request(method, url, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return httpx.Response(200, json=_anthropic_chat_response())

        mock_client = MagicMock()
        mock_client.request = capture_request

        with patch("whyllm_api.routes.proxy_anthropic.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=_mock_redis_no_budget()):

            await proxy_client.post(
                "/anthropic/v1/messages",
                json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "x-api-key": _ANTHROPIC_KEY},
            )

        lower_keys = {k.lower() for k in captured_headers}
        # User's key passes through
        assert "x-api-key" in lower_keys
        assert captured_headers.get("x-api-key") == _ANTHROPIC_KEY
        assert "anthropic-version" in lower_keys
        # whyllm key must be stripped
        assert "x-whyllm-key" not in lower_keys

    async def test_upstream_4xx_passed_through(self, proxy_client, proxy_db_ids):
        """Anthropic 4xx responses are passed through unchanged."""
        raw_key = proxy_db_ids["raw_key"]
        upstream_resp = httpx.Response(
            400, json={"type": "error", "error": {"type": "invalid_request_error"}}
        )
        mock_client = _mock_proxy_client_for(upstream_resp)

        with patch("whyllm_api.routes.proxy_anthropic.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=_mock_redis_no_budget()):

            response = await proxy_client.post(
                "/anthropic/v1/messages",
                json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "x-api-key": _ANTHROPIC_KEY},
            )

        assert response.status_code == 400

    async def test_missing_xapikey_returns_401(self, proxy_client, proxy_db_ids):
        """401 when x-api-key header is missing — user must pass their own Anthropic key."""
        raw_key = proxy_db_ids["raw_key"]

        response = await proxy_client.post(
            "/anthropic/v1/messages",
            json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 100,
                  "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-whyllm-Key": raw_key},
        )

        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "missing_api_key"

    async def test_span_uses_input_output_tokens(self, proxy_client, proxy_db_ids):
        """Anthropic span uses input_tokens/output_tokens (not prompt/completion)."""
        raw_key = proxy_db_ids["raw_key"]
        upstream_resp = httpx.Response(200, json=_anthropic_chat_response())
        mock_client = _mock_proxy_client_for(upstream_resp)

        enqueued: list[bytes] = []
        r = _mock_redis_no_budget()

        async def capture_lpush(queue, payload):
            enqueued.append(payload)
            return 1

        r.lpush = capture_lpush

        with patch("whyllm_api.routes.proxy_anthropic.get_proxy_client", return_value=mock_client), \
             patch("whyllm_api.proxy.utils.get_redis", return_value=r):

            await proxy_client.post(
                "/anthropic/v1/messages",
                json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-whyllm-Key": raw_key, "x-api-key": _ANTHROPIC_KEY},
            )
            # Sleep inside patch context so background task sees the mock
            await asyncio.sleep(0.1)

        assert len(enqueued) >= 1
        span = json.loads(enqueued[0])
        assert span["provider"] == "anthropic"
        assert span["input_tokens"] == 10
        assert span["output_tokens"] == 5
        assert span["source"] == "proxy"


# ── TestBudgetGate ──────────────────────────────────────────────────────────���─

@pytest.mark.asyncio
class TestBudgetGate:
    """Budget gate unit tests."""

    async def test_no_spend_in_redis_passes(self):
        """No spend in Redis → budget gate passes without DB query."""
        from whyllm_api.proxy.utils import check_budget

        with patch("whyllm_api.proxy.utils.get_redis") as mock_redis:
            r = AsyncMock()
            r.get = AsyncMock(return_value=None)
            mock_redis.return_value = r
            await check_budget(uuid.uuid4())  # Should not raise

    async def test_spend_below_limit_passes(self):
        """$3 spent with $10 limit: passes without 429."""
        from whyllm_api.proxy.utils import check_budget

        session = AsyncMock()
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value=10.0)
        result = MagicMock()
        result.fetchone = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        with patch("whyllm_api.proxy.utils.get_redis") as mock_redis, \
             patch("whyllm_api.proxy.utils.get_session_factory",
                   return_value=MagicMock(return_value=session)):
            r = AsyncMock()
            r.get = AsyncMock(return_value="3.00")
            mock_redis.return_value = r
            await check_budget(uuid.uuid4())  # Should not raise

    async def test_spend_over_limit_raises_429(self):
        """$10 spent with $5 limit: raises HTTP 429."""
        from whyllm_api.proxy.utils import check_budget
        from fastapi import HTTPException

        session = AsyncMock()
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value=5.0)
        result = MagicMock()
        result.fetchone = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        with patch("whyllm_api.proxy.utils.get_redis") as mock_redis, \
             patch("whyllm_api.proxy.utils.get_session_factory",
                   return_value=MagicMock(return_value=session)):
            r = AsyncMock()
            r.get = AsyncMock(return_value="10.00")
            mock_redis.return_value = r

            with pytest.raises(HTTPException) as exc_info:
                await check_budget(uuid.uuid4())

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["error"] == "budget_exceeded"

    async def test_redis_failure_is_nonfatal(self):
        """Budget gate silently passes if Redis raises."""
        from whyllm_api.proxy.utils import check_budget

        with patch("whyllm_api.proxy.utils.get_redis") as mock_redis:
            r = AsyncMock()
            r.get = AsyncMock(side_effect=ConnectionError("Redis down"))
            mock_redis.return_value = r
            await check_budget(uuid.uuid4())  # Should not raise


# ── TestHeaderStripping ────────────────────���────────────────────────────────��─

class TestHeaderStripping:
    """Unit tests for strip_proxy_headers."""

    def test_strips_whyllm_prefixed_headers(self):
        from whyllm_api.proxy.utils import strip_proxy_headers
        headers = {
            "X-whyllm-Key": "ld-test",
            "X-whyllm-Custom": "value",
            "Content-Type": "application/json",
        }
        result = strip_proxy_headers(headers)
        assert "X-whyllm-Key" not in result
        assert "X-whyllm-Custom" not in result
        assert result["Content-Type"] == "application/json"

    def test_strips_hop_by_hop_headers(self):
        from whyllm_api.proxy.utils import strip_proxy_headers
        headers = {
            "Host": "localhost:8000",
            "Content-Length": "42",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
            "Authorization": "Bearer sk-real",
            "Accept": "application/json",
        }
        result = strip_proxy_headers(headers)
        assert "Host" not in result
        assert "Content-Length" not in result
        assert "Transfer-Encoding" not in result
        assert "Connection" not in result
        assert "Authorization" in result
        assert "Accept" in result

    def test_empty_headers_returns_empty_dict(self):
        from whyllm_api.proxy.utils import strip_proxy_headers
        assert strip_proxy_headers({}) == {}

    def test_preserves_custom_headers(self):
        from whyllm_api.proxy.utils import strip_proxy_headers
        headers = {"X-Custom-Header": "value", "Accept-Language": "en-US"}
        result = strip_proxy_headers(headers)
        assert result == headers


# ── TestProxyUtils ────────────────────────────────────────────────────────────

class TestProxyUtils:
    """SSE parser and enqueue unit tests."""

    def test_parse_openai_sse_extracts_content_and_usage(self):
        import time
        from whyllm_api.proxy.utils import parse_openai_sse
        chunks = _openai_stream_chunks("Hi there")
        result = parse_openai_sse(chunks, "gpt-4o", time.perf_counter() - 0.1, ttft_ms=50)
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o"
        assert result["status"] == "success"
        assert result["input_tokens"] == 10
        assert result["output_tokens"] == 2
        assert result["ttft_ms"] == 50
        assert result["latency_ms"] >= 90
        response_content = result["response"]["choices"][0]["message"]["content"]
        assert "Hi there" in response_content

    def test_parse_openai_sse_empty_is_cancelled(self):
        import time
        from whyllm_api.proxy.utils import parse_openai_sse
        result = parse_openai_sse([], "gpt-4o", time.perf_counter(), ttft_ms=None)
        assert result["status"] == "cancelled"
        assert result["response"] is None

    def test_parse_anthropic_sse_extracts_content(self):
        import time
        from whyllm_api.proxy.utils import parse_anthropic_sse
        chunks = _anthropic_stream_chunks("Hi there")
        result = parse_anthropic_sse(chunks, "claude-3-5-sonnet-20241022",
                                     time.perf_counter() - 0.1, ttft_ms=60)
        assert result["provider"] == "anthropic"
        assert result["status"] == "success"
        assert result["ttft_ms"] == 60
        content_blocks = result["response"]["content"]
        assert any("Hi there" in b.get("text", "") for b in content_blocks)

    def test_parse_anthropic_sse_empty_is_cancelled(self):
        import time
        from whyllm_api.proxy.utils import parse_anthropic_sse
        result = parse_anthropic_sse([], "claude-3-5-sonnet-20241022",
                                     time.perf_counter(), ttft_ms=None)
        assert result["status"] == "cancelled"

    async def test_enqueue_proxy_span_never_raises(self):
        """enqueue_proxy_span is fire-and-forget — Redis failure is silently swallowed."""
        from whyllm_api.proxy.utils import enqueue_proxy_span
        from whyllm_api.middleware.api_key_auth import KeyContext

        ctx = KeyContext(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

        with patch("whyllm_api.proxy.utils.get_redis") as mock_redis:
            r = AsyncMock()
            r.lpush = AsyncMock(side_effect=ConnectionError("Redis gone"))
            mock_redis.return_value = r

            # Must not raise
            await enqueue_proxy_span({"span_id": str(uuid.uuid4()), "provider": "openai"}, ctx)

    async def test_enqueue_adds_proxy_metadata(self):
        """Enqueued span includes source=proxy, project_id, org_id."""
        from whyllm_api.proxy.utils import enqueue_proxy_span
        from whyllm_api.middleware.api_key_auth import KeyContext

        project_id = uuid.uuid4()
        org_id = uuid.uuid4()
        ctx = KeyContext(project_id, org_id, uuid.uuid4())

        enqueued: list[bytes] = []

        with patch("whyllm_api.proxy.utils.get_redis") as mock_redis:
            r = AsyncMock()

            async def capture(queue, payload):
                enqueued.append(payload)
                return 1

            r.lpush = capture
            mock_redis.return_value = r

            await enqueue_proxy_span(
                {"span_id": str(uuid.uuid4()), "provider": "openai"},
                ctx,
            )

        assert len(enqueued) == 1
        span = json.loads(enqueued[0])
        assert span["source"] == "proxy"
        assert span["project_id"] == str(project_id)
        assert span["org_id"] == str(org_id)
        assert "ingested_at" in span
