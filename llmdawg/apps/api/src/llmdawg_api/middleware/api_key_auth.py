"""API key authentication for ingest endpoints.

Flow (p99 optimised):
  1. Extract raw key from X-LLMDawg-Key header.
  2. Check Redis: "apikey:{sha256(key)[:32]}" → {project_id, org_id, key_id}
  3. Cache miss: query api_keys WHERE key_prefix = key[:12], bcrypt verify.
     bcrypt runs in a thread-pool executor so it never blocks the event loop.
  4. Set TTL=5 min on the cached entry.
  5. Fire-and-forget: UPDATE api_keys SET last_used_at = NOW().

Security notes:
  - The raw key is NEVER stored anywhere (Redis or DB).
  - Redis cache key is SHA256(raw_key)[:32] — unguessable, one-to-one with raw key.
  - bcrypt verification only runs on the first request per TTL window.
  - Cache entries expire, limiting exposure window if Redis is ever compromised.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import Header, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from llmdawg_api.database import get_session_factory
from llmdawg_api.models.api_key import ApiKey
from llmdawg_api.models.project import Project
from llmdawg_api.redis_client import get_redis

log = logging.getLogger(__name__)

# Redis TTL for cached API key entries (seconds)
_KEY_CACHE_TTL = 300  # 5 minutes


class KeyContext:
    """Resolved identity from a validated API key — injected via Depends."""

    __slots__ = ("project_id", "org_id", "key_id")

    def __init__(
        self,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        key_id: uuid.UUID,
    ) -> None:
        self.project_id = project_id
        self.org_id = org_id
        self.key_id = key_id


def _cache_key(raw_key: str) -> str:
    """Deterministic Redis key derived from the raw API key (never stores the key itself)."""
    return "apikey:" + hashlib.sha256(raw_key.encode()).hexdigest()[:32]


async def _lookup_in_redis(raw_key: str) -> KeyContext | None:
    """Return a KeyContext if the key is found in the Redis cache."""
    try:
        cached = await get_redis().get(_cache_key(raw_key))
        if cached:
            data = json.loads(cached)
            return KeyContext(
                project_id=uuid.UUID(data["project_id"]),
                org_id=uuid.UUID(data["org_id"]),
                key_id=uuid.UUID(data["key_id"]),
            )
    except Exception as exc:
        # Redis failure is non-fatal here — fall through to DB lookup
        log.warning("Redis cache lookup failed: %s", exc)
    return None


async def _cache_in_redis(raw_key: str, ctx: KeyContext) -> None:
    """Store the resolved KeyContext in Redis with a 5-minute TTL."""
    try:
        payload = json.dumps({
            "project_id": str(ctx.project_id),
            "org_id": str(ctx.org_id),
            "key_id": str(ctx.key_id),
        })
        await get_redis().setex(_cache_key(raw_key), _KEY_CACHE_TTL, payload)
    except Exception as exc:
        log.warning("Redis cache write failed: %s", exc)


async def _lookup_in_db(raw_key: str) -> KeyContext | None:
    """Verify key against PostgreSQL.

    Queries only the rows whose key_prefix matches (avoids full table scan),
    then runs bcrypt verification in the thread pool to avoid blocking.
    """
    import bcrypt as _bcrypt_lib  # lazy import — only on cache miss

    key_prefix = raw_key[:12]
    now = datetime.now(tz=timezone.utc)

    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(ApiKey, Project.org_id)
            .join(Project, Project.id == ApiKey.project_id)
            .where(
                ApiKey.key_prefix == key_prefix,
                ApiKey.is_active.is_(True),
            )
        )
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        return None

    loop = asyncio.get_event_loop()

    for api_key_obj, org_id in rows:
        # Skip expired keys
        if api_key_obj.expires_at and api_key_obj.expires_at < now:
            continue

        # bcrypt.checkpw is CPU-bound (~80-150ms) — run it off the event loop
        try:
            verified: bool = await loop.run_in_executor(
                None,
                _bcrypt_lib.checkpw,
                raw_key.encode(),
                api_key_obj.key_hash.encode(),
            )
        except Exception:
            continue

        if verified:
            return KeyContext(
                project_id=api_key_obj.project_id,
                org_id=org_id,
                key_id=api_key_obj.id,
            )

    return None


async def _update_last_used(key_id: uuid.UUID) -> None:
    """Fire-and-forget: update last_used_at without blocking the request."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id)
                .values(last_used_at=datetime.now(tz=timezone.utc))
            )
            await session.commit()
    except Exception as exc:
        log.debug("last_used_at update failed (non-critical): %s", exc)


async def verify_api_key(
    request: Request,
    x_llmdawg_key: Annotated[Optional[str], Header(alias="X-LLMDawg-Key")] = None,
) -> KeyContext:
    """FastAPI dependency — resolves and returns a KeyContext or raises HTTP 401."""
    if not x_llmdawg_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key", "message": "X-LLMDawg-Key header is required"},
        )

    # 1. Fast path: Redis cache hit
    ctx = await _lookup_in_redis(x_llmdawg_key)

    # 2. Slow path: DB verification (only on cache miss)
    if ctx is None:
        ctx = await _lookup_in_db(x_llmdawg_key)
        if ctx is None:
            raise HTTPException(
                status_code=401,
                detail={"error": "invalid_api_key", "message": "API key is invalid or inactive"},
            )
        # Warm the cache for subsequent requests
        asyncio.create_task(_cache_in_redis(x_llmdawg_key, ctx))

    # 3. Non-blocking last_used_at update (fire and forget)
    asyncio.create_task(_update_last_used(ctx.key_id))

    return ctx
