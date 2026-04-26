"""Add upstream_base_url + upstream_provider columns to projects.

Revision ID: a9f1e2b3c4d5
Revises: 8e7d6c5b4a3f
Create Date: 2026-04-23 00:00:00 UTC

Onboarding stores a single upstream LLM endpoint per project; the provider is
inferred from the base URL hostname at save time. Both columns are nullable —
legacy projects remain usable for ingest/SDK flows and only become proxy-ready
once an upstream is configured.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9f1e2b3c4d5"
down_revision: str | None = "8e7d6c5b4a3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("upstream_base_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("upstream_provider", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "upstream_provider")
    op.drop_column("projects", "upstream_base_url")
