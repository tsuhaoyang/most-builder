#!/usr/bin/env python3
"""most_engine 黃金/反例測試（對「讀 DB 資料的引擎」跑，非硬編 validator）。

用 build_from_seed() 取工廠 rule-set 當 fixture，斷言引擎重現規格黃金值（GM=28/CM=29）
與所有 edge case。這就是 system-architecture-v2 §3.4 的 CI 防線：引擎 + 資料 一起被鎖。

執行（需 app 套件路徑）：
    cd ddm-v2 && PYTHONPATH=src python3 scripts/core_logic/engine_golden_test.py
"""
from __future__ import annotations

import math

from ddm_v2.most_engine import SequenceError, build_from_seed, compute_cycle, compute_table

RS = build_from_seed()


def _a(reach=0, twist=0, foot=0):
    return {"reach_cm": reach, "twist_deg": twist, "foot_cm": foot}


def _gm(a0, g, a3, p, a6, b1=None, b4=None):
    return {"seq": "GM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: a3, 4: {"b_code": b4}, 5: p, 6: a6}}


def _cm(a0, g, m, x, i, a6, b1=None):
    return {"seq": "CM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: m, 4: x, 5: i, 6: a6}}


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

    print("\n── A. 黃金（引擎讀 seed 資料）──")
    gm = _gm(_a(reach=20), {"g_code": "g_grasp"}, _a(reach=25), {"p_base_code": "p_place_none"}, _a())
    r = compute_cycle(gm, RS)
    chk("GM = 28 TMU", r.total_tmu == 28, f"{r.total_tmu} ({r.tech_line})")
    chk("GM 秒 = 1.008", abs(r.total_seconds - 28 * 0.036) < 1e-9)
    cm = _cm(_a(reach=25), {"g_code": "g_touch", "modifiers": {"contact": True}},
             {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]},
             {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    r = compute_cycle(cm, RS)
    chk("CM = 29 TMU", r.total_tmu == 29, f"{r.total_tmu} ({r.tech_line})")

    print("\n── B. A 三分量 ──")
    chk("max(伸手6,手度3)=6", compute_cycle(_gm(_a(20, 120), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[0] == 6)
    chk("邊界 20→6 / 20.01→10", RS.band_index("reach", 20) == 6 and RS.band_index("reach", 20.01) == 10)
    err("A 負值", "A_NEGATIVE", lambda: compute_cycle(_gm(_a(reach=-5), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), RS))

    print("\n── C. B（1205 值，by code）──")
    chk("B 站立=42", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_stand"), RS).slot_tmus[1] == 42)
    chk("B 預設 b_none=0", compute_cycle(gm, RS).slot_tmus[1] == 0)
    err("B 未知 code", "B_UNKNOWN", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_zzz"), RS))

    print("\n── D. G 修飾門檻 ──")
    chk("抓握無修飾=6", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[2] == 6)
    chk("接觸未勾=0", compute_cycle(_gm(_a(), {"g_code": "g_touch"}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[2] == 0)
    chk("接觸已勾=3", compute_cycle(_gm(_a(), {"g_code": "g_touch", "modifiers": {"contact": True}}, _a(), {"p_base_code": "p_toss"}, _a()), RS).slot_tmus[2] == 3)
    err("G 未知", "G_UNKNOWN", lambda: compute_cycle(_gm(_a(), {"g_code": "g_zzz"}, _a(), {"p_base_code": "p_toss"}, _a()), RS))

    print("\n── E. P base+附加+精度 ──")
    chk("組一種+插入+卡合=40", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_asm_single", "p_addon_codes": ["a_insert", "a_snap"]}, _a()), RS).slot_tmus[5] == 40)
    chk("對準未勾精度=16", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_single", "p_addon_codes": ["a_align"]}, _a()), RS).slot_tmus[5] == 16)
    chk("對準勾精度=24", compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_single", "p_addon_codes": ["a_align"], "precision": True}, _a()), RS).slot_tmus[5] == 24)
    err("P 超過2附加", "P_TOO_MANY_ADDONS", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss", "p_addon_codes": ["a_insert", "a_snap", "a_press"]}, _a()), RS))
    err("P 重複附加", "P_DUP_ADDON", lambda: compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss", "p_addon_codes": ["a_insert", "a_insert"]}, _a()), RS))

    print("\n── F. M 取 max/階梯/旋轉 ──")
    chk("推 30cm=24 / 30.1=42", RS.ladder_tmu(30) == 24 and RS.ladder_tmu(30.1) == 42)
    chk("多分量 max(理6,手度10)=10", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_li", "distance_cm": 4}, {"verb_code": "m_hand", "angle_deg": 180}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[3] == 10)
    chk("旋轉 dia10/2圈=32", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": 2}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[3] == 32)
    err("M 未知動詞", "M_UNKNOWN", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_zzz"}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), RS))

    print("\n── G. X 連續/固定 ──")
    chk("並壓合 5秒=139", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": 5}, {"i_code": "i_none"}, _a()), RS).slot_tmus[4] == math.ceil(5 / 0.036))
    chk("刷條碼固定=6", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_scan"}, {"i_code": "i_none"}, _a()), RS).slot_tmus[4] == 6)
    err("X 未知", "X_UNKNOWN", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_zzz"}, {"i_code": "i_none"}, _a()), RS))
    err("X 負秒", "X_NEGATIVE", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": -1}, {"i_code": "i_none"}, _a()), RS))

    print("\n── H. I ──")
    chk("並對齊=16", compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_none"}, {"i_code": "i_align2"}, _a()), RS).slot_tmus[5] == 16)
    err("I 未知", "I_UNKNOWN", lambda: compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_none"}, {"i_code": "i_zzz"}, _a()), RS))

    print("\n── I. 結構（GM↔CM 不可混用）──")
    err("GM 的 P slot 帶 m_components", "SLOT_CROSS_MODEL", lambda: compute_cycle({"seq": "GM", "slots": {0: _a(), 1: {}, 2: {"g_code": "g_grasp"}, 3: _a(), 4: {}, 5: {"m_components": []}, 6: _a()}}, RS))
    err("CM 的 slot5 帶 p_base_code", "SLOT_CROSS_MODEL", lambda: compute_cycle({"seq": "CM", "slots": {0: _a(), 1: {}, 2: {"g_code": "g_grasp"}, 3: {"m_components": []}, 4: {"x_code": "x_none"}, 5: {"p_base_code": "p_toss"}, 6: _a()}}, RS))
    err("未知 seq", "SEQ_KIND", lambda: compute_cycle({"seq": "XX", "slots": {}}, RS))

    print("\n── J. 整表 SIMO/freq ──")
    table = compute_table([{**gm, "frequency": 2}, {**cm, "frequency": 1, "simo_group_id": "S1"}, {**cm, "frequency": 1, "simo_group_id": "S1"}], RS)
    chk("56 + max(29,29) = 85", table["total_tmu"] == 85, f'{table["total_tmu"]}')
    err("freq<=0", "FREQ_INVALID", lambda: compute_table([{**gm, "frequency": 0}], RS))

    print(f"\n{'='*52}\n引擎黃金/反例：{passed} passed, {failed} failed\n{'='*52}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_run())
