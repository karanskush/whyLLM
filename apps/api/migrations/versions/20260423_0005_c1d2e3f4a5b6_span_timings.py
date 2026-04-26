"""Add timings JSONB column to spans.

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-04-23 00:00:00 UTC

Flexible home for rich, extensible timing metadata extracted from the upstream
response — provider self-reported processing time (openai-processing-ms,
x-ms-azure-processing-ms, W3C Server-Timing), per-chunk streaming rhythm,
derived jitter / stall stats. Using JSONB means future timing fields don't
need their own migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "spans",
        sa.Column("timings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("spans", "timings")
