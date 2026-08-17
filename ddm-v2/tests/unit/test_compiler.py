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


# ── E 型完整性窄豁免（D3-026；IE 裁決 2026-08-17/18）─────────────────────────
#
# 純 I 句（面命中集合恰 {I}、I 已掛值、無 M 分量）→ controlled_move 缺 M 仍
# 完整（M=0，cycle 帶真 I 工時）。窄化判準逐條 mutation：
# - 面集合放寬（X 也豁免）→ test_pure_i_exemption_not_for_x_face 紅
#   （那正是 IE 否決的 (a) 全面放寬——C/G 型鎖附/清潔誠實 incomplete）；
# - G 面也豁免 → test_pure_i_exemption_not_for_g_face 紅（F 型 d001
#   「接觸…確認」有手部介入，非純目視）；
# - fail-closed 拆除（face_hit_params=None 也豁免）→
#   test_pure_i_exemption_fail_closed_without_face_evidence 紅。
# - D3-027（D3-026 複審 H1）：豁免改回靜默清空（issues.remove 不掛
#   `m_zero_pure_inspection_assumed`）→ test_pure_i_exemption_completes_
#   with_true_i_tmu 紅（字典外移動動詞的代表句＋routing 斷言在
#   test_linking.test_out_of_lexicon_motion_verb_*）——豁免的假設（M=0 是
#   lexicon 視角的假設，字典外移動動詞句也落入此類別）必須留下可見痕跡。


def _cm_plan(text: str) -> WorkInstructionPlan:
    return WorkInstructionPlan(
        source_text=text,
        normalized_text=text,
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="controlled_move",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=len(text), text=text)],
            )
        ],
    )


def _i_only_cands() -> list[SlotCandidateSet]:
    """linker 對純 I 句的候選形狀：M 核心格空（no_candidate）＋I 掛值。"""
    return [
        _cand("a1", "M", "m3.verb_code", None),
        _cand("a1", "I", "i5.i_code", "i_confirm"),
    ]


def test_pure_i_exemption_completes_with_true_i_tmu():
    """E 型（d021「並確認DIMM點位」形狀）：面集合恰 {I} → M=0 完整、
    cycle 帶 i_confirm（真 I 工時由引擎算——engine gate 測試在 test_linking）。
    豁免**不清空 issues**：missing_core_m 換成假設旗標（D3-027）。"""
    drafts = compile_plan(
        _cm_plan("並確認dimm點位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    d = drafts[0]
    assert d.complete is True
    assert "missing_core_m" not in d.issues
    assert "m_zero_pure_inspection_assumed" in d.issues, (
        "豁免＝假設不是觀測——旗標拆掉（回到靜默清空）必紅"
    )
    assert d.cycle["seq"] == "CM"
    assert d.cycle["i5"]["i_code"] == "i_confirm"
    assert d.cycle["m3"]["m_components"] == []




def test_pure_i_exemption_fail_closed_without_face_evidence():
    """face_hit_params 未提供（None）＝無面命中證據＝不豁免（行為同 D3-024）。"""
    drafts = compile_plan(
        _cm_plan("並確認dimm點位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_not_for_x_face():
    """X 面命中（鎖附/清潔型；含 H1「X 不落 chosen 但面已命中」）不豁免——
    IE 否決的 (a) 全面放寬。mutation：豁免條件放寬到含 X → 本測紅。"""
    drafts = compile_plan(
        _cm_plan("並鎖附固定並確認螺絲到位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I", "X"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_not_for_g_face():
    """G 面命中（接觸/拿取伴確認；F 型 d001 形狀）不豁免——手部已介入，
    非「目視確認無手部移動」。"""
    drafts = compile_plan(
        _cm_plan("接觸卡扣並確認到位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"G", "I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_requires_i_chosen():
    """面集合 {I} 但 I 未掛值（無 chosen）→ 不豁免——豁免的對價是真 I 工時，
    沒有值就沒有工時可帶。"""
    drafts = compile_plan(
        _cm_plan("並確認dimm點位"),
        [_cand("a1", "M", "m3.verb_code", None), _cand("a1", "I", "i5.i_code", None)],
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_not_with_m_component():
    """句面有距離（M 分量非空）→ 不豁免——有移動量就不是純目視。"""
    plan = _cm_plan("並確認dimm點位 30cm")
    drafts = compile_plan(
        plan,
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_only_controlled_move():
    """process（core X）不在豁免範圍：面集合 {I} 也不放寬 missing_core_x。"""
    plan = WorkInstructionPlan(
        source_text="並確認dimm點位",
        normalized_text="並確認dimm點位",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="process",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=9, text="並確認dimm點位")],
            )
        ],
    )
    drafts = compile_plan(
        plan,
        [_cand("a1", "X", "x4.x_code", None), _cand("a1", "I", "i5.i_code", "i_confirm")],
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_x" in drafts[0].issues


def test_compiler_package_has_no_tmu_symbols():
    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "ddm_v2" / "most_compiler"
    banned = re.compile(r"TMU_TO_SEC|total_tmu|_tmu\b|base_tmu")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "rule_set_data" not in text or "TYPE_CHECKING" in text or path.name == "engine_gate.py"
        if path.name == "engine_gate.py":
            continue  # gate 呼叫引擎，不內含表
        assert not banned.search(text), f"TMU symbol in {path}"
