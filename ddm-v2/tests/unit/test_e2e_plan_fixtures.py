"""附錄 A5：5 筆 e2e plan fixtures → link → compile → engine（無 DB）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddm_v2.most_compiler.compile import allow_lists_from_rule_set, compile_plan
from ddm_v2.most_compiler.engine_gate import apply_engine_gate
from ddm_v2.most_engine.providers import build_from_seed_v2
from ddm_v2.nlp.contracts import WorkInstructionPlan
from ddm_v2.nlp.linking import SlotLinker
from ddm_v2.nlp.routing import compute_routing

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "integration" / "fixtures" / "e2e_plans"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fname",
    [
        "01_acquire_dimm.json",
        "02_screwdriver_screw_x2.json",
        "03_push_fixture_30cm.json",
        "04_scan_and_confirm.json",
        "05_composite_unknown.json",
    ],
)
async def test_e2e_fixture_pipeline(fname: str):
    data = _load(fname)
    plan = WorkInstructionPlan.model_validate(data["plan"])
    linker = SlotLinker(data.get("synthetic_synonyms") or [])
    candidates = await linker.link(plan)
    rs = build_from_seed_v2()
    drafts = compile_plan(
        plan,
        candidates,
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=allow_lists_from_rule_set(rs),
    )
    drafts = apply_engine_gate(drafts, rs)
    status, reasons = compute_routing(plan, candidates, drafts, auto_enabled=False)

    expected = data["expected_cycles"]
    assert len(drafts) == len(expected)
    for draft, exp in zip(drafts, expected):
        assert draft.action_id == exp["action_id"]
        assert draft.complete is exp["complete"]
        if exp.get("cycle") is None and exp.get("complete") is False and not exp.get("seq"):
            assert draft.cycle is None
        if "issues_contain" in exp:
            for issue in exp["issues_contain"]:
                assert issue in draft.issues
        if not exp.get("complete"):
            continue
        assert draft.cycle is not None
        assert draft.cycle["seq"] == exp["seq"]
        assert draft.engine_result is not None
        assert draft.engine_result["total_tmu"] == exp["total_tmu"]
        assert draft.engine_result["tech_line"] == exp["tech_line"]
        if "g_code" in exp:
            assert draft.cycle["g2"]["g_code"] == exp["g_code"]
        if "p_base_code" in exp:
            assert draft.cycle["p5"]["p_base_code"] == exp["p_base_code"]
        if "x_code" in exp:
            assert draft.cycle["x4"]["x_code"] == exp["x_code"]
        if "i_code" in exp:
            assert draft.cycle["i5"]["i_code"] == exp["i_code"]
        if "m_verb" in exp:
            comps = draft.cycle["m3"]["m_components"]
            assert comps and comps[0]["verb_code"] == exp["m_verb"]
        if "distance_cm" in exp:
            assert draft.cycle["m3"]["m_components"][0]["distance_cm"] == exp["distance_cm"]
        if "frequency" in exp:
            assert draft.cycle["frequency"] == exp["frequency"]

    if fname.startswith("05"):
        assert status == "abstain"
    else:
        assert status in {"review", "auto"}
