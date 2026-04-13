"""Admin routes — internal operator dashboard.

Only accessible to users whose email is in the ADMIN_EMAILS env var.

GET  /api/v1/admin/projects   — list every org + project in the system with stats
POST /api/v1/admin/clients    — create a new org + project + API key for a new client
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from llmdawg_api.config import get_settings
from llmdawg_api.database import get_session_factory
from llmdawg_api.models.user import User
from llmdawg_api.services.auth_service import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return (slug or "item")[:80] + "-" + uuid.uuid4().hex[:6]


# ── Admin guard ───────────────────────────────────────────────────────────────

def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    settings = get_settings()
    if current_user.email.lower() not in settings.admin_email_set:
        raise HTTPException(status_code=403, detail={"error": "admin_only"})
    return current_user


# ── Schemas ───────────────────────────────────────────────────────────────────

class AdminProjectRow(BaseModel):
    org_id: uuid.UUID
    org_name: str
    project_id: uuid.UUID
    project_name: str
    project_slug: str
    created_at: datetime
    span_count: int
    total_cost_usd: float
    last_active_at: Optional[datetime]


class CreateClientRequest(BaseModel):
    org_name: str
    project_name: str


class CreateClientResponse(BaseModel):
    org_id: uuid.UUID
    org_name: str
    project_id: uuid.UUID
    project_name: str
    api_key: str   # raw key — shown once, never stored


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[AdminProjectRow])
async def admin_list_projects(
    _: User = Depends(_require_admin),
) -> list[AdminProjectRow]:
    """List every org + project in the system with span count and cost."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(text("""
            SELECT
                o.id          AS org_id,
                o.name        AS org_name,
                p.id          AS project_id,
                p.name        AS project_name,
                p.slug        AS project_slug,
                p.created_at  AS created_at,
                COUNT(s.id)                           AS span_count,
                COALESCE(SUM(s.cost_usd::numeric), 0) AS total_cost_usd,
                MAX(s.created_at)                     AS last_active_at
            FROM organizations o
            JOIN projects p ON p.org_id = o.id
            LEFT JOIN spans s ON s.project_id = p.id
            GROUP BY o.id, o.name, p.id, p.name, p.slug, p.created_at
            ORDER BY p.created_at DESC
        """))
        rows = result.fetchall()

    return [
        AdminProjectRow(
            org_id=r[0], org_name=r[1],
            project_id=r[2], project_name=r[3], project_slug=r[4],
            created_at=r[5],
            span_count=int(r[6]),
            total_cost_usd=float(r[7]),
            last_active_at=r[8],
        )
        for r in rows
    ]


@router.post("/clients", response_model=CreateClientResponse, status_code=201)
async def admin_create_client(
    body: CreateClientRequest,
    _: User = Depends(_require_admin),
) -> CreateClientResponse:
    """
    Create a brand-new org + project + API key for an incoming client.
    Returns the raw API key — show it to the client, it is never stored.
    """
    if not body.org_name.strip() or not body.project_name.strip():
        raise HTTPException(status_code=422, detail={"error": "names_required"})

    org_id = uuid.uuid4()
    project_id = uuid.uuid4()
    key_id = uuid.uuid4()
    org_slug = _slugify(body.org_name.strip())
    project_slug = _slugify(body.project_name.strip())

    # Generate API key
    import bcrypt as _bcrypt
    token = secrets.token_urlsafe(24)
    raw_key = f"ld-prod_{token}"
    key_prefix = raw_key[:12]
    key_hash = _bcrypt.hashpw(raw_key.encode(), _bcrypt.gensalt()).decode()

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text("""
            INSERT INTO organizations (id, name, slug)
            VALUES (:id, :name, :slug)
        """), {"id": str(org_id), "name": body.org_name.strip(), "slug": org_slug})

        await session.execute(text("""
            INSERT INTO projects (id, org_id, name, slug)
            VALUES (:id, :org_id, :name, :slug)
        """), {
            "id": str(project_id),
            "org_id": str(org_id),
            "name": body.project_name.strip(),
            "slug": project_slug,
        })

        await session.execute(text("""
            INSERT INTO api_keys (id, project_id, name, key_hash, key_prefix)
            VALUES (:id, :project_id, :name, :key_hash, :key_prefix)
        """), {
            "id": str(key_id),
            "project_id": str(project_id),
            "name": "Default",
            "key_hash": key_hash,
            "key_prefix": key_prefix,
        })

        await session.commit()

    log.info(
        "Admin created client: org=%s project=%s key_prefix=%s",
        body.org_name, body.project_name, key_prefix,
    )

    return CreateClientResponse(
        org_id=org_id,
        org_name=body.org_name.strip(),
        project_id=project_id,
        project_name=body.project_name.strip(),
        api_key=raw_key,
    )
