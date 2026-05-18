"""Insight persistence — upsert + stale-resolution.

Every analyser writes through `upsert_insight`, keyed on (project_id,
dedup_key): a recurring run refreshes the existing row instead of spamming
duplicates, and never clobbers a user-set status. `resolve_unlisted` closes
insights whose triggering condition the latest run no longer reproduces.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from whyllm_api.models.insight import Insight

log = logging.getLogger(__name__)


async def upsert_insight(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    type: str,
    dedup_key: str,
    severity: str,
    title: str,
    summary: str,
    detail: dict[str, Any],
    confidence: Optional[float] = None,
    predicted_for: Optional[datetime] = None,
) -> None:
    """Insert or refresh an insight.

    Re-running an analyser updates the existing row's content + `updated_at`;
    it never duplicates. `status` is intentionally left untouched on conflict
    so an acknowledged / resolved insight keeps the operator's decision.
    """
    now = datetime.now(tz=timezone.utc)
    conf = Decimal(str(round(confidence, 2))) if confidence is not None else None
    stmt = (
        pg_insert(Insight)
        .values(
            project_id=project_id,
            org_id=org_id,
            type=type,
            dedup_key=dedup_key,
            severity=severity,
            status="open",
            title=title,
            summary=summary,
            detail=detail,
            confidence=conf,
            predicted_for=predicted_for,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["project_id", "dedup_key"],
            set_={
                "severity": severity,
                "title": title,
                "summary": summary,
                "detail": detail,
                "confidence": conf,
                "predicted_for": predicted_for,
                "updated_at": now,
            },
        )
    )
    await session.execute(stmt)


async def resolve_unlisted(
    session: AsyncSession,
    project_id: uuid.UUID,
    active_keys: list[str],
    types: list[str],
) -> None:
    """Resolve open insights of `types` whose dedup_key the latest run did NOT
    re-emit — the predicted condition no longer holds.

    An empty `active_keys` means the analyser produced nothing this run, so
    every open insight of those types is resolved.
    """
    conds = [
        Insight.project_id == project_id,
        Insight.status == "open",
        Insight.type.in_(types),
    ]
    if active_keys:
        conds.append(Insight.dedup_key.notin_(active_keys))
    await session.execute(
        update(Insight)
        .where(*conds)
        .values(status="resolved", updated_at=datetime.now(tz=timezone.utc))
    )
