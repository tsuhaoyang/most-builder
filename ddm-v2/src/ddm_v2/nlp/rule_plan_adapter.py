"""RuleBasedParser → wi-plan-v1 WorkInstructionPlan adapter（L0 fallback / baseline）。

Spec §7.7、附錄 A3。
"""
from __future__ import annotations

from ddm_v2.nlp.contracts import (
    EvidenceSpan,
    OptionCandidate,
    ParseRunResult,
    PlannedAction,
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)
from ddm_v2.nlp.ports import NLDraftResult, SlotSuggestion

_SOURCE_MAP = {
    "exact": "synonym_exact",
    "longest_match": "synonym_longest",
    "default": "default",
    "retrieval": "trgm",
}


def _action_type_for_seq(seq: str | None) -> str:
    if seq == "GM":
        return "move_place"
    if seq == "CM":
        return "controlled_move"
    return "composite_unknown"


def _detect_language(text: str) -> str:
    if not text:
        return "zh"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ratio = cjk / max(len(text), 1)
    if ratio >= 0.3:
        return "zh"
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if ascii_letters / max(len(text), 1) >= 0.5:
        return "en"
    return "mixed"


def plan_from_rule_result(
    result: NLDraftResult,
    *,
    source_ref: SourceRef | None = None,
) -> tuple[WorkInstructionPlan, list[SlotCandidateSet]]:
    """將既有 NLDraftResult 包成單 action plan + slot candidates。"""
    action_type = _action_type_for_seq(result.suggested_seq)
    evidence: list[EvidenceSpan] = []
    if result.normalized_text:
        evidence.append(
            EvidenceSpan(
                start=0,
                end=len(result.normalized_text),
                text=result.normalized_text,
            )
        )

    unresolved: list[str] = []
    if action_type == "composite_unknown":
        unresolved.append("composite_unknown")

    action = PlannedAction(
        action_id="a1",
        action_type=action_type,  # type: ignore[arg-type]
        sequence_order=1,
        roles={},
        evidence=evidence,
        notes="rule_based_v1",
    )
    plan = WorkInstructionPlan(
        source_text=result.raw_text,
        normalized_text=result.normalized_text,
        language=_detect_language(result.normalized_text),  # type: ignore[arg-type]
        source_ref=source_ref
        or SourceRef(kind="interactive", worksheet_id=None, import_id=None, import_row_index=None),
        actions=[action],
        dependencies=[],
        unresolved=unresolved,
    )

    candidates = [_slot_to_candidate_set(s, action_id="a1") for s in result.slots]
    return plan, candidates


def _slot_to_candidate_set(slot: SlotSuggestion, *, action_id: str) -> SlotCandidateSet:
    param = _field_to_parameter(slot.field)
    top_k: list[OptionCandidate] = []
    for i, c in enumerate(slot.top_k):
        top_k.append(
            OptionCandidate(
                parameter=param,
                option_code=c.option_code,
                score=c.score,
                source=_SOURCE_MAP.get(c.source, "synonym_exact"),  # type: ignore[arg-type]
                rank=i + 1,
            )
        )
    chosen = top_k[0] if top_k else None
    reason = None
    if chosen is None:
        reason = "no_candidate"
    elif slot.needs_review:
        reason = "low_score"
    return SlotCandidateSet(
        action_id=action_id,
        parameter=param,
        field=_legacy_field_to_cycle_field(slot.field),
        chosen=chosen,
        top_k=top_k,
        needs_review=slot.needs_review or chosen is None,
        review_reason=reason,
    )


def _field_to_parameter(field: str) -> str:
    if field.startswith("a_"):
        return "A"
    if field.startswith("b_"):
        return "B"
    if field.startswith("g_"):
        return "G"
    if field.startswith("p_"):
        return "P"
    if field.startswith("m_"):
        return "M"
    if field.startswith("x_"):
        return "X"
    if field.startswith("i_"):
        return "I"
    return field[:1].upper() or "?"


def _legacy_field_to_cycle_field(field: str) -> str:
    """legacy NLDraftResult.field → CycleIn 風格 field 字串（附錄 A3）。"""
    return {
        "a_code": "a0",
        "b_code": "b1.b_code",
        "g_code": "g2.g_code",
        "a_code2": "a3",
        "b_code2": "b4.b_code",
        "p_base_code": "p5.p_base_code",
        "a_code3": "a6",
    }.get(field, field)


def legacy_from_parse_run(
    *,
    raw_text: str,
    normalized_text: str,
    slots: list[SlotSuggestion],
    suggested_seq: str | None,
    overall_confidence: float,
    provenance: dict,
) -> dict:
    """組舊 NLDraftResult 形狀 dict（供 /nl-draft 相容回應）。"""
    return {
        "raw_text": raw_text,
        "normalized_text": normalized_text,
        "suggested_seq": suggested_seq,
        "context": {},
        "slots": [
            {
                "slot_index": s.slot_index,
                "field": s.field,
                "chosen": (
                    {
                        "option_code": s.chosen.option_code,
                        "score": s.chosen.score,
                        "source": s.chosen.source,
                    }
                    if s.chosen
                    else None
                ),
                "top_k": [
                    {
                        "option_code": c.option_code,
                        "score": c.score,
                        "source": c.source,
                    }
                    for c in s.top_k
                ],
                "needs_review": s.needs_review,
            }
            for s in slots
        ],
        "overall_confidence": overall_confidence,
        "provenance": provenance,
    }


_CYCLE_FIELD_TO_LEGACY: dict[str, tuple[str, int]] = {
    "a0": ("a_code", 0),
    "b1.b_code": ("b_code", 1),
    "g2.g_code": ("g_code", 2),
    "a3": ("a_code2", 3),
    "b4.b_code": ("b_code2", 4),
    "p5.p_base_code": ("p_base_code", 5),
    "a6": ("a_code3", 6),
}

_CANDIDATE_SOURCE_TO_LEGACY = {
    "synonym_exact": "exact",
    "synonym_longest": "longest_match",
    "default": "default",
    "trgm": "retrieval",
    "embedding": "retrieval",
    "llm_rerank": "retrieval",
    "template": "exact",
}

_ACTION_TO_SEQ = {
    "acquire": "GM",
    "move_place": "GM",
    "release_return": "GM",
    "controlled_move": "CM",
    "process": "CM",
    "inspect": "CM",
}


def legacy_from_run_snapshot(
    *,
    raw_text: str,
    result: ParseRunResult,
    provenance_extra: dict | None = None,
) -> dict:
    """快取命中：自已存檔的 plan/candidates 還原 legacy，避免與當下 synonym 漂移。"""
    plan = result.plan
    suggested_seq: str | None = None
    if plan.actions:
        suggested_seq = _ACTION_TO_SEQ.get(plan.actions[0].action_type)

    by_field = {c.field: c for c in result.slot_candidates}
    slots_out: list[dict] = []
    filled = 0
    for cycle_field, (legacy_field, idx) in _CYCLE_FIELD_TO_LEGACY.items():
        cand = by_field.get(cycle_field)
        if cand and cand.chosen:
            filled += 1
            chosen = {
                "option_code": cand.chosen.option_code,
                "score": cand.chosen.score,
                "source": _CANDIDATE_SOURCE_TO_LEGACY.get(cand.chosen.source, cand.chosen.source),
            }
            top_k = [
                {
                    "option_code": t.option_code,
                    "score": t.score,
                    "source": _CANDIDATE_SOURCE_TO_LEGACY.get(t.source, t.source),
                }
                for t in cand.top_k
            ]
            needs_review = cand.needs_review
        else:
            chosen = None
            top_k = []
            needs_review = True
        slots_out.append(
            {
                "slot_index": idx,
                "field": legacy_field,
                "chosen": chosen,
                "top_k": top_k,
                "needs_review": needs_review,
            }
        )

    provenance = {
        "parser": "rule_based_v1",
        "rule_set_code": "",
        "elapsed_ms": (result.provenance.get("latency_ms") or {}).get("plan", 0),
        "from_cached_run": True,
    }
    if provenance_extra:
        provenance.update(provenance_extra)

    return {
        "raw_text": raw_text,
        "normalized_text": plan.normalized_text,
        "suggested_seq": suggested_seq,
        "context": {},
        "slots": slots_out,
        "overall_confidence": filled / 7.0 if slots_out else 0.0,
        "provenance": provenance,
    }
