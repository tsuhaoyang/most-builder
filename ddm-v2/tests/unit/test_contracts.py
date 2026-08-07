"""wi-plan-v1 契約與 confidence_band / validate_planner_output 單元測試（L0）。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ddm_v2.nlp.contracts import (
    SCHEMA_VERSION,
    ActionDependency,
    EvidenceSpan,
    PlannedAction,
    PlannerOutput,
    RoleValue,
    confidence_band,
    validate_planner_output,
)

pytestmark = pytest.mark.unit


def test_schema_version_constant():
    assert SCHEMA_VERSION == "wi-plan-v1"


def test_confidence_bands():
    assert confidence_band(0.95) == "高"
    assert confidence_band(0.7) == "中"
    assert confidence_band(0.5) == "低"
    assert confidence_band(0.99, review_reason="engines_disagree") == "低"
    assert confidence_band(None) == "低"


def test_planner_output_round_trip():
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={
                    "object": RoleValue(text="DIMM", status="explicit"),
                },
                evidence=[EvidenceSpan(start=0, end=6, text="拿起DIMM")],
            )
        ],
        dependencies=[],
        unresolved=["next_operation"],
    )
    dumped = out.model_dump()
    again = PlannerOutput.model_validate(dumped)
    assert again.actions[0].roles["object"].text == "DIMM"


def test_unknown_role_key_rejected_by_validator():
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={"widget": RoleValue(text="x", status="explicit")},
                evidence=[EvidenceSpan(start=0, end=1, text="x")],
            )
        ],
    )
    errs = validate_planner_output(out, normalized_text="x")
    assert any(e.startswith("unknown_role_key") for e in errs)


def test_evidence_offset_and_explicit_rules():
    norm = "拿起DIMM"
    good = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={"object": RoleValue(text="DIMM", status="explicit")},
                evidence=[EvidenceSpan(start=0, end=len(norm), text=norm)],
            )
        ],
    )
    assert validate_planner_output(good, normalized_text=norm) == []

    bad_offset = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={"object": RoleValue(text="DIMM", status="explicit")},
                evidence=[EvidenceSpan(start=0, end=99, text="x")],
            )
        ],
    )
    assert validate_planner_output(bad_offset, normalized_text=norm)


def test_dependency_must_reference_existing_actions():
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                evidence=[EvidenceSpan(start=0, end=1, text="a")],
            )
        ],
        dependencies=[ActionDependency(from_action="a1", to_action="a9", type="precedes")],
    )
    errs = validate_planner_output(out, normalized_text="a")
    assert any("dependency_unknown_action" in e for e in errs)


def test_action_type_enum_rejects_unknown():
    with pytest.raises(ValidationError):
        PlannedAction(
            action_id="a1",
            action_type="fly",  # type: ignore[arg-type]
            sequence_order=1,
        )


def test_no_invented_action_without_evidence():
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                evidence=[],
            )
        ],
    )
    errs = validate_planner_output(out, normalized_text="拿起DIMM")
    assert any(e.startswith("planner_invented_action") for e in errs)


def test_tool_state_must_point_to_prior_acquire():
    norm = "拿起起子鎖附"
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                evidence=[EvidenceSpan(start=0, end=4, text="拿起起子")],
            ),
            PlannedAction(
                action_id="a2",
                action_type="process",
                sequence_order=2,
                roles={"tool_ref": RoleValue(status="inferred", action_ref="a1")},
                evidence=[EvidenceSpan(start=4, end=6, text="鎖附")],
            ),
        ],
    )
    assert validate_planner_output(out, normalized_text=norm) == []

    bad = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="process",
                sequence_order=1,
                evidence=[EvidenceSpan(start=0, end=2, text="鎖附")],
            ),
            PlannedAction(
                action_id="a2",
                action_type="process",
                sequence_order=2,
                roles={"tool_ref": RoleValue(status="inferred", action_ref="a1")},
                evidence=[EvidenceSpan(start=0, end=2, text="鎖附")],
            ),
        ],
    )
    assert any("tool_state_violation" in e for e in validate_planner_output(bad, normalized_text="鎖附"))
