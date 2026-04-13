"""Pydantic v2 schemas for the ingest endpoints.

Validation rules (enforced at schema level so the route is zero-logic):
  - provider: lowercased and stripped
  - tags: max 20 keys, keys/values truncated to 100 chars
  - request / response JSONB payloads: serialized JSON capped at 50 KB
  - started_at / ended_at: ended_at must be >= started_at
  - latency_ms: auto-computed from timestamps if not provided explicitly
  - idempotency_key: max 128 chars, stripped

SpanIngest intentionally does NOT validate provider/model against the pricing
table — unknown models are accepted and cost is set to NULL.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_TAGS = 20
_MAX_TAG_KEY_LEN = 100
_MAX_TAG_VAL_LEN = 100
_MAX_PAYLOAD_BYTES = 50 * 1024  # 50 KB


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate_payload(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """If the serialised JSON exceeds 50 KB, replace with a sentinel dict."""
    if value is None:
        return None
    try:
        raw = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"_error": "payload_not_serializable"}
    if len(raw.encode()) > _MAX_PAYLOAD_BYTES:
        return {"_truncated": True, "_original_bytes": len(raw.encode())}
    return value


# ── Ingest request schema ─────────────────────────────────────────────────────

class SpanIngest(BaseModel):
    """Single LLM call span submitted by the SDK / proxy."""

    model_config = {"str_strip_whitespace": True, "populate_by_name": True}

    # ── Required ──────────────────────────────────────────────────────────────
    provider: str = Field(..., min_length=1, max_length=50, description="LLM provider (openai, anthropic, google…)")
    model: str = Field(..., min_length=1, max_length=255, description="Model name")
    status: str = Field(..., description="success | error | timeout | cancelled")

    # ── Optional — identity ───────────────────────────────────────────────────
    name: Optional[str] = Field(None, max_length=255)
    kind: str = Field("llm_call", max_length=50, description="llm_call | retrieval | tool_call | custom")
    environment: str = Field("production", max_length=50)

    # ── Optional — attribution ────────────────────────────────────────────────
    user_id: Optional[str] = Field(None, max_length=255)
    session_id: Optional[str] = Field(None, max_length=255)
    tags: dict[str, Any] = Field(default_factory=dict)

    # ── Optional — trace hierarchy ────────────────────────────────────────────
    trace_id: Optional[uuid.UUID] = None
    parent_span_id: Optional[uuid.UUID] = None

    # ── Optional — token counts ───────────────────────────────────────────────
    input_tokens: Optional[int] = Field(None, ge=0)
    output_tokens: Optional[int] = Field(None, ge=0)
    cached_tokens: int = Field(0, ge=0)

    # ── Optional — performance ────────────────────────────────────────────────
    latency_ms: Optional[int] = Field(None, ge=0)
    ttft_ms: Optional[int] = Field(None, ge=0)

    # ── Optional — error details ──────────────────────────────────────────────
    error_type: Optional[str] = Field(None, max_length=255)
    error_message: Optional[str] = None

    # ── Optional — timing ─────────────────────────────────────────────────────
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    # ── Optional — payloads ───────────────────────────────────────────────────
    request: Optional[dict[str, Any]] = None
    response: Optional[dict[str, Any]] = None

    # ── Optional — source ─────────────────────────────────────────────────────
    source: str = Field("api", max_length=50, description="proxy | python-sdk | js-sdk | api")
    sdk_version: Optional[str] = Field(None, max_length=50)

    # ── Optional — idempotency ────────────────────────────────────────────────
    idempotency_key: Optional[str] = Field(None, max_length=128)

    # ── Field validators ─────────────────────────────────────────────────────

    @field_validator("provider", mode="before")
    @classmethod
    def normalise_provider(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("provider must be a string")
        return v.strip().lower()

    @field_validator("status", mode="before")
    @classmethod
    def normalise_status(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("status must be a string")
        v = v.strip().lower()
        allowed = {"success", "error", "timeout", "cancelled"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v

    @field_validator("kind", mode="before")
    @classmethod
    def normalise_kind(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("kind must be a string")
        v = v.strip().lower()
        allowed = {"llm_call", "retrieval", "tool_call", "custom"}
        if v not in allowed:
            raise ValueError(f"kind must be one of {allowed}")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("tags must be a JSON object")
        if len(v) > _MAX_TAGS:
            raise ValueError(f"tags must have at most {_MAX_TAGS} keys (got {len(v)})")
        cleaned: dict[str, Any] = {}
        for k, val in v.items():
            k_str = str(k)[:_MAX_TAG_KEY_LEN]
            val_str = str(val)[:_MAX_TAG_VAL_LEN] if isinstance(val, str) else val
            cleaned[k_str] = val_str
        return cleaned

    @field_validator("request", "response", mode="before")
    @classmethod
    def truncate_payloads(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("request/response must be a JSON object")
        return _truncate_payload(v)

    @field_validator("started_at", "ended_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> Optional[datetime]:
        if v is None:
            return None
        if isinstance(v, str):
            # Parse ISO 8601 strings (e.g. "2026-04-10T12:00:00Z" or "+00:00")
            try:
                v = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"started_at/ended_at must be a valid ISO datetime: {exc}") from exc
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        raise ValueError("started_at/ended_at must be a datetime or ISO string")

    # ── Model validator (cross-field) ─────────────────────────────────────────

    @model_validator(mode="after")
    def compute_latency_and_check_timing(self) -> SpanIngest:
        if self.started_at and self.ended_at:
            if self.ended_at < self.started_at:
                raise ValueError("ended_at must be >= started_at")
            # Auto-compute latency_ms if not provided
            if self.latency_ms is None:
                delta_ms = int((self.ended_at - self.started_at).total_seconds() * 1000)
                self.latency_ms = max(0, delta_ms)
        return self


# ── Batch schema ─────────────────────────────────────────────────────────────

class BatchIngest(BaseModel):
    """Up to 100 spans in a single HTTP request."""

    spans: list[SpanIngest] = Field(..., min_length=1, max_length=100)


# ── Response schemas ──────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    """Response for a single span ingest."""

    span_id: uuid.UUID
    queued: bool = True
    cost_usd: Optional[float] = None  # None when model is unknown


class IngestError(BaseModel):
    """Per-span error detail in a batch response."""

    index: int
    error: str


class BatchIngestResponse(BaseModel):
    """Response for a batch ingest — partial success is allowed."""

    accepted: int
    rejected: int
    span_ids: list[uuid.UUID]
    errors: list[IngestError] = Field(default_factory=list)
