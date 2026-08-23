"""most_compiler 決策表／partial／allow-list／無 TMU 符號。"""
from __future__ import annotations

import pathlib
import re

import pytest

from ddm_v2.most_compiler.compile import CompileError, allow_lists_from_rule_set, compile_plan
from ddm_v2.most_compiler.policies import CORE_PARAM_BY_ACTION, SEQ_BY_ACTION
from ddm_v2.most_engine.providers import build_from_seed_v2
from ddm_v2.nlp.contracts import (
    EvidenceSpan,
    OptionCandidate,
    PlannedAction,
    RoleValue,
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)


def _allow() -> dict[str, set[str]]:
    return allow_lists_from_rule_set(build_from_seed_v2())


def _cand(action_id: str, parameter: str, field: str, code: str | None) -> SlotCandidateSet:
    chosen = None
    top: list[OptionCandidate] = []
    if code:
        chosen = OptionCandidate(
            parameter=parameter, option_code=code, score=0.95, source="synonym_exact", rank=1
        )
        top = [chosen]
    return SlotCandidateSet(
        action_id=action_id,
        parameter=parameter,
        field=field,
        chosen=chosen,
        top_k=top,
        needs_review=chosen is None,
        review_reason=None if chosen else "no_candidate",
    )


@pytest.mark.parametrize(
    "action_type,seq",
    list(SEQ_BY_ACTION.items()),
)
def test_seq_decision_table(action_type: str, seq: str):
    assert seq in {"GM", "CM"}
    assert action_type in CORE_PARAM_BY_ACTION


def test_acquire_complete_without_place():
    plan = WorkInstructionPlan(
        source_text="拿起DIMM",
        normalized_text="拿起dimm",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={"object": RoleValue(text="DIMM", status="explicit")},
                evidence=[EvidenceSpan(start=0, end=6, text="拿起dimm")],
            )
        ],
    )
    cands = [_cand("a1", "G", "g2.g_code", "g_grasp")]
    drafts = compile_plan(plan, cands, rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert len(drafts) == 1
    assert drafts[0].complete is True
    assert drafts[0].cycle["seq"] == "GM"
    assert drafts[0].cycle["g2"]["g_code"] == "g_grasp"
    assert drafts[0].cycle["p5"]["p_base_code"] is None


def test_partial_when_core_missing():
    plan = WorkInstructionPlan(
        source_text="鎖附",
        normalized_text="鎖附",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="process",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=2, text="鎖附")],
            )
        ],
    )
    drafts = compile_plan(plan, [], rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert drafts[0].complete is False
    assert "missing_core_x" in drafts[0].issues


def test_unknown_code_raises_compile_error():
    plan = WorkInstructionPlan(
        source_text="x",
        normalized_text="x",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=1, text="x")],
            )
        ],
    )
    cands = [_cand("a1", "G", "g2.g_code", "g_not_real")]
    with pytest.raises(CompileError) as ei:
        compile_plan(plan, cands, rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert ei.value.code == "OPTION_NOT_IN_ALLOWLIST"


def test_composite_unknown_not_compiled():
    plan = WorkInstructionPlan(
        source_text="其餘",
        normalized_text="其餘",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="composite_unknown",
                sequence_order=1,
                evidence=[EvidenceSpan(start=0, end=2, text="其餘")],
            )
        ],
        unresolved=["composite_unknown"],
    )
    drafts = compile_plan(plan, [], rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow())
    assert drafts[0].cycle is None
    assert drafts[0].complete is False


# ── E 型完整性窄豁免（D3-026；IE 裁決 2026-08-17/18）─────────────────────────
#
# 純 I 句（面命中集合恰 {I}、I 已掛值、無 M 分量）→ controlled_move 缺 M 仍
# 完整（M=0，cycle 帶真 I 工時）。窄化判準逐條 mutation：
# - 面集合放寬（X 也豁免）→ test_pure_i_exemption_not_for_x_face 紅
#   （那正是 IE 否決的 (a) 全面放寬——C/G 型鎖附/清潔誠實 incomplete）；
# - G 面也豁免 → test_pure_i_exemption_not_for_g_face 紅（F 型 d001
#   「接觸…確認」有手部介入，非純目視）；
# - fail-closed 拆除（face_hit_params=None 也豁免）→
#   test_pure_i_exemption_fail_closed_without_face_evidence 紅。
# - D3-027（D3-026 複審 H1）：豁免改回靜默清空（issues.remove 不掛
#   `m_zero_pure_inspection_assumed`）→ test_pure_i_exemption_completes_
#   with_true_i_tmu 紅（字典外移動動詞的代表句＋routing 斷言在
#   test_linking.test_out_of_lexicon_motion_verb_*）——豁免的假設（M=0 是
#   lexicon 視角的假設，字典外移動動詞句也落入此類別）必須留下可見痕跡。


def _cm_plan(text: str) -> WorkInstructionPlan:
    return WorkInstructionPlan(
        source_text=text,
        normalized_text=text,
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="controlled_move",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=len(text), text=text)],
            )
        ],
    )


def _i_only_cands() -> list[SlotCandidateSet]:
    """linker 對純 I 句的候選形狀：M 核心格空（no_candidate）＋I 掛值。"""
    return [
        _cand("a1", "M", "m3.verb_code", None),
        _cand("a1", "I", "i5.i_code", "i_confirm"),
    ]


def test_pure_i_exemption_completes_with_true_i_tmu():
    """E 型（d021「並確認DIMM點位」形狀）：面集合恰 {I} → M=0 完整、
    cycle 帶 i_confirm（真 I 工時由引擎算——engine gate 測試在 test_linking）。
    豁免**不清空 issues**：missing_core_m 換成假設旗標（D3-027）。"""
    drafts = compile_plan(
        _cm_plan("並確認dimm點位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    d = drafts[0]
    assert d.complete is True
    assert "missing_core_m" not in d.issues
    assert "m_zero_pure_inspection_assumed" in d.issues, (
        "豁免＝假設不是觀測——旗標拆掉（回到靜默清空）必紅"
    )
    assert d.cycle["seq"] == "CM"
    assert d.cycle["i5"]["i_code"] == "i_confirm"
    assert d.cycle["m3"]["m_components"] == []




def test_pure_i_exemption_fail_closed_without_face_evidence():
    """face_hit_params 未提供（None）＝無面命中證據＝不豁免（行為同 D3-024）。"""
    drafts = compile_plan(
        _cm_plan("並確認dimm點位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_not_for_x_face():
    """X 面命中（鎖附/清潔型；含 H1「X 不落 chosen 但面已命中」）不豁免——
    IE 否決的 (a) 全面放寬。mutation：豁免條件放寬到含 X → 本測紅。"""
    drafts = compile_plan(
        _cm_plan("並鎖附固定並確認螺絲到位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I", "X"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_not_for_g_face():
    """G 面命中（接觸/拿取伴確認；F 型 d001 形狀）不豁免——手部已介入，
    非「目視確認無手部移動」。"""
    drafts = compile_plan(
        _cm_plan("接觸卡扣並確認到位"),
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"G", "I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_requires_i_chosen():
    """面集合 {I} 但 I 未掛值（無 chosen）→ 不豁免——豁免的對價是真 I 工時，
    沒有值就沒有工時可帶。"""
    drafts = compile_plan(
        _cm_plan("並確認dimm點位"),
        [_cand("a1", "M", "m3.verb_code", None), _cand("a1", "I", "i5.i_code", None)],
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_not_with_m_component():
    """句面有距離（M 分量非空）→ 不豁免——有移動量就不是純目視。"""
    plan = _cm_plan("並確認dimm點位 30cm")
    drafts = compile_plan(
        plan,
        _i_only_cands(),
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_m" in drafts[0].issues


def test_pure_i_exemption_only_controlled_move():
    """process（core X）不在豁免範圍：面集合 {I} 也不放寬 missing_core_x。"""
    plan = WorkInstructionPlan(
        source_text="並確認dimm點位",
        normalized_text="並確認dimm點位",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="process",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=9, text="並確認dimm點位")],
            )
        ],
    )
    drafts = compile_plan(
        plan,
        [_cand("a1", "X", "x4.x_code", None), _cand("a1", "I", "i5.i_code", "i_confirm")],
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
        face_hit_params={"a1": frozenset({"I"})},
    )
    assert drafts[0].complete is False
    assert "missing_core_x" in drafts[0].issues


def test_compiler_package_has_no_tmu_symbols():
    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "ddm_v2" / "most_compiler"
    banned = re.compile(r"TMU_TO_SEC|total_tmu|_tmu\b|base_tmu")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "rule_set_data" not in text or "TYPE_CHECKING" in text or path.name == "engine_gate.py"
        if path.name == "engine_gate.py":
            continue  # gate 呼叫引擎，不內含表
        assert not banned.search(text), f"TMU symbol in {path}"


# ── S-2：無憑據數值不得靜默進 TMU ────────────────────────────────────────────
#
# 資安席（2026-08-22）實測：`contracts.validate_planner_output` 的證據綁定
# **擋不住**數值角色（只在 status=="explicit" 且 role.text 非 None 才驗，且比對
# 是雙向子字串），而 compiler 先前完全不讀 `RoleValue.status`——零憑據的數字直達
# A 參數／M 分量（distance）與 frequency（quantity）＝TMU 檔位，且 distance 這條
# 路連一個 review 旗標都沒有。
#
# 修法（`policies.numeric_claim_is_evidenced`）：**值照樣採用、但必掛旗標**。
# 為什麼不丟值：丟掉＝改用 0cm，那同樣是憑空的數字（往低估方向），而且會改變既有
# 案例的 TMU＝改計算語意（IE 裁決範圍）。S-2 的病是靜默，旗標把「這個數字沒有
# 出處」變成覆核者看得到、且擋得住 auto 的事實。
#
# 守衛邊界（2026-08-22 當時）：那一批**沒有**收緊 validation，
# `test_three_bypasses_still_pass_validation` 把該前提釘成斷言。
#
# ⚠️ 2026-08-23（ADR-033 P1）三條繞過的攔截點已經改變，但 **compiler 一行沒動**：
#   - 繞過 B（role.text 是 evidence 的超集）：D3 用「role.text 必須是
#     `normalized_text` 的字面子字串」取代雙向比對，contracts 現在就擋得住；
#   - 繞過 A／C（帶 value 的角色）：contracts 仍然放行，但 D1 讓 adapter 邊界
#     一律剝除 `value`／`unit`，LLM 路徑再也送不進來。
# 下面三條 compiler 旗標測試照舊——它們直接組 plan，不經 adapter，驗的是
# 「值真的送到 compiler 時會不會靜默」。攔截點搬家不等於守衛可以拆。


def _dist_plan(
    norm: str,
    ev: tuple[int, int, str],
    roles: dict,
    *,
    action_type: str = "controlled_move",
) -> WorkInstructionPlan:
    return WorkInstructionPlan(
        source_text=norm,
        normalized_text=norm,
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type=action_type,  # type: ignore[arg-type]
                sequence_order=1,
                roles={k: RoleValue(**v) for k, v in roles.items()},
                evidence=[EvidenceSpan(start=ev[0], end=ev[1], text=ev[2])],
            )
        ],
    )


def _compile_one(plan: WorkInstructionPlan, cands: list[SlotCandidateSet]):
    drafts = compile_plan(
        plan, cands, rule_set_code="MINIMOST_FACTORY_V2", allow_lists=_allow()
    )
    assert len(drafts) == 1
    return drafts[0]


def _m_dist(draft) -> float | None:
    comps = (draft.cycle or {}).get("m3", {}).get("m_components") or []
    return comps[0]["distance_cm"] if comps else None


def test_bypass_a_value_only_explicit_distance_is_flagged():
    """繞過 A：`status="explicit"` 但只有 value 沒有 text → contracts 的證據綁定
    整段跳過（`elif role.text is not None`）。300cm 是模型自帶的數字，原文
    「推動治具」一個數字都沒有 → 掛旗標。**只擋非 explicit 是不夠的**。"""
    draft = _compile_one(
        _dist_plan("推動治具", (0, 2, "推動"), {"distance": {"value": 300, "unit": "cm", "status": "explicit"}}),
        [_cand("a1", "M", "m3.verb_code", "m_push")],
    )
    assert "distance_unevidenced_review" in draft.issues
    assert _m_dist(draft) == 300.0, "值不被靜默改寫——本修法治的是靜默，不是數字"


def test_bypass_b_role_text_superset_of_evidence_is_flagged():
    """繞過 B：`role.text` 是 evidence.text 的**超集** → `_role_covered_by_evidence`
    的 `ev.text in text` 分支恆真，validate 放行。超集裡夾帶的「30公分」在原文
    根本不存在（改寫／幻覺）→ 掛旗標。"""
    draft = _compile_one(
        _dist_plan(
            "推動治具",
            (0, 2, "推動"),
            {"distance": {"text": "推動治具至三號無塵室30公分", "status": "explicit"}},
        ),
        [_cand("a1", "M", "m3.verb_code", "m_push")],
    )
    assert "distance_unevidenced_review" in draft.issues
    assert _m_dist(draft) == 30.0


def test_bypass_c_inferred_distance_with_action_ref_is_flagged():
    """繞過 C：`inferred` ＋合法 `action_ref` → validate 對 inferred 角色**完全不驗
    證據**（few-shot #2 正教了這個形狀）。400cm 直達 M 分量 → 掛旗標。"""
    draft = _compile_one(
        _dist_plan(
            "推動治具",
            (0, 2, "推動"),
            {"distance": {"status": "inferred", "action_ref": "a1", "value": 400, "unit": "cm"}},
        ),
        [_cand("a1", "M", "m3.verb_code", "m_push")],
    )
    assert "distance_unevidenced_review" in draft.issues
    assert _m_dist(draft) == 400.0


def test_where_each_bypass_is_intercepted_after_adr033_p1():
    """三條繞過**在哪一層**被攔下——攔截點是會搬家的，搬到哪裡要有斷言記著。

    2026-08-22（S-2 修法當時）：三條都 `errors=[]`，唯一的攔截點是 compiler 旗標。
    2026-08-23（ADR-033 P1）：

    - 繞過 B 由 **contracts** 擋（D3 的字面子字串不變式取代雙向比對）；
    - 繞過 A／C 的 contracts 仍放行（沒有 `text` 就沒有可驗的片語），改由
      **adapter 邊界**剝除 `value`／`unit`（D1），LLM 路徑送不進 compiler。

    compiler 側的三條旗標測試（上面）一行沒改、照舊會紅——這裡驗的是上游多了
    兩道，不是下游可以拆。
    """
    from ddm_v2.nlp.contracts import (
        PlannerOutput,
        sanitize_planner_output,
        validate_planner_output,
    )

    numeric_shapes = [
        {"distance": {"value": 300, "unit": "cm", "status": "explicit"}},
        {"distance": {"status": "inferred", "action_ref": "a1", "value": 400, "unit": "cm"}},
    ]
    for roles in numeric_shapes:
        plan = _dist_plan("推動治具", (0, 2, "推動"), roles)
        output = PlannerOutput(language="zh", actions=plan.actions)
        assert (
            validate_planner_output(output, normalized_text=plan.normalized_text) == []
        ), f"契約層不驗數值角色的出處（沒有 text 就沒有片語可驗）：{roles}"
        sanitized, reasons = sanitize_planner_output(
            output, normalized_text=plan.normalized_text
        )
        assert "role_numeric_stripped:a1:distance" in reasons, roles
        role = sanitized.actions[0].roles["distance"]
        assert (role.value, role.unit) == (None, None), (
            f"adapter 邊界必須剝掉模型主張的數值（{roles}）——這是 ADR-033 D1／D7 "
            "「距離只能來自對原文的確定性抽取或 ADR-031 佈局」的落地點。"
        )

    superset = {"distance": {"text": "推動治具至三號無塵室30公分", "status": "explicit"}}
    plan = _dist_plan("推動治具", (0, 2, "推動"), superset)
    errors = validate_planner_output(
        PlannerOutput(language="zh", actions=plan.actions),
        normalized_text=plan.normalized_text,
    )
    assert "role_text_not_in_source:a1:distance" in errors, (
        "D3 的字面子字串不變式應該擋下「role.text 是 evidence 的超集」這條繞過；"
        f"實際 errors={errors}"
    )


@pytest.mark.parametrize(
    "norm,span_end",
    [("推治具30cm", 7), ("push the fixture 30cm to the left rail", 38)],
)
def test_evidenced_distance_unchanged_and_unflagged(norm: str, span_end: int):
    """正向：距離在本 action 的 evidence 內定位得到 → 行為完全不變、不掛旗標。
    （中英各一：`extract_distances` 對兩種寫法都命中。）"""
    draft = _compile_one(
        _dist_plan(
            norm,
            (0, span_end, norm),
            {"distance": {"text": "30cm", "value": 30, "unit": "cm", "status": "explicit"}},
        ),
        [_cand("a1", "M", "m3.verb_code", "m_push")],
    )
    assert draft.issues == []
    assert _m_dist(draft) == 30.0


def test_distance_from_another_actions_span_is_flagged():
    """`_evidence_distance_cm` 的 fallback 分支（無 evidence 重疊時回「全句第一個
    距離」）同樣是無憑據：a1「拿起板子」沒有距離，30cm 是 a2 的——先前它會靜默
    變成 a1 的 A0 reach（＝TMU 檔位）。"""
    plan = WorkInstructionPlan(
        source_text="拿起板子,推動治具30cm",
        normalized_text="拿起板子,推動治具30cm",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=4, text="拿起板子")],
            ),
            PlannedAction(
                action_id="a2",
                action_type="controlled_move",
                sequence_order=2,
                roles={},
                evidence=[EvidenceSpan(start=5, end=14, text="推動治具30cm")],
            ),
        ],
    )
    drafts = compile_plan(
        plan,
        [_cand("a1", "G", "g2.g_code", "g_grasp"), _cand("a2", "M", "m3.verb_code", "m_push")],
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=_allow(),
    )
    a1, a2 = drafts
    assert a1.cycle["a0"]["reach_cm"] == 30.0
    assert "distance_unevidenced_review" in a1.issues, "別的 action 的距離不得靜默掛過來"
    assert a2.issues == [], "a2 的距離就在自己的 evidence 裡——不受影響"
    assert _m_dist(a2) == 30.0


def test_unevidenced_quantity_flagged_but_frequency_unchanged():
    """quantity 同病：`qty.value` 直接是 frequency（TMU 乘數）而不讀 status。
    `quantity_policy_review` 講的是「N 該不該當 frequency」，講不到「N 有沒有
    出處」——原文「鎖附螺絲」沒有 16。"""
    draft = _compile_one(
        _dist_plan(
            "鎖附螺絲",
            (0, 4, "鎖附螺絲"),
            {"quantity": {"value": 16, "status": "inferred", "action_ref": "a1"}},
            action_type="process",
        ),
        [_cand("a1", "X", "x4.x_code", "x_screw_fix")],
    )
    assert "quantity_unevidenced_review" in draft.issues
    assert "quantity_policy_review" in draft.issues
    assert draft.cycle["frequency"] == 16.0, "乘數不被靜默改寫（改值＝改計算語意）"


def test_evidenced_quantity_not_flagged():
    """正向（g02 形狀）：「兩顆」在本 action 的 evidence 窗內 → 只有既有的
    quantity_policy_review。

    接住它的是**路徑 (1)**（`extract_counts` 抽到「兩顆」＝2 且 span 與 evidence
    重疊），不是路徑 (2) 的帶單位數字退路——M2 mutation（路徑 (2) 換成
    `return False`）時本測仍綠可證。路徑 (2) 的專屬守衛在
    `test_path2_backs_units_outside_the_extraction_lexicon`。"""
    draft = _compile_one(
        _dist_plan(
            "鎖附兩顆螺絲",
            (0, 6, "鎖附兩顆螺絲"),
            {"quantity": {"text": "兩顆", "value": 2, "unit": "顆", "status": "explicit"}},
            action_type="process",
        ),
        [_cand("a1", "X", "x4.x_code", "x_screw_fix")],
    )
    assert "quantity_unevidenced_review" not in draft.issues
    assert draft.issues == ["quantity_policy_review"]
    assert draft.cycle["frequency"] == 2.0


@pytest.mark.parametrize(
    "norm,span_end,expect_status",
    [("推治具30cm", 7, "auto"), ("推動治具", 4, "review")],
)
def test_unevidenced_distance_blocks_auto_end_to_end(norm: str, span_end: int, expect_status: str):
    """compile → engine_gate → routing 全程：同一份計畫，距離有憑據時可 auto、
    無憑據時只能 review。成對斷言＝旗標從 draft.issues 一路活到 routing 的
    blocked 集（engine_gate 不得把它濾掉、`_eligible_auto` 不得漏掉它）。"""
    from ddm_v2.most_compiler.engine_gate import apply_engine_gate
    from ddm_v2.nlp.routing import compute_routing

    plan = _dist_plan(
        norm, (0, span_end, norm), {"distance": {"value": 30, "unit": "cm", "status": "explicit"}}
    )
    cands = [_cand("a1", "M", "m3.verb_code", "m_push")]
    rs = build_from_seed_v2()
    drafts = compile_plan(
        plan, cands, rule_set_code="MINIMOST_FACTORY_V2", allow_lists=allow_lists_from_rule_set(rs)
    )
    drafts = apply_engine_gate(drafts, rs)
    assert drafts[0].complete is True and drafts[0].engine_result is not None
    status, reasons = compute_routing(plan, cands, drafts, auto_enabled=True)
    assert status == expect_status
    if expect_status == "review":
        assert "distance_unevidenced_review" in reasons
        assert "distance_unevidenced_review" in drafts[0].issues, "engine_gate 不得濾掉旗標"


# ── 非有限值（NaN／±Inf）在 compiler 邊界拒收（S-2 複審的 fail-open）─────────
#
# S-2 修法的第一版對 NaN **fail-OPEN**：`abs(nan - v) > tol` 恆為 False，
# `numeric_claim_is_evidenced` 的 `continue` 不會執行，只要句面有任一距離與
# evidence 重疊就回 True → NaN 被認證為「有憑據」→ `reach_cm=nan` 進引擎。
# 而 `most_engine/rule_set_data.py` 的 `band_index` 對 NaN 的每個 `<=` 也都是
# False，一路落到溢位帶＝**最大** A 檔位：實測 A24／30 TMU、零旗標零錯誤。
#
# 三條同根因（缺有限值檢查）的實測後果，逐條由下面的測試釘住：
# - distance（GM）：NaN／+Inf → A24（最大檔）；-Inf → 引擎拒（誤打誤撞才擋住）
# - quantity：`int(nan)` → ValueError、`int(inf)` → OverflowError，拋出點在
#   `compile_plan`，在 `wi_ai_service` 的 LLM try/except **之外** → HTTP 500
# - process_kind 秒數：`x_seconds=nan` → `total_tmu: nan`（非合規 JSON，前端拿到
#   `NaN` 字面量）；`inf` → `Decimal` 丟 `InvalidOperation`，而 `engine_gate`
#   只接 `SequenceError` → 一路衝出去
#
# 修法與 S-2 主體相反——**拒收**而不是「照用＋掛旗標」：非有限值不是「沒出處的
# 量」，是「不是量」，照用等於讓它變成最貴的檔位或 500。拒收留痕
# （`non_finite_value_rejected`，擋 auto），不靜默。

NAN = float("nan")
INF = float("inf")


def _engine(draft):
    from ddm_v2.most_compiler.engine_gate import apply_engine_gate

    return apply_engine_gate([draft], build_from_seed_v2())[0]


@pytest.mark.parametrize("bad", [NAN, INF, -INF])
def test_non_finite_distance_never_reaches_the_engine(bad: float):
    """GM 路徑：非有限的 from_location **不得**進 `reach_cm`。原文有「30cm」，
    拒收後走句面抽取（有憑據）→ A10；放行的話 NaN／+Inf 會落到 **A24**（溢位帶）。
    mutation：拿掉 `finite_or_reject` → `A24` 斷言紅。"""
    import math

    plan = _dist_plan(
        "拿起板子30cm", (0, 10, "拿起板子30cm"),
        {"from_location": {"value": bad, "unit": "cm", "status": "explicit"}},
        action_type="acquire",
    )
    draft = _compile_one(plan, [_cand("a1", "G", "g2.g_code", "g_grasp")])
    assert "non_finite_value_rejected" in draft.issues, "拒收要留痕，不得靜默丟棄"
    reach = draft.cycle["a0"]["reach_cm"]
    assert math.isfinite(reach) and reach == 30.0
    gated = _engine(draft)
    assert gated.engine_result is not None
    assert "A24" not in gated.engine_result["tech_line"], "非有限值不得換到最大 A 檔位"


def test_nan_distance_is_rejected_even_when_a_distance_overlaps_evidence():
    """釘住 fail-open 的**來源**：句面有距離且與 evidence 重疊時，舊的比對式
    `abs(nan - 30) > tol` 為 False → 不 continue → 直接 return True（NaN 被認證
    為有憑據）。`numeric_claim_is_evidenced` 自己必須 fail-closed，不倚賴呼叫端。"""
    from ddm_v2.most_compiler.policies import numeric_claim_is_evidenced

    plan = _dist_plan("推治具30cm", (0, 7, "推治具30cm"), {})
    action = plan.actions[0]
    assert numeric_claim_is_evidenced(action, plan, value=30.0, kind="distance") is True
    assert numeric_claim_is_evidenced(action, plan, value=NAN, kind="distance") is False
    assert numeric_claim_is_evidenced(action, plan, value=INF, kind="distance") is False


@pytest.mark.parametrize("bad", [NAN, INF, -INF])
def test_non_finite_quantity_does_not_raise(bad: float):
    """quantity：`nan <= 0` 是 False，會一路走到 `int(n)`——舊行為 NaN 丟
    `ValueError`、Inf 丟 `OverflowError`，而拋出點在 `compile_plan`（LLM 的
    try/except 之外，`nl_draft` 只接 RuleSetNotFound／RuntimeError）→ HTTP 500。
    現在：frequency 回 1.0＋旗標，不拋。"""
    draft = _compile_one(
        _dist_plan(
            "鎖附螺絲", (0, 4, "鎖附螺絲"),
            {"quantity": {"value": bad, "status": "explicit"}},
            action_type="process",
        ),
        [_cand("a1", "X", "x4.x_code", "x_screw_fix")],
    )
    assert "non_finite_value_rejected" in draft.issues
    assert draft.cycle["frequency"] == 1.0, "非有限的乘數＝沒有乘數，不是 nan 也不是猜的 N"


@pytest.mark.parametrize("bad", [NAN, INF, -INF])
def test_non_finite_process_seconds_does_not_produce_nan_tmu(bad: float):
    """process_kind 秒數：`x_seconds=nan` 舊行為算出 `total_tmu: nan`（零旗標，
    且 `NaN` 不是合規 JSON——前端會拿到裸 `NaN`）；`inf` 讓 `Decimal` 丟
    `InvalidOperation`，`engine_gate` 只接 `SequenceError` → 一路衝出去。"""
    import json

    draft = _compile_one(
        _dist_plan(
            "按壓5秒", (0, 4, "按壓5秒"),
            {"process_kind": {"value": bad, "unit": "秒", "status": "explicit"}},
            action_type="process",
        ),
        [_cand("a1", "X", "x4.x_code", "x_press")],
    )
    assert "non_finite_value_rejected" in draft.issues
    assert draft.cycle["x4"]["x_seconds"] == 0.0
    gated = _engine(draft)  # 不得拋 InvalidOperation
    if gated.engine_result is not None:
        json.dumps(gated.engine_result, allow_nan=False)  # 不得出現裸 NaN


def test_finite_values_are_untouched_by_the_non_finite_gate():
    """正向對照：有限值行為完全不變、不掛 `non_finite_value_rejected`。"""
    dist = _compile_one(
        _dist_plan("推治具30cm", (0, 7, "推治具30cm"),
                   {"distance": {"value": 30, "unit": "cm", "status": "explicit"}}),
        [_cand("a1", "M", "m3.verb_code", "m_push")],
    )
    secs = _compile_one(
        _dist_plan("按壓5秒", (0, 4, "按壓5秒"),
                   {"process_kind": {"value": 5, "unit": "秒", "status": "explicit"}},
                   action_type="process"),
        [_cand("a1", "X", "x4.x_code", "x_press")],
    )
    qty = _compile_one(
        _dist_plan("鎖附兩顆螺絲", (0, 6, "鎖附兩顆螺絲"),
                   {"quantity": {"text": "兩顆", "value": 2, "unit": "顆", "status": "explicit"}},
                   action_type="process"),
        [_cand("a1", "X", "x4.x_code", "x_screw_fix")],
    )
    for draft in (dist, secs, qty):
        assert "non_finite_value_rejected" not in draft.issues
    assert _m_dist(dist) == 30.0
    assert secs.cycle["x4"]["x_seconds"] == 5.0
    assert qty.cycle["frequency"] == 2.0


# ── 判準路徑 (2)：帶單位數字的退路（code review M2 ＋ validator F1/F3/F4）──────
#
# 路徑 (2)（`_quantities_in_own_evidence`）先前是「裸數字出現在 evidence 文字裡」，
# 有兩個實測缺陷：
#
# (a) 誤觸——不看 kind、也不看數字是不是一個獨立的量。`十字起子`（十→10）替捏造的
#     `10cm` 背書、`一體成型` 替 `1cm`、`3顆螺絲` 用**件數**替**距離**背書、
#     `45cm` 反過來替 `count=45` 背書。「十字起子」是產線標準詞，不是構造的例子。
# (b) 誤報——`quantities._COUNT_RE` 的中文分支只吃單字元，「十六顆」抽成 6，
#     於是正確的 `quantity=16` 反被判成與原文矛盾。
#
# 收緊：路徑 (2) 要求「數字＋**相稱單位／量詞**」（kind-aware），中文數字補上
# 多字組合（1–99）。另加 **F3 矛盾檢查**：窗內抽到同 kind 的量卻沒有一個對得上
# → 直接判無憑據，不走退路——那正是 mm↔cm 混淆（`450mm` ＋ `value=450 unit=cm`
# ＝真值的 10 倍）唯一被擋下來的地方。
#
# ⚠️ M2（mutation）：把 `_quantities_in_own_evidence` 那一支換成 `return False`
# → 下面 `test_path2_backs_units_outside_the_extraction_lexicon` 會紅（已實跑驗證）。
# 那三個案例是**只有路徑 (2) 接得住**的形狀，其餘幾支走路徑 (1)。


def _evidenced(norm: str, value: float, kind: str) -> bool:
    from ddm_v2.most_compiler.policies import numeric_claim_is_evidenced

    plan = _dist_plan(norm, (0, len(norm), norm), {})
    return numeric_claim_is_evidenced(plan.actions[0], plan, value=value, kind=kind)


@pytest.mark.parametrize(
    "norm,value",
    [("以十字起子鎖附螺絲", 10.0), ("一體成型外殼壓合", 1.0), ("執行二次確認", 2.0)],
)
def test_path2_chinese_numeral_inside_an_ordinary_word_backs_nothing(norm: str, value: float):
    """中文數字是更長詞彙的一部分（十字／一體／二次）→ 不是一個量，不得替距離背書。"""
    assert _evidenced(norm, value, "distance") is False


@pytest.mark.parametrize(
    "norm,value,kind",
    [("取3顆螺絲推至定位", 3.0, "distance"), ("推45cm至定位", 45.0, "count")],
)
def test_path2_is_kind_aware(norm: str, value: float, kind: str):
    """件數不替距離背書、距離不替件數背書——docstring 宣稱的 kind 要真的做到。"""
    assert _evidenced(norm, value, kind) is False


@pytest.mark.parametrize("norm,value", [("依圖示鎖附十六顆螺絲", 16.0), ("鎖附二十顆螺絲", 20.0), ("推十六次", 16.0)])
def test_multi_character_chinese_numerals_are_not_false_flagged(norm: str, value: float):
    """F1：`_COUNT_RE` 中文分支只吃單字元（「十六顆」抽成 6），正確的 16／20 先前
    會被誤掛旗標。往左補回完整中文數字 token 後兩邊都對。"""
    assert _evidenced(norm, value, "count") is True


def test_truncated_chinese_numeral_does_not_back_the_wrong_value():
    """反向：修好截斷後，錯值 6 也不再被「十六顆」背書（先前 `_COUNT_RE` 抽出的
    正是 6，等於替錯值背書）。"""
    assert _evidenced("依圖示鎖附十六顆螺絲", 6.0, "count") is False


@pytest.mark.parametrize(
    "norm,value,kind",
    [("推治具45厘米至定位", 45.0, "distance"), ("取三支螺絲", 3.0, "count"), ("取 16 pcs 螺絲", 16.0, "count")],
)
def test_path2_backs_units_outside_the_extraction_lexicon(norm: str, value: float, kind: str):
    """路徑 (2) 存在的理由：單位／量詞不在 `quantities` 的抽取表內（厘米／支／pcs）
    但數字確實帶著單位出現在自己的 evidence 裡。**M2 守衛**——拿掉路徑 (2) 這三支必紅。"""
    assert _evidenced(norm, value, kind) is True


def test_unit_confusion_contradicting_the_text_is_flagged():
    """F3（validator）：原文「450mm」＋模型 `value=450 unit="cm"` ＝真值 45cm 的
    **10 倍**（跨好幾個 A 檔位）。路徑 (1) 其實已在同窗抽到 45.0，先前是裸數字
    退路（「450」字面出現）把它救回去。單位正規化是 LLM 最常見的數值錯誤形態。

    值照舊不改寫（450 仍進 cycle）——旗標讓覆核者看得到它與原文矛盾。"""
    norm = "推動治具450mm至定位"
    draft = _compile_one(
        _dist_plan(norm, (0, len(norm), norm),
                   {"distance": {"value": 450, "unit": "cm", "status": "explicit"}}),
        [_cand("a1", "M", "m3.verb_code", "m_push")],
    )
    assert "distance_unevidenced_review" in draft.issues
    assert _m_dist(draft) == 450.0
    # 對照組：同一句、模型正確換算成 45cm → 走路徑 (1)、不掛旗標
    ok = _compile_one(
        _dist_plan(norm, (0, len(norm), norm),
                   {"distance": {"value": 45, "unit": "cm", "status": "explicit"}}),
        [_cand("a1", "M", "m3.verb_code", "m_push")],
    )
    assert ok.issues == []
    assert _m_dist(ok) == 45.0


@pytest.mark.parametrize(
    "norm,label",
    [("走3公尺至料架", "公尺＝300cm（100 倍）"), ("走3米至料架", "米＝300cm"),
     ("走3尺至料架", "尺≈91cm（30 倍）"), ("推3公厘至定位", "公厘＝0.3cm（10 倍高估）")],
)
def test_path2_rejects_units_it_cannot_compare_by_magnitude(norm: str, label: str):
    """路徑 (2) 的單位表**只認得「像不像距離單位」、不認得量級**，所以不得收錄
    與 cm 不同量級、而抽取器（`quantities.UNIT_TO_CM`）又抽不出來的單位——
    那種組合下矛盾檢查放不出來（進不了 `in_window`），只剩裸數字比對：
    「走3公尺」＋主張 `3 unit="cm"` 差 **100 倍**卻靜默通過，與 F3 同構。

    這四個單位現在**保守誤報**（掛旗標），那是刻意的取捨。正解是擴充
    `quantities.UNIT_TO_CM`（矛盾檢查就自動涵蓋），屬另一票。"""
    assert _evidenced(norm, 3.0, "distance") is False, label


def test_path2_keeps_centimetre_synonyms():
    """對照：`厘米` 等於 cm、量級相同，沒有上面的問題 → 保留在表內。"""
    assert _evidenced("推治具45厘米至定位", 45.0, "distance") is True


def test_path2_reads_the_window_from_normalized_text_not_model_supplied_text():
    """守衛要自足：路徑 (2) 從 `normalized_text[start:end]` 切窗，不讀模型給的
    `ev.text`。捏造 `ev.text="推動治具450公分"`（原文只有「推動治具」）先前可以
    替 `450cm` 取得背書——今天上游會先擋（ADR-033 D4：`locate_evidence_spans`
    定位不到就剔除整個 action），但 `compile_plan` 自己不驗它，守衛不該倚賴
    另一個模組維持的不變量。原則不變：text 是模型給的資料、offset 是可推導的座標。"""
    from ddm_v2.most_compiler.policies import numeric_claim_is_evidenced

    norm = "推動治具"
    plan = WorkInstructionPlan(
        source_text=norm,
        normalized_text=norm,
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="controlled_move",
                sequence_order=1,
                roles={},
                # 模型捏造的 text，offset 仍指向真實原文的範圍
                evidence=[EvidenceSpan(start=0, end=4, text="推動治具450公分")],
            )
        ],
    )
    assert (
        numeric_claim_is_evidenced(plan.actions[0], plan, value=450.0, kind="distance")
        is False
    )


def test_out_of_range_evidence_span_is_an_empty_window_not_an_exception():
    """越界 span → 切不出文字＝空窗＝無憑據，不得拋例外。

    ADR-033 D4 之後正式管線不會再送進越界 span（offset 由
    `contracts.locate_evidence_spans` 推導，定位不到的 action 直接剔除）——
    但守衛不該倚賴另一個模組維持的不變量，本條照留。"""
    from ddm_v2.most_compiler.policies import numeric_claim_is_evidenced

    norm = "推動治具"
    plan = WorkInstructionPlan(
        source_text=norm,
        normalized_text=norm,
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="controlled_move",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=100, end=120, text="推45公分")],
            )
        ],
    )
    assert (
        numeric_claim_is_evidenced(plan.actions[0], plan, value=45.0, kind="distance")
        is False
    )
