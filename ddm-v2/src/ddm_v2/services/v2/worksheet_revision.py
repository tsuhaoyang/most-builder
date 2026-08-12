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


#: 本模組用 Core/raw UPDATE 直接改的欄位；改動 UPDATE 的 SET 清單時必須同步這裡，
#: 否則 identity map 會留下 stale 值（見 :func:`_resync_worksheet`）。
_BUMP_COLUMNS = ("revision_no", "last_edited_by", "last_edited_at")
_HASH_COLUMNS = ("content_hash",)


async def _resync_worksheet(
    session: AsyncSession, worksheet_id: UUID, columns: tuple[str, ...]
) -> MostWorksheet | None:
    """把 identity map 裡那顆 ``MostWorksheet`` 的 ``columns`` 重讀成 DB 真值。

    本模組一律用 Core/raw UPDATE 改 ``most_worksheets``，ORM 不會知道；而
    ``read_worksheet()`` 回應裡的 ``revision_no``/``content_hash`` 正是直接從這顆
    ORM 物件讀出來的，不同步就會回舊值（client 拿舊 revision 當下次的
    ``base_revision`` → 永遠 409）。

    為什麼**不是** ``session.expire_all()``：它會失效 session 內**所有**物件；呼叫端
    手上的 ORM 物件（wi_set 迴圈裡的 item、from-module 的 ws、import 的 rec）下一次
    屬性存取就變成 lazy load，在 AsyncSession 下即 ``MissingGreenlet``。
    為什麼**不是** ``session.expire(ws)``：expire 只是把值標成「下次再載」，async 下
    那個「下次」一樣是同步 IO——只是把雷從別人腳下移到自己腳下。必須在這裡
    （還在 await 內）就把值讀回來。
    為什麼**不是**整顆 ``refresh()``／``get(..., populate_existing=True)``：那會連已載入的
    relationship（``rows``/``process_version``）一起 expire，等於換個欄位埋同一顆雷。
    """
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        return None
    await session.refresh(ws, attribute_names=list(columns))
    return ws


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

    注意：bump 走 Core/raw UPDATE，一律以 :func:`_resync_worksheet` 把 identity map
    裡那**一顆** worksheet 對齊 DB 真值（不得用 ``expire_all()`` 掃全 session）。
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
        ws = await _resync_worksheet(session, worksheet_id, _BUMP_COLUMNS)
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
        # CAS 0 列：identity map 可能還握著 client 當初讀到的舊 revision，
        # 必須重讀才拿得到真正的 current_revision 回給 409。
        ws = await _resync_worksheet(session, worksheet_id, ("revision_no",))
        current = int(ws.revision_no) if ws is not None else None
        raise WorksheetRevisionConflict(
            worksheet_id=worksheet_id, current_revision=current
        )
    new_rev = int(row[0])
    await session.flush()
    await _resync_worksheet(session, worksheet_id, _BUMP_COLUMNS)
    return new_rev


async def set_content_hash(
    session: AsyncSession, *, worksheet_id: UUID, content_hash: str
) -> None:
    """寫入 content_hash（Core UPDATE），並把 identity map 對齊。

    與 bump 同一個失效模式：Core UPDATE 不會反映到已載入的 ORM 物件，而
    ``read_worksheet()`` 是直接讀 ``ws.content_hash`` 的——同一個 session 內
    只要再讀一次工序表（例如 wi_set 實體化迴圈的第 2 圈）就會拿到舊 hash。
    """
    await session.execute(
        update(MostWorksheet)
        .where(MostWorksheet.id == worksheet_id)
        .values(content_hash=content_hash)
    )
    await _resync_worksheet(session, worksheet_id, _HASH_COLUMNS)
