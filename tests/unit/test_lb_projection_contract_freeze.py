"""WP0 關卡：LB 投影 CSV 表頭凍結（Spec §6、§10）。

任何人動 `COLUMNS` 順序／名稱必先改本測試 ＝ 升 `CONTRACT_VERSION`＋同步 LB 契約
（實作書 §6 禁止事項#5）。此測試同時把 golden fixture 的表頭列鎖在 24 欄上。
"""
from __future__ import annotations

import pathlib

import pytest

from ddm_v2.lb_projection.emit import COLUMNS, CONTRACT_VERSION

pytestmark = pytest.mark.unit

# Spec §6：24 欄、順序凍結。前 21 欄＝LB TASK_CSV_COLUMN_DEFS，後 3 欄擴充。
_EXPECTED_COLUMNS = (
    "task_id",
    "action",
    "part_id",
    "group",
    "atomic_group",
    "duration",
    "predecessors",
    "station_name",
    "action_type",
    "complexity_level",
    "adjustable",
    "fixed_station",
    "offline_flag",
    "tool_id",
    "tool_action",
    "divisible",
    "p2",
    "quantity",
    "segment",
    "qty_scope",
    "duration_basis",
    "source_wi_row_id",
    "role_type",
    "general_role",
)

_REPO = pathlib.Path(__file__).resolve().parents[2]
_GOLDEN_CSV = _REPO / "docs" / "lb-integration" / "fixtures" / "server_node_tasks.expected.csv"


def test_columns_frozen_exactly() -> None:
    """COLUMNS 與凍結清單逐字、逐序相等（Spec §6）。"""
    assert COLUMNS == _EXPECTED_COLUMNS
    assert len(COLUMNS) == 24


def test_contract_version_is_v1_1() -> None:
    """Spec §0 標題宣告 most-lb-csv-v1.1（新增 general_role 第 24 欄）。"""
    assert CONTRACT_VERSION == "most-lb-csv-v1.1"


def test_golden_header_matches_columns() -> None:
    """golden fixture 第一行 ＝ ','.join(COLUMNS)（Spec §9 逐位元相等的表頭部分）。"""
    header = _GOLDEN_CSV.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(COLUMNS)
