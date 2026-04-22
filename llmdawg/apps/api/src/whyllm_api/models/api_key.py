"""ApiKey — project-scoped ingest credentials.

The actual key is NEVER stored. Only:
  - key_hash: bcrypt hash (for constant-time verification)
  - key_prefix: first ~12 chars (for display in UI: "wl-prod_a1b2...")
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whyllm_api.database import Base

if TYPE_CHECKING:
    from whyllm_api.models.project import Project


class ApiKey(Base):
    __tablename__ = "api_keys"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # bcrypt hash of the raw key — use passlib to verify
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # first 12 chars of the raw key, shown in UI e.g. "wl-prod_a1b2"
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    # ---- relationships --------------------------------------------------------
    project: Mapped[Project] = relationship(back_populates="api_keys")
