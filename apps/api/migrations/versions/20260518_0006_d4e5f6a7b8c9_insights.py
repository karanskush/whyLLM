"""Add insights table — forward-looking predictions from the prediction engine.

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-05-18 00:00:00 UTC

The prediction engine (services/predictions/) writes one row per active
prediction: cost-overrun forecasts, rate-limit exhaustion ETAs, and model
drift alerts. Rows are upserted on (project_id, dedup_key) so a recurring
batch run refreshes an existing insight instead of spamming duplicates.

Not partitioned — volume is tiny (a handful of open insights per project).
updated_at is maintained by the application layer (the upsert sets it), so
no DB trigger dependency here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insights",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        # cost_forecast | rate_limit_eta | model_drift
        sa.Column("type", sa.String(50), nullable=False),
        # info | warning | critical
        sa.Column("severity", sa.String(20), nullable=False, server_default=sa.text("'info'")),
        # open | acknowledged | resolved
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "detail", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        # Stable key — one row per (project_id, dedup_key); the engine upserts.
        sa.Column("dedup_key", sa.String(255), nullable=False),
        # 0.00-1.00 — engine's confidence in the prediction
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        # When the predicted event is expected to occur
        sa.Column("predicted_for", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    # Upsert target — the engine keys on (project_id, dedup_key).
    op.create_index(
        "uq_insights_project_dedup", "insights",
        ["project_id", "dedup_key"], unique=True,
    )
    # Dashboard read path — open insights for a project, newest first.
    op.create_index(
        "ix_insights_project_status", "insights",
        ["project_id", "status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_insights_project_status", table_name="insights")
    op.drop_index("uq_insights_project_dedup", table_name="insights")
    op.drop_table("insights")
