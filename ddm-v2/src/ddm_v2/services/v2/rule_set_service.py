"""rule-set 編輯/版本化服務（#1）。

治理（ADR-011 / 架構 §3）：
- 每個 rule-set 是一個版本（code 區分）；status draft/published/retired。
- 編輯只允許 draft；published 凍結（PUT → 409）。
- 建草稿＝clone 既有版本的全部子表為新 draft；發布＝draft→published。
- WI cycle 以 rule_set_id 快照，發布後改規則不影響舊單（須建新版本）。

ADR-023 §3.2 生命週期：status ∈ {draft,published,retired} × is_active ∈ {true,false}
- publish：draft → published，**須先過 validate_complete()**（引擎完整性契約）
- activate：published + validate_complete + 同交易全體 deactivate → 單一 activate（DB partial unique 兜底）
- retire：須先 deactivate；retired 為終態
⚠️ §3.4 鐵則：治理狀態只在「選擇」時生效，載入（load_rule_set_from_db）路徑永不過濾。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2 import rule_set_tables as rt
from ddm_v2.models.v2.audit import WorkflowAuditLog
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.most_engine.providers import load_rule_set_from_db
from ddm_v2.schemas.v2.rule_set_options import (
    BandInvalid,
    ParamInvalid,
    SectionInvalid,
    SectionRequired,
    resolve,
    validate_bands,
)
from ddm_v2.services.v2.audit_service import log_audit
from ddm_v2.services.v2.rule_set_diff import diff_full, section_row_counts, snapshot_digest


class RuleSetNotFound(Exception):
    pass


class RuleSetExists(Exception):
    pass


class NotEditable(Exception):
    pass


class CertifiedImmutable(NotEditable):
    """ADR-014 / ADR-023 §3.3 規則 3：certified_import 版本禁線上編輯（即使 status='draft'）。

    繼承 NotEditable 讓既有 handler 的 409 對映不必改；訊息不同以便使用者知道該走哪條路
    （認證版本要改值 → 改 JSON → 重跑 import_v3_dictionary.py → 新版本）。
    """


async def assert_editable(
    session: AsyncSession, code: str, *, not_draft_hint: str = "已凍結，請先建立草稿"
) -> RuleSet:
    """所有寫入端點共用的不可變 gate（ADR-023 §3.3 規則 1＋3）。

    404（不存在）→ 409（認證匯入）→ 409（非 draft）。單一實作＝不會有端點漏掛。

    `not_draft_hint` 只換非 draft 分支的「該怎麼辦」尾句：DELETE（D3b）走的是同一組
    前置條件與同一個順序，但「請先建立草稿」對想刪版本的人是錯誤指引。訊息可換、
    判斷順序不可分岔——所以是參數而不是第二份實作。
    """
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    if rs.provenance == "certified_import":
        raise CertifiedImmutable(
            f"rule-set {code} 為認證匯入版本，禁止線上編輯（ADR-014）；"
            "如需修改請改 minimost_ai_dictionary_v1.json 後重跑 scripts/import_v3_dictionary.py"
        )
    if rs.status != "draft":
        raise NotEditable(f"rule-set {code} 狀態為 {rs.status}，{not_draft_hint}")
    return rs


class NoActiveRuleSet(Exception):
    """全庫無 is_active 版本＝系統設定錯誤（非使用者錯誤）→ 500。"""


async def get_active_rule_set(session: AsyncSession) -> RuleSet:
    """取得唯一 active rule-set（ADR-023 §3.5：所有寫死 V1/V2 之處改讀此）。

    無 active → NoActiveRuleSet（設定錯誤，不得靜默 fallback 或回 None）。
    """
    rs = (await session.execute(select(RuleSet).where(RuleSet.is_active.is_(True)))).scalar_one_or_none()
    if rs is None:
        raise NoActiveRuleSet("系統無啟用中的 rule-set（請由管理者 activate 一個 published 版本）")
    return rs


async def get_active_rule_set_code(session: AsyncSession) -> str:
    return (await get_active_rule_set(session)).code


async def list_rule_sets(session: AsyncSession, selectable: bool = False) -> list[dict[str, Any]]:
    """版本清單。selectable=True → 只回 published+active（ADR-023 §3.4 規則 2，供 UI 下拉）。"""
    stmt = select(RuleSet).order_by(RuleSet.created_at)
    if selectable:
        stmt = stmt.where(RuleSet.status == "published", RuleSet.is_active.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id), "code": r.code, "name_zh": r.name_zh, "status": r.status,
            "multiplier": float(r.system_tmu_multiplier),
            "is_active": r.is_active, "provenance": r.provenance,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "notes": r.notes,
        }
        for r in rows
    ]


def _deterministic_order(model: Any) -> list[Any]:
    """全序的 ORDER BY：`sort_order` → 其餘內容欄 → `id`（D3 code-review MED-2）。

    為什麼不能只用 `sort_order`：`rule_a_bands` 三個 component 共用一張表且各自從 0 起算
    （`[0..6, 0..3, 0..4]`），`ORDER BY sort_order` 有三向 tie 且無 tiebreaker →
    `GET /full` / `/export` 的 `a_bands` 順序跨次呼叫不保證相同（API 非決定性），
    以位置比對的 round-trip 測試也就建立在運氣上。

    為什麼 tiebreaker 不能只加 `id`：子表主鍵是 `uuid4()`，匯入時會重新產生，
    **跨版本不可比**。只加 id 能修好單一版本內的決定性，卻會讓「來源版本」與
    「匯入版本」的 tie 群組各自排出不同順序 → round-trip 反而變成隨機紅燈。
    故 tiebreaker 取**內容欄**（跨版本相同內容 → 相同順序），`id` 只當最後兜底
    （唯有整列完全相同才會用到，那時順序不可觀測）。
    """
    from sqlalchemy import inspect as sa_inspect

    content = [
        getattr(model, c.key)
        for c in sa_inspect(model).mapper.column_attrs
        if c.key not in ("id", "rule_set_id", "sort_order")
    ]
    return [model.sort_order, *content, model.id]


async def _rows(session: AsyncSession, model: type, rs_id: uuid.UUID) -> list[Any]:
    return list((await session.execute(
        select(model).where(model.rule_set_id == rs_id).order_by(*_deterministic_order(model))
    )).scalars().all())


async def load_full(session: AsyncSession, code: str) -> dict[str, Any]:
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    return {
        "id": str(rs.id),
        "code": rs.code, "name_zh": rs.name_zh, "status": rs.status, "multiplier": float(rs.system_tmu_multiplier),
        "a_bands": [{"component": r.component, "max_value": float(r.max_value) if r.max_value is not None else None, "index": r.index_value, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleABand, rs.id)],
        "b": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "index": r.index_value, "is_default": r.is_default, "sentence_text_zh": r.sentence_text_zh, "sentence_text_en": r.sentence_text_en, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleBOption, rs.id)],
        "g": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "modifier_key": r.modifier_key, "requires_modifier": r.requires_modifier, "base_tmu": r.base_tmu, "sentence_text_zh": r.sentence_text_zh, "sentence_text_en": r.sentence_text_en, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleGAction, rs.id)],
        "p_bases": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "category": r.category, "direction_mode": r.direction_mode, "base_tmu": r.base_tmu, "sentence_text_zh": r.sentence_text_zh, "sentence_text_en": r.sentence_text_en, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RulePBase, rs.id)],
        "p_addons": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "delta": r.delta_tmu, "needs_precision": r.needs_precision, "max_select": r.max_select, "display_rule": r.display_rule, "sentence_text_zh": r.sentence_text_zh, "sentence_text_en": r.sentence_text_en, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RulePAddon, rs.id)],
        "m_ladder": [{"max_cm": float(r.max_cm) if r.max_cm is not None else None, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMLadderBand, rs.id)],
        "m_foot": [{"max_cm": float(r.max_cm) if r.max_cm is not None else None, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMFootBand, rs.id)],
        "m_verbs": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "pricing_kind": r.pricing_kind, "fixed_tmu": r.fixed_tmu, "sentence_text_zh": r.sentence_text_zh, "sentence_text_en": r.sentence_text_en, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMVerb, rs.id)],
        "m_rotation": [{"max_diameter_cm": float(r.max_diameter_cm) if r.max_diameter_cm is not None else None, "revolutions": r.revolutions, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMRotationBand, rs.id)],
        "m_hand": [{"max_deg": float(r.max_deg) if r.max_deg is not None else None, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMHandBand, rs.id)],
        "x": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "mode": r.mode, "fixed_seconds": float(r.fixed_seconds) if r.fixed_seconds is not None else None, "sentence_text_zh": r.sentence_text_zh, "sentence_text_en": r.sentence_text_en, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleXOption, rs.id)],
        "i": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "index": r.index_value, "vision_scope": r.vision_scope, "sentence_text_zh": r.sentence_text_zh, "sentence_text_en": r.sentence_text_en, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleIOption, rs.id)],
    }




def validate_full_bands(full: dict[str, Any]) -> None:
    """對 `PUT /full` 的 payload 套用與選項級 `PUT /bands` **完全相同**的帶界契約。

    為什麼必要（D2 code-review HIGH-2）：ADR-023 §2 之所以規定帶表「只提供整組替換」，
    立論是「逐筆增刪會產生非法中間態」。但 `PUT /full` 若不驗證，等於開了一扇後門把
    這個立論架空——而且 rotation 特別危險：`rule_set_data.build_rule_set_data` 對
    `m_rotation` 是 `tuple(m_rotation_rows)`，**唯一不經 `_sort_bands` 的帶族**，
    完全依賴 `order_by(sort_order)`。若 overflow 帶（max=null）排在有限帶之前，
    `rotation_tmu()` 的首次匹配就會命中 overflow → **靜默回傳錯誤 TMU**（不報錯）。

    A 依 component 分三組各自驗（含 reach/foot 的 open-ended 強制）；
    M 四張帶表各自驗。空/未提供的區塊跳過（不插入就無從違規）。
    """
    a_rows = full.get("a_bands") or []
    for comp in ("reach", "twist", "foot"):
        group = [r for r in a_rows if r.get("component") == comp]
        if group:
            validate_bands(resolve("A", comp), group)
    for key, section in (("m_ladder", "ladder"), ("m_foot", "foot"),
                         ("m_rotation", "rotation"), ("m_hand", "hand")):
        rows = full.get(key) or []
        if rows:
            validate_bands(resolve("M", section), rows)


async def _exists(session: AsyncSession, code: str) -> bool:
    return (await session.execute(select(RuleSet.id).where(RuleSet.code == code))).first() is not None


async def _auto_draft_code(session: AsyncSession, src_code: str) -> str:
    """缺省草稿 code：{code}_DRAFT_{YYYYMMDDHHMM}；已存在則附序號（同分鐘連按不得撞 UNIQUE）。"""
    base = f"{src_code}_DRAFT_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
    if not await _exists(session, base):
        return base
    for n in range(2, 100):
        candidate = f"{base}_{n}"
        if not await _exists(session, candidate):
            return candidate
    raise RuleSetExists(base)


async def clone_draft(
    session: AsyncSession, code: str, new_code: str | None, name_zh: str | None,
    actor: str | None = None,
) -> dict[str, Any]:
    """由既有版本 clone 出一個 draft（ADR-023 §3.2）。

    稽核（D7 / H-1）：這是**值改動鏈的起點**——「clone 草稿 → 改值 → 請人發布」原本
    整條鏈只有最後一步（publish，記的是覆核者）留下紀錄。

    payload 存 `source_code` ＋ `snapshot_sha256` ＋ 各區塊列數，**不存整份值快照**：
    clone 出來的內容依定義逐欄等於來源版本，而
    (a) 之後對這個 draft 的每一次改值都有前後值稽核（option CRUD／`PUT /full`），
    (b) 來源版本若被刪除，`delete_rule_set` 會存下它的完整快照，
    所以「這個 draft 當初是什麼值」在稽核鏈上恆可還原，hash 只負責釘死「當初 clone 的
    是不是這份內容」。存第二份全量快照只會讓每次 clone 多寫數百 KB 的重複資料。
    """
    src = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if src is None:
        raise RuleSetNotFound(code)
    if new_code is None:
        new_code = await _auto_draft_code(session, code)
    elif await _exists(session, new_code):
        raise RuleSetExists(new_code)
    full = await load_full(session, code)
    new_rs = RuleSet(id=uuid.uuid4(), code=new_code, name_zh=name_zh or (src.name_zh + " (草稿)"),
                     status="draft", system_tmu_multiplier=src.system_tmu_multiplier,
                     is_active=False, provenance="cloned")
    session.add(new_rs)
    await session.flush()
    _insert_children(session, new_rs.id, full)
    await session.flush()
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=new_rs.id,
        action="clone_draft",
        from_status=None,
        to_status="draft",
        actor=actor or "unknown",
        payload={
            "code": new_code,
            "source_code": code,
            "source_status": src.status,
            "source_is_active": src.is_active,
            "provenance": "cloned",
            "multiplier": float(src.system_tmu_multiplier),
            "row_counts": section_row_counts(full),
            "snapshot_sha256": snapshot_digest(full),
        },
    )
    await session.flush()
    return {"code": new_code, "status": "draft", "provenance": "cloned"}


# ══════════════════════════════════════════════════════════════════
# 匯出／匯入（ADR-023 §3.6 / D3）
# ══════════════════════════════════════════════════════════════════

EXPORT_SCHEMA_VERSION = "1"

# 匯出負載中「描述這次匯出」而非「描述字典內容」的欄位。
# 匯入時一律忽略（它們不是 PUT /full 的輸入），round-trip 對稱性以「去掉這三欄即可 PUT」定義。
EXPORT_METADATA_KEYS = ("schema_version", "exported_at", "exported_by")

# `load_full()` 產出的 12 個子表區塊鍵。**負載必須每一個鍵都在**（值可以是空陣列）。
# 這條「鍵存在性」檢查與「非空」檢查是兩件事，見 _assert_sections。
FULL_SECTION_KEYS = (
    "a_bands", "b", "g", "p_bases", "p_addons", "m_ladder", "m_foot",
    "m_verbs", "m_rotation", "m_hand", "x", "i",
)

# 必須**非空**的子表（與 validate_active_options / RuleSetData.validate_complete 的必要集合對齊）。
REQUIRED_IMPORT_SECTIONS = ("b", "g", "p_bases", "m_ladder", "m_verbs", "x", "i")
REQUIRED_A_COMPONENTS = ("reach", "twist", "foot")

# 「空表 → 引擎**靜默**改用別的表算」的區塊。空是合法的（V1 本來就沒有 foot 表，
# 回退是回放相容所需），但必須在匯入當下就講出來，不能等到工時已經低估 40–70% 才發現。
# 判準是「缺席時引擎是否給顯式錯誤」——p_addons→P_ADDON_UNKNOWN、m_rotation→M_ROTATION_RANGE、
# m_hand→M_HAND_RANGE 都會報錯，只有 m_foot 是 `rule_set_data.foot_tmu` 靜默回退 `ladder_tmu`。
SILENT_FALLBACK_SECTIONS: dict[str, str] = {
    "m_foot": "m_foot 為空：腳步動作將回退至距離階梯表計算",
}


class PayloadInvalid(ValueError):
    """負載結構/欄位不合法（缺區塊鍵、欄位缺漏、型別錯誤、multiplier 非正數）→ 400。

    ADR-023 §3.6：缺子表**不得**靜默建立不完整版本（那會產生一個 publish 時才炸、
    或更糟——activate 後才在 runtime 靜默算錯值的版本，見 SILENT_FALLBACK_SECTIONS）。
    """


# `load_full()`／匯出負載的區塊鍵 → (param, section, 區塊鍵名 → schema 欄位名)。
# section=None＝逐列由 `component` 欄決定（A 三分量共用一張表）。
# dict 的插入順序＝子表寫入順序（與 D3 之前的手寫版本一致，勿重排）。
_SECTION_SCHEMA_MAP: dict[str, tuple[str, str | None, dict[str, str]]] = {
    "a_bands": ("A", None, {"index": "index_value", "sort": "sort_order"}),
    "b": ("B", "default", {"index": "index_value", "sort": "sort_order"}),
    "g": ("G", "default", {"sort": "sort_order"}),
    "p_bases": ("P", "base", {"sort": "sort_order"}),
    "p_addons": ("P", "addon", {"delta": "delta_tmu", "sort": "sort_order"}),
    "m_ladder": ("M", "ladder", {"sort": "sort_order"}),
    "m_foot": ("M", "foot", {"sort": "sort_order"}),
    "m_verbs": ("M", "verb", {"sort": "sort_order"}),
    "m_rotation": ("M", "rotation", {"sort": "sort_order"}),
    "m_hand": ("M", "hand", {"sort": "sort_order"}),
    "x": ("X", "default", {"sort": "sort_order"}),
    "i": ("I", "default", {"index": "index_value", "sort": "sort_order"}),
}

assert set(_SECTION_SCHEMA_MAP) == set(FULL_SECTION_KEYS)


def _prepare_row(section_key: str, index: int, row: Any) -> tuple[Any, dict[str, Any]]:
    """把一列負載轉成「已過欄位級契約」的 ORM kwargs（ADR-023 D7 / M-1）。

    為什麼必須存在：`import` 與 `PUT /full` 原本是直接 `int(r["base_tmu"])` 寫進 DB，
    **完全繞過** `schemas/v2/rule_set_options.py` 的 `Field(ge=0)`，而 DB 的 CHECK 只覆蓋
    列舉欄、數值欄沒有 CHECK。結果是 `base_tmu: -50` 一路綠燈通過
    import → validate_complete（只看表在不在，不看值）→ publish → activate，
    最後在 runtime 產出**負的 TMU**——比「把值改小」更難目視察覺。

    契約來源沿用選項級 CRUD 的同一組 schema（`OptionSpec.resolve()` 的分派表），
    所以 `PUT /options/{code}` 擋得住的值，這兩條路徑也擋得住——不會有第二套數值契約。

    欄位取值刻意**白名單**（只取 schema 宣告的欄位，其餘忽略），與改動前的行為一致：
    本次修的是「數值契約被繞過」，不順手把未知欄位從忽略改成 422（那會影響既有呼叫端，
    屬另一個決策）。值為 None 的欄一律不傳、交給 schema 預設——12 個 schema 裡所有
    可為 None 的欄位其預設都正是 None，故語意不變。
    """
    param, section, renames = _SECTION_SCHEMA_MAP[section_key]
    if not isinstance(row, dict):
        raise PayloadInvalid(f"{section_key}[{index}] 不是物件（收到 {type(row).__name__}）")
    if section is None:
        section = str(row.get("component") or "").strip() or None
    try:
        spec = resolve(param, section)
    except (ParamInvalid, SectionInvalid, SectionRequired) as e:
        raise PayloadInvalid(f"{section_key}[{index}] 的 component 不合法：{e}") from e

    src = dict(row)
    for old, new in renames.items():
        if old in src:
            src.setdefault(new, src[old])
    kwargs = {f: src[f] for f in spec.schema.model_fields if src.get(f) is not None}
    kwargs.setdefault("sort_order", index)
    # is_active 只保留「明寫 null → False」這個特例（`kwargs` 的建法會把 None 濾掉，
    # 落到 schema 預設 True，與既有語意相反），其餘一律交給 schema 驗。
    #
    # 不可以寫 `bool(src.get("is_active", True))`（D7b · L-1）：`bool("false") is True`，
    # 而離線編輯/CSV 轉出的 JSON 很常把布林寫成字串——那會把「停用」靜默翻成「啟用」，
    # 直接改變引擎讀得到的選項集合。交給 Pydantic 則 "false"/"0" 正確解析為 False，
    # 無法解讀的字串（"maybe"）走既有的 PayloadInvalid → 400，而不是被脅迫成 True。
    raw_is_active = src.get("is_active", True)
    kwargs["is_active"] = False if raw_is_active is None else raw_is_active

    try:
        values: dict[str, Any] = spec.schema.model_validate(kwargs).model_dump()
    except PydanticValidationError as e:
        detail = "；".join(
            f"{'.'.join(str(x) for x in err['loc']) or '(整列)'}={err.get('input')!r} → {err['msg']}"
            for err in e.errors()
        )
        raise PayloadInvalid(f"{section_key}[{index}] 欄位不合法（{detail}）") from e
    if spec.filter_field is not None:  # A 三分量共用一張表：component 不在 schema 內但要落盤
        values[spec.filter_field] = spec.filter_value
    return spec.model, values


def validate_children_values(full: dict[str, Any]) -> None:
    """對 12 個區塊的每一列跑欄位級契約（不寫入）。

    必須在 `replace_children` **刪除既有子表之前**呼叫：否則一份含負數 TMU 的負載會先把
    整份字典刪掉、再在插入時才失敗，留下「驗證失敗但資料已毀」的中間態。
    """
    for section_key in _SECTION_SCHEMA_MAP:
        for i, row in enumerate(full.get(section_key) or []):
            _prepare_row(section_key, i, row)


def _insert_children(session: AsyncSession, rs_id: uuid.UUID, full: dict[str, Any]) -> None:
    for section_key in _SECTION_SCHEMA_MAP:
        for i, row in enumerate(full.get(section_key) or []):
            model, values = _prepare_row(section_key, i, row)
            session.add(model(id=uuid.uuid4(), rule_set_id=rs_id, **values))


async def export_full(session: AsyncSession, code: str, exported_by: str | None) -> dict[str, Any]:
    """匯出一個版本（ADR-023 §3.6）。

    形狀＝`load_full()` ＋ 三個 metadata 欄。**刻意不輸出 minimost_ai_dictionary_v1.json 格式**：
    那份 JSON 是**輸入**（JSON → import_v3_dictionary.py → seed → DB），反向產生會製造
    第二個值權威來源（ADR-014）。
    """
    full = await load_full(session, code)
    full["schema_version"] = EXPORT_SCHEMA_VERSION
    full["exported_at"] = datetime.now(timezone.utc).isoformat()
    full["exported_by"] = exported_by
    return full


def _assert_sections(payload: dict[str, Any], *, source: str) -> None:
    """區塊層驗證：**鍵存在性** ＋ 必要區塊非空（D3 code-review HIGH-1）。

    兩層之所以要分開：`load_full()` 對空表也會輸出 `"m_foot": []`，所以
    「鍵在但陣列空」＝來源版本真的沒有那張表（例如 V1），是**合法**的匯入；
    而「鍵整個不見」＝負載被手動編輯或工具 round-trip 弄丟了一個區塊，
    必須擋下——否則 m_foot 掉了會讓 `foot_tmu()` 靜默回退 `ladder_tmu()`
    （≤10cm 的腳步動作低估 40–70%），且 `validate_complete()` 與
    `validate_active_options()` 都不檢查 m_foot，publish/activate 全程無警告。
    """
    absent = [k for k in FULL_SECTION_KEYS if k not in payload]
    if absent:
        raise PayloadInvalid(
            f"{source}負載缺少區塊：{', '.join(absent)}（疑似手動編輯遺漏；"
            f"若該表本來就沒有資料請給空陣列 []，不要整個刪掉——"
            f"缺 m_foot 會讓腳步動作靜默改用距離階梯表計算）"
        )
    empty = [k for k in REQUIRED_IMPORT_SECTIONS if not payload.get(k)]
    a_rows = payload.get("a_bands") or []
    empty += [
        f"a_bands[{c}]" for c in REQUIRED_A_COMPONENTS
        if not [r for r in a_rows if isinstance(r, dict) and r.get("component") == c]
    ]
    if empty:
        raise PayloadInvalid(
            f"{source}負載的必要子表是空的：{', '.join(empty)}（不得建立不完整版本）"
        )


def _assert_multiplier(payload: dict[str, Any]) -> None:
    """`system_tmu_multiplier` 會等比縮放該版本**每一個** TMU，故型別與正負都要擋。

    未驗證時 `"abc"` → asyncpg DataError 500；`0`/負數則會被接受並靜默把整個版本
    的工時歸零或反號（D3 code-review MED-1）。
    """
    mult = payload.get("multiplier")
    if mult is None:
        return
    if isinstance(mult, bool) or not isinstance(mult, (int, float)) or mult <= 0:
        raise PayloadInvalid(
            f"multiplier 必須是正數，收到 {mult!r}（它會等比縮放此版本的所有 TMU）"
        )


def payload_warnings(payload: dict[str, Any]) -> list[str]:
    """建立版本時要對使用者講出來的「合法但會改變計算路徑」情況。"""
    return [msg for key, msg in SILENT_FALLBACK_SECTIONS.items() if not payload.get(key)]


def _validate_payload(payload: dict[str, Any], *, source: str) -> None:
    """區塊 → multiplier → 帶界，一組驗證供 import 與 `PUT /full` 共用。

    帶界驗證（`validate_full_bands`）必須包在型別 guard 內：手動編輯最常見的錯誤
    （帶列缺 `max_cm` / 缺 `revolutions` / 帶列根本不是 dict）是在 `validate_bands`
    **內部**拋 KeyError/TypeError，不是在 `_insert_children`——D3 初版把 guard 掛在
    後者，導致 6 種畸形負載有 5 種回 500（code-review HIGH-2）。
    """
    _assert_sections(payload, source=source)
    _assert_multiplier(payload)
    try:
        validate_full_bands(payload)
    except BandInvalid:
        raise  # 帶界契約違反：訊息已經是給人看的，原樣往上（端點對映 400）
    except (KeyError, TypeError, AttributeError, IndexError) as e:
        raise PayloadInvalid(f"{source}負載的帶（band）列欄位不合法：{e!r}") from e
    # D7 / M-1：欄位級數值契約（負 TMU 等）。**必須在任何寫入之前**——`replace_children`
    # 會先 DELETE 全部子表再插入，若留到插入時才失敗，一份非法負載就能把整份字典刪光。
    validate_children_values(payload)


def _assert_importable(payload: dict[str, Any]) -> None:
    got = payload.get("schema_version")
    if got is None:
        raise PayloadInvalid(
            f"匯入負載缺 schema_version（本系統接受 '{EXPORT_SCHEMA_VERSION}'）"
        )
    # 型別也要嚴格（不做 str() 寬鬆比對）：契約寫的是字串 "1"，JSON number 1 是另一種型別，
    # 靜默接受等於把版本協商變成猜測。
    if not isinstance(got, str) or got != EXPORT_SCHEMA_VERSION:
        raise PayloadInvalid(
            f"不支援的 schema_version={got!r}，本系統只接受 '{EXPORT_SCHEMA_VERSION}'"
        )
    _validate_payload(payload, source="匯入")


async def import_draft(
    session: AsyncSession,
    payload: dict[str, Any],
    new_code: str | None,
    name_zh: str | None,
    actor: str | None = None,
) -> dict[str, Any]:
    """由匯出負載建立新草稿（ADR-023 §3.6）。

    **只建 `status='draft', provenance='manual'`**——匯入來源是離線編輯過的檔案，
    既非認證匯入（那條路只走 `scripts/import_v3_dictionary.py` ＋ git ＋ CI Gate 3），
    也不是 clone。要上線必須再走 publish/activate 的既有把關。

    驗證順序：schema_version → 區塊鍵/必要子表非空 → multiplier → 帶界（與 `PUT /full`
    同一組 `_validate_payload`，否則 import 會成為繞過帶界契約的後門）→ code 查重 → 才寫入。
    """
    _assert_importable(payload)

    src_code = str(payload.get("code") or "IMPORTED")
    if new_code is None:
        new_code = await _auto_draft_code(session, src_code)
    elif await _exists(session, new_code):
        raise RuleSetExists(new_code)

    multiplier = payload.get("multiplier")
    rs = RuleSet(
        id=uuid.uuid4(),
        code=new_code,
        name_zh=name_zh or payload.get("name_zh") or new_code,
        status="draft",
        system_tmu_multiplier=multiplier if multiplier is not None else 1,
        is_active=False,
        provenance="manual",
    )
    session.add(rs)
    await session.flush()
    try:
        _insert_children(session, rs.id, payload)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        # 欄位缺漏/型別錯誤：明確回 400 並附欄位名，不得讓它變成 500，也不得補預設值蒙混。
        raise PayloadInvalid(f"匯入負載欄位不合法：{e!r}") from e
    try:
        # flush 單獨包：這裡只可能是 DB 層的型別/約束錯（例如 sort:"x" → DataError），
        # 上面那個 guard 不含 flush，才不會把真正的內部 TypeError 誤報成使用者輸入問題（LOW-1）。
        await session.flush()
    except DBAPIError as e:
        raise PayloadInvalid(f"匯入負載欄位型別不合法（資料庫拒收）：{e.orig!r}") from e
    # 稽核錨點（D7b · M-2）：digest 與列數取自**落盤後**的 `load_full()`，與 `clone_draft`
    # 同一組函式、同一個產生器——同樣的內容在兩條路徑上得到同樣的 digest，才比對得起來。
    #
    # 為什麼 import 特別需要這個：clone 的來源在庫內、delete 有全量快照，唯獨 import 的
    # 來源是一份系統外的離線 JSON（系統裡沒有副本）。它是「外部撰寫的值進入系統的唯一
    # 入口」，若稽核只記 {code, source_code, provenance}，事後問「這份 draft 匯入當下是
    # 什麼值」就完全無錨點——連「後來有沒有被改過」都答不出來。
    stored = await load_full(session, new_code)
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs.id,
        action="import",
        from_status=None,
        to_status="draft",
        actor=actor or "unknown",
        payload={
            "code": new_code,
            "source_code": src_code,
            "provenance": "manual",
            "multiplier": float(rs.system_tmu_multiplier),
            "row_counts": section_row_counts(stored),
            "snapshot_sha256": snapshot_digest(stored),
        },
    )
    await session.flush()
    return {
        "code": new_code, "status": "draft", "provenance": "manual",
        # 合法但會改變計算路徑的情況要在匯入當下講出來（HIGH-1 第 3 點）
        "warnings": payload_warnings(payload),
    }


async def replace_children(
    session: AsyncSession, code: str, full: dict[str, Any], actor: str | None = None
) -> dict[str, Any]:
    """整份 12 張子表替換（`PUT /full`）。

    稽核（D7 / H-1）：這是**改「值」最強力的一條路徑**，原本完全無紀錄。
    payload 存的是逐區塊逐列的**前後值差異**（`rule_set_diff.diff_full`）＋ 12 區塊的
    前後列數，而不是兩份全量快照：
    - 只存列數還原不了值（資安席對 delete 的同一項指摘）；
    - 存兩份全量快照則每次 PUT 都寫兩倍字典（絕大多數 PUT 只動幾列），
      而 diff 已完整回答「改了哪個參數的哪個選項、從什麼變成什麼」——
      真的整份換掉時 diff 自然退化成全量，資訊不會少。
    """
    # ADR-023 §3.3 規則 3 明文：「任何選項級寫入**或 PUT /full**一律 409」——
    # 故整份替換與選項級 CRUD 共用同一 gate（certified_import 也擋）。
    rs = await assert_editable(session, code)
    # D2 HIGH-2：帶界契約與 PUT /bands 同源，PUT /full 不得繞過（見 validate_full_bands）。
    # D3 HIGH-1/HIGH-2：區塊鍵存在性、multiplier 正數、帶列型別 guard 與 import 同源——
    # 這條路徑同樣是「建立版本內容」，掉了 m_foot 一樣會靜默回退 ladder。
    # 既有呼叫端（前端字典 UI 與 4 支整合測試）一律送完整 `GET /full` 負載，故不破壞既有契約。
    _validate_payload(full, source="")
    before = await load_full(session, code)  # 稽核用前值快照：必須在刪除子表之前取
    if "name_zh" in full and full["name_zh"]:
        rs.name_zh = full["name_zh"]
    if "multiplier" in full and full["multiplier"] is not None:
        rs.system_tmu_multiplier = full["multiplier"]
    for model in (rt.RuleABand, rt.RuleBOption, rt.RuleGAction, rt.RulePBase, rt.RulePAddon,
                  rt.RuleMLadderBand, rt.RuleMFootBand, rt.RuleMVerb, rt.RuleMRotationBand, rt.RuleMHandBand, rt.RuleXOption, rt.RuleIOption):
        await session.execute(delete(model).where(model.rule_set_id == rs.id))
    await session.flush()
    try:
        _insert_children(session, rs.id, full)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        raise PayloadInvalid(f"負載欄位不合法：{e!r}") from e
    try:
        await session.flush()
    except DBAPIError as e:
        raise PayloadInvalid(f"負載欄位型別不合法（資料庫拒收）：{e.orig!r}") from e
    after = await load_full(session, code)
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs.id,
        action="update_full",
        from_status=rs.status,
        to_status=rs.status,
        actor=actor or "unknown",
        payload={"code": code, "diff": diff_full(before, after)},
    )
    await session.flush()
    # 回應維持 `load_full()` 形狀（export/PUT 對稱性的地基），故 warnings 不併進本回應；
    # 空 m_foot 的提示由 import 端點負責（該處是「新建版本」的入口）。
    return after


async def diff_against_active(session: AsyncSession, code: str) -> dict[str, Any]:
    """`code` 相對**目前 active 版本**的值差異（ADR-023 D7 / H-1 第 3 點）。

    為什麼基準是 active 而不是 clone 來源：發布/啟用這一版之後，被取代的東西就是
    現在 active 的那一版——那才是覆核者需要看的「差在哪」。
    （`rule_sets` 也沒有指向 clone 來源的欄位，且不值得為此加 migration。）

    無 active → `NoActiveRuleSet`（§3.5：設定錯誤，不靜默 fallback）。
    `code` 本身就是 active 時 diff 為空（`summary.identical=true`），不是錯誤。

    **血緣揭露（D7b）**：若 target 是從**非 active** 的版本 clone 出來的，這份 diff 就
    混了兩件事——「兩條血緣本來就有的落差」與「作者這次真正編輯的內容」。覆核者若不
    知情會把前者誤讀成後者。故回應附上 clone 來源（查 `workflow_audit_log` 的
    `clone_draft` 紀錄，不需 migration）與 `base_is_source` 旗標；`false` 時另附
    `lineage_note` 明說「基準非本版之來源」。查不到 clone 紀錄（手動匯入/認證匯入/
    D7 之前建立的舊版本）→ `source_code=None`、`base_is_source=None`（不知道就說不知道，
    不要猜成 True）。
    """
    target = await load_full(session, code)          # 不存在 → RuleSetNotFound（404）
    active = await get_active_rule_set(session)
    base = await load_full(session, active.code)
    source_code = await _clone_source_code(session, uuid.UUID(target["id"]))
    base_is_source = None if source_code is None else (source_code == active.code)
    result: dict[str, Any] = {
        "target_code": code,
        "target_status": target.get("status"),
        "base_code": active.code,          # 比較基準版本 code：回應必須標明
        "base_is_active": True,
        "compared_with_self": active.code == code,
        "source_code": source_code,        # 本版 clone 自哪一版（無 clone 紀錄 → None）
        "base_is_source": base_is_source,
        "diff": diff_full(base, target),
    }
    if base_is_source is False:
        result["lineage_note"] = (
            f"比較基準是目前 active 的 {active.code}，但本版是從 {source_code} clone 出來的"
            "——下列差異同時包含「兩版之間本來就有的落差」與「本版被編輯的內容」，"
            "不可全部視為作者這次的改動。"
        )
    return result


async def _clone_source_code(session: AsyncSession, rs_id: uuid.UUID) -> str | None:
    """由稽核紀錄回推此版本 clone 自哪一版（最新一筆 `clone_draft`）。

    `rule_sets` 沒有指向來源的欄位，而 `clone_draft` 的稽核 payload 已存 `source_code`
    ——讀既有紀錄即可，不必為此加 migration/欄位。
    """
    row = (await session.execute(
        select(WorkflowAuditLog.payload)
        .where(
            WorkflowAuditLog.entity_type == "rule_set",
            WorkflowAuditLog.entity_id == rs_id,
            WorkflowAuditLog.action == "clone_draft",
        )
        .order_by(WorkflowAuditLog.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not isinstance(row, dict):
        return None
    src = row.get("source_code")
    return src if isinstance(src, str) else None


async def validate_active_options(session: AsyncSession, rs_id: uuid.UUID, code: str) -> None:
    """治理層完整性：每個**必要**參數至少要有一個 is_active=true 的列（ADR-023 D2）。

    與 `RuleSetData.validate_complete()` 的必要表集合對齊（A 三分量 / B / G / P.base /
    M.ladder / M.verb / X / I）；p_addons、m_foot、m_rotation、m_hand 為選配，不檢查。
    錯誤型別沿用 `RuleSetIncomplete` → 端點既有的 409 對映不必改。
    """
    from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete

    missing: list[str] = []

    async def _count_active(model: Any, *extra: Any) -> int:
        stmt = select(func.count()).select_from(model).where(
            model.rule_set_id == rs_id, model.is_active.is_(True), *extra
        )
        return int((await session.execute(stmt)).scalar_one())

    for comp in ("reach", "twist", "foot"):
        if await _count_active(rt.RuleABand, rt.RuleABand.component == comp) == 0:
            missing.append(f"a_bands[{comp}]")
    for label, model in (
        ("b_options", rt.RuleBOption),
        ("g_actions", rt.RuleGAction),
        ("p_bases", rt.RulePBase),
        ("m_ladder", rt.RuleMLadderBand),
        ("m_verbs", rt.RuleMVerb),
        ("x_options", rt.RuleXOption),
        ("i_options", rt.RuleIOption),
    ):
        if await _count_active(model) == 0:
            missing.append(label)
    if missing:
        raise RuleSetIncomplete(
            f"rule-set '{code}' 下列參數沒有任何啟用中的選項：{', '.join(missing)}"
        )


async def publish(session: AsyncSession, code: str, actor: str | None = None) -> dict[str, Any]:
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    if rs.status != "draft":
        raise NotEditable(f"rule-set {code} 狀態為 {rs.status}")
    # ADR-023 §3.2：發布前驗證＝引擎自己的完整性契約（RuleSetIncomplete → 409），
    # 保證 activate 後不會 runtime 才炸。
    (await load_rule_set_from_db(session, code)).validate_complete()
    # D2 補：引擎的 validate_complete 看不到 is_active（§3.4 鐵則——引擎不看治理狀態），
    # 所以「表有列、但全部停用」會通過引擎檢查卻讓 UI 端無任何選項可選。
    # 這一層是治理檢查，故留在 service 而非引擎。
    await validate_active_options(session, rs.id, code)
    rs.status = "published"
    rs.published_at = datetime.now(timezone.utc)
    rs.published_by = actor
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs.id,
        action="publish",
        from_status="draft",
        to_status="published",
        actor=actor or "unknown",
    )
    await session.flush()
    return {"code": code, "status": "published"}


async def activate(session: AsyncSession, code: str, actor: str | None = None) -> dict[str, Any]:
    """啟用單一 rule-set（ADR-023 §3.2/規則 4 雙重把關）。

    前置：status='published'（否則 NotEditable→400）＋ validate_complete()（否則 RuleSetIncomplete→409）。
    同交易先全體 deactivate → flush → 設目標 true；DB 的 partial unique index 兜底併發。
    """
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    if rs.status != "published":
        raise NotEditable(f"rule-set {code} 狀態為 {rs.status}，僅 published 版本可啟用")
    (await load_rule_set_from_db(session, code)).validate_complete()

    # 冪等：本來就是 active → 不重複寫 audit，但以 changed=false 讓呼叫端能區分
    # 「這次真的切換了」與「本來就是這一版」（否則稽核軌跡與回應都分不出來）。
    if rs.is_active:
        return {"code": code, "status": rs.status, "is_active": True, "changed": False}

    await session.execute(update(RuleSet).where(RuleSet.is_active.is_(True)).values(is_active=False))
    await session.flush()
    rs.is_active = True
    await session.flush()
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs.id,
        action="activate",
        from_status=rs.status,
        to_status=rs.status,
        actor=actor or "unknown",
        payload={"code": code, "is_active": True},
    )
    await session.flush()
    return {"code": code, "status": rs.status, "is_active": True, "changed": True}


class RuleSetActive(NotEditable):
    """啟用中版本不得刪除（防呆；draft 理論上不會 active，但顯式擋，不靠推論）。"""


class RuleSetInUse(Exception):
    """版本已被歷史資料引用 → 不可刪（ADR-023 §3.4 回放鐵則）。

    刪掉一個被 cycle/module 版本引用的 rule-set，會讓那些歷史資料再也載不到規則版本
    （`load_rule_set_from_db` 依鐵則不做治理狀態過濾，它只會找不到列）。
    DB 的 RESTRICT FK（清單見 `_RESTRICT_REFERRERS`）是最後防線；這一層先攔下來，
    才能回可讀的 409＋引用數，而不是 IntegrityError 500。
    """

    def __init__(self, code: str, refs: dict[str, int]) -> None:
        self.code = code
        self.refs = refs
        detail = "、".join(f"{k}={v}" for k, v in refs.items() if v)
        super().__init__(
            f"rule-set {code} 已被歷史資料引用（{detail}），不可刪除——"
            "刪除會讓那些資料無法回放當時的規則版本（ADR-023 §3.4）"
        )


# 對 rule_sets 具 ondelete='RESTRICT' 的引用方（與 DB 一致；見 v2_0001/v2_0011/v2_0026/v2_0028 migration）。
# 這些表任一有列指向本版本，刪除都必須先被擋下。CASCADE 的 12 張規則子表 ＋
# rule_option_synonyms 屬於「版本自身的內容」，由 DB 級聯清掉，不算引用。
#
# ⚠️ 新增任何指向 rule_sets 的 RESTRICT FK 時，**必須同步這份清單**——
# 漏加的後果不是「少數一張表」而已：`count_references` 少報 → 服務層放行 →
# DB 的 RESTRICT 在 flush 時拋 IntegrityError，原本設計好的 409＋引用數變成 500。
# 這件事已經發生過一次：v2_0026（ai_parse_runs）／v2_0028（ai_parse_jobs）加了 FK
# 卻沒同步清單。
#
# 守門者：`tests/integration/test_rule_set_delete_unretire.py::
# test_count_references_covers_every_restrict_referrer`（以 pg_catalog 反查實際的
# RESTRICT FK 與本常數對照）。它**只在 `pytest tests/integration` 這一段跑得到**——
# 上述 v2_0026/v2_0028 的漂移之所以能存活，正是因為當時 CI 用單一 `pytest -q`，
# 而 tests/unit 與 tests/integration 有同名檔案 → collection error → 整批中斷。
# CI 已改為兩段式（見 `.github/workflows/ci.yml` 與 `docs/CI_GATES.md`）；
# 若有人把它合回一行，這條守衛就再次形同不存在。
_RESTRICT_REFERRERS: tuple[tuple[str, str], ...] = (
    ("most_cycles", "rule_set_id"),
    ("most_worksheets", "default_rule_set_id"),
    ("motion_module_versions", "rule_set_id"),
    ("ai_parse_runs", "rule_set_id"),       # v2_0026
    ("ai_parse_jobs", "rule_set_id"),       # v2_0028
)

# 由 rule_sets 級聯刪除的子表（12 張規則表 ＋ 同義詞表）。刪除後逐張確認歸零。
CASCADED_CHILD_TABLES: tuple[str, ...] = (
    "rule_a_bands", "rule_b_options", "rule_g_actions", "rule_p_bases", "rule_p_addons",
    "rule_m_ladder_bands", "rule_m_foot_bands", "rule_m_verbs", "rule_m_rotation_bands",
    "rule_m_hand_bands", "rule_x_options", "rule_i_options", "rule_option_synonyms",
)


async def count_references(session: AsyncSession, rs_id: uuid.UUID) -> dict[str, int]:
    """數各引用方指向此版本的列數（0 也回，讓呼叫端能顯示完整表列）。"""
    refs: dict[str, int] = {}
    for table, column in _RESTRICT_REFERRERS:
        stmt = text(f"SELECT count(*) FROM {table} WHERE {column} = :rs_id")  # noqa: S608 - 表/欄名為模組常數
        refs[table] = int((await session.execute(stmt, {"rs_id": rs_id})).scalar_one())
    return refs


async def count_children(session: AsyncSession, rs_id: uuid.UUID) -> dict[str, int]:
    """數 13 張級聯子表各自的列數（刪除前快照，供稽核與回應）。"""
    return {
        table: int((await session.execute(
            text(f"SELECT count(*) FROM {table} WHERE rule_set_id = :i"),  # noqa: S608 - 表名為模組常數
            {"i": rs_id},
        )).scalar_one())
        for table in CASCADED_CHILD_TABLES
    }


async def delete_rule_set(session: AsyncSession, code: str, actor: str | None = None) -> dict[str, Any]:
    """刪除一個 draft 版本（ADR-023 D3b）。

    clone-on-write 是 draft 產生器（每次要改認證版的值就生一個），沒有反向操作 draft 只會
    累積——本 repo 已經清過一次 268 筆測試殘留版本。

    前置（順序與 `assert_editable` 同源，不分岔）：
    404 不存在 → 409 認證匯入 → 409 非 draft → 409 啟用中 → 409 被引用。
    12 張規則子表 ＋ rule_option_synonyms 由 DB `ondelete='CASCADE'` 級聯清除
    （model 與 migration 兩邊都確認過），故不手動逐表刪。

    稽核：`workflow_audit_log` **刻意無 FK**（v2_0017 migration 明文「允許實體刪除後 log 留存」）
    且 v2_0018 起 DB trigger 禁 UPDATE/DELETE，所以先寫 audit 再刪實體不會撞 FK，
    log 也留得住。payload 記下 code/name/provenance/子表列數 ＋ **`load_full()` 全量快照**
    ——實體沒了之後，這行 log 是唯一還說得清「刪掉的是什麼」的紀錄，而列數說不清值
    （D7 / H-1：只存列數等於沒有紀錄）。這是唯一存全量快照的路徑，因為也只有這裡
    「值的最後一份副本」會跟著實體一起消失。
    """
    rs = await assert_editable(session, code, not_draft_hint="僅 draft 版本可刪除")
    if rs.is_active:
        raise RuleSetActive(f"rule-set {code} 為啟用中版本，不可刪除（請先啟用其他版本）")

    refs = await count_references(session, rs.id)
    if any(refs.values()):
        raise RuleSetInUse(code, refs)

    children = await count_children(session, rs.id)
    snapshot = await load_full(session, code)
    rs_id, name_zh, provenance = rs.id, rs.name_zh, rs.provenance
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs_id,
        action="delete",
        from_status="draft",
        to_status=None,
        actor=actor or "unknown",
        payload={"code": code, "name_zh": name_zh, "provenance": provenance,
                 "children_deleted": children,
                 "snapshot_sha256": snapshot_digest(snapshot),
                 "snapshot": snapshot},
    )
    await session.flush()
    await session.delete(rs)
    await session.flush()
    return {"code": code, "deleted": True, "children_deleted": children}


async def unretire(session: AsyncSession, code: str, actor: str | None = None) -> dict[str, Any]:
    """解除封存：retired → published（ADR-023 D3b）。

    `retired` 的語意是「不再用於新工作」，歷史 cycle 依 §3.4 鐵則本來就照常載入，
    所以解除封存不影響任何資料完整性——把它做成終態是 UX 陷阱而非安全性質。

    `is_active` **維持 False**：解除封存不等於啟用；要啟用得另外走 `POST /activate`
    （那條路才有 validate_complete + 單一 active 的把關）。
    """
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    if rs.status != "retired":
        raise NotEditable(f"rule-set {code} 狀態為 {rs.status}，僅 retired 版本可解除封存")
    rs.status = "published"
    rs.is_active = False
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs.id,
        action="unretire",
        from_status="retired",
        to_status="published",
        actor=actor or "unknown",
        payload={"code": code, "is_active": False},
    )
    await session.flush()
    return {"code": code, "status": "published", "is_active": False}


async def retire(session: AsyncSession, code: str, actor: str | None = None) -> dict[str, Any]:
    """下架（＝ADR-023 §3.2 的 archive，但真的生效）。前置 is_active=false。

    ⚠️ retired 版本仍可被 load_rule_set_from_db 載入回放（§3.4 鐵則）；
    已引用它的 cycle/worksheet 的 TMU 不受影響。
    """
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    if rs.is_active:
        raise NotEditable(f"rule-set {code} 為啟用中版本，請先啟用其他版本再下架")
    if rs.status == "retired":
        return {"code": code, "status": "retired", "is_active": False, "changed": False}
    from_status = rs.status
    rs.status = "retired"
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs.id,
        action="retire",
        from_status=from_status,
        to_status="retired",
        actor=actor or "unknown",
    )
    await session.flush()
    return {"code": code, "status": "retired", "is_active": False, "changed": True}
