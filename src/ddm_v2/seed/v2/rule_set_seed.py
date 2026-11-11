"""工廠 rule-set 種子 `MINIMOST_FACTORY_V1`（重現黃金值 GM=28 / CM=29）。

資料即真相：以下 DATA 常數同時供 (a) DB 插入 seed_rule_set_factory_v1()、
(b) 本檔自我驗證的資料驅動 mini-compute（證明這份資料端到端算得出 28/29）。
此 mini-compute 是 P0 引擎化的雛形——正式引擎將以相同演算法讀 DB，
並由 scripts/core_logic 的 89 個黃金/反例測試鎖定一致性。

值來源：minimost-sequence-model-core-logic-spec §4 / scripts/core_logic/minimost_sequence_validator.py
（B 採 1205 值 0/10/32/42；A 三分量 reach/twist/foot 取 max）。
"""
from __future__ import annotations

import math
import uuid
from typing import Any

TMU_TO_SEC = 0.036

RULE_SET = {"code": "MINIMOST_FACTORY_V1", "name_zh": "MiniMOST 工廠規則 v1", "system_tmu_multiplier": 1}

# component, max_value(None=overflow), index_value, sort_order
A_BANDS: list[tuple[str, float | None, int, int]] = [
    ("reach", 2.5, 0, 0), ("reach", 5, 1, 1), ("reach", 10, 3, 2), ("reach", 20, 6, 3),
    ("reach", 35, 10, 4), ("reach", 60, 16, 5), ("reach", None, 24, 6),
    ("twist", 30, 0, 0), ("twist", 60, 1, 1), ("twist", 120, 3, 2), ("twist", 180, 6, 3),
    ("foot", 20, 6, 0), ("foot", 30, 10, 1), ("foot", 45, 16, 2), ("foot", 65, 24, 3), ("foot", None, 32, 4),
]
# code, label_zh, index, is_default, sort
B_OPTIONS = [
    ("b_none", "無身體動作", 0, True, 0), ("b_eye", "眼部動作", 10, False, 1),
    ("b_bend", "起身或彎腰/坐", 32, False, 2), ("b_stand", "站立", 42, False, 3),
]
# code, label_zh, modifier_key, requires_modifier, base_tmu, sort
G_ACTIONS = [
    ("g_tap", "輕按", "contact", True, 3, 0), ("g_touch", "接觸", "contact", True, 3, 1),
    ("g_pat", "輕拍", "contact", True, 3, 2), ("g_grasp", "抓握", None, False, 6, 3),
    ("g_grab", "抓取", None, False, 6, 4), ("g_regrasp", "重新抓握", None, False, 6, 5),
    ("g_handchange", "換手", "transfer", True, 10, 6), ("g_pick_sel", "拿取(選取)", "select", True, 10, 7),
    ("g_pick_small", "拿取(選取-小)", "select_small", True, 16, 8), ("g_pullout", "拔出", "separate", True, 16, 9),
    ("g_pick_collect", "拿取(收集)", "collect", True, 24, 10),
]
# code, label_zh, category, direction_mode, base_tmu, sort
P_BASES = [
    ("p_toss", "丟", "toss", None, 3, 0), ("p_hold", "保持住", "hold", None, 3, 1),
    ("p_place_none", "放(無方向)", "place", "none", 6, 2), ("p_place_multi", "放(多種方向)", "place", "multi", 10, 3),
    ("p_place_single", "放(一種方向)", "place", "single", 16, 4), ("p_asm_multi", "組(多種方向)", "assemble", "multi", 10, 5),
    ("p_asm_single", "組(一種方向)", "assemble", "single", 16, 6),
]
# code, label_zh, delta_tmu, needs_precision, sort
P_ADDONS = [
    ("a_align", "對準", 8, True, 0), ("a_insert", "插入", 8, False, 1), ("a_hard", "較難處理", 8, False, 2),
    ("a_snap", "卡合", 16, False, 3), ("a_press", "施加壓力", 16, False, 4),
]
# max_cm(None=overflow), tmu, sort
M_LADDER = [(1, 3, 0), (4, 6, 1), (10, 10, 2), (18, 16, 3), (30, 24, 4), (None, 42, 5)]
# code, label_zh, pricing_kind, fixed_tmu, sort
M_VERBS = [
    ("m_btn", "按動按鈕", "fixed", 3, 0), ("m_screw", "滑出螺絲", "fixed", 3, 1),
    ("m_li", "理", "ladder", None, 2), ("m_through", "穿", "ladder", None, 3), ("m_push", "推", "ladder", None, 4),
    ("m_pull", "拉", "ladder", None, 5), ("m_attach", "貼附", "ladder", None, 6), ("m_remove", "去除", "ladder", None, 7),
    ("m_teartape", "撕除", "ladder", None, 8), ("m_fold", "折", "ladder", None, 9), ("m_wipe", "擦拭", "ladder", None, 10),
    ("m_tearopen", "撕開", "ladder", None, 11), ("m_rotate", "旋轉", "rotate", None, 12),
    ("m_hand", "手度", "hand", None, 13), ("m_foot", "腳步", "foot", None, 14),
]
# max_diameter_cm(None=overflow), revolutions, tmu, sort
M_ROTATION = [(12.5, 1, 16, 0), (12.5, 2, 32, 1), (12.5, 3, 42, 2), (None, 1, 24, 3), (None, 2, 42, 4), (None, 3, 42, 5)]
# max_deg(None=overflow), tmu, sort
M_HAND = [(90, 6, 0), (None, 10, 1)]
# code, label_zh, mode, fixed_seconds, sort
X_OPTIONS = [
    ("x_none", "無機台等待", "zero", None, 0), ("x_press", "並壓合機台", "seconds", None, 1),
    ("x_heat", "並熱熔機台", "seconds", None, 2), ("x_scan", "刷條碼(固定)", "fixed", 0.216, 3),
]
# code, label_zh, index_value, sort
I_OPTIONS = [
    ("i_none", "不額外對齊", 0, 0), ("i_check", "並檢查(正常視線)", 6, 1),
    ("i_align1", "並對準(正常視線·到點)", 10, 2), ("i_align2", "並對齊(正常視線·到兩點)", 16, 3),
]


# ───────────────────────── DB 插入 ─────────────────────────
def seed_rule_set_factory_v1(session: Any) -> Any:
    """插入工廠 rule-set 與所有子表（published）。回傳 RuleSet。"""
    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet

    rs = RuleSet(id=uuid.uuid4(), code=RULE_SET["code"], name_zh=RULE_SET["name_zh"],
                 status="published", system_tmu_multiplier=RULE_SET["system_tmu_multiplier"])
    session.add(rs)

    def _id() -> uuid.UUID:
        return uuid.uuid4()

    for comp, mx, iv, so in A_BANDS:
        session.add(rt.RuleABand(id=_id(), rule_set_id=rs.id, component=comp, max_value=mx, index_value=iv, sort_order=so))
    for code, lab, iv, dft, so in B_OPTIONS:
        session.add(rt.RuleBOption(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, index_value=iv, is_default=dft, sort_order=so))
    for code, lab, mod, req, tmu, so in G_ACTIONS:
        session.add(rt.RuleGAction(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, modifier_key=mod, requires_modifier=req, base_tmu=tmu, sort_order=so))
    for code, lab, cat, dm, tmu, so in P_BASES:
        session.add(rt.RulePBase(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, category=cat, direction_mode=dm, base_tmu=tmu, sort_order=so))
    for code, lab, dt, prec, so in P_ADDONS:
        session.add(rt.RulePAddon(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, delta_tmu=dt, needs_precision=prec, sort_order=so))
    for mx, tmu, so in M_LADDER:
        session.add(rt.RuleMLadderBand(id=_id(), rule_set_id=rs.id, max_cm=mx, tmu=tmu, sort_order=so))
    for code, lab, kind, ftmu, so in M_VERBS:
        session.add(rt.RuleMVerb(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, pricing_kind=kind, fixed_tmu=ftmu, sort_order=so))
    for mx, rev, tmu, so in M_ROTATION:
        session.add(rt.RuleMRotationBand(id=_id(), rule_set_id=rs.id, max_diameter_cm=mx, revolutions=rev, tmu=tmu, sort_order=so))
    for mx, tmu, so in M_HAND:
        session.add(rt.RuleMHandBand(id=_id(), rule_set_id=rs.id, max_deg=mx, tmu=tmu, sort_order=so))
    for code, lab, mode, fsec, so in X_OPTIONS:
        session.add(rt.RuleXOption(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, mode=mode, fixed_seconds=fsec, sort_order=so))
    for code, lab, iv, so in I_OPTIONS:
        session.add(rt.RuleIOption(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, index_value=iv, sort_order=so))
    return rs


# ───────────── 資料驅動 mini-compute（自我驗證；P0 引擎雛形）─────────────
def _band_index(value: float, comp: str) -> int | None:
    if not value or value <= 0:
        return None
    bands = sorted([(mx, iv) for c, mx, iv, _ in A_BANDS if c == comp],
                   key=lambda b: (b[0] is None, b[0] if b[0] is not None else 0))
    for mx, iv in bands:
        if mx is None or value <= float(mx):
            return iv
    return bands[-1][1]


def _a_tmu(reach: float = 0, twist: float = 0, foot: float = 0) -> int:
    parts = [_band_index(reach, "reach"), _band_index(twist, "twist"), _band_index(foot, "foot")]
    present = [p for p in parts if p is not None]
    return max(present) if present else 0


def _g_tmu(code: str | None, modifiers: dict[str, bool]) -> int:
    if not code:
        return 0
    row = next((r for r in G_ACTIONS if r[0] == code), None)
    if not row:
        raise ValueError(f"unknown G {code}")
    _c, _l, mod, req, tmu, _s = row
    if req and mod and not modifiers.get(mod):
        return 0
    return tmu


def _p_tmu(base: str | None, addons: list[str], precision: bool) -> int:
    if not base:
        return 0
    total = next(r[4] for r in P_BASES if r[0] == base)
    for a in addons:
        code, _l, delta, prec, _s = next(r for r in P_ADDONS if r[0] == a)
        if prec and not precision:
            continue
        total += delta
    return total


def _ladder(cm: float) -> int:
    for mx, tmu, _ in sorted(M_LADDER, key=lambda b: (b[0] is None, b[0] or 0)):
        if mx is None or cm <= float(mx):
            return tmu
    return M_LADDER[-1][1]


def _m_tmu(components: list[dict]) -> int:
    vals = []
    for c in components:
        v = next((r for r in M_VERBS if r[0] == c.get("verb")), None)
        if not v:
            continue
        kind, ftmu = v[2], v[3]
        if kind == "fixed":
            vals.append(ftmu)
        elif kind in ("ladder", "foot"):
            vals.append(_ladder(c.get("distance_cm", 0)))
        elif kind == "hand":
            deg = c.get("angle_deg", 0)
            vals.append(next(t for mx, t, _ in sorted(M_HAND, key=lambda b: (b[0] is None, b[0] or 0)) if mx is None or deg <= float(mx)))
        elif kind == "rotate":
            dia, rev = c.get("diameter_cm", 0), max(1, min(3, c.get("revolutions", 1)))
            vals.append(next(t for mx, rv, t, _ in M_ROTATION if rv == rev and (mx is None or dia <= float(mx))))
    return max(vals) if vals else 0


def _x_tmu(code: str, seconds: float = 0) -> int:
    row = next(r for r in X_OPTIONS if r[0] == code)
    mode, fsec = row[2], row[3]
    if mode == "zero":
        return 0
    if mode == "fixed":
        return math.ceil(float(fsec) / TMU_TO_SEC)
    return math.ceil(seconds / TMU_TO_SEC) if seconds and seconds > 0 else 0


def _i_tmu(code: str) -> int:
    return next(r[2] for r in I_OPTIONS if r[0] == code)


def _self_check() -> int:
    mult = RULE_SET["system_tmu_multiplier"]
    # GM: 伸手20→A6, B0, 抓握G6, 伸手25→A10, B0, 放無方向P6, A0 = 28
    gm = (_a_tmu(reach=20) + 0 + _g_tmu("g_grasp", {}) + _a_tmu(reach=25) + 0
          + _p_tmu("p_place_none", [], False) + 0) * mult
    # CM: 伸手25→A10, B0, 接觸G3(勾contact), 推18→M16, X0, I0, A0 = 29
    cm = (_a_tmu(reach=25) + 0 + _g_tmu("g_touch", {"contact": True})
          + _m_tmu([{"verb": "m_push", "distance_cm": 18}]) + _x_tmu("x_none") + _i_tmu("i_none") + 0) * mult
    ok_gm, ok_cm = gm == 28, cm == 29
    print(f"  {'✅' if ok_gm else '❌'} 工廠 seed 資料 → GM = {gm} (期望 28)")
    print(f"  {'✅' if ok_cm else '❌'} 工廠 seed 資料 → CM = {cm} (期望 29)")
    # 抽查：B 1205 值、M 階梯 30cm→24、X 10S→278、旋轉 dia10/2圈→32
    checks = [
        ("B 值 = {0,10,32,42}", {b[2] for b in B_OPTIONS} == {0, 10, 32, 42}),
        ("M 推 30cm → 24", _ladder(30) == 24),
        ("M 推 30.1cm → 42", _ladder(30.1) == 42),
        ("X 10S → 278", _x_tmu("x_press", 10) == 278),
        ("旋轉 dia10/2圈 → 32", _m_tmu([{"verb": "m_rotate", "diameter_cm": 10, "revolutions": 2}]) == 32),
    ]
    fails = 0 if ok_gm and ok_cm else 1
    for name, cond in checks:
        print(f"  {'✅' if cond else '❌'} {name}")
        fails += 0 if cond else 1
    print(f"\n{'='*46}\nseed 資料驗證：{'✅ 全部通過' if fails == 0 else f'❌ {fails} 項失敗'}\n{'='*46}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_self_check())
