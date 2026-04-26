"""Add proxy_overhead_ms column to spans.

Revision ID: b1c2d3e4f5a6
Revises: a9f1e2b3c4d5
Create Date: 2026-04-23 00:00:00 UTC

Captures the time whyllm's proxy spent on auth-adjacent work before forwarding
the request to the upstream provider — independent of `ttft_ms` and
`latency_ms`, which now cleanly represent upstream-only timings. Adding a
column to a partitioned table cascades to every partition automatically.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a9f1e2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "spans",
        sa.Column("proxy_overhead_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("spans", "proxy_overhead_ms")
