"""rule_plan_adapter 單元測試（L0）。"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.contracts import ParseRunResult
from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.nlp.rule_plan_adapter import (
    LEGACY_SLOTS_PARSER,
    legacy_from_run_snapshot,
    legacy_provenance,
    plan_from_rule_result,
)

pytestmark = pytest.mark.unit


def test_gm_maps_to_move_place_single_action():
    result = RuleBasedParser([]).parse("將零件放到壓合治具上")
    plan, cands = plan_from_rule_result(result)
    assert len(plan.actions) == 1
    assert plan.actions[0].action_type == "move_place"
    assert plan.actions[0].action_id == "a1"
    assert len(cands) == 7


def test_cm_maps_to_controlled_move():
    result = RuleBasedParser([]).parse("並壓合機台進行壓合作業")
    plan, _ = plan_from_rule_result(result)
    assert plan.actions[0].action_type == "controlled_move"


def test_no_seq_is_composite_unknown():
    result = RuleBasedParser([]).parse("拿起零件放到位置上")
    plan, _ = plan_from_rule_result(result)
    assert plan.actions[0].action_type == "composite_unknown"
    assert "composite_unknown" in plan.unresolved


def test_synonym_candidate_source_mapped():
    parser = RuleBasedParser(
        [{"parameter": "G", "option_code": "G3", "synonym_norm": "拿取小型零件", "priority": 0}]
    )
    result = parser.parse("拿取小型零件並放置", "TEST_RS")
    _, cands = plan_from_rule_result(result)
    g = next(c for c in cands if c.field == "g2.g_code")
    assert g.chosen is not None
    assert g.chosen.option_code == "G3"
    assert g.chosen.source == "synonym_exact"


def test_compute_routing_abstain_for_composite():
    from ddm_v2.nlp.routing import compute_routing

    result = RuleBasedParser([]).parse("拿起零件放到位置上")
    plan, _ = plan_from_rule_result(result)
    status, reasons = compute_routing(plan, [], [], auto_enabled=False)
    assert status == "abstain"
    assert "composite_unknown" in reasons


def test_compute_routing_review_for_gm():
    from ddm_v2.nlp.routing import compute_routing

    result = RuleBasedParser([]).parse("將零件放到壓合治具上")
    plan, _ = plan_from_rule_result(result)
    status, reasons = compute_routing(plan, [], [], auto_enabled=False)
    assert status == "review"
    # fallback_rule_based 由 orchestrator 附加，不在 compute_routing 內
    assert "composite_unknown" not in reasons


# --- legacy_provenance ---------------------------------------------------------
#
# 為什麼補在 unit：這支是純函式、契約明確（哪個欄位說哪件事），但先前**零 unit 覆蓋**
# ——只有 `tests/integration/test_wi_ai_fallback.py` 摸得到它，而那一檔沒有
# DATABASE_URL 時整檔 skip。CLAUDE.md 明列 `pytest tests/unit` 是免 DB 的那條路徑，
# 在那條路徑上這個函式的迴歸完全隱形。它守的又正是「觀測欄位不得說謊」——
# 一個會說謊的 provenance 比沒有 provenance 更糟（實機驗證已被誤導過兩次）。

_LLM_PLANNER = "llm_planner_v1"


def _prov(**over):
    kwargs = dict(
        rule_provenance=None,
        planner="rule_based_v1",
        model=None,
        prompt_version=None,
        fallback=True,
        slots_parser=LEGACY_SLOTS_PARSER,
    )
    kwargs.update(over)
    return legacy_provenance(**kwargs)


@pytest.mark.parametrize("planner", ["rule_based_v1", _LLM_PLANNER, "llm_planner_v2"])
def test_parser_is_the_planner_that_actually_ran(planner: str):
    """`parser` 忠實反映傳入的 planner——不得再退化成寫死的 rule_based_v1。"""
    prov = _prov(planner=planner, model="claude-x", prompt_version="plan-v1.3", fallback=False)
    assert prov["parser"] == planner
    assert prov["model"] == "claude-x"
    assert prov["prompt_version"] == "plan-v1.3"
    assert prov["fallback"] is False


def test_fresh_path_slots_parser_is_the_rule_parser():
    """fresh 路徑：legacy slots 直接取自 `RuleBasedParser`，與 planner 無關。

    LLM 跑成功（fallback=False）時 `parser` 是 LLM，`slots_parser` 仍是 rule——
    兩個欄位講的是兩件事，這條就是它們**必須能不一致**的證據。
    """
    prov = _prov(planner=_LLM_PLANNER, fallback=False, slots_parser=LEGACY_SLOTS_PARSER)
    assert prov["parser"] == _LLM_PLANNER
    assert prov["slots_parser"] == "rule_based_v1"


def test_replay_path_slots_parser_names_the_slot_linker():
    """重播路徑：slots 是 `SlotLinker.link(plan)` 的產物，出處要跟著當初的 planner。

    重播回的 slots 由 run 存下來的 `slot_candidates` 還原，planner 是 LLM 時那批
    candidates link 的就是 LLM plan——標成 `rule_based_v1` 是謊報。
    """
    prov = _prov(planner=_LLM_PLANNER, fallback=False, slots_parser=f"slot_linker:{_LLM_PLANNER}")
    assert prov["slots_parser"] == f"slot_linker:{_LLM_PLANNER}"


def test_slots_parser_is_required():
    """`slots_parser` 必須由呼叫端傳——它曾是寫死的模組常數，那正是它說謊的原因。

    退回預設值（不管預設成哪一個）就會有一條路徑被標錯，所以缺參數必須是 TypeError，
    不是靜靜地用一個「大多數時候對」的值。
    """
    with pytest.raises(TypeError):
        legacy_provenance(  # type: ignore[call-arg]
            rule_provenance=None,
            planner="rule_based_v1",
            model=None,
            prompt_version=None,
            fallback=True,
        )


def test_rule_provenance_keys_are_preserved():
    """rule parser 自己的欄位要原樣帶出去，只有這 5 個受管欄位會被蓋掉。"""
    rule_prov = {
        "rule_set_code": "RS_DEFAULT",
        "elapsed_ms": 12,
        "parser": "rule_based_v1",  # rule parser 自報；受管欄位，必須被蓋掉
    }
    prov = _prov(rule_provenance=rule_prov, planner=_LLM_PLANNER, fallback=False)
    assert prov["rule_set_code"] == "RS_DEFAULT"
    assert prov["elapsed_ms"] == 12
    assert prov["parser"] == _LLM_PLANNER, "rule parser 自報的 parser 必須被實際 planner 蓋掉"
    assert rule_prov["parser"] == "rule_based_v1", "不得就地改動呼叫端傳進來的 dict"


def test_none_rule_provenance_still_yields_the_managed_keys():
    prov = _prov(rule_provenance=None)
    assert set(prov) == {"parser", "model", "prompt_version", "fallback", "slots_parser"}


def test_extra_is_merged_last():
    """`extra` 加欄位（實際用法：`cached_run_id`／`raced`），且是最後一手。

    後半段記錄的是既有行為而非鼓勵用法：`extra` 覆蓋得掉 `parser`，目前沒有呼叫端
    這樣用；哪天有人這樣用，這條會讓那個決定是明知的，而不是意外。
    """
    prov = _prov(extra={"cached_run_id": "run-1", "raced": True})
    assert prov["cached_run_id"] == "run-1"
    assert prov["raced"] is True
    assert prov["slots_parser"] == LEGACY_SLOTS_PARSER

    assert _prov(planner="rule_based_v1", extra={"parser": "shadowed"})["parser"] == "shadowed"
    assert _prov(extra=None)["parser"] == "rule_based_v1"


def test_run_snapshot_provenance_reports_planner_and_slot_linker():
    """組裝端的驗證：重播回的 provenance 兩個欄位都指向當初那個 planner。

    只測 `legacy_provenance` 不夠——欄位說不說謊取決於**呼叫端傳什麼**。
    這條把 `legacy_from_run_snapshot` 的那一段接起來測（純函式，不需要 DB）。
    """
    result = RuleBasedParser([]).parse("將零件放到壓合治具上")
    plan, cands = plan_from_rule_result(result)
    run = ParseRunResult(
        run_id="00000000-0000-0000-0000-000000000001",
        plan=plan,
        slot_candidates=cands,
        drafts=[],
        routing_status="review",
        routing_reasons=[],
        provenance={
            "planner": _LLM_PLANNER,
            "model": "claude-x",
            "prompt_version": "plan-v1.3",
            "fallback": False,
            "latency_ms": {"plan": 42},
        },
    )
    legacy = legacy_from_run_snapshot(raw_text=result.raw_text, result=run)
    prov = legacy["provenance"]
    assert prov["parser"] == _LLM_PLANNER
    assert prov["slots_parser"] == f"slot_linker:{_LLM_PLANNER}"
    assert prov["fallback"] is False
    assert prov["from_cached_run"] is True
    assert prov["elapsed_ms"] == 42
