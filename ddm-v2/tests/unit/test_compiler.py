"""most_compiler 決策表／partial／allow-list／無 TMU 符號。"""
from __future__ import annotations

import pathlib
import re

import pytest

from ddm_v2.most_compiler.compile import CompileError, allow_lists_from_rule_set, compile_plan
from ddm_v2.most_compiler.policies import CORE_PARAM_BY_ACTION, SEQ_BY_ACTION
from ddm_v2.most_engine.providers import build_from_seed_v2
from ddm_v2.nlp.contracts import (
    EvidenceSpan,
    OptionCandidate,
    PlannedAction,
    RoleValue,
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)


def _allow() -> dict[str, set[str]]:
    return allow_lists_from_rule_set(build_from_seed_v2())


def _cand(action_id: str, parameter: str, field: str, code: str | None) -> SlotCandidateSet:
    chosen = None
    top: list[OptionCandidate] = []
    if code:
        chosen = OptionCandidate(
            parameter=parameter, option_code=code, score=0.95, source="synonym_exact", rank=1
        )
        top = [chosen]
    return SlotCandidateSet(
        action_id=action_id,
        parameter=parameter,
        field=field,
        chosen=chosen,
        top_k=top,
        needs_review=chosen is None,
        review_reason=None if chosen else "no_candidate",
    )


@pytest.mark.parametrize(
    "action_type,seq",
    list(SEQ_BY_ACTION.items()),
)
def test_seq_decision_table(action_type: str, seq: str):
    assert seq in {"GM", "CM"}
    assert action_type in CORE_PARAM_BY_ACTION


def test_acquire_complete_without_place():
    plan = WorkInstructionPlan(
        source_text="拿起DIMM",
        normalized_text="拿起dimm",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={"object": RoleValue(text="DIMM", status="explicit")},
                evidence=[EvidenceSpan(start=0, end=6, text="拿起dimm")],
            )
        ],
    )
    cands = [_cand("a1", "G", "g2.g_code", "g_grasp")]
    drafts = compile_plan(plan, cands, rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert len(drafts) == 1
    assert drafts[0].complete is True
    assert drafts[0].cycle["seq"] == "GM"
    assert drafts[0].cycle["g2"]["g_code"] == "g_grasp"
    assert drafts[0].cycle["p5"]["p_base_code"] is None


def test_partial_when_core_missing():
    plan = WorkInstructionPlan(
        source_text="鎖附",
        normalized_text="鎖附",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="process",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=2, text="鎖附")],
            )
        ],
    )
    drafts = compile_plan(plan, [], rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert drafts[0].complete is False
    assert "missing_core_x" in drafts[0].issues


def test_unknown_code_raises_compile_error():
    plan = WorkInstructionPlan(
        source_text="x",
        normalized_text="x",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=1, text="x")],
            )
        ],
    )
    cands = [_cand("a1", "G", "g2.g_code", "g_not_real")]
    with pytest.raises(CompileError) as ei:
        compile_plan(plan, cands, rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert ei.value.code == "OPTION_NOT_IN_ALLOWLIST"


def test_composite_unknown_not_compiled():
    plan = WorkInstructionPlan(
        source_text="其餘",
        normalized_text="其餘",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="composite_unknown",
                sequence_order=1,
                evidence=[EvidenceSpan(start=0, end=2, text="其餘")],
            )
        ],
        unresolved=["composite_unknown"],
    )
    drafts = compile_plan(plan, [], rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert drafts[0].cycle is None
    assert drafts[0].complete is False


def test_compiler_package_has_no_tmu_symbols():
    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "ddm_v2" / "most_compiler"
    banned = re.compile(r"TMU_TO_SEC|total_tmu|_tmu\b|base_tmu")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "rule_set_data" not in text or "TYPE_CHECKING" in text or path.name == "engine_gate.py"
        if path.name == "engine_gate.py":
            continue  # gate 呼叫引擎，不內含表
        assert not banned.search(text), f"TMU symbol in {path}"
