"""Planner 段評測（text → plan）。

規格出處（**全檔名**，兩份 spec 的 §14.4/§19 是不同章節，不可簡寫）：

- `docs/architecture/wi-ai-parser-system-spec.md` §14.4「指標與上線門檻」
  （Plan 層 action-count exact match、boundary/dependency F1）與 §19「分階段交付」
  （P2 退出條件）。
- `docs/llm/wi-ai-parser-implementation-spec.md` 的 §14.4 是 Playwright e2e、
  §19 是未決事項——與本模組無關。

與 `gold_eval.py` 的 compile 段互補、兩段並列：

- compile 段（gold_eval）：gold **plan 為輸入** → link → compile → engine，驗 compiler+engine；
- planner 段（本模組）：gold **原文為輸入** → planner → 與 gold plan 比對，驗 text→plan。

指標操作型定義（spec 只給指標名與門檻，未給計算細節；採以下定義並隨報告輸出）：

1. **plan action-count exact match**：`len(pred.actions) == len(gold.plan.actions)`
   的案例比例（每案 0/1，取平均）。action_type 不參與此指標。
2. **boundary span F1**（報告 key＝`boundary_span_f1`）：以
   `plan.actions[*].evidence` 的 `(start, end)` 半開區間（對 normalized_text 的
   字元 offset）為 action 邊界標註。predicted span 與 gold span **嚴格相等**
   （start 與 end 都相同）才算 TP；跨案例 micro 聚合（加總 TP/FP/FN 後算
   P/R/F1），另附 per-case F1。span 不歸屬特定 action_id（比對的是「切在哪裡」，
   不是「切給誰」）。
3. **dependency F1：未實作**（報告固定輸出 `dependency_f1: null` 並附原因）。
   spec §14.4 的門檻列是「boundary/**dependency** F1 ≥ 0.90」合為一項；
   `boundary_span_f1` 只涵蓋前半，**不得單獨引用為該列達標**。未實作原因見
   `DEPENDENCY_F1_NOTE`。

自我指涉排除（Plan 層指標的證據力守門）：

- gold 檔若標 `plan_origin=<planner>_preannotation` 且 `ie_modified` 非 true，
  代表 gold plan 就是受測 planner 的預標註輸出、IE 原樣核准——planner 給自己
  打分沒有證據力，這類案例**排除出 Plan 層指標**（action_count_accuracy 與
  boundary span F1 的分母都不含它們），summary 的 `self_referential_excluded`
  明列筆數、名單與理由。IE 改過（`ie_modified: true`）的案例是真實 ground
  truth，照常計入。compile 段（gold_eval）不受此排除影響。

boundary 標註可用性規則（缺就點名，不硬湊）：

- `composite_unknown` 依 `contracts.sanitize_planner_output` 可合法無 evidence，
  不產生 span、不算缺標註。
- 其他 action_type 的 gold action 若無 evidence → 該案 `boundary_annotated=False`，
  排除於 F1 聚合並列入 `unannotated_cases`（缺 `plan.actions[*].evidence`）。
- gold evidence offset 越界、slice 與 text 不符、或 evidence 缺 `start`/`end` →
  標註無效（`ok=False`、具名 `gold_*` 錯誤），同樣排除於 F1 聚合。
  注意 Python slice 會靜默 clamp，越界不能靠 slice 相等看出。
- pred 與 gold 的 normalized_text 不同 → span 無共同座標系，
  `boundary_comparable=False`：gold span 全記 FN、pred span 全記 FP（誠實計分，不略過）。
- 兩邊**皆無 span**（gold 純 composite_unknown 無 evidence、planner 也不給
  evidence）→ `boundary_span_f1=None`、`boundary_trivially_empty=True`，
  聚合排除並在 summary 的 `trivially_empty_cases` 點名。**不給 1.0**：
  否則「全部 abstain、不給 evidence」的 planner 會在這類案例拿滿分
  （指標獎勵棄權，可被 game）。

Planner 個案失敗隔離（`planner_failed`）：

- planner 對單一案例拋例外（LLM schema retry 用盡的 `PlannerError`、timeout、連線失敗…）
  **不再中止整批**：該案記 `planner_failed=True`、`planner_error`（例外訊息，
  **URL 一律遮蔽**——見 `_redact_urls`）與 `planner_error_codes`
  （`PlannerError.errors` 的錯誤碼前綴，例 `evidence_offset_oor`），繼續評測
  其餘案例——否則「失敗形態的分布」量不到。
- 失敗案例**計入 Plan 層指標且記為漏**（`pred_action_count=0`、
  `action_count_match` 僅在 gold 也是 0 個 action 時為真、gold span 全記 FN、
  無 FP），不是排除。排除會讓「難的案例失敗、簡單的案例得分」變成分數上升，
  指標就獎勵了崩潰。
- `ok` 仍只反映 **gold 標註**是否可用（planner 失敗不是 gold 的問題），因此
  `wi_ai_eval.py` 的退出碼契約維持原義；但「全部案例都失敗」＝管道壞掉而非量測結果，
  由 CLI 另行判為失敗（見該檔 docstring）。
- 例外**帶著模型回應**時（`PlannerError.raw`）另記 `planner_raw_rejected`＝
  **被拒絕的原始回應本文**（遮蔽後截斷，見 `_sanitize_rejected_raw`）。只記錯誤碼的話
  「那份輸出的切分到底對不對」事後無從回答：ADR-033 §1.4(c) 的 `g07`／`g23`／`g46`
  正是這個形狀（模型都輸出了 `a2`，而 gold 是單一 action），契約放寬後它們會從
  「硬失敗」變成「**切分錯誤**」——那才是要量的東西。沒有回應的失敗（timeout、
  連線失敗、rule planner 的例外）恆為 `None`；回應是空字串則記 `""`——兩者不同，
  不可混為一談。

DB 依賴：rule_based 路徑**不需要 DB** —— planner 只需 gold 檔內 `synthetic_synonyms`
（`RuleBasedParser` 的 GM/CM 判型關鍵字是程式常數；讀 motion_templates/synonyms 的
`SlotLinker` 屬 compile 段，不在 text→plan 路徑上）。LLM 路徑僅供顯式 flag 使用，
CI 與預設一律 rule_based。
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

from pydantic import ValidationError

from ddm_v2.nlp.contracts import SourceRef, WorkInstructionPlan
from ddm_v2.nlp.gold_eval import default_gold_dir, load_gold_cases
from ddm_v2.nlp.planner_ports import PlannerError
from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.nlp.rule_plan_adapter import plan_from_rule_result

RULE_PLANNER_NAME = "rule_based_v1"

# 規格全檔名（引用時不可只寫「spec §14.4」——implementation spec 的 §14.4 是別的章節）
SPEC_DOC = "docs/architecture/wi-ai-parser-system-spec.md"

# gold/draft 檔的 `plan_origin` 值（scripts/gold_harvest.py 寫入；summarize 排除比對用）
PREANNOTATION_ORIGIN_SUFFIX = "_preannotation"


def planner_preannotation_origin(planner: str) -> str:
    """`plan_origin` 的規範值：<planner>_preannotation（預標註草稿的 plan 出處標記）。"""
    return f"{planner}{PREANNOTATION_ORIGIN_SUFFIX}"


SELF_REFERENTIAL_EXCLUSION_REASON = (
    "這些案例的 gold plan 即受測 planner 的預標註輸出（plan_origin=<planner>_preannotation）"
    "且 IE 未修改內容（ie_modified≠true）：拿 planner 自己的輸出當標準答案評 planner"
    "＝自我指涉，對 Plan 層指標零證據力，故排除。IE 實際改過（ie_modified=true）的"
    "案例是真實 ground truth，照常計入；compile 段不受影響（驗 compiler+engine，非 planner）。"
)

# `docs/architecture/wi-ai-parser-system-spec.md` §14.4 / §19 P2 退出條件
# （報告對照用；本模組不以此決定成敗）。
# 注意：spec §14.4 該列原文是「boundary/**dependency** F1 ≥ 0.90」；本實作只算
# boundary span F1，故 key 取 `boundary_span_f1`，dependency F1 未實作
# （見 DEPENDENCY_F1_NOTE）。boundary_span_f1 達 0.90 **不等於** §14.4 該列達標。
SPEC_TARGETS = {
    "action_count_exact_match": 0.95,
    "boundary_span_f1": 0.90,
}

DEPENDENCY_F1_NOTE = (
    f"未實作（{SPEC_DOC} §14.4 門檻列原文為「boundary/dependency F1」合為一項，"
    "boundary_span_f1 只涵蓋前半）。未實作原因："
    "(1) action counts 不齊時 pred↔gold 的 action 對齊無定義，dependency 端點無從對應；"
    "(2) rule_based_v1 永遠回空 dependencies（gold g02 有 tool_held_for，真的算恆為 0）。"
    "實作並定義對齊規則前，不得以 boundary_span_f1 單獨宣告 §14.4 該列達標。"
)

RULE_DEGENERATE_NOTE = (
    "退化分數警告：rule_based_v1 恆輸出單一 action、evidence 恆為整句 "
    "[0, len(normalized_text))、dependencies 恆空——本節分數反映 gold 集形狀"
    "（單 action 且整句標註的案例佔比），不是 planner 的切分能力，"
    "不得引用為 P2 進度或能力證據。"
    "另：由本 planner 預標註、IE 未修改即轉正（ie_modified=false）的案例已排除於 "
    "Plan 層指標（見 self_referential_excluded）——若轉正後指標往 1.0 跳，"
    "那是自我指涉假象（planner 給自己打分），不是能力提升。"
)

# data(gold case dict) → 預測 plan
PlannerFn = Callable[[dict], Awaitable[WorkInstructionPlan]]


class GoldCaseError(ValueError):
    """gold case 本身不完整/不一致（非 planner 品質問題）。"""


@dataclass
class GoldLoadError:
    """gold 檔在載入/結構層即無效（malformed JSON、缺 plan…）；點名檔案、進報告。"""

    file: str
    error: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def load_gold_cases_checked(
    gold_dir: Path | None = None,
) -> tuple[list[tuple[Path, dict]], list[GoldLoadError]]:
    """載入 gold 檔並把「檔案壞掉」轉成具名 `gold_case_invalid` 錯誤（不 traceback）。

    只擋結構層問題（JSON 解析、頂層形狀、`plan` 可通過 wi-plan-v1 schema）；
    標註層問題（offset 越界、text 不符…）留給 `evaluate_planner_case` 逐案點名。
    """
    root = gold_dir or default_gold_dir()
    cases: list[tuple[Path, dict]] = []
    load_errors: list[GoldLoadError] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            load_errors.append(
                GoldLoadError(file=path.name, error=f"gold_case_invalid:malformed_json:{exc}")
            )
            continue
        if not isinstance(data, dict):
            load_errors.append(
                GoldLoadError(
                    file=path.name,
                    error=f"gold_case_invalid:not_an_object:top-level is {type(data).__name__}",
                )
            )
            continue
        plan = data.get("plan")
        if not isinstance(plan, dict):
            load_errors.append(
                GoldLoadError(file=path.name, error="gold_case_invalid:missing_plan:缺 `plan` 物件")
            )
            continue
        try:
            WorkInstructionPlan.model_validate(plan)
        except ValidationError as exc:
            details = exc.errors()
            loc = ".".join(str(p) for p in details[0]["loc"]) if details else ""
            msg = details[0]["msg"] if details else "invalid"
            load_errors.append(
                GoldLoadError(
                    file=path.name,
                    error=f"gold_case_invalid:plan_schema:{loc}:{msg}",
                )
            )
            continue
        cases.append((path, data))
    return cases, load_errors


def gold_source_text(data: dict) -> str:
    """取 planner 輸入原文；頂層與 plan.source_text 都在時必須一致。"""
    top = data.get("source_text")
    plan_src = (data.get("plan") or {}).get("source_text")
    if top is not None and plan_src is not None and top != plan_src:
        raise GoldCaseError(f"source_text mismatch: top={top!r} plan={plan_src!r}")
    src = top if top is not None else plan_src
    if not src:
        raise GoldCaseError("missing source_text")
    return str(src)


async def rule_based_plan(data: dict) -> WorkInstructionPlan:
    """與 wi_ai_service 關閉 LLM 時同路徑：RuleBasedParser → plan_from_rule_result。"""
    text = gold_source_text(data)
    parser = RuleBasedParser(data.get("synthetic_synonyms") or [])
    rule_result = parser.parse(text)
    plan, _candidates = plan_from_rule_result(
        rule_result,
        source_ref=SourceRef(kind="interactive"),
    )
    return plan


@dataclass
class PlannerCaseResult:
    case_id: str
    ok: bool  # 評測本身成立（gold 完整且比對可執行）；分數高低不影響 ok
    gold_action_count: int
    pred_action_count: int
    action_count_match: bool
    boundary_annotated: bool
    boundary_comparable: bool
    boundary_trivially_empty: bool
    boundary_tp: int
    boundary_fp: int
    boundary_fn: int
    boundary_span_f1: float | None  # per-case；無有效標註或兩邊皆無 span 時為 None
    # gold plan 出處（自我指涉排除依據；見 SELF_REFERENTIAL_EXCLUSION_REASON）
    plan_origin: str | None = None
    ie_modified: bool | None = None  # 僅認 JSON bool；缺欄或非 bool 一律 None（保守＝排除）
    # planner 個案失敗（例外被隔離）：計入 Plan 層指標且記為漏，不排除
    planner_failed: bool = False
    planner_error: str | None = None
    planner_error_codes: list[str] = field(default_factory=list)
    # 被拒絕的**原始模型回應**（遮蔽＋截斷後）；只在該案失敗且例外帶得出回應時有值。
    # None＝這次失敗沒有回應可留（timeout／連線失敗／rule planner）；""＝真的回了空字串
    planner_raw_rejected: str | None = None
    planner_elapsed_ms: float = 0.0
    gold_spans: list[list[int]] = field(default_factory=list)
    pred_spans: list[list[int]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _spans_of(plan_dict_actions: list[dict], normalized_text: str, errors: list[str]) -> tuple[Counter, bool]:
    """抽 gold actions 的 evidence spans；回傳 (spans, annotated)。"""
    spans: Counter = Counter()
    annotated = True
    nlen = len(normalized_text)
    for action in plan_dict_actions:
        evidence = action.get("evidence") or []
        if not evidence:
            if action.get("action_type") != "composite_unknown":
                annotated = False
                errors.append(
                    f"gold_boundary_unannotated:{action.get('action_id')}:"
                    "missing plan.actions[].evidence"
                )
            continue
        for ev in evidence:
            # 缺欄/型別錯是 gold 資料問題：具名點名，不讓 KeyError/ValueError traceback
            if not isinstance(ev, dict) or ev.get("start") is None or ev.get("end") is None:
                annotated = False
                errors.append(
                    f"gold_evidence_missing_field:{action.get('action_id')}:"
                    "evidence 需要 start/end"
                )
                continue
            try:
                start, end = int(ev["start"]), int(ev["end"])
            except (TypeError, ValueError):
                annotated = False
                errors.append(
                    f"gold_evidence_invalid_field:{action.get('action_id')}:"
                    f"start/end 非整數（start={ev.get('start')!r} end={ev.get('end')!r}）"
                )
                continue
            if not (0 <= start < end <= nlen):
                annotated = False
                errors.append(
                    f"gold_evidence_offset_out_of_range:{action.get('action_id')}:"
                    f"[{start},{end}) len={nlen}"
                )
                continue
            if normalized_text[start:end] != ev.get("text"):
                annotated = False
                errors.append(
                    f"gold_evidence_text_mismatch:{action.get('action_id')}:[{start},{end})"
                )
                continue
            spans[(start, end)] += 1
    return spans, annotated


def _pred_spans_of(plan: WorkInstructionPlan) -> Counter:
    spans: Counter = Counter()
    for action in plan.actions:
        for ev in action.evidence:
            spans[(ev.start, ev.end)] += 1
    return spans


def _f1(tp: int, fp: int, fn: int) -> float | None:
    if tp + fp + fn == 0:
        return None
    return (2 * tp) / (2 * tp + fp + fn)


# 任何 scheme 的 URL；在引號／空白／角括號處停住（httpx 的訊息把 URL 包在單引號裡）
_URL_RE = re.compile(r"""\w+://[^\s'"<>]+""")


def _redact_urls(message: str) -> str:
    """把例外訊息裡的 URL 換成 `<redacted-url>`。

    **例外訊息不是可信的字串來源**：httpx 的 `HTTPStatusError` 會把完整 request
    URL **連同 userinfo** 寫進訊息——
    ``Client error '401 Unauthorized' for url 'http://user:pass@host/v1/...'``——
    而 `planner_error` 會被寫進**要入版控的評測報告**。觸發條件是日常的
    （401 key 錯／過期、404、429、5xx），且 endpoint 設錯正是「跑一次、失敗、
    修好再跑」的時候，那批報告最可能被一起 commit。

    不特判 `HTTPStatusError`：洩漏的類別是「訊息含 URL」，產生者不只一個
    （`UnsupportedProtocol`、`InvalidURL`、proxy 錯誤、未來換掉的 client…），
    只擋一種等於留著同一個洞的其他入口。

    **診斷力不受影響**：訊息其餘部分原樣保留——HTTP 錯誤仍看得到狀態碼與原因短語
    （``Client error '401 Unauthorized' for url '<redacted-url>'``），Pydantic 的
    ``input_value='多顆'`` 這類細節照留；被換掉的只有 URL 本身（含 MDN／
    pydantic 的說明連結，那些沒有診斷價值）。錯誤**分類**另有
    `_planner_error_codes`（不經訊息字串）。
    """
    return _URL_RE.sub("<redacted-url>", message)


# 被拒回應的長度上限（字元）。gold 尺度的**合法**回應遠低於此：現行 55 案的 gold plan
# 序列化後最長 830 字元，模型加上縮排與 roles 也在 3000 以內；而回應是**遠端可控**且
# 長度無界（`llm_client` 只做 `str()`、httpx 未設 response size limit，`max_tokens`
# 只約束守規矩的伺服器），一個回應就能把 100KB 塞進要入版控的報告。
PLANNER_RAW_REJECTED_MAX_LEN = 4000

# 短於此的「憑證」不做字面抹除：`""` 會讓 str.replace 在每個字元間插入標記、
# 一兩個字元的值會把正常文字打成馬賽克——遮蔽過當的後果是報告失去診斷價值
# （正是本欄位存在的目的）。真實 api key 遠長於此；**設得比這短的憑證不受保護**，
# 這是刻意的取捨，不是漏看。
MIN_REDACTABLE_SECRET_LEN = 8


def _redact_secrets(text: str, secrets: Sequence[str]) -> str:
    """把**已知憑證的字面值**換成 `<redacted-secret>`。

    `_redact_urls` 擋的是「訊息裡內嵌 URL」，擋不到裸 token：`planner_raw_rejected`
    存的是**伺服器回應本文**，而伺服器拿得到我們送出的 `Authorization: Bearer <key>`
    ——回聲式的 proxy／debug endpoint 把收到的 header 抄進回應本文，key 就會隨報告
    進版控。這裡只抹**我們自己知道的值**（由 CLI 從 settings 傳入），不做樣式猜測
    （猜測會誤殺模型輸出的正常內容）。
    """
    for secret in secrets:
        if secret and len(secret) >= MIN_REDACTABLE_SECRET_LEN:
            text = text.replace(secret, "<redacted-secret>")
    return text


def _sanitize_rejected_raw(content: str, secrets: Sequence[str]) -> str:
    """被拒回應寫進報告前的處理：**先遮蔽、後截斷**。

    順序不可對調——理由是**憑證字面值**而不是 URL：`_redact_secrets` 靠字面比對，
    先截斷會把橫跨切點的 api key 剖成兩半，前半留在報告裡而完整值不再匹配
    （截掉尾巴的 key 仍是大部分的祕密材料）。URL 那層不受影響：`_URL_RE`
    沒有結尾要求，被攔腰切斷的 URL 照樣整段匹配得到——所以真正靠順序保護的是前者。

    截斷**留痕**（同 `wi_ai_eval._sanitize_model_name`）：截過的值帶
    `…[truncated from N chars]`，不讓它看起來像完整回應——一份被截斷卻裝成完整的
    「原始回應」會讓事後判讀切分時得出錯的結論。N 是**遮蔽後**的長度（遮蔽會改變
    長度，報遮蔽前的數字對不上眼前這串字）。

    不剝控制字元（與 `model_served` 不同）：回應本文的換行是合法內容，剝掉會把
    pretty-print 的 JSON 打爛；`json.dumps` 會把控制字元逸出，報告 JSON 這個 sink
    本來就是安全的。代價是**本欄位不得未經逸出印到終端機**（CLI 只印統計數字，
    不印內容；有測試守）。
    """
    cleaned = _redact_urls(_redact_secrets(content, secrets))
    if len(cleaned) > PLANNER_RAW_REJECTED_MAX_LEN:
        head = cleaned[:PLANNER_RAW_REJECTED_MAX_LEN]
        return f"{head}…[truncated from {len(cleaned)} chars]"
    return cleaned


# 被剝除值的長度上限（字元）。比 `PLANNER_RAW_REJECTED_MAX_LEN`（4000，存整份回應）
# 小兩個數量級是因為存的東西不同：這裡是**單一 role 的片語**——gold 全 55 案裡最長的
# role text 是 6 個字。設 200 給改寫／幻覺留足空間（幻覺常比原文長），又不讓一個
# 惡意長字串塞爆要入版控的報告。超長照樣**留痕**（截斷是事實，不能裝成完整值）。
STRIPPED_VALUE_MAX_LEN = 200


def sanitize_stripped_value(text: str, secrets: Sequence[str]) -> str:
    """被剝除的模型字串寫進報告前的處理：**先遮蔽、後截斷**（同 `_sanitize_rejected_raw`）。

    與被拒回應同一套規則、同一個理由——順序不可對調，因為 `_redact_secrets` 靠字面
    比對，先截斷會把橫跨切點的憑證剖成兩半而不再匹配。這裡另外把它寫成**公開**函式
    （被拒回應那支是私有的），因為呼叫端在 `scripts/wi_ai_eval.py`：遮蔽規則只能有
    一份，複製一份到腳本裡就一定會漂移。

    ⚠️ 這是**模型可控字串**且報告要入版控。它之所以只出現在報告，是因為
    `contracts.StripDetail` 走的是 observer 旁通道，不進 `unresolved`／
    `routing_reasons`（那條路會落 DB 並回 API）——見該 dataclass 的 docstring。
    """
    cleaned = _redact_urls(_redact_secrets(text, secrets))
    if len(cleaned) > STRIPPED_VALUE_MAX_LEN:
        head = cleaned[:STRIPPED_VALUE_MAX_LEN]
        return f"{head}…[truncated from {len(cleaned)} chars]"
    return cleaned


def _rejected_raw_of(exc: BaseException, secrets: Sequence[str]) -> str | None:
    """例外帶得出模型回應就留存，否則 None。

    `None`＝**這次失敗沒有回應可留**（timeout、連線失敗、rule planner 的例外，或
    `PlannerError` 未帶 raw）；`""`＝伺服器真的回了空字串。兩者在報告裡必須分得開，
    否則「模型到底吐了什麼」的答案會退化成「不知道」。留的是 `PlannerError.raw`，
    即 **retry 那次**的回應（adapter 只把最後一次掛上例外）——initial 那次的回應
    現行契約留不下來，見報告的 `raw_rejected_note`。
    """
    if not isinstance(exc, PlannerError) or exc.raw is None:
        return None
    return _sanitize_rejected_raw(exc.raw.content, secrets)


def _planner_error_codes(exc: BaseException) -> list[str]:
    """把 planner 例外壓成可統計的錯誤碼（失敗形態分布用）。

    `PlannerError.errors` 是 `validate_planner_output` 的具名錯誤
    （例 ``evidence_offset_oor:a2``）；取冒號前的前綴當碼，讓「模型錯在哪一類」
    可以聚合。非 PlannerError（timeout、連線失敗…）以例外類名為碼。
    """
    if isinstance(exc, PlannerError) and exc.errors:
        codes: list[str] = []
        for e in exc.errors:
            code = str(e).split(":", 1)[0]
            if code:
                codes.append(code)
        if codes:
            return codes
    return [type(exc).__name__]


def _case_provenance(data: dict) -> tuple[str | None, bool | None]:
    """gold 檔的 (plan_origin, ie_modified)；ie_modified 僅認 JSON bool，其餘視為未宣告。"""
    origin = data.get("plan_origin")
    origin = str(origin) if isinstance(origin, str) and origin else None
    ie_mod = data.get("ie_modified")
    return origin, (ie_mod if isinstance(ie_mod, bool) else None)


async def evaluate_planner_case(
    data: dict, plan_fn: PlannerFn, *, secrets: Sequence[str] = ()
) -> PlannerCaseResult:
    """評測單一案例。

    `secrets`：本次執行**已知的憑證字面值**（CLI 從 settings 取 api key 傳入）。
    寫進報告的字串（`planner_error`／`planner_raw_rejected`）會先抹掉這些值——
    回應本文是遠端可控的，而報告要入版控。預設空＝rule planner 路徑不需要也拿不到。
    """
    case_id = str(data.get("id") or "unknown")
    errors: list[str] = []
    plan_origin, ie_modified = _case_provenance(data)

    gold_plan = data.get("plan") or {}
    gold_actions = gold_plan.get("actions") or []
    gold_norm = str(gold_plan.get("normalized_text") or "")

    try:
        gold_source_text(data)
    except GoldCaseError as exc:
        return PlannerCaseResult(
            case_id=case_id,
            ok=False,
            gold_action_count=len(gold_actions),
            pred_action_count=0,
            action_count_match=False,
            boundary_annotated=False,
            boundary_comparable=False,
            boundary_trivially_empty=False,
            boundary_tp=0,
            boundary_fp=0,
            boundary_fn=0,
            boundary_span_f1=None,
            plan_origin=plan_origin,
            ie_modified=ie_modified,
            errors=[f"gold_case_invalid:{exc}"],
        )

    # planner 個案例外被隔離成「該案失敗」（不中止整批），但**不靜默**：
    # 訊息與錯誤碼進 errors／planner_error(_codes)，並在 Plan 層記為漏。
    # 「管道存在但恆空」的防線改由 CLI 的「全案失敗＝管道壞掉」判定承接。
    pred_plan: WorkInstructionPlan | None = None
    planner_error: str | None = None
    planner_error_codes: list[str] = []
    planner_raw_rejected: str | None = None
    t0 = time.perf_counter()
    try:
        pred_plan = await plan_fn(data)
    except Exception as exc:  # noqa: BLE001 — 個案失敗是被量測的對象，逐案記錄後續評
        # URL 與已知憑證一律遮蔽：例外訊息會夾帶 endpoint 與其中的 userinfo，而這裡的
        # 字串會進入要入版控的報告（見 _redact_urls／_redact_secrets）
        planner_error = _redact_urls(_redact_secrets(f"{type(exc).__name__}:{exc}", secrets))
        planner_error_codes = _planner_error_codes(exc)
        # 被拒絕的原始回應：錯誤碼答不了「這份輸出的切分對不對」（ADR-033 T-12）
        planner_raw_rejected = _rejected_raw_of(exc, secrets)
        errors.append(f"planner_failed:{planner_error}")
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    gold_spans, annotated = _spans_of(gold_actions, gold_norm, errors)

    if pred_plan is None:
        # 沒有 plan＝什麼都沒預測：gold span 全記 FN、無 FP；action count 只在
        # gold 也是 0 個 action 時算命中。comparable 對「無 pred」無意義，記 False
        # 但不報 normalized_text_mismatch（那是 planner 品質問題，不是這裡的情形）。
        pred_action_count = 0
        action_count_match = len(gold_actions) == 0
        pred_spans = Counter()
        comparable = False
    else:
        pred_action_count = len(pred_plan.actions)
        action_count_match = pred_action_count == len(gold_actions)
        pred_spans = _pred_spans_of(pred_plan)
        comparable = pred_plan.normalized_text == gold_norm
        if not comparable:
            errors.append(
                f"normalized_text_mismatch: pred={pred_plan.normalized_text!r} gold={gold_norm!r}"
            )

    trivially_empty = False
    if annotated:
        if comparable or pred_plan is None:
            tp = sum((gold_spans & pred_spans).values())
            fp = sum(pred_spans.values()) - tp
            fn = sum(gold_spans.values()) - tp
        else:
            # 不同座標系：無一可信匹配，誠實記帳而非跳過
            tp = 0
            fp = sum(pred_spans.values())
            fn = sum(gold_spans.values())
        f1 = _f1(tp, fp, fn)
        if f1 is None:
            # 兩邊皆無 span（gold 純 composite_unknown 無 evidence、planner 也不給）：
            # 不給 1.0——那會讓「全面 abstain」拿滿分（獎勵棄權）。記 None、
            # trivially_empty=True，聚合排除並在 summary 點名。
            trivially_empty = True
            tp = fp = fn = 0
    else:
        tp = fp = fn = 0
        f1 = None

    # gold_* 錯誤＝標註/資料問題（評測不成立）；normalized_text_mismatch 是 planner
    # 品質問題，已計入 FP/FN，不影響 ok。
    ok = not any(e.startswith("gold_") for e in errors)

    return PlannerCaseResult(
        case_id=case_id,
        ok=ok,
        gold_action_count=len(gold_actions),
        pred_action_count=pred_action_count,
        action_count_match=action_count_match,
        boundary_annotated=annotated,
        boundary_comparable=comparable,
        boundary_trivially_empty=trivially_empty,
        boundary_tp=tp,
        boundary_fp=fp,
        boundary_fn=fn,
        boundary_span_f1=f1,
        plan_origin=plan_origin,
        ie_modified=ie_modified,
        planner_failed=pred_plan is None,
        planner_error=planner_error,
        planner_error_codes=planner_error_codes,
        planner_raw_rejected=planner_raw_rejected,
        planner_elapsed_ms=elapsed_ms,
        gold_spans=sorted([list(k) for k in gold_spans.elements()]),
        pred_spans=sorted([list(k) for k in pred_spans.elements()]),
        errors=errors,
    )


def planner_pipeline_broken(results: list[PlannerCaseResult]) -> bool:
    """n>0 且**每一案**都 planner 失敗＝管道壞掉，不是量測結果。

    個案失敗是被量測的對象（記為漏、不影響退出碼）；但「全滅」通常代表 endpoint
    連不上／模型名打錯／prompt 全毀，此時報告裡的 0 分不具意義。這條承接原本
    「planner 例外不捕捉」所守的「管道存在但恆空」防線，由 CLI 判為失敗（exit 1）。
    """
    return bool(results) and all(r.planner_failed for r in results)


def is_self_referential(result: PlannerCaseResult, planner: str) -> bool:
    """gold plan＝受測 planner 的預標註且 IE 未（宣告）修改——對 Plan 層指標零證據力。

    ie_modified 缺欄或非 bool 視同未修改（保守排除）；轉正流程必填 bool，
    守門在 tests/unit/test_gold_draft_isolation.py 的空殼/欄位 tripwire。
    """
    return (
        result.plan_origin == planner_preannotation_origin(planner)
        and result.ie_modified is not True
    )


def summarize_planner_results(
    results: list[PlannerCaseResult], *, planner: str
) -> dict[str, Any]:
    n = len(results)
    # 自我指涉排除（P0-1）：planner 不得給自己打分。排除只作用於 Plan 層指標，
    # 名單與理由必須進 summary——不是靜默少算。
    excluded = [r for r in results if is_self_referential(r, planner)]
    plan_scored = [r for r in results if not is_self_referential(r, planner)]
    matches = sum(1 for r in plan_scored if r.action_count_match)
    annotated = [r for r in plan_scored if r.boundary_annotated]
    scored = [r for r in annotated if not r.boundary_trivially_empty]
    tp = sum(r.boundary_tp for r in scored)
    fp = sum(r.boundary_fp for r in scored)
    fn = sum(r.boundary_fn for r in scored)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    failed = [r for r in results if r.planner_failed]
    code_counts: Counter = Counter()
    for r in failed:
        for code in r.planner_error_codes or ["unknown"]:
            code_counts[code] += 1
    elapsed = [r.planner_elapsed_ms for r in results]
    return {
        "planner": planner,
        "n": n,
        "plan_metrics_n": len(plan_scored),
        # 個案失敗＝被量測的對象（不是工具故障）：計入 Plan 層指標記為漏，
        # 名單／錯誤碼分布在此顯著呈現。分母是全部 n（含自我指涉排除的案例）。
        "planner_failures": {
            "count": len(failed),
            "rate": (len(failed) / n) if n else None,
            "cases": [r.case_id for r in failed],
            "error_codes": dict(code_counts.most_common()),
        },
        "planner_latency_ms": {
            "total": round(sum(elapsed), 2),
            "mean": round(sum(elapsed) / n, 2) if n else None,
            "median": round(median(elapsed), 2) if elapsed else None,
            "max": round(max(elapsed), 2) if elapsed else None,
        },
        "self_referential_excluded": {
            "count": len(excluded),
            "cases": [r.case_id for r in excluded],
            "reason": SELF_REFERENTIAL_EXCLUSION_REASON,
        },
        "action_count_accuracy": (matches / len(plan_scored)) if plan_scored else None,
        "action_count_matches": matches,
        "boundary_span": {
            "annotated_cases": len(annotated),
            "scored_cases": len(scored),
            "unannotated_cases": [r.case_id for r in plan_scored if not r.boundary_annotated],
            "trivially_empty_cases": [
                r.case_id for r in annotated if r.boundary_trivially_empty
            ],
            "micro": {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": _f1(tp, fp, fn),
            },
        },
        "dependency_f1": None,
        "dependency_f1_note": DEPENDENCY_F1_NOTE,
        "degenerate_planner_note": (
            RULE_DEGENERATE_NOTE if planner == RULE_PLANNER_NAME else None
        ),
        "spec_targets": dict(SPEC_TARGETS),
    }


async def evaluate_planner_all(
    gold_dir: Path | None = None,
    *,
    plan_fn: PlannerFn | None = None,
    planner_name: str = RULE_PLANNER_NAME,
    secrets: Sequence[str] = (),
) -> tuple[list[PlannerCaseResult], dict[str, Any]]:
    # secrets 透傳（見 evaluate_planner_case）：自訂 plan_fn 可以是 LLM planner，
    # 遮蔽不該只在 CLI 那條路上生效
    fn = plan_fn or rule_based_plan
    results: list[PlannerCaseResult] = []
    for _path, data in load_gold_cases(gold_dir):
        results.append(await evaluate_planner_case(data, fn, secrets=secrets))
    return results, summarize_planner_results(results, planner=planner_name)
