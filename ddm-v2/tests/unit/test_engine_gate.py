"""engine_gate：partial 跳過引擎；SequenceError → engine_reject_*。"""
from __future__ import annotations

from ddm_v2.most_compiler.engine_gate import apply_engine_gate
from ddm_v2.most_engine.providers import build_from_seed_v2
from ddm_v2.nlp.contracts import CycleDraft


def test_partial_draft_skips_engine():
    draft = CycleDraft(
        action_id="a1",
        cycle={
            "seq": "CM",
            "rule_set_code": "MINIMOST_FACTORY_V2",
            "x4": {"x_code": None},
        },
        complete=False,
        issues=["missing_core_x"],
    )
    out = apply_engine_gate([draft], build_from_seed_v2())
    assert out[0].engine_result is None
    assert out[0].complete is False


def test_engine_reject_x_seconds_required():
    draft = CycleDraft(
        action_id="a1",
        cycle={
            "seq": "CM",
            "rule_set_code": "MINIMOST_FACTORY_V2",
            "x4": {"x_code": "x_heat", "x_seconds": 0},
        },
        complete=True,
    )
    out = apply_engine_gate([draft], build_from_seed_v2())
    assert out[0].engine_result is None
    assert "engine_reject_X_SECONDS_REQUIRED" in out[0].issues


def test_engine_reject_m_distance_range():
    draft = CycleDraft(
        action_id="a1",
        cycle={
            "seq": "CM",
            "rule_set_code": "MINIMOST_FACTORY_V2",
            "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 9999}]},
        },
        complete=True,
    )
    out = apply_engine_gate([draft], build_from_seed_v2())
    assert out[0].engine_result is None
    assert "engine_reject_M_DISTANCE_RANGE" in out[0].issues


def test_engine_reject_does_not_block_sibling():
    rs = build_from_seed_v2()
    bad = CycleDraft(
        action_id="a1",
        cycle={
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V2",
            "g2": {"g_code": "g_does_not_exist"},
        },
        complete=True,
    )
    good = CycleDraft(
        action_id="a2",
        cycle={
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V2",
            "g2": {"g_code": "g_grasp"},
        },
        complete=True,
    )
    out = apply_engine_gate([bad, good], rs)
    assert out[0].engine_result is None
    assert any(i.startswith("engine_reject_") for i in out[0].issues)
    assert out[1].engine_result is not None
    assert out[1].engine_result["total_tmu"] == 6.0


def test_p_addon_no_base_engine_reject():
    draft = CycleDraft(
        action_id="a1",
        cycle={
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V2",
            "g2": {"g_code": "g_grasp"},
            "p5": {"p_base_code": None, "p_addon_codes": ["a_insert"]},
        },
        complete=True,
    )
    out = apply_engine_gate([draft], build_from_seed_v2())
    assert out[0].engine_result is None
    assert "engine_reject_P_ADDON_NO_BASE" in out[0].issues
