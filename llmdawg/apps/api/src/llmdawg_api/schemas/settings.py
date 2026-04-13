"""Request/response schemas for API keys, budgets, and alerts."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── API Keys ───────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    environment: str = Field(default="production", pattern="^(production|staging|development)$")
    expires_at: Optional[datetime] = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    key_prefix: str
    environment: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned ONCE on creation — includes the raw key."""
    raw_key: str


# ── Budgets ────────────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    scope: str = Field(default="project", pattern="^(project|user|session)$")
    scope_value: Optional[str] = Field(default=None, max_length=255)
    amount_usd: Decimal = Field(gt=0)
    period: str = Field(pattern="^(daily|weekly|monthly|total)$")
    action: str = Field(default="alert", pattern="^(alert|block)$")


class BudgetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    scope: str
    scope_value: Optional[str]
    amount_usd: Decimal
    period: str
    action: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Alerts ─────────────────────────────────────────────────────────────────────

class AlertChannel(BaseModel):
    type: str = Field(pattern="^(email|webhook|slack)$")
    target: str = Field(min_length=1, max_length=500)


class AlertCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    metric: str = Field(pattern="^(cost_usd|error_rate|latency_p95|hallucination_score)$")
    condition: str = Field(pattern="^(gt|lt)$")
    threshold: Decimal = Field(ge=0)
    window_minutes: int = Field(default=60, ge=1, le=10080)
    channels: list[AlertChannel] = Field(default_factory=list)


class AlertResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    metric: str
    condition: str
    threshold: Decimal
    window_minutes: int
    channels: list[Any]
    is_active: bool
    last_triggered_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Cost breakdown ─────────────────────────────────────────────────────────────

class CostBreakdownItem(BaseModel):
    model: str
    provider: str
    span_count: int
    total_cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    pct_of_total: float


class CostBreakdownResponse(BaseModel):
    project_id: uuid.UUID
    window: str
    since: datetime
    total_cost_usd: Decimal
    items: list[CostBreakdownItem]
    top_users: list[dict[str, Any]]
