"""Parse routing §10.3（純函數）。"""
from __future__ import annotations

from ddm_v2.nlp.contracts import CycleDraft, SlotCandidateSet, WorkInstructionPlan
from ddm_v2.settings import get_settings

ROUTING_REASONS = frozenset(
    {
        "engines_disagree",
        "baseline_disagreement",
        "quantity_policy_review",
        # S-2：數值主張無法定位到該 action 的文字證據（distance→A/M 檔位、
        # quantity→frequency 乘數）。值照樣採用，但覆核者必須看得到「沒有出處」
        "distance_unevidenced_review",
        "quantity_unevidenced_review",
        # 非有限值（NaN／±Inf）被 compiler 拒收——放行會落到最大 A 檔位／算出
        # nan TMU／丟 Decimal 例外（見 policies.NON_FINITE_VALUE_REJECTED）
        "non_finite_value_rejected",
        # `template_hint`：由 `compute_routing` 從 candidate 的 review_reason 寫進
        # reasons，並列在 `_eligible_auto` 的 `blocked` 內擋 auto——**先前漏宣告**。
        # 這裡是宣告，那裡是執行；兩者由
        # `tests/unit/test_contract_enum_freeze.py::test_eligible_auto_blocked_reasons_are_all_declared`
        # 單向釘死（blocked ⊆ 本集合）。
        "template_hint",
        "planner_invented_action",
        "tool_state_violation",
        # ADR-033 D6（spec §7.5.1）：adapter 邊界的**剝除**旗標。契約放寬後這些
        # 情形不再讓整筆輸出作廢，代價是「我方改過模型的輸出」必須看得見——
        # 四者都經 plan.unresolved 進來（`sanitize_planner_output` 併入），
        # 並列在下方 `_eligible_auto` 的 blocked 內顯式擋 auto。
        "role_key_dropped",          # 自創角色鍵（實測最大宗：object_ref/hand_ref）
        "role_numeric_stripped",     # value/unit 被剝除（D1：數值不歸 LLM）
        "role_text_not_in_source",   # 片語不是原文的字面子字串（改寫／幻覺）
        "dependency_dropped",        # 型別不合法或端點已不存在
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
        # S-2：無憑據的數值（模型主張、文字定位不到）不得自動落地成工時標準
        "distance_unevidenced_review",
        "quantity_unevidenced_review",
        # 送進來 NaN／Inf 的計畫是壞掉的模型輸出，一律人工覆核
        "non_finite_value_rejected",
        "template_hint",
        # ADR-033 D6：被我方剝除過的輸出一律不得自動落地（見 ROUTING_REASONS 註）
        "role_key_dropped",
        "role_numeric_stripped",
        "role_text_not_in_source",
        "dependency_dropped",
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
