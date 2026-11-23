"""工作區編輯區服務（ADR-038 D2／D3，W1）。

編輯區是工時表的草稿層：人工、單句 AI、整份上傳的產出都先進這裡；「確認」只是標記，
`commit_drafts`（寫入工時表）才把已確認的列一次**追加到工時表最後面**。

寫入走既有的存檔元件，沒有第二套計算或寫入：
- 版本鎖：`bump_worksheet_revision`（CAS，ADR-027 §2）；不符 → 409，草稿維持已確認。
- TMU：`compute_rows_for_save`（與整份存檔、LB 預覽同一套），以**目標工時表的規則版本**重算，不沿用任何預覽值
  （ADR-037 D3：預覽不是可接受的依據；ADR-038 D3：寫入前重算）。
- 落盤：`persist_computed_rows`＋`finalize_content_change`（與整份存檔共用；content hash、level 驗證、outbox）。
- level 欄位留空，由人事後標註（ADR-037 D5）；不支援插入中間，一律追加到表尾（Howard 2026-11-23）。

只在**草稿版本**的工序上可以新增、修改、確認、寫入；讀取不限。
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.import_staging import ImportRow
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.wi_draft import WiDraftRow
from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion, WiRow
from ddm_v2.schemas.v2.wi_draft import WiDraftContent, WiDraftCreateItem
from ddm_v2.schemas.v2.worksheet import LevelFieldsIn, WiRowSaveIn, WorksheetSaveIn
from ddm_v2.services.v2.rule_set_service import get_active_rule_set_code
from ddm_v2.services.v2.worksheet_revision import bump_worksheet_revision
from ddm_v2.services.v2.worksheet_service import (
    NotEditable,
    RowOrigin,
    RowSequenceError,
    RuleSetNotFound,
    WorksheetNotFound,
    compute_rows_for_save,
    finalize_content_change,
    persist_computed_rows,
)

logger = logging.getLogger(__name__)

# 一份工時表的編輯區最多幾列（含已寫入的紀錄）。整份上傳上限 1000 列 Excel、一句通常拆 2–3 個 motion，
# 5000 留了餘裕；寫入一次處理所有已確認的列，所以總數上限也是單次寫入的上限（擋住用大量草稿讓寫入超時）。
MAX_DRAFTS_PER_WORKSHEET = 5000

# 草稿來源 → 寫入工時表後的 `wi_rows.provenance`。rule_based（含 AI 降級）是 MOST 自己的解析、經人確認，
# 和人工建的列同等看待；只有外部 AI 的產出標 ai_external（ADR-037 D5）。
_PROVENANCE_BY_SOURCE = {
    "manual": "manual",
    "rule_based": "manual",
    "ai_service": "ai_external",
    "imported": "imported",
}


class DraftNotFound(Exception):
    pass


class DraftStateConflict(Exception):
    """草稿的狀態不允許這個動作（例：修改或刪除已寫入的草稿）。"""


class NothingToCommit(Exception):
    pass


class TooManyDrafts(Exception):
    pass


class SourceNotCommittable(Exception):
    """這個來源的草稿目前不能寫入（外部 AI 草稿要等 W3 補上 engine_gate 檢查，ADR-037 D3）。"""


class DraftContentInvalid(Exception):
    """存著的草稿內容驗證不過（例：之後 schema 加嚴）。帶 draft_id 讓使用者知道是哪一列。"""

    def __init__(self, draft_id: uuid.UUID, message: str) -> None:
        super().__init__(message)
        self.draft_id = draft_id


class DraftComputeError(Exception):
    """寫入時引擎算不出某一列。帶 draft_id（不是寫入時才產生的 wi_row id），使用者才找得到是哪一列。"""

    def __init__(self, draft_id: uuid.UUID, exc: Exception) -> None:
        super().__init__(str(exc))
        self.draft_id = draft_id
        self.cause = exc


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_worksheet(session: AsyncSession, worksheet_id: uuid.UUID) -> MostWorksheet:
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    return ws


async def _require_editable(session: AsyncSession, ws: MostWorksheet) -> None:
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv is not None and pv.status != "draft":
        raise NotEditable(f"版本狀態為 {pv.status}，已凍結不可編輯（請另存新檔）")


async def _get_draft(session: AsyncSession, draft_id: uuid.UUID, *, for_update: bool = False) -> WiDraftRow:
    stmt = select(WiDraftRow).where(WiDraftRow.id == draft_id)
    if for_update:
        stmt = stmt.with_for_update()
    draft = (await session.execute(stmt)).scalar_one_or_none()
    if draft is None:
        raise DraftNotFound(str(draft_id))
    return draft


async def list_drafts(session: AsyncSession, worksheet_id: uuid.UUID) -> list[WiDraftRow]:
    await _get_worksheet(session, worksheet_id)
    return list(
        (
            await session.execute(
                select(WiDraftRow)
                .where(WiDraftRow.worksheet_id == worksheet_id)
                .order_by(WiDraftRow.sort_order, WiDraftRow.order_in_group, WiDraftRow.created_at)
            )
        ).scalars()
    )


async def add_drafts(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    items: Sequence[WiDraftCreateItem],
    *,
    source: str,
    actor: str,
    ai_parse_run_id: uuid.UUID | None = None,
    import_row_ids: Sequence[uuid.UUID | None] | None = None,
    ai_candidates: Sequence[dict[str, Any] | None] | None = None,
) -> list[WiDraftRow]:
    """新增草稿列。手動路由只傳 `source='manual'`；AI／匯入（W3）由後端呼叫並帶出處。"""
    if source not in _PROVENANCE_BY_SOURCE:
        raise ValueError(f"unknown draft source: {source}")
    if import_row_ids is not None and len(import_row_ids) != len(items):
        raise ValueError("import_row_ids must align with items")
    if ai_candidates is not None and len(ai_candidates) != len(items):
        raise ValueError("ai_candidates must align with items")
    ws = await _get_worksheet(session, worksheet_id)
    await _require_editable(session, ws)
    # 鎖住工時表列：同一份工時表的並行新增依序配 sort_order，總數上限也不會被並行繞過
    await session.execute(select(MostWorksheet.id).where(MostWorksheet.id == worksheet_id).with_for_update())
    existing = (
        await session.execute(select(func.count()).select_from(WiDraftRow).where(WiDraftRow.worksheet_id == worksheet_id))
    ).scalar_one()
    if existing + len(items) > MAX_DRAFTS_PER_WORKSHEET:
        raise TooManyDrafts(f"編輯區最多 {MAX_DRAFTS_PER_WORKSHEET} 列（目前 {existing}，本次 {len(items)}）")

    next_sort = (
        await session.execute(
            select(func.coalesce(func.max(WiDraftRow.sort_order), 0)).where(WiDraftRow.worksheet_id == worksheet_id)
        )
    ).scalar_one()
    now = _now()
    out: list[WiDraftRow] = []
    for i, item in enumerate(items):
        next_sort += 1
        draft = WiDraftRow(
            id=uuid.uuid4(),
            worksheet_id=worksheet_id,
            group_key=item.group_key or str(uuid.uuid4()),
            order_in_group=item.order_in_group,
            sort_order=next_sort,
            source=source,
            status="pending",
            content=item.content.model_dump(mode="json"),
            ai_candidates=ai_candidates[i] if ai_candidates is not None else None,
            ai_parse_run_id=ai_parse_run_id,
            import_row_id=import_row_ids[i] if import_row_ids is not None else None,
            source_revision=int(ws.revision_no or 1),
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        session.add(draft)
        out.append(draft)
    await session.flush()
    return out


async def patch_draft(
    session: AsyncSession, draft_id: uuid.UUID, content: WiDraftContent, *, actor: str
) -> WiDraftRow:
    draft = await _get_draft(session, draft_id, for_update=True)
    if draft.status == "committed":
        raise DraftStateConflict("已寫入工時表的草稿不能修改")
    ws = await _get_worksheet(session, draft.worksheet_id)
    await _require_editable(session, ws)
    draft.content = content.model_dump(mode="json")
    # 改了內容就要重新確認
    draft.status = "pending"
    draft.confirmed_by = None
    draft.confirmed_at = None
    draft.updated_by = actor
    draft.updated_at = _now()
    await session.flush()
    return draft


async def delete_draft(session: AsyncSession, draft_id: uuid.UUID, *, actor: str) -> None:
    """刪除尚未寫入的草稿。pending／confirmed 的草稿還沒進工時表，所以不寫稽核表，只留伺服器 log（誰刪了誰建的哪一列）。"""
    draft = await _get_draft(session, draft_id, for_update=True)
    if draft.status == "committed":
        raise DraftStateConflict("已寫入工時表的草稿是紀錄，不能刪除")
    ws = await _get_worksheet(session, draft.worksheet_id)
    await _require_editable(session, ws)
    logger.info(
        "worksheet draft deleted: draft=%s worksheet=%s status=%s created_by=%s deleted_by=%s",
        draft.id, draft.worksheet_id, draft.status, draft.created_by, actor,
    )
    await session.delete(draft)
    await session.flush()


async def confirm_drafts(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    *,
    draft_ids: Sequence[uuid.UUID] | None,
    group_key: str | None,
    actor: str,
) -> list[WiDraftRow]:
    """確認一些列或一整組（ADR-038 D2 整組確認）。已確認的列維持不變；已寫入的列不能再確認。"""
    ws = await _get_worksheet(session, worksheet_id)
    await _require_editable(session, ws)
    # 鎖定順序與 commit_drafts 相同，避免兩邊交錯取鎖而死鎖
    stmt = (
        select(WiDraftRow)
        .where(WiDraftRow.worksheet_id == worksheet_id)
        .order_by(WiDraftRow.sort_order, WiDraftRow.order_in_group, WiDraftRow.created_at, WiDraftRow.id)
        .with_for_update()
    )
    if draft_ids is not None:
        stmt = stmt.where(WiDraftRow.id.in_(list(draft_ids)))
    else:
        stmt = stmt.where(WiDraftRow.group_key == group_key)
    drafts = list((await session.execute(stmt)).scalars())
    if draft_ids is not None:
        missing = set(draft_ids) - {d.id for d in drafts}
        if missing:
            raise DraftNotFound(", ".join(sorted(str(m) for m in missing)))
    elif not drafts:
        raise DraftNotFound(f"group_key={group_key}")
    committed = [d for d in drafts if d.status == "committed"]
    if committed:
        raise DraftStateConflict(f"已寫入工時表的草稿不能再確認：{sorted(str(d.id) for d in committed)}")
    now = _now()
    for d in drafts:
        if d.status == "pending":
            d.status = "confirmed"
            d.confirmed_by = actor
            d.confirmed_at = now
            d.updated_by = actor
            d.updated_at = now
    await session.flush()
    return drafts


async def _target_rule_set_code(session: AsyncSession, ws: MostWorksheet) -> str:
    """寫入用目標工時表的規則版本（ADR-037 D3：目標 worksheet 的 rule-set，不是「當前 active」）。"""
    if ws.default_rule_set_id is not None:
        rs = await session.get(RuleSet, ws.default_rule_set_id)
        if rs is None:
            raise RuleSetNotFound(str(ws.default_rule_set_id))
        return rs.code
    return await get_active_rule_set_code(session)


async def commit_drafts(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    *,
    base_revision: int,
    actor: str,
) -> tuple[dict[str, Any], list[WiDraftRow]]:
    """把所有已確認的草稿追加到工時表最後面（ADR-038 D3「寫入工時表」）。回傳 (工時表讀取結果, 寫入的草稿)。

    同一交易內：CAS revision → 以目標規則版本重算 → 寫 wi_row／cycle／level → 草稿標 committed 並記寫入的列 id。
    任何一步失敗都整個回滾（呼叫端的 session）。
    """
    ws = await _get_worksheet(session, worksheet_id)
    await _require_editable(session, ws)
    # 先 CAS 版本鎖、再取草稿：兩個同時按「寫入」的請求，第二個會拿到 409（版本衝突）而不是「沒有可寫入的列」。
    # 失敗（含後面的 NothingToCommit）由呼叫端整筆回滾，版本號不會白白增加。
    await bump_worksheet_revision(
        session, worksheet_id=worksheet_id, base_revision=base_revision, edited_by=actor
    )
    drafts = list(
        (
            await session.execute(
                select(WiDraftRow)
                .where(WiDraftRow.worksheet_id == worksheet_id, WiDraftRow.status == "confirmed")
                .order_by(WiDraftRow.sort_order, WiDraftRow.order_in_group, WiDraftRow.created_at, WiDraftRow.id)
                .with_for_update()
            )
        ).scalars()
    )
    if not drafts:
        raise NothingToCommit(str(worksheet_id))
    ai = [d for d in drafts if d.source == "ai_service"]
    if ai:
        # Fail-Fast：ADR-037 D3 要求可接受的 AI motion 還要過 engine_gate（無 high 級問題），寫入路徑尚未實作（W3）。
        # W3 之前不讓任何外部 AI 草稿進工時表，即使有人從後端灌進來。
        raise SourceNotCommittable(f"外部 AI 草稿暫時不能寫入（W3 前）：{sorted(str(d.id) for d in ai)}")

    code = await _target_rule_set_code(session, ws)
    next_seq = (
        await session.execute(
            select(func.coalesce(func.max(WiRow.seq_no), 0)).where(WiRow.worksheet_id == worksheet_id)
        )
    ).scalar_one()

    # 匯入列的出處：import_row → excel_imports.id
    import_ids: dict[uuid.UUID, uuid.UUID] = {}
    row_ids = [d.import_row_id for d in drafts if d.import_row_id is not None]
    if row_ids:
        for row in (await session.execute(select(ImportRow.id, ImportRow.import_id).where(ImportRow.id.in_(row_ids)))).all():
            import_ids[row.id] = row.import_id

    new_rows: list[WiRowSaveIn] = []
    origin_by_row: dict[uuid.UUID, RowOrigin] = {}
    draft_by_row: dict[uuid.UUID, uuid.UUID] = {}
    for i, d in enumerate(drafts, start=1):
        try:
            content = WiDraftContent.model_validate(d.content)
        except PydanticValidationError as exc:
            raise DraftContentInvalid(d.id, f"草稿內容不合格：{exc.error_count()} 個錯誤") from exc
        cycle = content.cycle.model_copy(update={"rule_set_code": code})
        row_id = uuid.uuid4()
        new_rows.append(
            WiRowSaveIn(
                id=row_id,
                seq_no=next_seq + i,
                sub_activity=content.sub_activity,
                key_parts=content.key_parts,
                hand=content.hand,
                object_vocab_id=content.object_vocab_id,
                from_vocab_id=content.from_vocab_id,
                to_vocab_id=content.to_vocab_id,
                tool_vocab_id=content.tool_vocab_id,
                frequency=content.frequency,
                narrative=content.narrative,
                wi_group=content.wi_group,
                cycle=cycle,
                level=LevelFieldsIn(),
            )
        )
        origin_by_row[row_id] = RowOrigin(
            provenance=_PROVENANCE_BY_SOURCE[d.source],
            source_import_id=import_ids.get(d.import_row_id) if d.import_row_id else None,
        )
        draft_by_row[row_id] = d.id
        d.committed_wi_row_id = row_id

    try:
        computed, ctx = await compute_rows_for_save(session, ws, WorksheetSaveIn(rows=new_rows))
    except RowSequenceError as exc:
        raise DraftComputeError(draft_by_row.get(exc.row_id, exc.row_id), exc) from exc
    persist_computed_rows(
        session,
        worksheet_id=worksheet_id,
        computed=computed,
        rs_row=ctx.rs_row,
        origin_of=lambda r: origin_by_row[r.id],
    )
    now = _now()
    for d in drafts:
        d.status = "committed"
        d.committed_by = actor
        d.committed_at = now
        d.updated_by = actor
        d.updated_at = now
    await session.flush()
    out = await finalize_content_change(session, ws, edited_by=actor)
    return out, drafts
