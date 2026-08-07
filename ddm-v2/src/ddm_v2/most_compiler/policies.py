"""Compiler policies（純函數、可版本化、無 IO）。"""
from __future__ import annotations

from ddm_v2.nlp.contracts import PlannedAction, WorkInstructionPlan

# 附錄 A2：核心 slot 參數（completeness 判準）
CORE_PARAM_BY_ACTION: dict[str, str] = {
    "acquire": "G",
    "move_place": "P",
    "controlled_move": "M",
    "process": "X",
    "inspect": "I",
    # release_return：放開→P；歸位當 move_place（compile 內細分）
    "release_return": "P",
}

SEQ_BY_ACTION: dict[str, str] = {
    "acquire": "GM",
    "move_place": "GM",
    "release_return": "GM",
    "controlled_move": "CM",
    "process": "CM",
    "inspect": "CM",
}


def is_tool_held(
    action: PlannedAction,
    plan: WorkInstructionPlan,
) -> bool:
    """明示 tool_ref／tool_held_for／same_object／uses_tool → G 可留空（已持有＝0 TMU）。

    不依「較早有 acquire」自行推斷（附錄 A2：需 dependency／同物件證據）。
    """
    if action.roles.get("tool_ref") and action.roles["tool_ref"].action_ref:
        return True
    for dep in plan.dependencies:
        if dep.to_action != action.action_id:
            continue
        if dep.type in {"tool_held_for", "same_object", "uses_tool"}:
            prior = next((a for a in plan.actions if a.action_id == dep.from_action), None)
            if prior and prior.action_type == "acquire" and prior.sequence_order < action.sequence_order:
                return True
    return False


def resolve_frequency(action: PlannedAction) -> tuple[float, list[str]]:
    """QuantityPolicyV1：保守——quantity 掛在 process/move_place → frequency=N + review。

    其餘情境 frequency=1＋quantity_policy_review（若有 quantity）。
    """
    reasons: list[str] = []
    qty = action.roles.get("quantity")
    n: float | None = None
    if qty is not None and qty.value is not None:
        try:
            n = float(qty.value)
        except (TypeError, ValueError):
            n = None
    if n is None or n <= 0:
        return 1.0, reasons
    if action.action_type in {"process", "move_place"} and n == int(n):
        reasons.append("quantity_policy_review")
        return float(int(n)), reasons
    reasons.append("quantity_policy_review")
    return 1.0, reasons


def holding_inferred_reason(
    action: PlannedAction,
    plan: WorkInstructionPlan,
) -> bool:
    return is_tool_held(action, plan) and action.action_type == "move_place"
