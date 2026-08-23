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
    SourceRef,
    WorkInstructionPlan,
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


# ── D4：evidence 的 offset 由我方推導，不由模型報 ──────────────────────────
#
# 模型會抄對原文、算錯位置：worklog §8 量到 `evidence_offset_repaired` 在
# plan-v1.3 兩輪各觸發 62／63 次（55 案）——幾乎每一份輸出都要修。ADR-033 D4
# 因此把 offset 整個收回我方推導（`locate_evidence_spans`）：模型只給 `text`。
# 三條規則：唯一出現→直接定位；多次出現→依 sequence_order 由左至右單調指派
# （U-4 裁決「不會有倒裝」，故不掛假設旗標、不擋 auto）；找不到→剔除該 action。


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


def _action(aid: str, order: int, text: str, **kw) -> PlannedAction:
    return PlannedAction(
        action_id=aid,
        action_type="acquire",
        sequence_order=order,
        evidence=[EvidenceSpan(text=text, **kw)],
    )


def test_model_may_omit_offsets_entirely():
    """D4 的目標形狀：evidence 只有 `text`，start/end 缺席仍是合法契約。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = _one_action([EvidenceSpan(text="拿起dimm")])
    assert validate_planner_output(out, normalized_text=norm) == []

    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    ev = sanitized.actions[0].evidence[0]
    assert (ev.start, ev.end) == (0, len(norm))
    assert not any(r.startswith("evidence_") for r in reasons), (
        "模型沒給 offset 不是「修復」，不該記診斷"
    )


def test_wrong_offset_is_recomputed_from_text():
    """few-shot 教出來的典型錯誤：text 抄對、end 多算 2 且越界 → 推導成正解。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    out = _one_action([EvidenceSpan(start=7, end=18, text="依圖示鎖附兩顆螺絲")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    ev = sanitized.actions[0].evidence[0]
    assert (ev.start, ev.end) == (7, 16)
    assert norm[ev.start:ev.end] == ev.text
    assert validate_planner_output(sanitized, normalized_text=norm) == []
    assert any(r.startswith("evidence_offset_repaired:a1:") for r in reasons)


def test_in_range_mismatch_is_recomputed_too():
    """offset 在範圍內但指到別的內容 → 同一條規則，以 text 為準重算。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm後插入插槽"
    out = _one_action([EvidenceSpan(start=0, end=4, text="插入插槽")])
    assert "evidence_text_mismatch:a1" in validate_planner_output(out, normalized_text=norm)

    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    ev = sanitized.actions[0].evidence[0]
    assert (ev.start, ev.end) == (7, 11)
    assert validate_planner_output(sanitized, normalized_text=norm) == []
    assert any(r.startswith("evidence_offset_repaired") for r in reasons)


def test_model_offset_no_longer_wins_over_derivation():
    """D4 收回權威：模型自證一致的 offset **也**要重算。

    舊實作（`repair_evidence_offsets`）的第一分支是「offset 已正確就原樣不動」，
    於是「鎖附鎖附」裡模型說第二個、我方就用第二個。D4 之後座標只有一個來源：
    由左至右的推導。這條與 `test_multi_occurrence_assigned_left_to_right` 是
    同一條規則的兩面（單 action 版）。
    """
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "鎖附鎖附"
    out = _one_action([EvidenceSpan(start=2, end=4, text="鎖附")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    ev = sanitized.actions[0].evidence[0]
    assert (ev.start, ev.end) == (0, 2)
    assert any(r.startswith("evidence_offset_repaired:a1") for r in reasons)


def test_multi_occurrence_assigned_left_to_right():
    """D4 規則 2 的**探針**：同一片語出現兩次 → 依 sequence_order 由左至右指派。

    ⚠️ 這條在 gold 上是**空跑**（55 案的 evidence 全是整句單 span，不會重複），
    所以不能拿「gold 全綠」當它被執行過的證據——worklog §9 T-8 記著這個陷阱。
    這裡自建語料把它逼出來：兩個 action 的 evidence text 完全相同，唯一能區分
    它們的就是指派規則本身。
    """
    from ddm_v2.nlp.contracts import sanitize_planner_output

    phrase = "拿取螺絲放入治具"
    norm = f"{phrase},{phrase}"
    assert norm.count(phrase) == 2
    out = PlannerOutput(
        language="zh",
        actions=[_action("a1", 1, phrase), _action("a2", 2, phrase)],
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    spans = [(a.evidence[0].start, a.evidence[0].end) for a in sanitized.actions]
    assert spans == [(0, 8), (9, 17)], "第二個 action 必須拿到第二次出現的位置"
    assert all(norm[s:e] == phrase for s, e in spans)
    assert not any(r.startswith("evidence_") for r in reasons)


def test_multi_occurrence_assignment_ignores_model_supplied_order():
    """同上，但模型把兩個 span 都指到第一次出現——推導仍然單調、不重用位置。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    phrase = "拿取螺絲放入治具"
    norm = f"{phrase},{phrase}"
    out = PlannerOutput(
        language="zh",
        actions=[
            _action("a1", 1, phrase, start=0, end=8),
            _action("a2", 2, phrase, start=0, end=8),
        ],
    )
    sanitized, _reasons = sanitize_planner_output(out, normalized_text=norm)
    spans = [(a.evidence[0].start, a.evidence[0].end) for a in sanitized.actions]
    assert spans == [(0, 8), (9, 17)]


def test_assignment_follows_sequence_order_not_list_order():
    """指派依 `sequence_order`，不依 JSON 裡的排列順序。

    刻意把 `sequence_order=2` 的 action 排在 list 前面：位置若是照 list 順序發，
    前面那個會拿到左邊的 (0,2)。實際上 `sequence_order=1` 的那個才拿 (0,2)。
    （這種輸入走不到正式管線——`_parse_sanitize_validate` 會先以
    `sequence_order_not_contiguous` 整筆退回；這裡直接驗定位函式的規則。）
    """
    from ddm_v2.nlp.contracts import locate_evidence_spans

    phrase = "鎖附"
    norm = "鎖附鎖附"
    actions = [_action("a2", 2, phrase), _action("a1", 1, phrase)]
    located, unlocatable, _diag = locate_evidence_spans(actions, norm)
    assert unlocatable == set()
    assert [(located["a1"][0].start, located["a1"][0].end)] == [(0, 2)]
    assert [(located["a2"][0].start, located["a2"][0].end)] == [(2, 4)]


def test_occurrences_are_not_reused_and_exhaustion_drops_the_action():
    """位置用完就定位不到 → 該 action 剔除（不重用、不猜）。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    phrase = "鎖附"
    norm = "鎖附鎖附"
    out = PlannerOutput(
        language="zh",
        actions=[
            _action("a1", 1, phrase),
            _action("a2", 2, phrase),
            _action("a3", 3, phrase),
        ],
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert len(sanitized.actions) == 2
    assert any(r.startswith("planner_invented_action:a3") for r in reasons)


def test_evidence_text_not_found_drops_the_action():
    """模型改寫／幻覺出原文沒有的 text → D4 規則 3：剔除該 action，沿用
    `planner_invented_action` 語意；後綴留下**是哪一種**失敗。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = _one_action([EvidenceSpan(start=0, end=99, text="拿起記憶體模組")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert sanitized.actions == []
    assert "planner_invented_action:a1:evidence_text_not_found" in reasons
    assert "planner_invented_action" in sanitized.unresolved


def test_partially_locatable_action_is_dropped_whole():
    """一個 action 的多個 span 只要有一個定位不到，整個 action 剔除（fail-closed）。

    留著「一半是幻覺」的 action 等於讓 compiler 的 evidence 窗建立在半真的座標上。
    """
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm後插入插槽"
    out = _one_action(
        [EvidenceSpan(text="拿起dimm"), EvidenceSpan(text="插入主機板插槽")]
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert sanitized.actions == []
    assert any(r.startswith("planner_invented_action:a1") for r in reasons)


def test_dropped_action_does_not_consume_positions_for_later_actions():
    """被剔除的 action 不得佔住位置——一個幻覺不該連鎖打掉後面的 action。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    phrase = "鎖附"
    norm = "鎖附鎖附"
    out = PlannerOutput(
        language="zh",
        actions=[
            # a1 第一個 span 佔到 0，第二個 span 是幻覺 → 整個 a1 被剔除
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                evidence=[EvidenceSpan(text=phrase), EvidenceSpan(text="幻覺片語")],
            ),
            _action("a2", 2, phrase),
        ],
    )
    sanitized, _reasons = sanitize_planner_output(out, normalized_text=norm)
    assert len(sanitized.actions) == 1
    assert (sanitized.actions[0].evidence[0].start, sanitized.actions[0].evidence[0].end) == (
        0,
        2,
    ), "a2 應拿得到 a1 沒用成的第一個位置"


def test_evidence_empty_text_drops_the_action():
    """空 text 無從定位——不得靜默放行成一個沒有證據的 action。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = _one_action([EvidenceSpan(start=0, end=2, text="")])
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert sanitized.actions == []
    assert "planner_invented_action:a1:evidence_text_not_found" in reasons


def test_offset_diagnostics_do_not_leak_into_unresolved():
    """offset 診斷不是語意缺口：混進 unresolved 會讓每筆被推導過的計畫都被擋 auto
    （`routing._eligible_auto` 見 unresolved 非空即拒 auto）。語意類 reasons 照舊併入。"""
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


def test_derivation_does_not_change_drop_or_downgrade_behaviour():
    """推導不得動到 §7.5 既有防線：無 evidence 仍剔除、非法 tool_ref 仍降 missing。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="process",
                sequence_order=1,
                # 越界但可推導：推完仍不影響它「有 evidence」不被剔除
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


# ── D3：取代 `status` 的單一不變式 ─────────────────────────────────────────


def test_status_is_optional_and_not_validated():
    """`status` 不再向模型索取：整個省略是合法的，也不再有任何規則讀它。

    ADR-011 只增不改——欄位本身留著（既有 gold／`ai_parse_runs` 帶著它），
    只是沒有人再依它做判斷。
    """
    norm = "拿起dimm"
    out = _one_action(
        [EvidenceSpan(start=0, end=len(norm), text=norm)],
        roles={"object": RoleValue(text="dimm")},
    )
    assert out.actions[0].roles["object"].status is None
    assert validate_planner_output(out, normalized_text=norm) == []


def test_role_text_must_be_literal_substring_of_normalized_text():
    """D3 的單一不變式：role 的 `text` 必須是 `normalized_text` 的**字面**子字串。

    比舊的 `_role_covered_by_evidence` 嚴：那是**雙向**比對（`text in ev.text`
    或 `ev.text in text`），「role.text 是 evidence 的超集」可以夾帶原文沒有的
    內容通過（資安 S-2 的繞過 B）。這裡直接比對全句原文，沒有那個洞。
    """
    norm = "推動治具"
    out = _one_action(
        [EvidenceSpan(start=0, end=2, text="推動")],
        roles={"destination": RoleValue(text="推動治具至三號無塵室30公分")},
    )
    errs = validate_planner_output(out, normalized_text=norm)
    assert "role_text_not_in_source:a1:destination" in errs


def test_abolished_status_rules_are_gone():
    """D3 連帶廢止的四條規則不得再出現。

    `explicit_without_value`／`explicit_without_evidence`／`inferred_without_ref`／
    `action_ref_unknown` 驗的都是模型的**自我宣告**；宣告不是事實。
    這裡一次擺出四種舊規則會抓、新契約放行的形狀。
    """
    norm = "推動治具"
    shapes = [
        # explicit 卻沒有 text 也沒有 value（舊：explicit_without_value）
        {"object": RoleValue(status="explicit")},
        # explicit 且 text 在原文裡，但沒有 evidence 覆蓋它（舊：explicit_without_evidence）
        {"object": RoleValue(text="治具", status="explicit")},
        # inferred 沒有 action_ref（舊：inferred_without_ref）
        {"object": RoleValue(text="治具", status="inferred")},
        # action_ref 指向不存在的 action（舊：action_ref_unknown）
        {"tool_ref": RoleValue(status="inferred", action_ref="a9")},
    ]
    for roles in shapes:
        out = _one_action([EvidenceSpan(start=0, end=2, text="推動")], roles=roles)
        assert validate_planner_output(out, normalized_text=norm) == [], roles


def test_role_text_not_in_source_is_stripped_not_fatal():
    """不變式違反在 adapter 邊界**逐項剝除**，不讓整份切分作廢（D6）。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "推動治具"
    out = _one_action(
        [EvidenceSpan(start=0, end=2, text="推動")],
        roles={
            "object": RoleValue(text="治具"),
            "destination": RoleValue(text="三號無塵室"),
        },
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert len(sanitized.actions) == 1, "剝一個角色不得賠掉整個 action"
    assert set(sanitized.actions[0].roles) == {"object"}
    assert "role_text_not_in_source:a1:destination" in reasons
    assert "role_text_not_in_source" in sanitized.unresolved
    assert validate_planner_output(sanitized, normalized_text=norm) == []


def test_role_text_not_in_source_keeps_the_structural_reference():
    """`tool_ref` 帶了幻覺片語 → 只剝 `text`，保留 `action_ref`。

    不變式管的是**片語**，`action_ref` 是結構參照（`is_tool_held` 讓 G 歸零，
    是真實 TMU 效果，D5）——把它一起丟掉是無關的附帶損害。
    """
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿取電動起子,鎖附螺絲"
    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                evidence=[EvidenceSpan(text="拿取電動起子")],
            ),
            PlannedAction(
                action_id="a2",
                action_type="process",
                sequence_order=2,
                roles={"tool_ref": RoleValue(text="氣動起子", action_ref="a1")},
                evidence=[EvidenceSpan(text="鎖附螺絲")],
            ),
        ],
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    tool_ref = sanitized.actions[1].roles["tool_ref"]
    assert tool_ref.text is None
    assert tool_ref.action_ref == "a1"
    assert "role_text_not_in_source:a2:tool_ref" in reasons


# ── D1（P1 的剝除半段）：數值不由模型產生 ──────────────────────────────────


def test_role_numeric_is_stripped_at_the_adapter_boundary():
    """`value`／`unit` 一律剝除並記名——距離／數量／秒數收窄後不由 LLM 產生。

    這正是資安 S-2 的病灶：「推動治具450mm至定位」＋模型 `value=450 unit="cm"`
    ＝真值的 10 倍，而 role 值優先於句面 regex。剝掉之後那條競爭來源不存在。
    """
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "推動治具"
    out = _one_action(
        [EvidenceSpan(start=0, end=2, text="推動")],
        roles={"distance": RoleValue(value=450, unit="cm", status="explicit")},
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    role = sanitized.actions[0].roles["distance"]
    assert (role.value, role.unit) == (None, None)
    assert "role_numeric_stripped:a1:distance" in reasons
    assert "role_numeric_stripped" in sanitized.unresolved


def test_role_numeric_strip_keeps_the_phrase():
    """剝的是數值，不是角色——`text` 仍然是 linking 要用的查詢字串。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "清潔治具6秒"
    out = _one_action(
        [EvidenceSpan(start=0, end=len(norm), text=norm)],
        roles={"process_kind": RoleValue(text="清潔", value=6, unit="秒")},
    )
    sanitized, _ = sanitize_planner_output(out, normalized_text=norm)
    role = sanitized.actions[0].roles["process_kind"]
    assert role.text == "清潔"
    assert (role.value, role.unit) == (None, None)


# ── D6：未知角色鍵改為剝除 ────────────────────────────────────────────────


def test_unknown_role_key_is_dropped_not_fatal():
    """自創角色鍵（實測最大宗：`object_ref`／`hand_ref`）→ 剝除並記名。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = _one_action(
        [EvidenceSpan(start=0, end=len(norm), text=norm)],
        roles={
            "object": RoleValue(text="dimm"),
            "object_ref": RoleValue(action_ref="a1"),
        },
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert set(sanitized.actions[0].roles) == {"object"}
    assert "role_key_dropped:a1:object_ref" in reasons
    assert validate_planner_output(sanitized, normalized_text=norm) == []


def test_return_to_is_a_contract_role_key():
    """`return_to`（＝A6「返回若有」）已進契約白名單（ADR-033 D2／spec §5.2.2 P1）。

    ⚠️ 今天**沒有任何產生者**：prompt 不索取（P2）、compiler 沒有分支（P3）。
    這條只釘住「契約已經容得下它」，不代表管線接得起來。
    """
    from ddm_v2.nlp.contracts import ROLE_KEYS, sanitize_planner_output

    assert "return_to" in ROLE_KEYS
    norm = "拿起dimm後放回料盒"
    out = _one_action(
        [EvidenceSpan(text=norm)], roles={"return_to": RoleValue(text="料盒")}
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert "return_to" in sanitized.actions[0].roles
    assert not any(r.startswith("role_key_dropped") for r in reasons)


# ── D5：dependency 選用且非致命 ───────────────────────────────────────────


def test_illegal_dependency_type_is_dropped_before_pydantic():
    """型別不合法的 dependency 一律丟棄並記名，**不得**讓整份輸出失敗。

    為什麼必須在 `model_validate` 之前：`ActionDependency.type` 是 Literal，
    模型自創一個 type（實測 `same_hand`）會讓整份 JSON 在 pydantic 就炸掉——
    `g13` 就是這樣被打掉的。
    """
    from ddm_v2.nlp.contracts import prepare_planner_payload

    payload = {
        "language": "zh",
        "actions": [],
        "dependencies": [
            {"from_action": "a1", "to_action": "a2", "type": "same_hand"},
            {"from_action": "a1", "to_action": "a2", "type": "tool_held_for"},
        ],
    }
    cleaned, reasons = prepare_planner_payload(payload)
    assert [d["type"] for d in cleaned["dependencies"]] == ["tool_held_for"]
    assert any(r.startswith("dependency_dropped:0:illegal_type=") for r in reasons)
    # 清乾淨之後 pydantic 收得下（原始 payload 收不下）
    PlannerOutput.model_validate(cleaned)
    with pytest.raises(ValidationError):
        PlannerOutput.model_validate(payload)


def test_malformed_dependency_shapes_are_dropped():
    from ddm_v2.nlp.contracts import prepare_planner_payload

    payload = {
        "language": "zh",
        "actions": [],
        "dependencies": [
            "not-an-object",
            {"from_action": "a1", "type": "uses_tool"},
            {"from_action": "a1", "to_action": 3, "type": "uses_tool"},
        ],
    }
    cleaned, reasons = prepare_planner_payload(payload)
    assert cleaned["dependencies"] == []
    assert len(reasons) == 3
    assert all(r.startswith("dependency_dropped:") for r in reasons)


def test_legal_dependencies_pass_through_untouched():
    """負向控制：合法 payload 不得被改寫，也不得憑空生出 reason。"""
    from ddm_v2.nlp.contracts import prepare_planner_payload

    payload = {
        "language": "zh",
        "actions": [],
        "dependencies": [{"from_action": "a1", "to_action": "a2", "type": "precedes"}],
    }
    cleaned, reasons = prepare_planner_payload(payload)
    assert cleaned is payload
    assert reasons == []


def test_dependency_with_dropped_endpoint_is_recorded():
    """端點被剔除的 dependency 一樣要留名——原本是靜默丟棄。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = PlannerOutput(
        language="zh",
        actions=[
            _action("a1", 1, "拿起dimm"),
            # 無 evidence → 被剔除，指向它的 dependency 也保不住
            PlannedAction(
                action_id="a2", action_type="acquire", sequence_order=2, evidence=[]
            ),
        ],
        dependencies=[
            ActionDependency(from_action="a1", to_action="a2", type="same_object")
        ],
    )
    sanitized, reasons = sanitize_planner_output(out, normalized_text=norm)
    assert sanitized.dependencies == []
    assert any(r.startswith("dependency_dropped:a1->a2") for r in reasons)
    assert "dependency_dropped" in sanitized.unresolved


def test_carried_reasons_reach_unresolved():
    """`model_validate` 之前就剝掉的項目也要進 unresolved，否則擋不住 auto。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    out = PlannerOutput(language="zh", actions=[_action("a1", 1, norm)])
    sanitized, reasons = sanitize_planner_output(
        out,
        normalized_text=norm,
        carried_reasons=["dependency_dropped:0:illegal_type='same_hand'"],
    )
    assert "dependency_dropped" in sanitized.unresolved
    assert any(r.startswith("dependency_dropped:0") for r in reasons)


# ── ADR-011 相容性：放寬不得打破既有資料 ──────────────────────────────────


def _gold_plan_payloads() -> list[tuple[str, dict]]:
    import json
    from pathlib import Path

    gold_dir = Path(__file__).resolve().parents[1] / "gold" / "wi_plans"
    out = []
    for path in sorted(gold_dir.glob("g*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        plan = data.get("plan") or {}
        out.append((data["id"], plan))
    return out


def test_existing_gold_plans_still_validate_as_planner_output():
    """55 案 gold（帶 `status`、帶 `value`／`unit`、帶 offset）必須照常解析。

    ADR-011：本次契約變更全部是「必填→選填」的放寬與新增，沒有欄位被刪除、
    沒有列舉被收窄——既有 `ai_parse_runs.plan` JSONB 與 gold 語料都得原樣讀得回來。
    """
    payloads = _gold_plan_payloads()
    assert len(payloads) >= 55, f"gold 語料只找到 {len(payloads)} 案"
    for gid, plan in payloads:
        PlannerOutput.model_validate(
            {
                "language": plan.get("language", "zh"),
                "actions": plan.get("actions") or [],
                "dependencies": plan.get("dependencies") or [],
                "unresolved": plan.get("unresolved") or [],
            }
        ), gid
        WorkInstructionPlan.model_validate(plan)


def test_existing_gold_role_status_values_survive_round_trip():
    """gold 帶的 `status` 值（explicit／inferred）不得在放寬後掉字。"""
    seen = set()
    for _gid, plan in _gold_plan_payloads():
        for action in plan.get("actions") or []:
            for key, role in (action.get("roles") or {}).items():
                parsed = RoleValue.model_validate(role)
                assert parsed.status == role.get("status"), key
                if parsed.status:
                    seen.add(parsed.status)
    assert seen, "gold 一個 status 都沒有＝這條守衛在空跑"


def test_sanitized_evidence_always_carries_concrete_offsets():
    """把 optional offset 與**沒有動過的** `most_compiler` 之間的橋釘住。

    `EvidenceSpan.start`／`end` 因 D4 改為選填，而 `most_compiler.policies` 的
    evidence 窗（`_overlaps_evidence`／`_window_text`）直接讀這兩個欄位、
    對 None 會炸。保證來自 sanitize：定位不到的 action 一律剔除，所以留下來的
    span 恆為具體座標。這條紅了就代表 compiler 會收到 None（P1 明令不得改 compiler）。
    """
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿取電動起子,鎖附螺絲"
    out = PlannerOutput(
        language="zh",
        actions=[
            _action("a1", 1, "拿取電動起子"),
            PlannedAction(
                action_id="a2",
                action_type="process",
                sequence_order=2,
                evidence=[EvidenceSpan(text="鎖附螺絲"), EvidenceSpan(text="鎖附")],
            ),
            PlannedAction(
                action_id="a3",
                action_type="composite_unknown",
                sequence_order=3,
                evidence=[],
            ),
        ],
    )
    sanitized, _reasons = sanitize_planner_output(out, normalized_text=norm)
    spans = [ev for a in sanitized.actions for ev in a.evidence]
    assert spans, "這條守衛不得空跑"
    for ev in spans:
        assert isinstance(ev.start, int) and isinstance(ev.end, int)
        assert norm[ev.start:ev.end] == ev.text


# ── 觀測旁通道：被剝除的值（ADR-033 P1 觀察期補測）────────────────────────
#
# 為什麼需要：P1 之後「有問題的輸出」不再硬失敗而是降級，於是
# `planner_raw_rejected`（只在硬失敗時留存）失去對象——觀察期量到
# `role_text_not_in_source` 4 次卻查不出**被剝掉的字是什麼**，「模型幻覺」與
# 「不變式過嚴、誤殺合法改寫」因此分不開（T-16）。
#
# 硬要求（下面 `test_stripped_values_never_reach_unresolved_or_routing` 守）：
# 被剝的值是**模型可控字串**，只准走 observer 旁通道進評測報告，
# **不得**進 reasons／`unresolved`／`routing_reasons`——那條路會落 DB 並回 API。

_HALLUCINATION = "記憶體模組"


def _degrading_output(norm: str) -> PlannerOutput:
    """一次觸發四種剝除的輸出（幻覺片語／數值／自創鍵／幻覺 evidence）。"""
    return PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={
                    "object": RoleValue(text=_HALLUCINATION),
                    "distance": RoleValue(value=450, unit="cm"),
                    "object_ref": RoleValue(text="治具", action_ref="a1"),
                },
                evidence=[EvidenceSpan(text=norm)],
            )
        ],
    )


def test_details_capture_the_stripped_role_text():
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    details: list = []
    sanitize_planner_output(
        _degrading_output(norm), normalized_text=norm, details=details
    )
    hit = [d for d in details if d.reason == "role_text_not_in_source"]
    assert len(hit) == 1
    assert (hit[0].action_id, hit[0].role_key, hit[0].text) == ("a1", "object", _HALLUCINATION)


def test_details_capture_the_stripped_numeric():
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    details: list = []
    sanitize_planner_output(
        _degrading_output(norm), normalized_text=norm, details=details
    )
    hit = [d for d in details if d.reason == "role_numeric_stripped"]
    assert len(hit) == 1
    assert (hit[0].role_key, hit[0].value, hit[0].unit) == ("distance", 450, "cm")


def test_details_capture_the_dropped_role_key_and_its_content():
    """自創鍵不只要記「鍵名」，還要記**它底下放了什麼**——否則看不出模型想表達什麼。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    details: list = []
    sanitize_planner_output(
        _degrading_output(norm), normalized_text=norm, details=details
    )
    hit = [d for d in details if d.reason == "role_key_dropped"]
    assert len(hit) == 1
    assert (hit[0].role_key, hit[0].text) == ("object_ref", "治具")


def test_details_capture_the_hallucinated_evidence_text():
    """evidence 定位不到時被剔除的是整個 action——留下模型寫的那串字才答得出為什麼。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    details: list = []
    out = _one_action([EvidenceSpan(text="拿起記憶體模組")])
    sanitize_planner_output(out, normalized_text=norm, details=details)
    hit = [d for d in details if d.reason == "evidence_text_not_found"]
    assert len(hit) == 1
    assert hit[0].text == "拿起記憶體模組"
    assert hit[0].role_key is None


def test_stripped_values_never_reach_unresolved_or_routing():
    """**這條是硬要求**：模型可控字串不得進 reasons／unresolved／routing_reasons。

    那條路會落 DB（`ai_parse_runs.routing_reasons`）並回 API，把模型可控字串放進去
    等於開一個新的注入／洩漏面。這裡走完整條真實鏈路：
    sanitize → `plan.unresolved` → `compute_routing()` → `routing_reasons`。

    mutation：把 `_record` 的內容改塞進 reasons 字串（例如
    `f"role_text_not_in_source:{aid}:{key}:{role.text}"`）→ 本測轉紅。
    """
    from ddm_v2.nlp.contracts import sanitize_planner_output
    from ddm_v2.nlp.routing import compute_routing

    norm = "拿起dimm"
    details: list = []
    sanitized, reasons = sanitize_planner_output(
        _degrading_output(norm), normalized_text=norm, details=details
    )
    assert details, "這條守衛不得空跑：必須真的有東西被剝掉"

    plan = WorkInstructionPlan(
        source_text=norm,
        normalized_text=norm,
        source_ref=SourceRef(kind="interactive"),
        actions=sanitized.actions,
        dependencies=sanitized.dependencies,
        unresolved=sanitized.unresolved,
    )
    _status, routing_reasons = compute_routing(plan, [], [], auto_enabled=False)

    leaked = [_HALLUCINATION, "治具", "450", "cm"]
    for needle in leaked:
        assert not any(needle in r for r in reasons), f"reasons 洩漏 {needle!r}：{reasons}"
        assert not any(needle in u for u in sanitized.unresolved), f"unresolved 洩漏 {needle!r}"
        assert not any(needle in r for r in routing_reasons), f"routing_reasons 洩漏 {needle!r}"
    # 反向控制：值確實被收集到旁通道了（否則上面全 pass 只是因為什麼都沒發生）
    assert any(d.text == _HALLUCINATION for d in details)


def test_details_is_opt_in_and_changes_nothing_when_absent():
    """不訂閱＝不收集，且**輸出與 reasons 逐字相同**——觀測通道不得影響判準。"""
    from ddm_v2.nlp.contracts import sanitize_planner_output

    norm = "拿起dimm"
    with_details: list = []
    a, reasons_a = sanitize_planner_output(
        _degrading_output(norm), normalized_text=norm, details=with_details
    )
    b, reasons_b = sanitize_planner_output(_degrading_output(norm), normalized_text=norm)
    assert a.model_dump() == b.model_dump()
    assert reasons_a == reasons_b
    assert with_details


def test_strip_detail_is_not_a_contract_model():
    """`StripDetail` 刻意不是 pydantic 契約模型——做成契約模型會讓它看起來可以被塞進
    `WorkInstructionPlan`／`ai_parse_runs`，那正是它要避免的事。"""
    import dataclasses

    from pydantic import BaseModel

    from ddm_v2.nlp.contracts import StripDetail

    assert dataclasses.is_dataclass(StripDetail)
    assert not issubclass(StripDetail, BaseModel)
