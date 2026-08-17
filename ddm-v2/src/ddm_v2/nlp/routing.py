"""Parse routing §10.3（純函數）。"""
from __future__ import annotations

from ddm_v2.nlp.contracts import CycleDraft, SlotCandidateSet, WorkInstructionPlan
from ddm_v2.settings import get_settings

ROUTING_REASONS = frozenset(
    {
        "engines_disagree",
        "baseline_disagreement",
        "quantity_policy_review",
        "planner_invented_action",
        "tool_state_violation",
        "fallback_rule_based",
        "composite_unknown",
        "next_operation",
        "i_range_assumed",
        "m_zero_pure_inspection_assumed",
    }
)


def compute_routing(
    plan: WorkInstructionPlan,
    candidates: list[SlotCandidateSet],
    drafts: list[CycleDraft],
    *,
    extra_reasons: list[str] | None = None,
    auto_enabled: bool | None = None,
) -> tuple[str, list[str]]:
    """回傳 (routing_status, routing_reasons)。

    invalid  ⇐ 任一 complete draft 被 engine reject，且無任何 valid draft
    abstain  ⇐ 所有 action 都是 composite_unknown，或 plan 無 action
    auto     ⇐ flag 開且全 L1-exact、無 unresolved、無 disagree（v1 flag 硬關）
    review   ⇐ 其他
    """
    reasons: list[str] = []
    if extra_reasons:
        for r in extra_reasons:
            if r not in reasons:
                reasons.append(r)
    reasons.extend(x for x in plan.unresolved if x not in reasons)

    if not plan.actions or all(a.action_type == "composite_unknown" for a in plan.actions):
        if "composite_unknown" not in reasons:
            reasons.append("composite_unknown")
        return "abstain", reasons

    complete_drafts = [d for d in drafts if d.complete]
    valid = [
        d
        for d in complete_drafts
        if d.engine_result is not None
        and not any(i.startswith("engine_reject_") for i in d.issues)
    ]
    rejected = [
        d
        for d in drafts
        if any(i.startswith("engine_reject_") for i in d.issues)
    ]
    if rejected and not valid:
        for d in rejected:
            for i in d.issues:
                if i.startswith("engine_reject_") and i not in reasons:
                    reasons.append(i)
        return "invalid", reasons

    for c in candidates:
        if c.review_reason == "engines_disagree" and "engines_disagree" not in reasons:
            reasons.append("engines_disagree")
        if c.review_reason == "template_hint" and "template_hint" not in reasons:
            reasons.append("template_hint")
        if c.review_reason == "no_candidate":
            key = f"no_candidate_{c.parameter.lower()}"
            if key not in reasons:
                reasons.append(key)
        if c.review_reason and c.review_reason.startswith("missing_core_"):
            if c.review_reason not in reasons:
                reasons.append(c.review_reason)

    for d in drafts:
        for i in d.issues:
            if i not in reasons:
                reasons.append(i)

    if auto_enabled is None:
        auto_enabled = get_settings().wi_ai_auto_enabled
    if auto_enabled and _eligible_auto(plan, candidates, drafts, reasons):
        return "auto", reasons

    return "review", reasons


def _eligible_auto(
    plan: WorkInstructionPlan,
    candidates: list[SlotCandidateSet],
    drafts: list[CycleDraft],
    reasons: list[str],
) -> bool:
    if plan.unresolved:
        return False
    blocked = {
        "engines_disagree",
        "baseline_disagreement",
        "quantity_policy_review",
        "template_hint",
        "i_range_assumed",
        # D3-027（D3-026 複審 H1）：E 型豁免的假設旗標顯式擋 auto——先前擋
        # auto 靠「M 候選 chosen=None」的結構巧合（linker 對 controlled_move
        # 恆掛 M 候選集），豁免語意的保證不得倚賴另一模組的實作細節
        "m_zero_pure_inspection_assumed",
        "next_operation",
    }
    if any(r in blocked for r in reasons):
        return False
    if any(
        any(i in blocked or i.startswith("engine_reject_") or i.startswith("missing_core_") for i in d.issues)
        for d in drafts
    ):
        return False
    if not drafts or not all(d.complete and d.engine_result for d in drafts):
        return False
    if not candidates:
        return False
    for c in candidates:
        if c.parameter == "TEMPLATE":
            return False
        if c.chosen is None:
            return False
        if c.chosen.source != "synonym_exact":
            return False
        if c.needs_review:
            return False
    return True
