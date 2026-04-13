"""Project routes — create and list projects for the authenticated user's org.

GET  /v1/projects        — list all projects in the user's org
POST /v1/projects        — create a new project under the user's org
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from pydantic import BaseModel
from sqlalchemy import select, text

from llmdawg_api.database import get_session_factory
from llmdawg_api.models.org_member import OrgMember
from llmdawg_api.models.user import User
from llmdawg_api.services.auth_service import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["projects"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return (slug or "project")[:80] + "-" + uuid.uuid4().hex[:6]


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    created_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_user_org(user: User) -> uuid.UUID:
    """Return the primary org_id for the user. Raises 404 if none."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(OrgMember.org_id)
            .where(OrgMember.user_id == user.id)
            .order_by(OrgMember.created_at)
            .limit(1)
        )
        row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "no_organization"})
    return row[0]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/v1/projects", response_model=list[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_user),
) -> list[ProjectResponse]:
    """List all projects in the authenticated user's organization."""
    org_id = await _get_user_org(current_user)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT id, org_id, name, slug, description, created_at
                FROM projects
                WHERE org_id = :org_id
                ORDER BY created_at ASC
            """),
            {"org_id": str(org_id)},
        )
        rows = result.fetchall()

    return [
        ProjectResponse(
            id=r[0], org_id=r[1], name=r[2], slug=r[3],
            description=r[4], created_at=r[5],
        )
        for r in rows
    ]


@router.post("/v1/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Create a new project under the authenticated user's organization."""
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=422, detail={"error": "name_required"})

    org_id = await _get_user_org(current_user)

    project_id = uuid.uuid4()
    slug = _slugify(body.name.strip())
    now = datetime.now(tz=timezone.utc)

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO projects (id, org_id, name, slug, description)
                VALUES (:id, :org_id, :name, :slug, :description)
            """),
            {
                "id": str(project_id),
                "org_id": str(org_id),
                "name": body.name.strip(),
                "slug": slug,
                "description": body.description,
            },
        )
        await session.commit()

    log.info("Created project %s (%s) for org %s", body.name, project_id, org_id)

    return ProjectResponse(
        id=project_id,
        org_id=org_id,
        name=body.name.strip(),
        slug=slug,
        description=body.description,
        created_at=now,
    )
