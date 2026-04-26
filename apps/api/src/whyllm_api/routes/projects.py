"""Project routes — create and list projects for the authenticated user's org.

GET   /v1/projects                   — list all projects in the user's org
POST  /v1/projects                   — create a new project under the user's org
PATCH /v1/projects/{id}/upstream     — set the project's upstream LLM endpoint
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from pydantic import BaseModel
from sqlalchemy import select, text

from whyllm_api.database import get_session_factory
from whyllm_api.models.org_member import OrgMember
from whyllm_api.models.user import User
from whyllm_api.routes.proxy import infer_provider, invalidate_upstream_cache
from whyllm_api.services.auth_service import get_current_user

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
    upstream_base_url: Optional[str] = None  # optional at create; can be set later


class UpstreamPatch(BaseModel):
    base_url: str


class ProjectResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    upstream_base_url: Optional[str]
    upstream_provider: Optional[str]
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

def _normalize_base_url(raw: str) -> str:
    """Reject obviously-bad URLs and trim the trailing slash."""
    url = (raw or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_base_url",
                "message": "base_url must be a full http(s) URL, e.g. https://api.openai.com",
            },
        )
    return url


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
                SELECT id, org_id, name, slug, description,
                       upstream_base_url, upstream_provider, created_at
                FROM projects
                WHERE org_id = :org_id
                ORDER BY created_at ASC
            """),
            {"org_id": str(org_id)},
        )
        rows = result.fetchall()

    return [
        ProjectResponse(
            id=r[0], org_id=r[1], name=r[2], slug=r[3], description=r[4],
            upstream_base_url=r[5], upstream_provider=r[6], created_at=r[7],
        )
        for r in rows
    ]


@router.post("/v1/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Create a new project under the authenticated user's organization.

    If `upstream_base_url` is provided, the provider is inferred from the
    hostname and stored alongside it.
    """
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=422, detail={"error": "name_required"})

    org_id = await _get_user_org(current_user)

    project_id = uuid.uuid4()
    slug = _slugify(body.name.strip())
    now = datetime.now(tz=timezone.utc)

    upstream_url: Optional[str] = None
    upstream_provider: Optional[str] = None
    if body.upstream_base_url:
        upstream_url = _normalize_base_url(body.upstream_base_url)
        upstream_provider = infer_provider(upstream_url)

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO projects
                    (id, org_id, name, slug, description,
                     upstream_base_url, upstream_provider)
                VALUES
                    (:id, :org_id, :name, :slug, :description,
                     :upstream_base_url, :upstream_provider)
            """),
            {
                "id": str(project_id),
                "org_id": str(org_id),
                "name": body.name.strip(),
                "slug": slug,
                "description": body.description,
                "upstream_base_url": upstream_url,
                "upstream_provider": upstream_provider,
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
        upstream_base_url=upstream_url,
        upstream_provider=upstream_provider,
        created_at=now,
    )


@router.patch("/v1/projects/{project_id}/upstream", response_model=ProjectResponse)
async def set_project_upstream(
    project_id: uuid.UUID,
    body: UpstreamPatch,
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Set (or replace) the project's upstream LLM endpoint.

    Provider is inferred from the base URL hostname — the caller only supplies
    the URL. Invalidates the proxy's upstream cache so the change takes effect
    within a request or two.
    """
    org_id = await _get_user_org(current_user)
    url = _normalize_base_url(body.base_url)
    provider = infer_provider(url)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("""
                UPDATE projects
                SET upstream_base_url = :base_url,
                    upstream_provider = :provider
                WHERE id = :id AND org_id = :org_id
                RETURNING id, org_id, name, slug, description,
                          upstream_base_url, upstream_provider, created_at
            """),
            {
                "id": str(project_id),
                "org_id": str(org_id),
                "base_url": url,
                "provider": provider,
            },
        )
        row = result.fetchone()
        await session.commit()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    await invalidate_upstream_cache(project_id)
    log.info("Set upstream for project %s → %s (%s)", project_id, url, provider)

    return ProjectResponse(
        id=row[0], org_id=row[1], name=row[2], slug=row[3], description=row[4],
        upstream_base_url=row[5], upstream_provider=row[6], created_at=row[7],
    )
