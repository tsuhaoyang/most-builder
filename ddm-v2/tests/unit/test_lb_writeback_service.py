"""B4（ADR-036）：LB 回寫解析／聚合／差異純函式。用 LB 實跑 fixture ＋合成 general/simo/cross。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddm_v2.services.v2.lb_writeback_service import (
    UNITS_SOURCE_CYCLIC,
    UNITS_SOURCE_INFERRED,
    LbWritebackContractMismatch,
    LbWritebackMalformed,
    MostRowInfo,
    RowPlacement,
    aggregate,
    build_most_rows_from_read,
    diff,
    parse,
)

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "writeback_sample.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_vendored_fixture_is_the_pinned_lb_artifact():
    """絆線：這份 fixture 是 LB 端的產物，逐位元 vendor、**不得編輯**——但 README 的那句話原本沒有任何
    機械保證。這支測試就是保證。

    紅了代表有人動過它（re-vendor、或 end-of-file-fixer 補了換行）。**正確的反應是刻意更新這裡的常數
    與 `fixtures/README.md` 的 sha／LB commit／ortools 版本，不是重跑產生器把它弄綠**——LB 的決定性
    是經驗性的（求解從未在 time limit 前跑完，靠 incumbent 早定；`max_deterministic_time` 未接），
    換一個 ortools build 就可能得到另一組等價最優解。
    """
    import hashlib
    from collections import Counter

    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == \
        "c38b03dfb6577ed9c4177a72c5ac95a9f543ebb83dba66d691d65a97f0c0c9b3"
    rows = _payload()["rows"]
    assert len(rows) == 34
    assert len({r["source_wi_row_id"] for r in rows}) == 24
    # 件數語意的形狀（ADR-036 D6）：只有 cyclic 列是件數，setup 列是 used
    assert Counter(r.get("qty_scope") for r in rows) == Counter({None: 29, "cyclic": 3, "setup": 2})


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
    tri = agg["00000000-0000-4000-8000-000000000004"]  # tasks 4,5,6 都同一站
    assert tri.task_ids == [4, 5, 6]
    # 「同一站」才是這支測試要證的事；站號幾號是求解器這次挑的，釘它只會在 re-vendor 時 churn
    assert len(tri.stations) == 1
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
    """LB 實跑 fixture 的 seq9（electric_driver，repeat 8）：units 1/8/1，三列 setup／cyclic／setup。
    setup 列帶的是 used（經手次數）不是件數，不可加總成 10；fixture 自 LB `106bf14` 起帶 qty_scope
    → 直接取 cyclic 那列＝8（確定值，不再是推算）。"""
    p = parse(_payload())
    agg = aggregate(p.rows, general_ids=set())
    q = agg["00000000-0000-4000-8000-000000000009"]
    assert q.units_total == 8
    assert q.units_source == UNITS_SOURCE_CYCLIC
    assert len(q.workers) == 1  # 三列同一人；是誰由求解器決定，不釘
    lot = agg["00000000-0000-4000-8000-000000000007"]  # frequency 8（單列 cyclic）
    assert (lot.units_total, lot.units_source) == (8, UNITS_SOURCE_CYCLIC)
    single = agg["00000000-0000-4000-8000-000000000003"]  # Q=1 → LB 不帶 units、qty_scope 為 null
    assert (single.units_total, single.units_source) == (None, None)


def test_aggregate_units_fallback_when_fixture_has_no_qty_scope():
    """退路不能因為主路徑通了就失去覆蓋：DB 裡的舊快照沒有 qty_scope，而且會存在很久。
    拿同一份 fixture 剝掉 qty_scope（＝LB 加欄前的樣子）→ 同樣得 8，但標為推算。"""
    payload = _payload()
    for row in payload["rows"]:
        row.pop("qty_scope", None)
    agg = aggregate(parse(payload).rows, general_ids=set())
    q = agg["00000000-0000-4000-8000-000000000009"]
    assert (q.units_total, q.units_source) == (8, UNITS_SOURCE_INFERRED)  # 1/8/1 取最大值
    lot = agg["00000000-0000-4000-8000-000000000007"]
    assert (lot.units_total, lot.units_source) == (8, UNITS_SOURCE_INFERRED)


def _tool_rows(units: list[list[dict]], scopes: list[str | None]) -> list[RowPlacement]:
    return [RowPlacement("wi-t", 10 + i, False, 0, 0, sorted({u["worker"] for u in us}), us, scope)
            for i, (us, scope) in enumerate(zip(units, scopes))]


def test_aggregate_units_uses_cyclic_row_when_qty_scope_present():
    """有 qty_scope（LB 加欄後）→ 取 cyclic 那列；setup 列的 used 不算件數。"""
    rows = _tool_rows(
        [[{"worker": "W-0", "units": 1}, {"worker": "W-1", "units": 1}],
         [{"worker": "W-0", "units": 5}, {"worker": "W-1", "units": 3}],
         [{"worker": "W-0", "units": 1}, {"worker": "W-1", "units": 1}]],
        ["setup", "cyclic", "setup"],
    )
    mp = aggregate(rows)["wi-t"]
    assert (mp.units_total, mp.units_source) == (8, UNITS_SOURCE_CYCLIC)


def test_aggregate_units_inferred_max_without_qty_scope_multi_worker():
    """缺 qty_scope → 各列 Σunits 取最大值（cyclic 列 Σ=Q ≥ setup 列 Σ=經手人數）。"""
    rows = _tool_rows(
        [[{"worker": "W-0", "units": 1}, {"worker": "W-1", "units": 1}],
         [{"worker": "W-0", "units": 5}, {"worker": "W-1", "units": 3}],
         [{"worker": "W-0", "units": 1}, {"worker": "W-1", "units": 1}]],
        [None, None, None],
    )
    mp = aggregate(rows)["wi-t"]
    assert (mp.units_total, mp.units_source) == (8, UNITS_SOURCE_INFERRED)


@pytest.mark.parametrize("scopes, source", [(["cyclic"] * 3, UNITS_SOURCE_CYCLIC), ([None] * 3, UNITS_SOURCE_INFERRED)])
def test_aggregate_tool_frequency_gt1_all_cyclic_not_tripled(scopes, source):
    """持工具 frequency F=3：三列皆 cyclic、各 Σ=3。件數是 3，不是 9（舊做法全加總會誤報）。"""
    rows = _tool_rows([[{"worker": "W-0", "units": 3}]] * 3, scopes)
    mp = aggregate(rows)["wi-t"]
    assert (mp.units_total, mp.units_source) == (3, source)
    most = [MostRowInfo("wi-t", is_general=False, is_simo_subordinate=False, offline=False, expected_n=3)]
    assert diff(most, aggregate(rows)).unit_mismatches == []


def test_aggregate_qty_scope_present_but_no_cyclic_gives_no_count():
    rows = _tool_rows([[{"worker": "W-0", "units": 1}]] * 2, ["setup", "setup"])
    mp = aggregate(rows)["wi-t"]
    assert (mp.units_total, mp.units_source) == (None, None)


def test_parse_reads_optional_qty_scope():
    payload = _payload()
    payload["rows"][0]["qty_scope"] = "cyclic"
    p = parse(payload)
    assert p.rows[0].qty_scope == "cyclic"
    assert p.rows[1].qty_scope is None  # 顯式 null → None（新 fixture 每列都有 key；缺欄的路徑見下一支）


def test_parse_treats_missing_qty_scope_key_same_as_null():
    """缺欄＝None（加法相容）：LB 加欄前的舊快照沒有這個 key，必須與顯式 null 等價。"""
    payload = _payload()
    for row in payload["rows"]:
        row.pop("qty_scope", None)
    assert all(r.qty_scope is None for r in parse(payload).rows)


def test_build_most_rows_expected_n_from_projection_not_frequency():
    """比對基準是 MOST 投影出的 Q（不是 frequency）：frequency 8 但投影沒給 → 不比對；投影給多少就是多少。"""
    read = {"rows": [
        {"wi_row_id": "wi-f", "frequency": 8, "lb_tags": {}, "simo_group_id": None},
        {"wi_row_id": "wi-r", "frequency": 1, "lb_tags": {}, "simo_group_id": None},
    ]}
    by_id = {m.wi_row_id: m for m in build_most_rows_from_read(read, projected_quantity={"wi-r": 8})}
    assert by_id["wi-f"].expected_n is None
    assert by_id["wi-r"].expected_n == 8


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
    assert d.unit_mismatches == [
        {"wi_row_id": "wi-b", "expected_n": 12, "units_total": 8, "units_source": UNITS_SOURCE_INFERRED}
    ]


# ── parse 邊界：壞 payload 一律 LbWritebackMalformed（路由 422），不落到後段變 500 ─────────────

def _with_row0(**patch) -> dict:
    payload = _payload()
    payload["rows"][0].update(patch)
    return payload


@pytest.mark.parametrize("scope", ["Cyclic", "CYCLIC", " cyclic", "", "auto", 1, False, {}, ["cyclic"]])
def test_parse_rejects_qty_scope_outside_setup_cyclic(scope):
    """未知值不收：大小寫漂移或 auto 會讓件數比對靜默失效（有欄但找不到 cyclic → 不比）。"""
    with pytest.raises(LbWritebackMalformed):
        parse(_with_row0(qty_scope=scope))


@pytest.mark.parametrize("units", [
    "abc", {"worker": "W", "units": 1}, 5, [1],
    [{"worker": "W", "units": None}], [{"worker": "W", "units": "8"}], [{"worker": "W", "units": 1.5}],
    [{"worker": "W", "units": float("nan")}], [{"worker": "W", "units": -1}], [{"worker": "W", "units": True}],
    [{"units": 1}], [{"worker": "", "units": 1}],
])
def test_parse_rejects_malformed_units(units):
    with pytest.raises(LbWritebackMalformed):
        parse(_with_row0(units=units))


@pytest.mark.parametrize("sid", ["not-a-uuid", "", "00000000-0000-4000-8000-00000000000g"])
def test_parse_rejects_non_uuid_source_wi_row_id(sid):
    with pytest.raises(LbWritebackMalformed):
        parse(_with_row0(source_wi_row_id=sid))


def test_diff_lists_units_uncomparable_instead_of_skipping():
    """MOST 投影 Q>1、LB 沒給件數（非 offline）→ 明列 units_uncomparable；offline 列不列（LB 對 offline 本就不給 units）。"""
    rows = [
        RowPlacement("wi-lot", 1, False, 0, 0, ["W-0"], None),
        RowPlacement("wi-off", 2, True, None, None, [], None),
    ]
    most = [
        MostRowInfo("wi-lot", is_general=False, is_simo_subordinate=False, offline=False, expected_n=8),
        MostRowInfo("wi-off", is_general=False, is_simo_subordinate=False, offline=True, expected_n=8),
    ]
    d = diff(most, aggregate(rows))
    assert d.units_uncomparable == [{"wi_row_id": "wi-lot", "expected_n": 8, "reason": "no_units"}]
    assert d.unit_mismatches == []


@pytest.mark.parametrize("patch", [
    {"offline_flag": "false"}, {"offline_flag": 0}, {"offline_flag": None},   # "false" 會被 bool() 變 True
    {"task_id": 2.9}, {"task_id": "3"}, {"task_id": True},
    {"station_index": "x"}, {"station_index": 1.5}, {"line_index": [0]},
    {"workers": "W-0"}, {"workers": [{}]}, {"workers": [""]},
])
def test_parse_rejects_loose_field_types(patch):
    """不做 int()／bool() 轉型：否則 "false" 會變成 offline=True、2.9 被截成 2，壞值到存檔才 500。"""
    with pytest.raises(LbWritebackMalformed):
        parse(_with_row0(**patch))
