"""compute_routing §10.3 決策表。"""
from __future__ import annotations

from ddm_v2.nlp.contracts import (
    CycleDraft,
    EvidenceSpan,
    OptionCandidate,
    PlannedAction,
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)
from ddm_v2.nlp.routing import compute_routing


def _plan(*types: str) -> WorkInstructionPlan:
    actions = [
        PlannedAction(
            action_id=f"a{i}",
            action_type=t,  # type: ignore[arg-type]
            sequence_order=i,
            evidence=[EvidenceSpan(start=0, end=1, text="x")],
        )
        for i, t in enumerate(types, start=1)
    ]
    unresolved = ["composite_unknown"] if types and all(t == "composite_unknown" for t in types) else []
    return WorkInstructionPlan(
        source_text="x",
        normalized_text="x",
        source_ref=SourceRef(kind="interactive"),
        actions=actions,
        unresolved=unresolved,
    )


def test_abstain_all_unknown():
    status, reasons = compute_routing(_plan("composite_unknown"), [], [], auto_enabled=False)
    assert status == "abstain"
    assert "composite_unknown" in reasons


def test_invalid_when_engine_rejects_all_complete():
    drafts = [
        CycleDraft(
            action_id="a1",
            cycle={"seq": "GM"},
            complete=True,
            engine_result=None,
            issues=["engine_reject_G_UNKNOWN"],
        )
    ]
    status, reasons = compute_routing(_plan("acquire"), [], drafts, auto_enabled=False)
    assert status == "invalid"
    assert any(r.startswith("engine_reject_") for r in reasons)


def test_review_default():
    drafts = [
        CycleDraft(
            action_id="a1",
            cycle={"seq": "GM"},
            complete=True,
            engine_result={"total_tmu": 6},
            issues=[],
        )
    ]
    status, _ = compute_routing(_plan("acquire"), [], drafts, auto_enabled=False)
    assert status == "review"


def test_auto_never_when_flag_off():
    cand = SlotCandidateSet(
        action_id="a1",
        parameter="G",
        field="g2.g_code",
        chosen=OptionCandidate(
            parameter="G", option_code="g_grasp", score=0.95, source="synonym_exact", rank=1
        ),
        top_k=[],
        needs_review=False,
    )
    drafts = [
        CycleDraft(
            action_id="a1",
            cycle={"seq": "GM"},
            complete=True,
            engine_result={"total_tmu": 6},
            issues=[],
        )
    ]
    status, _ = compute_routing(_plan("acquire"), [cand], drafts, auto_enabled=False)
    assert status == "review"


def test_auto_blocked_by_quantity_policy_review():
    cand = SlotCandidateSet(
        action_id="a1",
        parameter="X",
        field="x4.x_code",
        chosen=OptionCandidate(
            parameter="X", option_code="x_screw_fix", score=0.95, source="synonym_exact", rank=1
        ),
        top_k=[],
        needs_review=False,
    )
    drafts = [
        CycleDraft(
            action_id="a1",
            cycle={"seq": "CM", "frequency": 2},
            complete=True,
            engine_result={"total_tmu": 6},
            issues=["quantity_policy_review"],
        )
    ]
    status, _ = compute_routing(_plan("process"), [cand], drafts, auto_enabled=True)
    assert status == "review"


def test_auto_blocked_by_m_zero_pure_inspection_assumed():
    """D3-027（D3-026 複審 H1）：E 型豁免的假設旗標**顯式**擋 auto。

    合成「結構巧合被移除」的形狀——candidates 全 synonym_exact 且無 M 候選集
    （生產上 controlled_move 恆掛 chosen=None 的 M 候選集才擋住 auto，那是
    linker 的實作細節，不是豁免語意的保證）。mutation：旗標拆出
    `_eligible_auto` 的 blocked 集合 → status 變 auto → 本測紅。"""
    cand = SlotCandidateSet(
        action_id="a1",
        parameter="I",
        field="i5.i_code",
        chosen=OptionCandidate(
            parameter="I", option_code="i_confirm", score=0.95, source="synonym_exact", rank=1
        ),
        top_k=[],
        needs_review=False,
    )
    drafts = [
        CycleDraft(
            action_id="a1",
            cycle={"seq": "CM"},
            complete=True,
            engine_result={"total_tmu": 6},
            issues=["m_zero_pure_inspection_assumed"],
        )
    ]
    status, reasons = compute_routing(
        _plan("controlled_move"), [cand], drafts, auto_enabled=True
    )
    assert status == "review", "M=0 假設（豁免）不得自動採用——顯式保證，不靠結構巧合"
    assert "m_zero_pure_inspection_assumed" in reasons


def test_auto_when_flag_on_and_exact():
    cand = SlotCandidateSet(
        action_id="a1",
        parameter="G",
        field="g2.g_code",
        chosen=OptionCandidate(
            parameter="G", option_code="g_grasp", score=0.95, source="synonym_exact", rank=1
        ),
        top_k=[],
        needs_review=False,
    )
    drafts = [
        CycleDraft(
            action_id="a1",
            cycle={"seq": "GM"},
            complete=True,
            engine_result={"total_tmu": 6},
            issues=[],
        )
    ]
    status, _ = compute_routing(_plan("acquire"), [cand], drafts, auto_enabled=True)
    assert status == "auto"
