"""Worksheet revision optimistic locking（R1 / ADR-027 §2）。"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.exceptions import ConflictError
from ddm_v2.models.v2.worksheet import MostWorksheet

logger = logging.getLogger(__name__)

REVISION_CONFLICT_CODE = "WORKSHEET_REVISION_CONFLICT"


class WorksheetRevisionConflict(ConflictError):
    """Stale write：base_revision 與 DB 不符。"""

    def __init__(self, *, worksheet_id: UUID | str, current_revision: int | None = None) -> None:
        detail = {"code": REVISION_CONFLICT_CODE}
        if current_revision is not None:
            detail["current_revision"] = str(current_revision)
        super().__init__(
            f"worksheet revision conflict：{worksheet_id}",
            detail=detail,
        )


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def content_hash_from_read(payload: dict[str, Any]) -> str:
    """自 read_worksheet 形狀（或等價）計算 content_hash。"""
    slim = {
        "allowance_percent": payload.get("allowance_percent"),
        "rows": [
            {
                "wi_row_id": r.get("wi_row_id"),
                "seq_no": r.get("seq_no"),
                "hand": r.get("hand"),
                "sub_activity": r.get("sub_activity"),
                "key_parts": r.get("key_parts"),
                "object_vocab_id": r.get("object_vocab_id"),
                "from_vocab_id": r.get("from_vocab_id"),
                "to_vocab_id": r.get("to_vocab_id"),
                "tool_vocab_id": r.get("tool_vocab_id"),
                "frequency": r.get("frequency"),
                "simo_group_id": r.get("simo_group_id"),
                "cycle": (r.get("cycle") or {}).get("slot_inputs"),
                "level": r.get("level"),
            }
            for r in (payload.get("rows") or [])
        ],
    }
    return sha256_hex(canonical_json(slim))


async def bump_worksheet_revision(
    session: AsyncSession,
    *,
    worksheet_id: UUID,
    base_revision: int | None,
    edited_by: str | None,
) -> int:
    """在任何內容 mutation 前呼叫。

    - ``base_revision`` 有值：CAS ``UPDATE ... WHERE revision_no=:base``；0 列 → 409。
    - ``None``：legacy（過渡期）無條件 +1 並記 warning（規格允許直至前端必填）。
    回傳 bump 後的 ``revision_no``。

    注意：一律 ``expire`` ORM 快取，避免後續 flush 把舊 revision_no 蓋回 DB。
    """
    now = datetime.now(timezone.utc)
    if base_revision is None:
        logger.warning(
            "worksheet %s save without base_revision (legacy last-write path)",
            worksheet_id,
        )
        await session.execute(
            update(MostWorksheet)
            .where(MostWorksheet.id == worksheet_id)
            .values(
                revision_no=MostWorksheet.revision_no + 1,
                last_edited_by=edited_by,
                last_edited_at=now,
            )
        )
        await session.flush()
        session.expire_all()
        ws = await session.get(MostWorksheet, worksheet_id)
        assert ws is not None
        return int(ws.revision_no)

    sql = text(
        """
        UPDATE most_worksheets
        SET revision_no = revision_no + 1,
            last_edited_by = :edited_by,
            last_edited_at = :edited_at
        WHERE id = :id AND revision_no = :base
        RETURNING revision_no
        """
    )
    row = (
        await session.execute(
            sql,
            {
                "id": worksheet_id,
                "base": base_revision,
                "edited_by": edited_by,
                "edited_at": now,
            },
        )
    ).first()
    if row is None:
        session.expire_all()
        ws = await session.get(MostWorksheet, worksheet_id)
        current = int(ws.revision_no) if ws is not None else None
        raise WorksheetRevisionConflict(
            worksheet_id=worksheet_id, current_revision=current
        )
    new_rev = int(row[0])
    await session.flush()
    session.expire_all()
    return new_rev


async def set_content_hash(
    session: AsyncSession, *, worksheet_id: UUID, content_hash: str
) -> None:
    await session.execute(
        update(MostWorksheet)
        .where(MostWorksheet.id == worksheet_id)
        .values(content_hash=content_hash)
    )
