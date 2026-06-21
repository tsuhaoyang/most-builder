"""MOST 引擎黃金/反例（純引擎，讀 seed rule-set，免 DB）。

鎖定 spec 黃金值（GM=28 / CM=29）與各格 edge case。對應原 scripts/core_logic/engine_golden_test.py。
"""
from __future__ import annotations

import math

import pytest

from ddm_v2.most_engine import SequenceError, compute_cycle, compute_table

pytestmark = pytest.mark.unit


def _a(reach=0, twist=0, foot=0):
    return {"reach_cm": reach, "twist_deg": twist, "foot_cm": foot}


def _gm(a0, g, a3, p, a6, b1=None, b4=None):
    return {"seq": "GM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: a3, 4: {"b_code": b4}, 5: p, 6: a6}}


def _cm(a0, g, m, x, i, a6, b1=None):
    return {"seq": "CM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: m, 4: x, 5: i, 6: a6}}


# ── 黃金 ──
def test_gm_golden_28(rs):
    r = compute_cycle(_gm(_a(reach=20), {"g_code": "g_grasp"}, _a(reach=25), {"p_base_code": "p_place_none"}, _a()), rs)
    assert r.total_tmu == 28
    assert abs(r.total_seconds - 28 * 0.036) < 1e-9


def test_cm_golden_29(rs):
    r = compute_cycle(_cm(_a(reach=25), {"g_code": "g_touch", "modifiers": {"contact": True}},
                          {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]},
                          {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), rs)
    assert r.total_tmu == 29


# ── A 三分量 ──
def test_a_max_of_components(rs):
    r = compute_cycle(_gm(_a(20, 120), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
    assert r.slot_tmus[0] == 6  # max(伸手6, 手度3)


def test_a_band_boundary(rs):
    assert rs.band_index("reach", 20) == 6
    assert rs.band_index("reach", 20.01) == 10


def test_a_negative_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(reach=-5), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
    assert e.value.code == "A_NEGATIVE"


# ── B（1205 值）──
def test_b_stand_42(rs):
    r = compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_stand"), rs)
    assert r.slot_tmus[1] == 42


def test_b_unknown_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_zzz"), rs)
    assert e.value.code == "B_UNKNOWN"


# ── G 修飾門檻 ──
def test_g_grasp_no_modifier_6(rs):
    assert compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), rs).slot_tmus[2] == 6


def test_g_touch_gating(rs):
    off = compute_cycle(_gm(_a(), {"g_code": "g_touch"}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
    on = compute_cycle(_gm(_a(), {"g_code": "g_touch", "modifiers": {"contact": True}}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
    assert off.slot_tmus[2] == 0 and on.slot_tmus[2] == 3


# ── P base+附加+精度 ──
def test_p_align_precision_gate(rs):
    no = compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_single", "p_addon_codes": ["a_align"]}, _a()), rs)
    yes = compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_single", "p_addon_codes": ["a_align"], "precision": True}, _a()), rs)
    assert no.slot_tmus[5] == 16 and yes.slot_tmus[5] == 24


def test_p_too_many_addons_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss", "p_addon_codes": ["a_insert", "a_snap", "a_press"]}, _a()), rs)
    assert e.value.code == "P_TOO_MANY_ADDONS"


# ── M 取 max/階梯/旋轉 ──
def test_m_ladder_boundary(rs):
    assert rs.ladder_tmu(30) == 24 and rs.ladder_tmu(30.1) == 42


def test_m_max_of_components(rs):
    r = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_li", "distance_cm": 4}, {"verb_code": "m_hand", "angle_deg": 180}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), rs)
    assert r.slot_tmus[3] == 10


def test_m_rotate(rs):
    r = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": 2}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), rs)
    assert r.slot_tmus[3] == 32


# ── X 連續/固定 ──
def test_x_continuous_and_fixed(rs):
    cont = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": 5}, {"i_code": "i_none"}, _a()), rs)
    fixed = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_scan"}, {"i_code": "i_none"}, _a()), rs)
    assert cont.slot_tmus[4] == math.ceil(5 / 0.036)
    assert fixed.slot_tmus[4] == 6


def test_x_negative_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": -1}, {"i_code": "i_none"}, _a()), rs)
    assert e.value.code == "X_NEGATIVE"


# ── 結構守門：GM↔CM 不可混用 ──
def test_slot_cross_model_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle({"seq": "GM", "slots": {0: _a(), 1: {}, 2: {"g_code": "g_grasp"}, 3: _a(), 4: {}, 5: {"m_components": []}, 6: _a()}}, rs)
    assert e.value.code == "SLOT_CROSS_MODEL"


# ── 整表 SIMO / freq ──
def test_table_simo_and_freq(rs):
    gm = _gm(_a(reach=20), {"g_code": "g_grasp"}, _a(reach=25), {"p_base_code": "p_place_none"}, _a())  # 28
    cm = _cm(_a(reach=25), {"g_code": "g_touch", "modifiers": {"contact": True}}, {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]}, {"x_code": "x_none"}, {"i_code": "i_none"}, _a())  # 29
    table = compute_table([{**gm, "frequency": 2}, {**cm, "frequency": 1, "simo_group_id": "S1"}, {**cm, "frequency": 1, "simo_group_id": "S1"}], rs)
    assert table["total_tmu"] == 85  # 56 + max(29,29)


def test_table_freq_invalid_raises(rs):
    gm = _gm(_a(reach=20), {"g_code": "g_grasp"}, _a(reach=25), {"p_base_code": "p_place_none"}, _a())
    with pytest.raises(SequenceError) as e:
        compute_table([{**gm, "frequency": 0}], rs)
    assert e.value.code == "FREQ_INVALID"
