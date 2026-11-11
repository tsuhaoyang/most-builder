"""`rule_set_diff.diff_full` 的值差異契約（ADR-023 D7 / H-1）。

純函式、免 DB。端點層（`GET /rule-sets/{code}/diff`）與 `PUT /full` 的稽核 payload
共用這一份實作，所以三種差異（值變更／新增／刪除）在這裡先鎖死。
"""
from __future__ import annotations

import pytest

from ddm_v2.services.v2.rule_set_diff import diff_full, section_row_counts, snapshot_digest

pytestmark = pytest.mark.unit


def _full(**sections):
    base = {"code": "X", "name_zh": "X", "multiplier": 1.0}
    base.update(sections)
    return base


def _g(code: str, tmu: int) -> dict:
    return {"code": code, "label_zh": code, "base_tmu": tmu, "sort": 0, "is_active": True}


def test_identical_reports_no_difference():
    before = _full(g=[_g("g_grasp", 6)])
    d = diff_full(before, _full(g=[_g("g_grasp", 6)]))
    assert d["sections"] == {}
    assert d["summary"]["identical"] is True


def test_value_change_carries_before_and_after():
    """核心情境：analyst 把 G 動作 base_tmu 6 改成 3。"""
    d = diff_full(_full(g=[_g("g_grasp", 6)]), _full(g=[_g("g_grasp", 3)]))
    changed = d["sections"]["g"]["changed"]
    assert len(changed) == 1
    assert changed[0]["key"] == "g_grasp"
    # 只斷言「有差異」會空洞通過——必須拿得到具體的前後值。
    assert changed[0]["fields"]["base_tmu"] == {"before": 6, "after": 3}
    assert d["summary"]["changed"] == 1
    assert d["summary"]["changed_sections"] == ["g"]


def test_added_option_reported_with_its_values():
    d = diff_full(_full(g=[_g("g_grasp", 6)]), _full(g=[_g("g_grasp", 6), _g("g_new", 99)]))
    added = d["sections"]["g"]["added"]
    assert [a["key"] for a in added] == ["g_new"]
    assert added[0]["after"]["base_tmu"] == 99
    assert d["sections"]["g"]["changed"] == []


def test_removed_option_reported_with_its_values():
    d = diff_full(_full(g=[_g("g_grasp", 6), _g("g_gone", 42)]), _full(g=[_g("g_grasp", 6)]))
    removed = d["sections"]["g"]["removed"]
    assert [r["key"] for r in removed] == ["g_gone"]
    assert removed[0]["before"]["base_tmu"] == 42, "刪掉的選項的值必須留在 diff 裡"


def test_band_rows_keyed_by_position_within_group():
    """帶型無 code：身分是「組內第幾帶」，且 A 依 component、rotation 依 revolutions 分組。"""
    before = _full(
        a_bands=[{"component": "reach", "max_value": 20.0, "index": 6},
                 {"component": "twist", "max_value": 90.0, "index": 1}],
        m_rotation=[{"revolutions": 1, "max_diameter_cm": 5.0, "tmu": 6},
                    {"revolutions": 2, "max_diameter_cm": 5.0, "tmu": 10}],
    )
    after = _full(
        a_bands=[{"component": "reach", "max_value": 20.0, "index": 6},
                 {"component": "twist", "max_value": 45.0, "index": 1}],
        m_rotation=[{"revolutions": 1, "max_diameter_cm": 5.0, "tmu": 6},
                    {"revolutions": 2, "max_diameter_cm": 5.0, "tmu": 99}],
    )
    a_changed = after and diff_full(before, after)["sections"]["a_bands"]["changed"]
    assert [c["key"] for c in a_changed] == ["twist[0]"], "reach 沒動就不該出現在 diff"
    assert a_changed[0]["fields"]["max_value"] == {"before": 90.0, "after": 45.0}

    rot_changed = diff_full(before, after)["sections"]["m_rotation"]["changed"]
    assert [c["key"] for c in rot_changed] == ["rev2[0]"]
    assert rot_changed[0]["fields"]["tmu"] == {"before": 10, "after": 99}


def test_header_multiplier_change_is_reported():
    """multiplier 等比縮放該版本每一個 TMU——不能只看子表。"""
    before = _full(g=[_g("g_grasp", 6)])
    after = {**_full(g=[_g("g_grasp", 6)]), "multiplier": 1.5}
    d = diff_full(before, after)
    assert d["header"]["multiplier"] == {"before": 1.0, "after": 1.5}
    assert d["summary"]["identical"] is False


def test_row_counts_cover_all_twelve_sections():
    d = diff_full(_full(g=[_g("a", 1)]), _full(g=[]))
    assert len(d["row_counts"]) == 12
    assert d["row_counts"]["g"] == {"before": 1, "after": 0}
    assert d["row_counts"]["m_hand"] == {"before": 0, "after": 0}


def test_section_row_counts_and_digest_track_content():
    a = _full(g=[_g("g_grasp", 6)])
    b = _full(g=[_g("g_grasp", 3)])
    assert section_row_counts(a)["g"] == 1
    assert len(section_row_counts(a)) == 12
    # 列數相同、值不同 → 這正是「只存列數還原不了值」的證明；digest 至少要能分辨。
    assert section_row_counts(a) == section_row_counts(b)
    assert snapshot_digest(a) != snapshot_digest(b)
    assert snapshot_digest(a) == snapshot_digest(_full(g=[_g("g_grasp", 6)]))
