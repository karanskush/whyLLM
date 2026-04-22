"""Spans list/detail response schemas."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel


class SpanListItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    trace_id: Optional[uuid.UUID]
    project_id: uuid.UUID
    provider: str
    model: str
    status: str
    kind: str
    environment: str
    user_id: Optional[str]
    session_id: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    cost_usd: Optional[Decimal]
    latency_ms: Optional[int]
    ttft_ms: Optional[int]
    hallucination_score: Optional[Decimal]
    source: str
    started_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SpanDetailResponse(SpanListItem):
    tags: dict[str, Any]
    request: Optional[dict[str, Any]]
    response: Optional[dict[str, Any]]
    hallucination_flags: Optional[dict[str, Any]]
    error_type: Optional[str]
    error_message: Optional[str]
    ended_at: Optional[datetime]
    sdk_version: Optional[str]
    parent_span_id: Optional[uuid.UUID]

    # Sibling spans (same trace_id), for timeline rendering
    siblings: list["SpanListItem"] = []


class SpanListResponse(BaseModel):
    items: list[SpanListItem]
    next_cursor: Optional[str]
    has_more: bool
    total_hint: int  # approximate count for display


def encode_cursor(ts: datetime, span_id: uuid.UUID) -> str:
    """Encode a cursor from a created_at timestamp and span id."""
    payload = json.dumps({"ts": ts.isoformat(), "id": str(span_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode a cursor string. Raises ValueError on any invalid input."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        ts = datetime.fromisoformat(payload["ts"])
        span_id = uuid.UUID(payload["id"])
        return ts, span_id
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {exc}") from exc


SpanDetailResponse.model_rebuild()
