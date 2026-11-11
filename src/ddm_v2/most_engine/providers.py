"""rule-set providers（adapter）：產生 RuleSetData 供引擎使用。

- build_from_seed()：in-memory，從 seed DATA 建（測試 / 黃金 fixture；單一來源＝seed）。
- load_rule_set_from_db()：async，從 v2 DB 表建（正式 runtime）。

兩者都呼叫 rule_set_data.build_rule_set_data() 確保形狀一致。引擎只依賴 RuleSetData，
不知道資料來自 seed 還是 DB（hexagonal：換來源＝換 adapter）。
"""
from __future__ import annotations

from typing import Any

from ddm_v2.most_engine.rule_set_data import RuleSetData, build_rule_set_data

_P_ADDON_MAX = 2


def build_from_seed() -> RuleSetData:
    """從 seed.rule_set_seed 的 DATA 常數建 in-memory rule-set（工廠 v1）。"""
    from ddm_v2.seed.v2 import rule_set_seed as s

    data = build_rule_set_data(
        code=s.RULE_SET["code"],
        multiplier=float(s.RULE_SET["system_tmu_multiplier"]),
        a_bands_rows=[(comp, mx, idx) for comp, mx, idx, _so in s.A_BANDS],
        b_rows=[(code, idx, dft) for code, _lab, idx, dft, _so in s.B_OPTIONS],
        g_rows=[(code, mod, req, tmu) for code, _lab, mod, req, tmu, _so in s.G_ACTIONS],
        p_base_rows=[(code, tmu) for code, _lab, _cat, _dm, tmu, _so in s.P_BASES],
        p_addon_rows=[(code, delta, prec) for code, _lab, delta, prec, _so in s.P_ADDONS],
        p_addon_max=_P_ADDON_MAX,
        m_ladder_rows=[(mx, tmu) for mx, tmu, _so in s.M_LADDER],
        m_verb_rows=[(code, kind, ftmu) for code, _lab, kind, ftmu, _so in s.M_VERBS],
        m_rotation_rows=[(mx, rev, tmu) for mx, rev, tmu, _so in s.M_ROTATION],
        m_hand_rows=[(mx, tmu) for mx, tmu, _so in s.M_HAND],
        x_rows=[(code, mode, fsec) for code, _lab, mode, fsec, _so in s.X_OPTIONS],
        i_rows=[(code, idx) for code, _lab, idx, _so in s.I_OPTIONS],
    )
    return data


def build_options_from_seed() -> dict[str, Any]:
    """回傳含 label 的選項清單（給前端 render 下拉）。FE-1 preview 版；P1 改讀 DB labels。"""
    from ddm_v2.seed.v2 import rule_set_seed as s

    def _band(comp: str) -> list[dict[str, Any]]:
        return [{"max_value": mx, "index": idx} for c, mx, idx, _so in s.A_BANDS if c == comp]

    return {
        "code": s.RULE_SET["code"],
        "multiplier": float(s.RULE_SET["system_tmu_multiplier"]),
        "a_bands": {"reach": _band("reach"), "twist": _band("twist"), "foot": _band("foot")},
        "b": [{"code": c, "label": lab, "index": iv, "is_default": d} for c, lab, iv, d, _ in s.B_OPTIONS],
        "g": [{"code": c, "label": lab, "modifier_key": mod, "requires_modifier": req, "base_tmu": tmu} for c, lab, mod, req, tmu, _ in s.G_ACTIONS],
        "p_bases": [{"code": c, "label": lab, "base_tmu": tmu} for c, lab, _cat, _dm, tmu, _ in s.P_BASES],
        "p_addons": [{"code": c, "label": lab, "delta": dt, "needs_precision": prec} for c, lab, dt, prec, _ in s.P_ADDONS],
        "m_verbs": [{"code": c, "label": lab, "pricing_kind": kind} for c, lab, kind, _ftmu, _ in s.M_VERBS],
        "x": [{"code": c, "label": lab, "mode": mode} for c, lab, mode, _fsec, _ in s.X_OPTIONS],
        "i": [{"code": c, "label": lab, "index": iv} for c, lab, iv, _ in s.I_OPTIONS],
    }


def build_from_seed_v2() -> RuleSetData:
    """從 seed.rule_set_seed_v2（v3 IE 認證字典，ADR-014）建 in-memory rule-set（工廠 v2）。"""
    from ddm_v2.seed.v2 import rule_set_seed_v2 as s

    return build_rule_set_data(
        code=s.RULE_SET["code"],
        multiplier=float(s.RULE_SET["system_tmu_multiplier"]),
        a_bands_rows=[(comp, mx, idx) for comp, mx, idx, _so in s.A_BANDS],
        b_rows=[(code, idx, dft) for code, _lab, idx, dft, _so, _sent in s.B_OPTIONS],
        g_rows=[(code, mod, req, tmu) for code, _lab, mod, req, tmu, _so, _sent in s.G_ACTIONS],
        p_base_rows=[(code, tmu) for code, _lab, _cat, _dm, tmu, _so, _sent in s.P_BASES],
        p_addon_rows=[(code, delta, prec) for code, _lab, delta, prec, _so, _dr, _sent in s.P_ADDONS],
        p_addon_max=_P_ADDON_MAX,
        m_ladder_rows=[(mx, tmu) for mx, tmu, _so in s.M_LADDER],
        m_verb_rows=[(code, kind, ftmu) for code, _lab, kind, ftmu, _so, _sent in s.M_VERBS],
        m_rotation_rows=[(mx, rev, tmu) for mx, rev, tmu, _so in s.M_ROTATION],
        m_hand_rows=[(mx, tmu) for mx, tmu, _so in s.M_HAND],
        x_rows=[(code, mode, fsec) for code, _lab, mode, fsec, _so, _sent in s.X_OPTIONS],
        i_rows=[(code, idx) for code, _lab, idx, _so, _scope, _sent in s.I_OPTIONS],
        m_foot_rows=[(mx, tmu) for mx, tmu, _so in s.M_FOOT],
    )


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


async def load_options_from_db(session: Any, code: str) -> dict[str, Any]:
    """從 DB 載含 label 的選項清單（FE-1 正式版；下拉用）。找不到 → 回 None。"""
    from sqlalchemy import select

    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet

    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs is None:
        return None

    async def rows(model: type) -> list[Any]:
        res = await session.execute(select(model).where(model.rule_set_id == rs.id).order_by(model.sort_order))
        return list(res.scalars().all())

    a = await rows(rt.RuleABand)
    return {
        "id": str(rs.id),
        "code": rs.code,
        "multiplier": float(rs.system_tmu_multiplier),
        "a_bands": {
            comp: [{"max_value": _f(r.max_value), "index": r.index_value} for r in a if r.component == comp]
            for comp in ("reach", "twist", "foot")
        },
        "b": [{"code": r.code, "label": r.label_zh, "label_en": r.label_en, "index": r.index_value, "is_default": r.is_default, "sentence": r.sentence_text_zh, "sentence_en": r.sentence_text_en} for r in await rows(rt.RuleBOption)],
        "g": [{"code": r.code, "label": r.label_zh, "label_en": r.label_en, "modifier_key": r.modifier_key, "requires_modifier": r.requires_modifier, "base_tmu": r.base_tmu, "sentence": r.sentence_text_zh, "sentence_en": r.sentence_text_en} for r in await rows(rt.RuleGAction)],
        "p_bases": [{"code": r.code, "label": r.label_zh, "label_en": r.label_en, "base_tmu": r.base_tmu, "sentence": r.sentence_text_zh, "sentence_en": r.sentence_text_en} for r in await rows(rt.RulePBase)],
        "p_addons": [{"code": r.code, "label": r.label_zh, "label_en": r.label_en, "delta": r.delta_tmu, "needs_precision": r.needs_precision, "sentence": r.sentence_text_zh, "sentence_en": r.sentence_text_en, "display_rule": r.display_rule} for r in await rows(rt.RulePAddon)],
        "m_verbs": [{"code": r.code, "label": r.label_zh, "label_en": r.label_en, "pricing_kind": r.pricing_kind, "sentence": r.sentence_text_zh, "sentence_en": r.sentence_text_en} for r in await rows(rt.RuleMVerb)],
        "x": [{"code": r.code, "label": r.label_zh, "label_en": r.label_en, "mode": r.mode, "sentence": r.sentence_text_zh, "sentence_en": r.sentence_text_en} for r in await rows(rt.RuleXOption)],
        "i": [{"code": r.code, "label": r.label_zh, "label_en": r.label_en, "index": r.index_value, "vision_scope": r.vision_scope, "sentence": r.sentence_text_zh, "sentence_en": r.sentence_text_en} for r in await rows(rt.RuleIOption)],
    }


def build_label_map(opts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`load_options_from_db()` 的選項清單 → 兩個敘事模組吃的 `{param: {code: entry}}`。

    中英兩套樣板共用同一份 entry（`label`/`sentence` ＋ `label_en`/`sentence_en`），
    所以這裡是**單一**的形狀來源——先前 worksheet 與 motion module 兩個 service 各自
    抄了一份 `_lmap`，加英文欄時等於要記得改兩個地方。
    """
    def _one(rows_: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            o["code"]: {
                "label": o.get("label"), "sentence": o.get("sentence"),
                "label_en": o.get("label_en"), "sentence_en": o.get("sentence_en"),
                "display_rule": o.get("display_rule"),
                # M 專屬：敘事層靠它認出手度／腳步是伴隨維度而非動詞（ADR-032 敘事排除規則）。
                # 其餘參數沒有這個鍵 → None，與 `display_rule` 同樣的「只有用得到的表才有值」。
                "pricing_kind": o.get("pricing_kind"),
            }
            for o in rows_
        }

    return {"g": _one(opts["g"]), "p_base": _one(opts["p_bases"]), "p_addon": _one(opts["p_addons"]),
            "m_verb": _one(opts["m_verbs"]), "x": _one(opts["x"]), "i": _one(opts["i"])}


async def load_options_by_rule_set_id(session: Any, rule_set_id: Any) -> dict[str, Any] | None:
    """同 `load_options_from_db`，但以 rule_set **id** 定位版本。找不到 → 回 None。

    存在的理由是回放：`most_cycles.rule_set_id` 與 `motion_module_versions.rule_set_id`
    釘的是 id 而非 code，用 active code 去載標籤等於拿現行字典重新詮釋歷史列
    （ADR-032 I4）。`rule_sets.code` 有 UNIQUE，故 id → code → 既有載入器是等價的。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet

    code = (await session.execute(
        select(RuleSet.code).where(RuleSet.id == rule_set_id)
    )).scalar_one_or_none()
    if code is None:
        return None
    return await load_options_from_db(session, code)


async def load_rule_set_from_db(session: Any, code: str) -> RuleSetData:
    """從 v2 DB 表建 RuleSetData（依 rule_set code）。runtime 用；P1 串 API。"""
    from sqlalchemy import select

    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet

    rs = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one()

    async def rows(model: type) -> list[Any]:
        res = await session.execute(select(model).where(model.rule_set_id == rs.id).order_by(model.sort_order))
        return list(res.scalars().all())

    a = await rows(rt.RuleABand)
    b = await rows(rt.RuleBOption)
    g = await rows(rt.RuleGAction)
    pb = await rows(rt.RulePBase)
    pa = await rows(rt.RulePAddon)
    ml = await rows(rt.RuleMLadderBand)
    mf = await rows(rt.RuleMFootBand)
    mv = await rows(rt.RuleMVerb)
    mr = await rows(rt.RuleMRotationBand)
    mh = await rows(rt.RuleMHandBand)
    x = await rows(rt.RuleXOption)
    i = await rows(rt.RuleIOption)

    return build_rule_set_data(
        code=rs.code,
        multiplier=float(rs.system_tmu_multiplier),
        a_bands_rows=[(r.component, _f(r.max_value), r.index_value) for r in a],
        b_rows=[(r.code, r.index_value, r.is_default) for r in b],
        g_rows=[(r.code, r.modifier_key, r.requires_modifier, r.base_tmu) for r in g],
        p_base_rows=[(r.code, r.base_tmu) for r in pb],
        p_addon_rows=[(r.code, r.delta_tmu, r.needs_precision) for r in pa],
        p_addon_max=min((r.max_select for r in pa), default=_P_ADDON_MAX),
        m_ladder_rows=[(_f(r.max_cm), r.tmu) for r in ml],
        m_verb_rows=[(r.code, r.pricing_kind, r.fixed_tmu) for r in mv],
        m_rotation_rows=[(_f(r.max_diameter_cm), r.revolutions, r.tmu) for r in mr],
        m_hand_rows=[(_f(r.max_deg), r.tmu) for r in mh],
        x_rows=[(r.code, r.mode, _f(r.fixed_seconds)) for r in x],
        i_rows=[(r.code, r.index_value) for r in i],
        m_foot_rows=[(_f(r.max_cm), r.tmu) for r in mf],
    )
