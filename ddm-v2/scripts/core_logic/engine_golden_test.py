#!/usr/bin/env python3
"""most_engine 黃金/反例測試（對「讀 DB 資料的引擎」跑，非硬編 validator）。

主錨＝`MINIMOST_FACTORY_V2`（v3 IE 認證字典，ADR-014）＋ V1 回放段（快照隔離證明）。
黃金值語意（impl-02 E8）：CM 的「推 18」＝18 吋＝45cm；X 為 half-up 3 位；G 無 gating（V2 資料）。
這就是 system-architecture-v2 §3.4 的 CI 防線：引擎 + 資料 一起被鎖。

執行：cd ddm-v2 && PYTHONPATH=src python3 scripts/core_logic/engine_golden_test.py
"""
from __future__ import annotations

from ddm_v2.most_engine import SequenceError, build_from_seed, build_from_seed_v2, compute_cycle, compute_table

RS = build_from_seed_v2()
RS_V1 = build_from_seed()


def _a(reach=0, twist=0, foot=0):
    return {"reach_cm": reach, "twist_deg": twist, "foot_cm": foot}


def _gm(a0, g, a3, p, a6, b1=None, b4=None):
    return {"seq": "GM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: a3, 4: {"b_code": b4}, 5: p, 6: a6}}


def _cm(a0, g, m, x, i, a6, b1=None):
    return {"seq": "CM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: m, 4: x, 5: i, 6: a6}}


def _gm_gold():
    return _gm(_a(reach=20), {"g_code": "g_grasp"}, _a(reach=25), {"p_base_code": "p_place_none"}, _a())


def _cm_gold():
    return _cm(_a(reach=25), {"g_code": "g_touch"},
               {"m_components": [{"verb_code": "m_push", "distance_cm": 45}]},
               {"x_code": "x_none"}, {"i_code": "i_none"}, _a())


def _run() -> int:
    passed = failed = 0

    def chk(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}  {detail}")

    def err(name, code, fn):
        nonlocal passed, failed
        try:
            fn()
        except SequenceError as e:
            chk(f"{name}（擋下 {code}）", e.code == code, f"got {e.code}")
        except Exception as e:  # noqa: BLE001
            chk(name, False, f"got {type(e).__name__}: {e}")
        else:
            chk(name, False, "未報錯")

    print("\n── A. 黃金（引擎讀 V2 seed 資料）──")
    r = compute_cycle(_gm_gold(), RS)
    chk("GM = 28 TMU", r.total_tmu == 28, f"{r.total_tmu} ({r.tech_line})")
    chk("GM 秒 = 1.008", abs(r.total_seconds - 28 * 0.036) < 1e-9)
    r = compute_cycle(_cm_gold(), RS)
    chk("CM = 29 TMU（推 45cm＝18 吋檔）", r.total_tmu == 29, f"{r.total_tmu} ({r.tech_line})")
    chk("單位回歸反例：推 18cm → M10", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[3] == 10)

    print("\n── B. A 三分量／A3 返回（E1）──")
    chk("max(伸手6,手度3)=6", compute_cycle(_gm(_a(20, 120), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[0] == 6)
    chk("邊界 20→6 / 20.01→10", RS.band_index("reach", 20) == 6 and RS.band_index("reach", 20.01) == 10)
    chk("返回 25cm → 10", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(reach=25)), RS).slot_tmus[6] == 10)
    err("返回格帶手度", "A_RETURN_COMPONENT", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(reach=25, twist=90)), RS))
    err("A 負值", "A_NEGATIVE", lambda: compute_cycle(_gm(_a(reach=-5), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), RS))

    print("\n── C. B（1205 值，by code）──")
    chk("B 站立=42", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_stand"), RS).slot_tmus[1] == 42)
    chk("B 預設 b_none=0", compute_cycle(_gm_gold(), RS).slot_tmus[1] == 0)
    err("B 未知 code", "B_UNKNOWN", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_zzz"), RS))

    print("\n── D. G（V2 無 gating——選項即語意，ADR-014）──")
    chk("抓握=6", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[2] == 6)
    chk("接觸（無需勾修飾）=3", compute_cycle(_gm(_a(), {"g_code": "g_touch"}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[2] == 3)
    chk("拿取(選取-小)=16", compute_cycle(_gm(_a(), {"g_code": "g_pick_small"}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[2] == 16)
    err("G 未知", "G_UNKNOWN", lambda: compute_cycle(_gm(_a(), {"g_code": "g_zzz"}, _a(), {"p_base_code": "p_toss"}, _a()), RS))

    print("\n── E. P base+附加（E3：互斥／無 base 顯式錯；V2 對準直接加成）──")
    chk("組一種+對準=24", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_asm_single", "p_addon_codes": ["a_align"]}, _a()), RS).slot_tmus[5] == 24)
    chk("放無方向+插入+施壓=30", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_none", "p_addon_codes": ["a_insert", "a_press"]}, _a()), RS).slot_tmus[5] == 30)
    err("插入⊥卡合", "P_ADDON_CONFLICT", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_asm_single", "p_addon_codes": ["a_insert", "a_snap"]}, _a()), RS))
    err("有附加無 base", "P_ADDON_NO_BASE", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_addon_codes": ["a_insert"]}, _a()), RS))
    err("P 超過2附加", "P_TOO_MANY_ADDONS", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss", "p_addon_codes": ["a_insert", "a_hard", "a_press"]}, _a()), RS))
    err("P 重複附加", "P_DUP_ADDON", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss", "p_addon_codes": ["a_insert", "a_insert"]}, _a()), RS))

    print("\n── F. M：階梯 cm 正確值／腳步獨立帶／範圍錯誤（E9）──")
    chk("階梯 45→16 / 45.1→24 / 75→24", RS.ladder_tmu(45) == 16 and RS.ladder_tmu(45.1) == 24 and RS.ladder_tmu(75) == 24)
    err("推 76cm 超界", "M_DISTANCE_RANGE", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_push", "distance_cm": 76}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS))
    chk("腳步 30cm→16（獨立帶）/ 80cm→42", RS.foot_tmu(30) == 16 and RS.foot_tmu(80) == 42)
    chk("多分量 max(理10cm→6,手度180→10)=10", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_li", "distance_cm": 10}, {"verb_code": "m_hand", "angle_deg": 180}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[3] == 10)
    err("手度 181° 超界", "M_HAND_RANGE", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_hand", "angle_deg": 181}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS))
    chk("旋轉 dia10/2圈=32", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": 2}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[3] == 32)
    err("旋轉 dia60 超界", "M_ROTATION_RANGE", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_rotate", "diameter_cm": 60, "revolutions": 1}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS))
    err("M 未知動詞", "M_UNKNOWN", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_zzz"}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS))

    print("\n── G. X：half-up（E2）＋九檔 ──")
    chk("並壓合 10 秒=277.778", abs(compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": 10}, {"i_code": "i_none"}, _a()), RS).slot_tmus[4] - 277.778) < 1e-9)
    chk("刷條形碼固定=6", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_scan_bar"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[4] == 6)
    chk("並鎖附固定=6", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_screw_fix"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[4] == 6)
    err("X 未知", "X_UNKNOWN", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_zzz"}, {"i_code": "i_none"}, _a()), RS))
    err("X 負秒", "X_NEGATIVE", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": -1}, {"i_code": "i_none"}, _a()), RS))

    print("\n── H. I：八檔（含視線外）──")
    chk("並對齊(正常·兩點)=16", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_none"}, {"i_code": "i_align2"}, _a()), RS).slot_tmus[5] == 16)
    chk("並對齊(視線外·兩點)=32", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_none"}, {"i_code": "i_align2_out"}, _a()), RS).slot_tmus[5] == 32)
    err("I 未知", "I_UNKNOWN", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_none"}, {"i_code": "i_zzz"}, _a()), RS))

    print("\n── I. repeat（E4）＋人工覆寫（E7）──")
    chk("G×2=12", compute_cycle(_gm(_a(), {"g_code": "g_grasp", "repeat_count": 2}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[2] == 12)
    chk("M 推45×3 只乘動詞再 max=48", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_push", "distance_cm": 45}, {"verb_code": "m_hand", "angle_deg": 180}], "repeat_count": 3}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[3] == 48)
    err("repeat=0", "REPEAT_INVALID", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp", "repeat_count": 0}, _a(), {"p_base_code": "p_toss"}, _a()), RS))
    err("A 格 repeat", "REPEAT_INVALID", lambda: compute_cycle(_gm({**_a(reach=10), "repeat_count": 2}, {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), RS))
    ov = _gm_gold()
    ov["slots"][5] = {**ov["slots"][5], "manual_override": {"tmu": 10, "reason": "現場實測", "by": "E123"}}
    r = compute_cycle(ov, RS)
    chk("覆寫 P→10、總 32、tech 標*", r.total_tmu == 32 and "P10*" in r.tech_line and r.overrides[0]["auto_tmu"] == 6)
    bad = _gm_gold()
    bad["slots"][5] = {**bad["slots"][5], "manual_override": {"tmu": 5, "reason": " "}}
    err("覆寫 reason 空", "OVERRIDE_INVALID", lambda: compute_cycle(bad, RS))

    print("\n── J. 結構（GM↔CM 不可混用）──")
    err("GM 的 P slot 帶 m_components", "SLOT_CROSS_MODEL", lambda: compute_cycle({"seq": "GM", "slots": {0: _a(), 1: {}, 2: {"g_code": "g_grasp"}, 3: _a(), 4: {}, 5: {"m_components": []}, 6: _a()}}, RS))
    err("CM 的 slot5 帶 p_base_code", "SLOT_CROSS_MODEL", lambda: compute_cycle({"seq": "CM", "slots": {0: _a(), 1: {}, 2: {"g_code": "g_grasp"}, 3: {"m_components": []}, 4: {"x_code": "x_none"}, 5: {"p_base_code": "p_toss"}, 6: _a()}}, RS))
    err("未知 seq", "SEQ_KIND", lambda: compute_cycle({"seq": "XX", "slots": {}}, RS))

    print("\n── K. 整表 SIMO/freq ──")
    table = compute_table([{**_gm_gold(), "frequency": 2}, {**_cm_gold(), "frequency": 1, "simo_group_id": "S1"}, {**_cm_gold(), "frequency": 1, "simo_group_id": "S1"}], RS)
    chk("56 + max(29,29) = 85", table["total_tmu"] == 85, f'{table["total_tmu"]}')
    err("freq<=0", "FREQ_INVALID", lambda: compute_table([{**_gm_gold(), "frequency": 0}], RS))

    print("\n── L. V1 回放（快照隔離：舊資料＋舊規則＝舊行為）──")
    chk("V1 GM=28", compute_cycle(_gm_gold(), RS_V1).total_tmu == 28)
    cm_v1 = _cm(_a(reach=25), {"g_code": "g_touch", "modifiers": {"contact": True}}, {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    chk("V1 CM=29（V1 階梯語意 18→16）", compute_cycle(cm_v1, RS_V1).total_tmu == 29)
    chk("V1 gating：接觸未勾=0", compute_cycle(_gm(_a(), {"g_code": "g_touch"}, _a(), {"p_base_code": "p_toss"}, _a()), RS_V1).slot_tmus[2] == 0)
    chk("V1 對準未勾精度=16", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_single", "p_addon_codes": ["a_align"]}, _a()), RS_V1).slot_tmus[5] == 16)
    chk("V1 階梯 30→24 / 30.1→42", RS_V1.ladder_tmu(30) == 24 and RS_V1.ladder_tmu(30.1) == 42)

    print(f"\n{'='*52}\n引擎黃金/反例：{passed} passed, {failed} failed\n{'='*52}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_run())
