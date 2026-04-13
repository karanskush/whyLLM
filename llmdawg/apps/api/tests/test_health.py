"""Smoke tests for /health and /ready endpoints.

These tests run against a live app instance (requires DB + Redis via Docker).
The health endpoint is always expected to return 200 regardless of downstream state.
"""

from httpx import AsyncClient, ASGITransport

from llmdawg_api.main import app


async def test_health_returns_ok() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_health_version_format() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    version = response.json()["version"]
    parts = version.split(".")
    assert len(parts) == 3, f"Expected semver, got: {version}"


async def test_ready_endpoint_exists() -> None:
    """Verify /ready exists and returns a structured response (may be 200 or 503)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    # 503 wraps the payload in HTTPException.detail
    if response.status_code == 503:
        data = data.get("detail", data)
    assert "status" in data
    assert "checks" in data
