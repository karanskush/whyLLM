"""Shared httpx.AsyncClient pool for all proxy routes.

A single long-lived client instance is created at startup and reused across
all concurrent proxy requests — avoids per-request TCP handshakes and DNS
lookups, which would add 50–200ms latency.

Lifecycle:
    init_proxy_client()  — called once during app startup (lifespan)
    get_proxy_client()   — called per-request to retrieve the singleton
    close_proxy_client() — called once during app shutdown (lifespan)
"""

from __future__ import annotations

import httpx

_proxy_client: httpx.AsyncClient | None = None


def get_proxy_client() -> httpx.AsyncClient:
    """Return the module-level httpx client (created on first call if not initialized)."""
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = _build_client()
    return _proxy_client


async def init_proxy_client() -> None:
    """Explicitly initialize the client at startup."""
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = _build_client()


async def close_proxy_client() -> None:
    """Close the httpx client pool — call on app shutdown."""
    global _proxy_client
    if _proxy_client is not None:
        await _proxy_client.aclose()
        _proxy_client = None


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0,   # time to establish TCP connection
            read=120.0,    # max time to receive first byte (LLM latency)
            write=10.0,    # time to send the request body
            pool=5.0,      # time to acquire a connection from the pool
        ),
        limits=httpx.Limits(
            max_connections=200,
            max_keepalive_connections=50,
        ),
        follow_redirects=False,
    )
