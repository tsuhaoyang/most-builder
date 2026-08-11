"""rule_plan_adapter 單元測試（L0）。"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.nlp.rule_plan_adapter import plan_from_rule_result

pytestmark = pytest.mark.unit


def test_gm_maps_to_move_place_single_action():
    result = RuleBasedParser([]).parse("將零件放到壓合治具上")
    plan, cands = plan_from_rule_result(result)
    assert len(plan.actions) == 1
    assert plan.actions[0].action_type == "move_place"
    assert plan.actions[0].action_id == "a1"
    assert len(cands) == 7


def test_cm_maps_to_controlled_move():
    result = RuleBasedParser([]).parse("並壓合機台進行壓合作業")
    plan, _ = plan_from_rule_result(result)
    assert plan.actions[0].action_type == "controlled_move"


def test_no_seq_is_composite_unknown():
    result = RuleBasedParser([]).parse("拿起零件放到位置上")
    plan, _ = plan_from_rule_result(result)
    assert plan.actions[0].action_type == "composite_unknown"
    assert "composite_unknown" in plan.unresolved


def test_synonym_candidate_source_mapped():
    parser = RuleBasedParser(
        [{"parameter": "G", "option_code": "G3", "synonym_norm": "拿取小型零件", "priority": 0}]
    )
    result = parser.parse("拿取小型零件並放置", "TEST_RS")
    _, cands = plan_from_rule_result(result)
    g = next(c for c in cands if c.field == "g2.g_code")
    assert g.chosen is not None
    assert g.chosen.option_code == "G3"
    assert g.chosen.source == "synonym_exact"


def test_compute_routing_abstain_for_composite():
    from ddm_v2.nlp.routing import compute_routing

    result = RuleBasedParser([]).parse("拿起零件放到位置上")
    plan, _ = plan_from_rule_result(result)
    status, reasons = compute_routing(plan, [], [], auto_enabled=False)
    assert status == "abstain"
    assert "composite_unknown" in reasons


def test_compute_routing_review_for_gm():
    from ddm_v2.nlp.routing import compute_routing

    result = RuleBasedParser([]).parse("將零件放到壓合治具上")
    plan, _ = plan_from_rule_result(result)
    status, reasons = compute_routing(plan, [], [], auto_enabled=False)
    assert status == "review"
    # fallback_rule_based 由 orchestrator 附加，不在 compute_routing 內
    assert "composite_unknown" not in reasons
