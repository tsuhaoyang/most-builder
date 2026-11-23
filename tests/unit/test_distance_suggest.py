"""距離建議的純計算（ADR-038 D5.6 修訂，W7b）。"""
from __future__ import annotations

import uuid

import pytest

from ddm_v2.services.v2.distance_service import Endpoint, apply_to_cycle, suggest_row, suggest_slot

pytestmark = pytest.mark.unit

PERSON = Endpoint("person", point=(0.0, 0.0, 140.0), source="person_offset")


def _at(role: str, x: float, y: float, z: float) -> Endpoint:
    return Endpoint(role, uuid.uuid4(), uuid.uuid4(), (x, y, z), "zone_center", "anchor")


def test_reach_at_or_below_threshold_foot_above():
    near = _at("from", 0, 70, 140)  # 剛好 70
    far = _at("from", 0, 70.1, 140)
    assert suggest_slot("a0", PERSON, near, threshold_cm=70).field == "reach_cm"
    s = suggest_slot("a0", PERSON, far, threshold_cm=70)
    assert (s.status, s.field, s.distance_cm) == ("suggested", "foot_cm", 70.1)


def test_threshold_compares_unrounded_distance():
    s = suggest_slot("a0", PERSON, _at("from", 0, 70.04, 140), threshold_cm=70)
    assert (s.field, s.distance_cm) == ("foot_cm", 70.0), "70.04 > 70：取整只影響記錄的值，不影響判斷"
    m = suggest_slot("m3", _at("from", 0, 0, 0), _at("to", 75.04, 0, 0), threshold_cm=70, ladder_components=1)
    assert m.status == "needs_ie"


def test_straight_line_3d_rounded():
    s = suggest_slot("a3", _at("from", 0, 0, 0), _at("to", 3, 4, 12), threshold_cm=70)
    assert s.distance_cm == 13.0


def test_a6_over_threshold_needs_ie_not_foot():
    s = suggest_slot("a6", _at("to", 0, 100, 140), PERSON, threshold_cm=70)
    assert (s.status, s.field, s.reason) == ("needs_ie", None, "a6_over_threshold")
    assert s.distance_cm == 100.0, "距離仍給出供 IE 參考"


@pytest.mark.parametrize(("n", "d", "status", "reason"), [
    (1, 75.0, "suggested", None),
    (1, 75.1, "needs_ie", "m_over_75"),
    (0, 10.0, "needs_ie", "m_component_missing"),
    (2, 10.0, "needs_ie", "m_components_multiple"),
])
def test_m3_rules(n, d, status, reason):
    s = suggest_slot("m3", _at("from", 0, 0, 0), _at("to", d, 0, 0), threshold_cm=70, ladder_components=n)
    assert (s.status, s.reason) == (status, reason)
    assert s.field == ("distance_cm" if status == "suggested" else None)


def test_missing_endpoint_is_unavailable_with_reason():
    s = suggest_slot("a3", _at("from", 0, 0, 0), Endpoint("to", uuid.uuid4(), reason="not_assigned"), threshold_cm=70)
    assert (s.status, s.reason, s.distance_cm) == ("unavailable", "not_assigned", None)


def test_row_slots_by_sequence():
    o, d = _at("from", 0, 30, 100), _at("to", 0, 50, 100)
    assert [s.slot for s in suggest_row("GM", person=PERSON, origin=o, destination=d, threshold_cm=70,
                                        ladder_components=0)] == ["a0", "a3", "a6"]
    assert [s.slot for s in suggest_row("CM", person=PERSON, origin=o, destination=d, threshold_cm=70,
                                        ladder_components=1)] == ["a0", "m3", "a6"]


def test_apply_to_cycle_sets_field_and_clears_the_other():
    cycle = {"seq": "GM", "a0": {"reach_cm": 5, "foot_cm": 9, "twist_deg": 30}, "a3": {"reach_cm": 1}}
    o, d = _at("from", 0, 80, 140), _at("to", 0, 90, 140)
    s = suggest_row("GM", person=PERSON, origin=o, destination=d, threshold_cm=70, ladder_components=0)
    out = apply_to_cycle(cycle, s, set())
    assert out["a0"] == {"reach_cm": 0, "foot_cm": 80.0, "twist_deg": 30}
    assert out["a3"] == {"reach_cm": 10.0, "foot_cm": 0}
    assert "a6" not in out, "需 IE 裁決的格位不動"
    assert cycle["a0"]["foot_cm"] == 9, "不改原物件"


def test_apply_to_cycle_m3_only_ladder_component():
    cycle = {"seq": "CM", "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 1},
                                                  {"verb_code": "m_rotate", "revolutions": 2}]}}
    s = [suggest_slot("m3", _at("from", 0, 0, 0), _at("to", 30, 0, 0), threshold_cm=70, ladder_components=1)]
    out = apply_to_cycle(cycle, s, {"m_push"})
    assert out["m3"]["m_components"] == [{"verb_code": "m_push", "distance_cm": 30.0},
                                         {"verb_code": "m_rotate", "revolutions": 2}]
