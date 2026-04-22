"""Initial schema — all 11 tables, updated_at trigger, spans partitions + indexes.

Revision ID: 4f3e2d1c0b9a
Revises: —
Create Date: 2026-04-10 00:00:00 UTC

Tables created (dependency order):
  organizations → users → org_members → projects → api_keys →
  model_pricing → traces → spans (partitioned) →
  cost_budgets → alerts → alert_events

The spans table uses PARTITION BY RANGE (created_at). PostgreSQL requires the
partition key to be included in any UNIQUE constraint, so the PK is (id, created_at).
Indexes on a partitioned parent table propagate automatically to all partitions (PG10+).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4f3e2d1c0b9a"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Helper: create a BEFORE UPDATE trigger on a table using set_updated_at()
# ---------------------------------------------------------------------------
def _attach_updated_at_trigger(table_name: str) -> None:
    op.execute(f"""
        CREATE TRIGGER trg_{table_name}_updated_at
        BEFORE UPDATE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def _drop_updated_at_trigger(table_name: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_updated_at ON {table_name}")


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------
def upgrade() -> None:

    # ── Trigger function ─────────────────────────────────────────────────────
    # A single shared function used by all updated_at triggers.
    # CREATE OR REPLACE is idempotent; safe to run multiple times.
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # ── 1. organizations ─────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    _attach_updated_at_trigger("organizations")

    # ── 2. users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    _attach_updated_at_trigger("users")

    # ── 3. org_members ───────────────────────────────────────────────────────
    op.create_table(
        "org_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE", name="fk_org_members_org"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_org_members_user"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(50),
            server_default=sa.text("'member'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "user_id", name="uq_org_members_org_user"),
    )

    # ── 4. projects ──────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE", name="fk_projects_org"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "slug", name="uq_projects_org_slug"),
    )
    _attach_updated_at_trigger("projects")

    # ── 5. api_keys ──────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_api_keys_project"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )

    # ── 6. model_pricing ─────────────────────────────────────────────────────
    op.create_table(
        "model_pricing",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("input_cost_per_1k_tokens", sa.Numeric(12, 8), nullable=False),
        sa.Column("output_cost_per_1k_tokens", sa.Numeric(12, 8), nullable=False),
        sa.Column("cached_input_cost_per_1k_tokens", sa.Numeric(12, 8), nullable=True),
        sa.Column(
            "effective_from",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("effective_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "provider", "model", "effective_from",
            name="uq_model_pricing_provider_model_effective_from",
        ),
    )

    # ── 7. traces ────────────────────────────────────────────────────────────
    op.create_table(
        "traces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_traces_project"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "environment",
            sa.String(50),
            server_default=sa.text("'production'"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(50),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("total_cost_usd", sa.Numeric(12, 8), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "span_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_traces_project_created", "traces", ["project_id", "created_at"])
    op.create_index(
        "idx_traces_project_user_created", "traces",
        ["project_id", "user_id", "created_at"],
    )

    # ── 8. spans (partitioned) ───────────────────────────────────────────────
    #
    # Cannot use op.create_table() because:
    #   a) PARTITION BY RANGE is not supported by Alembic's DDL helpers
    #   b) GENERATED ALWAYS AS requires specific syntax
    #
    # PostgreSQL constraint: the partition key (created_at) MUST be part of any
    # UNIQUE or PRIMARY KEY constraint on a partitioned table.
    op.execute("""
        CREATE TABLE spans (
            id                  UUID NOT NULL DEFAULT gen_random_uuid(),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            trace_id            UUID,
            parent_span_id      UUID,
            project_id          UUID NOT NULL
                                    REFERENCES projects(id) ON DELETE CASCADE
                                    DEFERRABLE INITIALLY DEFERRED,
            org_id              UUID NOT NULL,

            name                VARCHAR(255),
            kind                VARCHAR(50) NOT NULL,
            environment         VARCHAR(50) NOT NULL DEFAULT 'production',

            user_id             VARCHAR(255),
            session_id          VARCHAR(255),
            tags                JSONB NOT NULL DEFAULT '{}',

            provider            VARCHAR(50)  NOT NULL,
            model               VARCHAR(255) NOT NULL,

            input_tokens        INTEGER,
            output_tokens       INTEGER,
            cached_tokens       INTEGER NOT NULL DEFAULT 0,
            total_tokens        INTEGER GENERATED ALWAYS AS
                                    (COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))
                                    STORED,

            cost_usd            NUMERIC(12, 8),

            latency_ms          INTEGER,
            ttft_ms             INTEGER,

            status              VARCHAR(50)  NOT NULL,
            error_type          VARCHAR(255),
            error_message       TEXT,

            request             JSONB,
            response            JSONB,

            hallucination_score NUMERIC(3, 2),
            hallucination_flags JSONB,

            source              VARCHAR(50)  NOT NULL,
            sdk_version         VARCHAR(50),

            started_at          TIMESTAMPTZ,
            ended_at            TIMESTAMPTZ,

            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # Indexes on the parent propagate automatically to all current and future partitions
    op.execute(
        "CREATE INDEX idx_spans_project_created "
        "ON spans (project_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_spans_project_model "
        "ON spans (project_id, model, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_spans_project_user "
        "ON spans (project_id, user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_spans_project_status "
        "ON spans (project_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_spans_trace "
        "ON spans (trace_id) WHERE trace_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_spans_tags "
        "ON spans USING GIN (tags)"
    )

    # Monthly partitions — current month + 2 ahead (2026-04, 2026-05, 2026-06)
    op.execute("""
        CREATE TABLE spans_2026_04 PARTITION OF spans
            FOR VALUES FROM ('2026-04-01') TO ('2026-05-01')
    """)
    op.execute("""
        CREATE TABLE spans_2026_05 PARTITION OF spans
            FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
    """)
    op.execute("""
        CREATE TABLE spans_2026_06 PARTITION OF spans
            FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
    """)

    # ── 9. cost_budgets ──────────────────────────────────────────────────────
    op.create_table(
        "cost_budgets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_cost_budgets_project"),
            nullable=False,
        ),
        sa.Column(
            "scope",
            sa.String(50),
            server_default=sa.text("'project'"),
            nullable=False,
        ),
        sa.Column("scope_value", sa.String(255), nullable=True),
        sa.Column("amount_usd", sa.Numeric(10, 4), nullable=False),
        sa.Column("period", sa.String(50), nullable=False),
        sa.Column(
            "action",
            sa.String(50),
            server_default=sa.text("'alert'"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # ── 10. alerts ───────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_alerts_project"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(100), nullable=False),
        sa.Column("condition", sa.String(20), nullable=False),
        sa.Column("threshold", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "window_minutes",
            sa.Integer(),
            server_default=sa.text("60"),
            nullable=False,
        ),
        sa.Column(
            "channels",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
        sa.Column("last_triggered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # ── 11. alert_events ─────────────────────────────────────────────────────
    op.create_table(
        "alert_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("alerts.id", ondelete="CASCADE", name="fk_alert_events_alert"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_alert_events_project"),
            nullable=False,
        ),
        sa.Column("metric_value", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "triggered_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("context", postgresql.JSONB(), nullable=True),
    )


# ---------------------------------------------------------------------------
# downgrade — reverse the upgrade in strict reverse-dependency order
# ---------------------------------------------------------------------------
def downgrade() -> None:
    # Leaf tables first
    op.drop_table("alert_events")
    op.drop_table("alerts")
    op.drop_table("cost_budgets")

    # Spans: drop partitions explicitly first, then the parent table.
    # Dropping the parent with CASCADE also removes partitions, but being
    # explicit makes the downgrade intent clear and avoids surprises.
    op.execute("DROP TABLE IF EXISTS spans_2026_06")
    op.execute("DROP TABLE IF EXISTS spans_2026_05")
    op.execute("DROP TABLE IF EXISTS spans_2026_04")
    op.execute("DROP TABLE IF EXISTS spans CASCADE")

    op.drop_table("traces")
    op.drop_table("model_pricing")
    op.drop_table("api_keys")

    # Drop triggers before dropping tables (avoids "trigger does not exist" errors)
    _drop_updated_at_trigger("projects")
    op.drop_table("projects")

    op.drop_table("org_members")

    _drop_updated_at_trigger("users")
    op.drop_table("users")

    _drop_updated_at_trigger("organizations")
    op.drop_table("organizations")

    # Drop the shared trigger function last
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
