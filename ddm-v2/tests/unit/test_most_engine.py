"""MOST 引擎黃金/反例（純引擎，讀 seed rule-set，免 DB）。

主錨＝`MINIMOST_FACTORY_V2`（v3 IE 認證字典，ADR-014；fixture `rs`）；
V1 回放測試（fixture `rs_v1`）證明快照隔離：舊資料用舊規則仍得舊值。
黃金值語意（impl-02 E8）：CM 的「推 18」＝18 吋＝45cm；M 階梯門檻為 cm 正確值 2.5/10/25/45/75。
"""
from __future__ import annotations

import pytest

from ddm_v2.most_engine import SequenceError, compute_cycle, compute_table

pytestmark = pytest.mark.unit


def _a(reach=0, twist=0, foot=0):
    return {"reach_cm": reach, "twist_deg": twist, "foot_cm": foot}


def _gm(a0, g, a3, p, a6, b1=None, b4=None):
    return {"seq": "GM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: a3, 4: {"b_code": b4}, 5: p, 6: a6}}


def _cm(a0, g, m, x, i, a6, b1=None):
    return {"seq": "CM", "slots": {0: a0, 1: {"b_code": b1}, 2: g, 3: m, 4: x, 5: i, 6: a6}}


def GM_GOLD():
    return _gm(_a(reach=20), {"g_code": "g_grasp"}, _a(reach=25), {"p_base_code": "p_place_none"}, _a())


def CM_GOLD():
    return _cm(_a(reach=25), {"g_code": "g_touch"}, {"m_components": [{"verb_code": "m_push", "distance_cm": 45}]},
               {"x_code": "x_none"}, {"i_code": "i_none"}, _a())


# ── 黃金（V2）──
def test_gm_golden_28(rs):
    r = compute_cycle(GM_GOLD(), rs)
    assert r.total_tmu == 28
    assert abs(r.total_seconds - 28 * 0.036) < 1e-9


def test_cm_golden_29_push_45cm(rs):
    """CM=29：推 45cm（=18 吋檔 →16）。C1 定案後的權威輸入語意。"""
    r = compute_cycle(CM_GOLD(), rs)
    assert r.total_tmu == 29


def test_cm_push_18cm_is_10_not_16(rs):
    """單位回歸反例（C1）：推 18『cm』落 ≤25 檔 →10，不是 16。"""
    cm = _cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]},
             {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    assert compute_cycle(cm, rs).slot_tmus[3] == 10


# ── A 三分量／A3 返回（E1）──
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


def test_a_return_reach_only(rs):
    """E1：返回格僅計伸手；twist/foot 非零 → 422（零值容忍舊 payload 形狀）。"""
    ok = compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(reach=25)), rs)
    assert ok.slot_tmus[6] == 10
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(reach=25, twist=90)), rs)
    assert e.value.code == "A_RETURN_COMPONENT"


# ── B（1205 值）──
def test_b_stand_42(rs):
    r = compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_stand"), rs)
    assert r.slot_tmus[1] == 42


def test_b_unknown_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a(), b1="b_zzz"), rs)
    assert e.value.code == "B_UNKNOWN"


# ── G：V2 無 gating（選項即語意，ADR-014）──
def test_g_touch_no_gating_v2(rs):
    r = compute_cycle(_gm(_a(), {"g_code": "g_touch"}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
    assert r.slot_tmus[2] == 3


def test_g_values_v2(rs):
    assert rs.g_actions["g_grasp"].base_tmu == 6
    assert rs.g_actions["g_pick_small"].base_tmu == 16
    assert rs.g_actions["g_pick_collect"].base_tmu == 24


# ── P：base+附加（E3：互斥／無 base 顯式錯；V2 對準無精度 gating）──
def test_p_align_always_adds_v2(rs):
    """V2：a_align 選項自含精度語意（needs_precision=False）→ 直接 +8。"""
    r = compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_single", "p_addon_codes": ["a_align"]}, _a()), rs)
    assert r.slot_tmus[5] == 24


def test_p_insert_snap_conflict_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss", "p_addon_codes": ["a_insert", "a_snap"]}, _a()), rs)
    assert e.value.code == "P_ADDON_CONFLICT"


def test_p_addon_without_base_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_addon_codes": ["a_insert"]}, _a()), rs)
    assert e.value.code == "P_ADDON_NO_BASE"


def test_p_too_many_addons_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss", "p_addon_codes": ["a_insert", "a_hard", "a_press"]}, _a()), rs)
    assert e.value.code == "P_TOO_MANY_ADDONS"


# ── M：階梯（cm 正確值）／腳步獨立帶／範圍錯誤（E9）──
def test_m_ladder_v2_boundaries(rs):
    assert rs.ladder_tmu(45) == 16 and rs.ladder_tmu(45.1) == 24 and rs.ladder_tmu(75) == 24


def test_m_ladder_over_75_raises(rs):
    cm = _cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_push", "distance_cm": 76}]},
             {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    with pytest.raises(SequenceError) as e:
        compute_cycle(cm, rs)
    assert e.value.code == "M_DISTANCE_RANGE"


def test_m_foot_band_v2(rs):
    """C2 定案：M 腳步走獨立帶（30cm→16；>75→42 overflow）。"""
    assert rs.foot_tmu(30) == 16 and rs.foot_tmu(80) == 42
    cm = _cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_foot", "distance_cm": 30}]},
             {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    assert compute_cycle(cm, rs).slot_tmus[3] == 16


def test_m_hand_over_180_raises(rs):
    cm = _cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_hand", "angle_deg": 181}]},
             {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    with pytest.raises(SequenceError) as e:
        compute_cycle(cm, rs)
    assert e.value.code == "M_HAND_RANGE"


def test_m_rotate_and_range(rs):
    ok = _cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": 2}]},
             {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    assert compute_cycle(ok, rs).slot_tmus[3] == 32
    over = _cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_rotate", "diameter_cm": 60, "revolutions": 1}]},
               {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    with pytest.raises(SequenceError) as e:
        compute_cycle(over, rs)
    assert e.value.code == "M_ROTATION_RANGE"


def test_m_max_of_components(rs):
    r = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": [{"verb_code": "m_li", "distance_cm": 10}, {"verb_code": "m_hand", "angle_deg": 180}]},
                          {"x_code": "x_none"}, {"i_code": "i_none"}, _a()), rs)
    assert r.slot_tmus[3] == 10  # max(理10cm→6, 手度180→10)


# ── X：half-up（E2）＋九檔 ──
def test_x_halfup_and_fixed(rs):
    cont = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": 10}, {"i_code": "i_none"}, _a()), rs)
    fixed = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_scan_bar"}, {"i_code": "i_none"}, _a()), rs)
    screw = compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_screw_fix"}, {"i_code": "i_none"}, _a()), rs)
    assert abs(cont.slot_tmus[4] - 277.778) < 1e-9
    assert fixed.slot_tmus[4] == 6.0 and screw.slot_tmus[4] == 6.0


def test_x_negative_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, {"x_code": "x_press", "x_seconds": -1}, {"i_code": "i_none"}, _a()), rs)
    assert e.value.code == "X_NEGATIVE"


def test_x_zero_or_missing_seconds_raises(rs):
    """CL-01 §2 X（v3 認證）：動態秒數項目必須輸入正數——0/未填 → X_SECONDS_REQUIRED。"""
    for x4 in ({"x_code": "x_press", "x_seconds": 0}, {"x_code": "x_press"}):
        with pytest.raises(SequenceError) as e:
            compute_cycle(_cm(_a(), {"g_code": "g_grasp"}, {"m_components": []}, x4, {"i_code": "i_none"}, _a()), rs)
        assert e.value.code == "X_SECONDS_REQUIRED"


# ── I：八檔（含視線外）──
def test_i_outside_options_v2(rs):
    assert rs.i_index["i_confirm"] == 6 and rs.i_index["i_check_out"] == 16
    assert rs.i_index["i_align1_out"] == 24 and rs.i_index["i_align2_out"] == 32


# ── repeat（E4）──
def test_repeat_g_multiplies(rs):
    r = compute_cycle(_gm(_a(), {"g_code": "g_grasp", "repeat_count": 2}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
    assert r.slot_tmus[2] == 12


def test_repeat_m_verb_only_then_max(rs):
    """v3 認證：repeat 只乘動詞再進 max，手度分量不乘（推45×3=48 > 手度10）。"""
    cm = _cm(_a(), {"g_code": "g_grasp"},
             {"m_components": [{"verb_code": "m_push", "distance_cm": 45}, {"verb_code": "m_hand", "angle_deg": 180}], "repeat_count": 3},
             {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    assert compute_cycle(cm, rs).slot_tmus[3] == 48


def test_repeat_invalid_raises(rs):
    for bad in (0, 1.5, 100):
        with pytest.raises(SequenceError) as e:
            compute_cycle(_gm(_a(), {"g_code": "g_grasp", "repeat_count": bad}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
        assert e.value.code == "REPEAT_INVALID"


def test_repeat_on_a_b_rejected(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle(_gm({**_a(reach=10), "repeat_count": 2}, {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a()), rs)
    assert e.value.code == "REPEAT_INVALID"
    cyc = _gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_toss"}, _a())
    cyc["slots"][1] = {"b_code": "b_eye", "repeat_count": 2}
    with pytest.raises(SequenceError) as e:
        compute_cycle(cyc, rs)
    assert e.value.code == "REPEAT_INVALID"


# ── 人工覆寫（E7）──
def test_manual_override_applies_and_marks(rs):
    cyc = GM_GOLD()
    cyc["slots"][5] = {**cyc["slots"][5], "manual_override": {"tmu": 10, "reason": "現場實測", "by": "E123"}}
    r = compute_cycle(cyc, rs)
    assert r.slot_tmus[5] == 10 and r.total_tmu == 32
    assert r.overrides[0]["auto_tmu"] == 6 and "P10*" in r.tech_line


def test_manual_override_invalid_raises(rs):
    for bad in ({"tmu": -1, "reason": "x"}, {"tmu": 5, "reason": " "}, {"tmu": None, "reason": "x"}):
        cyc = GM_GOLD()
        cyc["slots"][5] = {**cyc["slots"][5], "manual_override": bad}
        with pytest.raises(SequenceError) as e:
            compute_cycle(cyc, rs)
        assert e.value.code == "OVERRIDE_INVALID"


# ── 結構守門：GM↔CM 不可混用 ──
def test_slot_cross_model_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_cycle({"seq": "GM", "slots": {0: _a(), 1: {}, 2: {"g_code": "g_grasp"}, 3: _a(), 4: {}, 5: {"m_components": []}, 6: _a()}}, rs)
    assert e.value.code == "SLOT_CROSS_MODEL"


# ── 整表 SIMO / freq（ADR-020：SIMO 標記列貢獻 0，對齊 v3 認證語義）──
def test_table_simo_and_freq(rs):
    """ADR-020：帶 simo_group_id 標記的列貢獻 0（時間由未標記主列吸收），不再群組取 max。"""
    table = compute_table([{**GM_GOLD(), "frequency": 2},
                           {**CM_GOLD(), "frequency": 1, "simo_group_id": "S1"},
                           {**CM_GOLD(), "frequency": 1, "simo_group_id": "S1"}], rs)
    assert table["total_tmu"] == 56  # 只計未標記列 28×2；S1 兩列貢獻 0
    assert [r["simo"] for r in table["rows"]] == [False, True, True]


def test_table_lone_simo_marked_row_is_zero(rs):
    """ADR-020 黃金：單獨標記列（無同組夥伴）也貢獻 0（舊群組 max 語義會全額計入）。"""
    table = compute_table([{**CM_GOLD(), "frequency": 1, "simo_group_id": "S9"}], rs)
    assert table["total_tmu"] == 0
    assert table["rows"][0]["eff_tmu"] == 29  # 列自身 eff TMU 仍照算（顯示用），只是不入總計


def test_table_main_row_unmarked_counts_full(rs):
    """ADR-020 黃金：主列未標記全額計入（freq 乘算不受 SIMO 語義影響）。"""
    table = compute_table([{**GM_GOLD(), "frequency": 3}], rs)
    assert table["total_tmu"] == 84  # 28×3


def test_table_mixed_simo_total(rs):
    """ADR-020 黃金混合案例：主列 28 ＋ 標記列 0 ＋ 一般列 29 = 57。"""
    table = compute_table([GM_GOLD(),
                           {**GM_GOLD(), "frequency": 2, "simo_group_id": "S1"},
                           CM_GOLD()], rs)
    assert table["total_tmu"] == 57
    assert table["total_seconds"] == round(57 * 0.036, 4)


def test_table_freq_invalid_raises(rs):
    with pytest.raises(SequenceError) as e:
        compute_table([{**GM_GOLD(), "frequency": 0}], rs)
    assert e.value.code == "FREQ_INVALID"


# ── V1 回放（快照隔離：舊資料＋舊規則＝舊行為）──
def test_v1_replay_goldens(rs_v1):
    assert compute_cycle(GM_GOLD(), rs_v1).total_tmu == 28
    cm_v1 = _cm(_a(reach=25), {"g_code": "g_touch", "modifiers": {"contact": True}},
                {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]},
                {"x_code": "x_none"}, {"i_code": "i_none"}, _a())
    assert compute_cycle(cm_v1, rs_v1).total_tmu == 29  # V1 語意：階梯門檻 18→16


def test_v1_replay_gating_and_precision(rs_v1):
    off = compute_cycle(_gm(_a(), {"g_code": "g_touch"}, _a(), {"p_base_code": "p_toss"}, _a()), rs_v1)
    assert off.slot_tmus[2] == 0  # V1 資料仍有 gating（requires_modifier=True）
    no_prec = compute_cycle(_gm(_a(), {"g_code": "g_grasp"}, _a(), {"p_base_code": "p_place_single", "p_addon_codes": ["a_align"]}, _a()), rs_v1)
    assert no_prec.slot_tmus[5] == 16  # V1：未勾精度不加成


def test_v1_replay_ladder_semantics(rs_v1):
    assert rs_v1.ladder_tmu(30) == 24 and rs_v1.ladder_tmu(30.1) == 42
