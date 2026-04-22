"""Spans API routes — list, detail, and feedback.

GET  /v1/projects/:id/spans          — cursor-paginated span list with filters
GET  /v1/spans/:span_id              — span detail + sibling spans for timeline
POST /v1/spans/:span_id/feedback     — store user feedback tag on a span

Cursor pagination design:
  - Cursor = base64(json({"ts": iso_str, "id": uuid_str}))
  - WHERE (created_at, id) < (cursor_ts, cursor_id) ORDER BY created_at DESC, id DESC
  - This avoids OFFSET and supports PostgreSQL partition pruning via created_at
  - Returns limit+1 rows; if len == limit+1, there are more results (pop the last)

Filter parameters (all optional, additive):
  model, provider, status, environment, user_id, session_id,
  trace_id, started_after, started_before, min_cost, max_cost, has_hallucination
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text

from whyllm_api.database import get_session_factory
from whyllm_api.models.user import User
from whyllm_api.schemas.spans import (
    SpanDetailResponse,
    SpanListItem,
    SpanListResponse,
    decode_cursor,
    encode_cursor,
)
from whyllm_api.services.auth_service import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["spans"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


async def _check_project_access(project_id: uuid.UUID, user: User) -> None:
    from sqlalchemy import select
    from whyllm_api.models.org_member import OrgMember
    from whyllm_api.models.project import Project

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Project.org_id).where(Project.id == project_id))
        row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    async with factory() as session:
        result = await session.execute(
            select(OrgMember.id).where(
                OrgMember.org_id == row[0], OrgMember.user_id == user.id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail={"error": "forbidden"})


@router.get("/v1/projects/{project_id}/spans", response_model=SpanListResponse)
async def list_spans(
    project_id: uuid.UUID,
    cursor: Optional[str] = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    # Filters
    model: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    environment: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    trace_id: Optional[uuid.UUID] = Query(default=None),
    started_after: Optional[datetime] = Query(default=None),
    started_before: Optional[datetime] = Query(default=None),
    min_cost: Optional[Decimal] = Query(default=None),
    max_cost: Optional[Decimal] = Query(default=None),
    has_hallucination: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> SpanListResponse:
    """List spans for a project with cursor pagination and optional filters."""
    await _check_project_access(project_id, current_user)

    # Build WHERE clauses dynamically
    conditions = ["project_id = :project_id"]
    params: dict = {"project_id": str(project_id)}

    # Cursor pagination — skip rows older than cursor position
    if cursor:
        try:
            cursor_ts, cursor_id = decode_cursor(cursor)
            conditions.append(
                "(created_at < :cursor_ts OR (created_at = :cursor_ts AND id < :cursor_id))"
            )
            params["cursor_ts"] = cursor_ts
            params["cursor_id"] = str(cursor_id)
        except ValueError:
            raise HTTPException(status_code=400, detail={"error": "invalid_cursor"})

    if model:
        conditions.append("model = :model")
        params["model"] = model

    if provider:
        conditions.append("provider = :provider")
        params["provider"] = provider

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if environment:
        conditions.append("environment = :environment")
        params["environment"] = environment

    if user_id:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id

    if session_id:
        conditions.append("session_id = :session_id")
        params["session_id"] = session_id

    if trace_id:
        conditions.append("trace_id = :trace_id")
        params["trace_id"] = str(trace_id)

    if started_after:
        conditions.append("started_at >= :started_after")
        params["started_after"] = started_after

    if started_before:
        conditions.append("started_at <= :started_before")
        params["started_before"] = started_before

    if min_cost is not None:
        conditions.append("cost_usd >= :min_cost")
        params["min_cost"] = float(min_cost)

    if max_cost is not None:
        conditions.append("cost_usd <= :max_cost")
        params["max_cost"] = float(max_cost)

    if has_hallucination is True:
        conditions.append("hallucination_score IS NOT NULL AND hallucination_score > 0.3")
    elif has_hallucination is False:
        conditions.append(
            "(hallucination_score IS NULL OR hallucination_score <= 0.3)"
        )

    where_clause = " AND ".join(conditions)
    fetch_limit = limit + 1  # fetch one extra to detect if there are more

    sql = text(f"""
        SELECT
            id, created_at, trace_id, project_id, provider, model, status,
            kind, environment, user_id, session_id,
            input_tokens, output_tokens, total_tokens,
            cost_usd, latency_ms, ttft_ms, hallucination_score,
            source, started_at
        FROM spans
        WHERE {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
    """)
    params["limit"] = fetch_limit

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(sql, params)
        rows = result.fetchall()

    has_more = len(rows) == fetch_limit
    if has_more:
        rows = rows[:-1]  # drop the sentinel row

    items = [
        SpanListItem(
            id=row[0],
            created_at=row[1],
            trace_id=row[2],
            project_id=row[3],
            provider=row[4],
            model=row[5],
            status=row[6],
            kind=row[7],
            environment=row[8],
            user_id=row[9],
            session_id=row[10],
            input_tokens=row[11],
            output_tokens=row[12],
            total_tokens=row[13],
            cost_usd=row[14],
            latency_ms=row[15],
            ttft_ms=row[16],
            hallucination_score=row[17],
            source=row[18],
            started_at=row[19],
        )
        for row in rows
    ]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    # Count hint — use a quick approximate count
    async with factory() as session:
        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM spans WHERE {where_clause}"),
            {k: v for k, v in params.items() if k != "limit"},
        )
        total_hint = count_result.scalar() or 0

    return SpanListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_hint=int(total_hint),
    )


@router.get("/v1/spans/{span_id}", response_model=SpanDetailResponse)
async def get_span(
    span_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> SpanDetailResponse:
    """Return detailed information for a single span, including sibling spans."""
    factory = get_session_factory()

    # Fetch the span (search across all partitions)
    async with factory() as session:
        result = await session.execute(
            text("""
                SELECT
                    id, created_at, trace_id, project_id, provider, model, status,
                    kind, environment, user_id, session_id, tags,
                    input_tokens, output_tokens, total_tokens,
                    cost_usd, latency_ms, ttft_ms,
                    hallucination_score, hallucination_flags,
                    source, started_at, ended_at, sdk_version,
                    parent_span_id, error_type, error_message,
                    request, response
                FROM spans
                WHERE id = :span_id
                LIMIT 1
            """),
            {"span_id": str(span_id)},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "span_not_found"})

    span_project_id = row[3]

    # Verify access to the span's project
    await _check_project_access(span_project_id, current_user)

    # Fetch sibling spans if trace_id present
    siblings: list[SpanListItem] = []
    trace_id = row[2]
    if trace_id:
        async with factory() as session:
            sib_result = await session.execute(
                text("""
                    SELECT
                        id, created_at, trace_id, project_id, provider, model, status,
                        kind, environment, user_id, session_id,
                        input_tokens, output_tokens, total_tokens,
                        cost_usd, latency_ms, ttft_ms, hallucination_score,
                        source, started_at
                    FROM spans
                    WHERE trace_id = :trace_id
                      AND project_id = :project_id
                      AND id != :span_id
                    ORDER BY started_at ASC NULLS LAST
                """),
                {
                    "trace_id": str(trace_id),
                    "project_id": str(span_project_id),
                    "span_id": str(span_id),
                },
            )
            for srow in sib_result.fetchall():
                siblings.append(SpanListItem(
                    id=srow[0], created_at=srow[1], trace_id=srow[2],
                    project_id=srow[3], provider=srow[4], model=srow[5],
                    status=srow[6], kind=srow[7], environment=srow[8],
                    user_id=srow[9], session_id=srow[10],
                    input_tokens=srow[11], output_tokens=srow[12], total_tokens=srow[13],
                    cost_usd=srow[14], latency_ms=srow[15], ttft_ms=srow[16],
                    hallucination_score=srow[17], source=srow[18], started_at=srow[19],
                ))

    return SpanDetailResponse(
        id=row[0],
        created_at=row[1],
        trace_id=row[2],
        project_id=row[3],
        provider=row[4],
        model=row[5],
        status=row[6],
        kind=row[7],
        environment=row[8],
        user_id=row[9],
        session_id=row[10],
        tags=row[11] or {},
        input_tokens=row[12],
        output_tokens=row[13],
        total_tokens=row[14],
        cost_usd=row[15],
        latency_ms=row[16],
        ttft_ms=row[17],
        hallucination_score=row[18],
        hallucination_flags=row[19],
        source=row[20],
        started_at=row[21],
        ended_at=row[22],
        sdk_version=row[23],
        parent_span_id=row[24],
        error_type=row[25],
        error_message=row[26],
        request=row[27],
        response=row[28],
        siblings=siblings,
    )


@router.post("/v1/spans/{span_id}/feedback", status_code=204, response_class=Response)
async def submit_feedback(
    span_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Store user feedback on a span as a tag.

    Body: {"feedback": "positive" | "negative" | "flagged", "note": "..."}
    Stored as: tags["_feedback"] = "positive", tags["_feedback_note"] = "..."
    """
    feedback = body.get("feedback")
    if feedback not in ("positive", "negative", "flagged"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_feedback", "message": "feedback must be positive, negative, or flagged"},
        )

    # Verify span exists and get project_id for access check
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT project_id, created_at FROM spans WHERE id = :id LIMIT 1"),
            {"id": str(span_id)},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "span_not_found"})

    await _check_project_access(row[0], current_user)

    note = str(body.get("note", ""))[:500]  # cap note length

    # Update tags using jsonb concatenation — partition-safe (created_at from row)
    tag_update: dict = {"_feedback": feedback}
    if note:
        tag_update["_feedback_note"] = note

    import json as _json
    async with factory() as session:
        await session.execute(
            text("""
                UPDATE spans
                SET tags = tags || CAST(:tag_json AS jsonb)
                WHERE id = :span_id
                  AND created_at = :created_at
            """),
            {
                "tag_json": _json.dumps(tag_update),
                "span_id": str(span_id),
                "created_at": row[1],
            },
        )
        await session.commit()
    return Response(status_code=204)
