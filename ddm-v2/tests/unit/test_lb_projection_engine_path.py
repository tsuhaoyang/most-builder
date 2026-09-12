"""WP3 關卡：引擎路徑 vs 靜態路徑相等（Spec §3.3）。

fixture（`server_node_worksheet.json`）只提供**靜態** slot_tmus，無 slot_inputs（fixtures/README），
故引擎路徑無法直接對 fixture 24 motion 逐一重跑。本測試以**構造的合法 slot_inputs**（含 repeat）
證明：`decompose_engine(slot_inputs)` 與 `decompose_static(compute_cycle(slot_inputs).slot_tmus)`
對同一 motion **相等**——即投影層兩條路徑一致（實作書 WP3 關卡）。

WI-I（190=22+8×19+16）的守恆斷言在 `test_lb_projection_tmu.py` 以靜態路徑鎖定；此處補「引擎重算＝
靜態」的一致性，特別覆蓋帶 repeat 的持工具 CM（M fixed verb ×N 線性可拆）。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.tmu import decompose_engine, decompose_static
from ddm_v2.most_engine.calculate import compute_cycle
from ddm_v2.most_engine.providers import build_from_seed_v2

pytestmark = pytest.mark.unit


def _rs():
    return build_from_seed_v2()


def _assert_two_paths_equal(cyc: dict, repeat_counts: dict) -> None:
    rs = _rs()
    full = compute_cycle(cyc, rs)
    de = decompose_engine(cyc, full.total_tmu, rs, "t")
    ds = decompose_static(list(full.slot_tmus), repeat_counts, full.total_tmu, "t")
    assert de == ds, f"engine {de} != static {ds}"
    # 守恆（Spec §3.3）
    assert de.acquire_tmu + de.n * de.use_once_tmu + de.release_tmu == pytest.approx(full.total_tmu, abs=1e-6)


def test_engine_equals_static_tool_cm_with_repeat() -> None:
    """持工具 CM，use 段（M/X/I）repeat ×8：M fixed verb ×8 線性可拆 → 兩路徑相等。"""
    cyc = {
        "seq": "CM",
        "slots": {
            0: {"reach_cm": 20},
            1: {},
            2: {"g_code": "g_tap"},
            3: {"m_components": [{"verb_code": "m_screw"}], "repeat_count": 8},
            4: {"x_code": "x_press", "x_seconds": 2.0, "repeat_count": 8},
            5: {"i_code": "i_check", "repeat_count": 8},
            6: {"reach_cm": 20},
        },
    }
    _assert_two_paths_equal(cyc, {"3": 8, "4": 8, "5": 8})


def test_engine_equals_static_no_repeat_gm() -> None:
    """一般 GM（無 repeat）：兩路徑相等，n=1。"""
    cyc = {
        "seq": "GM",
        "slots": {
            0: {"reach_cm": 35},
            1: {},
            2: {"g_code": "g_tap"},
            3: {"reach_cm": 20},
            4: {},
            5: {"p_base_code": "p_place_none"},
            6: {"reach_cm": 10},
        },
    }
    _assert_two_paths_equal(cyc, {})


def test_engine_equals_static_all_use_slots_repeat() -> None:
    """use 段（M/X/I）全格同步 repeat ×12（如 WI-I 形狀：Σslot[3..5]/N 靜態公式成立）。

    註（❓見 WP3 回報）：Spec §3.3 靜態公式 `use_once = Σslot[3..5] / N` 只在 use 段**所有非零格
    同步 repeat** 時與引擎路徑相等；「只有部分 use 格 repeat」（如 M 不 repeat、I repeat）
    靜態除法會錯而引擎對——該情況的合法性待 User 裁決，本測試只覆蓋 Spec 明確支援的全格同步案例。
    """
    cyc = {
        "seq": "CM",
        "slots": {
            0: {"reach_cm": 10},
            1: {},
            2: {"g_code": "g_tap"},
            3: {"m_components": [{"verb_code": "m_screw"}], "repeat_count": 12},
            4: {"x_code": "x_press", "x_seconds": 1.0, "repeat_count": 12},
            5: {"i_code": "i_check", "repeat_count": 12},
            6: {"reach_cm": 10},
        },
    }
    _assert_two_paths_equal(cyc, {"3": 12, "4": 12, "5": 12})
