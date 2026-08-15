"""motion_module 持久化服務（impl-04）。

設計原則：
- publish 即驗證：每列 cycle 過 compute_cycle；total_tmu/narrative 由引擎產，不接受呼叫端提供。
- 版本不可變：發布後 MotionModuleVersion 禁 UPDATE；修改＝發新版。
- 實體化＝複製：version.rows → WiRow + MostCycle；合計走引擎（compute_table），不走模組快取。
- SIMO 配對（ADR-020）：simo_pair_index 指向 rows 陣列＝該列為「從屬列」（貢獻 0，
  時間由被指向的主列吸收）；實體化時僅從屬列標記 simo_group_id，主列不標記。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import ROLE_ORDER
from ddm_v2.models.v2.motion_module import MotionModule, MotionModuleVersion
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import LevelEntry, MostCycle, MostWorksheet, ProcessVersion, WiRow
from ddm_v2.most_engine import SequenceError, compute_cycle, load_rule_set_from_db
from ddm_v2.most_engine.calculate import compute_table
from ddm_v2.most_engine.narrative import HAND_NAMES, build_narrative
from ddm_v2.most_engine.providers import load_options_from_db
from ddm_v2.most_engine.rule_set_data import TMU_TO_SEC, RuleSetData
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine, resolve_cycle_rule_set
from ddm_v2.schemas.v2.motion_module import (
    FromModuleRequest,
    ModuleRowIn,
    MotionModuleCreate,
    MotionModuleResponse,
    MotionModuleUpdate,
    MotionModuleVersionResponse,
    PublishRequest,
    VersionFromRowsRequest,
)

logger = logging.getLogger(__name__)

# SM-3：最低 approver 層級，從 ROLE_ORDER 取值（Fix-3：消除魔術常數）。
_MANAGER_LEVEL = ROLE_ORDER["approver"]

# ── domain exceptions ────────────────────────────────────────────────

class ModuleNotFound(Exception):
    pass


class ModuleVersionNotFound(Exception):
    pass


class ModuleNotEditable(Exception):
    """status != 'draft' 時不可改 metadata 或發布（需先 retire/新建）。"""
    pass


class ModuleRetired(Exception):
    """嘗試對 retired 模組實體化。"""
    pass


class ScopePermissionError(Exception):
    pass


class PublishValidationError(Exception):
    """publish 時某列 cycle 算不過（detail = {row_index, code, message}）。"""
    def __init__(self, row_index: int, code: str, message: str) -> None:
        super().__init__(message)
        self.row_index = row_index
        self.code = code
        self.message = message


class RuleSetNotFound(Exception):
    pass


class WorksheetNotFound(Exception):
    pass


class WorksheetPermissionError(Exception):
    """呼叫者無權操作目標工序表。"""
    pass


class ModuleIsStandard(Exception):
    """status == 'standard' 不可直接刪除；需先由管理員 retire。"""
    pass


class ModuleRowNotFound(Exception):
    """row_index 越界（ADR-022 A-2 row 級操作）。"""
    pass


# ── helpers ──────────────────────────────────────────────────────────

def _validate_simo_pairs(pair_indices: list[int | None]) -> None:
    """ADR-020 寫入守門：驗證 rows 的 simo_pair_index。

    規則：
    1. simo_pair_index 須指向 rows 內另一列（0..n-1，不可自指/越界）。
    2. 被指為配對目標（主列）的列不得自身宣告配對——否則互指/鏈式配對
       會讓整組都被標記 → 全部貢獻 0（靜默歸零，SIMO review Finding 1）。

    違反 → PublishValidationError(code="SIMO_PAIR_INVALID")。
    """
    n = len(pair_indices)
    declared: dict[int, int] = {}
    for idx, pi in enumerate(pair_indices):
        if pi is None:
            continue
        if not isinstance(pi, int) or pi < 0 or pi >= n or pi == idx:
            raise PublishValidationError(
                idx, "SIMO_PAIR_INVALID",
                f"simo_pair_index={pi!r} 須指向 rows 內另一列（0..{n - 1}，不可自指）")
        declared[idx] = pi
    for idx, pi in declared.items():
        if pi in declared:
            raise PublishValidationError(
                idx, "SIMO_PAIR_INVALID",
                f"配對目標列 {pi}（主列）自身也宣告配對——ADR-020：主列不得標記")


async def _validate_and_compute_rows(
    session: AsyncSession,
    rows: list[ModuleRowIn],
    rsdata: RuleSetData,
    rule_set_code: str,
) -> tuple[list[dict[str, Any]], float, float]:
    """ADR-022 A-1：驗證 rows ＋ 引擎計算 ＋ 每列 computed/narrative 持久化素材。

    單一引擎鐵則：每列與合計數值全部取自 most_engine（compute_table 的回傳），
    service 不重新實作任何公式。回傳 (validated_rows, total_tmu, total_seconds)。

    每列 rows JSON 形狀（版本快照）：
      sub_activity / hand / frequency / simo_pair_index / vocab_refs / cycle（原始輸入）
      computed: {total_tmu, total_seconds, eff_tmu, contribution_tmu}
        - contribution_tmu：SIMO 標記列（宣告 simo_pair_index 的從屬列）= 0（ADR-020），
          否則 = eff_tmu（total_tmu × frequency）。
      narrative_zh: 引擎產生的 METHOD 句（sub_activity 使用者句另存，不覆蓋）。
      _computed_tmu: 向後相容快取（instantiate drift 檢查沿用）。
    """
    # ADR-020 寫入守門：simo_pair_index 合法性（越界/自指/主列自身宣告配對 → 422）
    _validate_simo_pairs([row.simo_pair_index for row in rows])

    # ADR-023 §3.4：rows[].cycle 會被 dump 成版本快照 JSON（回放權威原始輸入）→ 先回填版本代碼。
    # 與 worksheet_service 用同一個 helper，兩條持久化路徑契約一致。
    for row in rows:
        resolve_cycle_rule_set(row.cycle, rule_set_code)

    # 逐列先過 compute_cycle 取得帶 row_index 的錯誤（compute_table 不回列號），
    # 數值仍以下方 compute_table 回傳為準（同一引擎、同一演算法）。
    engine_steps: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        try:
            engine_cycle = cycle_in_to_engine(row.cycle)
            compute_cycle(engine_cycle, rsdata)
        except SequenceError as e:
            raise PublishValidationError(idx, e.code, str(e)) from e
        engine_steps.append({
            **engine_cycle,
            "frequency": row.frequency,
            # compute_table 的 SIMO 語義吃 simo_group_id 標記；模組層以
            # simo_pair_index 表達從屬列 → 轉為標記（ADR-020：從屬列貢獻 0）。
            "simo_group_id": "SIMO-DEP" if row.simo_pair_index is not None else None,
        })

    table = compute_table(engine_steps, rsdata)

    # 敘事素材：rule-set 標籤/句字 + vocab 名（單一權威 = most_engine.narrative）
    opts = await load_options_from_db(session, rule_set_code)

    def _lmap(rows_: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {o["code"]: {"label": o.get("label"), "sentence": o.get("sentence"),
                            "display_rule": o.get("display_rule")} for o in rows_}

    labels = {"g": _lmap(opts["g"]), "p_base": _lmap(opts["p_bases"]),
              "p_addon": _lmap(opts["p_addons"]), "m_verb": _lmap(opts["m_verbs"]),
              "x": _lmap(opts["x"]), "i": _lmap(opts["i"])}

    vids: set[uuid.UUID] = set()
    for row in rows:
        for key in ("object_vocab_id", "from_vocab_id", "to_vocab_id"):
            raw = (row.vocab_refs or {}).get(key)
            if raw:
                try:
                    vids.add(uuid.UUID(str(raw)))
                except ValueError:
                    pass  # 非 UUID 的 ref 不阻斷發布；實體化時另有守門
    vname: dict[str, str] = {}
    if vids:
        res = await session.execute(select(WorkVocabItem).where(WorkVocabItem.id.in_(vids)))
        vname = {str(v.id): v.name_zh for v in res.scalars().all()}

    validated_rows: list[dict[str, Any]] = []
    for row, trow in zip(rows, table["rows"]):
        refs = row.vocab_refs or {}
        voc = {"object": vname.get(str(refs.get("object_vocab_id")), ""),
               "from": vname.get(str(refs.get("from_vocab_id")), ""),
               "to": vname.get(str(refs.get("to_vocab_id")), ""),
               "hand": HAND_NAMES.get(row.hand or "", "")}
        narrative = build_narrative(row.cycle.model_dump(mode="json"), labels, voc)

        row_tmu = trow["tmu"]                       # 該列單次 TMU（引擎）
        eff_tmu = round(trow["eff_tmu"], 3)         # ×frequency（引擎）
        contribution = 0.0 if trow["simo"] else eff_tmu  # ADR-020：SIMO 標記列貢獻 0
        validated_rows.append({
            "sub_activity": row.sub_activity,
            "hand": row.hand,
            "frequency": row.frequency,
            "simo_pair_index": row.simo_pair_index,
            "vocab_refs": row.vocab_refs,
            "cycle": row.cycle.model_dump(mode="json"),
            "computed": {
                "total_tmu": row_tmu,
                "total_seconds": round(row_tmu * TMU_TO_SEC, 4),
                "eff_tmu": eff_tmu,
                "contribution_tmu": contribution,
            },
            "narrative_zh": narrative,
            "_computed_tmu": row_tmu,   # 向後相容快取（instantiate drift 檢查）
        })

    return validated_rows, float(table["total_tmu"]), float(table["total_seconds"])


def _module_to_response(
    m: MotionModule,
    version: MotionModuleVersion | None = None,
    *,
    include_detail: bool = True,
) -> MotionModuleResponse:
    """組 MotionModuleResponse。

    F-02b：version 有值時一律回填輕量摘要欄 total_tmu / action_count；
    include_detail=False 時省略完整 current_version_detail（list 端點用，避免 payload 過大）。
    """
    ver_detail = None
    total_tmu: float | None = None
    action_count: int | None = None
    seq_kind: str | None = None
    hand: str | None = None
    base_tmu: float | None = None
    frequency: float | None = None
    if version is not None:
        total_tmu = float(version.total_tmu)
        action_count = len(version.rows)
        # 摘要欄：取 rows[0] 的 cycle seq 與 hand（同一趟資料回填，不加新查詢）
        if version.rows:
            first_row = version.rows[0]
            seq_kind = (first_row.get("cycle") or {}).get("seq")
            hand = first_row.get("hand")
            # E-2：base_tmu / frequency 摘要欄（rows 已於 publish 豐富化 computed）
            computed = first_row.get("computed") or {}
            raw_base = computed.get("total_tmu", first_row.get("_computed_tmu"))
            base_tmu = float(raw_base) if raw_base is not None else None
            raw_freq = first_row.get("frequency")
            frequency = float(raw_freq) if raw_freq is not None else None
        if include_detail:
            ver_detail = MotionModuleVersionResponse(
                id=version.id,
                module_id=version.module_id,
                version_no=version.version_no,
                rule_set_id=version.rule_set_id,
                rows=list(version.rows),
                narrative_zh=version.narrative_zh,
                total_tmu=float(version.total_tmu),
                total_seconds=float(version.total_seconds),
                published_by=version.published_by,
                published_at=version.published_at,
            )
    return MotionModuleResponse(
        id=m.id,
        site_id=m.site_id,
        name_zh=m.name_zh,
        category=m.category,
        keywords=list(m.keywords or []),
        scope=m.scope,
        owner=m.owner,
        status=m.status,
        current_version=m.current_version,
        created_at=m.created_at,
        updated_at=m.updated_at,
        current_version_detail=ver_detail,
        total_tmu=total_tmu,
        action_count=action_count,
        seq_kind=seq_kind,
        hand=hand,
        base_tmu=base_tmu,
        frequency=frequency,
    )


async def _current_versions_map(
    session: AsyncSession,
    modules: list[MotionModule],
) -> dict[uuid.UUID, MotionModuleVersion]:
    """一次撈齊各 module 的 current version（單一 tuple-IN 查詢，避免 N+1）。"""
    pairs = [(m.id, m.current_version) for m in modules if m.current_version > 0]
    if not pairs:
        return {}
    from sqlalchemy import tuple_

    res = await session.execute(
        select(MotionModuleVersion).where(
            tuple_(
                MotionModuleVersion.module_id,
                MotionModuleVersion.version_no,
            ).in_(pairs)
        )
    )
    return {v.module_id: v for v in res.scalars().all()}


def _version_to_response(v: MotionModuleVersion) -> MotionModuleVersionResponse:
    return MotionModuleVersionResponse(
        id=v.id,
        module_id=v.module_id,
        version_no=v.version_no,
        rule_set_id=v.rule_set_id,
        rows=list(v.rows),
        narrative_zh=v.narrative_zh,
        total_tmu=float(v.total_tmu),
        total_seconds=float(v.total_seconds),
        published_by=v.published_by,
        published_at=v.published_at,
    )


# ── CRUD ─────────────────────────────────────────────────────────────

async def create_module(
    session: AsyncSession,
    data: MotionModuleCreate,
    current_user_no: str,
    current_user_level: int = 0,
) -> MotionModuleResponse:
    """建立 draft 模組（scope=personal 時自動填 owner）。

    SM-3：只有 manager/admin 可建立 scope=site/global 模組。
    """
    # SM-3：scope escalation guard
    if data.scope in ("site", "global") and current_user_level < _MANAGER_LEVEL:
        raise ScopePermissionError("只有 approver/admin 可建立 site/global scope 模組")

    owner = data.owner
    if data.scope == "personal":
        owner = owner or current_user_no  # 個人草稿歸屬呼叫者

    now = datetime.now(timezone.utc)
    m = MotionModule(
        id=uuid.uuid4(),
        site_id=data.site_id,
        name_zh=data.name_zh,
        category=data.category,
        keywords=list(data.keywords),
        scope=data.scope,
        owner=owner,
        status="draft",
        current_version=0,
        created_at=now,
        updated_at=now,
    )
    session.add(m)
    await session.flush()
    return _module_to_response(m)


async def get_module(
    session: AsyncSession,
    module_id: uuid.UUID,
    current_user_no: str,
) -> MotionModuleResponse:
    """取得模組（含 current_version 內容）。

    SM-1：personal scope 的模組只有 owner 可見；
    對他人不可見的模組回 404（不洩漏存在性，IDOR 防護）。
    """
    m = await session.get(MotionModule, module_id)
    if m is None:
        raise ModuleNotFound(str(module_id))
    # SM-1：personal scope 隔離
    if m.scope == "personal" and m.owner != current_user_no:
        raise ModuleNotFound(str(module_id))  # 404 not 403，避免洩漏存在性
    version: MotionModuleVersion | None = None
    if m.current_version > 0:
        res = await session.execute(
            select(MotionModuleVersion)
            .where(
                MotionModuleVersion.module_id == module_id,
                MotionModuleVersion.version_no == m.current_version,
            )
        )
        version = res.scalar_one_or_none()
    return _module_to_response(m, version)


async def list_modules(
    session: AsyncSession,
    current_user_no: str,
    q: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> list[MotionModuleResponse]:
    """列出可見模組（global/site 全可見；personal 只顯示自己的）。

    F-02b：支援 status 過濾；每筆回填輕量摘要欄 total_tmu / action_count
    （自 current version，單一 tuple-IN 查詢撈齊，避免 N+1）。
    """
    from sqlalchemy import and_, or_

    stmt = select(MotionModule)

    # scope 過濾
    if scope:
        stmt = stmt.where(MotionModule.scope == scope)
        if scope == "personal":
            stmt = stmt.where(MotionModule.owner == current_user_no)
    else:
        # 未指定 scope：global + site + 自己的 personal
        stmt = stmt.where(
            or_(
                MotionModule.scope.in_(["global", "site"]),
                and_(MotionModule.scope == "personal", MotionModule.owner == current_user_no),
            )
        )

    if category:
        stmt = stmt.where(MotionModule.category == category)

    if status:
        stmt = stmt.where(MotionModule.status == status)

    modules: list[MotionModule] | None = None
    if q:
        # Fix-1：直接在 motion_modules 表用 pg_trgm similarity 排序，
        # scope/category/status WHERE 已在上方加入 stmt，不會被截斷。
        # Fix-2：trgm 不可用時降級到 ILIKE。
        from sqlalchemy import func as sa_func
        stmt_q = stmt.where(
            sa_func.similarity(MotionModule.name_zh, q) > 0.05
        ).order_by(
            sa_func.similarity(MotionModule.name_zh, q).desc()
        )
        try:
            result = await session.execute(stmt_q)
            modules = list(result.scalars().all())
        except Exception:
            # trgm 不可用時降級到 ILIKE
            stmt = stmt.where(MotionModule.name_zh.ilike(f"%{q}%"))
            stmt = stmt.order_by(MotionModule.updated_at.desc())
    else:
        stmt = stmt.order_by(MotionModule.updated_at.desc())

    if modules is None:
        result = await session.execute(stmt)
        modules = list(result.scalars().all())

    vmap = await _current_versions_map(session, modules)
    return [
        _module_to_response(m, vmap.get(m.id), include_detail=False)
        for m in modules
    ]


async def update_module(
    session: AsyncSession,
    module_id: uuid.UUID,
    data: MotionModuleUpdate,
    current_user_no: str,
    current_user_level: int = 0,
) -> MotionModuleResponse:
    """更新模組 metadata（僅 draft 可改）。

    SM-3：scope 升格至 site/global 需要 manager/admin 角色。
    SM-4：owner 欄位已從 MotionModuleUpdate schema 移除，不允許重新指派。
    """
    m = await session.get(MotionModule, module_id)
    if m is None:
        raise ModuleNotFound(str(module_id))
    if m.status != "draft":
        raise ModuleNotEditable(f"模組 status={m.status}，非 draft 不可改 metadata")
    # personal scope 隔離
    if m.scope == "personal" and m.owner != current_user_no:
        raise ScopePermissionError("無法修改他人的 personal 模組")
    # SM-3：scope escalation guard
    if data.scope in ("site", "global") and current_user_level < _MANAGER_LEVEL:
        raise ScopePermissionError("只有 approver/admin 可將模組設為 site/global scope")

    if data.name_zh is not None:
        m.name_zh = data.name_zh
    if data.category is not None:
        m.category = data.category
    if data.keywords is not None:
        m.keywords = list(data.keywords)
    if data.scope is not None:
        m.scope = data.scope
    # SM-4：owner 欄位已從 MotionModuleUpdate 移除，此處不更新 owner。
    if data.site_id is not None:
        m.site_id = data.site_id
    m.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return _module_to_response(m)


# ── 刪除 ─────────────────────────────────────────────────────────────

async def delete_module(
    session: AsyncSession,
    module_id: uuid.UUID,
    current_user_no: str,
) -> None:
    """刪除模組（僅限非 standard 狀態）。

    - standard modules 需先由管理員 retire → 409。
    - draft / retired 直接刪除；DB cascade 處理 MotionModuleVersion。
    - personal scope：只有 owner 可刪除自己的模組。
    - search_documents 投影必須在**同一交易**以 raw SQL 清掉：search_documents
      沒有 ORM model（v2_0013 以 raw SQL 建表；寫入端 clone/publish 也是 raw SQL
      upsert），ref_id 是跨 doc_type 的裸 uuid、刻意無 FK——ORM cascade 與 DB
      cascade 都救不到。不清會留下指向已刪模組的孤兒投影，/api/v2/search 會
      持續回傳已刪模組（既存孤兒由 v2_0036 data migration 清理）。
    """
    m = await session.get(MotionModule, module_id)
    if m is None:
        raise ModuleNotFound(str(module_id))
    if m.scope == "personal" and m.owner != current_user_no:
        raise ScopePermissionError("無權刪除他人的個人模組")
    if m.status == "standard":
        raise ModuleIsStandard(
            f"模組 {module_id} 為 standard 狀態，需先由管理員 retire 才可刪除"
        )
    await session.execute(
        text(
            "DELETE FROM search_documents"
            " WHERE doc_type = 'motion_module' AND ref_id = :ref_id"
        ),
        {"ref_id": str(module_id)},
    )
    await session.delete(m)
    await session.flush()


# ── 複製 ─────────────────────────────────────────────────────────────

async def clone_module(
    session: AsyncSession,
    module_id: uuid.UUID,
    current_user_no: str,
) -> MotionModuleResponse:
    """複製模組（含最新版本內容）。

    規則：
    - name_zh 加上「複製-」前綴。
    - scope 重設為 personal，owner = current_user。
    - status = 'draft'，current_version = 0（若來源有發布版本則複製為 version 1）。
    - 若來源 current_version > 0，複製最新版本之 rows/totals 為新模組 version 1。
    """
    m = await session.get(MotionModule, module_id)
    if m is None:
        raise ModuleNotFound(str(module_id))
    # SM-1 gap fix：clone 也要隱藏他人的 personal module（不洩漏存在性）
    if m.scope == "personal" and m.owner != current_user_no:
        raise ModuleNotFound(str(module_id))

    # 取來源最新版本（若有）
    source_ver: MotionModuleVersion | None = None
    if m.current_version > 0:
        res = await session.execute(
            select(MotionModuleVersion)
            .where(
                MotionModuleVersion.module_id == module_id,
                MotionModuleVersion.version_no == m.current_version,
            )
        )
        source_ver = res.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    new_module_id = uuid.uuid4()

    new_m = MotionModule(
        id=new_module_id,
        site_id=m.site_id,
        name_zh=f"複製-{m.name_zh}",
        category=m.category,
        keywords=list(m.keywords or []),
        scope="personal",
        owner=current_user_no,
        status="draft",
        current_version=0,
        created_at=now,
        updated_at=now,
    )
    session.add(new_m)
    await session.flush()

    cloned_ver: MotionModuleVersion | None = None
    if source_ver is not None:
        cloned_ver = MotionModuleVersion(
            id=uuid.uuid4(),
            module_id=new_module_id,
            version_no=1,
            rule_set_id=source_ver.rule_set_id,
            rows=list(source_ver.rows),
            narrative_zh=source_ver.narrative_zh,
            total_tmu=source_ver.total_tmu,
            total_seconds=source_ver.total_seconds,
            published_by=current_user_no,
            published_at=now,
        )
        session.add(cloned_ver)
        new_m.current_version = 1
        new_m.updated_at = now
        await session.flush()

    # Fix-3：clone 後寫入 search_documents（同 publish_version 模式）
    try:
        async with session.begin_nested():
            from ddm_v2.search.normalization import build_content_norm
            content = build_content_norm(new_m.name_zh, "", list(new_m.keywords or []))
            await session.execute(text("""
                INSERT INTO search_documents (id, doc_type, ref_id, rule_set_id, content_norm, scope, owner, updated_at)
                VALUES (gen_random_uuid(), 'motion_module', :ref_id, :rule_set_id, :content, :scope, :owner, now())
                ON CONFLICT (doc_type, ref_id) DO UPDATE
                  SET content_norm = EXCLUDED.content_norm, scope = EXCLUDED.scope,
                      owner = EXCLUDED.owner, embedding = NULL, updated_at = now()
            """), {
                "ref_id": str(new_m.id),
                "rule_set_id": str(cloned_ver.rule_set_id) if cloned_ver else None,
                "content": content,
                "scope": new_m.scope,
                "owner": new_m.owner,
            })
    except Exception as exc:
        logger.warning("clone search 投影失敗 module=%s: %s", new_m.id, exc)

    return _module_to_response(new_m, cloned_ver)


# ── 版本發布 ─────────────────────────────────────────────────────────

async def publish_version(
    session: AsyncSession,
    module_id: uuid.UUID,
    data: PublishRequest,
    current_user_no: str,
) -> MotionModuleVersionResponse:
    """發布新版本（引擎驗證+算值；版本不可變）。

    不變量：
    1. 每列 cycle 過 compute_cycle；算不過 → PublishValidationError（→ 422）。
    2. total_tmu = Σ(未帶 SIMO 配對列的 total_tmu × frequency)——ADR-020：宣告
       simo_pair_index 的從屬列貢獻 0（時間由被指向的主列吸收）。合計取自
       most_engine.compute_table（單一引擎，service 不重算）。
    3. ADR-022 A-1：每列寫入 computed（total_tmu/total_seconds/eff_tmu/contribution_tmu）
       與 narrative_zh（引擎敘事；sub_activity 使用者句保留不覆蓋）。
    """
    if not data.rows:
        raise PublishValidationError(0, "EMPTY_ROWS", "rows 不可為空")

    module_row = await session.execute(
        select(MotionModule).where(MotionModule.id == module_id).with_for_update()
    )
    m = module_row.scalar_one_or_none()
    if m is None:
        raise ModuleNotFound(str(module_id))
    # SM-5：ownership guard — personal 模組只有 owner 可發布新版本
    if m.scope == "personal" and m.owner != current_user_no:
        raise ScopePermissionError("只能發布自己的 personal 模組")
    if m.status == "retired":
        raise ModuleNotEditable("module status=retired 不可發布新版本")

    # 載入 rule set（F-01：id / code 擇一，schema 已保證恰好一個有值）
    if data.rule_set_code is not None:
        rs_row = (await session.execute(
            select(RuleSet).where(RuleSet.code == data.rule_set_code)
        )).scalar_one_or_none()
        if rs_row is None:
            raise RuleSetNotFound(data.rule_set_code)
    else:
        rs_row = (await session.execute(
            select(RuleSet).where(RuleSet.id == data.rule_set_id)
        )).scalar_one_or_none()
        if rs_row is None:
            raise RuleSetNotFound(str(data.rule_set_id))
    rsdata = await load_rule_set_from_db(session, rs_row.code)

    # ADR-022 A-1：驗證 + 引擎計算 + 每列 computed/narrative（單一路徑）
    validated_rows, total_tmu, total_seconds = await _validate_and_compute_rows(
        session, data.rows, rsdata, rs_row.code
    )

    new_version_no = m.current_version + 1
    now = datetime.now(timezone.utc)

    ver = MotionModuleVersion(
        id=uuid.uuid4(),
        module_id=module_id,
        version_no=new_version_no,
        rule_set_id=rs_row.id,
        rows=validated_rows,
        narrative_zh=None,    # 版本級敘事留 None；每列敘事已入 rows[i].narrative_zh
        total_tmu=total_tmu,
        total_seconds=total_seconds,
        published_by=current_user_no,
        published_at=now,
    )
    session.add(ver)

    m.current_version = new_version_no
    m.updated_at = now
    await session.flush()

    # search_documents upsert（search/ 模組；失敗不阻斷發布）
    try:
        from ddm_v2.search.normalization import build_content_norm
        content = build_content_norm(
            m.name_zh,
            "",  # module 尚無 description 欄
            list(m.keywords or []),
        )
        upsert_sql = text("""
            INSERT INTO search_documents (id, doc_type, ref_id, rule_set_id, content_norm, scope, owner, updated_at)
            VALUES (gen_random_uuid(), 'motion_module', :ref_id, :rule_set_id, :content, :scope, :owner, now())
            ON CONFLICT (doc_type, ref_id) DO UPDATE
              SET content_norm = EXCLUDED.content_norm,
                  rule_set_id = EXCLUDED.rule_set_id,
                  scope = EXCLUDED.scope,
                  owner = EXCLUDED.owner,
                  embedding = NULL,
                  embedding_model = NULL,
                  updated_at = now()
        """)
        async with session.begin_nested():
            await session.execute(upsert_sql, {
                "ref_id": str(module_id),
                "rule_set_id": str(rs_row.id),
                "content": content,
                "scope": m.scope,
                "owner": m.owner,
            })
    except Exception as exc:
        logger.warning("search 投影失敗 module=%s: %s", module_id, exc)

    return _version_to_response(ver)


# ── apply-back：從 rows 建立新版本（F-03b §3）────────────────────────

async def create_version_from_rows(
    session: AsyncSession,
    module_id: uuid.UUID,
    data: VersionFromRowsRequest,
    current_user_no: str,
) -> MotionModuleVersionResponse:
    """把 rows 同步回模組，建立新版本（apply-back）。

    語義（F-03b §3）：使用者在 ProcessWorkspace 修改 worksheet rows 後，
    想把修改同步回 module library；建立新 MotionModuleVersion，
    不改 module.status（讓使用者自行決定是否 promote）。

    與 publish_version 的差異：
    - personal 模組必須是 owner 才能 apply-back。
    - 用途是 workspace 內的「快速同步」，不等同正式發布流程。
    """
    module_row = await session.execute(
        select(MotionModule).where(MotionModule.id == module_id).with_for_update()
    )
    m = module_row.scalar_one_or_none()
    if m is None:
        raise ModuleNotFound(str(module_id))
    # ownership guard：personal 模組只有 owner 可 apply-back
    if m.scope == "personal" and m.owner != current_user_no:
        raise ScopePermissionError("只能 apply-back 自己的 personal 模組")
    if m.status == "retired":
        raise ModuleNotEditable("module status=retired 不可建立新版本")

    # 載入 rule set
    rs_row = (await session.execute(
        select(RuleSet).where(RuleSet.id == data.rule_set_id)
    )).scalar_one_or_none()
    if rs_row is None:
        raise RuleSetNotFound(str(data.rule_set_id))
    rsdata = await load_rule_set_from_db(session, rs_row.code)

    # ADR-022 A-1：與 publish_version 同一路徑（驗證 + compute_table + computed/narrative）
    validated_rows, total_tmu, total_seconds = await _validate_and_compute_rows(
        session, data.rows, rsdata, rs_row.code
    )

    new_version_no = m.current_version + 1
    now = datetime.now(timezone.utc)

    ver = MotionModuleVersion(
        id=uuid.uuid4(),
        module_id=module_id,
        version_no=new_version_no,
        rule_set_id=data.rule_set_id,
        rows=validated_rows,
        narrative_zh=None,
        total_tmu=total_tmu,
        total_seconds=total_seconds,
        published_by=current_user_no,
        published_at=now,
    )
    session.add(ver)

    m.current_version = new_version_no
    m.updated_at = now
    await session.flush()

    return _version_to_response(ver)


# ── 版本歷史 ─────────────────────────────────────────────────────────

async def get_versions(
    session: AsyncSession,
    module_id: uuid.UUID,
    current_user_no: str,
) -> list[MotionModuleVersionResponse]:
    """列出模組所有歷史版本。

    SM-1 gap fix：personal scope 的模組只有 owner 可見版本歷史；
    對他人不可見的模組回 404（不洩漏存在性）。
    """
    m = await session.get(MotionModule, module_id)
    if m is None:
        raise ModuleNotFound(str(module_id))
    # SM-1 gap fix：personal scope 隔離
    if m.scope == "personal" and m.owner != current_user_no:
        raise ModuleNotFound(str(module_id))  # 404 不洩漏存在性

    result = await session.execute(
        select(MotionModuleVersion)
        .where(MotionModuleVersion.module_id == module_id)
        .order_by(MotionModuleVersion.version_no)
    )
    versions = list(result.scalars().all())
    return [_version_to_response(v) for v in versions]


# ── row 級操作（ADR-022 A-2：WI 微調 = Inspector 後端）───────────────

async def _load_module_and_current_version(
    session: AsyncSession,
    module_id: uuid.UUID,
    current_user_no: str,
) -> tuple[MotionModule, MotionModuleVersion]:
    """取模組（FOR UPDATE）＋ current version；套 publish 同款守門。"""
    module_row = await session.execute(
        select(MotionModule).where(MotionModule.id == module_id).with_for_update()
    )
    m = module_row.scalar_one_or_none()
    if m is None:
        raise ModuleNotFound(str(module_id))
    if m.scope == "personal" and m.owner != current_user_no:
        # SM-1/SM-5 同款：他人的 personal 模組不可見（404 不洩漏存在性）
        raise ModuleNotFound(str(module_id))
    if m.status == "retired":
        raise ModuleNotEditable("module status=retired 不可修改 rows")
    if m.current_version == 0:
        raise ModuleVersionNotFound("模組尚無任何發布版本（current_version=0）")
    ver = (await session.execute(
        select(MotionModuleVersion).where(
            MotionModuleVersion.module_id == module_id,
            MotionModuleVersion.version_no == m.current_version,
        )
    )).scalar_one_or_none()
    if ver is None:
        raise ModuleVersionNotFound(
            f"模組 {module_id} 版本 {m.current_version} 不存在"
        )
    return m, ver


def _stored_rows_to_inputs(stored_rows: list[dict[str, Any]]) -> list[ModuleRowIn]:
    """版本 rows JSON → ModuleRowIn（快取鍵 computed/_computed_tmu/narrative_zh 自然被忽略）。"""
    return [ModuleRowIn.model_validate(r) for r in stored_rows]


async def _republish_rows(
    session: AsyncSession,
    m: MotionModule,
    rule_set_id: uuid.UUID,
    rows_in: list[ModuleRowIn],
    current_user_no: str,
) -> MotionModuleVersionResponse:
    """以 rows_in 發新版本（版本不可變：修改＝新版本；引擎重算全表）。"""
    rs_row = await session.get(RuleSet, rule_set_id)
    if rs_row is None:
        raise RuleSetNotFound(str(rule_set_id))
    rsdata = await load_rule_set_from_db(session, rs_row.code)

    validated_rows, total_tmu, total_seconds = await _validate_and_compute_rows(
        session, rows_in, rsdata, rs_row.code
    )

    new_version_no = m.current_version + 1
    now = datetime.now(timezone.utc)
    ver = MotionModuleVersion(
        id=uuid.uuid4(),
        module_id=m.id,
        version_no=new_version_no,
        rule_set_id=rs_row.id,
        rows=validated_rows,
        narrative_zh=None,
        total_tmu=total_tmu,
        total_seconds=total_seconds,
        published_by=current_user_no,
        published_at=now,
    )
    session.add(ver)
    m.current_version = new_version_no
    m.updated_at = now
    await session.flush()
    return _version_to_response(ver)


async def update_row(
    session: AsyncSession,
    module_id: uuid.UUID,
    row_index: int,
    row: ModuleRowIn,
    current_user_no: str,
) -> MotionModuleVersionResponse:
    """替換 current version 的第 row_index 列 → 引擎重算全表 → 發新版本。

    越界 → ModuleRowNotFound（404）；SIMO 驗證沿 _validate_simo_pairs（422）。
    """
    m, ver = await _load_module_and_current_version(session, module_id, current_user_no)
    if not (0 <= row_index < len(ver.rows)):
        raise ModuleRowNotFound(
            f"row_index={row_index} 越界（rows 共 {len(ver.rows)} 列）"
        )
    rows_in = _stored_rows_to_inputs(ver.rows)
    rows_in[row_index] = row
    return await _republish_rows(session, m, ver.rule_set_id, rows_in, current_user_no)


async def reorder_rows(
    session: AsyncSession,
    module_id: uuid.UUID,
    ordered_indexes: list[int],
    current_user_no: str,
) -> MotionModuleVersionResponse:
    """依 ordered_indexes 重排 rows → 發新版本。

    ordered_indexes 必須是 0..n-1 的完整排列，否則 PublishValidationError（422）。
    simo_pair_index 指向陣列位置 → 重排時同步換算為新位置。
    """
    m, ver = await _load_module_and_current_version(session, module_id, current_user_no)
    n = len(ver.rows)
    if sorted(ordered_indexes) != list(range(n)):
        raise PublishValidationError(
            0, "REORDER_INVALID",
            f"ordered_indexes 必須是 0..{n - 1} 的完整排列，收到 {ordered_indexes}",
        )
    rows_in = _stored_rows_to_inputs(ver.rows)
    # 舊索引 → 新位置（simo_pair_index 換算用）
    new_pos = {old: new for new, old in enumerate(ordered_indexes)}
    reordered: list[ModuleRowIn] = []
    for old_idx in ordered_indexes:
        r = rows_in[old_idx]
        if r.simo_pair_index is not None:
            r = r.model_copy(update={"simo_pair_index": new_pos[r.simo_pair_index]})
        reordered.append(r)
    return await _republish_rows(session, m, ver.rule_set_id, reordered, current_user_no)


async def delete_row(
    session: AsyncSession,
    module_id: uuid.UUID,
    row_index: int,
    current_user_no: str,
) -> MotionModuleVersionResponse:
    """移除第 row_index 列 → 引擎重算 → 發新版本。

    - 刪到 0 列 → PublishValidationError EMPTY_ROWS（422）：WI 至少 1 動作。
    - 若其他列的 simo_pair_index 指向被刪列 → 422（需先解除配對；不得靜默改變貢獻語義）。
    - 刪除後其餘列的 simo_pair_index 依位移換算。
    """
    m, ver = await _load_module_and_current_version(session, module_id, current_user_no)
    n = len(ver.rows)
    if not (0 <= row_index < n):
        raise ModuleRowNotFound(f"row_index={row_index} 越界（rows 共 {n} 列）")
    if n == 1:
        raise PublishValidationError(
            0, "EMPTY_ROWS", "WI 至少需保留 1 個動作，不可刪除最後一列"
        )
    rows_in = _stored_rows_to_inputs(ver.rows)
    # 其他列指向被刪列 → 明確拒絕（否則從屬列會靜默變回全額貢獻，ADR-020 語義劇變）
    for idx, r in enumerate(rows_in):
        if idx != row_index and r.simo_pair_index == row_index:
            raise PublishValidationError(
                idx, "SIMO_PAIR_INVALID",
                f"列 {idx} 的 SIMO 配對指向被刪除的列 {row_index}，請先解除配對",
            )
    remaining: list[ModuleRowIn] = []
    for idx, r in enumerate(rows_in):
        if idx == row_index:
            continue
        if r.simo_pair_index is not None and r.simo_pair_index > row_index:
            r = r.model_copy(update={"simo_pair_index": r.simo_pair_index - 1})
        remaining.append(r)
    return await _republish_rows(session, m, ver.rule_set_id, remaining, current_user_no)


# ── 實體化（工序表 from-module）──────────────────────────────────────

async def instantiate_to_worksheet(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    data: FromModuleRequest,
    current_user_no: str,
) -> dict[str, Any]:
    """把模組版本展開為 WiRow + MostCycle，附加至工序表末尾。

    不變量（impl-04 §2）：
    - 實體化後即普通列；合計走 compute_table（此函式不合計，讓既有路由讀取）。
    - 使用工序表當前 rule-set 重算 cycle（非模組發布時的 rule-set）。
    - 若重算結果與模組快取 _computed_tmu 不同 → tmu_drift 警示。
    - SIMO simo_pair_index → simo_group_id（ADR-020：僅從屬列標記，主列不標記）。
    """
    # 取工序表 + rule-set
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    # 確認呼叫者擁有此工序表（透過 ProcessVersion.created_by）
    pv_check = await session.get(ProcessVersion, ws.process_version_id)
    if (
        pv_check is not None
        and pv_check.created_by is not None
        and pv_check.created_by != current_user_no
    ):
        raise WorksheetPermissionError("無權操作此工序表")

    # R1：append 前 CAS（失敗則不寫列）
    from ddm_v2.services.v2.worksheet_revision import bump_worksheet_revision

    await bump_worksheet_revision(
        session,
        worksheet_id=worksheet_id,
        base_revision=data.base_revision,
        edited_by=current_user_no,
    )

    if ws.default_rule_set_id is None:
        raise RuleSetNotFound("工序表未設定 default_rule_set_id")

    rs_row = await session.get(RuleSet, ws.default_rule_set_id)
    if rs_row is None:
        raise RuleSetNotFound(str(ws.default_rule_set_id))
    rsdata = await load_rule_set_from_db(session, rs_row.code)

    # 取模組 + 版本
    m = await session.get(MotionModule, data.module_id)
    if m is None:
        raise ModuleNotFound(str(data.module_id))
    if m.status == "retired":
        raise ModuleRetired(f"模組 {m.id} 已 retired，無法實體化")

    target_ver_no = data.version_no if data.version_no is not None else m.current_version
    if target_ver_no == 0:
        raise ModuleVersionNotFound("模組尚無任何發布版本（current_version=0）")

    ver_res = await session.execute(
        select(MotionModuleVersion)
        .where(
            MotionModuleVersion.module_id == data.module_id,
            MotionModuleVersion.version_no == target_ver_no,
        )
    )
    ver = ver_res.scalar_one_or_none()
    if ver is None:
        raise ModuleVersionNotFound(
            f"模組 {data.module_id} 版本 {target_ver_no} 不存在"
        )

    # 計算新 seq_no 起始值
    existing_rows = (await session.execute(
        select(WiRow.seq_no)
        .where(WiRow.worksheet_id == worksheet_id)
        .order_by(WiRow.seq_no.desc())
        .limit(1)
    )).scalar_one_or_none()
    next_seq = (existing_rows or 0) + 1

    # SIMO union-find（simo_pair_index 是陣列內 0-based 索引）
    # ADR-020：僅「宣告配對的從屬列」標記 simo_group_id（貢獻 0）；被指向的主列不標記。
    # 同一配對鏈的從屬列共用一個 gid（附配對資訊）。
    n = len(ver.rows)
    parent: list[int] = list(range(n))

    def _find(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    # 信任前提：版本 rows 應已在 publish/from-rows 寫入時通過 SIMO 守門。
    # 若仍出現非法值（舊版本資料、手改 DB），依 no-error-bypass 原則 raise
    # SIMO_PAIR_INVALID，而非靜默把該列當主列（Finding 4：與 publish 同口徑）。
    _validate_simo_pairs([row_data.get("simo_pair_index") for row_data in ver.rows])

    dependent_idx: list[int] = []
    for idx, row_data in enumerate(ver.rows):
        pi = row_data.get("simo_pair_index")
        if pi is not None:
            dependent_idx.append(idx)
            _union(idx, pi)

    simo_group_map: dict[int, str] = {}
    roots: dict[int, list[int]] = {}
    for idx in dependent_idx:
        roots.setdefault(_find(idx), []).append(idx)
    for g_counter, (_root, members) in enumerate(sorted(roots.items()), start=1):
        gid = f"SIMO-M{g_counter}"
        for m_idx in members:
            simo_group_map[m_idx] = gid

    # 展開列
    new_rows_out = []
    drift_warnings = []
    now = datetime.now(timezone.utc)

    for idx, row_data in enumerate(ver.rows):
        # 取 vocab refs
        vocab_refs: dict[str, Any] = row_data.get("vocab_refs") or {}
        obj_vid_raw = vocab_refs.get("object_vocab_id")
        obj_vid: uuid.UUID | None = None
        if obj_vid_raw is not None:
            try:
                obj_vid = uuid.UUID(str(obj_vid_raw))
            except ValueError as error:
                raise PublishValidationError(
                    idx,
                    "VOCAB_REF_INVALID",
                    f"object_vocab_id 不是合法 UUID：{obj_vid_raw}",
                ) from error

        def _optional_uuid(key: str) -> uuid.UUID | None:
            v = vocab_refs.get(key)
            if v is None:
                return None
            try:
                return uuid.UUID(str(v))
            except ValueError as error:
                raise PublishValidationError(
                    idx,
                    "VOCAB_REF_INVALID",
                    f"{key} 不是合法 UUID：{v}",
                ) from error

        from_vid = _optional_uuid("from_vocab_id")
        to_vid = _optional_uuid("to_vocab_id")
        tool_vid = _optional_uuid("tool_vocab_id")

        # 重算 cycle（用工序表 rule-set，非模組發布時的 rule-set）
        cycle_dict_raw: dict[str, Any] = row_data.get("cycle") or {}
        try:
            cycle_obj = CycleIn.model_validate(cycle_dict_raw)
            engine_cycle = cycle_in_to_engine(cycle_obj)
            result = compute_cycle(engine_cycle, rsdata)
        except (SequenceError, ValueError):
            # cycle 結構損壞或 rule-set 差異無法算 → 用模組快取值（有風險，附警示）
            result = None

        if result is not None:
            actual_tmu = result.total_tmu
            actual_seconds = result.total_seconds
            module_cached_tmu = float(row_data.get("_computed_tmu") or 0)
            if module_cached_tmu and abs(actual_tmu - module_cached_tmu) > 0.001:
                drift_warnings.append({
                    "row_index": idx,
                    "module_tmu": module_cached_tmu,
                    "actual_tmu": actual_tmu,
                    "delta": round(actual_tmu - module_cached_tmu, 3),
                })
        else:
            # fallback：使用模組發布時快取值
            actual_tmu = float(row_data.get("_computed_tmu") or 0)
            actual_seconds = round(actual_tmu * TMU_TO_SEC, 4)
            cycle_obj = CycleIn.model_validate(cycle_dict_raw) if cycle_dict_raw else None

        # ADR-023 §3.4：實體化寫入 most_cycles.slot_inputs（回放權威原始輸入）→ 回填實際使用的版本。
        # 涵蓋上面兩條分支（引擎重算成功 / 用模組快取值的 fallback），與 worksheet_service 同 helper。
        resolve_cycle_rule_set(cycle_obj, rs_row.code)

        new_row_id = uuid.uuid4()
        seq_no = next_seq + idx
        simo_gid = simo_group_map.get(idx)
        hand = row_data.get("hand")
        freq = float(row_data.get("frequency") or 1)

        session.add(WiRow(
            id=new_row_id,
            worksheet_id=worksheet_id,
            seq_no=seq_no,
            sub_activity=row_data.get("sub_activity"),
            hand=hand,
            object_vocab_id=obj_vid,
            from_vocab_id=from_vid,
            to_vocab_id=to_vid,
            tool_vocab_id=tool_vid,
            frequency=freq,
            simo_group_id=simo_gid,
            provenance="manual",   # TODO: 加 'module' 到 provenance CHECK 後改
            source_module_id=data.module_id,
            source_module_version=target_ver_no,
        ))

        if result is not None:
            session.add(MostCycle(
                id=uuid.uuid4(),
                wi_row_id=new_row_id,
                seq_kind=result.seq,
                rule_set_id=rs_row.id,
                slot_inputs=cycle_obj.model_dump(mode="json") if cycle_obj else {},
                computed={
                    "breakdown": [
                        {"letter": L, "tmu": t}
                        for L, t in zip(result.letters, result.slot_tmus)
                    ],
                    "tech_line": result.tech_line,
                },
                narrative_zh=None,
                total_tmu=actual_tmu,
                total_seconds=actual_seconds,
                computed_at=now,
            ))
        elif cycle_obj is not None:
            # fallback：store cycle 但 total 用模組快取值
            session.add(MostCycle(
                id=uuid.uuid4(),
                wi_row_id=new_row_id,
                seq_kind=cycle_obj.seq,
                rule_set_id=rs_row.id,
                slot_inputs=cycle_obj.model_dump(mode="json"),
                computed=None,
                narrative_zh=None,
                total_tmu=actual_tmu,
                total_seconds=actual_seconds,
                computed_at=now,
            ))

        session.add(LevelEntry(
            id=uuid.uuid4(),
            wi_row_id=new_row_id,
            worksheet_id=worksheet_id,
            raw_seconds=actual_seconds,
            coefficient=1.0,
        ))

        new_rows_out.append({
            "wi_row_id": str(new_row_id),
            "seq_no": seq_no,
            "sub_activity": row_data.get("sub_activity"),
            "hand": hand,
            "frequency": freq,
            "simo_group_id": simo_gid,
            "source_module_id": str(data.module_id),
            "source_module_version": target_ver_no,
            "total_tmu": actual_tmu,
            "total_seconds": actual_seconds,
        })

    await session.flush()
    # R1：append 後更新 content_hash（不另 bump；bump 已在前置做完）
    from ddm_v2.services.v2 import worksheet_service as ws_svc
    from ddm_v2.services.v2.worksheet_revision import content_hash_from_read, set_content_hash

    snap = await ws_svc.read_worksheet(session, worksheet_id)
    ch = content_hash_from_read(snap)
    await set_content_hash(session, worksheet_id=worksheet_id, content_hash=ch)
    await session.flush()
    return {
        "new_rows": new_rows_out,
        "tmu_drift": drift_warnings,
        "skipped_vocab_missing": 0,
        "revision_no": int(snap["revision_no"]),
        "content_hash": ch,
    }
