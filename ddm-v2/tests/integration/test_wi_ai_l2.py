"""Engine gate + multi_action 整合測試。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

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
async def test_multi_action_fixture_via_service_path(db_session, monkeypatch):
    """mock LLM 固定 fixture plan → drafts 2 筆、multi_action 語意、TMU 鎖定。"""
    from ddm_v2.nlp.contracts import PlannerOutput, WorkInstructionPlan
    from ddm_v2.nlp.planner_ports import LLMRawResponse
    from ddm_v2.services.v2 import synonym_service as syn_svc
    from ddm_v2.services.v2 import wi_ai_service

    data = json.loads((FIXTURE_DIR / "02_screwdriver_screw_x2.json").read_text(encoding="utf-8"))
    plan = WorkInstructionPlan.model_validate(data["plan"])
    # ensure synonyms exist so linking works on real DB
    rs_code = "MINIMOST_FACTORY_V2"
    try:
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

        async def _fake_llm(*, normalized_text, context, timeout_s):
            out = PlannerOutput(
                language=plan.language,
                actions=plan.actions,
                dependencies=plan.dependencies,
                unresolved=plan.unresolved,
            )
            raw = LLMRawResponse(
                content="{}",
                model="fake",
                usage={},
                latency_ms=1.0,
                response_format_mode="json_object",
            )
            return out, raw

        monkeypatch.setenv("DDM_WI_AI_ENABLED", "1")
        # clear settings cache if any
        from ddm_v2 import settings as settings_mod

        if hasattr(settings_mod, "_SETTINGS"):
            settings_mod._SETTINGS = None  # type: ignore[attr-defined]
        get_settings = settings_mod.get_settings
        # force reload
        if hasattr(get_settings, "cache_clear"):
            get_settings.cache_clear()

        monkeypatch.setattr(wi_ai_service, "_try_llm_plan", _fake_llm)

        result, legacy = await wi_ai_service.parse_interactive(
            db_session,
            text=data["source_text"],
            rule_set_code=rs_code,
            created_by="TEST",
        )
        assert len(result.plan.actions) == 2
        assert len(result.drafts) == 2
        assert result.drafts[0].engine_result["total_tmu"] == 6.0
        assert result.drafts[1].engine_result["total_tmu"] == 6.0
        assert result.drafts[1].cycle["frequency"] == 2
        assert "quantity_policy_review" in result.drafts[1].issues
        assert legacy["slots"]  # 相容欄位仍在
    finally:
        from ddm_v2 import settings as settings_mod

        monkeypatch.delenv("DDM_WI_AI_ENABLED", raising=False)
        if hasattr(settings_mod.get_settings, "cache_clear"):
            settings_mod.get_settings.cache_clear()
