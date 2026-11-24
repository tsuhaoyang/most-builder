"""Excel 數量權威的歸屬規則（ADR-037 D6，W3b）：純函式。"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.contracts import CycleDraft, ParseRunResult, PlannedAction, RoleValue, SourceRef, WorkInstructionPlan
from ddm_v2.services.v2.wi_draft_service import apply_excel_quantity, drafts_from_parse

pytestmark = pytest.mark.unit

GM = {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"}}


def _result(text: str, actions: list[tuple[str, str | None]], labels: list[str | None] | None = None) -> ParseRunResult:
    plan_actions = [
        PlannedAction(action_id=f"a{i}", action_type=t, sequence_order=i,  # type: ignore[arg-type]
                      roles={"object": RoleValue(text=o)} if o and labels is None else {})
        for i, (t, o) in enumerate(actions, 1)
    ]
    prov: dict = {}
    if labels is not None:
        prov["motion_labels"] = [{"action_id": f"a{i}", "object_text": o} for i, o in enumerate(labels, 1)]
    return ParseRunResult(
        run_id="", plan=WorkInstructionPlan(source_text=text, normalized_text=text, source_ref=SourceRef(kind="import_row"),
                                            actions=plan_actions),
        slot_candidates=[], drafts=[CycleDraft(action_id=f"a{i}", cycle=dict(GM), complete=True, engine_result={"t": 1})
                                    for i in range(1, len(actions) + 1)],
        routing_status="review", routing_reasons=[], provenance=prov,
    )


def _apply(result: ParseRunResult, qty):
    parsed = drafts_from_parse(result, text=result.plan.source_text, hand=None, wi_group=None, ai_status="rule_based")
    out = apply_excel_quantity(parsed, result, qty)
    return [(p.item.content.frequency, p.snapshot.get("quantity")) for p in out]


def test_missing_or_one_does_nothing():
    r = _result("拿起螺絲", [("acquire", "螺絲")])
    assert _apply(r, None) == [(1, None)]
    assert _apply(r, 1) == [(1, None)]


def test_rule_1_count_word_matches_excel_applies_to_the_counted_object():
    r = _result("拿取電動起子，鎖附兩顆螺絲", [("acquire", "電動起子"), ("process", "螺絲")])
    (f1, q1), (f2, q2) = _apply(r, 2)
    assert (f1, q1["applied"], q1["rule"], q1["reason"]) == (1, False, "1", "not_the_counted_object")
    assert (f2, q2["applied"], q2["rule"]) == (2, True, "1")


def test_rule_4_sentence_number_differs_from_excel():
    r = _result("鎖附兩顆螺絲", [("process", "螺絲")])
    ((f, q),) = _apply(r, 3)
    assert (f, q["rule"], q["applied"], q["reason"]) == (1, "4", False, "sentence_quantity_differs")


def test_rule_2_no_count_word_applies_to_process_and_move_place_only():
    r = _result("拿起螺絲鎖到主板", [("acquire", "螺絲"), ("process", "螺絲"), ("move_place", "主板")])
    out = _apply(r, 4)
    assert [f for f, _q in out] == [1, 4, 4]
    assert out[0][1] == {"excel": 4, "rule": "2", "applied": False, "reason": "other_motion_not_applied"}
    assert all(q["rule"] == "2" for _f, q in out)


def test_rule_3_ai_expanded_into_n_motions_of_the_same_object():
    r = _result("鎖附螺絲", [("process", None), ("process", None), ("process", None)], labels=["螺絲", "螺絲", "螺絲"])
    out = _apply(r, 3)
    assert [f for f, _q in out] == [1, 1, 1]
    assert {q["rule"] for _f, q in out} == {"3"} and {q["reason"] for _f, q in out} == {"ai_expanded"}


@pytest.mark.parametrize("bad", [2.5, -1, 0, "abc", float("nan")])
def test_rule_4_excel_value_not_a_positive_integer(bad):
    r = _result("拿起螺絲", [("process", "螺絲")])
    ((f, q),) = _apply(r, bad)
    assert (f, q["rule"], q["reason"]) == (1, "4", "excel_quantity_invalid")


def test_rule_4_no_process_motion_without_count_word():
    r = _result("拿起螺絲", [("acquire", "螺絲")])
    ((f, q),) = _apply(r, 2)
    assert (f, q["rule"], q["reason"]) == (1, "4", "no_process_or_move_place")


def test_quantity_does_not_change_the_cycle_hash():
    """改 frequency 不算「人補過 cycle」，不完整的判斷不受影響。"""
    r = _result("拿起螺絲鎖到主板", [("process", "螺絲")])
    parsed = drafts_from_parse(r, text="x", hand=None, wi_group=None, ai_status="rule_based")
    out = apply_excel_quantity(parsed, r, 2)
    assert out[0].snapshot["cycle_hash"] == parsed[0].snapshot["cycle_hash"]


def test_rule_1_does_not_cross_a_clause_boundary():
    """「鎖附螺絲 2 顆，拿起電動起子」：2 顆後面隔了逗號才出現起子，不綁到起子。"""
    r = _result("鎖附螺絲2顆，拿起電動起子", [("process", "螺絲"), ("acquire", "電動起子")])
    out = _apply(r, 2)
    assert {q["rule"] for _f, q in out} == {"4"} and [f for f, _q in out] == [1, 1]


@pytest.mark.parametrize("text", ["螺絲鎖兩次", "鎖附螺絲x2"])
def test_repeat_counts_do_not_bind_an_object(text):
    r = _result(text, [("process", "螺絲")])
    ((f, q),) = _apply(r, 2)
    assert (f, q["rule"], q["reason"]) == (1, "4", "quantity_target_unclear")


def test_rule_3_needs_the_same_action_type():
    """拿螺絲＋鎖螺絲不是「展開」：走規則 1，數量套到被修飾的那個動作。"""
    r = _result("拿起螺絲，鎖附兩顆螺絲", [("acquire", "螺絲"), ("process", "螺絲")])
    out = _apply(r, 2)
    assert {q["rule"] for _f, q in out} == {"1"}


def test_excel_one_but_sentence_says_otherwise_is_flagged():
    r = _result("鎖附兩顆螺絲", [("process", "螺絲")])
    ((f, q),) = _apply(r, 1)
    assert (f, q["rule"], q["reason"]) == (1, "4", "sentence_quantity_differs")


def test_unrecognised_count_words_are_not_treated_as_no_count():
    r = _result("鎖附三支螺絲", [("process", "螺絲")])
    ((f, q),) = _apply(r, 3)
    assert (f, q["rule"]) == (1, "4"), "「三支」extract_counts 認不得：不當成整句重複"


def test_excel_quantity_above_the_frequency_cap_is_invalid():
    r = _result("拿起螺絲", [("process", "螺絲")])
    ((f, q),) = _apply(r, 50_000)
    assert (f, q["reason"]) == (1, "excel_quantity_invalid")


def test_unknown_code_from_ai_is_listed_first_on_every_draft():
    """ai_service 回了允許清單外的代碼：每一列草稿的 issues 都標 ai_unknown_code（放第一個），complete 不變。"""
    r = _result("雙手按壓卡扣並確認", [("process", "卡扣"), ("inspect", "卡扣")])
    r.routing_reasons = ["ai_source_no_evidence", "ai_unknown_code"]
    parsed = drafts_from_parse(r, text="x", hand=None, wi_group=None, ai_status="ai_service")
    assert [p.snapshot["issues"][0] for p in parsed] == ["ai_unknown_code", "ai_unknown_code"]
    assert [p.snapshot["complete"] for p in parsed] == [True, True]
    r2 = _result("拿起螺絲", [("acquire", "螺絲")])
    assert "ai_unknown_code" not in drafts_from_parse(r2, text="x", hand=None, wi_group=None, ai_status="rule_based")[0].snapshot["issues"]


def test_unknown_code_is_not_duplicated():
    r = _result("按壓卡扣", [("process", "卡扣")])
    r.routing_reasons = ["ai_unknown_code"]
    r.drafts[0].issues = ["ai_unknown_code", "ai_candidate_preview"]
    issues = drafts_from_parse(r, text="x", hand=None, wi_group=None, ai_status="ai_service")[0].snapshot["issues"]
    assert issues.count("ai_unknown_code") == 1
