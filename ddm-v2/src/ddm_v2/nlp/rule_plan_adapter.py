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
    """Detect language of input text with improved accuracy.
    
    Returns 'zh' for Chinese, 'en' for English, 'mixed' for mixed content.
    """
    if not text:
        return "zh"  # Default to Chinese for empty text
    
    # Count CJK characters (Chinese, Japanese, Korean)
    cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    
    # Count ASCII letters 
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    
    # Count total non-whitespace characters
    total_chars = len([ch for ch in text if not ch.isspace()])
    
    if total_chars == 0:
        return "zh"
    
    cjk_ratio = cjk_count / total_chars
    ascii_ratio = ascii_letters / total_chars
    
    # If majority CJK characters, it's Chinese
    if cjk_ratio >= 0.3:
        return "zh"
    
    # If majority ASCII letters and very few CJK, it's English  
    if ascii_ratio >= 0.5 and cjk_ratio < 0.1:
        return "en"
    
    # Mixed content
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


# fresh 路徑（`wi_ai_service.parse_interactive`）的 legacy `slots` 出處：那條路徑的
# slots 直接取自 `RuleBasedParser` 的 `NLDraftResult.slots`，與 planner 無關。
# ⚠️ 這不是全域真理——快取重播路徑的 slots 是另一批東西（見 legacy_provenance），
#    所以這個常數只給 fresh 路徑用，不要當成 slots_parser 的預設值。
LEGACY_SLOTS_PARSER = "rule_based_v1"


def legacy_provenance(
    *,
    rule_provenance: dict | None,
    planner: str,
    model: str | None,
    prompt_version: str | None,
    fallback: bool,
    slots_parser: str,
    extra: dict | None = None,
) -> dict:
    """legacy `provenance` 的**單一**組裝點：`parser` 必須是實際跑的 planner。

    為什麼要這支：`parser` 原本在兩個地方各自寫死 `"rule_based_v1"`，而
    `api/routes/v2/nl_draft.py` 直接把整個 legacy dict 展開進回應——於是不管實際
    用了 LLM 還是 rule，對外的 `provenance.parser` 永遠是 `rule_based_v1`。
    實機驗證時它兩度讓人誤判「LLM 沒被呼叫」（真正的權威訊號在
    `ai_parse_runs.fallback` 與 `llm_raw_response`）。誤導性的觀測欄位比沒有更糟。

    `slots_parser` 另外記 legacy `slots` 的出處。它**必須由呼叫端傳**，因為兩條路徑
    回的根本不是同一批 slots：

    - fresh（`wi_ai_service.parse_interactive`）：legacy slots 直接取自
      `rule_result.slots`，即 `RuleBasedParser` 的產物，與 planner 無關
      → 傳 `LEGACY_SLOTS_PARSER`（LLM 路徑的權威草稿另在 `ai.drafts`）。
    - 快取重播（`legacy_from_run_snapshot`）：legacy slots 是從 run 存下來的
      `ParseRunResult.slot_candidates` 還原的，而那批 candidates 出自
      `SlotLinker.link(plan)`——planner 是 LLM 時 link 的就是 **LLM plan**，
      跟 rule parser 沒有關係 → 傳 `slot_linker:{planner}`。

    這個欄位原本是寫死的模組常數，於是同一輸入第一次回 rule slots、第二次回 LLM plan
    衍生的 slots，卻對兩者都說 `rule_based_v1`——它犯的正是自己要治的那個病（謊報來源）。

    `parser` 與 `slots_parser` 講的是兩件事，把它們合成一個就一定有一邊在說謊。
    """
    prov = dict(rule_provenance or {})
    prov.update(
        {
            "parser": planner,
            "model": model,
            "prompt_version": prompt_version,
            "fallback": fallback,
            "slots_parser": slots_parser,
        }
    )
    if extra:
        prov.update(extra)
    return prov


def legacy_from_parse_run(
    *,
    raw_text: str,
    normalized_text: str,
    slots: list[SlotSuggestion],
    suggested_seq: str | None,
    overall_confidence: float,
    provenance: dict,
) -> dict:
    """組舊 NLDraftResult 形狀 dict（供 /nl-draft 相容回應）。

    `provenance` 請用 `legacy_provenance()` 組，不要直接把 rule parser 的
    provenance 傳進來——那會讓 `parser` 說謊（見該函式 docstring）。
    """
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

    # 快取命中時實際 planner 記在 run 上，由 `_result_from_run` 還原進
    # `result.provenance`——照抄它，不要另立一套（否則重播的回應會與當初不符）。
    src = result.provenance or {}
    planner = str(src.get("planner") or "rule_based_v1")
    provenance = legacy_provenance(
        rule_provenance={
            "rule_set_code": "",
            "elapsed_ms": (src.get("latency_ms") or {}).get("plan", 0),
            "from_cached_run": True,
        },
        planner=planner,
        model=src.get("model"),
        prompt_version=src.get("prompt_version"),
        fallback=bool(src.get("fallback", True)),
        # 上面那批 slots_out 是從 `result.slot_candidates` 還原的，而那批 candidates
        # 出自 `SlotLinker.link()` 對「當初那個 planner 的 plan」做的 link——planner 是
        # LLM 時它們就是 LLM plan 的衍生物，寫 `rule_based_v1` 是謊報。
        # （planner=rule 時 orchestrator 可能改用 rule adapter 的 candidates；兩者都源自
        #  同一次 rule parse，run 上沒有留下區分兩者的訊號，故一律以 planner 標示出處。）
        slots_parser=f"slot_linker:{planner}",
        extra=provenance_extra,
    )

    return {
        "raw_text": raw_text,
        "normalized_text": plan.normalized_text,
        "suggested_seq": suggested_seq,
        "context": {},
        "slots": slots_out,
        "overall_confidence": filled / 7.0 if slots_out else 0.0,
        "provenance": provenance,
    }
