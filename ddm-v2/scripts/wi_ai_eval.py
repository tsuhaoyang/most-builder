#!/usr/bin/env python3
"""WI AI gold eval CLI — 兩段並列：planner 段 + compile 段。

規格出處（全檔名；`docs/llm/wi-ai-parser-implementation-spec.md` 的 §14.4/§19
是別的章節，引用時不可簡寫「spec §14.4」）：
`docs/architecture/wi-ai-parser-system-spec.md` §14.4 指標與上線門檻、§19 分階段交付。

- **planner 段**（§14.4 Plan 層 / §19 P2 退出條件）：gold 原文 → planner
  （預設 rule_based，無 DB、無 LLM）→ 與 gold plan 比對，產出
  plan action-count accuracy 與 boundary **span** F1（§14.4 的 dependency F1
  未實作，報告固定輸出 `dependency_f1: null` 並附原因）。分數低不影響退出碼
  （P2 門檻是上線 gate，不是本腳本的成敗）；但 gold 標註缺損（ok=False）會失敗。
- **compile 段**（既有）：gold plan → SlotLinker → compile → engine_gate → routing，
  驗 compiler+engine；任一案 fail → 退出碼 1。

用法（於 ddm-v2/）：
  PYTHONPATH=src python scripts/wi_ai_eval.py
  PYTHONPATH=src python scripts/wi_ai_eval.py --gold-dir tests/gold/wi_plans --out docs/llm/eval-reports
  # LLM planner 僅限顯式指定（需 LLM_BASE_URL 等設定；CI 與預設絕不打真模型）
  PYTHONPATH=src python scripts/wi_ai_eval.py --planner llm

退出碼（區分「eval 跑完發現問題」與「gold 輸入根本不可用」）：
  0 ＝ compile 全過、planner 段完整執行（n>0、無 gold 標註缺損）、無載入錯誤；
  1 ＝ eval 跑完但有失敗（compile fail 或 gold 標註缺損，如 offset 越界）；
  2 ＝ gold 輸入不可用（malformed JSON／缺 `plan`／plan schema 不合＝
       `gold_case_invalid`，或 n=0 沒量到任何案例）。有載入錯誤時仍會評測
       其餘有效案例並產出報告（`gold_load_errors` 區塊），但退出碼以 2 為準。

報告檔名守門：gold_dir 含任何**未核准**案例（approved_by 空、或 review_status
非 approved）時，報告寫成 `wi-draft-latest.json`／`wi-draft-<stamp>.json`，
**拒寫** `wi-gold-latest.json`——覆核期間不得污染官方報告。

Plan 層自我指涉排除：gold 檔標 `plan_origin=<planner>_preannotation` 且
`ie_modified` 非 true 者，排除出 planner 段 Plan 層指標（planner 不得給自己
打分；見 `nlp/planner_eval.py` 的 SELF_REFERENTIAL_EXCLUSION_REASON）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ddm_v2.nlp.gold_eval import (  # noqa: E402
    GOLD_SCHEMA_VERSION,
    evaluate_gold_case,
    is_seed_gold_case,
)
from ddm_v2.nlp.planner_eval import (  # noqa: E402
    RULE_PLANNER_NAME,
    SPEC_DOC,
    PlannerFn,
    evaluate_planner_case,
    is_self_referential,
    load_gold_cases_checked,
    rule_based_plan,
    summarize_planner_results,
)

REPORT_SCHEMA_VERSION = "wi-gold-report-v4"

EXIT_CODE_HELP = (
    "exit codes: 0 = all green; "
    "1 = eval ran but found failures (compile fail / gold annotation defect); "
    "2 = gold input unusable (gold_case_invalid load errors, or n=0)"
)


def _build_llm_plan_fn(timeout_s: float) -> PlannerFn:
    """顯式 --planner llm 才建構；需要已設定的 LLM endpoint。"""
    from ddm_v2.nlp.contracts import ParseContext, SourceRef, WorkInstructionPlan
    from ddm_v2.nlp.llm_client import OpenAICompatClient
    from ddm_v2.nlp.llm_planner import LLMPlannerAdapter
    from ddm_v2.nlp.normalization import normalize
    from ddm_v2.nlp.planner_eval import gold_source_text
    from ddm_v2.settings import get_settings

    settings = get_settings()
    if not settings.llm_base_url:
        raise SystemExit("--planner llm 需要 LLM_BASE_URL 等設定；CI/預設請用 --planner rule")
    client = OpenAICompatClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        response_format_mode="json_object",
    )
    adapter = LLMPlannerAdapter(client, timeout_s=timeout_s)

    async def _plan(data: dict) -> WorkInstructionPlan:
        text = gold_source_text(data)
        norm = normalize(text)
        ctx = ParseContext(rule_set_code=str(data.get("rule_set_code") or "MINIMOST_FACTORY_V2"))
        output, _raw = await adapter.plan(norm, ctx)
        return WorkInstructionPlan(
            source_text=text,
            normalized_text=norm,
            language=output.language,
            source_ref=SourceRef(kind="interactive"),
            actions=output.actions,
            dependencies=output.dependencies,
            unresolved=list(output.unresolved),
        )

    return _plan


def _case_is_approved(data: dict) -> bool:
    """核准判定：approved_by 非空 且 review_status ∈ {缺欄(seed 慣例), approved}。

    `approved_by: "seed"` 只認 `SEED_GOLD_IDS` 白名單（R6）：seed 是三個已知
    A5 fixture 的慣例，不是任人填的豁免字串——非白名單的 seed 視同未核准
    （報告降級 wi-draft-*、進 unapproved_cases 點名）。
    """
    if data.get("approved_by") in (None, ""):
        return False
    if data.get("approved_by") == "seed" and not is_seed_gold_case(data):
        return False
    return data.get("review_status") in (None, "approved")


def _is_unmodified_preannotation(data: dict) -> bool:
    """plan 出處是 planner 預標註且 IE 未宣告修改（與 planner_eval 的自我指涉
    排除同語意：ie_modified 僅認 JSON true，缺欄/false 都算未修改）。"""
    origin = data.get("plan_origin")
    return (
        isinstance(origin, str)
        and origin.endswith("_preannotation")
        and data.get("ie_modified") is not True
    )


def _dataset_note(cases: list[tuple[Path, dict]]) -> str:
    """依實際 n 與 approved_by 動態生成（不寫死「未達 50 筆」——gold 長大後會變錯）。"""
    n = len(cases)
    seed_n = sum(1 for _, d in cases if is_seed_gold_case(d))
    fake_seed_n = sum(
        1 for _, d in cases if d.get("approved_by") == "seed" and not is_seed_gold_case(d)
    )
    ie_cases = [d for _, d in cases if d.get("approved_by") not in (None, "", "seed")]
    ie_n = len(ie_cases)
    unmarked_n = n - seed_n - fake_seed_n - ie_n
    # 給主管看的頭條句必須自帶但書（R4）：原樣核准的預標註對 planner 段
    # 零證據力，不能讓「IE 核准 N 筆」單獨成立
    rubber_n = sum(1 for d in ie_cases if _is_unmodified_preannotation(d))
    parts = [f"n={n}"]
    if n and seed_n == n:
        parts.append("全部 seed（approved_by=seed）")
    elif seed_n:
        parts.append(f"seed {seed_n} 筆")
    if fake_seed_n:
        parts.append(f"approved_by=seed 但非白名單 {fake_seed_n} 筆（不計核准）")
    if unmarked_n:
        parts.append(f"approved_by 未標 {unmarked_n} 筆")
    if ie_n < 50:
        parts.append(f"IE 核准 {ie_n}/50，未達 {SPEC_DOC} §19 P0 前置")
    else:
        parts.append(f"IE 核准 {ie_n} 筆，已達 {SPEC_DOC} §19 P0 的 50 筆前置")
    if rubber_n:
        parts.append(
            f"其中 ie_modified≠true 的預標註 {rubber_n} 筆"
            "（原樣核准，不計 planner 段證據力——見 self_referential_excluded）"
        )
    return "；".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate WI AI gold plans",
        epilog=EXIT_CODE_HELP,
    )
    parser.add_argument(
        "--gold-dir",
        type=Path,
        default=ROOT / "tests" / "gold" / "wi_plans",
        help="Directory of wi-gold-v1 JSON cases",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "llm" / "eval-reports",
        help="Output directory for versioned JSON reports",
    )
    parser.add_argument(
        "--planner",
        choices=["rule", "llm"],
        default="rule",
        help="planner 段使用的 planner（預設 rule；llm 需顯式指定與 LLM 設定）",
    )
    parser.add_argument(
        "--llm-timeout-s",
        type=float,
        default=30.0,
        help="--planner llm 時的單案 timeout 秒數",
    )
    args = parser.parse_args()

    plan_fn: PlannerFn = rule_based_plan
    planner_name = RULE_PLANNER_NAME
    if args.planner == "llm":
        plan_fn = _build_llm_plan_fn(args.llm_timeout_s)
        planner_name = "llm"

    # 載入層先把「檔案壞掉」轉成具名 gold_case_invalid（點名檔案、進報告、exit 2），
    # 其餘有效案例照常評測——不讓 JSONDecodeError/KeyError traceback 且無報告可看。
    cases, load_errors = load_gold_cases_checked(args.gold_dir)

    async def _run():
        compile_results = [await evaluate_gold_case(data) for _path, data in cases]
        planner_results = [await evaluate_planner_case(data, plan_fn) for _path, data in cases]
        return compile_results, planner_results

    compile_results, planner_results = asyncio.run(_run())
    planner_summary = summarize_planner_results(planner_results, planner=planner_name)

    passed = sum(1 for r in compile_results if r.ok)
    failed = len(compile_results) - passed
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")

    # P2-9：未核准案例混入 gold_dir → 官方報告檔名拒用 wi-gold-*（降級 wi-draft-*）
    unapproved_cases = [path.name for path, d in cases if not _case_is_approved(d)]

    report = {
        "report_kind": "wi-gold-eval",
        # v3：planner_eval.summary 的 boundary → boundary_span（含 scored_cases/
        # trivially_empty_cases）、spec_targets.boundary_f1 → boundary_span_f1、
        # 新增 dependency_f1(=null)+note、gold_load_errors、動態 dataset_note；
        # cases 的 boundary_f1 → boundary_span_f1、新增 boundary_trivially_empty。
        # v4：Plan 層指標語意變更——自我指涉案例（plan_origin=planner 預標註且
        # ie_modified≠true）排除出 action_count_accuracy／boundary_span 聚合；
        # planner_eval.summary 新增 plan_metrics_n＋self_referential_excluded、
        # cases 新增 plan_origin/ie_modified；頂層新增 unapproved_cases（有值時
        # 報告檔名降級 wi-draft-*）。頂層 summary/cases（compile 段）自 v1 起形狀不變。
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "gold_schema_version": GOLD_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "gold_dir": str(args.gold_dir),
        "dataset_note": _dataset_note(cases),
        "gold_load_errors": [e.to_dict() for e in load_errors],
        "unapproved_cases": unapproved_cases,
        "summary": {
            "total": len(compile_results),
            "passed": passed,
            "failed": failed,
        },
        "cases": [r.to_dict() for r in compile_results],
        "compile_eval_note": (
            "頂層 summary/cases 為 compile 段（gold plan → link/compile/engine），"
            "planner 段見 planner_eval"
        ),
        "planner_eval": {
            "db_required": False,
            "summary": planner_summary,
            "cases": [r.to_dict() for r in planner_results],
        },
    }

    args.out.mkdir(parents=True, exist_ok=True)
    prefix = "wi-draft" if unapproved_cases else "wi-gold"
    out_path = args.out / f"{prefix}-{stamp}.json"
    latest = args.out / f"{prefix}-latest.json"
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    out_path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")

    print(f"gold eval → {out_path}")
    if unapproved_cases:
        print(
            f"[gold]     WARNING: gold_dir 含 {len(unapproved_cases)} 筆未核准案例"
            f"（{', '.join(unapproved_cases[:5])}{'…' if len(unapproved_cases) > 5 else ''}）"
            f"——報告降級為 {latest.name}，拒寫 wi-gold-latest.json（防覆核期間污染官方報告）"
        )
    if load_errors:
        print(f"[gold]     {len(load_errors)} invalid gold file(s):")
        for e in load_errors:
            print(f"  [INVALID] {e.file}: {e.error}")
    print(f"[compile]  {passed}/{len(compile_results)} passed")
    for r in compile_results:
        mark = "OK" if r.ok else "FAIL"
        print(f"  [{mark}] {r.case_id}  routing={r.routing_status}  actions={r.action_count}")
        if not r.ok:
            for e in r.errors[:8]:
                print(f"       - {e}")

    acc = planner_summary["action_count_accuracy"]
    micro = planner_summary["boundary_span"]["micro"]
    excluded = planner_summary["self_referential_excluded"]
    print(
        f"[planner]  planner={planner_summary['planner']}  n={planner_summary['n']}  "
        f"plan_metrics_n={planner_summary['plan_metrics_n']}  "
        f"self_ref_excluded={excluded['count']}  "
        f"action_count_accuracy={acc if acc is None else round(acc, 4)} "
        f"(target {planner_summary['spec_targets']['action_count_exact_match']})  "
        f"boundary_span_f1={micro['f1'] if micro['f1'] is None else round(micro['f1'], 4)} "
        f"(target {planner_summary['spec_targets']['boundary_span_f1']})  "
        "dependency_f1=n/a(未實作)"
    )
    if excluded["count"]:
        print(
            f"           excluded (self-referential, plan_origin=planner 且 ie_modified≠true): "
            f"{', '.join(excluded['cases'][:8])}{'…' if excluded['count'] > 8 else ''}"
        )
    for r in planner_results:
        mark = "OK" if r.ok else "GOLD-ERR"
        f1 = "n/a" if r.boundary_span_f1 is None else round(r.boundary_span_f1, 4)
        # 被自我指涉排除的案例逐案標 [SELF-REF]——只在 summary 列名單的話，
        # 逐案表會讓人以為它們有計入 Plan 層指標
        self_ref = "  [SELF-REF]" if is_self_referential(r, planner_name) else ""
        print(
            f"  [{mark}] {r.case_id}  actions {r.pred_action_count}/{r.gold_action_count}"
            f"  match={r.action_count_match}  boundary_span_f1={f1}{self_ref}"
        )
        for e in r.errors[:8]:
            print(f"       - {e}")

    # 退出碼分層（見 module docstring / --help epilog）：
    # gold 輸入不可用（載入錯誤或 n=0）→ 2；eval 跑完但有失敗 → 1。
    if load_errors:
        print(f"[gold]     ERROR: {len(load_errors)} gold_case_invalid file(s) — exit 2")
        return 2
    if not planner_results:
        print("[planner]  ERROR: no gold cases evaluated (n=0) — exit 2")
        return 2
    planner_ok = all(r.ok for r in planner_results)
    return 0 if (failed == 0 and planner_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
