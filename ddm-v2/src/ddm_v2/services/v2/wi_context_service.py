"""wi_row_contexts CRUD（R3a）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.exceptions import ConflictError, NotFoundError, ValidationError
from ddm_v2.models.v2.wi_context import WiRowContext
from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion, WiRow
from ddm_v2.schemas.v2.wi_context import (
    context_hash_for,
    validate_context_payload,
)


async def _require_editable_row(session: AsyncSession, wi_row_id: uuid.UUID) -> WiRow:
    wr = await session.get(WiRow, wi_row_id)
    if wr is None:
        raise NotFoundError(f"wi_row 不存在：{wi_row_id}")
    ws = await session.get(MostWorksheet, wr.worksheet_id)
    if ws is None:
        raise NotFoundError(f"worksheet 不存在：{wr.worksheet_id}")
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv is not None and pv.status != "draft":
        raise ConflictError(
            f"版本狀態為 {pv.status}，已凍結不可改 context（請另存新檔）",
            detail={"code": "VERSION_PUBLISHED"},
        )
    return wr


def _out(row: WiRowContext) -> dict[str, Any]:
    return {
        "id": row.id,
        "wi_row_id": row.wi_row_id,
        "schema_version": row.schema_version,
        "context_data": row.context_data,
        "context_hash": row.context_hash,
        "source": row.source,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def get_context(session: AsyncSession, wi_row_id: uuid.UUID) -> dict[str, Any]:
    wr = await session.get(WiRow, wi_row_id)
    if wr is None:
        raise NotFoundError(f"wi_row 不存在：{wi_row_id}")
    row = (
        await session.execute(
            select(WiRowContext).where(WiRowContext.wi_row_id == wi_row_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"wi_row context 不存在：{wi_row_id}")
    return _out(row)


async def upsert_context(
    session: AsyncSession,
    wi_row_id: uuid.UUID,
    *,
    schema_version: str,
    context_data: dict[str, Any],
    source: str,
    actor: str | None,
) -> dict[str, Any]:
    await _require_editable_row(session, wi_row_id)
    try:
        normalized = validate_context_payload(
            schema_version=schema_version, context_data=context_data or {}
        )
    except ValueError as e:
        raise ValidationError(str(e), detail={"code": "WI_CONTEXT_INVALID"}) from e
    except Exception as e:
        # Pydantic ValidationError 等 → 422
        raise ValidationError(str(e), detail={"code": "WI_CONTEXT_INVALID"}) from e

    ch = context_hash_for(normalized)
    existing = (
        await session.execute(
            select(WiRowContext).where(WiRowContext.wi_row_id == wi_row_id)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing is None:
        row = WiRowContext(
            id=uuid.uuid4(),
            wi_row_id=wi_row_id,
            schema_version=schema_version,
            context_data=normalized,
            context_hash=ch,
            source=source,
            created_by=actor,
            updated_by=actor,
        )
        session.add(row)
    else:
        existing.schema_version = schema_version
        existing.context_data = normalized
        existing.context_hash = ch
        existing.source = source
        existing.updated_by = actor
        existing.updated_at = now
        row = existing
    await session.flush()
    return _out(row)


async def delete_context(session: AsyncSession, wi_row_id: uuid.UUID) -> None:
    await _require_editable_row(session, wi_row_id)
    row = (
        await session.execute(
            select(WiRowContext).where(WiRowContext.wi_row_id == wi_row_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"wi_row context 不存在：{wi_row_id}")
    await session.delete(row)
    await session.flush()
