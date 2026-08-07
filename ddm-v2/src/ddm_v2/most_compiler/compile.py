"""compile_plan：WorkInstructionPlan + candidates → CycleDraft（無 TMU）。"""
from __future__ import annotations

from typing import Any, Iterable

from ddm_v2.most_compiler.intermediate import (
    StrictASlot,
    StrictBSlot,
    StrictCmDraft,
    StrictGmDraft,
    StrictGSlot,
    StrictISlot,
    StrictMComponent,
    StrictMSlot,
    StrictPSlot,
    StrictXSlot,
)
from ddm_v2.most_compiler.policies import (
    CORE_PARAM_BY_ACTION,
    SEQ_BY_ACTION,
    holding_inferred_reason,
    is_tool_held,
    resolve_frequency,
)
from ddm_v2.nlp.contracts import CycleDraft, PlannedAction, SlotCandidateSet, WorkInstructionPlan
from ddm_v2.nlp.quantities import extract_distances
from ddm_v2.schemas.v2.most import CycleIn


class CompileError(ValueError):
    """Bug 級：linking 回了不在 allow-list 的 option code（I3）。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _chosen(
    candidates: Iterable[SlotCandidateSet],
    *,
    action_id: str,
    parameter: str,
) -> str | None:
    for c in candidates:
        if c.action_id == action_id and c.parameter == parameter and c.chosen:
            return c.chosen.option_code
    return None


def _addon_codes(
    candidates: Iterable[SlotCandidateSet],
    *,
    action_id: str,
) -> list[str]:
    for c in candidates:
        if c.action_id == action_id and c.parameter == "P_ADDON" and c.chosen:
            return [c.chosen.option_code]
    return []


def _assert_allowed(parameter: str, code: str | None, allow: dict[str, set[str]]) -> None:
    if code is None:
        return
    pool = allow.get(parameter, set())
    if code not in pool:
        raise CompileError(
            "OPTION_NOT_IN_ALLOWLIST",
            f"{parameter} code {code!r} not in rule-set allow-list",
        )


def _role_distance_cm(action: PlannedAction, role_key: str) -> float | None:
    role = action.roles.get(role_key)
    if role is None:
        return None
    if role.unit and role.value is not None:
        # already preferably cm
        if role.unit in {"cm", "公分"}:
            return float(role.value)
        if role.unit in {"mm", "毫米"}:
            return float(role.value) * 0.1
    if role.value is not None and (role.unit is None or role.unit in {"cm", "公分"}):
        return float(role.value)
    if role.text:
        dists = extract_distances(role.text)
        if dists and dists[0].normalized_cm is not None:
            return float(dists[0].normalized_cm)
    return None


def _evidence_distance_cm(action: PlannedAction, plan: WorkInstructionPlan) -> float | None:
    for d in extract_distances(plan.normalized_text):
        if d.normalized_cm is None:
            continue
        # prefer distances overlapping evidence spans
        for ev in action.evidence:
            if not (d.end <= ev.start or d.start >= ev.end):
                return float(d.normalized_cm)
    dists = extract_distances(plan.normalized_text)
    if len(action.evidence) == 0 and dists:
        return float(dists[0].normalized_cm) if dists[0].normalized_cm is not None else None
    # single-action or sole distance in text
    if dists and dists[0].normalized_cm is not None:
        return float(dists[0].normalized_cm)
    return None


def _core_complete(action: PlannedAction, candidates: list[SlotCandidateSet]) -> tuple[bool, str | None]:
    if action.action_type == "composite_unknown":
        return False, "composite_unknown"
    core = CORE_PARAM_BY_ACTION.get(action.action_type)
    if core is None:
        return False, "missing_core"
    code = _chosen(candidates, action_id=action.action_id, parameter=core)
    if code:
        return True, None
    return False, f"missing_core_{core.lower()}"


def compile_plan(
    plan: WorkInstructionPlan,
    candidate_sets: list[SlotCandidateSet],
    *,
    rule_set_code: str,
    allow_lists: dict[str, set[str]],
) -> list[CycleDraft]:
    """確定性編譯。allow_lists keys: G,P,P_ADDON,M,X,I,B。"""
    drafts: list[CycleDraft] = []
    for action in sorted(plan.actions, key=lambda a: a.sequence_order):
        if action.action_type == "composite_unknown":
            drafts.append(
                CycleDraft(
                    action_id=action.action_id,
                    cycle=None,
                    complete=False,
                    issues=["composite_unknown"],
                )
            )
            continue

        complete, miss_reason = _core_complete(action, candidate_sets)
        freq, freq_reasons = resolve_frequency(action)
        issues: list[str] = []
        if miss_reason:
            issues.append(miss_reason)
        issues.extend(freq_reasons)

        seq = SEQ_BY_ACTION.get(action.action_type)
        if seq is None:
            drafts.append(
                CycleDraft(
                    action_id=action.action_id,
                    cycle=None,
                    complete=False,
                    issues=issues or ["unknown_action_type"],
                )
            )
            continue

        g_code = _chosen(candidate_sets, action_id=action.action_id, parameter="G")
        p_code = _chosen(candidate_sets, action_id=action.action_id, parameter="P")
        b_code = _chosen(candidate_sets, action_id=action.action_id, parameter="B")
        m_code = _chosen(candidate_sets, action_id=action.action_id, parameter="M")
        x_code = _chosen(candidate_sets, action_id=action.action_id, parameter="X")
        i_code = _chosen(candidate_sets, action_id=action.action_id, parameter="I")
        addons = _addon_codes(candidate_sets, action_id=action.action_id)

        # 已持有：G 留空（附錄 A2）
        if holding_inferred_reason(action, plan) or (
            is_tool_held(action, plan) and action.action_type != "acquire"
        ):
            g_code = None

        for param, code in (
            ("G", g_code),
            ("P", p_code),
            ("B", b_code),
            ("M", m_code),
            ("X", x_code),
            ("I", i_code),
        ):
            _assert_allowed(param, code, allow_lists)
        for ad in addons:
            _assert_allowed("P_ADDON", ad, allow_lists)

        cycle_dict: dict[str, Any]
        if seq == "GM":
            a0_cm = _role_distance_cm(action, "from_location") or (
                _evidence_distance_cm(action, plan) if action.action_type == "acquire" else None
            )
            a3_cm = _role_distance_cm(action, "distance") or (
                _evidence_distance_cm(action, plan)
                if action.action_type in {"move_place", "release_return"}
                else None
            )
            gm = StrictGmDraft(
                a0=StrictASlot(reach_cm=float(a0_cm or 0)),
                b1=StrictBSlot(b_code=b_code),
                g2=StrictGSlot(g_code=g_code),
                a3=StrictASlot(reach_cm=float(a3_cm or 0)),
                p5=StrictPSlot(p_base_code=p_code, p_addon_codes=addons),
                frequency=freq,
            )
            cycle_dict = gm.model_dump()
        else:
            dist = _role_distance_cm(action, "distance") or _evidence_distance_cm(action, plan)
            m_comps: list[StrictMComponent] = []
            if m_code or (dist and action.action_type == "controlled_move"):
                m_comps.append(
                    StrictMComponent(
                        verb_code=m_code,
                        distance_cm=float(dist or 0),
                    )
                )
            x_seconds = 0.0
            pk = action.roles.get("process_kind")
            if pk and pk.unit in {"s", "sec", "秒"} and pk.value is not None:
                x_seconds = float(pk.value)
            cm = StrictCmDraft(
                b1=StrictBSlot(b_code=b_code),
                g2=StrictGSlot(g_code=g_code),
                m3=StrictMSlot(m_components=m_comps),
                x4=StrictXSlot(x_code=x_code, x_seconds=x_seconds),
                i5=StrictISlot(i_code=i_code),
                frequency=freq,
            )
            cycle_dict = cm.model_dump()

        cycle_dict["rule_set_code"] = rule_set_code
        # Validate against CycleIn (forbid drift)
        cin = CycleIn.model_validate(cycle_dict)
        if action.action_type == "acquire" and "destination" not in action.roles:
            if "next_operation" not in issues:
                issues.append("next_operation")
        drafts.append(
            CycleDraft(
                action_id=action.action_id,
                cycle=cin.model_dump(mode="json"),
                complete=complete,
                issues=issues,
            )
        )
    return drafts


def allow_lists_from_rule_set(rs: Any) -> dict[str, set[str]]:
    """RuleSetData → compiler allow-lists。"""
    return {
        "G": set(getattr(rs, "g_actions", {}) or {}),
        "P": set(getattr(rs, "p_bases", {}) or {}),
        "P_ADDON": set(getattr(rs, "p_addons", {}) or {}),
        "M": set(getattr(rs, "m_verbs", {}) or {}),
        "X": set(getattr(rs, "x_options", {}) or {}),
        "I": set(getattr(rs, "i_index", {}) or {}),
        "B": set(getattr(rs, "b_index", {}) or {}),
    }
