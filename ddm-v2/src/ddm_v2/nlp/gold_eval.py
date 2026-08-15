"""WI AI gold **compile 段**評測 runner（L3-3）。

輸入：`tests/gold/wi_plans/*.json`（IE 核准案例；目前以 A5 fixture 作種子）。
pipeline：gold plan → SlotLinker → compile → engine_gate → routing（無 LLM）。

注意：本段以 gold `plan` 為**輸入**，驗的是 compiler+engine；text→plan 的
planner 段（`docs/architecture/wi-ai-parser-system-spec.md` §14.4 的
plan action-count / boundary F1——另一份 implementation spec 的 §14.4 是別的章節，
引用需帶全檔名）在 `nlp/planner_eval.py`，兩段由 `scripts/wi_ai_eval.py` 並列輸出。
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
DEFAULT_RULE_SET_CODE = "MINIMOST_FACTORY_V2"

# 正式 gold 的 seed fixture 白名單（唯一出處）：`approved_by: "seed"` 的豁免
# （空殼守門、轉正欄位要求、報告核准計數）**只對這三個已知 A5 種子檔有效**。
# 「seed」不是任人填的萬用豁免字串——先前只認字串時，把任意案例標
# `approved_by: "seed"` 並刪 `plan_origin` 就能同時穿透空殼守門（P1-3）與
# 自我指涉排除（P0-1），實測可重現 0.98 的假指標。新增 seed fixture 需改這裡
# ＋對應守門測試（tests/unit/test_gold_draft_isolation.py）。
SEED_GOLD_IDS = frozenset(
    {
        "g01_acquire_dimm",
        "g02_screwdriver_screw_x2",
        "g05_composite_unknown",
    }
)


def is_seed_gold_case(data: dict) -> bool:
    """本案例是否為白名單內的 seed fixture（approved_by=seed 且 id 在名單上）。"""
    return data.get("approved_by") == "seed" and str(data.get("id")) in SEED_GOLD_IDS


def case_rule_set_code(data: dict) -> str:
    """gold/draft 檔內的 rule_set_code（頂層優先，其次 preannotation），缺省 V2。

    單一出處：`scripts/gold_harvest.py --recompile` 與本模組共用，兩邊不得各硬寫。
    """
    top = data.get("rule_set_code")
    pre = (data.get("preannotation") or {}).get("rule_set_code")
    return str(top or pre or DEFAULT_RULE_SET_CODE)


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
            if exp.get("expected_engine_rejected"):
                # 期望＝「complete 但引擎拒絕」（harvest 對 engine_result=None 的
                # complete cycle 寫的期望形狀）：驗「引擎仍拒絕」，不驗 TMU。
                # 引擎若改為接受，代表期望過時（規則變了）——照樣紅，不假綠。
                if draft.engine_result is not None:
                    errors.append(
                        "expected engine rejection (expected_engine_rejected) "
                        "but engine accepted"
                    )
            elif draft.engine_result is None:
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
        rule_set_code=case_rule_set_code(data),
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
