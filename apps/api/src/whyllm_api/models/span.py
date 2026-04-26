"""Span — the atomic unit of observability. Every LLM call becomes a span.

This table is PARTITIONED BY RANGE (created_at) with monthly partitions.
PostgreSQL requires the partition key to be part of any UNIQUE or PRIMARY KEY
constraint, so the primary key is (id, created_at).

The table DDL is managed entirely via raw SQL in the migration — Alembic's
op.create_table() does not support PARTITION BY RANGE or GENERATED columns.
This model exists for ORM read/write operations only.

Important constraints:
- No formal FK from other tables TO spans (partitioned tables can't be FK targets)
- trace_id and parent_span_id are soft references enforced at application level
- total_tokens is a GENERATED ALWAYS AS STORED column — do NOT write to it
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Computed, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from whyllm_api.database import Base


class Span(Base):
    __tablename__ = "spans"

    # Composite PK required by PostgreSQL for partitioned tables.
    # The partition key (created_at) must be part of every unique constraint.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        primary_key=True,
        server_default=text("NOW()"),
        nullable=False,
    )

    # ---- Grouping / hierarchy ------------------------------------------------
    # Soft FK to traces.id — no formal FK constraint (partitioned table limitation)
    trace_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Soft self-reference to parent span (e.g. tool call within agent loop)
    parent_span_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized — avoids join to projects on every analytical query
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # ---- Identity ------------------------------------------------------------
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # llm_call | retrieval | tool_call | custom
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(50),
        server_default=text("'production'"),
        nullable=False,
    )

    # ---- Attribution (end-user of the calling app, not the developer) --------
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'"), nullable=False
    )

    # ---- LLM specifics -------------------------------------------------------
    # openai | anthropic | google | cohere
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # gpt-4o | claude-sonnet-4-6 | gemini-1.5-pro
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    # ---- Token economics -----------------------------------------------------
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    # GENERATED ALWAYS AS STORED — do NOT include in INSERT statements
    total_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        Computed("COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)", persisted=True),
        nullable=True,
    )

    # ---- Cost ----------------------------------------------------------------
    # Computed at ingest time from model_pricing, stored for fast aggregation
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 8), nullable=True)

    # ---- Performance ---------------------------------------------------------
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Time to first token — only meaningful for streaming requests
    ttft_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Time spent inside whyllm before forwarding to upstream
    # (upstream resolve + body parse + budget gate + header build).
    # ttft_ms and latency_ms are measured *from forward*, so they are
    # upstream-only; proxy_overhead_ms captures everything we add on top.
    proxy_overhead_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Rich extensible timing metadata extracted from upstream — provider
    # self-reported processing_ms (openai-processing-ms etc.), per-chunk
    # streaming rhythm (downsampled), derived jitter/stall stats, request id.
    # See proxy.py:_build_timings for the schema.
    timings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ---- Status --------------------------------------------------------------
    # success | error | timeout | cancelled
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- Payloads (stored for debugging; can be redacted via project settings) -
    request: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    response: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ---- Quality signals -----------------------------------------------------
    # 0.00–1.00, NULL if not computed yet
    hallucination_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    # {"repetition": 0.7, "contradiction": 0.3, ...}
    hallucination_flags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ---- Provenance ----------------------------------------------------------
    # proxy | python-sdk | js-sdk | api
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    sdk_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
