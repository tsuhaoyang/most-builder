"""Engine gate：對 complete drafts 呼叫 compute_cycle；失敗不擋其他 draft。"""
from __future__ import annotations

from typing import Any

from ddm_v2.most_engine.calculate import SequenceError, compute_cycle
from ddm_v2.most_engine.narrative import build_narrative
from ddm_v2.most_engine.rule_set_data import RuleSetData
from ddm_v2.nlp.contracts import CycleDraft
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine


def apply_engine_gate(
    drafts: list[CycleDraft],
    rs: RuleSetData,
    *,
    labels: dict[str, dict[str, Any]] | None = None,
) -> list[CycleDraft]:
    """僅對 complete=True 且 cycle 非空者算 TMU；partial 跳過（A5）。"""
    out: list[CycleDraft] = []
    empty_vocab = {"object": "", "from": "", "to": "", "hand": ""}
    lab = labels or {}
    for draft in drafts:
        if not draft.complete or not draft.cycle:
            out.append(draft)
            continue
        try:
            cin = CycleIn.model_validate(draft.cycle)
            result = compute_cycle(cycle_in_to_engine(cin), rs)
            engine_result = {
                "total_tmu": result.total_tmu,
                "total_seconds": result.total_seconds,
                "tech_line": result.tech_line,
                "breakdown": [
                    {"letter": L, "tmu": t} for L, t in zip(result.letters, result.slot_tmus)
                ],
            }
            narrative = build_narrative(cin.model_dump(mode="json"), lab, empty_vocab)
            # strip compile-only soft issues that don't invalidate engine success
            soft = {
                "quantity_policy_review",
                "next_operation",
                "i_range_assumed",
            }
            remaining = [i for i in draft.issues if i not in soft and not i.startswith("missing_core_")]
            # keep soft reasons for routing visibility
            issues = [i for i in draft.issues if i in soft] + remaining
            out.append(
                draft.model_copy(
                    update={
                        "engine_result": engine_result,
                        "narrative": narrative,
                        "issues": issues,
                    }
                )
            )
        except SequenceError as exc:
            out.append(
                draft.model_copy(
                    update={
                        "engine_result": None,
                        "narrative": None,
                        "issues": list(draft.issues) + [f"engine_reject_{exc.code}"],
                        # completeness stays True but invalid for routing
                    }
                )
            )
    return out
