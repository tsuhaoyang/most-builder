"""Transactional outbox 服務（R3b）。

enqueue 必須與業務寫入同一 session／transaction；本模組不自行 commit。
Publisher worker 未上線前僅提供 claim／mark helpers 供測試與之後 worker。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.outbox import OutboxEvent

EVENT_REVIEW_RECORDED = "wi_ai.review_recorded"
EVENT_WORKSHEET_SAVED = "worksheet.content_saved"

SCHEMA_REVIEW_V1 = "wi_ai.review_recorded.v1"
SCHEMA_WORKSHEET_SAVED_V1 = "worksheet.content_saved.v1"

# R0 未定核可前：claim helper 用保守上限（worker 上線前不無限 retry）
DEFAULT_MAX_ATTEMPTS = 8


async def _next_event_no(
    session: AsyncSession, *, aggregate_type: str, aggregate_id: uuid.UUID
) -> int:
    q = await session.execute(
        select(func.coalesce(func.max(OutboxEvent.event_no), 0)).where(
            OutboxEvent.aggregate_type == aggregate_type,
            OutboxEvent.aggregate_id == aggregate_id,
        )
    )
    return int(q.scalar_one()) + 1


async def enqueue_outbox(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    aggregate_revision: int | None,
    payload_schema_version: str,
    payload_json: dict[str, Any],
) -> OutboxEvent:
    """同 session flush；不 commit。payload 僅放 reference／最小必要欄位。"""
    event_no = await _next_event_no(
        session, aggregate_type=aggregate_type, aggregate_id=aggregate_id
    )
    row = OutboxEvent(
        id=uuid.uuid4(),
        event_no=event_no,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_revision=aggregate_revision,
        payload_schema_version=payload_schema_version,
        payload_json=payload_json,
        status="pending",
        attempt_count=0,
        next_attempt_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


async def enqueue_review_recorded(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    review_event_ids: list[str],
    review_event_types: list[str],
    worksheet_id: uuid.UUID | None,
    worksheet_revision: int | None,
) -> OutboxEvent:
    if worksheet_id is not None:
        aggregate_type, aggregate_id = "worksheet", worksheet_id
        rev = worksheet_revision
    else:
        aggregate_type, aggregate_id = "ai_parse_run", run_id
        rev = None
    return await enqueue_outbox(
        session,
        event_type=EVENT_REVIEW_RECORDED,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_revision=rev,
        payload_schema_version=SCHEMA_REVIEW_V1,
        payload_json={
            "run_id": str(run_id),
            "review_event_ids": review_event_ids,
            "review_event_types": review_event_types,
            "worksheet_id": str(worksheet_id) if worksheet_id else None,
            "worksheet_revision": worksheet_revision,
        },
    )


async def enqueue_worksheet_saved(
    session: AsyncSession,
    *,
    worksheet_id: uuid.UUID,
    revision_no: int,
    content_hash: str | None,
    edited_by: str | None,
) -> OutboxEvent:
    return await enqueue_outbox(
        session,
        event_type=EVENT_WORKSHEET_SAVED,
        aggregate_type="worksheet",
        aggregate_id=worksheet_id,
        aggregate_revision=revision_no,
        payload_schema_version=SCHEMA_WORKSHEET_SAVED_V1,
        payload_json={
            "worksheet_id": str(worksheet_id),
            "revision_no": revision_no,
            "content_hash": content_hash,
            "edited_by": edited_by,
        },
    )


async def claim_pending(
    session: AsyncSession,
    *,
    limit: int = 10,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> list[OutboxEvent]:
    """SKIP LOCKED 領取 pending（且 next_attempt_at 已到期）。"""
    now = datetime.now(timezone.utc)
    # 先把超過 max_attempts 的 pending 升成 dead_letter
    await session.execute(
        update(OutboxEvent)
        .where(
            OutboxEvent.status == "pending",
            OutboxEvent.attempt_count >= max_attempts,
        )
        .values(status="dead_letter", last_error="max_attempts exceeded")
    )
    await session.flush()

    result = await session.execute(
        text(
            """
            SELECT id FROM outbox_events
            WHERE status = 'pending'
              AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT :lim
            """
        ),
        {"now": now, "lim": limit},
    )
    ids = [row[0] for row in result.fetchall()]
    if not ids:
        return []
    by_id = {
        r.id: r
        for r in (
            await session.execute(select(OutboxEvent).where(OutboxEvent.id.in_(ids)))
        ).scalars().all()
    }
    # 維持 SKIP LOCKED 選出順序（created_at ASC）
    return [by_id[i] for i in ids if i in by_id]


async def mark_published(session: AsyncSession, event_id: uuid.UUID) -> None:
    row = await session.get(OutboxEvent, event_id)
    if row is None:
        return
    row.status = "published"
    row.published_at = datetime.now(timezone.utc)
    row.last_error = None
    await session.flush()


async def mark_failed(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    error: str,
    backoff_seconds: int = 30,
) -> None:
    row = await session.get(OutboxEvent, event_id)
    if row is None:
        return
    row.attempt_count = int(row.attempt_count or 0) + 1
    row.last_error = error[:2000]
    row.status = "pending"
    row.next_attempt_at = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + backoff_seconds,
        tz=timezone.utc,
    )
    await session.flush()
