"""Auth routes — register, login, me.

POST /api/v1/auth/register  — creates User + Organization + OrgMember(owner)
POST /api/v1/auth/login     — verifies credentials, returns JWT
GET  /api/v1/auth/me        — returns the current authenticated user

Registration auto-creates an organization named after the user (or org_name if
provided). The user becomes the owner.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from whyllm_api.config import get_settings
from whyllm_api.database import get_session_factory
from whyllm_api.models.org_member import OrgMember, ROLE_OWNER
from whyllm_api.models.organization import Organization
from whyllm_api.models.user import User
from whyllm_api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from whyllm_api.services.auth_service import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password_async,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return (slug or "org")[:80] + "-" + uuid.uuid4().hex[:6]


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest) -> TokenResponse:
    """Create a new user account with a personal organization."""
    factory = get_session_factory()

    # Hash password in executor (CPU-bound)
    import asyncio
    loop = asyncio.get_event_loop()
    hashed = await loop.run_in_executor(None, hash_password, body.password)

    org_name = body.org_name or (body.name or body.email.split("@")[0]) + "'s Org"
    org_slug = _slugify(org_name)

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    async with factory() as session:
        # Check email uniqueness
        existing = await session.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail={"error": "email_taken", "message": "An account with this email already exists"},
            )

        # Create org, user, membership in one transaction
        org = Organization(id=org_id, name=org_name, slug=org_slug)
        user = User(
            id=user_id,
            email=body.email,
            hashed_password=hashed,
            name=body.name,
        )
        session.add(org)
        session.add(user)
        await session.flush()  # get IDs before membership

        membership = OrgMember(org_id=org_id, user_id=user_id, role=ROLE_OWNER)
        session.add(membership)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail={"error": "email_taken", "message": "An account with this email already exists"},
            )

    token = create_access_token(user_id, org_id, body.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            email=body.email,
            name=body.name,
            org_id=org_id,
            org_name=org_name,
            is_admin=body.email.lower() in get_settings().admin_email_set,
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """Authenticate with email + password, return a JWT."""
    factory = get_session_factory()

    async with factory() as session:
        result = await session.execute(select(User).where(User.email == body.email))
        user: Optional[User] = result.scalar_one_or_none()

    _AUTH_ERR = HTTPException(
        status_code=401,
        detail={"error": "invalid_credentials", "message": "Email or password is incorrect"},
    )

    if user is None or not user.is_active or not user.hashed_password:
        # Constant-time — don't reveal whether email exists
        raise _AUTH_ERR

    verified = await verify_password_async(body.password, user.hashed_password)
    if not verified:
        raise _AUTH_ERR

    # Get the user's primary org
    async with factory() as session:
        result = await session.execute(
            select(OrgMember.org_id, Organization.name)
            .join(Organization, Organization.id == OrgMember.org_id)
            .where(OrgMember.user_id == user.id)
            .order_by(OrgMember.created_at)
            .limit(1)
        )
        row = result.first()

    org_id = row[0] if row else None
    org_name = row[1] if row else None

    token = create_access_token(user.id, org_id, user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            org_id=org_id,
            org_name=org_name,
            is_admin=user.email.lower() in get_settings().admin_email_set,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the current authenticated user's profile."""
    factory = get_session_factory()

    async with factory() as session:
        result = await session.execute(
            select(OrgMember.org_id, Organization.name)
            .join(Organization, Organization.id == OrgMember.org_id)
            .where(OrgMember.user_id == current_user.id)
            .order_by(OrgMember.created_at)
            .limit(1)
        )
        row = result.first()

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        org_id=row[0] if row else None,
        org_name=row[1] if row else None,
        is_admin=current_user.email.lower() in get_settings().admin_email_set,
    )
