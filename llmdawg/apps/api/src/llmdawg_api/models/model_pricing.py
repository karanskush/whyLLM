"""ModelPricing — versioned LLM pricing table.

Rows are NEVER deleted. When a provider changes prices, a new row is
inserted with a new effective_from and the old row gets effective_to set.
This allows accurate cost recalculation for historical spans.

Prices are stored per 1,000 tokens (not per 1M) for SQL math convenience:
  cost = (tokens / 1000.0) * cost_per_1k
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Numeric, String, UniqueConstraint, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from llmdawg_api.database import Base


class ModelPricing(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (
        UniqueConstraint(
            "provider", "model", "effective_from",
            name="uq_model_pricing_provider_model_effective_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    # USD per 1,000 tokens
    input_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    output_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    # NULL means provider does not support prompt caching
    cached_input_cost_per_1k_tokens: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    # Inclusive lower bound of this price's validity window
    effective_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    # NULL = still current. Set when a price change is published.
    effective_to: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
