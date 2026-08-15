"""Unit tests for import_service pure functions (no DB required).

Tests cover suggest_header_row and apply_mapping — both are sync pure functions.
submit_to_worksheet requires a live DB session and is covered by integration tests.
"""
from __future__ import annotations

import pytest

from ddm_v2.services.v2.import_service import apply_mapping, suggest_header_row

# ── suggest_header_row ────────────────────────────────────────────────────────

class TestSuggestHeaderRow:
    def test_picks_row_with_most_string_cells(self) -> None:
        grid = [
            [1, 2, 3],                          # row 0: all numeric
            ["作業描述", "工時(秒)", "手別"],     # row 1: 3 strings → winner
            ["裝螺絲", 5.2, "RH"],              # row 2: 1 string
        ]
        assert suggest_header_row(grid) == 1

    def test_empty_grid_returns_zero(self) -> None:
        assert suggest_header_row([]) == 0

    def test_single_row(self) -> None:
        assert suggest_header_row([["col_a", "col_b"]]) == 0

    def test_ignores_rows_beyond_15(self) -> None:
        # Build 20-row grid: rows 0-14 empty, row 16 has strings (beyond limit)
        grid: list[list] = [[]] * 16 + [["a", "b", "c", "d"]]
        # Should not pick row 16; best within first 15 is row 0 (score 0 but still wins)
        result = suggest_header_row(grid)
        assert result < 15

    def test_tie_picks_first(self) -> None:
        # Two rows with equal string count → first one wins
        grid = [
            ["col_a", "col_b"],
            ["col_c", "col_d"],
        ]
        assert suggest_header_row(grid) == 0


# ── apply_mapping ─────────────────────────────────────────────────────────────

def _make_payload(grid: list[list]) -> dict:
    return {"sheets": [{"name": "Sheet1", "grid": grid, "n_rows": len(grid), "n_cols": 3}]}


class TestApplyMapping:
    def test_basic_mapping_seconds(self) -> None:
        grid = [
            ["作業描述", "工時(秒)", "手別"],   # header row 0
            ["裝螺絲", 10.5, "RH"],             # data row
        ]
        payload = _make_payload(grid)
        rows, warnings = apply_mapping(
            payload, "Sheet1", 0,
            {"description": 0, "seconds": 1, "hand": 2},
            "sec",
        )
        assert len(rows) == 1
        assert rows[0]["description"] == "裝螺絲"
        assert rows[0]["seconds"] == pytest.approx(10.5)
        assert rows[0]["hand"] == "RH"
        assert warnings == []

    def test_minutes_converted_to_seconds(self) -> None:
        grid = [
            ["作業", "工時(分)"],
            ["鎖螺絲", 0.5],
        ]
        payload = _make_payload(grid)
        rows, _ = apply_mapping(payload, "Sheet1", 0, {"description": 0, "seconds": 1}, "min")
        assert rows[0]["seconds"] == pytest.approx(30.0)

    def test_hand_normalisation(self) -> None:
        grid = [
            ["description", "hand"],
            ["task", "left"],
            ["task2", "右手"],
            ["task3", "both"],
            ["task4", "UNKNOWN"],
        ]
        payload = _make_payload(grid)
        rows, _ = apply_mapping(payload, "Sheet1", 0, {"description": 0, "hand": 1}, "sec")
        assert rows[0]["hand"] == "LH"
        assert rows[1]["hand"] == "RH"
        assert rows[2]["hand"] == "BH"
        assert rows[3]["hand"] is None

    def test_missing_sheet_returns_warning(self) -> None:
        payload = _make_payload([["a", "b"]])
        rows, warnings = apply_mapping(payload, "NoSuchSheet", 0, {"description": 0}, "sec")
        assert rows == []
        assert any("找不到分頁" in w for w in warnings)

    def test_all_empty_rows_skipped(self) -> None:
        grid = [
            ["描述", "工時"],
            [None, None],
            ["", ""],
        ]
        payload = _make_payload(grid)
        rows, _ = apply_mapping(payload, "Sheet1", 0, {"description": 0, "seconds": 1}, "sec")
        assert rows == []

    def test_bad_seconds_value_produces_warning(self) -> None:
        grid = [
            ["描述", "工時"],
            ["拿零件", "N/A"],
        ]
        payload = _make_payload(grid)
        rows, warnings = apply_mapping(payload, "Sheet1", 0, {"description": 0, "seconds": 1}, "sec")
        assert len(rows) == 1
        assert rows[0]["seconds"] is None
        assert any("工時無法解析" in w for w in warnings)

    def test_quantity_parsed_as_float(self) -> None:
        grid = [
            ["描述", "數量"],
            ["鎖螺絲", "3"],
        ]
        payload = _make_payload(grid)
        rows, _ = apply_mapping(payload, "Sheet1", 0, {"description": 0, "quantity": 1}, "sec")
        assert rows[0]["quantity"] == pytest.approx(3.0)

    def test_row_number_tag_present(self) -> None:
        grid = [
            ["描述"],
            ["作業A"],
        ]
        payload = _make_payload(grid)
        rows, _ = apply_mapping(payload, "Sheet1", 0, {"description": 0}, "sec")
        # _row 應是 Excel 列號（header=row 0 → data starts at row 1 → _row=2）
        assert rows[0]["_row"] == 2
