"""`MotionSuggestion` → `WorkInstructionPlan`＋候選（ADR-037 D3；實作計畫 S3）。純函式，不碰 DB、不呼叫外部服務。

## 責任分工（Howard 2026-11-22）

ai_service 只做「句子 → motion 分解＋候選 slot code」；規則、驗證、TMU 都在 MOST：

- **規則在 MOST**：`action_type`（決定走 GM 還是 CM、核心位置是哪個）由 MOST 用固定規則從 slot 內容推導，
  **不看** ai_service 給的 `hand_hint`／`seq_kind_hint`（ADR-037 D3：不採信）。
- **AI 的 code 只是候選**：放進 `SlotCandidateSet.top_k`（來源 `ai_service`），**`chosen` 一律是 None**。
  `chosen` 的意思是「MOST 或人的決定」；把 AI 的 code 直接填進去，等於 MOST 照單全收。
- **看得到草稿，但不是決定**：`preview_drafts` 用候選的**複本**（暫時把第一候選當 chosen）讓 compile 算一份
  預覽 draft，每份都帶 `ai_candidate_preview`。人工採用（實作計畫 S4）才會真的寫入 `chosen`。
- **TMU 只來自引擎**：本模組不算任何數值；A 位置的 `magnitude_*_hint` 不轉成 `Measurement`
  （`ai_estimate_confirmed` 須有人確認，ADR-037 D3），所以預覽的 A 位置距離只會來自 MOST 自己的句面抽取，
  並照舊被 `distance_unevidenced_review` 標出來。
- **不比對 linker**（第一版）：ai_service 的 motion 切法不一定對得上 MOST 的 action 切法；每個 AI motion 都標
  `ai_source_no_evidence`，一律人工審核。與 linker 結果的比對留到審核畫面（S4）。

## 不產生的東西

SIMO（ADR-020）、手別（MOST 的來源是 Excel 欄、使用者輸入、確定性解析）、`roles`／`evidence`
（ai_service 沒有 evidence span，ADR-033 D3 的字面子字串不變式不適用，所以也不捏造 role 文字）。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from ddm_v2.ai_integration.mapper import ISSUE_A_RETURN_NEEDS_REVIEW, ISSUE_UNKNOWN_CODE
from ddm_v2.ai_integration.ports import AllowLists, Hand, MotionSuggestion
from ddm_v2.most_compiler.compile import compile_plan
from ddm_v2.nlp.contracts import (
    ActionType,
    CycleDraft,
    OptionCandidate,
    PlannedAction,
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)

Language = Literal["zh", "en", "mixed"]

AI_PLANNER_NOTE = "ai_service"
AI_REVIEW_REASON = "ai_candidate"

REASON_NO_EVIDENCE = "ai_source_no_evidence"
REASON_UNKNOWN_CODE = "ai_unknown_code"
REASON_RETURN_A = "ai_return_a_position"
REASON_HAND_MISMATCH = "ai_hand_hint_mismatch"
REASON_ADDON_TRUNCATED = "ai_addon_truncated"
REASON_CANDIDATE_PREVIEW = "ai_candidate_preview"

# parameter → field（與 `nlp/linking.py` 的欄位名一致，審核與落盤端用同一套鍵）
_FIELD_BY_PARAMETER: dict[str, str] = {
    "B": "b1.b_code",
    "G": "g2.g_code",
    "P": "p5.p_base_code",
    "P_ADDON": "p5.p_addon_codes",
    "M": "m3.verb_code",
    "X": "x4.x_code",
    "I": "i5.i_code",
}


@dataclass(frozen=True)
class MotionLabel:
    """只供審核畫面顯示的語意描述（已由 mapper 清理並限長）。不進 plan、不參與任何判斷。"""

    sub_activity: str
    object_text: str
    # ai_service 的手別提示（不採信）。沒有手別來源可比對時不標 reason，留給審核（S4）採用時人工指定
    hand_hint: str | None = None


@dataclass(frozen=True)
class AiPlanBuild:
    plan: WorkInstructionPlan
    candidates: list[SlotCandidateSet]
    # 要經 `compute_routing(extra_reasons=...)` 併入 routing_reasons 的旗標
    reasons: list[str] = field(default_factory=list)
    labels: dict[str, MotionLabel] = field(default_factory=dict)
    # ai_service 給了、但 MOST 的 compile 沒有地方放而**沒有進 plan／候選**的內容（例 `a1:b4`、`a1:a0.magnitude_hint`）。
    # 只含 MOST 自己的常數（動作編號與位置名），給審核畫面說明「為什麼這個欄位是空的」；不是 routing reason。
    dropped: list[str] = field(default_factory=list)


def derive_action_type(m: MotionSuggestion) -> ActionType:
    """MOST 的固定規則：從 slot 內容推導，不看 `hand_hint`／`seq_kind_hint`。

    - CM 的中段（M／X／I）與 GM 的中段（A／B／P）同時有值＝形狀矛盾，不猜 → `composite_unknown`。
    - CM：M → `controlled_move`；否則 X → `process`；否則 I → `inspect`。
    - GM：有 P base → `move_place`；否則有 G → `acquire`。
    - 什麼都沒有 → `composite_unknown`。
    """
    has_cm_mid = bool(m.m3 or m.x4 or m.i5)
    has_place = m.p5 is not None and m.p5.base is not None
    has_gm_mid = bool(has_place or m.b4 or m.a3)
    if has_cm_mid and has_gm_mid:
        return "composite_unknown"
    if m.m3:
        return "controlled_move"
    if m.x4:
        return "process"
    if m.i5:
        return "inspect"
    if has_place:
        return "move_place"
    if m.g2:
        return "acquire"
    return "composite_unknown"


def _candidate_set(
    action_id: str, parameter: str, codes: Sequence[str]
) -> SlotCandidateSet:
    # ai_service 不給分數；0.0 代表「沒有分數」，不是「分數很低」。排序只看 rank。
    top_k = [
        OptionCandidate(parameter=parameter, option_code=code, score=0.0, source="ai_service", rank=i + 1)
        for i, code in enumerate(codes)
    ]
    return SlotCandidateSet(
        action_id=action_id,
        parameter=parameter,
        field=_FIELD_BY_PARAMETER[parameter],
        chosen=None,
        top_k=top_k,
        needs_review=True,
        review_reason=AI_REVIEW_REASON,
    )


def _slot_codes(m: MotionSuggestion) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    if m.b1:
        out.append(("B", [m.b1]))
    if m.g2:
        out.append(("G", [m.g2]))
    if m.p5 is not None:
        if m.p5.base:
            out.append(("P", [m.p5.base]))
        if m.p5.addon:
            out.append(("P_ADDON", list(m.p5.addon)))
    if m.m3:
        out.append(("M", [m.m3]))
    if m.x4:
        out.append(("X", [m.x4]))
    if m.i5:
        out.append(("I", [m.i5]))
    return out


def _dropped_slots(m: MotionSuggestion) -> list[str]:
    """ai_service 給了、但 compile 沒有地方放的東西（不進 plan，也不是 routing reason，只是說明）。"""
    out: list[str] = []
    if m.b4:
        out.append("b4")  # compile 只有一個 B 參數（b1）
    for name in ("a0", "a3", "a6"):
        a = getattr(m, name)
        if a is None:
            continue
        if a.kind in ("foot", "twist"):
            out.append(f"{name}.{a.kind}")  # compile 沒有對應分支
        if a.magnitude_cm_hint is not None or a.magnitude_deg_hint is not None:
            out.append(f"{name}.magnitude_hint")  # 估計值不進 TMU，須經人確認才能成為量測值
    return out


def _has_return_a(m: MotionSuggestion) -> bool:
    return any(a is not None and a.kind == "return" for a in (m.a0, m.a3, m.a6))


def build_plan_from_motions(
    motions: Sequence[MotionSuggestion],
    *,
    source_text: str,
    normalized_text: str,
    language: Language,
    source_ref: SourceRef,
    result_issues: Sequence[str] = (),
    known_hand: Hand | None = None,
    allow_lists: AllowLists | None = None,
) -> AiPlanBuild:
    """把 ai_service 的 motion 建議轉成 plan 與候選。

    `known_hand`：MOST 已知的手別（Excel 欄或使用者輸入）。給了才比對；ai_service 的手別只作提示，不一致標審核。
    `allow_lists`：給了就再擋一次（縱深防禦；mapper 已擋過）——不在目標 rule-set 的 code 不進候選，標 `ai_unknown_code`。

    `motions` 的 `index` 必須互不相同（mapper 以順序編號）；重複是呼叫端的 bug → `ValueError`。
    """
    if len({m.index for m in motions}) != len(motions):
        raise ValueError("MotionSuggestion.index must be unique within one result")
    ordered = sorted(motions, key=lambda m: m.index)
    actions: list[PlannedAction] = []
    candidates: list[SlotCandidateSet] = []
    labels: dict[str, MotionLabel] = {}
    reasons: list[str] = []
    dropped: list[str] = []

    def add(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    if ordered:
        # ai_service 的回應沒有 evidence span（ADR-037 D3）
        add(REASON_NO_EVIDENCE)

    for n, m in enumerate(ordered, start=1):
        action_id = f"a{n}"
        actions.append(
            PlannedAction(
                action_id=action_id,
                action_type=derive_action_type(m),
                sequence_order=n,
                roles={},
                evidence=[],
                notes=AI_PLANNER_NOTE,
            )
        )
        labels[action_id] = MotionLabel(sub_activity=m.sub_activity, object_text=m.object_text, hand_hint=m.hand_hint)
        for parameter, codes in _slot_codes(m):
            if allow_lists is not None:
                allowed = [c for c in codes if c in allow_lists.get(parameter, ())]
                if len(allowed) != len(codes):
                    add(REASON_UNKNOWN_CODE)
                codes = allowed
                if not codes:
                    continue
            candidates.append(_candidate_set(action_id, parameter, codes))
            if parameter == "P_ADDON" and len(codes) > 1:
                add(REASON_ADDON_TRUNCATED)
        dropped.extend(f"{action_id}:{what}" for what in _dropped_slots(m))
        if any(i.startswith(f"{ISSUE_UNKNOWN_CODE}:") for i in m.issues):
            add(REASON_UNKNOWN_CODE)
        if _has_return_a(m) or any(i.startswith(f"{ISSUE_A_RETURN_NEEDS_REVIEW}:") for i in m.issues):
            add(REASON_RETURN_A)
        if known_hand is not None and m.hand_hint is not None and m.hand_hint != known_hand:
            add(REASON_HAND_MISMATCH)

    if any(i.startswith(f"{ISSUE_UNKNOWN_CODE}:") for i in result_issues):
        add(REASON_UNKNOWN_CODE)

    plan = WorkInstructionPlan(
        source_text=source_text,
        normalized_text=normalized_text,
        language=language,
        source_ref=source_ref,
        actions=actions,
        dependencies=[],
        unresolved=[],
    )
    return AiPlanBuild(plan=plan, candidates=candidates, reasons=reasons, labels=labels, dropped=dropped)


def promote_for_preview(
    candidates: Sequence[SlotCandidateSet], allow_lists: AllowLists
) -> list[SlotCandidateSet]:
    """**只用來算預覽**：回傳完整複本，`chosen` 是空、第一候選來源為 `ai_service` 且在目標 rule-set 內者，
    暫時把第一候選當 chosen。原本的 `candidates` 與複本不共用任何物件，存檔與回應仍是 `chosen=None`。

    ⚠️ 這個函式的**輸出不得存檔、不得回 API、不得當成「已採用」**：採用是人工動作（實作計畫 S4），
    要由人寫入 `chosen`，並重跑 compile 與引擎，而不是沿用預覽。

    孤立的 P addon（同一個 action 沒有可提升的 P base）不提升：addon 沒有 base 沒有意義，
    提升了 compile 會組出沒有 base 的 P 位置。
    """
    def promotable(c: SlotCandidateSet) -> OptionCandidate | None:
        first = c.top_k[0] if c.top_k else None
        if (
            c.chosen is None
            and first is not None
            and first.source == "ai_service"
            and first.option_code in allow_lists.get(c.parameter, ())
        ):
            return first
        return None

    actions_with_base = {c.action_id for c in candidates if c.parameter == "P" and promotable(c) is not None}
    out: list[SlotCandidateSet] = []
    for c in candidates:
        first = promotable(c)
        if first is not None and (c.parameter != "P_ADDON" or c.action_id in actions_with_base):
            out.append(c.model_copy(deep=True, update={"chosen": first.model_copy()}))
        else:
            out.append(c.model_copy(deep=True))
    return out


def preview_drafts(
    plan: WorkInstructionPlan,
    candidates: Sequence[SlotCandidateSet],
    *,
    rule_set_code: str,
    allow_lists: AllowLists,
    face_hit_params: Mapping[str, frozenset[str]] | None = None,
) -> list[CycleDraft]:
    """用 ai_service 的候選算預覽 draft（compile 仍是單一權威；TMU 由引擎之後算，不在這裡）。

    每份 draft 都帶 `ai_candidate_preview`：它進 routing reasons 並擋 auto，也讓審核端知道這份不是決定。
    """
    drafts = compile_plan(
        plan,
        promote_for_preview(candidates, allow_lists),
        rule_set_code=rule_set_code,
        allow_lists={k: set(v) for k, v in allow_lists.items()},
        face_hit_params=face_hit_params,
    )
    return [
        d if REASON_CANDIDATE_PREVIEW in d.issues else d.model_copy(update={"issues": [*d.issues, REASON_CANDIDATE_PREVIEW]})
        for d in drafts
    ]
