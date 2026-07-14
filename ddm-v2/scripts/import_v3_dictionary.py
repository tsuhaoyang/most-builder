"""v3 IE 認證字典 → `MINIMOST_FACTORY_V2` seed 轉換器（ADR-014 / impl-01 §3）。

讀 docs/v3/reference/minimost_ai_dictionary_v1.json（值的唯一權威），
產出 src/ddm_v2/seed/v2/rule_set_seed_v2.py（AUTO-GENERATED，禁手改）。

鐵則：
- 純函數轉換；JSON 出現而對照表沒有的 option_code → 報錯中止（不得靜默丟棄）。
- M ladder 動詞的距離檔位必須全動詞一致，收斂為單一階梯；不一致 → 中止。
- b_none / x_none / i_none 三個顯式零值列由本轉換器注入（v3 以「未選=0」表達）。

用法：cd ddm-v2 && python3 scripts/import_v3_dictionary.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DICT_PATH = ROOT / "docs/v3/reference/minimost_ai_dictionary_v1.json"
OUT_PATH = ROOT / "src/ddm_v2/seed/v2/rule_set_seed_v2.py"

# ── v3 option_code → v2 code 對照（impl-01 §2；未列者＝中止）──
G_MAP = {
    "G_LIGHT_PRESS": "g_tap", "G_TOUCH": "g_touch", "G_LIGHT_TAP": "g_pat",
    "G_GRASP": "g_grasp", "G_PICK": "g_grab", "G_REGRASP": "g_regrasp",
    "G_TRANSFER_HAND": "g_handchange", "G_SELECT": "g_pick_sel",
    "G_SELECT_SMALL": "g_pick_small", "G_SEPARATE": "g_pullout", "G_COLLECT": "g_pick_collect",
}
P_BASE_MAP = {  # code -> (v2_code, category, direction_mode)
    "P_THROW": ("p_toss", "toss", None), "P_HOLD": ("p_hold", "hold", None),
    "P_PLACE_NO_DIRECTION": ("p_place_none", "place", "none"),
    "P_PLACE_MULTI_DIRECTION": ("p_place_multi", "place", "multi"),
    "P_PLACE_ONE_DIRECTION": ("p_place_single", "place", "single"),
    "P_ASSEMBLE_MULTI_DIRECTION": ("p_asm_multi", "assemble", "multi"),
    "P_ASSEMBLE_ONE_DIRECTION": ("p_asm_single", "assemble", "single"),
}
P_ADDON_MAP = {
    "P_ALIGN_LT_4MM": "a_align", "P_INSERT": "a_insert", "P_DIFFICULT_HANDLE": "a_hard",
    "P_SNAP_FIT": "a_snap", "P_APPLY_PRESSURE": "a_press",
}
M_VERB_MAP = {  # sentence_text_zh -> v2 code（ladder 類以動詞字歸組）
    "理": "m_li", "穿": "m_through", "推": "m_push", "拉": "m_pull", "貼附": "m_attach",
    "去除": "m_remove", "撕除": "m_teartape", "折": "m_fold", "擦拭": "m_wipe", "撕開": "m_tearopen",
}
M_FIXED_MAP = {"M_PRESS_BUTTON": "m_btn", "M_SLIDE_OUT_SCREW": "m_screw",
               "M_PRESS": "m_press"}  # M_PRESS：v3 現場字典同步 2026-07-14（按壓 / fixed 3 TMU）
M_ROTATE_MAP = {  # option_code -> (max_dia, revolutions)
    "M_ROTATE_D12_1": (12.5, 1), "M_ROTATE_D12_2": (12.5, 2), "M_ROTATE_D12_3": (12.5, 3),
    "M_ROTATE_D50_1": (50.0, 1), "M_ROTATE_D50_2": (50.0, 2),
}
X_MAP = {
    "X_PRESS_MACHINE": "x_press", "X_SNAP_PRESS_MACHINE": "x_snap_press",
    "X_HOT_MELT_MACHINE": "x_heat", "X_DISPENSE_GLUE": "x_glue", "X_SCREW_FIX": "x_screw_fix",
    "X_LASER_MARK": "x_laser", "X_SCAN_PPID": "x_scan_ppid",
    "X_SCAN_WORK_ORDER_QR": "x_scan_wo", "X_SCAN_BARCODE": "x_scan_bar",
    "X_BLOW_CLEAN": "x_blow_clean",  # v3 現場字典同步 2026-07-14（user-input-seconds 模式）
}
I_MAP = {
    "I_CHECK_NORMAL": "i_check", "I_CONFIRM_NORMAL": "i_confirm",
    "I_ALIGN_POINT_NORMAL": "i_align1", "I_ALIGN_TWO_POINTS_NORMAL": "i_align2",
    "I_CHECK_OUTSIDE": "i_check_out", "I_CONFIRM_OUTSIDE": "i_confirm_out",
    "I_ALIGN_POINT_OUTSIDE": "i_align1_out", "I_ALIGN_TWO_POINTS_OUTSIDE": "i_align2_out",
}

_NUM = re.compile(r"([\d.]+)")


def _bound(condition_zh: str) -> float | None:
    """condition_zh 如 '<=20cm' / '<=30°' → 上界；'>...' → None（overflow 帶）。"""
    c = (condition_zh or "").strip()
    if c.startswith(">"):
        return None
    m = _NUM.search(c)
    if not m:
        raise SystemExit(f"[中止] 無法解析 condition_zh: {condition_zh!r}")
    return float(m.group(1))


def _die(msg: str) -> None:
    raise SystemExit(f"[中止] {msg}")


def convert() -> dict:
    d = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    p = d["parameters"]
    out: dict = {}

    # A：三分量帶（component, max, index, sort）
    a_rows = []
    comp_map = {"reach_distance": "reach", "hand_degree": "twist", "foot_step": "foot"}
    for ck, comp in comp_map.items():
        for so, o in enumerate(p["A"]["controls"][ck]["options"]):
            a_rows.append((comp, _bound(o["condition_zh"]), int(o["tmu_value"]), so))
    out["A_BANDS"] = a_rows

    # B：注入 b_none 預設 + 三檔（code, label, index, is_default, sort, sentence）
    b_rows = [("b_none", "無身體動作", 0, True, 0, "")]
    b_map = {"B_EYE_MOVE": "b_eye", "B_BEND_OR_SIT": "b_bend", "B_STAND": "b_stand"}
    for so, o in enumerate(p["B"]["options"], start=1):
        code = b_map.get(o["option_code"]) or _die(f"未知 B option：{o['option_code']}")
        b_rows.append((code, o["display_text_zh"], int(o["tmu_value"]), False, so, o.get("sentence_text_zh", "")))
    out["B_OPTIONS"] = b_rows

    # G：gating 全關（code, label, modifier_key, requires_modifier, base_tmu, sort, sentence）
    g_rows = []
    for so, o in enumerate(p["G"]["options"]):
        code = G_MAP.get(o["option_code"]) or _die(f"未知 G option：{o['option_code']}")
        g_rows.append((code, o["display_text_zh"], None, False, int(o["tmu_value"]), so, o.get("sentence_text_zh", "")))
    out["G_ACTIONS"] = g_rows

    # P base（code, label, category, direction_mode, base_tmu, sort, sentence）
    pb_rows = []
    for so, o in enumerate(p["P"]["base_actions"]):
        v2c, cat, dm = P_BASE_MAP.get(o["option_code"]) or _die(f"未知 P base：{o['option_code']}")
        pb_rows.append((v2c, o["display_text_zh"], cat, dm, int(o["tmu_value"]), so, o.get("sentence_text_zh", "")))
    out["P_BASES"] = pb_rows

    # P addon（code, label, delta, needs_precision=False, sort, display_rule, sentence）
    pa_rows = []
    for so, o in enumerate(p["P"]["modifiers"]):
        code = P_ADDON_MAP.get(o["option_code"]) or _die(f"未知 P addon：{o['option_code']}")
        pa_rows.append((code, o["display_text_zh"], int(o["tmu_value"]), False, so,
                        o.get("display_rule", "show_self"), o.get("sentence_text_zh", "")))
    out["P_ADDONS"] = pa_rows

    # M：verbs（fixed/ladder/rotate/hand/foot）＋ ladder 收斂驗證
    verbs = p["M"]["controls"]["verb"]["options"]
    ladders: dict[str, list[tuple[float | None, int]]] = {}
    m_verb_rows, m_rot_rows = [], []
    so = 0
    seen_fixed, seen_rot = set(), set()
    for o in verbs:
        code = o["option_code"]
        if code in M_FIXED_MAP:
            if M_FIXED_MAP[code] not in seen_fixed:
                seen_fixed.add(M_FIXED_MAP[code])
                m_verb_rows.append((M_FIXED_MAP[code], o["display_text_zh"], "fixed", int(o["tmu_value"]), so, o.get("sentence_text_zh", "")))
                so += 1
        elif code in M_ROTATE_MAP:
            dia, rev = M_ROTATE_MAP[code]
            m_rot_rows.append((dia, rev, int(o["tmu_value"]), len(m_rot_rows)))
            if "m_rotate" not in seen_rot:
                seen_rot.add("m_rotate")
                m_verb_rows.append(("m_rotate", "旋轉", "rotate", None, so, o.get("sentence_text_zh", "旋轉")))
                so += 1
        elif o.get("input_type") == "distance_range":
            verb_zh = o.get("sentence_text_zh") or _die(f"距離動詞缺 sentence_text_zh：{code}")
            v2c = M_VERB_MAP.get(verb_zh) or _die(f"未知 M 距離動詞：{verb_zh}（{code}）")
            ladders.setdefault(v2c, []).append((_bound(o["condition_zh"]), int(o["tmu_value"])))
            if all(r[0] != v2c for r in m_verb_rows):
                m_verb_rows.append((v2c, verb_zh, "ladder", None, so, verb_zh))
                so += 1
        else:
            _die(f"未知 M verb option：{code}")
    # ladder 收斂：全部動詞的檔位必須相同
    canonical = sorted(next(iter(ladders.values())))
    for v2c, rows in ladders.items():
        if sorted(rows) != canonical:
            _die(f"M ladder 不一致：{v2c} {sorted(rows)} != {canonical}")
    out["M_LADDER"] = [(mx, tmu, so) for so, (mx, tmu) in enumerate(canonical)]  # 無 overflow 檔（殘項#1）
    out["M_ROTATION"] = m_rot_rows  # 無大直徑 overflow / D50 3圈（殘項#2）

    # M hand / foot（skip *_NONE 列——引擎以「無輸入=0」表達）
    mh = [( _bound(o["condition_zh"]), int(o["tmu_value"]))
          for o in p["M"]["controls"]["hand_degree"]["options"] if o.get("condition_zh") != "default_none"]
    out["M_HAND"] = [(mx, tmu, so) for so, (mx, tmu) in enumerate(sorted(mh))]
    mf = [(_bound(o["condition_zh"]), int(o["tmu_value"]))
          for o in p["M"]["controls"]["foot_step"]["options"] if o.get("condition_zh") != "default_none"]
    mf_sorted = sorted(mf, key=lambda r: (r[0] is None, r[0] or 0))
    out["M_FOOT"] = [(mx, tmu, so) for so, (mx, tmu) in enumerate(mf_sorted)]
    # foot 動詞掛尾（走 M_FOOT 表）；hand 動詞
    m_verb_rows.append(("m_hand", "手度", "hand", None, so, ""))
    so += 1
    m_verb_rows.append(("m_foot", "腳步", "foot", None, so, ""))
    so += 1
    out["M_VERBS"] = m_verb_rows

    # X：注入 x_none ＋ 九檔（code, label, mode, fixed_seconds, sort, sentence）
    x_rows = [("x_none", "無機台等待", "zero", None, 0, "")]
    for so, o in enumerate(p["X"]["options"], start=1):
        code = X_MAP.get(o["option_code"]) or _die(f"未知 X option：{o['option_code']}")
        mode = "fixed" if o.get("seconds_source") == "fixed_seconds" else "seconds"
        x_rows.append((code, o["display_text_zh"], mode, o.get("fixed_seconds"), so, o.get("sentence_text_zh", "")))
    out["X_OPTIONS"] = x_rows

    # I：注入 i_none ＋ 八檔（code, label, index, sort, vision_scope, sentence）
    i_rows = [("i_none", "不額外對齊", 0, 0, None, "")]
    for so, o in enumerate(p["I"]["options"], start=1):
        code = I_MAP.get(o["option_code"]) or _die(f"未知 I option：{o['option_code']}")
        scope = "outside" if o["option_code"].endswith("_OUTSIDE") else "normal"
        i_rows.append((code, o["display_text_zh"], int(o["tmu_value"]), so, scope, o.get("sentence_text_zh", "")))
    out["I_OPTIONS"] = i_rows

    return out


HEADER = '''"""`MINIMOST_FACTORY_V2` seed —— v3 IE 認證字典（ADR-014 值權威）。

⚠️ AUTO-GENERATED by scripts/import_v3_dictionary.py — 禁止手改數值；
   改值＝改 docs/v3/reference/minimost_ai_dictionary_v1.json（IE 認證流程）後重跑轉換器。

與 V1 的裁決差異（詳 docs/v3/impl/impl-01）：M 階梯門檻修正為 cm 正確值（2.5/10/25/45/75，無 overflow 檔）；
M 腳步獨立帶（M_FOOT）；G gating 全關（選項即語意）；I 八檔（含視線外）；X 九檔；X 捨入 half-up（引擎 E2）。
"""
from __future__ import annotations

import uuid
from typing import Any

TMU_TO_SEC = 0.036

RULE_SET = {"code": "MINIMOST_FACTORY_V2", "name_zh": "MiniMOST 工廠規則 v2（v3 IE 認證）", "system_tmu_multiplier": 1}
'''

FOOTER = r'''

# ───────────────────────── DB 插入 ─────────────────────────
def seed_rule_set_factory_v2(session: Any) -> Any:
    """插入 V2 rule-set 與所有子表（published）。idempotent 由呼叫端以 code 查重。回傳 RuleSet。"""
    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet

    rs = RuleSet(id=uuid.uuid4(), code=RULE_SET["code"], name_zh=RULE_SET["name_zh"],
                 status="published", system_tmu_multiplier=RULE_SET["system_tmu_multiplier"])
    session.add(rs)
    _id = uuid.uuid4

    for comp, mx, iv, so in A_BANDS:
        session.add(rt.RuleABand(id=_id(), rule_set_id=rs.id, component=comp, max_value=mx, index_value=iv, sort_order=so))
    for code, lab, iv, dft, so, sent in B_OPTIONS:
        session.add(rt.RuleBOption(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, index_value=iv,
                                   is_default=dft, sort_order=so, sentence_text_zh=sent or None))
    for code, lab, mod, req, tmu, so, sent in G_ACTIONS:
        session.add(rt.RuleGAction(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, modifier_key=mod,
                                   requires_modifier=req, base_tmu=tmu, sort_order=so, sentence_text_zh=sent or None))
    for code, lab, cat, dm, tmu, so, sent in P_BASES:
        session.add(rt.RulePBase(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, category=cat,
                                 direction_mode=dm, base_tmu=tmu, sort_order=so, sentence_text_zh=sent or None))
    for code, lab, dt, prec, so, drule, sent in P_ADDONS:
        session.add(rt.RulePAddon(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, delta_tmu=dt,
                                  needs_precision=prec, sort_order=so, display_rule=drule, sentence_text_zh=sent or None))
    for mx, tmu, so in M_LADDER:
        session.add(rt.RuleMLadderBand(id=_id(), rule_set_id=rs.id, max_cm=mx, tmu=tmu, sort_order=so))
    for mx, tmu, so in M_FOOT:
        session.add(rt.RuleMFootBand(id=_id(), rule_set_id=rs.id, max_cm=mx, tmu=tmu, sort_order=so))
    for code, lab, kind, ftmu, so, sent in M_VERBS:
        session.add(rt.RuleMVerb(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, pricing_kind=kind,
                                 fixed_tmu=ftmu, sort_order=so, sentence_text_zh=sent or None))
    for mx, rev, tmu, so in M_ROTATION:
        session.add(rt.RuleMRotationBand(id=_id(), rule_set_id=rs.id, max_diameter_cm=mx, revolutions=rev, tmu=tmu, sort_order=so))
    for mx, tmu, so in M_HAND:
        session.add(rt.RuleMHandBand(id=_id(), rule_set_id=rs.id, max_deg=mx, tmu=tmu, sort_order=so))
    for code, lab, mode, fsec, so, sent in X_OPTIONS:
        session.add(rt.RuleXOption(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, mode=mode,
                                   fixed_seconds=fsec, sort_order=so, sentence_text_zh=sent or None))
    for code, lab, iv, so, scope, sent in I_OPTIONS:
        session.add(rt.RuleIOption(id=_id(), rule_set_id=rs.id, code=code, label_zh=lab, index_value=iv,
                                   sort_order=so, vision_scope=scope, sentence_text_zh=sent or None))
    return rs


# ───────────── 自我驗證（黃金錨；引擎重錨見 impl-02 E8）─────────────
def _self_check() -> int:
    from ddm_v2.most_engine import compute_cycle
    from ddm_v2.most_engine.providers import build_from_seed_v2

    rs = build_from_seed_v2()

    def _a(reach=0):
        return {"reach_cm": reach}

    gm = compute_cycle({"seq": "GM", "slots": {0: _a(20), 1: {}, 2: {"g_code": "g_grasp"}, 3: {"reach_cm": 25}, 4: {}, 5: {"p_base_code": "p_place_none"}, 6: _a()}}, rs)
    cm = compute_cycle({"seq": "CM", "slots": {0: _a(25), 1: {}, 2: {"g_code": "g_touch"}, 3: {"m_components": [{"verb_code": "m_push", "distance_cm": 45}]}, 4: {"x_code": "x_none"}, 5: {"i_code": "i_none"}, 6: _a()}}, rs)
    checks = [
        ("GM 黃金 = 28", gm.total_tmu == 28),
        ("CM 黃金 = 29（推 45cm=18 吋檔）", cm.total_tmu == 29),
        ("M 推 30cm → 16（≤45 檔）", rs.ladder_tmu(30) == 16),
        ("M 腳步 30cm → 16（foot 帶 ≤40）", rs.foot_tmu(30) == 16),
        ("X 10s → 277.778（half-up）", abs(rs.seconds_to_tmu(10) - 277.778) < 1e-9),
        ("X 0.216s → 6", abs(rs.seconds_to_tmu(0.216) - 6.0) < 1e-9),
        ("G 接觸（無 gating）→ 3", rs.g_actions["g_touch"].base_tmu == 3 and not rs.g_actions["g_touch"].requires_modifier),
        ("I 視線外對齊兩點 → 32", rs.i_index["i_align2_out"] == 32),
        ("B 值 = {0,10,32,42}", {r[2] for r in B_OPTIONS} == {0, 10, 32, 42}),
        ("M ladder 無 overflow（>75 應由引擎報錯）", M_LADDER[-1][0] == 75.0),
    ]
    fails = 0
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        fails += 0 if ok else 1
    print(f"\n{'='*46}\nV2 seed 驗證：{'✅ 全部通過' if fails == 0 else f'❌ {fails} 項失敗'}\n{'='*46}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_self_check())
'''


def emit(out: dict) -> str:
    def fmt_rows(name: str, rows: list, comment: str) -> str:
        body = "\n".join(f"    {r!r}," for r in rows)
        return f"# {comment}\n{name} = [\n{body}\n]\n"

    parts = [HEADER]
    parts.append(fmt_rows("A_BANDS", out["A_BANDS"], "component, max_value(None=overflow), index, sort"))
    parts.append(fmt_rows("B_OPTIONS", out["B_OPTIONS"], "code, label_zh, index, is_default, sort, sentence_zh（b_none 為轉換器注入）"))
    parts.append(fmt_rows("G_ACTIONS", out["G_ACTIONS"], "code, label_zh, modifier_key(=None), requires_modifier(=False), base_tmu, sort, sentence_zh"))
    parts.append(fmt_rows("P_BASES", out["P_BASES"], "code, label_zh, category, direction_mode, base_tmu, sort, sentence_zh"))
    parts.append(fmt_rows("P_ADDONS", out["P_ADDONS"], "code, label_zh, delta_tmu, needs_precision(=False), sort, display_rule, sentence_zh"))
    parts.append(fmt_rows("M_LADDER", out["M_LADDER"], "max_cm, tmu, sort ——【C1 定案】吋(cm) 正確值；無 overflow（>75 → 422）"))
    parts.append(fmt_rows("M_FOOT", out["M_FOOT"], "max_cm(None=overflow), tmu, sort ——【C2 定案】M 腳步獨立帶"))
    parts.append(fmt_rows("M_VERBS", out["M_VERBS"], "code, label_zh, pricing_kind, fixed_tmu, sort, sentence_zh"))
    parts.append(fmt_rows("M_ROTATION", out["M_ROTATION"], "max_diameter_cm, revolutions, tmu, sort ——無 D50 3圈/大直徑 overflow（殘項#2）"))
    parts.append(fmt_rows("M_HAND", out["M_HAND"], "max_deg, tmu, sort ——≤180 封頂（>180 → 422）"))
    parts.append(fmt_rows("X_OPTIONS", out["X_OPTIONS"], "code, label_zh, mode, fixed_seconds, sort, sentence_zh（x_none 為轉換器注入）"))
    parts.append(fmt_rows("I_OPTIONS", out["I_OPTIONS"], "code, label_zh, index, sort, vision_scope, sentence_zh（i_none 為轉換器注入）"))
    parts.append(FOOTER)
    return "\n".join(parts)


def main() -> int:
    out = convert()
    OUT_PATH.write_text(emit(out), encoding="utf-8")
    counts = {k: len(v) for k, v in out.items()}
    print(f"已產出 {OUT_PATH.relative_to(ROOT)}")
    for k, v in counts.items():
        print(f"  {k}: {v} 列")
    return 0


if __name__ == "__main__":
    sys.exit(main())
