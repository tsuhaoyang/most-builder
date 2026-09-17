"""B4（ADR-036）：LB 回寫解析／聚合／差異純函式。用 LB 實跑 fixture ＋合成 general/simo/cross。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddm_v2.services.v2.lb_writeback_service import (
    LbWritebackContractMismatch,
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
    assert len(p.rows) == 33


def test_parse_contract_mismatch_raises():
    bad = {**_payload(), "contract_version": "lb-most-writeback-v2"}
    with pytest.raises(LbWritebackContractMismatch):
        parse(bad)


def test_parse_ignores_unknown_fields():
    payload = _payload()
    payload["rows"][0]["some_future_field"] = "x"
    payload["top_level_future"] = 1
    p = parse(payload)  # 加法相容：未知欄位忽略，不炸
    assert len(p.rows) == 33


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

def test_diff_matched_unmatched_missing_with_reasons():
    p = parse(_payload())
    agg = aggregate(p.rows, general_ids=set())
    # MOST 端：兩個 fixture 有的（matched）＋一個 general（missing→general_not_written_back）
    # ＋一個 SIMO 從屬列（missing→simo_subordinate）＋一個 offline-only（missing→no_result）
    most = [
        MostRowInfo("00000000-0000-4000-8000-000000000004", is_general=False, is_simo_subordinate=False, offline=False),
        MostRowInfo("00000000-0000-4000-8000-000000000006", is_general=False, is_simo_subordinate=False, offline=False),
        MostRowInfo("wi-general-A", is_general=True, is_simo_subordinate=False, offline=False),
        MostRowInfo("wi-simo-sub", is_general=False, is_simo_subordinate=True, offline=False),
        MostRowInfo("wi-offline-only", is_general=False, is_simo_subordinate=False, offline=True),
    ]
    d = diff(most, agg)
    assert "00000000-0000-4000-8000-000000000004" in d.matched
    # unmatched：fixture 有但 most 清單沒有的（其餘 21 個 wi）
    assert len(d.unmatched) == 23 - 2
    reasons = {m["wi_row_id"]: m["reason"] for m in d.missing}
    assert reasons["wi-general-A"] == "general_not_written_back"
    assert reasons["wi-simo-sub"] == "simo_subordinate"
    assert reasons["wi-offline-only"] == "no_result"


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
