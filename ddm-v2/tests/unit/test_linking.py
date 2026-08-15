"""SlotLinker unit tests（池隔離／低分回空／disagree）。"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.contracts import (
    EvidenceSpan,
    OptionCandidate,
    PlannedAction,
    RoleValue,
    SourceRef,
    WorkInstructionPlan,
)
from ddm_v2.nlp.linking import SlotLinker, _merge_l1_l2


def _plan(action_type: str, text: str, roles: dict | None = None) -> WorkInstructionPlan:
    return WorkInstructionPlan(
        source_text=text,
        normalized_text=text,
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type=action_type,  # type: ignore[arg-type]
                sequence_order=1,
                roles=roles or {},
                evidence=[EvidenceSpan(start=0, end=len(text), text=text)],
            )
        ],
    )


@pytest.mark.asyncio
async def test_g_pool_does_not_return_x_candidates():
    syn = [
        {"parameter": "G", "option_code": "g_grasp", "synonym_norm": "拿取", "priority": 1},
        {"parameter": "X", "option_code": "x_screw_fix", "synonym_norm": "鎖附", "priority": 1},
    ]
    linker = SlotLinker(syn)
    plan = _plan("acquire", "拿取螺絲", {"object": RoleValue(text="螺絲", status="explicit")})
    sets = await linker.link(plan)
    g = [s for s in sets if s.parameter == "G"]
    assert g and g[0].chosen and g[0].chosen.option_code == "g_grasp"
    assert all(c.parameter == "G" for s in g for c in s.top_k)


@pytest.mark.asyncio
async def test_no_candidate_when_below_threshold():
    linker = SlotLinker([])
    plan = _plan("acquire", "神秘動詞物件")
    sets = await linker.link(plan)
    assert sets
    assert sets[0].chosen is None
    assert sets[0].review_reason == "no_candidate"


@pytest.mark.asyncio
async def test_l0_template_hint_needs_review():
    plan = _plan("acquire", "雙手抓握主板放到DIMM壓合治具")
    templates = [
        {
            "id": "tmpl-1",
            "keywords": ["治具", "DIMM"],
            "cycle_template": {"seq": "GM", "g2": {"g_code": "g_grasp"}},
        }
    ]
    linker = SlotLinker([])
    sets = await linker.link(plan, templates=templates)
    tmpl = [s for s in sets if s.parameter == "TEMPLATE"]
    assert tmpl and tmpl[0].chosen and tmpl[0].chosen.option_code == "tmpl-1"
    assert tmpl[0].needs_review is True
    assert tmpl[0].review_reason == "template_hint"


def test_engines_disagree_marks_reason():
    l1 = [
        OptionCandidate(parameter="G", option_code="g_grasp", score=0.95, source="synonym_exact", rank=1)
    ]
    l2 = [
        OptionCandidate(parameter="G", option_code="g_touch", score=0.8, source="trgm", rank=1)
    ]
    chosen, top, reason = _merge_l1_l2(l1, l2)
    assert reason == "engines_disagree"
    assert chosen and chosen.option_code == "g_grasp"
    assert {c.option_code for c in top} >= {"g_grasp", "g_touch"}
