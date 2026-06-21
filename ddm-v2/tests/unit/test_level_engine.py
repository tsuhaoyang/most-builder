"""Level System 引擎：R1–R9 驗證 + 巢狀 + LB 輸出合約（純引擎，免 DB）。"""
from __future__ import annotations

import pytest

from ddm_v2.most_engine import level as L

pytestmark = pytest.mark.unit


def R(content, **kw):
    return L.LevelRow(content=content, **kw)


def codes(rows):
    return {i.code for i in L.validate(rows)}


# ── 合法 ──
def test_standalone_mains_valid():
    rows = [R("A", ascription="main", level="1"), R("B", ascription="main", level="2")]
    assert L.validate(rows) == []


def test_valid_sub_group():
    rows = [R("A", ascription="main", level="1"),
            R("B", ascription="main", level="2", countersignature="sub1", order=1),
            R("C", countersignature="sub1", order=2)]
    assert L.validate(rows) == []


# ── image5 三個反例 ──
def test_orphan_no_ascription_no_counter():
    rows = [R("A", ascription="main", level="1"), R("C", order=2)]
    assert "R3_ORPHAN" in codes(rows)


def test_member_redefines_main():
    rows = [R("E", ascription="main", level="4", countersignature="sub2", order=1),
            R("G", ascription="main", level="5", countersignature="sub2", order=3)]
    assert "R2_REDEFINE" in codes(rows)


def test_head_without_main():
    rows = [R("B", countersignature="sub1", order=1), R("C", countersignature="sub1", order=2)]
    assert "R1_HEAD_NO_MAIN" in codes(rows)


# ── R7 主序非遞減 ──
def test_non_decreasing_violation():
    rows = [R("A", ascription="main", level="3"), R("B", ascription="main", level="1")]
    assert "R7_NON_DECREASING" in codes(rows)


def test_variable_level_parsing_valid():
    # 1~2 範圍、1/3 列舉皆合法
    rows = [R("A", ascription="main", level="1~2"), R("B", ascription="main", level="3/5")]
    assert L.validate(rows) == []


# ── R6 nb 與 cub 矛盾 ──
def test_nb_vs_cub_conflict():
    rows = [R("H", ascription="main", level="3", countersignature="cub1", order=1, number="nb1", number_count=1),
            R("I", countersignature="cub1", order=2, number="nb1", number_count=1)]
    assert "R6_NB_VS_CUB" in codes(rows)


# ── R9 巢狀 sub⊃cub ──
def _nest_legal():
    return [R("A", ascription="main", level="1"),
            R("E", ascription="main", level="2", countersignature="sub2", order=1),
            R("F", ascription="main", level="2", countersignature="cub1", parent_countersignature="sub2", order=1),
            R("G", countersignature="cub1", parent_countersignature="sub2", order=2)]


def test_nesting_legal():
    assert L.validate(_nest_legal()) == []


def test_nesting_parent_missing():
    rows = [R("A", ascription="main", level="1"),
            R("F", ascription="main", level="2", countersignature="cub1", parent_countersignature="sub9", order=1),
            R("G", countersignature="cub1", parent_countersignature="sub9", order=2)]
    assert "R9_PARENT_MISSING" in codes(rows)


def test_nesting_sub_cannot_be_nested():
    rows = [R("X", ascription="main", level="1", countersignature="sub1", order=1),
            R("Y", countersignature="sub1", order=2),
            R("B", ascription="main", level="2", countersignature="sub2", parent_countersignature="sub1", order=1),
            R("C", countersignature="sub2", parent_countersignature="sub1", order=2)]
    assert "R9_SUB_NESTED" in codes(rows)


def test_nesting_cub_in_cub_illegal():
    rows = [R("H", ascription="main", level="1", countersignature="cub1", order=1),
            R("I", countersignature="cub1", order=2),
            R("F", ascription="main", level="2", countersignature="cub2", parent_countersignature="cub1", order=1),
            R("G", countersignature="cub2", parent_countersignature="cub1", order=2)]
    assert "R9_NEST_ILLEGAL" in codes(rows)


# ── LB 輸出合約：自由度 + 群組語意 ──
def test_build_output_preserves_freedom():
    out = L.build_output([R("A", ascription="main", level="1~2"), R("B", ascription="main", level="3/5")])
    by = {n["content"]: n for n in out["nodes"]}
    assert by["A"]["levels"] == [1, 2] and by["A"]["variable"] is True
    assert by["B"]["levels"] == [3, 5]


def test_build_output_groups_and_nesting():
    out = L.build_output(_nest_legal())
    groups = {g["label"]: g for g in out["groups"]}
    assert groups["sub2"]["movable"] is True and groups["sub2"]["same_station"] is False
    assert groups["cub1"]["same_station"] is True and groups["cub1"]["parent"] == "sub2"
    assert out["group_parents"] == {"cub1": "sub2"}


def test_build_output_number_constraints():
    out = L.build_output([R("A", ascription="main", level="1", number="nb1", number_count=1),
                          R("B", ascription="main", level="2", number="nb1", number_count=1)])
    nc = out["number_constraints"]["nb1"]
    assert nc["kind"] == "max_per_station" and nc["limit"] == 1 and len(nc["members"]) == 2
