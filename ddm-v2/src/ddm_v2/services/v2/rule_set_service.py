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

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2 import rule_set_tables as rt
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.most_engine.providers import load_rule_set_from_db
from ddm_v2.services.v2.audit_service import log_audit


class RuleSetNotFound(Exception):
    pass


class RuleSetExists(Exception):
    pass


class NotEditable(Exception):
    pass


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
        "a_bands": [{"component": r.component, "max_value": float(r.max_value) if r.max_value is not None else None, "index": r.index_value, "sort": r.sort_order} for r in await _rows(session, rt.RuleABand, rs.id)],
        "b": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "index": r.index_value, "is_default": r.is_default, "sort": r.sort_order} for r in await _rows(session, rt.RuleBOption, rs.id)],
        "g": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "modifier_key": r.modifier_key, "requires_modifier": r.requires_modifier, "base_tmu": r.base_tmu, "sort": r.sort_order} for r in await _rows(session, rt.RuleGAction, rs.id)],
        "p_bases": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "category": r.category, "direction_mode": r.direction_mode, "base_tmu": r.base_tmu, "sort": r.sort_order} for r in await _rows(session, rt.RulePBase, rs.id)],
        "p_addons": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "delta": r.delta_tmu, "needs_precision": r.needs_precision, "sort": r.sort_order} for r in await _rows(session, rt.RulePAddon, rs.id)],
        "m_ladder": [{"max_cm": float(r.max_cm) if r.max_cm is not None else None, "tmu": r.tmu, "sort": r.sort_order} for r in await _rows(session, rt.RuleMLadderBand, rs.id)],
        "m_verbs": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "pricing_kind": r.pricing_kind, "fixed_tmu": r.fixed_tmu, "sort": r.sort_order} for r in await _rows(session, rt.RuleMVerb, rs.id)],
        "m_rotation": [{"max_diameter_cm": float(r.max_diameter_cm) if r.max_diameter_cm is not None else None, "revolutions": r.revolutions, "tmu": r.tmu, "sort": r.sort_order} for r in await _rows(session, rt.RuleMRotationBand, rs.id)],
        "m_hand": [{"max_deg": float(r.max_deg) if r.max_deg is not None else None, "tmu": r.tmu, "sort": r.sort_order} for r in await _rows(session, rt.RuleMHandBand, rs.id)],
        "x": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "mode": r.mode, "fixed_seconds": float(r.fixed_seconds) if r.fixed_seconds is not None else None, "sort": r.sort_order} for r in await _rows(session, rt.RuleXOption, rs.id)],
        "i": [{"code": r.code, "label_zh": r.label_zh, "label_en": r.label_en, "index": r.index_value, "sort": r.sort_order} for r in await _rows(session, rt.RuleIOption, rs.id)],
    }


def _insert_children(session: AsyncSession, rs_id: uuid.UUID, full: dict[str, Any]) -> None:
    def so(i: int, r: dict) -> int:
        return r.get("sort", i)
    for i, r in enumerate(full.get("a_bands", [])):
        session.add(rt.RuleABand(id=uuid.uuid4(), rule_set_id=rs_id, component=r["component"], max_value=r.get("max_value"), index_value=int(r["index"]), sort_order=so(i, r)))
    for i, r in enumerate(full.get("b", [])):
        session.add(rt.RuleBOption(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), index_value=int(r["index"]), is_default=bool(r.get("is_default")), sort_order=so(i, r)))
    for i, r in enumerate(full.get("g", [])):
        session.add(rt.RuleGAction(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), modifier_key=r.get("modifier_key"), requires_modifier=bool(r.get("requires_modifier")), base_tmu=int(r["base_tmu"]), sort_order=so(i, r)))
    for i, r in enumerate(full.get("p_bases", [])):
        session.add(rt.RulePBase(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), category=r.get("category"), direction_mode=r.get("direction_mode"), base_tmu=int(r["base_tmu"]), sort_order=so(i, r)))
    for i, r in enumerate(full.get("p_addons", [])):
        session.add(rt.RulePAddon(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), delta_tmu=int(r["delta"]), needs_precision=bool(r.get("needs_precision")), sort_order=so(i, r)))
    for i, r in enumerate(full.get("m_ladder", [])):
        session.add(rt.RuleMLadderBand(id=uuid.uuid4(), rule_set_id=rs_id, max_cm=r.get("max_cm"), tmu=int(r["tmu"]), sort_order=so(i, r)))
    for i, r in enumerate(full.get("m_verbs", [])):
        session.add(rt.RuleMVerb(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), pricing_kind=r["pricing_kind"], fixed_tmu=r.get("fixed_tmu"), sort_order=so(i, r)))
    for i, r in enumerate(full.get("m_rotation", [])):
        session.add(rt.RuleMRotationBand(id=uuid.uuid4(), rule_set_id=rs_id, max_diameter_cm=r.get("max_diameter_cm"), revolutions=int(r["revolutions"]), tmu=int(r["tmu"]), sort_order=so(i, r)))
    for i, r in enumerate(full.get("m_hand", [])):
        session.add(rt.RuleMHandBand(id=uuid.uuid4(), rule_set_id=rs_id, max_deg=r.get("max_deg"), tmu=int(r["tmu"]), sort_order=so(i, r)))
    for i, r in enumerate(full.get("x", [])):
        session.add(rt.RuleXOption(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), mode=r["mode"], fixed_seconds=r.get("fixed_seconds"), sort_order=so(i, r)))
    for i, r in enumerate(full.get("i", [])):
        session.add(rt.RuleIOption(id=uuid.uuid4(), rule_set_id=rs_id, code=r["code"], label_zh=r["label_zh"], label_en=r.get("label_en"), index_value=int(r["index"]), sort_order=so(i, r)))


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
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    if rs.status != "draft":
        raise NotEditable(f"rule-set {code} 狀態為 {rs.status}，已凍結不可編輯（請建立草稿）")
    if "name_zh" in full and full["name_zh"]:
        rs.name_zh = full["name_zh"]
    if "multiplier" in full and full["multiplier"] is not None:
        rs.system_tmu_multiplier = full["multiplier"]
    for model in (rt.RuleABand, rt.RuleBOption, rt.RuleGAction, rt.RulePBase, rt.RulePAddon,
                  rt.RuleMLadderBand, rt.RuleMVerb, rt.RuleMRotationBand, rt.RuleMHandBand, rt.RuleXOption, rt.RuleIOption):
        await session.execute(delete(model).where(model.rule_set_id == rs.id))
    await session.flush()
    _insert_children(session, rs.id, full)
    await session.flush()
    return await load_full(session, code)


async def publish(session: AsyncSession, code: str, actor: str | None = None) -> dict[str, Any]:
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(code)
    if rs.status != "draft":
        raise NotEditable(f"rule-set {code} 狀態為 {rs.status}")
    # ADR-023 §3.2：發布前驗證＝引擎自己的完整性契約（RuleSetIncomplete → 409），
    # 保證 activate 後不會 runtime 才炸。
    (await load_rule_set_from_db(session, code)).validate_complete()
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
