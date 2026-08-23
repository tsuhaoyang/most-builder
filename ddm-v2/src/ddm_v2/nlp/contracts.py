"""wi-plan-v1 契約：MOST-neutral 作業計畫與候選。

上游：docs/architecture/wi-ai-parser-system-spec.md §7
實作：docs/llm/wi-ai-parser-implementation-spec.md §5 / §5.2 / 附錄 A
規則：欄位只增不改（ADR-011）；LLM structured output 只產生 PlannerOutput。

ADR-033（accepted 2026-08-23）P1 收窄後的責任分層（spec §5.2、§7.5.1）：

- **契約**（`validate_planner_output`）只驗**結構完整性**：`action_id` 唯一、
  `sequence_order` 連續、role `text` 是 `normalized_text` 的字面子字串、
  dependency 端點存在、role key 在封閉集合內。
- **adapter 邊界**（`prepare_planner_payload` ＋ `sanitize_planner_output`）**寬容**：
  剝未知鍵、剝數值、丟壞 dependency、推導 evidence offset——逐項記名，**不 raise**。
- 整筆失敗只剩三種（判在 `llm_planner`）：JSON 解析失敗、`actions` 全空、
  `sequence_order` 不連續。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

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

# ADR-033 D3：`status` 不再向模型索取（`RoleValue.status` 改為選填）。列舉本身保留
# ——既有 gold 與既有 `ai_parse_runs.plan` 都帶著這些值，收窄列舉＝毀相容（ADR-011）。
RoleStatus = Literal["explicit", "inferred", "default", "explicit_unresolved", "missing"]

# ADR-033 D5：`precedes` 零消費者、不再索取；型別保留（ADR-011 只增不改）。
DependencyType = Literal["uses_tool", "tool_held_for", "same_object", "precedes"]

ROLE_KEYS = frozenset({
    "hand",
    "object",
    "tool",
    "tool_ref",
    "from_location",
    "destination",
    # ADR-033 D2／spec §5.2.2：「返回（若有）」→ A6。契約先加（P1），
    # prompt 索取（P2）與 compiler 分支（P3）另階段——今天沒有任何產生者。
    "return_to",
    "distance",
    "quantity",
    "process_kind",
    "inspect_kind",
})

_LEGAL_DEPENDENCY_TYPES = frozenset(get_args(DependencyType))

# 附錄 A6：前後端同源顯示檔位（非校準機率）
CONFIDENCE_BANDS = {"high": 0.9, "mid": 0.6}


class EvidenceSpan(BaseModel):
    """對 normalized_text 的字元 offset（半開區間 [start, end)）。

    ADR-033 D4：**offset 由我方推導，不由模型報**（`locate_evidence_spans`）。
    因此 `start`/`end` 改為選填——模型只需要給 `text`。經過
    `sanitize_planner_output` 之後兩者恆為 int（定位不到的 action 會被剔除），
    下游（`most_compiler.policies` 的 evidence 窗）拿到的一律是具體座標。
    """

    start: int | None = None
    end: int | None = None
    text: str


class RoleValue(BaseModel):
    """角色片語。

    ADR-033 D1：`value`／`unit` 不再向模型索取，adapter 邊界剝除並記
    `role_numeric_stripped`（欄位保留給非 LLM 來源：CSV／匯入欄／IE 手填）。
    ADR-033 D3：`status` 不再索取，改為選填；「這個詞有沒有出處」改由
    「`text` 是 `normalized_text` 的字面子字串」這個**可機械驗證的事實**回答。
    """

    text: str | None = None
    value: float | int | None = None
    unit: str | None = None
    status: RoleStatus | None = None
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
    """回傳 errors；空列表＝通過。**只驗結構完整性**（ADR-033 D6／spec §7.5.1）。

    驗什麼：`action_id` 唯一、`sequence_order` 連續、role key 在封閉集合內、
    role `text` 是 `normalized_text` 的字面子字串（D3 的單一不變式）、
    dependency 端點存在；evidence 的 offset **只在模型有給時**驗（D4 之後
    offset 由 `locate_evidence_spans` 推導，沒給是合法的）。

    **不再驗**（D3 廢止，連同 `status` 一起）：`explicit_without_value`／
    `explicit_without_evidence`／`inferred_without_ref`／`action_ref_unknown`。
    那四條驗的是模型的**自我宣告**（`status`）；子字串驗的是**事實**。
    舊的 `_role_covered_by_evidence` 是**雙向**比對（`text in ev.text` 或
    `ev.text in text`），所以「role.text 是 evidence 的超集」可以夾帶原文沒有的
    數字通過（資安 S-2 的繞過 B）——新不變式直接比對全句原文，沒有這個洞。

    ⚠️ 本函式**不決定**誰要整筆失敗：adapter 邊界（`sanitize_planner_output`）
    會先把可剝的都剝掉，剩下的錯誤才代表輸出真的壞了。整筆失敗的三種情形判在
    `llm_planner._parse_sanitize_validate`。
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
        for ev in action.evidence:
            if ev.start is None and ev.end is None:
                continue  # D4：模型不必給 offset，由我方推導
            if ev.start is None or ev.end is None:
                errors.append(f"evidence_offset_partial:{action.action_id}")
                continue
            if not (0 <= ev.start < ev.end <= nlen):
                errors.append(f"evidence_offset_oor:{action.action_id}")
                continue
            if normalized_text[ev.start:ev.end] != ev.text:
                errors.append(f"evidence_text_mismatch:{action.action_id}")
        for role_key, role in action.roles.items():
            if role_key not in ROLE_KEYS:
                errors.append(f"unknown_role_key:{action.action_id}:{role_key}")
                continue
            if role.text is not None and role.text not in normalized_text:
                errors.append(f"role_text_not_in_source:{action.action_id}:{role_key}")
    return errors


def _find_all(haystack: str, needle: str) -> list[int]:
    """所有出現位置（**含重疊**）；`str.count` 只算非重疊，會低估歧義。"""
    starts: list[int] = []
    pos = haystack.find(needle)
    while pos != -1:
        starts.append(pos)
        pos = haystack.find(needle, pos + 1)
    return starts


def _pick_occurrence(
    normalized_text: str, text: str, cursor: int, used: set[int]
) -> int | None:
    """D4 的定位規則；回傳起點，定位不到回 None。

    1. 恰好出現一次 → 直接定位（唯一出現就是事實，不受 cursor 影響）。
    2. 出現多次 → 取**第一個 ≥ cursor 且未被用過**的位置（由左至右單調指派）；
       都在 cursor 之前就退而取第一個未被用過的；全被用過＝定位不到。
    3. 找不到（模型改寫／幻覺）／空字串 → None，由呼叫端剔除該 action。
    """
    if not text:
        return None
    starts = _find_all(normalized_text, text)
    if not starts:
        return None
    if len(starts) == 1:
        return starts[0]
    free = [s for s in starts if s not in used]
    if not free:
        return None
    forward = [s for s in free if s >= cursor]
    return forward[0] if forward else free[0]


def locate_evidence_spans(
    actions: list[PlannedAction],
    normalized_text: str,
    *,
    details: list[StripDetail] | None = None,
) -> tuple[dict[str, list[EvidenceSpan]], set[str], list[str]]:
    """ADR-033 D4：evidence 的 offset **由我方算**，模型只給 `text`。

    回傳 `(action_id → 定位後的 spans, 定位不到的 action_id, 診斷 reasons)`。

    為什麼不再信模型報的 offset：worklog §8 量到 `evidence_offset_repaired` 在
    plan-v1.3 兩輪各觸發 62／63 次（55 案）——幾乎每一份輸出都要修。模型很會抄
    原文、很不會數字元位置；`text` 是可驗證的資料、offset 是可推導的座標。

    多次出現時依 `sequence_order` **由左至右單調指派**、同一位置不重用。
    U-4（User 2026-08-23）裁決「應該不會有倒裝」——動作順序與文字順序一致，
    因此**不掛假設旗標、不擋 auto**（ADR 原文的 `evidence_span_assumed_order`
    設計因這條裁決作廢）。

    診斷 `evidence_offset_repaired` 只在**模型有給 offset 且與推導結果不同**時記，
    它已不是防線、純粹是「模型多常數錯」的觀測量（不併入 `unresolved`）。

    `details` 是**只給觀測端的旁通道**（見 `StripDetail`）：傳了就把定位不到的
    evidence 片語**原文**收進去，答「模型寫的是什麼」。不傳＝不收集，行為完全不變。
    """
    located: dict[str, list[EvidenceSpan]] = {}
    unlocatable: set[str] = set()
    diagnostics: list[str] = []
    cursor = 0
    used: set[int] = set()
    for action in sorted(actions, key=lambda a: a.sequence_order):
        # 逐 action 試算，**整個成功才提交** cursor/used——半途失敗的 action 會被
        # 剔除，它佔用的位置不該擋住後面的 action（否則一個幻覺會連鎖）。
        spans: list[EvidenceSpan] = []
        span_diagnostics: list[str] = []
        taken: set[int] = set()
        next_cursor = cursor
        ok = True
        for ev in action.evidence:
            start = _pick_occurrence(normalized_text, ev.text, next_cursor, used | taken)
            if start is None:
                diagnostics.append(f"evidence_text_not_found:{action.action_id}")
                if details is not None:
                    details.append(
                        StripDetail(
                            action_id=action.action_id,
                            reason="evidence_text_not_found",
                            text=ev.text,
                        )
                    )
                ok = False
                break
            end = start + len(ev.text)
            if (ev.start, ev.end) not in ((None, None), (start, end)):
                span_diagnostics.append(
                    f"evidence_offset_repaired:{action.action_id}:"
                    f"[{ev.start},{ev.end})->[{start},{end})"
                )
            spans.append(ev.model_copy(update={"start": start, "end": end}))
            taken.add(start)
            next_cursor = max(next_cursor, end)
        if ok:
            located[action.action_id] = spans
            diagnostics.extend(span_diagnostics)
            used |= taken
            cursor = next_cursor
        else:
            unlocatable.add(action.action_id)
    return located, unlocatable, diagnostics


def prepare_planner_payload(data: Any) -> tuple[Any, list[str]]:
    """`PlannerOutput.model_validate` **之前**的寬容前處理（ADR-033 D5）。

    只做一件事：丟掉**型別不合法**的 dependency 並記 `dependency_dropped`。

    為什麼一定要在 model_validate 之前：`ActionDependency.type` 是 Literal，
    模型自創一個 type（實測 `same_hand`）會讓整份 JSON 在 pydantic 就炸掉，
    連同語意正確的切分一起丟——`g13` 就是這樣被打掉的。丟一條 dependency 的
    代價遠小於丟一份切分。

    ⚠️ 邊界：其餘型別錯誤（`roles` 不是物件、`action_type` 不在列舉…）仍由
    pydantic 拒絕＝整筆失敗。這裡不做泛用型別修補——那會變成靜默改寫模型輸出，
    而且無從記名。
    """
    if not isinstance(data, dict) or "dependencies" not in data:
        return data, []
    deps = data.get("dependencies")
    if deps is None:
        return data, []
    if not isinstance(deps, list):
        return {**data, "dependencies": []}, [f"dependency_dropped:not_a_list:{type(deps).__name__}"]
    kept: list[Any] = []
    reasons: list[str] = []
    for i, dep in enumerate(deps):
        if not isinstance(dep, dict):
            reasons.append(f"dependency_dropped:{i}:not_an_object")
            continue
        dep_type = dep.get("type")
        if dep_type not in _LEGAL_DEPENDENCY_TYPES:
            reasons.append(f"dependency_dropped:{i}:illegal_type={dep_type!r}")
            continue
        if not isinstance(dep.get("from_action"), str) or not isinstance(
            dep.get("to_action"), str
        ):
            reasons.append(f"dependency_dropped:{i}:bad_endpoint")
            continue
        kept.append(dep)
    if not reasons:
        return data, []
    return {**data, "dependencies": kept}, reasons


@dataclass(frozen=True)
class StripDetail:
    """被剝除內容的**觀測明細**——刻意**不是**契約模型（ADR-033 P1 補測 2026-08-23）。

    為什麼需要它：P1 之後「模型輸出有問題」不再整筆退回，於是
    `planner_raw_rejected`（只在**硬失敗**時留存）也跟著失去對象——觀察期量到
    `role_text_not_in_source` 4 次，卻查不出**被剝掉的字是什麼**，於是「模型幻覺」
    與「不變式過嚴、誤殺了合法改寫」分不開。T-16 的裁決卡在這裡，而 P2 一改 prompt
    就更分不清（prompt 與契約兩個變因會疊在一起）。

    為什麼**不塞進 reasons**：`sanitize_planner_output` 的 reasons 會把冒號前的前綴
    併進 `plan.unresolved` → `routing_reasons` → **落 DB 並回 API**。被剝的 role text
    是**模型可控字串**，把它接進 reason 字串等於讓它逐字流過那條路。

    ⚠️ **但那條路不是乾淨的，本設計也沒有把它變乾淨**（資安複審 2026-08-23 更正）：
    `PlannerOutput.unresolved` 本身就是模型可控的 `list[str]`，而
    `sanitize_planner_output` 的 `unresolved = list(output.unresolved)` **逐字沿用它**
    ——模型寫什麼就流什麼到 `routing_reasons`／`ai_parse_runs`／API。那是既有的
    **S-5，至今未修**（治本是讓 `routing.ROUTING_REASONS` 從宣告變成真正的過濾器，
    那會改變既有 reason 的值域，屬獨立切片）。所以這裡的決定不是「避免開一個新的
    洩漏面」，而是**不再多開一條**：既有的洞已經夠一票了，不該再加一個入口，
    而且被剝的值在生產環境根本沒有消費者。
    **讀到這段的人請不要據此以為 `routing_reasons` 可以不經逸出地渲染。**

    明細因此走**另一條只給觀測端的通道**：呼叫端顯式傳 `details` 才收集，
    生產路徑（`wi_ai_service`）不傳，值只會出現在評測報告。

    為什麼是 dataclass 而不是 `BaseModel`：這**不屬於 `wi-plan-v1`**。做成契約模型
    會讓它看起來可以塞進 `WorkInstructionPlan`／`ai_parse_runs`，那正是上一段要避免
    的事；它也沒有 `schema_version`、不參與 ADR-011 的欄位演進承諾。

    `reason` 與 sanitize reasons 的代碼同名（`role_text_not_in_source`／
    `role_numeric_stripped`／`role_key_dropped`／`evidence_text_not_found`），
    但**不帶** `action_id` 後綴——那是 reason 字串的格式，這裡是結構化欄位。
    """

    action_id: str
    reason: str
    role_key: str | None = None   # evidence 類的剝除沒有角色
    text: str | None = None       # 被剝掉的原文片語／evidence 片語（模型可控字串）
    value: float | int | None = None
    unit: str | None = None


def _record(
    details: list[StripDetail] | None,
    action_id: str,
    reason: str,
    role_key: str,
    role: RoleValue,
) -> None:
    """把剝掉的東西收進觀測旁通道；`details is None` ＝呼叫端沒訂閱，什麼都不做。"""
    if details is None:
        return
    details.append(
        StripDetail(
            action_id=action_id,
            reason=reason,
            role_key=role_key,
            text=role.text,
            value=role.value,
            unit=role.unit,
        )
    )


def _sanitize_roles(
    action: PlannedAction,
    normalized_text: str,
    details: list[StripDetail] | None = None,
) -> tuple[dict[str, RoleValue], list[str]]:
    """逐項剝除（ADR-033 D1／D3），**不 raise**：

    - 未知鍵 → 整個角色丟棄，記 `role_key_dropped`；
    - `text` 不是 `normalized_text` 的字面子字串（模型改寫／幻覺）→ 記
      `role_text_not_in_source`；該角色若還帶 `action_ref`（結構參照不是片語）
      則只剝掉 `text`，否則整個丟棄；
    - `value`／`unit` → 一律剝除，記 `role_numeric_stripped`。距離／數量／秒數
      收窄後只能來自對**原文**的確定性抽取或匯入欄（ADR-033 D1／D7）。

    `details` 是**只給觀測端的旁通道**（見 `StripDetail`）：傳了就把被剝掉的**值本身**
    收進去，不傳＝不收集。**判準一條都不受它影響**——它只在已經決定要剝之後被追加。
    """
    roles: dict[str, RoleValue] = {}
    reasons: list[str] = []
    for key, role in action.roles.items():
        if key not in ROLE_KEYS:
            reasons.append(f"role_key_dropped:{action.action_id}:{key}")
            _record(details, action.action_id, "role_key_dropped", key, role)
            continue
        if role.text is not None and role.text not in normalized_text:
            reasons.append(f"role_text_not_in_source:{action.action_id}:{key}")
            _record(details, action.action_id, "role_text_not_in_source", key, role)
            if not role.action_ref:
                continue
            role = role.model_copy(update={"text": None})
        if role.value is not None or role.unit is not None:
            reasons.append(f"role_numeric_stripped:{action.action_id}:{key}")
            _record(details, action.action_id, "role_numeric_stripped", key, role)
            role = role.model_copy(update={"value": None, "unit": None})
        roles[key] = role
    return roles, reasons


def sanitize_planner_output(
    output: PlannerOutput,
    *,
    normalized_text: str,
    carried_reasons: list[str] | None = None,
    details: list[StripDetail] | None = None,
) -> tuple[PlannerOutput, list[str]]:
    """adapter 邊界的寬容前處理（spec §7.5.1 的第一層）。

    做四件事，全部**逐項記名、不 raise**：

    1. **evidence 定位**（D4，`locate_evidence_spans`）：定位不到的 action 剔除，
       沿用既有 `planner_invented_action` 語意。
    2. **角色剝除**（D1／D3，`_sanitize_roles`）：未知鍵、原文沒有的片語、數值。
    3. **既有兩條語意防線不變**（spec §7.5）：非 `composite_unknown` 而無 evidence
       的 action 剔除（`planner_invented_action`）；`tool_ref` 未指向排序在前的
       `acquire` 則降為 missing（`tool_state_violation`）。它們判的是「計畫本身有
       沒有缺口」，不是「模型的自我宣告可不可信」，不在收窄範圍內。
    4. 剔除後重新編號，並丟掉端點已不存在的 dependency。

    `carried_reasons`＝adapter 在 `model_validate` **之前**就剝掉的項目
    （`prepare_planner_payload` 的 `dependency_dropped`）。它們一樣要進
    `unresolved` 才擋得住 auto，但那時還沒有 `PlannerOutput` 可以掛。

    回傳 (sanitized, reasons)。reasons 分兩類，**只有語意／剝除類會併進 unresolved**：

    - 語意與剝除（`planner_invented_action`／`tool_state_violation`／
      `role_key_dropped`／`role_text_not_in_source`／`role_numeric_stripped`／
      `dependency_dropped`）：代表計畫少了東西或被我方改過，併入 `unresolved`
      ——`routing._eligible_auto` 見 `unresolved` 非空即拒 auto，覆核者也看得到。
    - evidence offset 診斷（`evidence_offset_repaired`）：**不併入**——推導出來的
      座標不是未解的語意缺口，塞進 unresolved 會讓每一筆都被踢去人工覆核。

    `details`＝**被剝掉的值本身**的旁通道（見 `StripDetail`），與 reasons 是兩條路：
    reasons 的前綴會進 `unresolved`（落 DB／回 API），所以**模型可控的字串一律不進
    reasons**；`details` 只有顯式訂閱的呼叫端（評測）拿得到。不傳＝不收集，
    行為與判準完全不變。
    """
    reasons: list[str] = list(carried_reasons or [])
    # offset 診斷與語意防線分開累積：只有 reasons 會併進 unresolved（見 docstring）
    diagnostics: list[str] = []
    located, unlocatable, locate_diagnostics = locate_evidence_spans(
        output.actions, normalized_text, details=details
    )
    kept: list[PlannedAction] = []
    for action in output.actions:
        if action.action_type != "composite_unknown" and not action.evidence:
            reasons.append(f"planner_invented_action:{action.action_id}")
            continue
        if action.action_id in unlocatable:
            # evidence 的 text 在原文定位不到＝模型改寫或幻覺（D4 規則 3）。
            # 代碼前綴沿用 `planner_invented_action`（unresolved 的鍵不變），
            # 後綴留下**是哪一種**——「無 evidence」與「evidence 是幻覺」是兩種
            # 失敗形態，報告裡分不出來就查不出模型到底壞在哪。
            reasons.append(f"planner_invented_action:{action.action_id}:evidence_text_not_found")
            continue
        evidence = located.get(action.action_id, [])
        roles, role_reasons = _sanitize_roles(action, normalized_text, details)
        reasons.extend(role_reasons)
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
        kept.append(action.model_copy(update={"roles": roles, "evidence": evidence}))

    # 定位診斷只留下 offset 推導那類；`evidence_text_not_found` 已經以
    # `planner_invented_action:<id>:evidence_text_not_found` 記過，重複列會讓
    # 同一次剔除在報告的 by_code 裡被數兩遍。
    diagnostics.extend(
        r for r in locate_diagnostics if not r.startswith("evidence_text_not_found:")
    )

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
        else:
            reasons.append(f"dependency_dropped:{d.from_action}->{d.to_action}:dropped_endpoint")

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
    return sanitized, reasons + diagnostics
