"""Engine gate + multi_action 整合測試。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "e2e_plans"


@pytest.mark.asyncio
async def test_engine_gate_illegal_code_compile_error():
    from ddm_v2.most_compiler.compile import CompileError, allow_lists_from_rule_set, compile_plan
    from ddm_v2.most_engine.providers import build_from_seed_v2
    from ddm_v2.nlp.contracts import (
        EvidenceSpan,
        OptionCandidate,
        PlannedAction,
        SlotCandidateSet,
        SourceRef,
        WorkInstructionPlan,
    )

    plan = WorkInstructionPlan(
        source_text="x",
        normalized_text="x",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                evidence=[EvidenceSpan(start=0, end=1, text="x")],
            )
        ],
    )
    bad = SlotCandidateSet(
        action_id="a1",
        parameter="G",
        field="g2.g_code",
        chosen=OptionCandidate(
            parameter="G", option_code="g_fake", score=0.9, source="synonym_exact", rank=1
        ),
        top_k=[],
        needs_review=False,
    )
    with pytest.raises(CompileError):
        compile_plan(
            plan,
            [bad],
            rule_set_code="MINIMOST_FACTORY_V2",
            allow_lists=allow_lists_from_rule_set(build_from_seed_v2()),
        )


@pytest.mark.asyncio
async def test_multi_action_fixture_through_link_compile_gate(db_session):
    """多 action fixture plan → link → compile → engine_gate：drafts 2 筆、TMU 鎖定。

    ADR-037 前這條以假 LLM 灌 plan 走 `wi_ai_service.parse_interactive`；MOST 內的 LLM
    planner 移除後，服務層不再接受外部 plan（外部 ai_service 接入在實作計畫 S3）。
    這裡改為直接驅動同一條確定性下游（與 `parse_interactive` 同樣的 SlotLinker、
    compile_plan、apply_engine_gate 與真 DB rule-set），釘住的語意不變。
    """
    from ddm_v2.most_compiler.compile import allow_lists_from_rule_set, compile_plan
    from ddm_v2.most_compiler.engine_gate import apply_engine_gate
    from ddm_v2.most_engine import load_rule_set_from_db
    from ddm_v2.most_engine.providers import load_options_from_db
    from ddm_v2.nlp.contracts import WorkInstructionPlan
    from ddm_v2.nlp.linking import SlotLinker
    from ddm_v2.services.v2 import synonym_service as syn_svc
    from ddm_v2.services.v2 import wi_ai_service

    data = json.loads((FIXTURE_DIR / "02_screwdriver_screw_x2.json").read_text(encoding="utf-8"))
    plan = WorkInstructionPlan.model_validate(data["plan"])
    rs_code = "MINIMOST_FACTORY_V2"
    for s in data["synthetic_synonyms"]:
        try:
            await syn_svc.create_synonym(
                db_session,
                rs_code,
                {
                    "parameter": s["parameter"],
                    "option_code": s["option_code"],
                    "synonym_raw": s["synonym_norm"],
                    "priority": s.get("priority", 0),
                },
                created_by="TEST",
            )
        except Exception:
            pass  # already exists / conflict OK

    rs = await wi_ai_service._get_rule_set(db_session, rs_code)
    synonyms = await syn_svc.list_synonyms(db_session, rs_code)
    linker = SlotLinker(synonyms)
    candidates = await linker.link(plan, session=db_session, rule_set_id=rs.id)
    rsdata = await load_rule_set_from_db(db_session, rs_code)
    rsdata.validate_complete()
    drafts = compile_plan(
        plan,
        candidates,
        rule_set_code=rs_code,
        allow_lists=allow_lists_from_rule_set(rsdata),
        face_hit_params=linker.face_hit_params(plan),
    )
    opts = await load_options_from_db(db_session, rs_code)
    drafts = apply_engine_gate(drafts, rsdata, labels=wi_ai_service._option_labels(opts))

    assert len(plan.actions) == 2
    assert len(drafts) == 2
    assert drafts[0].engine_result["total_tmu"] == 6.0
    # ADR-035 D4 QuantityPolicyV2：持工具 quantity=2 → x4.repeat_count=2、frequency=1；
    # compute_cycle total_tmu 6→12（repeat 燙進格），effective TMU 不變。
    assert drafts[1].engine_result["total_tmu"] == 12.0
    assert drafts[1].cycle["frequency"] == 1
    assert drafts[1].cycle["x4"]["repeat_count"] == 2
    assert "quantity_policy_review" in drafts[1].issues
