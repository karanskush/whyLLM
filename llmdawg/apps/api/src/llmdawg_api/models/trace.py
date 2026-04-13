"""Trace — a lightweight grouping of related spans.

A trace represents one logical user-facing operation (e.g. "process document").
Its aggregate fields (total_cost_usd, total_tokens, status) are maintained by
the background worker that processes the ingest queue — never updated inline.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from llmdawg_api.database import Base


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (
        Index("idx_traces_project_created", "project_id", "created_at"),
        Index("idx_traces_project_user_created", "project_id", "user_id", "created_at"),
    )

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
    # Denormalized for query performance — avoids join to projects on every query
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    environment: Mapped[str] = mapped_column(
        String(50),
        server_default=text("'production'"),
        nullable=False,
    )
    # End-user of the calling application (not the developer)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'"), nullable=False
    )
    # Derived from worst child span status: running | success | error | timeout | cancelled
    status: Mapped[str] = mapped_column(
        String(50),
        server_default=text("'running'"),
        nullable=False,
    )
    # Aggregate fields — maintained by background worker
    total_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 8), nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Wall-clock latency: first span started_at → last span ended_at
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    span_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
