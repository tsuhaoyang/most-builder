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

DB 依賴：rule_based 路徑**不需要 DB** —— planner 只需 gold 檔內 `synthetic_synonyms`
（`RuleBasedParser` 的 GM/CM 判型關鍵字是程式常數；讀 motion_templates/synonyms 的
`SlotLinker` 屬 compile 段，不在 text→plan 路徑上）。LLM 路徑僅供顯式 flag 使用，
CI 與預設一律 rule_based。
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ddm_v2.nlp.contracts import SourceRef, WorkInstructionPlan
from ddm_v2.nlp.gold_eval import default_gold_dir, load_gold_cases
from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.nlp.rule_plan_adapter import plan_from_rule_result

RULE_PLANNER_NAME = "rule_based_v1"

# 規格全檔名（引用時不可只寫「spec §14.4」——implementation spec 的 §14.4 是別的章節）
SPEC_DOC = "docs/architecture/wi-ai-parser-system-spec.md"

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
            first = exc.errors()[0] if exc.errors() else {}
            loc = ".".join(str(p) for p in first.get("loc", ()))
            load_errors.append(
                GoldLoadError(
                    file=path.name,
                    error=f"gold_case_invalid:plan_schema:{loc}:{first.get('msg', 'invalid')}",
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


async def evaluate_planner_case(data: dict, plan_fn: PlannerFn) -> PlannerCaseResult:
    case_id = str(data.get("id") or "unknown")
    errors: list[str] = []

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
            errors=[f"gold_case_invalid:{exc}"],
        )

    # planner 例外不捕捉：崩潰要讓上層炸掉（防「管道存在但恆空」）
    pred_plan = await plan_fn(data)

    action_count_match = len(pred_plan.actions) == len(gold_actions)

    gold_spans, annotated = _spans_of(gold_actions, gold_norm, errors)
    pred_spans = _pred_spans_of(pred_plan)

    comparable = pred_plan.normalized_text == gold_norm
    if not comparable:
        errors.append(
            f"normalized_text_mismatch: pred={pred_plan.normalized_text!r} gold={gold_norm!r}"
        )

    trivially_empty = False
    if annotated:
        if comparable:
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
        pred_action_count=len(pred_plan.actions),
        action_count_match=action_count_match,
        boundary_annotated=annotated,
        boundary_comparable=comparable,
        boundary_trivially_empty=trivially_empty,
        boundary_tp=tp,
        boundary_fp=fp,
        boundary_fn=fn,
        boundary_span_f1=f1,
        gold_spans=sorted([list(k) for k in gold_spans.elements()]),
        pred_spans=sorted([list(k) for k in pred_spans.elements()]),
        errors=errors,
    )


def summarize_planner_results(
    results: list[PlannerCaseResult], *, planner: str
) -> dict[str, Any]:
    n = len(results)
    matches = sum(1 for r in results if r.action_count_match)
    annotated = [r for r in results if r.boundary_annotated]
    scored = [r for r in annotated if not r.boundary_trivially_empty]
    tp = sum(r.boundary_tp for r in scored)
    fp = sum(r.boundary_fp for r in scored)
    fn = sum(r.boundary_fn for r in scored)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "planner": planner,
        "n": n,
        "action_count_accuracy": (matches / n) if n else None,
        "action_count_matches": matches,
        "boundary_span": {
            "annotated_cases": len(annotated),
            "scored_cases": len(scored),
            "unannotated_cases": [r.case_id for r in results if not r.boundary_annotated],
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
) -> tuple[list[PlannerCaseResult], dict[str, Any]]:
    fn = plan_fn or rule_based_plan
    results: list[PlannerCaseResult] = []
    for _path, data in load_gold_cases(gold_dir):
        results.append(await evaluate_planner_case(data, fn))
    return results, summarize_planner_results(results, planner=planner_name)
