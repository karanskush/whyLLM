"""Authentication service — JWT creation/verification + password hashing.

Security design:
  - Passwords hashed with bcrypt (via passlib). Never stored in plaintext.
  - JWTs signed with HS256 + SECRET_KEY. 7-day expiry.
  - bcrypt.checkpw is CPU-bound (~80–150ms) — always runs in executor.
  - get_current_user raises HTTP 401 on any failure (no information leakage).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llmdawg_api.config import get_settings
from llmdawg_api.database import get_session_factory
from llmdawg_api.models.user import User

log = logging.getLogger(__name__)


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt. CPU-bound — run in executor."""
    import bcrypt as _bcrypt
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


async def verify_password_async(plain: str, hashed: str) -> bool:
    """Verify a password off the event loop to avoid blocking."""
    import bcrypt as _bcrypt
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _bcrypt.checkpw,
        plain.encode(),
        hashed.encode(),
    )


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(
    user_id: uuid.UUID,
    org_id: Optional[uuid.UUID],
    email: str,
) -> str:
    """Create a signed JWT access token with 7-day expiry."""
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id) if org_id else None,
        "email": email,
        "exp": datetime.now(tz=timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises ValueError on any failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
        return payload
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
) -> User:
    """FastAPI dependency — verifies JWT and returns the User object.

    Raises HTTP 401 on any failure (missing header, bad token, user not found).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_token", "message": "Authorization header required"},
        )

    token = authorization[7:]  # strip "Bearer "

    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "message": str(exc)},
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={"error": "user_not_found", "message": "User not found or inactive"},
        )

    return user
