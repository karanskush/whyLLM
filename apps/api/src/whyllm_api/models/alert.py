"""Alert — a metric threshold rule that triggers notifications.

Supported metrics: cost_usd | error_rate | latency_p95 | hallucination_score
Conditions:        gt (greater than) | lt (less than)
Window:            evaluated over the past window_minutes minutes

channels example:
  [{"type": "email",   "target": "ops@example.com"},
   {"type": "webhook", "target": "https://hooks.example.com/alert"}]
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whyllm_api.database import Base

if TYPE_CHECKING:
    from whyllm_api.models.alert_event import AlertEvent
    from whyllm_api.models.project import Project


class Alert(Base):
    __tablename__ = "alerts"

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
    # cost_usd | error_rate | latency_p95 | hallucination_score
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    # gt | lt
    condition: Mapped[str] = mapped_column(String(20), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    window_minutes: Mapped[int] = mapped_column(
        Integer,
        server_default=text("60"),
        nullable=False,
    )
    channels: Mapped[list[Any]] = mapped_column(
        JSONB,
        server_default=text("'[]'"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    # ---- relationships --------------------------------------------------------
    project: Mapped[Project] = relationship(back_populates="alerts")
    events: Mapped[list[AlertEvent]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
    )
