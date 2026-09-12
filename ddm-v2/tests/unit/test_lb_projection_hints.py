"""B4（ADR-035 D10）：hints.py 每規則正／反例（合成 fixture）。純函式、只看結構。

黃金 hints 快照（server_node_hints.expected.json）首次由 agent 產出、經 User 過目後才鎖 assert；
本檔只鎖規則行為（正例出、反例不出）。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.hints import hints
from ddm_v2.lb_projection.models import ProjectionRow, ProjectionVocab
from ddm_v2.lb_projection.project import project_rows

pytestmark = pytest.mark.unit

_VOCAB = {"scanner": ProjectionVocab(kind="tool", name_en="scanner")}


def _cm(seq, *, freq=1, x_seconds=0.0, segment=None, cs="", tool=None, obj=None, x_code=None, head=True):
    slots = {"4": {"x_seconds": x_seconds}} if x_seconds else {}
    if x_code:
        slots.setdefault("4", {})["x_code"] = x_code
    # 群組列：head 帶 ascription=main+level，其餘 None（對齊 derive/hydrate）
    lvl = {"countersignature": cs, "order": seq}
    if head:
        lvl["ascription"] = "main"
        lvl["level"] = "1"
    else:
        lvl["ascription"] = None
        lvl["level"] = None
    return ProjectionRow.model_validate({
        "wi_row_id": f"00000000-0000-4000-8000-{seq:012d}", "seq_no": seq,
        "object_vocab": obj, "tool_vocab": tool, "frequency": freq,
        "cycle": {"seq_kind": "CM", "slot_tmus": [0, 0, 0, 24, 6, 0, 0], "repeat_counts": {},
                  "x_seconds": x_seconds, "total_tmu": 30,
                  "narrative_en": f"row {seq}", "slot_inputs": {"seq": "CM", "slots": slots}},
        "level": lvl,
        "lb_tags": {"segment": segment},
    })


def _hints_of(rows):
    res = project_rows(rows, _VOCAB)
    return {h.kind for h in hints(res, rows)}, hints(res, rows)


def test_machine_time_positive_and_negative():
    kinds, _ = _hints_of([_cm(1, x_seconds=3.0), _cm(2, x_seconds=0.0)])
    assert "H_MACHINE_TIME" in kinds  # x_seconds>=1
    # 反例：x_seconds<1 不出
    kinds2, hs = _hints_of([_cm(1, x_seconds=0.2)])
    assert "H_MACHINE_TIME" not in kinds2


def test_lot_run_segment_positive_and_negative():
    # 正例：同 chain(sub7) 連續兩列 freq=8、無 segment
    rows = [_cm(1, freq=8, cs="sub7", head=True), _cm(2, freq=8, cs="sub7", head=False)]
    kinds, hs = _hints_of(rows)
    assert "H_LOT_RUN_SEGMENT" in kinds
    h = next(h for h in hs if h.kind == "H_LOT_RUN_SEGMENT")
    assert h.params == {"frequency": 8}
    # 反例：已帶 segment → 不出
    rows2 = [_cm(1, freq=8, cs="sub7", segment="batch1", head=True), _cm(2, freq=8, cs="sub7", segment="batch1", head=False)]
    kinds2, _ = _hints_of(rows2)
    assert "H_LOT_RUN_SEGMENT" not in kinds2
    # 反例：freq=1 → 不出
    kinds3, _ = _hints_of([_cm(1, freq=1, cs="sub7", head=True), _cm(2, freq=1, cs="sub7", head=False)])
    assert "H_LOT_RUN_SEGMENT" not in kinds3


def test_hints_pure_and_deterministic():
    rows = [_cm(1, x_seconds=3.0), _cm(2, freq=8, cs="sub7", head=True), _cm(3, freq=8, cs="sub7", head=False)]
    res = project_rows(rows, _VOCAB)
    a = [h.as_dict() for h in hints(res, rows)]
    b = [h.as_dict() for h in hints(res, rows)]
    assert a == b  # 相同輸入相同輸出


# ── 黃金快照鎖定（B4b；架構師核准 6 條）──
import json as _json  # noqa: E402
import pathlib as _pathlib  # noqa: E402

_SNAP = _pathlib.Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "server_node_hints.expected.json"
_FX = _pathlib.Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "server_node_worksheet.json"


def test_golden_hints_snapshot():
    from ddm_v2.lb_projection.adapter import load_fixture

    rows, vocab, _ = load_fixture(_FX)
    res = project_rows(rows, vocab)
    got = [h.to_dict() for h in hints(res, rows)]
    expected = _json.loads(_SNAP.read_text())
    assert got == expected  # list of dict，含順序，逐項相等


# ── B4b：Pattern A episode 狀態機（合成，走 project_rows 取真實 plans/chains）──

def _pa(seq, part, *, cs="sub9", head=False, tool="scanner"):
    """Pattern A 列：part∈{acquire(GM,object=tool),use(CM,object=tool held),release(GM,object=tool)}。"""
    is_gm = part in ("acquire", "release")
    lvl = {"countersignature": cs, "order": seq}
    if head:
        lvl["ascription"] = "main"; lvl["level"] = "1"
    else:
        lvl["ascription"] = None; lvl["level"] = None
    return ProjectionRow.model_validate({
        "wi_row_id": f"00000000-0000-4000-8000-{seq:012d}", "seq_no": seq,
        "object_vocab": tool, "tool_vocab": None, "frequency": 1,
        "cycle": {"seq_kind": "GM" if is_gm else "CM",
                  "slot_tmus": [16, 0, 6, 0, 0, 6, 0] if is_gm else [0, 0, 0, 0, 22, 0, 0],
                  "repeat_counts": {}, "x_seconds": 0,
                  "total_tmu": 28 if is_gm else 22, "narrative_en": f"r{seq}", "slot_inputs": {}},
        "level": lvl, "lb_tags": {}})


def test_episode_pattern_a_three_rows_one_hint():
    # GM 拿起 → CM 使用 → GM 放回，同 sub、無 cub → 恰 1 條
    rows = [_pa(1, "acquire", head=True), _pa(2, "use"), _pa(3, "release")]
    _kinds, hs = _hints_of(rows)
    eps = [h for h in hs if h.kind == "H_TOOL_EPISODE_SAME_STATION"]
    assert len(eps) == 1
    assert eps[0].wi_row_ids == [r.wi_row_id for r in rows]
    assert eps[0].params == {"tool_id": "scanner"}


def test_two_pattern_b_same_tool_no_episode_hint():
    # 兩個獨立 Pattern B 列（tool_vocab=scanner，各自拆三列），同 sub、同 tool → episode 0 條
    def _pb(seq, head):
        lvl = {"countersignature": "sub9", "order": seq}
        if head: lvl["ascription"] = "main"; lvl["level"] = "1"
        else: lvl["ascription"] = None; lvl["level"] = None
        return ProjectionRow.model_validate({
            "wi_row_id": f"00000000-0000-4000-8000-{seq:012d}", "seq_no": seq,
            "tool_vocab": "scanner", "object_vocab": None, "frequency": 1,
            "cycle": {"seq_kind": "CM", "slot_tmus": [16, 0, 0, 22, 0, 0, 10], "repeat_counts": {},
                      "x_seconds": 0, "total_tmu": 48, "narrative_en": f"scan{seq}", "slot_inputs": {}},
            "level": lvl, "lb_tags": {}})
    rows = [_pb(1, True), _pb(2, False)]
    _kinds, hs = _hints_of(rows)
    assert not [h for h in hs if h.kind == "H_TOOL_EPISODE_SAME_STATION"]
    dec = [h for h in hs if h.kind == "H_TOOL_DECOMPOSED"]
    assert len(dec) == 1 and len(dec[0].wi_row_ids) == 2  # 兩列同 tool 一條 decomposed


def test_episode_all_same_cub_no_hint():
    # 三列 Pattern A 全在同一巢狀 cub（parent sub）→ 0 條
    def _pa_cub(seq, part, head=False):
        r = _pa(seq, part, cs="cub30", head=head)
        # cub30 的 parent sub9（讓它成為 sub9 chain 的巢狀 cub）
        return r.model_copy(update={"level": r.level.model_copy(update={"parent_countersignature": "sub9"})})
    # sub9 head + 巢狀 cub30 的三列
    head = _pa(1, "acquire", cs="sub9", head=True)
    rows = [head, _pa_cub(2, "acquire"), _pa_cub(3, "use"), _pa_cub(4, "release")]
    # 為讓 cub30 是純三列 episode，把 head 也放進 cub 讓段全在 cub30：改用純 cub30 三列 + sub9 head 空殼
    rows = [
        _pa(1, "use", cs="sub9", head=True),  # sub9 head（非工具佔位，用 use 但 object=scanner 未 held → 視為孤兒；改為非工具）
    ]
    rows[0] = ProjectionRow.model_validate({
        "wi_row_id": "00000000-0000-4000-8000-000000000001", "seq_no": 1,
        "object_vocab": None, "tool_vocab": None, "frequency": 1,
        "cycle": {"seq_kind": "CM", "slot_tmus": [0, 0, 0, 22, 0, 0, 0], "repeat_counts": {}, "x_seconds": 0,
                  "total_tmu": 22, "narrative_en": "head", "slot_inputs": {}},
        "level": {"countersignature": "sub9", "order": 1, "ascription": "main", "level": "1"}, "lb_tags": {}})
    rows += [_pa_cub(2, "acquire"), _pa_cub(3, "use"), _pa_cub(4, "release")]
    _kinds, hs = _hints_of(rows)
    assert not [h for h in hs if h.kind == "H_TOOL_EPISODE_SAME_STATION"]


def test_episode_two_row_pattern_b_via_release():
    # 2 列 Pattern B（CM tool_vocab=scanner ['acquire','use'] + 後面 GM object=scanner ['release']）→ 1 條、2 id
    head = ProjectionRow.model_validate({
        "wi_row_id": "00000000-0000-4000-8000-000000000001", "seq_no": 1,
        "tool_vocab": "scanner", "object_vocab": None, "frequency": 1,
        "cycle": {"seq_kind": "CM", "slot_tmus": [16, 0, 0, 22, 0, 0, 10], "repeat_counts": {}, "x_seconds": 0,
                  "total_tmu": 48, "narrative_en": "scan", "slot_inputs": {}},
        "level": {"countersignature": "sub9", "order": 1, "ascription": "main", "level": "1"}, "lb_tags": {}})
    rel = _pa(2, "release", cs="sub9")
    rows = [head, rel]
    _kinds, hs = _hints_of(rows)
    eps = [h for h in hs if h.kind == "H_TOOL_EPISODE_SAME_STATION"]
    assert len(eps) == 1 and len(eps[0].wi_row_ids) == 2


def test_two_pattern_a_episodes_same_tool_two_hints():
    # 同 chain 前後兩段 Pattern A（同 tool）→ 2 條、key 不同
    rows = [
        _pa(1, "acquire", head=True), _pa(2, "use"), _pa(3, "release"),
        _pa(4, "acquire"), _pa(5, "use"), _pa(6, "release"),
    ]
    _kinds, hs = _hints_of(rows)
    eps = [h for h in hs if h.kind == "H_TOOL_EPISODE_SAME_STATION"]
    assert len(eps) == 2
    assert eps[0].key != eps[1].key
