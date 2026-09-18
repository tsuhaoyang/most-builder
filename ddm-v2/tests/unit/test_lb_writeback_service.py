"""B4（ADR-036）：LB 回寫解析／聚合／差異純函式。用 LB 實跑 fixture ＋合成 general/simo/cross。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddm_v2.services.v2.lb_writeback_service import (
    LbWritebackContractMismatch,
    LbWritebackMalformed,
    MostRowInfo,
    RowPlacement,
    aggregate,
    diff,
    parse,
)

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "writeback_sample.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ── parse ──────────────────────────────────────────────────────────────────

def test_parse_fixture_contract_and_rows():
    p = parse(_payload())
    assert p.contract_version == "lb-most-writeback-v1"
    assert p.unattended_machine_policy == "free"
    assert p.unattended_machine_policy_source == "persisted"
    assert len(p.rows) == 34


def test_parse_contract_mismatch_raises():
    bad = {**_payload(), "contract_version": "lb-most-writeback-v2"}
    with pytest.raises(LbWritebackContractMismatch):
        parse(bad)


def test_parse_ignores_unknown_fields():
    payload = _payload()
    payload["rows"][0]["some_future_field"] = "x"
    payload["top_level_future"] = 1
    p = parse(payload)  # 加法相容：未知欄位忽略，不炸
    assert len(p.rows) == 34


def test_parse_missing_required_row_field_raises():
    # 必要欄位缺 → Fail-Fast（LbWritebackMalformed，route 映 422），不得靜默塞預設（No error bypass）
    payload = _payload()
    del payload["rows"][0]["task_id"]
    with pytest.raises(LbWritebackMalformed):
        parse(payload)


# ── aggregate ──────────────────────────────────────────────────────────────

def test_aggregate_tool_triple_same_station_one_station():
    p = parse(_payload())
    agg = aggregate(p.rows, general_ids=set())
    tri = agg["00000000-0000-4000-8000-000000000004"]  # tasks 4,5,6 都 station 0
    assert tri.task_ids == [4, 5, 6]
    assert tri.stations == {0}
    assert tri.cross_station is False


def test_aggregate_cross_station_flagged_when_nongeneral():
    rows = [
        RowPlacement("wi-x", 1, False, 0, 0, ["W-0"], None),
        RowPlacement("wi-x", 2, False, 0, 1, ["W-1"], None),  # 不同站
    ]
    agg = aggregate(rows, general_ids=set())
    assert agg["wi-x"].stations == {0, 1}
    assert agg["wi-x"].cross_station is True


def test_aggregate_general_multistation_not_flagged():
    rows = [
        RowPlacement("wi-g", 1, False, 0, 0, ["W-0"], None),
        RowPlacement("wi-g", 2, False, 0, 1, ["W-1"], None),
    ]
    # general 用 MOST 自己的判定傳入 → 多站是預期，不標 cross_station
    agg = aggregate(rows, general_ids={"wi-g"})
    assert agg["wi-g"].stations == {0, 1}
    assert agg["wi-g"].cross_station is False


def test_aggregate_units_total_and_workers_union():
    p = parse(_payload())
    agg = aggregate(p.rows, general_ids=set())
    q = agg["00000000-0000-4000-8000-000000000009"]  # units 1+8+1
    assert q.units_total == 10
    assert q.workers == {"W-2-0"}


def test_aggregate_offline_conflict():
    rows = [
        RowPlacement("wi-o", 1, True, None, None, [], None),
        RowPlacement("wi-o", 2, False, 0, 0, ["W-0"], None),
    ]
    agg = aggregate(rows, general_ids=set())
    assert agg["wi-o"].offline_conflict is True


# ── diff ───────────────────────────────────────────────────────────────────

# 黃金複本 24 列 MOST 端：seq1 是 general（take_unit），其餘非 general；本 fixture 無 SIMO 從屬列。
def _fid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def _golden_most_rows() -> list[MostRowInfo]:
    return [
        MostRowInfo(_fid(n), is_general=(n == 1), is_simo_subordinate=False, offline=(n == 2))
        for n in range(1, 25)
    ]


def test_diff_general_fixed_matched_24_missing_0_unmatched_0():
    """LB aac992f 修好 general 血緣後：general 不再 missing；matched 24／missing 0／unmatched 0（ruling a+b）。"""
    p = parse(_payload())
    general_ids = {_fid(1)}  # MOST 自己的 is_general（seq1 take_unit）
    agg = aggregate(p.rows, general_ids=general_ids)
    d = diff(_golden_most_rows(), agg)

    # (a) general 列不再是 missing
    gid = _fid(1)
    assert gid in d.matched
    assert all(m["wi_row_id"] != gid for m in d.missing)
    # (b) matched 24、missing 0、unmatched 0
    assert len(d.matched) == 24
    assert d.missing == []
    assert d.unmatched == []


def test_diff_general_multistation_not_cross_station_synthetic():
    """(ruling c) general 即使對到多站也不標 cross_station（ADR-036 D6）。
    本 fixture 的 general 是 take_unit 單站，故用合成資料補一個多站 general。"""
    rows = [
        RowPlacement("wi-gen", 100, False, 0, 0, ["W-0-0"], None),
        RowPlacement("wi-gen", 101, False, 1, 1, ["W-1-0"], None),  # 不同線/站
        RowPlacement("wi-gen", 102, False, 2, 2, ["W-2-0"], None),  # 每站一份（general 插回多站）
    ]
    agg = aggregate(rows, general_ids={"wi-gen"})
    mp = agg["wi-gen"]
    assert mp.stations == {0, 1, 2}          # 多站
    assert mp.cross_station is False         # general 多站是預期，不標異常
    # 對照：同樣多站但非 general → 標 cross_station
    agg_ng = aggregate(rows, general_ids=set())
    assert agg_ng["wi-gen"].cross_station is True


def test_diff_missing_reason_classification_synthetic():
    """missing reason 分類仍需覆蓋（general_not_written_back 為未來缺口回歸；simo_subordinate；no_result）。
    用合成 MOST 列（fixture 沒有的 wi_row_id）驗三種 reason。"""
    p = parse(_payload())
    agg = aggregate(p.rows, general_ids=set())
    most = [
        MostRowInfo(_fid(4), is_general=False, is_simo_subordinate=False, offline=False),  # matched
        MostRowInfo("wi-general-gap", is_general=True, is_simo_subordinate=False, offline=False),
        MostRowInfo("wi-simo-sub", is_general=False, is_simo_subordinate=True, offline=False),
        MostRowInfo("wi-no-result", is_general=False, is_simo_subordinate=False, offline=True),
    ]
    d = diff(most, agg)
    assert _fid(4) in d.matched
    reasons = {m["wi_row_id"]: m["reason"] for m in d.missing}
    assert reasons["wi-general-gap"] == "general_not_written_back"
    assert reasons["wi-simo-sub"] == "simo_subordinate"
    assert reasons["wi-no-result"] == "no_result"


def test_diff_offline_and_unit_mismatch():
    # MOST offline=False 但 LB 該列 offline → offline_diff；expected_n 與 units_total 不符 → unit_mismatch
    rows = [
        RowPlacement("wi-a", 1, True, None, None, [], None),                        # LB offline
        RowPlacement("wi-b", 2, False, 0, 0, ["W-0"], [{"worker": "W-0", "units": 8}]),
    ]
    agg = aggregate(rows, general_ids=set())
    most = [
        MostRowInfo("wi-a", is_general=False, is_simo_subordinate=False, offline=False),
        MostRowInfo("wi-b", is_general=False, is_simo_subordinate=False, offline=False, expected_n=12),
    ]
    d = diff(most, agg)
    assert d.offline_diffs == [{"wi_row_id": "wi-a", "most_offline": False, "lb_offline": True}]
    assert d.unit_mismatches == [{"wi_row_id": "wi-b", "expected_n": 12, "units_total": 8}]
