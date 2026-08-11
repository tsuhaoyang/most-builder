"""wi-plan-v1 契約：MOST-neutral 作業計畫與候選。

上游：docs/architecture/wi-ai-parser-system-spec.md §7
實作：docs/llm/wi-ai-parser-implementation-spec.md §5 / 附錄 A
規則：欄位只增不改（ADR-011）；LLM structured output 只產生 PlannerOutput。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "wi-plan-v1"
CONTRACT_VERSION = "wi-ai-v1"

ActionType = Literal[
    "acquire",
    "move_place",
    "controlled_move",
    "process",
    "inspect",
    "release_return",
    "composite_unknown",
]

RoleStatus = Literal["explicit", "inferred", "default", "explicit_unresolved", "missing"]

DependencyType = Literal["uses_tool", "tool_held_for", "same_object", "precedes"]

ROLE_KEYS = frozenset({
    "hand",
    "object",
    "tool",
    "tool_ref",
    "from_location",
    "destination",
    "distance",
    "quantity",
    "process_kind",
    "inspect_kind",
})

# 附錄 A6：前後端同源顯示檔位（非校準機率）
CONFIDENCE_BANDS = {"high": 0.9, "mid": 0.6}


class EvidenceSpan(BaseModel):
    """對 normalized_text 的字元 offset（半開區間 [start, end)）。"""

    start: int
    end: int
    text: str


class RoleValue(BaseModel):
    text: str | None = None
    value: float | int | None = None
    unit: str | None = None
    status: RoleStatus
    action_ref: str | None = None


class PlannedAction(BaseModel):
    action_id: str
    action_type: ActionType
    sequence_order: int
    roles: dict[str, RoleValue] = Field(default_factory=dict)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    notes: str | None = None


class ActionDependency(BaseModel):
    from_action: str
    to_action: str
    type: DependencyType


class SourceRef(BaseModel):
    kind: Literal["interactive", "import_row"]
    worksheet_id: str | None = None
    import_id: str | None = None
    import_row_index: int | None = None


class WorkInstructionPlan(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source_text: str
    normalized_text: str
    language: Literal["zh", "en", "mixed"] = "zh"
    source_ref: SourceRef
    actions: list[PlannedAction]
    dependencies: list[ActionDependency] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


CandidateSource = Literal[
    "template",
    "synonym_exact",
    "synonym_longest",
    "trgm",
    "embedding",
    "llm_rerank",
    "default",
]


class OptionCandidate(BaseModel):
    parameter: str
    option_code: str
    score: float
    source: CandidateSource
    rank: int


class SlotCandidateSet(BaseModel):
    action_id: str
    parameter: str
    field: str
    chosen: OptionCandidate | None
    top_k: list[OptionCandidate]
    needs_review: bool
    review_reason: str | None = None


RoutingStatus = Literal["auto", "review", "abstain", "invalid"]


class CycleDraft(BaseModel):
    action_id: str
    cycle: dict | None
    complete: bool
    engine_result: dict | None = None
    narrative: str | None = None
    issues: list[str] = Field(default_factory=list)


class ParseRunResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    run_id: str
    plan: WorkInstructionPlan
    slot_candidates: list[SlotCandidateSet]
    drafts: list[CycleDraft]
    routing_status: RoutingStatus
    routing_reasons: list[str]
    provenance: dict
    # R1：綁 worksheet 時的來源 revision（未綁為 null）
    source_revision: int | None = None


class PlannerOutput(BaseModel):
    """LLM structured output 子集（candidates/TMU/routing 一律不在其內）。"""

    language: Literal["zh", "en", "mixed"]
    actions: list[PlannedAction]
    dependencies: list[ActionDependency] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class ParseContext(BaseModel):
    rule_set_code: str
    station_hint: str | None = None
    available_tools: list[str] = Field(default_factory=list)
    available_locations: list[str] = Field(default_factory=list)
    previous_row_summary: str | None = None


def confidence_band(score: float | None, *, review_reason: str | None = None) -> str:
    """附錄 A6：高 / 中 / 低。"""
    if review_reason in {"engines_disagree", "no_candidate"} or score is None:
        return "低"
    if score >= CONFIDENCE_BANDS["high"]:
        return "高"
    if score >= CONFIDENCE_BANDS["mid"]:
        return "中"
    return "低"


def validate_planner_output(
    output: PlannerOutput,
    *,
    normalized_text: str,
) -> list[str]:
    """回傳 errors；空列表＝通過（§5.1 結構規則）。

    §7.5 語意防線由 ``sanitize_planner_output`` 先處理（剔除／降級），
    不應再以整筆失敗迫使 rule fallback。
    """
    errors: list[str] = []
    ids = [a.action_id for a in output.actions]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_action_id")
    orders = [a.sequence_order for a in output.actions]
    expected = list(range(1, len(output.actions) + 1))
    if sorted(orders) != expected or orders != expected:
        errors.append("sequence_order_not_contiguous")

    id_set = set(ids)
    for dep in output.dependencies:
        if dep.from_action not in id_set or dep.to_action not in id_set:
            errors.append(f"dependency_unknown_action:{dep.from_action}->{dep.to_action}")

    nlen = len(normalized_text)
    for action in output.actions:
        for key in action.roles:
            if key not in ROLE_KEYS:
                errors.append(f"unknown_role_key:{action.action_id}:{key}")
        for ev in action.evidence:
            if not (0 <= ev.start < ev.end <= nlen):
                errors.append(f"evidence_offset_oor:{action.action_id}")
                continue
            if normalized_text[ev.start:ev.end] != ev.text:
                errors.append(f"evidence_text_mismatch:{action.action_id}")
        for role_key, role in action.roles.items():
            if role.status == "explicit":
                if role.text is None and role.value is None:
                    errors.append(f"explicit_without_value:{action.action_id}:{role_key}")
                elif role.text is not None and not _role_covered_by_evidence(role.text, action.evidence):
                    errors.append(f"explicit_without_evidence:{action.action_id}:{role_key}")
            if role.status == "inferred" and not role.action_ref:
                errors.append(f"inferred_without_ref:{action.action_id}:{role_key}")
            if role.action_ref and role.action_ref not in id_set:
                errors.append(f"action_ref_unknown:{action.action_id}:{role_key}")
    return errors


def sanitize_planner_output(output: PlannerOutput) -> tuple[PlannerOutput, list[str]]:
    """§7.5：invented action 剔除；非法 tool_ref 降為 missing。回傳 (sanitized, reasons)。"""
    reasons: list[str] = []
    kept: list[PlannedAction] = []
    for action in output.actions:
        if action.action_type != "composite_unknown" and not action.evidence:
            reasons.append(f"planner_invented_action:{action.action_id}")
            continue
        roles = dict(action.roles)
        tool_ref = roles.get("tool_ref")
        if tool_ref is not None and tool_ref.action_ref:
            ref = next((a for a in output.actions if a.action_id == tool_ref.action_ref), None)
            ok = (
                ref is not None
                and ref.action_type == "acquire"
                and ref.sequence_order < action.sequence_order
            )
            if not ok:
                reasons.append(f"tool_state_violation:{action.action_id}")
                roles["tool_ref"] = RoleValue(status="missing")
        kept.append(action.model_copy(update={"roles": roles}))

    # resequence after drops
    renumbered: list[PlannedAction] = []
    id_map: dict[str, str] = {}
    for i, action in enumerate(kept, start=1):
        new_id = f"a{i}"
        id_map[action.action_id] = new_id
        roles = {}
        for k, v in action.roles.items():
            if v.action_ref and v.action_ref in id_map:
                roles[k] = v.model_copy(update={"action_ref": id_map[v.action_ref]})
            elif v.action_ref and v.action_ref not in id_map:
                # pointed at dropped action
                roles[k] = RoleValue(status="missing") if k == "tool_ref" else v
            else:
                roles[k] = v
        renumbered.append(
            action.model_copy(update={"action_id": new_id, "sequence_order": i, "roles": roles})
        )

    deps = []
    for d in output.dependencies:
        if d.from_action in id_map and d.to_action in id_map:
            deps.append(
                ActionDependency(
                    from_action=id_map[d.from_action],
                    to_action=id_map[d.to_action],
                    type=d.type,
                )
            )

    unresolved = list(output.unresolved)
    for r in reasons:
        key = r.split(":", 1)[0]
        if key not in unresolved:
            unresolved.append(key)

    sanitized = PlannerOutput(
        language=output.language,
        actions=renumbered,
        dependencies=deps,
        unresolved=unresolved,
    )
    return sanitized, reasons


def _role_covered_by_evidence(text: str, evidence: list[EvidenceSpan]) -> bool:
    return any(text in ev.text or ev.text in text for ev in evidence)
