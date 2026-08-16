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


# ── P 方向數情境規則（IE 裁決 D3-017：放入機構件→對準／放上盤面→無方向）──────

_P_VARIANTS = [
    {"parameter": "P", "option_code": "p_place_single", "synonym_norm": "放至", "priority": 0},
    {"parameter": "P", "option_code": "p_place_none", "synonym_norm": "放至", "priority": 1},
    {"parameter": "P", "option_code": "p_place_single", "synonym_norm": "放置", "priority": 0},
    {"parameter": "P", "option_code": "p_place_none", "synonym_norm": "放置", "priority": 1},
    {"parameter": "P", "option_code": "p_hold", "synonym_norm": "保持住", "priority": 0},
]


def _p_set(sets):
    return next(s for s in sets if s.parameter == "P")


@pytest.mark.asyncio
async def test_p_direction_mechanism_defaults_single():
    """機構件賓語（治具）→ p_place_single（方向數預設一種）；另一變體進 top_k。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "雙手抓握主板放至DIMM壓合治具"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_single"
    assert [c.option_code for c in p.top_k[:2]] == ["p_place_single", "p_place_none"]


@pytest.mark.asyncio
async def test_p_direction_surface_picks_none():
    """盤面賓語（工作台）→ p_place_none（IE 情境規則：無方向）。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "雙手重新抓握主板放至潔淨棚的工作台"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_none"
    assert [c.option_code for c in p.top_k[:2]] == ["p_place_none", "p_place_single"]


@pytest.mark.asyncio
async def test_p_direction_unclassified_keeps_default_flags_review():
    """賓語不在兩類名單（規定位置處）→ 維持預設 single＋needs_review（IE 裁決）。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "左手抓握DIMM材料盒放至規定位置處"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_single"
    assert p.needs_review is True
    assert p.review_reason == "p_direction_unclassified"


@pytest.mark.asyncio
async def test_p_direction_tail_bounded_by_clause():
    """賓語擷取止於子句標點：「放至定位,再從料架取料」不得跨子句配到料架（盤面）。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "放至定位,再從料架取料"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_single"
    assert p.review_reason == "p_direction_unclassified"


@pytest.mark.asyncio
async def test_p_direction_rule_skips_non_variant_faces():
    """非方向變體面（保持住→p_hold）原樣通過，不被規則改寫。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "雙手抓握主板保持住至流水線"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_hold"
    assert p.review_reason is None
