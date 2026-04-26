"""Project — a named observability scope within an organization."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whyllm_api.database import Base

if TYPE_CHECKING:
    from whyllm_api.models.alert import Alert
    from whyllm_api.models.api_key import ApiKey
    from whyllm_api.models.cost_budget import CostBudget
    from whyllm_api.models.organization import Organization


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_projects_org_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Upstream LLM endpoint — one per project. provider is inferred from base_url
    # at save time; both are NULL until the customer completes onboarding.
    upstream_base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    upstream_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    # updated_at is kept current by the set_updated_at DB trigger
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    # ---- relationships --------------------------------------------------------
    organization: Mapped[Organization] = relationship(back_populates="projects")
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    cost_budgets: Mapped[list[CostBudget]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
