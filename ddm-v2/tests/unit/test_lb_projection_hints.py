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
