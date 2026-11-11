"""WP6 關卡：golden 逐位元。project_rows(fixture) 的 csv_text == expected CSV（bit-exact）。"""
from __future__ import annotations

import pathlib

import pytest

from ddm_v2.lb_projection.adapter import load_fixture
from ddm_v2.lb_projection.project import project_rows

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[2]
_FX = _REPO / "docs" / "lb-integration" / "fixtures" / "server_node_worksheet.json"
_EXPECTED = _REPO / "docs" / "lb-integration" / "fixtures" / "server_node_tasks.expected.csv"


def test_golden_bit_exact() -> None:
    rows, vocab, _meta = load_fixture(_FX)
    result = project_rows(rows, vocab)
    expected = _EXPECTED.read_text()
    assert result.errors == [], f"unexpected errors: {result.errors}"
    # 逐列比對定位第一處差異
    got_lines = result.csv_text.splitlines()
    exp_lines = expected.splitlines()
    assert len(got_lines) == len(exp_lines), f"line count {len(got_lines)} != {len(exp_lines)}"
    for i, (g, e) in enumerate(zip(got_lines, exp_lines)):
        assert g == e, f"line {i} differs:\n  got={g}\n  exp={e}"
    assert result.csv_text == expected
