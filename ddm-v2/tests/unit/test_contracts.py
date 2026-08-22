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
    from ddm_v2.nlp.contracts import sanitize_planner_output

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
    sanitized, reasons = sanitize_planner_output(out, normalized_text="拿起dimm")
    assert any(r.startswith("planner_invented_action") for r in reasons)
    assert sanitized.actions == []


def test_tool_state_downgrades_bad_ref():
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "鎖附鎖附"
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
                evidence=[EvidenceSpan(start=2, end=4, text="鎖附")],
            ),
        ],
    )
    sanitized, reasons = sanitize_planner_output(bad, normalized_text=norm)
    assert any("tool_state_violation" in r for r in reasons)
    assert sanitized.actions[1].roles["tool_ref"].status == "missing"
    assert validate_planner_output(sanitized, normalized_text=norm) == []


# ── evidence offset 修復（fail-closed）─────────────────────────────────────
#
# 模型會抄對原文、算錯位置（prompts/plan_v1.py 的 few-shot 自己就有 3/4 個
# span offset 是錯的、其中 2 個越界）。`text` 可唯一定位時 offset 是可推導的，
# 推得出來就不該讓整筆計畫失敗；推不出來（找不到／多處）就維持原樣讓
# validate 拒絕——不猜。


def _one_action(evidence: list[EvidenceSpan], **kw) -> PlannerOutput:
    return PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                evidence=evidence,
                **kw,
            )
        ],
    )


def test_evidence_offset_repaired_when_text_unique():
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    # few-shot 教出來的典型錯誤：text 抄對、end 多算 2 且越界
    out = _one_action([EvidenceSpan(start=7, end=18, text="依圖示鎖附兩顆螺絲")])
    assert validate_planner_output(out, normalized_text=norm)  # 修復前：拒絕

    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    ev = sanitized.actions[0].evidence[0]
    assert (ev.start, ev.end) == (7, 16)
    assert norm[ev.start:ev.end] == ev.text
    assert validate_planner_output(sanitized, normalized_text=norm) == []
    assert any(r.startswith("evidence_offset_repaired:a1:") for r in reasons)


def test_evidence_offset_repair_handles_in_range_mismatch():
    """offset 在範圍內但指到別的內容（evidence_text_mismatch）也是同一條規則修。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm後插入插槽"
    out = _one_action([EvidenceSpan(start=0, end=4, text="插入插槽")])
    assert "evidence_text_mismatch:a1" in validate_planner_output(out, normalized_text=norm)

    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert (sanitized.actions[0].evidence[0].start, sanitized.actions[0].evidence[0].end) == (7, 11)
    assert validate_planner_output(sanitized, normalized_text=norm) == []
    assert any(r.startswith("evidence_offset_repaired") for r in reasons)


def test_correct_offset_is_never_touched_even_if_text_repeats():
    """已自證正確的 offset 不動——即使 text 在原文出現多次也不得「修」去別處。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "鎖附鎖附"
    out = _one_action([EvidenceSpan(start=2, end=4, text="鎖附")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert (sanitized.actions[0].evidence[0].start, sanitized.actions[0].evidence[0].end) == (2, 4)
    assert not any(r.startswith("evidence_") for r in reasons)


def test_evidence_text_not_found_stays_rejected():
    """模型改寫/幻覺出原文沒有的 text → 不猜，維持原 offset 讓 validate 拒絕。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = _one_action([EvidenceSpan(start=0, end=99, text="拿起記憶體模組")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert (sanitized.actions[0].evidence[0].start, sanitized.actions[0].evidence[0].end) == (0, 99)
    assert "evidence_text_not_found:a1" in reasons
    assert validate_planner_output(sanitized, normalized_text=norm)


def test_evidence_text_ambiguous_stays_rejected():
    """text 出現多次無從判斷指哪一處 → fail-closed，不挑第一個。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "鎖附鎖附"
    out = _one_action([EvidenceSpan(start=1, end=3, text="鎖附")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert (sanitized.actions[0].evidence[0].start, sanitized.actions[0].evidence[0].end) == (1, 3)
    assert "evidence_text_ambiguous:a1:2" in reasons
    assert "evidence_text_mismatch:a1" in validate_planner_output(sanitized, normalized_text=norm)


def test_evidence_ambiguity_counts_overlapping_occurrences():
    """重疊出現也算歧義（str.count 只算非重疊，會誤判成唯一而亂修）。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "aaa"
    out = _one_action([EvidenceSpan(start=0, end=3, text="aa")])
    _sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert "evidence_text_ambiguous:a1:2" in reasons


def test_evidence_empty_text_is_not_repaired():
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = _one_action([EvidenceSpan(start=0, end=2, text="")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert "evidence_empty_text:a1" in reasons
    assert validate_planner_output(sanitized, normalized_text=norm)


def test_repair_reasons_do_not_leak_into_unresolved():
    """offset 診斷不是語意缺口：混進 unresolved 會讓每筆被修過的計畫都被擋 auto
    （routing._eligible_auto 見 unresolved 非空即拒 auto）。語意類 reasons 照舊併入。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    out = _one_action([EvidenceSpan(start=7, end=18, text="依圖示鎖附兩顆螺絲")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert any(r.startswith("evidence_offset_repaired") for r in reasons)
    assert sanitized.unresolved == []

    invented = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1", action_type="acquire", sequence_order=1, evidence=[]
            )
        ],
    )
    sanitized2, _ = sanitize_planner_output(invented, normalized_text=norm)
    assert "planner_invented_action" in sanitized2.unresolved


def test_repair_does_not_change_drop_or_downgrade_behaviour():
    """修復不得動到 §7.5 既有防線：無 evidence 仍剔除、非法 tool_ref 仍降 missing。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="process",
                sequence_order=1,
                # 越界但可修：修完仍不影響它「有 evidence」不被剔除
                roles={"tool_ref": RoleValue(status="inferred", action_ref="a2")},
                evidence=[EvidenceSpan(start=7, end=18, text="依圖示鎖附兩顆螺絲")],
            ),
            PlannedAction(
                action_id="a2", action_type="acquire", sequence_order=2, evidence=[]
            ),
        ],
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert any(r.startswith("planner_invented_action:a2") for r in reasons)
    assert any(r.startswith("tool_state_violation:a1") for r in reasons)
    assert any(r.startswith("evidence_offset_repaired:a1") for r in reasons)
    assert len(sanitized.actions) == 1
    assert sanitized.actions[0].roles["tool_ref"].status == "missing"
    assert (sanitized.actions[0].evidence[0].start, sanitized.actions[0].evidence[0].end) == (7, 16)
