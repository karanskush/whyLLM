"""AlertEvent — a single firing of an Alert rule.

One row per trigger. The context JSONB column stores a snapshot of the
metric window that caused the trigger (for display in the UI and notifications).

context example:
  {
    "window_start":  "2026-04-10T10:00:00Z",
    "window_end":    "2026-04-10T11:00:00Z",
    "metric_value":  12.45,
    "threshold":     10.00,
    "span_count":    3821,
    "top_models":    ["gpt-4o", "claude-sonnet-4-6"]
  }
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Numeric, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llmdawg_api.database import Base

if TYPE_CHECKING:
    from llmdawg_api.models.alert import Alert


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ---- relationships --------------------------------------------------------
    alert: Mapped[Alert] = relationship(back_populates="events")
