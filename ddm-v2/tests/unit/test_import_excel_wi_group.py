"""B1（ADR-035 D10）：Excel 匯入 apply_mapping 帶 wi_group 純文字；未對應→不帶。"""
from __future__ import annotations

import pytest

from ddm_v2.schemas.v2.import_excel import TARGET_FIELDS
from ddm_v2.services.v2.import_service import apply_mapping

pytestmark = pytest.mark.unit


def _payload():
    return {"sheets": [{"name": "S1", "grid": [
        ["說明", "手", "秒", "作業"],
        ["取 HDD", "R", "1.2", "裝 HDD"],
        ["鎖螺絲", "R", "2.0", "鎖螺絲"],
    ]}]}


def test_wi_group_in_target_fields():
    assert "wi_group" in TARGET_FIELDS


def test_apply_mapping_carries_wi_group():
    rows, _w = apply_mapping(_payload(), "S1", 0,
                             {"description": 0, "hand": 1, "seconds": 2, "wi_group": 3}, "sec")
    assert rows[0]["wi_group"] == "裝 HDD"
    assert rows[1]["wi_group"] == "鎖螺絲"


def test_apply_mapping_without_wi_group_absent():
    rows, _w = apply_mapping(_payload(), "S1", 0,
                             {"description": 0, "hand": 1, "seconds": 2}, "sec")
    assert "wi_group" not in rows[0]
