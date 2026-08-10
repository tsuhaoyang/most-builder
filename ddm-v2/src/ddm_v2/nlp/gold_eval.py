"""WI AI gold-plan 評測 runner（L3-3）。

輸入：`tests/gold/wi_plans/*.json`（IE 核准案例；目前以 A5 fixture 作種子）。
pipeline：gold plan → SlotLinker → compile → engine_gate → routing（無 LLM）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ddm_v2.most_compiler.compile import allow_lists_from_rule_set, compile_plan
from ddm_v2.most_compiler.engine_gate import apply_engine_gate
from ddm_v2.most_engine.providers import build_from_seed_v2
from ddm_v2.nlp.contracts import WorkInstructionPlan
from ddm_v2.nlp.linking import SlotLinker
from ddm_v2.nlp.routing import compute_routing

GOLD_SCHEMA_VERSION = "wi-gold-v1"


@dataclass
class CycleCheck:
    action_id: str
    ok: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class GoldCaseResult:
    case_id: str
    ok: bool
    action_count: int
    routing_status: str
    routing_reasons: list[str]
    cycle_checks: list[CycleCheck]
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def default_gold_dir() -> Path:
    # src/ddm_v2/nlp/gold_eval.py → parents[3] = ddm-v2/
    return Path(__file__).resolve().parents[3] / "tests" / "gold" / "wi_plans"


def load_gold_cases(gold_dir: Path | None = None) -> list[tuple[Path, dict]]:
    root = gold_dir or default_gold_dir()
    files = sorted(root.glob("*.json"))
    out: list[tuple[Path, dict]] = []
    for path in files:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        out.append((path, data))
    return out


def _check_cycle(draft: Any, exp: dict) -> CycleCheck:
    errors: list[str] = []
    aid = exp.get("action_id") or getattr(draft, "action_id", "?")
    if draft.action_id != exp["action_id"]:
        errors.append(f"action_id {draft.action_id!r} != {exp['action_id']!r}")
    if draft.complete is not exp["complete"]:
        errors.append(f"complete {draft.complete} != {exp['complete']}")
    if exp.get("cycle") is None and exp.get("complete") is False and not exp.get("seq"):
        if draft.cycle is not None:
            errors.append("expected cycle=null")
    if "issues_contain" in exp:
        for issue in exp["issues_contain"]:
            if issue not in (draft.issues or []):
                errors.append(f"missing issue {issue!r}")
    if exp.get("complete"):
        if draft.cycle is None:
            errors.append("expected cycle")
        else:
            if draft.cycle.get("seq") != exp.get("seq"):
                errors.append(f"seq {draft.cycle.get('seq')!r} != {exp.get('seq')!r}")
            if draft.engine_result is None:
                errors.append("expected engine_result")
            else:
                if draft.engine_result.get("total_tmu") != exp.get("total_tmu"):
                    errors.append(
                        f"tmu {draft.engine_result.get('total_tmu')} != {exp.get('total_tmu')}"
                    )
                if exp.get("tech_line") and draft.engine_result.get("tech_line") != exp["tech_line"]:
                    errors.append("tech_line mismatch")
            if "g_code" in exp and draft.cycle.get("g2", {}).get("g_code") != exp["g_code"]:
                errors.append("g_code mismatch")
            if "p_base_code" in exp and draft.cycle.get("p5", {}).get("p_base_code") != exp["p_base_code"]:
                errors.append("p_base_code mismatch")
            if "x_code" in exp and draft.cycle.get("x4", {}).get("x_code") != exp["x_code"]:
                errors.append("x_code mismatch")
            if "i_code" in exp and draft.cycle.get("i5", {}).get("i_code") != exp["i_code"]:
                errors.append("i_code mismatch")
            if "m_verb" in exp:
                comps = (draft.cycle.get("m3") or {}).get("m_components") or []
                verb = comps[0].get("verb_code") if comps else None
                if verb != exp["m_verb"]:
                    errors.append(f"m_verb {verb!r} != {exp['m_verb']!r}")
            if "distance_cm" in exp:
                comps = (draft.cycle.get("m3") or {}).get("m_components") or []
                dist = comps[0].get("distance_cm") if comps else None
                if dist != exp["distance_cm"]:
                    errors.append(f"distance_cm {dist} != {exp['distance_cm']}")
            if "frequency" in exp and draft.cycle.get("frequency") != exp["frequency"]:
                errors.append("frequency mismatch")
    return CycleCheck(action_id=str(aid), ok=not errors, errors=errors)


async def evaluate_gold_case(data: dict) -> GoldCaseResult:
    case_id = str(data.get("id") or "unknown")
    errors: list[str] = []
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

    expected = data.get("expected_cycles") or []
    if len(drafts) != len(expected):
        errors.append(f"draft count {len(drafts)} != expected {len(expected)}")

    checks: list[CycleCheck] = []
    for draft, exp in zip(drafts, expected):
        checks.append(_check_cycle(draft, exp))

    # optional top-level expectations
    exp_status = (data.get("expected") or {}).get("routing_status")
    if exp_status and status != exp_status:
        errors.append(f"routing_status {status!r} != {exp_status!r}")
    exp_actions = (data.get("expected") or {}).get("action_count")
    if exp_actions is not None and len(plan.actions) != exp_actions:
        errors.append(f"action_count {len(plan.actions)} != {exp_actions}")

    # boundary metrics (spec §14.3)
    metrics: dict[str, Any] = {
        "action_count": len(plan.actions),
        "complete_drafts": sum(1 for d in drafts if d.complete),
        "engine_ok": sum(1 for d in drafts if d.engine_result is not None),
        "routing_status": status,
    }
    if data.get("boundary"):
        metrics["boundary"] = data["boundary"]
        if data["boundary"] == "acquire_only_no_invented_steps":
            if len(plan.actions) != 1 or plan.actions[0].action_type != "acquire":
                errors.append("boundary acquire_only violated")

    ok = not errors and all(c.ok for c in checks)
    for c in checks:
        errors.extend(c.errors)

    return GoldCaseResult(
        case_id=case_id,
        ok=ok,
        action_count=len(plan.actions),
        routing_status=status,
        routing_reasons=list(reasons),
        cycle_checks=checks,
        errors=errors,
        metrics=metrics,
    )


async def evaluate_all(gold_dir: Path | None = None) -> list[GoldCaseResult]:
    results: list[GoldCaseResult] = []
    for _path, data in load_gold_cases(gold_dir):
        results.append(await evaluate_gold_case(data))
    return results
