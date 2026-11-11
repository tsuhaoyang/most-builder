"""B4（ADR-035 D10）：build_report 黃金形狀 + include_tasks 鍵序 + 既有鍵回歸。"""
from __future__ import annotations

import pathlib

import pytest

from ddm_v2.lb_projection.adapter import load_fixture
from ddm_v2.lb_projection.emit import COLUMNS
from ddm_v2.lb_projection.project import project_rows
from ddm_v2.lb_projection.report import build_report

pytestmark = pytest.mark.unit

_FX = pathlib.Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "server_node_worksheet.json"


def _report(include_tasks=False):
    rows, vocab, _ = load_fixture(_FX)
    res = project_rows(rows, vocab)
    return build_report(res, rows, include_tasks=include_tasks), rows


def test_report_golden_shape():
    rep, rows = _report()
    assert rep["tasks_out"] == 34
    assert len(rep["rows"]) == 24
    # 既有鍵（回歸 lb_export_report 形狀）
    for k in ("contract_version", "groups", "atomic_groups", "tool_episodes", "errors", "warnings"):
        assert k in rep
    assert rep["contract_version"] == "most-lb-csv-v1.1"
    # 加法鍵
    assert "rows" in rep and "hints" in rep


def test_report_general_row_flag():
    rep, _rows = _report()
    a = next(r for r in rep["rows"] if r["wi_row_id"].endswith("000000000001"))
    assert a["is_general"] is True
    assert a["general_role"] == "take_unit"


def test_report_electric_driver_row_parts_and_repeat():
    rep, _rows = _report()
    # seq9 = electric_driver, 3 列 acquire/use/release, repeat_n=8
    e = next(r for r in rep["rows"] if r["wi_row_id"].endswith("000000000009"))
    assert e["parts"] == ["acquire", "use", "release"]
    assert e["repeat_n"] == 8
    assert e["tool_id"] == "electric_driver"


def test_report_include_tasks_key_order():
    rep, _rows = _report(include_tasks=True)
    assert "tasks" in rep
    assert list(rep["tasks"][0].keys()) == list(COLUMNS)


def test_report_non_tool_row_parts_use():
    rep, _rows = _report()
    c = next(r for r in rep["rows"] if r["wi_row_id"].endswith("000000000003"))  # 非工具列
    assert c["parts"] == ["use"]
    assert c["repeat_n"] is None
