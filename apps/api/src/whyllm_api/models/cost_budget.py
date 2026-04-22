"""CostBudget — spending limit attached to a project, user, or session.

When a budget is breached, the action field determines what happens:
  alert  — publish an alert event, do not block traffic
  block  — return HTTP 429 from the ingest/proxy endpoint until the period resets
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Numeric, String, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whyllm_api.database import Base

if TYPE_CHECKING:
    from whyllm_api.models.project import Project


class CostBudget(Base):
    __tablename__ = "cost_budgets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # project | user | session
    scope: Mapped[str] = mapped_column(
        String(50),
        server_default=text("'project'"),
        nullable=False,
    )
    # The user_id / session_id to enforce this budget for, NULL for project-level
    scope_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    # daily | weekly | monthly | total
    period: Mapped[str] = mapped_column(String(50), nullable=False)
    # alert | block
    action: Mapped[str] = mapped_column(
        String(50),
        server_default=text("'alert'"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    # ---- relationships --------------------------------------------------------
    project: Mapped[Project] = relationship(back_populates="cost_budgets")
