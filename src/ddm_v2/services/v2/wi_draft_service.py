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
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.import_staging import ImportRow
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.wi_draft import WiDraftRow
from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion, WiRow
from ddm_v2.nlp.contracts import CycleDraft, ParseRunResult
from ddm_v2.schemas.v2.wi_draft import WiDraftContent, WiDraftCreateItem
from ddm_v2.schemas.v2.worksheet import LevelFieldsIn, WiRowSaveIn, WorksheetSaveIn
from ddm_v2.services.v2.rule_set_service import get_active_rule_set_code
from ddm_v2.services.v2.worksheet_revision import bump_worksheet_revision, canonical_json, sha256_hex
from ddm_v2.services.v2.worksheet_service import (
    NotEditable,
    RowOrigin,
    RowSequenceError,
    RuleSetNotFound,
    WorksheetNotFound,
    assert_version_still_draft,
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


class DraftIncomplete(Exception):
    """解析出的草稿不完整（或引擎算不過）且沒有人補過 cycle，不能確認或寫入（ADR-037 D3）。"""

    def __init__(self, draft_ids: Sequence[uuid.UUID]) -> None:
        self.draft_ids = sorted(draft_ids, key=str)
        super().__init__(f"有 {len(self.draft_ids)} 列草稿解析不完整，請先補齊")


class DraftsStale(Exception):
    """已確認的草稿過期（ADR-037 D5）：draft_id → 原因。"""

    def __init__(self, reasons: dict[uuid.UUID, str]) -> None:
        self.reasons = reasons
        super().__init__(f"{len(reasons)} 列草稿已過期")


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


def _provenance_for(d: WiDraftRow) -> str:
    """寫入後的 `wi_rows.provenance`：外部 AI 一律 ai_external；其餘來自 Excel 列的標 imported（沿用匯入的語意）。"""
    if d.source == "ai_service":
        return "ai_external"
    if d.import_row_id is not None:
        return "imported"
    return _PROVENANCE_BY_SOURCE[d.source]


def cycle_hash(cycle: dict[str, Any]) -> str:
    """草稿 cycle 的雜湊（不含 rule_set_code：寫入時一律換成工時表的版本）。判斷人有沒有補過解析結果。"""
    return sha256_hex(canonical_json({k: v for k, v in (cycle or {}).items() if k != "rule_set_code"}))


def is_unfilled_incomplete(d: WiDraftRow) -> bool:
    """解析時不完整、而且 cycle 到現在還沒被人改過。人工草稿（沒有 parse_snapshot）一律 False。"""
    snap = d.parse_snapshot
    if not snap or snap.get("complete"):
        return False
    return cycle_hash((d.content or {}).get("cycle") or {}) == snap.get("cycle_hash")


async def _current_import_hashes(
    session: AsyncSession, row_ids: Sequence[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    ids = [r for r in row_ids if r is not None]
    if not ids:
        return {}
    rows = (await session.execute(select(ImportRow.id, ImportRow.input_hash).where(ImportRow.id.in_(ids)))).all()
    return {r.id: r.input_hash for r in rows}


async def detect_stale(
    session: AsyncSession, ws: MostWorksheet, drafts: Sequence[WiDraftRow]
) -> dict[uuid.UUID, str]:
    """ADR-037 D5 的過期條件中，草稿層要判斷的兩個（版本非草稿、工時表被刪、revision 鎖另外處理）：
    - 工時表改綁規則版本（`default_rule_set_id` 與草稿的基準不同）；
    - 來源 Excel 列的輸入變了或被刪了（輸入雜湊不同）。
    一般存檔（revision 遞增）不算過期：草稿追加到表尾，不引用既有列。
    """
    hashes = await _current_import_hashes(session, [d.import_row_id for d in drafts])
    out: dict[uuid.UUID, str] = {}
    for d in drafts:
        if d.source_rule_set_id != ws.default_rule_set_id:
            out[d.id] = "rule_set_changed"
            continue
        want = (d.parse_snapshot or {}).get("import_input_hash")
        if want is not None and (d.import_row_id is None or hashes.get(d.import_row_id) != want):
            out[d.id] = "import_row_changed"
    return out


async def mark_stale_drafts(session: AsyncSession, worksheet_id: uuid.UUID, *, actor: str) -> dict[uuid.UUID, str]:
    """把已確認但過期的草稿退回待確認並記原因（寫入失敗後另開交易呼叫）。鎖順序同 commit：先工時表、再草稿。"""
    await session.execute(select(MostWorksheet.id).where(MostWorksheet.id == worksheet_id).with_for_update())
    ws = await _get_worksheet(session, worksheet_id)
    await session.refresh(ws)
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
    stale = await detect_stale(session, ws, drafts)
    now = _now()
    for d in drafts:
        if d.id in stale:
            d.status = "pending"
            d.stale_reason = stale[d.id]
            d.confirmed_by = None
            d.confirmed_at = None
            d.updated_by = actor
            d.updated_at = now
    await session.flush()
    return stale


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


async def assert_room_for(session: AsyncSession, worksheet_id: uuid.UUID, n: int = 1) -> None:
    """編輯區還放得下 n 列（先擋，免得 AI 回來才發現滿了、額度白花）。寫入時 add_drafts 會在鎖內再檢查一次。"""
    existing = (
        await session.execute(select(func.count()).select_from(WiDraftRow).where(WiDraftRow.worksheet_id == worksheet_id))
    ).scalar_one()
    if existing + n > MAX_DRAFTS_PER_WORKSHEET:
        raise TooManyDrafts(f"編輯區最多 {MAX_DRAFTS_PER_WORKSHEET} 列（目前 {existing}）")


async def get_editable_worksheet(session: AsyncSession, worksheet_id: uuid.UUID) -> MostWorksheet:
    """取工時表並確認它的工序版本仍是草稿（先擋，免得為一份不能寫的工時表花 AI 額度）。"""
    ws = await _get_worksheet(session, worksheet_id)
    await _require_editable(session, ws)
    return ws


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
    parse_snapshots: Sequence[dict[str, Any] | None] | None = None,
) -> list[WiDraftRow]:
    """新增草稿列。手動路由只傳 `source='manual'`；解析產生的草稿走 `add_parsed_drafts`。"""
    if source not in _PROVENANCE_BY_SOURCE:
        raise ValueError(f"unknown draft source: {source}")
    if parse_snapshots is not None and len(parse_snapshots) != len(items):
        raise ValueError("parse_snapshots must align with items")
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
            source_rule_set_id=ws.default_rule_set_id,
            parse_snapshot=parse_snapshots[i] if parse_snapshots is not None else None,
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
    pending = [d for d in drafts if d.status == "pending"]
    incomplete = [d.id for d in pending if is_unfilled_incomplete(d)]
    if incomplete:
        raise DraftIncomplete(incomplete)
    # 確認＝人看過目前的內容：以現在的規則版本與 Excel 列為新的基準，清掉過期標記
    hashes = await _current_import_hashes(session, [d.import_row_id for d in pending])
    now = _now()
    for d in pending:
        d.status = "confirmed"
        d.confirmed_by = actor
        d.confirmed_at = now
        d.updated_by = actor
        d.updated_at = now
        d.stale_reason = None
        d.source_rule_set_id = ws.default_rule_set_id
        if d.parse_snapshot and d.parse_snapshot.get("import_input_hash") is not None:
            d.parse_snapshot = {**d.parse_snapshot, "import_input_hash": hashes.get(d.import_row_id)}
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


target_rule_set_code = _target_rule_set_code


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
    # 拿到列鎖後再確認版本仍是 draft（並行核准時，進入時的檢查可能已過期）
    await assert_version_still_draft(session, ws.process_version_id)
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
    # ADR-037 D3「可接受的 motion」：解析出的草稿要完整、引擎算得過（下面 compute_rows_for_save 會再算一次，
    # 算不過就整筆失敗）；不完整的只有在人補過 cycle 之後才可接受。確認時已擋過，這裡是寫入當下的權威檢查。
    incomplete = [d.id for d in drafts if is_unfilled_incomplete(d)]
    if incomplete:
        raise DraftIncomplete(incomplete)
    stale = await detect_stale(session, ws, drafts)
    if stale:
        # 呼叫端回滾本交易後，以 `mark_stale_drafts` 另開交易把它們退回待確認
        raise DraftsStale(stale)

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
                distance_status=content.distance_status,
                cycle=cycle,
                level=LevelFieldsIn(),
            )
        )
        origin_by_row[row_id] = RowOrigin(
            provenance=_provenance_for(d),
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
    # ADR-038 D6：經新工作區寫入過的工時表開啟距離完成檢查，之後不自動關閉
    ws.distance_check_required = True
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


# ════════ 解析結果 → 編輯區（ADR-038 D2 情境 2／3，W3）════════

# 解析不出 cycle 時的佔位（讓這一列照樣進編輯區給人補）。parse_snapshot.complete=False 且 cycle 沒被改過 → 不能確認。
PLACEHOLDER_CYCLE: dict[str, Any] = {"seq": "GM"}
WI_GROUP_MAX = 200
MAX_SNAPSHOT_ISSUES = 50
MAX_ISSUE_CHARS = 200
# 每個參數只留前幾個候選；整列候選序列化後超過上限就不存（只影響「哪些格是 AI 填的」的顯示，不進計算）
MAX_TOP_K = 5
MAX_CANDIDATES_BYTES = 16 * 1024


@dataclass(frozen=True)
class ParsedDraft:
    item: WiDraftCreateItem
    candidates: dict[str, Any] | None
    snapshot: dict[str, Any]


def _engine_ok(d: CycleDraft) -> bool:
    return d.engine_result is not None and not any(i.startswith("engine_reject_") for i in d.issues)


def drafts_from_parse(
    result: ParseRunResult,
    *,
    text: str,
    hand: str | None,
    wi_group: str | None,
    ai_status: str,
    group_key: str | None = None,
) -> list[ParsedDraft]:
    """把一次解析（一句 WI）轉成同一組的草稿列，依 action 順序。純函式。

    - 每個 motion 一列；同一句共用 `group_key`；`wi_group` 預設原句，超過 200 字截斷並記在 snapshot（ADR-037 D5）。
    - cycle 用解析的預覽值（AI 路徑是候選算的預覽，`chosen` 仍空；ADR-038 D3：畫面上預填、狀態 pending）。
    - `complete`＝解析判定完整且引擎算得過（engine_gate 無 `engine_reject_*`）＝ADR-037 D3「可接受的 motion」。
    - 一個 motion 都沒解析出來時，仍放一列佔位（降級或失敗的結果照樣進編輯區，ADR-038 D3）。
    - 手別只用 MOST 已知的（使用者輸入或 Excel 欄），不採信 ai_service 的提示（ADR-037 D3）。
    """
    key = group_key or str(uuid.uuid4())
    raw_group = (wi_group or text or "").strip()
    truncated = len(raw_group) > WI_GROUP_MAX
    group = raw_group[:WI_GROUP_MAX] or None
    order = {a.action_id: a.sequence_order for a in result.plan.actions}
    cands_by_action: dict[str, list[dict[str, Any]]] = {}
    for c in result.slot_candidates:
        dumped_c = c.model_dump(mode="json")
        dumped_c["top_k"] = (dumped_c.get("top_k") or [])[:MAX_TOP_K]
        cands_by_action.setdefault(c.action_id, []).append(dumped_c)
    drafts = sorted(result.drafts, key=lambda d: (order.get(d.action_id, 10**9), d.action_id))
    out: list[ParsedDraft] = []
    if not drafts:
        drafts = [CycleDraft(action_id="none", cycle=None, complete=False, issues=["no_motion_parsed"])]
    # ai_service 回了不在允許清單的代碼（mapper 已丟掉、不進計算）：ai_service 端的 schema 驗證不完整
    # （2026-11-24 ai_service 查明，修正為 S-085／poc004），在那之前每一列都要讓審核的人看得到（放最前面，不被截斷）。
    unknown_code = "ai_unknown_code" in result.routing_reasons
    for idx, d in enumerate(drafts):
        issues = list(d.issues)
        if unknown_code and "ai_unknown_code" not in issues:
            issues.insert(0, "ai_unknown_code")
        complete = bool(d.complete and d.cycle and _engine_ok(d))
        narrative = (d.narrative or None) and d.narrative[:2000]
        try:
            content = WiDraftContent(hand=hand, narrative=narrative, wi_group=group, cycle=d.cycle or PLACEHOLDER_CYCLE)
        except PydanticValidationError:
            content = WiDraftContent(hand=hand, narrative=narrative, wi_group=group, cycle=PLACEHOLDER_CYCLE)
            complete = False
            issues.append("cycle_invalid")
        dumped = content.model_dump(mode="json")
        snapshot = {
            "complete": complete,
            "issues": [i[:MAX_ISSUE_CHARS] for i in issues[:MAX_SNAPSHOT_ISSUES]],
            "cycle_hash": cycle_hash(dumped["cycle"]),
            "ai_status": ai_status,
            "action_id": d.action_id,
            "routing_status": result.routing_status,
            "wi_group_truncated": truncated,
        }
        cands = cands_by_action.get(d.action_id)
        if cands and len(canonical_json(cands)) > MAX_CANDIDATES_BYTES:
            cands = None
            snapshot["candidates_dropped"] = True
        out.append(
            ParsedDraft(
                item=WiDraftCreateItem(content=content, group_key=key, order_in_group=idx),
                candidates={"slot_candidates": cands} if cands else None,
                snapshot=snapshot,
            )
        )
    return out


def parsed_source(ai_status: str) -> str:
    """草稿來源：外部 AI 成功＝ai_service；沒試或降級＝rule_based（ADR-038 D2）。"""
    return "ai_service" if ai_status == "ai_service" else "rule_based"


async def add_parsed_drafts(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    result: ParseRunResult,
    *,
    text: str,
    hand: str | None,
    wi_group: str | None,
    ai_status: str,
    actor: str,
    import_row: ImportRow | None = None,
    excel_quantity: Any = None,
) -> list[WiDraftRow]:
    """解析結果寫進編輯區。來自 Excel 列時（`import_row`）同一列重新解析會取代它沒人動過的草稿；
    已經有人確認、寫入或修改過的不再追加（人已經處理了），回傳空 list。
    """
    # 先鎖工時表（與 add_drafts 同一把鎖）：同一 Excel 列的兩個解析不會都判定「沒人動過」而各寫一份
    await session.execute(select(MostWorksheet.id).where(MostWorksheet.id == worksheet_id).with_for_update())
    if import_row is not None:
        existing = list(
            (
                await session.execute(
                    select(WiDraftRow).where(
                        WiDraftRow.worksheet_id == worksheet_id, WiDraftRow.import_row_id == import_row.id
                    )
                )
            ).scalars()
        )
        # 有人確認、寫入或改過（updated_by 有值）就不動它們，也不追加重複的列
        if any(d.status != "pending" or d.updated_by is not None for d in existing):
            return []
        for d in existing:
            await session.delete(d)
        await session.flush()
    parsed = drafts_from_parse(result, text=text, hand=hand, wi_group=wi_group, ai_status=ai_status)
    if import_row is not None:
        parsed = apply_excel_quantity(parsed, result, excel_quantity)
    snapshots = [
        {**p.snapshot, "import_input_hash": import_row.input_hash} if import_row is not None else p.snapshot
        for p in parsed
    ]
    return await add_drafts(
        session,
        worksheet_id,
        [p.item for p in parsed],
        source=parsed_source(ai_status),
        actor=actor,
        ai_parse_run_id=uuid.UUID(result.run_id) if result.run_id else None,
        import_row_ids=[import_row.id] * len(parsed) if import_row is not None else None,
        ai_candidates=[p.candidates for p in parsed],
        parse_snapshots=snapshots,
    )


# ════════ Excel 數量權威（ADR-037 D6，W3b）════════
# Excel 的數量欄是權威；MOST 依序判斷歸屬並**預填**到草稿的 frequency（仍逐項審核，不自動落盤）。
# 每列草稿的 parse_snapshot["quantity"] 記下：Excel 值、套用的規則、這一列有沒有套用、原因（畫面顯示依據，IE 可改）。
#   規則 1：句中有數量詞且數字與 Excel 一致 → 套到物件對得上被修飾物件的 motion，其餘為 1。
#   規則 2：句中沒有數量詞 → 整句重複：套到 process／move_place 類；其他類不套，標「未套用」。
#   規則 3：AI 已把數量展開成同物件的 N 個 motion → 不套，標審核「AI 已展開成 N 個 motion」。
#   規則 4：其他（對不到、多個候選、數字不一致、Excel 值不是正整數）→ 不猜，標審核。
# 持工具時 QuantityPolicyV2 會改走 repeat_count；外部 AI 的 plan 沒有工具依賴，這裡一律預填 frequency。

QUANTITY_PREFILL_TYPES = frozenset({"process", "move_place"})
# 數量詞之後幾個字內出現物件名稱，視為修飾該物件（例「兩顆螺絲」）；遇到標點就停（不跨子句）
_QTY_OBJECT_WINDOW = 4
_CLAUSE_BREAK = re.compile(r"[，,。．；;、\n]")
# 「次」與「x N」是重複次數，不修飾物件：不靠它綁物件（走規則 4，交 IE）
_REPEAT_UNITS = frozenset({"次", "count"})
# 與 WiDraftContent.frequency 的上限一致
MAX_EXCEL_QUANTITY = 10_000
# 句中「數字＋任意量詞」的寬鬆偵測：extract_counts 只認 顆／件／個／次／xN，「三支」「12 pcs」它看不到
_LOOSE_COUNT = re.compile(r"(?:\d+|[一二兩三四五六七八九十百]+)\s*(?:支|片|根|組|條|顆|件|個|次|台|只|枚|張|塊|pcs?|PCS?)")


def _excel_quantity(raw: Any) -> tuple[int | None, bool]:
    """回傳 (N, 有效)。沒填或 1 → (None, True)：不處理。非正整數 → (None, False)：規則 4。"""
    if raw is None or raw == "":
        return None, True
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None, False
    if not math.isfinite(v) or v <= 0 or v != int(v) or v > MAX_EXCEL_QUANTITY:
        return None, False
    n = int(v)
    return (None, True) if n == 1 else (n, True)


def _object_text(action: Any, labels: dict[str, Any]) -> str | None:
    role = (getattr(action, "roles", None) or {}).get("object")
    text = getattr(role, "text", None) if role is not None else None
    if not text:
        label = labels.get(action.action_id) or {}
        text = label.get("object_text")
    text = (text or "").strip()
    return text or None


def apply_excel_quantity(parsed: list[ParsedDraft], result: ParseRunResult, raw_quantity: Any) -> list[ParsedDraft]:
    """依 ADR-037 D6 預填數量並在 snapshot 記依據。不改 cycle，只改 content.frequency。純函式。"""
    from ddm_v2.nlp.quantities import extract_counts

    n, valid = _excel_quantity(raw_quantity)
    excel_is_one = valid and n is None and raw_quantity not in (None, "")
    if n is None and valid and not excel_is_one:
        return parsed  # Excel 沒填：不處理
    norm = result.plan.normalized_text or ""
    counts = extract_counts(norm)
    actions = {a.action_id: a for a in result.plan.actions}
    labels = {
        lb.get("action_id"): lb for lb in ((result.provenance or {}).get("motion_labels") or []) if isinstance(lb, dict)
    }
    rows = [(p, actions.get(p.snapshot.get("action_id") or "")) for p in parsed]

    def note(rule: str, applied: set[int], reason: str | None, n_value: Any = n) -> list[ParsedDraft]:
        out = []
        for i, (p, _a) in enumerate(rows):
            q = {"excel": raw_quantity if n_value is None else n_value, "rule": rule, "applied": i in applied,
                 "reason": None if i in applied else reason}
            content = p.item.content
            if i in applied:
                content = content.model_copy(update={"frequency": float(n)})
            snap = {**p.snapshot, "quantity": q}
            out.append(ParsedDraft(item=p.item.model_copy(update={"content": content}), candidates=p.candidates,
                                   snapshot=snap))
        return out

    if not valid:
        return note("4", set(), "excel_quantity_invalid", n_value=raw_quantity)
    if excel_is_one:
        # Excel 寫 1，句子卻寫了別的數量：數字不一致，交 IE（規則 4）；一致或沒寫就不處理
        if any(c.value != 1 for c in counts) or (not counts and _LOOSE_COUNT.search(norm)):
            return note("4", set(), "sentence_quantity_differs", n_value=1)
        return parsed
    if not rows or all(a is None for _p, a in rows):
        return note("4", set(), "no_motion")

    objects = [_object_text(a, labels) if a is not None else None for _p, a in rows]
    # 規則 3：同一物件、同一種動作的 motion 剛好 N 個 → AI 已展開（「拿螺絲＋鎖螺絲」不算：動作不同）。
    # 排在規則 1 之前：展開成 N 個 motion 後若再各乘 N，合計會是 N² 倍
    types = [a.action_type if a is not None else None for _p, a in rows]
    for key in {(o, t) for o, t in zip(objects, types) if o}:
        if sum(1 for o, t in zip(objects, types) if (o, t) == key) == n:
            return note("3", set(), "ai_expanded")

    if counts:
        hits = [c for c in counts if c.value == n]
        if not hits:
            return note("4", set(), "sentence_quantity_differs")
        if any(c.unit in _REPEAT_UNITS for c in hits):
            return note("4", set(), "quantity_target_unclear")
        targets: set[str] = set()
        longest = max((len(o) for o in objects if o), default=0)
        for c in hits:
            tail = norm[c.end: c.end + _QTY_OBJECT_WINDOW + longest]
            cut = _CLAUSE_BREAK.search(tail)
            if cut:
                tail = tail[: cut.start()]
            for o in {o for o in objects if o}:
                at = tail.find(o)
                if 0 <= at <= _QTY_OBJECT_WINDOW:
                    targets.add(o)
        if len(targets) != 1:
            return note("4", set(), "quantity_target_unclear")
        (target,) = targets
        return note("1", {i for i, o in enumerate(objects) if o == target}, "not_the_counted_object")
    if _LOOSE_COUNT.search(norm):
        # 句中有「數字＋量詞」但不是 extract_counts 認得的寫法：比不了，不猜
        return note("4", set(), "quantity_target_unclear")

    # 規則 2：沒有數量詞＝整句重複
    applied = {i for i, (_p, a) in enumerate(rows) if a is not None and a.action_type in QUANTITY_PREFILL_TYPES}
    if not applied:
        return note("4", set(), "no_process_or_move_place")
    return note("2", applied, "other_motion_not_applied")


class ImportRowsNotFound(Exception):
    """要建空白草稿的匯入列不存在，或不屬於綁定這份工時表的匯入。"""

    def __init__(self, ids: Sequence[uuid.UUID]) -> None:
        super().__init__(", ".join(sorted(str(i) for i in ids)))
        self.ids = list(ids)


async def add_blank_import_drafts(
    session: AsyncSession, worksheet_id: uuid.UUID, import_row_ids: Sequence[uuid.UUID], *, actor: str
) -> list[WiDraftRow]:
    """為沒有產生草稿的 Excel 列建空白草稿（ADR-038 W5）。由後端建：帶 import_row_id 與出處，cycle 是佔位，
    `parse_snapshot.complete=False`——人沒補齊格位前不能確認或寫入（DRAFT_INCOMPLETE），也納入過期判斷。

    已經有草稿的列跳過（重按不會重複建）。只接受綁定這份工時表的匯入的列。
    """
    from ddm_v2.models.v2.import_staging import ExcelImport

    wanted = list(dict.fromkeys(import_row_ids))
    rows = list(
        (
            await session.execute(
                select(ImportRow)
                .join(ExcelImport, ExcelImport.id == ImportRow.import_id)
                .where(ImportRow.id.in_(wanted), ExcelImport.worksheet_id == worksheet_id)
            )
        ).scalars()
    )
    found = {r.id for r in rows}
    if missing := [i for i in wanted if i not in found]:
        raise ImportRowsNotFound(missing)
    await session.execute(select(MostWorksheet.id).where(MostWorksheet.id == worksheet_id).with_for_update())
    have = set(
        (
            await session.execute(
                select(WiDraftRow.import_row_id).where(
                    WiDraftRow.worksheet_id == worksheet_id, WiDraftRow.import_row_id.in_(wanted)
                )
            )
        ).scalars()
    )
    todo = sorted((r for r in rows if r.id not in have), key=lambda r: r.source_row_no)
    if not todo:
        return []
    items: list[WiDraftCreateItem] = []
    snapshots: list[dict[str, Any]] = []
    for r in todo:
        nd = r.normalized_data or {}
        desc = str(nd.get("description") or "").strip()
        group = str(nd.get("wi_group") or "").strip() or desc
        hand = nd.get("hand") if nd.get("hand") in ("LH", "RH", "BH") else None
        content = WiDraftContent(
            hand=hand, wi_group=group[:WI_GROUP_MAX] or None, narrative=desc[:2000] or None, cycle=PLACEHOLDER_CYCLE
        )
        items.append(WiDraftCreateItem(content=content, group_key=str(uuid.uuid4())))
        snapshots.append({
            "complete": False,
            "issues": ["blank_from_import"],
            "cycle_hash": cycle_hash(content.model_dump(mode="json")["cycle"]),
            "ai_status": "none",
            "action_id": None,
            "routing_status": None,
            "wi_group_truncated": len(group) > WI_GROUP_MAX,
            "import_input_hash": r.input_hash,
        })
    return await add_drafts(
        session, worksheet_id, items, source="imported", actor=actor,
        import_row_ids=[r.id for r in todo], parse_snapshots=snapshots,
    )
