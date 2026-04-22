"""Seed model_pricing with current LLM prices from packages/cost-tables/prices.json.

Revision ID: 8e7d6c5b4a3f
Revises: 4f3e2d1c0b9a
Create Date: 2026-04-10 00:01:00 UTC

Prices sourced from packages/cost-tables/prices.json (USD per 1M tokens).
Stored as USD per 1K tokens: per_1k = per_1m / 1000.

This migration is intentionally self-contained — it does NOT import loader.py
at runtime. Migrations must be reproducible without external file dependencies.
If prices change, add a NEW migration row (never UPDATE existing rows).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8e7d6c5b4a3f"
down_revision: str | None = "4f3e2d1c0b9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Effective date for this price snapshot
_EFFECTIVE_FROM = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)

# Prices are stored PER 1K TOKENS (source JSON is per 1M tokens → divide by 1000)
# Format: (provider, model, input_per_1k, output_per_1k, cached_per_1k or None)
_PRICES: list[tuple[str, str, str, str, str | None]] = [
    # ── OpenAI ───────────────────────────────────────────────────────────────
    # gpt-4o: $2.50/$10.00/$1.25 per 1M → $0.0025/$0.01/$0.00125 per 1K
    ("openai", "gpt-4o",      "0.00250000", "0.01000000", "0.00125000"),
    # gpt-4o-mini: $0.15/$0.60/$0.075 per 1M
    ("openai", "gpt-4o-mini", "0.00015000", "0.00060000", "0.00007500"),
    # o1: $15.00/$60.00/$7.50 per 1M
    ("openai", "o1",          "0.01500000", "0.06000000", "0.00750000"),
    # o3-mini: $1.10/$4.40/$0.55 per 1M
    ("openai", "o3-mini",     "0.00110000", "0.00440000", "0.00055000"),

    # ── Anthropic ────────────────────────────────────────────────────────────
    # claude-opus-4-6: $15.00/$75.00/$1.50 per 1M
    ("anthropic", "claude-opus-4-6",             "0.01500000", "0.07500000", "0.00150000"),
    # claude-sonnet-4-6: $3.00/$15.00/$0.30 per 1M
    ("anthropic", "claude-sonnet-4-6",           "0.00300000", "0.01500000", "0.00030000"),
    # claude-haiku-4-5-20251001: $0.80/$4.00/$0.08 per 1M
    ("anthropic", "claude-haiku-4-5-20251001",   "0.00080000", "0.00400000", "0.00008000"),

    # ── Google ───────────────────────────────────────────────────────────────
    # gemini-1.5-pro: $1.25/$5.00/$0.3125 per 1M
    ("google", "gemini-1.5-pro",   "0.00125000", "0.00500000", "0.00031250"),
    # gemini-1.5-flash: $0.075/$0.30/$0.01875 per 1M
    ("google", "gemini-1.5-flash", "0.00007500", "0.00030000", "0.00001875"),
]


def upgrade() -> None:
    model_pricing = sa.table(
        "model_pricing",
        sa.column("id", postgresql.UUID()),
        sa.column("provider", sa.String()),
        sa.column("model", sa.String()),
        sa.column("input_cost_per_1k_tokens", sa.Numeric()),
        sa.column("output_cost_per_1k_tokens", sa.Numeric()),
        sa.column("cached_input_cost_per_1k_tokens", sa.Numeric()),
        sa.column("effective_from", sa.TIMESTAMP(timezone=True)),
        sa.column("effective_to", sa.TIMESTAMP(timezone=True)),
    )

    op.bulk_insert(
        model_pricing,
        [
            {
                "id": str(uuid.uuid4()),
                "provider": provider,
                "model": model,
                "input_cost_per_1k_tokens": input_per_1k,
                "output_cost_per_1k_tokens": output_per_1k,
                "cached_input_cost_per_1k_tokens": cached_per_1k,
                "effective_from": _EFFECTIVE_FROM,
                "effective_to": None,
            }
            for provider, model, input_per_1k, output_per_1k, cached_per_1k in _PRICES
        ],
    )


def downgrade() -> None:
    # Remove only the rows inserted by this migration — identified by effective_from.
    # Other price rows (from future migrations) are untouched.
    op.execute(
        sa.text(
            "DELETE FROM model_pricing WHERE effective_from = :ts"
        ).bindparams(ts=_EFFECTIVE_FROM)
    )
