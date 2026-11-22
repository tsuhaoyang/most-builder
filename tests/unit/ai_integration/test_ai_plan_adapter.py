"""ai_integration.plan_adapter：motion 建議 → plan＋候選＋預覽 draft（ADR-037 D3）。

鎖住的事：AI 的 code 只是候選（`chosen` 恆為 None）、`action_type` 由 MOST 規則推導（不看 hint）、
預覽用複本算（不改原候選）、數值提示不變成距離、一律不得 auto。
"""
from __future__ import annotations

import pytest

from ddm_v2.ai_integration.plan_adapter import (
    AI_PLANNER_NOTE,
    REASON_ADDON_TRUNCATED,
    REASON_CANDIDATE_PREVIEW,
    REASON_HAND_MISMATCH,
    REASON_NO_EVIDENCE,
    REASON_RETURN_A,
    REASON_UNKNOWN_CODE,
    build_plan_from_motions,
    derive_action_type,
    preview_drafts,
    promote_for_preview,
)
from ddm_v2.ai_integration.ports import ASlotSuggestion, MotionSuggestion, PSlotSuggestion
from ddm_v2.most_compiler.compile import allow_lists_from_rule_set
from ddm_v2.most_engine.providers import build_from_seed_v2
from ddm_v2.nlp.contracts import OptionCandidate, SlotCandidateSet, SourceRef
from ddm_v2.nlp.routing import ROUTING_REASONS, compute_routing

pytestmark = pytest.mark.unit

ALLOW = allow_lists_from_rule_set(build_from_seed_v2())
RULE_SET = "MINIMOST_FACTORY_V2"
M_CODE = sorted(ALLOW["M"])[0]
X_CODE = sorted(ALLOW["X"])[0]
I_CODE = sorted(ALLOW["I"])[0]
SRC = SourceRef(kind="interactive")


def _m(index: int = 0, **kw) -> MotionSuggestion:
    base = dict(
        index=index,
        hand_hint="RH",
        seq_kind_hint="GM",
        sub_activity="右手動作",
        object_text="DIMM",
        a0=None,
        b1=None,
        g2=None,
    )
    base.update(kw)
    return MotionSuggestion(**base)


def _build(motions, **kw):
    return build_plan_from_motions(
        motions, source_text="拿DIMM放到座上", normalized_text="拿DIMM放到座上", language="zh", source_ref=SRC, **kw
    )


GM_FULL = dict(b1="b_stand", g2="g_pick_sel", p5=PSlotSuggestion(base="p_hold", addon=("a_align",)))


# ═════════ action_type 由 MOST 規則推導 ═════════

@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (dict(g2="g_pick_sel"), "acquire"),
        (dict(g2="g_pick_sel", p5=PSlotSuggestion(base="p_hold")), "move_place"),
        (dict(p5=PSlotSuggestion(base="p_hold")), "move_place"),
        (dict(m3=M_CODE), "controlled_move"),
        (dict(g2="g_pick_sel", m3=M_CODE, x4=X_CODE), "controlled_move"),
        (dict(x4=X_CODE), "process"),
        (dict(x4=X_CODE, i5=I_CODE), "process"),
        (dict(i5=I_CODE), "inspect"),
        ({}, "composite_unknown"),
        (dict(b1="b_stand"), "composite_unknown"),
        # 形狀矛盾：CM 中段與 GM 中段同時有值 → 不猜
        (dict(m3=M_CODE, p5=PSlotSuggestion(base="p_hold")), "composite_unknown"),
        (dict(x4=X_CODE, b4="b_eye"), "composite_unknown"),
        (dict(i5=I_CODE, a3=ASlotSuggestion(kind="reach")), "composite_unknown"),
    ],
)
def test_action_type_is_derived_from_slot_content(kwargs, expected):
    assert derive_action_type(_m(**kwargs)) == expected


@pytest.mark.parametrize("hand", ["LH", "RH", "BH", None])
@pytest.mark.parametrize("seq", ["GM", "CM", None])
def test_hand_and_seq_kind_hints_never_change_the_action_type(hand, seq):
    m = _m(hand_hint=hand, seq_kind_hint=seq, g2="g_pick_sel", p5=PSlotSuggestion(base="p_hold"))
    assert derive_action_type(m) == "move_place"


# ═════════ plan 與候選 ═════════

def test_codes_become_ai_service_candidates_and_chosen_stays_empty():
    b = _build([_m(**GM_FULL)])
    assert {c.parameter for c in b.candidates} == {"B", "G", "P", "P_ADDON"}
    for c in b.candidates:
        assert c.chosen is None, "AI 的 code 只是候選；chosen 是 MOST 或人的決定"
        assert c.needs_review is True
        assert [t.source for t in c.top_k] == ["ai_service"]
    fields = {c.parameter: c.field for c in b.candidates}
    assert fields == {"B": "b1.b_code", "G": "g2.g_code", "P": "p5.p_base_code", "P_ADDON": "p5.p_addon_codes"}
    assert {c.parameter: c.top_k[0].option_code for c in b.candidates} == {
        "B": "b_stand", "G": "g_pick_sel", "P": "p_hold", "P_ADDON": "a_align",
    }


def test_cm_codes_map_to_m_x_i_candidates():
    b = _build([_m(seq_kind_hint="CM", m3=M_CODE, x4=X_CODE, i5=I_CODE)])
    assert {c.parameter: c.field for c in b.candidates} == {"M": "m3.verb_code", "X": "x4.x_code", "I": "i5.i_code"}


def test_plan_shape_order_and_planner_tag():
    b = _build([_m(2, g2="g_pick_sel"), _m(0, **GM_FULL), _m(1, i5=I_CODE)])
    assert [a.action_id for a in b.plan.actions] == ["a1", "a2", "a3"]
    assert [a.sequence_order for a in b.plan.actions] == [1, 2, 3]
    assert [a.action_type for a in b.plan.actions] == ["move_place", "inspect", "acquire"], "依 ai_service 的 index 排序"
    assert all(a.notes == AI_PLANNER_NOTE and a.roles == {} and a.evidence == [] for a in b.plan.actions)
    assert b.plan.unresolved == [] and b.plan.dependencies == []
    assert {c.action_id for c in b.candidates} <= {"a1", "a2", "a3"}


def test_labels_carry_display_text_only():
    b = _build([_m(sub_activity="右手拿起", object_text="假DIMM", g2="g_pick_sel")])
    assert b.labels["a1"].sub_activity == "右手拿起" and b.labels["a1"].object_text == "假DIMM"
    assert "假DIMM" not in b.plan.model_dump_json(), "ai_service 的文字不進 plan（沒有 evidence，不捏造 role 文字）"


def test_no_motions_gives_an_empty_plan_without_reasons():
    b = _build([])
    assert b.plan.actions == [] and b.candidates == [] and b.reasons == []
    status, reasons = compute_routing(b.plan, b.candidates, [], extra_reasons=b.reasons, auto_enabled=True)
    assert status == "abstain"


# ═════════ routing reasons ═════════

def test_every_ai_result_is_flagged_as_having_no_evidence():
    assert _build([_m(g2="g_pick_sel")]).reasons == [REASON_NO_EVIDENCE]


def test_unknown_code_issue_from_the_mapper_is_flagged():
    b = _build([_m(g2=None, issues=("unknown_code:s2_G",))])
    assert REASON_UNKNOWN_CODE in b.reasons
    assert _build([_m(g2="g_pick_sel")], result_issues=("unknown_code:s5.base",)).reasons.count(REASON_UNKNOWN_CODE) == 1


@pytest.mark.parametrize("slot", ["a0", "a3", "a6"])
def test_return_type_a_position_is_flagged(slot):
    b = _build([_m(g2="g_pick_sel", **{slot: ASlotSuggestion(kind="return")})])
    assert REASON_RETURN_A in b.reasons


def test_hand_hint_is_only_compared_when_the_known_hand_is_given():
    m = _m(hand_hint="LH", g2="g_pick_sel")
    assert REASON_HAND_MISMATCH not in _build([m]).reasons
    assert REASON_HAND_MISMATCH not in _build([m], known_hand="LH").reasons
    assert REASON_HAND_MISMATCH in _build([m], known_hand="RH").reasons
    assert REASON_HAND_MISMATCH not in _build([_m(hand_hint=None, g2="g_pick_sel")], known_hand="RH").reasons


def test_more_than_one_addon_is_flagged_as_truncated():
    one = _build([_m(p5=PSlotSuggestion(base="p_hold", addon=("a_align",)))])
    two = _build([_m(p5=PSlotSuggestion(base="p_hold", addon=("a_align", "a_insert")))])
    assert REASON_ADDON_TRUNCATED not in one.reasons
    assert REASON_ADDON_TRUNCATED in two.reasons
    addon = next(c for c in two.candidates if c.parameter == "P_ADDON")
    assert [t.option_code for t in addon.top_k] == ["a_align", "a_insert"] and [t.rank for t in addon.top_k] == [1, 2]


def test_all_ai_reasons_are_declared_routing_reasons():
    for r in (REASON_NO_EVIDENCE, REASON_UNKNOWN_CODE, REASON_RETURN_A, REASON_HAND_MISMATCH,
              REASON_ADDON_TRUNCATED, REASON_CANDIDATE_PREVIEW):
        assert r in ROUTING_REASONS


# ═════════ 預覽 ═════════

def test_promote_returns_copies_and_does_not_touch_the_originals():
    b = _build([_m(**GM_FULL)])
    promoted = promote_for_preview(b.candidates, ALLOW)
    assert all(c.chosen is not None and c.chosen.source == "ai_service" for c in promoted)
    assert all(c.chosen is None for c in b.candidates), "原候選不被改"
    assert all(p is not o for p, o in zip(promoted, b.candidates, strict=True))


def test_promote_skips_codes_outside_the_target_rule_set():
    cand = SlotCandidateSet(
        action_id="a1", parameter="G", field="g2.g_code", chosen=None, needs_review=True,
        top_k=[OptionCandidate(parameter="G", option_code="g_not_in_rule_set", score=0.0, source="ai_service", rank=1)],
    )
    (out,) = promote_for_preview([cand], ALLOW)
    assert out.chosen is None


def test_promote_leaves_non_ai_and_already_chosen_candidates_alone():
    rule = OptionCandidate(parameter="G", option_code="g_grab", score=0.9, source="synonym_exact", rank=1)
    already = SlotCandidateSet(action_id="a1", parameter="G", field="g2.g_code", chosen=rule, top_k=[rule], needs_review=False)
    from_rule = SlotCandidateSet(action_id="a1", parameter="B", field="b1.b_code", chosen=None, top_k=[
        OptionCandidate(parameter="B", option_code="b_stand", score=0.9, source="synonym_exact", rank=1)], needs_review=True)
    out = promote_for_preview([already, from_rule], ALLOW)
    assert out[0].chosen == rule and out[1].chosen is None


def _preview(motions, **kw):
    b = _build(motions, **kw)
    return b, preview_drafts(b.plan, b.candidates, rule_set_code=RULE_SET, allow_lists=ALLOW)


def test_preview_draft_uses_the_ai_codes_and_is_marked_as_a_preview():
    b, drafts = _preview([_m(**GM_FULL)])
    (d,) = drafts
    assert d.complete is True
    assert d.cycle["g2"]["g_code"] == "g_pick_sel" and d.cycle["p5"]["p_base_code"] == "p_hold"
    assert d.cycle["p5"]["p_addon_codes"] == ["a_align"] and d.cycle["b1"]["b_code"] == "b_stand"
    assert REASON_CANDIDATE_PREVIEW in d.issues
    assert all(c.chosen is None for c in b.candidates), "預覽不改原候選"
    assert d.engine_result is None, "本模組不算 TMU"


def test_preview_marks_incomplete_and_composite_drafts_too():
    _, drafts = _preview([_m(), _m(1, g2="g_pick_sel")])
    assert [d.complete for d in drafts] == [False, True]
    assert all(REASON_CANDIDATE_PREVIEW in d.issues for d in drafts)
    assert "composite_unknown" in drafts[0].issues


def test_preview_cm_motion_compiles_from_ai_codes():
    _, drafts = _preview([_m(seq_kind_hint="CM", i5=I_CODE)])
    (d,) = drafts
    assert d.cycle["seq"] == "CM" and d.cycle["i5"]["i_code"] == I_CODE
    assert REASON_CANDIDATE_PREVIEW in d.issues


def test_magnitude_hints_never_become_distances():
    b, drafts = _preview([_m(
        a0=ASlotSuggestion(kind="reach", magnitude_cm_hint=35.0),
        a3=ASlotSuggestion(kind="reach", magnitude_cm_hint=60.0),
        a6=ASlotSuggestion(kind="reach", magnitude_cm_hint=12.0),
        **GM_FULL,
    )])
    c = drafts[0].cycle
    assert c["a0"]["reach_cm"] == 0.0 and c["a3"]["reach_cm"] == 0.0 and c["a6"]["reach_cm"] == 0.0
    assert b.plan.actions[0].measurements == {}, "ai_estimate_confirmed 須有人確認，這裡不產生"


def test_a_distance_written_in_the_sentence_is_flagged_not_trusted():
    """句面的距離由 MOST 自己抽取，沒有 evidence 窗 → 照舊標 `distance_unevidenced_review`。"""
    b = build_plan_from_motions(
        [_m(**GM_FULL)], source_text="從30cm外拿DIMM放到座上", normalized_text="從30cm外拿DIMM放到座上",
        language="zh", source_ref=SRC,
    )
    (d,) = preview_drafts(b.plan, b.candidates, rule_set_code=RULE_SET, allow_lists=ALLOW)
    assert "distance_unevidenced_review" in d.issues


def test_an_ai_result_can_never_route_to_auto_even_with_the_flag_on():
    b, drafts = _preview([_m(**GM_FULL)])
    status, reasons = compute_routing(b.plan, b.candidates, drafts, extra_reasons=b.reasons, auto_enabled=True)
    assert status == "review"
    assert REASON_NO_EVIDENCE in reasons and REASON_CANDIDATE_PREVIEW in reasons


def test_ai_flags_alone_block_auto_even_if_everything_else_looked_chosen():
    """即使有人把 candidates 都填成 chosen（來源 synonym_exact），只要帶 ai_* 旗標仍不得 auto。"""
    b, drafts = _preview([_m(g2="g_pick_sel")])
    chosen = [c.model_copy(update={"chosen": OptionCandidate(parameter=c.parameter, option_code=c.top_k[0].option_code,
              score=1.0, source="synonym_exact", rank=1), "needs_review": False}) for c in b.candidates]
    complete = [d.model_copy(update={"engine_result": {"tmu": 1}}) for d in drafts]
    clean = [d.model_copy(update={"issues": []}) for d in complete]
    assert compute_routing(b.plan, chosen, clean, extra_reasons=[], auto_enabled=True)[0] == "auto", "前提：沒有 ai 旗標時會 auto"
    assert compute_routing(b.plan, chosen, clean, extra_reasons=[REASON_NO_EVIDENCE], auto_enabled=True)[0] == "review"


# ═════════ 審查後補強 ═════════

def test_promoted_copies_share_no_objects_with_the_originals():
    b = _build([_m(**GM_FULL)])
    promoted = promote_for_preview(b.candidates, ALLOW)
    for new, old in zip(promoted, b.candidates, strict=True):
        assert new.top_k is not old.top_k and new.top_k[0] is not old.top_k[0]
        assert new.chosen is not new.top_k[0], "chosen 與 top_k[0] 不是同一個物件"
    promoted[0].top_k.append(OptionCandidate(parameter="B", option_code="x", score=0, source="ai_service", rank=9))
    assert len(b.candidates[0].top_k) == 1, "改複本不影響原候選"


def test_an_orphan_p_addon_is_not_promoted_and_does_not_make_a_p_slot():
    b = _build([_m(g2="g_pick_sel", p5=PSlotSuggestion(base=None, addon=("a_align",)))])
    assert {c.parameter for c in b.candidates} == {"G", "P_ADDON"}
    addon = next(c for c in promote_for_preview(b.candidates, ALLOW) if c.parameter == "P_ADDON")
    assert addon.chosen is None
    (d,) = preview_drafts(b.plan, b.candidates, rule_set_code=RULE_SET, allow_lists=ALLOW)
    assert d.cycle["p5"]["p_addon_codes"] == [] and d.cycle["p5"]["p_base_code"] is None


def test_duplicate_motion_index_is_a_caller_bug():
    with pytest.raises(ValueError, match="unique"):
        _build([_m(0, g2="g_pick_sel"), _m(0, i5=I_CODE)])


def test_slots_compile_cannot_hold_are_listed_as_dropped_not_silently_lost():
    b = _build([_m(
        g2="g_pick_sel",
        b4="b_eye",
        a0=ASlotSuggestion(kind="foot", magnitude_cm_hint=20.0),
        a3=ASlotSuggestion(kind="reach"),
        a6=ASlotSuggestion(kind="twist", magnitude_deg_hint=90.0),
        p5=PSlotSuggestion(base="p_hold"),
    )])
    assert b.dropped == ["a1:b4", "a1:a0.foot", "a1:a0.magnitude_hint", "a1:a6.twist", "a1:a6.magnitude_hint"]
    assert all(c.parameter != "B" or c.top_k[0].option_code != "b_eye" for c in b.candidates)
    assert _build([_m(g2="g_pick_sel")]).dropped == []


def test_allow_lists_filter_candidates_again_as_defence_in_depth():
    b = _build(
        [_m(b1="b_not_in_rule_set", g2="g_pick_sel", p5=PSlotSuggestion(base="p_hold", addon=("a_align", "a_nope")))],
        allow_lists=ALLOW,
    )
    by = {c.parameter: [t.option_code for t in c.top_k] for c in b.candidates}
    assert "B" not in by and by["G"] == ["g_pick_sel"] and by["P_ADDON"] == ["a_align"]
    assert REASON_UNKNOWN_CODE in b.reasons
    assert REASON_ADDON_TRUNCATED not in b.reasons, "被濾掉後只剩一個 addon，沒有被截斷"


def test_every_candidate_code_comes_from_the_target_rule_set_when_allow_lists_are_given():
    b = _build([_m(**GM_FULL), _m(1, seq_kind_hint="CM", m3=M_CODE, x4=X_CODE, i5=I_CODE)], allow_lists=ALLOW)
    for c in b.candidates:
        assert all(t.option_code in ALLOW[c.parameter] for t in c.top_k)


def test_a_sentence_distance_is_flagged_on_every_motion_it_could_be_misattributed_to():
    b = build_plan_from_motions(
        [_m(0, g2="g_pick_sel"), _m(1, g2="g_pick_sel", p5=PSlotSuggestion(base="p_hold"))],
        source_text="拿起30cm外的DIMM再放到座上", normalized_text="拿起30cm外的DIMM再放到座上", language="zh", source_ref=SRC,
    )
    drafts = preview_drafts(b.plan, b.candidates, rule_set_code=RULE_SET, allow_lists=ALLOW)
    assert all("distance_unevidenced_review" in d.issues for d in drafts)


@pytest.mark.parametrize(
    "reason",
    [REASON_NO_EVIDENCE, REASON_UNKNOWN_CODE, REASON_RETURN_A, REASON_HAND_MISMATCH, REASON_ADDON_TRUNCATED,
     REASON_CANDIDATE_PREVIEW],
)
def test_each_ai_reason_alone_blocks_auto(reason):
    b, drafts = _preview([_m(g2="g_pick_sel")])
    chosen = [c.model_copy(update={"chosen": OptionCandidate(parameter=c.parameter, option_code=c.top_k[0].option_code,
              score=1.0, source="synonym_exact", rank=1), "needs_review": False}) for c in b.candidates]
    clean = [d.model_copy(update={"engine_result": {"tmu": 1}, "issues": []}) for d in drafts]
    assert compute_routing(b.plan, chosen, clean, extra_reasons=[], auto_enabled=True)[0] == "auto"
    assert compute_routing(b.plan, chosen, clean, extra_reasons=[reason], auto_enabled=True)[0] == "review"
