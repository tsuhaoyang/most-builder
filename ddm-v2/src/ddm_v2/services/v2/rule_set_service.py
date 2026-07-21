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

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2 import rule_set_tables as rt
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.most_engine.providers import load_rule_set_from_db
from ddm_v2.schemas.v2.rule_set_options import resolve, validate_bands
from ddm_v2.services.v2.audit_service import log_audit


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


async def assert_editable(session: AsyncSession, code: str) -> RuleSet:
    """所有寫入端點共用的不可變 gate（ADR-023 §3.3 規則 1＋3）。

    404（不存在）→ 409（認證匯入）→ 409（非 draft）。單一實作＝不會有端點漏掛。
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
        raise NotEditable(f"rule-set {code} 狀態為 {rs.status}，已凍結，請先建立草稿")
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


async def _rows(session: AsyncSession, model: type, rs_id: uuid.UUID) -> list[Any]:
    return list((await session.execute(select(model).where(model.rule_set_id == rs_id).order_by(model.sort_order))).scalars().all())


async def load_full(session: AsyncSession, code: str) -> dict[str, Any]:
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    return {
        "id": str(rs.id),
        "code": rs.code, "name_zh": rs.name_zh, "status": rs.status, "multiplier": float(rs.system_tmu_multiplier),
        "a_bands": [{"component": r.component, "max_value": float(r.max_value) if r.max_value is not None else None, "index": r.index_value, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleABand, rs.id)],
        "b": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "index": r.index_value, "is_default": r.is_default, "sentence_text_zh": r.sentence_text_zh, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleBOption, rs.id)],
        "g": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "modifier_key": r.modifier_key, "requires_modifier": r.requires_modifier, "base_tmu": r.base_tmu, "sentence_text_zh": r.sentence_text_zh, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleGAction, rs.id)],
        "p_bases": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "category": r.category, "direction_mode": r.direction_mode, "base_tmu": r.base_tmu, "sentence_text_zh": r.sentence_text_zh, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RulePBase, rs.id)],
        "p_addons": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "delta": r.delta_tmu, "needs_precision": r.needs_precision, "max_select": r.max_select, "display_rule": r.display_rule, "sentence_text_zh": r.sentence_text_zh, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RulePAddon, rs.id)],
        "m_ladder": [{"max_cm": float(r.max_cm) if r.max_cm is not None else None, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMLadderBand, rs.id)],
        "m_foot": [{"max_cm": float(r.max_cm) if r.max_cm is not None else None, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMFootBand, rs.id)],
        "m_verbs": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "pricing_kind": r.pricing_kind, "fixed_tmu": r.fixed_tmu, "sentence_text_zh": r.sentence_text_zh, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMVerb, rs.id)],
        "m_rotation": [{"max_diameter_cm": float(r.max_diameter_cm) if r.max_diameter_cm is not None else None, "revolutions": r.revolutions, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMRotationBand, rs.id)],
        "m_hand": [{"max_deg": float(r.max_deg) if r.max_deg is not None else None, "tmu": r.tmu, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleMHandBand, rs.id)],
        "x": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "mode": r.mode, "fixed_seconds": float(r.fixed_seconds) if r.fixed_seconds is not None else None, "sentence_text_zh": r.sentence_text_zh, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleXOption, rs.id)],
        "i": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "index": r.index_value, "vision_scope": r.vision_scope, "sentence_text_zh": r.sentence_text_zh, "sort": r.sort_order, "is_active": r.is_active} for r in await _rows(session, rt.RuleIOption, rs.id)],
    }


def _insert_children(session: AsyncSession, rs_id: uuid.UUID, full: dict[str, Any]) -> None:
    def so(i: int, r: dict) -> int:
        return r.get("sort", i)
    for i, r in enumerate(full.get("a_bands", [])):
        session.add(rt.RuleABand(id=uuid.uuid4(), rule_set_id=rs_id, component=r["component"], max_value=r.get("max_value"), index_value=int(r["index"]), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("b", [])):
        session.add(rt.RuleBOption(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), index_value=int(r["index"]), is_default=bool(r.get("is_default")), sentence_text_zh=r.get("sentence_text_zh"), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("g", [])):
        session.add(rt.RuleGAction(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), modifier_key=r.get("modifier_key"), requires_modifier=bool(r.get("requires_modifier")), base_tmu=int(r["base_tmu"]), sentence_text_zh=r.get("sentence_text_zh"), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("p_bases", [])):
        session.add(rt.RulePBase(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), category=r.get("category"), direction_mode=r.get("direction_mode"), base_tmu=int(r["base_tmu"]), sentence_text_zh=r.get("sentence_text_zh"), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("p_addons", [])):
        session.add(rt.RulePAddon(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), delta_tmu=int(r["delta"]), needs_precision=bool(r.get("needs_precision")), max_select=int(r.get("max_select", 2)), display_rule=r.get("display_rule") or "show_self", sentence_text_zh=r.get("sentence_text_zh"), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("m_ladder", [])):
        session.add(rt.RuleMLadderBand(id=uuid.uuid4(), rule_set_id=rs_id, max_cm=r.get("max_cm"), tmu=int(r["tmu"]), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("m_foot", [])):
        session.add(rt.RuleMFootBand(id=uuid.uuid4(), rule_set_id=rs_id, max_cm=r.get("max_cm"), tmu=int(r["tmu"]), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("m_verbs", [])):
        session.add(rt.RuleMVerb(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), pricing_kind=r["pricing_kind"], fixed_tmu=r.get("fixed_tmu"), sentence_text_zh=r.get("sentence_text_zh"), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("m_rotation", [])):
        session.add(rt.RuleMRotationBand(id=uuid.uuid4(), rule_set_id=rs_id, max_diameter_cm=r.get("max_diameter_cm"), revolutions=int(r["revolutions"]), tmu=int(r["tmu"]), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("m_hand", [])):
        session.add(rt.RuleMHandBand(id=uuid.uuid4(), rule_set_id=rs_id, max_deg=r.get("max_deg"), tmu=int(r["tmu"]), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("x", [])):
        session.add(rt.RuleXOption(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), mode=r["mode"], fixed_seconds=r.get("fixed_seconds"), sentence_text_zh=r.get("sentence_text_zh"), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))
    for i, r in enumerate(full.get("i", [])):
        session.add(rt.RuleIOption(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), index_value=int(r["index"]), vision_scope=r.get("vision_scope"), sentence_text_zh=r.get("sentence_text_zh"), sort_order=so(i, r), is_active=bool(r.get("is_active", True))))


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


async def clone_draft(session: AsyncSession, code: str, new_code: str | None, name_zh: str | None) -> dict[str, Any]:
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
    return {"code": new_code, "status": "draft", "provenance": "cloned"}


async def replace_children(session: AsyncSession, code: str, full: dict[str, Any]) -> dict[str, Any]:
    # ADR-023 §3.3 規則 3 明文：「任何選項級寫入**或 PUT /full**一律 409」——
    # 故整份替換與選項級 CRUD 共用同一 gate（certified_import 也擋）。
    rs = await assert_editable(session, code)
    # HIGH-2：帶界契約與 PUT /bands 同源，PUT /full 不得繞過（見 validate_full_bands）
    validate_full_bands(full)
    if "name_zh" in full and full["name_zh"]:
        rs.name_zh = full["name_zh"]
    if "multiplier" in full and full["multiplier"] is not None:
        rs.system_tmu_multiplier = full["multiplier"]
    for model in (rt.RuleABand, rt.RuleBOption, rt.RuleGAction, rt.RulePBase, rt.RulePAddon,
                  rt.RuleMLadderBand, rt.RuleMFootBand, rt.RuleMVerb, rt.RuleMRotationBand, rt.RuleMHandBand, rt.RuleXOption, rt.RuleIOption):
        await session.execute(delete(model).where(model.rule_set_id == rs.id))
    await session.flush()
    _insert_children(session, rs.id, full)
    await session.flush()
    return await load_full(session, code)


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
