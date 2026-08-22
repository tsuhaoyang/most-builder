"""compile_plan：WorkInstructionPlan + candidates → CycleDraft（無 TMU）。"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

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
    DISTANCE_UNEVIDENCED_REVIEW,
    SEQ_BY_ACTION,
    finite_or_reject,
    holding_inferred_reason,
    is_tool_held,
    numeric_claim_is_evidenced,
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


def _resolve_distance_cm(
    action: PlannedAction,
    plan: WorkInstructionPlan,
    *,
    role_key: str,
    text_fallback: bool,
) -> tuple[float, list[str]]:
    """回傳 (cm, issues)——距離進 TMU 檔位的**唯一**入口（S-2）。

    A 參數（`StrictASlot.reach_cm`）與 M 分量（`StrictMComponent.distance_cm`）
    就是 TMU 檔位，所以「這個 cm 從哪來」必須是可回答的問題：

    - role 帶值（`_role_distance_cm`）→ 那是**模型的主張**，須能定位到本 action
      的文字證據（`numeric_claim_is_evidenced`），否則掛
      `distance_unevidenced_review`。
    - role 無值 → 退回句面抽取（`_evidence_distance_cm`）。它的 fallback 分支會
      在**沒有任何 evidence 重疊**時回「全句第一個距離」——那是把別的 action 的
      距離掛到這個 action 上（多 action 計畫實測可重現），同樣要掛旗標。

    兩條路都**照常回傳該值**（不靜默改成 0）：本票治的是靜默，不是數字本身
    （取捨理由見 `policies.DISTANCE_UNEVIDENCED_REVIEW`）。旗標擋 auto
    （`routing._eligible_auto`），覆核者一定看得到。

    **例外是非有限值**（`NaN`／`±Inf`）：那不是「沒出處的量」而是「不是量」，
    在這裡就拒收（`finite_or_reject`），改走句面抽取／0——放行的話 `band_index`
    的每個 `<=` 比較都是 False，直接落到溢位帶＝**最大** A 檔位。攔在這裡而不是
    `_role_distance_cm`：那支只回「多少 cm」，回不了「有個值被丟掉了」，而拒收
    必須留痕。
    """
    issues: list[str] = []
    role_cm = finite_or_reject(_role_distance_cm(action, role_key), issues)
    # 沿用既有語意：role 值為 0／None 都往句面抽取那條路走
    cm = role_cm if role_cm else (_evidence_distance_cm(action, plan) if text_fallback else None)
    # 句面抽取來自 regex，恆為有限；這道是 fail-closed，不倚賴那個性質
    cm = finite_or_reject(cm, issues)
    if not cm:
        return 0.0, issues
    if numeric_claim_is_evidenced(action, plan, value=cm, kind="distance"):
        return float(cm), issues
    if DISTANCE_UNEVIDENCED_REVIEW not in issues:
        issues.append(DISTANCE_UNEVIDENCED_REVIEW)
    return float(cm), issues


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
    face_hit_params: Mapping[str, frozenset[str]] | None = None,
) -> list[CycleDraft]:
    """確定性編譯。allow_lists keys: G,P,P_ADDON,M,X,I,B。

    `face_hit_params`（D3-026）：action_id → 該 action 的 lexicon 面命中參數
    集合（`SlotLinker.face_hit_params` 產出）——E 型窄豁免的判準輸入。候選層
    看不到未被查詢的參數面（controlled_move 不掛 G spec），故需獨立證據；
    未提供（None）＝無面命中證據＝不豁免（fail-closed，行為同 D3-024）。
    """
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
        freq, freq_reasons = resolve_frequency(action, plan)
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
            a0_cm, a0_issues = _resolve_distance_cm(
                action,
                plan,
                role_key="from_location",
                text_fallback=action.action_type == "acquire",
            )
            a3_cm, a3_issues = _resolve_distance_cm(
                action,
                plan,
                role_key="distance",
                text_fallback=action.action_type in {"move_place", "release_return"},
            )
            for issue in a0_issues + a3_issues:
                if issue not in issues:
                    issues.append(issue)
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
            dist, dist_issues = _resolve_distance_cm(
                action, plan, role_key="distance", text_fallback=True
            )
            for issue in dist_issues:
                if issue not in issues:
                    issues.append(issue)
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
                # 同一道有限值關卡（S-2 複審）：nan 秒數會讓引擎算出 nan 的
                # TMU 總計（非合規 JSON、零旗標），inf 讓 `Decimal` 丟
                # `InvalidOperation`——而 engine_gate 只接 `SequenceError`，
                # 那個例外會一路衝出去變 500
                secs = finite_or_reject(float(pk.value), issues)
                x_seconds = float(secs) if secs is not None else 0.0
            # ── E 型完整性窄豁免（D3-026；IE 裁決 2026-08-17/18，見 worklog）──
            # 純 I 句：該 action 的面命中集合**恰為 {I}**（無 X、無 M、無 G、
            # 無任何其他 slot 面）、I 已掛值、且無任何 M 分量（句面也無距離）
            # → M=0 視為完整，cycle 帶真 I 工時（如「並確認DIMM點位」＝
            # A0 B0 G0 M0 X0 I6 A0）。IE 原話：「目視確認無手部移動」。
            # **窄**：X 面命中（鎖附/清潔型）不豁免——那正是 IE 否決的 (a)
            # 全面放寬（C/G 型的移動真實存在，走 expected_incomplete_reason
            # 誠實 incomplete）；G 面命中（接觸/拿取伴確認）同樣不豁免（手部
            # 已介入＝非純目視）。face_hit_params 未提供＝不豁免（fail-closed）。
            #
            # **已知限制（D3-027；掛 F 票）**：面集合是 lexicon 視角——本豁免
            # 的實際類別＝「含 I 面且無其他**字典內** slot 面」。字典外的真實
            # 移動動詞（「旋轉旋鈕並確認」「翻轉主板並確認」）同樣塌成 {I}
            # 而落入豁免。所以豁免**不清空 issues**：missing_core_m 換成假設
            # 旗標 `m_zero_pure_inspection_assumed`（與 i_range_assumed 同風格）
            # ——「M=0 是假設不是觀測」對 routing/覆核永遠可見，並顯式擋 auto
            # （routing._eligible_auto 釘死本旗標，不倚賴 M 候選空的結構巧合）。
            # F 票（lexicon 面比對修復）修好後類別會縮小，旗標語意不變。
            if (
                not complete
                and miss_reason == "missing_core_m"
                and action.action_type == "controlled_move"
                and face_hit_params is not None
                and face_hit_params.get(action.action_id) == frozenset({"I"})
                and i_code is not None
                and not m_comps
            ):
                complete = True
                issues[issues.index("missing_core_m")] = "m_zero_pure_inspection_assumed"
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
