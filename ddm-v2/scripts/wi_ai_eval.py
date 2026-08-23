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
  1 ＝ eval 跑完但有失敗（compile fail 或 gold 標註缺損，如 offset 越界；
       或 planner 對**所有**案例都失敗＝管道壞掉，見下）；
  2 ＝ gold 輸入不可用（malformed JSON／缺 `plan`／plan schema 不合＝
       `gold_case_invalid`，或 n=0 沒量到任何案例）。有載入錯誤時仍會評測
       其餘有效案例並產出報告（`gold_load_errors` 區塊），但退出碼以 2 為準。

planner 個案失敗與退出碼（v5 起）：planner 對單一案例拋例外（schema retry 用盡、
timeout、連線失敗…）**不再讓整批 traceback 中止**，而是逐案記成 `planner_failed`
並繼續（否則失敗形態的分布量不到，連報告都產不出來）。這類失敗**不改變退出碼**——
planner 品質是本腳本量測的對象，不是工具故障；分數低同理不影響退出碼。失敗筆數、
案例名單與錯誤碼分布顯著呈現於 stdout 與報告的 `planner_eval.summary.planner_failures`，
且失敗案例在 Plan 層指標中**記為漏**（不是排除——排除會讓「難的案例崩潰」變成分數上升）。
例外：n>0 且**全部**案例都失敗時視為管道壞掉（endpoint 連不上、模型名打錯…）而非
量測結果，退出碼 1——這承接原本「planner 例外不捕捉」所守的「管道存在但恆空」防線。

報告檔名守門：gold_dir 含任何**未核准**案例（approved_by 空、或 review_status
非 approved）時，報告寫成 `wi-draft-latest.json`／`wi-draft-<stamp>.json`，
**拒寫** `wi-gold-latest.json`——覆核期間不得污染官方報告。

Plan 層自我指涉排除：gold 檔標 `plan_origin=<planner>_preannotation` 且
`ie_modified` 非 true 者，排除出 planner 段 Plan 層指標（planner 不得給自己
打分；見 `nlp/planner_eval.py` 的 SELF_REFERENTIAL_EXCLUSION_REASON）。

sanitize 觀測（v6 起）：報告的 `planner_eval.sanitize_reasons` 記
`contracts.sanitize_planner_output()` 的 reasons（含 evidence offset 修復次數）。
純觀測，不影響分數與退出碼；rule planner 不經 sanitize，恆為空。

執行來源自述（v7 起）：報告頂層 `planner_run` 記這趟是**哪個 planner、哪顆模型、
哪一版 prompt** 跑出來的——在此之前報告對自己的來源無法佐證，版本歸屬只能靠
人工命名的檔名（`docs/llm/eval-reports/local-14b/` 那批即是事後手改名）。
模型記兩個：`model_requested`（送出去的）與 `model_served`（伺服器回報的，證據力
較強）。rule planner 不碰 LLM，這些欄位恆為 null／空。
**不記** `llm_base_url` 與 `llm_api_key`：報告要入版控，base_url 有夾帶憑證的可能。
「報告不含 endpoint」是**整份**的性質，不只 `planner_run`——另一個入口是例外訊息
（httpx 的 `HTTPStatusError` 會把完整 URL 連同 userinfo 寫進訊息），由
`planner_eval._redact_urls()` 在寫進 `planner_error` 前遮成 `<redacted-url>`。
同版起 `gold_dir` 改記相對於 `ddm-v2/` 的路徑（絕對路徑會寫進本機路徑與 OS 使用者名）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
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
    planner_pipeline_broken,
    rule_based_plan,
    summarize_planner_results,
)

REPORT_SCHEMA_VERSION = "wi-gold-report-v7"

EXIT_CODE_HELP = (
    "exit codes: 0 = all green; "
    "1 = eval ran but found failures (compile fail / gold annotation defect / "
    "every planner case failed); "
    "2 = gold input unusable (gold_case_invalid load errors, or n=0). "
    "per-case planner failures alone do NOT change the exit code (they are the "
    "measurement target); see planner_eval.summary.planner_failures"
)


SANITIZE_REASONS_NOTE = (
    "sanitize_planner_output() 的 reasons（`nlp/contracts.py`）——觀測用，"
    "不影響分數與退出碼。`evidence_offset_repaired` 的次數＝模型算錯 evidence "
    "offset 但 `text` 可唯一定位、已被自動修正的次數；`evidence_text_not_found`／"
    "`evidence_text_ambiguous` 是修不了而被 validate 照常拒絕的（fail-closed）。"
    "phase=initial 是第一次呼叫、retry 是帶驗證錯誤重試的那次。"
    "rule planner 不經過 sanitize，恆為空。"
)


# C0（含 ESC/CR/LF）與 C1 控制字元；不含任何可見字元，剝掉不會動到合法模型名
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# 合法 tag 遠短於此（`qwen2.5:14b-instruct-q4_K_M` 是 26 字元）
MODEL_NAME_MAX_LEN = 200


def _sanitize_model_name(model: str) -> str:
    """`model_served` 是**遠端可控字串**（LLM 伺服器回應的 `model` 欄）——先剝控制
    字元再截斷。

    兩個 sink，一個修法：

    - **終端機**（本檔的 `print`，未經逸出）：回應若含 ESC 序列
      （``gpt-4\x1b[2J\x1b]0;pwned\x07``）可以清屏、改視窗標題，並**覆寫先前印出的
      內容——包括這次評測的其他數字**。這是本功能新增的 sink，比 JSON 那邊嚴重。
    - **報告 JSON**：`json.dumps` 會把 ESC 逸出成 `\u001b`（安全），但長度無界
      （`llm_client` 只做 `str(model)`，httpx 未設 response size limit），一個回應
      就能把 100KB 塞進要入版控的報告。

    **不用字元白名單**：合法 tag 本來就含 `:` `/` `.` `-`，未來也可能有非 ASCII；
    白名單會誤殺真值，而誤殺的後果是「報告說不出自己跑了哪顆模型」——正好摧毀這個
    欄位存在的目的。這裡只剝「不可見且能操控終端機」的那一類，其餘原樣保留。

    截斷**留痕**：截過的值帶 `…[truncated from N chars]`，不會看起來像完整值
    （自述欄位長成完整值的樣子就是另一種說謊）。
    """
    cleaned = _CONTROL_CHARS_RE.sub("", model)
    if len(cleaned) > MODEL_NAME_MAX_LEN:
        return f"{cleaned[:MODEL_NAME_MAX_LEN]}…[truncated from {len(cleaned)} chars]"
    return cleaned


PLANNER_RUN_NOTE = (
    "本報告的執行來源自述：這趟是哪個 planner、哪顆模型、哪一版 prompt 跑的。"
    "`model_requested`＝送出去的模型名（settings 的 DDM_LLM_MODEL）；"
    "`model_served`＝**伺服器回報**的模型名，證據力較強（ollama 的 tag 解析、"
    "伺服器端別名或 endpoint 被指到別顆模型時，兩者會分岔）——同一個問題，"
    "`wi_ai_service` 用的也是伺服器回報值（`llm_raw_response.model`）。"
    "⚠️ 伺服器若沒回 model 欄，`llm_client` 會退回請求值，此時 served 等於 "
    "requested 並非真的被證實。`model_served` 僅在**成功呼叫且回報值一致**時為"
    "單一字串；全案失敗（沒有任何成功呼叫）時為 null——此時 requested 仍是有用的"
    "資訊，不會一起消失；回報值分岐時 served 為 null 且 `model_served_variants` "
    "列出全部（不靜默挑一個）。"
    "⚠️ served 是**遠端可控字串**：寫入前已剝除控制字元並截斷至 "
    f"{MODEL_NAME_MAX_LEN} 字元，截過的值帶 `…[truncated from N chars]`。"
    "以上四欄與 `llm_timeout_s` 僅 --planner llm 有值；rule planner 不碰 LLM，恆為 "
    "null／空。"
    "刻意**不記** llm_base_url 與 llm_api_key——報告要入版控，base_url 有夾帶憑證的"
    "可能；重現指令見 docs/llm/eval-reports/local-14b/README.md。"
    "同一理由，`planner_eval.cases[*].planner_error` 的例外訊息會先把 URL 遮成 "
    "`<redacted-url>`（httpx 的 HTTP 錯誤訊息內嵌完整 endpoint 連同 userinfo），"
    "所以「不含 endpoint」是整份報告的性質，不只本區塊。"
)


class RunIdentity:
    """報告 `planner_run` 的來源欄；與 `SanitizeLog` 同樣是「跑的過程中收集」的觀測物。

    `model_served` 只有**呼叫成功**才知道（在 `LLMRawResponse.model` 裡），所以不能
    在建構 planner 時就定案——由 `_plan()` 每案 `observe_served()`，跑完再 `to_dict()`
    快照。全案失敗時 served 為 null 而 requested 仍在（失敗時「送出去的是哪顆」正是
    要查的資訊，不該一起消失）。
    """

    def __init__(
        self,
        planner: str,
        *,
        model_requested: str | None = None,
        prompt_version: str | None = None,
        llm_timeout_s: float | None = None,
    ) -> None:
        self.planner = planner
        self.model_requested = model_requested
        self.prompt_version = prompt_version
        self.llm_timeout_s = llm_timeout_s
        self.served: Counter = Counter()

    def observe_served(self, model: str | None) -> None:
        if model:
            self.served[_sanitize_model_name(model)] += 1

    def to_dict(self) -> dict:
        variants = sorted(self.served)
        return {
            "planner": self.planner,
            "model_requested": self.model_requested,
            # 恰好一種回報值才給單一字串；0 種（全案失敗）或 >1 種（分岐）皆為 null，
            # 由 variants 顯示實況——挑一個代表會讓分岐消失於無形
            "model_served": variants[0] if len(variants) == 1 else None,
            "model_served_variants": variants,
            "prompt_version": self.prompt_version,
            "llm_timeout_s": self.llm_timeout_s,
            "note": PLANNER_RUN_NOTE,
        }


def _repo_relative(path: Path) -> str:
    """報告用的 gold_dir：以 `ddm-v2/` 為基準的相對路徑。

    絕對路徑會把本機路徑與 OS 使用者名寫進要入版控的報告（worklog §9 S-6）。
    """
    return Path(os.path.relpath(path.resolve(), ROOT)).as_posix()


class SanitizeLog:
    """把 planner 的 sanitize reasons 收成可統計量（逐案 + 全案）。

    reasons 走 `LLMPlannerAdapter(on_sanitize=...)` callback 進來，callback 本身
    不知道 case id，所以由 `_plan()` 在呼叫 planner 前 `bind()`——評測迴圈是
    嚴格循序的（`wi_ai_eval` 逐案 await），不會有交錯。
    """

    def __init__(self) -> None:
        self.by_code: Counter = Counter()
        self.by_phase: Counter = Counter()
        self.by_case: dict[str, list[str]] = {}
        self._case_id: str | None = None

    def bind(self, case_id: str) -> None:
        self._case_id = case_id

    def observe(self, phase: str, reasons: list[str]) -> None:
        self.by_phase[phase] += len(reasons)
        for r in reasons:
            self.by_code[str(r).split(":", 1)[0]] += 1
        if self._case_id is not None and reasons:
            self.by_case.setdefault(self._case_id, []).extend(
                f"{phase}:{r}" for r in reasons
            )

    def to_dict(self) -> dict:
        return {
            "note": SANITIZE_REASONS_NOTE,
            "by_code": dict(self.by_code.most_common()),
            "by_phase": dict(self.by_phase.most_common()),
            "by_case": {k: v for k, v in sorted(self.by_case.items())},
        }


def _build_llm_plan_fn(
    timeout_s: float, sanitize_log: SanitizeLog
) -> tuple[PlannerFn, RunIdentity]:
    """顯式 --planner llm 才建構；需要已設定的 LLM endpoint。

    一併回傳這趟的 `RunIdentity` 給報告的 `planner_run`。`model_requested` 與建構
    client 用的是**同一次** `get_settings()`——不是因為再讀一次會拿到別的值
    （`get_settings` 有 lru_cache，同一次執行內必然同一個物件），而是為了讓
    「報告寫的」與「實際送出去的」在結構上同源：日後若有人把取值改成直接讀 env、
    或在 `cache_clear()` 之後另建 Settings，兩者才不會各走各的。
    `model_served`（伺服器回報值）由 `_plan()` 逐案 `observe_served()` 收。
    """
    from ddm_v2.nlp.contracts import ParseContext, SourceRef, WorkInstructionPlan
    from ddm_v2.nlp.llm_client import OpenAICompatClient
    from ddm_v2.nlp.llm_planner import LLMPlannerAdapter
    from ddm_v2.nlp.normalization import normalize
    from ddm_v2.nlp.planner_eval import gold_source_text
    from ddm_v2.nlp.prompts import plan_v1
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
    adapter = LLMPlannerAdapter(client, timeout_s=timeout_s, on_sanitize=sanitize_log.observe)
    identity = RunIdentity(
        "llm",
        model_requested=settings.llm_model,
        prompt_version=plan_v1.PROMPT_VERSION,
        llm_timeout_s=timeout_s,
    )

    async def _plan(data: dict) -> WorkInstructionPlan:
        sanitize_log.bind(str(data.get("id") or "unknown"))
        text = gold_source_text(data)
        norm = normalize(text)
        ctx = ParseContext(rule_set_code=str(data.get("rule_set_code") or "MINIMOST_FACTORY_V2"))
        output, raw = await adapter.plan(norm, ctx)
        identity.observe_served(raw.model if raw is not None else None)
        return WorkInstructionPlan(
            source_text=text,
            normalized_text=norm,
            language=output.language,
            source_ref=SourceRef(kind="interactive"),
            actions=output.actions,
            dependencies=output.dependencies,
            unresolved=list(output.unresolved),
        )

    # base_url／api_key 不進報告（報告入版控，base_url 有夾帶憑證的可能）
    return _plan, identity


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
    sanitize_log = SanitizeLog()
    # rule planner 不碰 LLM：來源欄恆 null／空。精確的性質是「**rule 分支在 runtime
    # 不呼叫 get_settings()**」——不是「完全不讀 settings」：`ddm_v2.settings` 在
    # module scope 就呼叫了六次 get_settings()（ROOT_DIR/SECRET_KEY/APP_NAME…），
    # 本腳本的 import 鏈一定會走到。零操作影響（每個欄位都有預設值），真正要保住的
    # 是 **`--planner rule` 不需要 LLM 設定就能跑**（有測試守）。
    run_identity = RunIdentity(RULE_PLANNER_NAME)
    if args.planner == "llm":
        plan_fn, run_identity = _build_llm_plan_fn(args.llm_timeout_s, sanitize_log)
    planner_name = run_identity.planner

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
        # v7：新增頂層 `planner_run`（planner/model_requested/model_served/
        # model_served_variants/prompt_version/llm_timeout_s＋note）——報告原本不記
        # 自己是哪顆模型、哪一版 prompt 跑的，版本歸屬只能靠人工命名的檔名。
        # model 記**兩個**：requested（送出去的）與 served（伺服器回報的，證據力較
        # 強，與 wi_ai_service 的 llm_raw_response.model 同源）。同版 `gold_dir` 改
        # 記相對於 ddm-v2/ 的路徑（原本是含 OS 使用者名的本機絕對路徑）、
        # `planner_eval.cases[*].planner_error` 的 URL 遮成 <redacted-url>。
        # 純加法＋兩個既有欄位的值域收斂，其餘形狀不變。
        # v3：planner_eval.summary 的 boundary → boundary_span（含 scored_cases/
        # trivially_empty_cases）、spec_targets.boundary_f1 → boundary_span_f1、
        # 新增 dependency_f1(=null)+note、gold_load_errors、動態 dataset_note；
        # cases 的 boundary_f1 → boundary_span_f1、新增 boundary_trivially_empty。
        # v6：新增 planner_eval.sanitize_reasons（by_code/by_phase/by_case）——
        # sanitize_planner_output 的 reasons 原本被丟棄，evidence offset 修復次數
        # 無處可量。純觀測欄位，不影響分數與退出碼；rule planner 恆為空。
        # v5：planner 個案失敗隔離——planner_eval.cases 新增 planner_failed/
        # planner_error/planner_error_codes/planner_elapsed_ms、summary 新增
        # planner_failures（count/rate/cases/error_codes）＋planner_latency_ms；
        # 個案失敗計入 Plan 層指標記為漏，且不改變退出碼（全案失敗除外）。
        # v4：Plan 層指標語意變更——自我指涉案例（plan_origin=planner 預標註且
        # ie_modified≠true）排除出 action_count_accuracy／boundary_span 聚合；
        # planner_eval.summary 新增 plan_metrics_n＋self_referential_excluded、
        # cases 新增 plan_origin/ie_modified；頂層新增 unapproved_cases（有值時
        # 報告檔名降級 wi-draft-*）。頂層 summary/cases（compile 段）自 v1 起形狀不變。
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "gold_schema_version": GOLD_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        # 相對於 ddm-v2/（不得寫入本機絕對路徑：報告要入版控）
        "gold_dir": _repo_relative(args.gold_dir),
        "planner_run": run_identity.to_dict(),
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
            "sanitize_reasons": sanitize_log.to_dict(),
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
    run_block = report["planner_run"]
    served = run_block["model_served"] or (
        f"分岐{run_block['model_served_variants']}" if run_block["model_served_variants"] else "n/a"
    )
    print(
        f"[run]      planner={planner_name}"
        f"  model_requested={run_block['model_requested'] or 'n/a'}"
        f"  model_served={served}"
        f"  prompt_version={run_block['prompt_version'] or 'n/a'}"
        f"  gold_dir={report['gold_dir']}"
    )
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
    failures = planner_summary["planner_failures"]
    if failures["count"]:
        rate = failures["rate"]
        codes = ", ".join(f"{k}={v}" for k, v in failures["error_codes"].items())
        print(
            f"           planner_failed={failures['count']}/{planner_summary['n']}"
            f" ({'n/a' if rate is None else f'{rate:.1%}'})"
            f"  error_codes: {codes or 'n/a'}"
            "  ← 個案失敗記為漏（Plan 層指標已含），不影響退出碼"
        )
    lat = planner_summary["planner_latency_ms"]
    print(
        f"           latency_ms total={lat['total']} mean={lat['mean']} "
        f"median={lat['median']} max={lat['max']}"
    )
    if sanitize_log.by_code:
        codes = ", ".join(f"{k}={v}" for k, v in sanitize_log.by_code.most_common())
        phases = ", ".join(f"{k}={v}" for k, v in sanitize_log.by_phase.most_common())
        print(
            f"           sanitize_reasons: {codes}  (phase: {phases})"
            "  ← 觀測量，不影響分數／退出碼"
        )
    for r in planner_results:
        mark = "OK" if r.ok else "GOLD-ERR"
        if r.planner_failed:
            mark = "PLANNER-FAIL"
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
    # 全案失敗＝管道壞掉（endpoint/模型設定問題），不是「planner 表現差」的量測結果
    pipeline_broken = planner_pipeline_broken(planner_results)
    if pipeline_broken:
        print(
            f"[planner]  ERROR: 全部 {len(planner_results)} 案 planner 皆失敗"
            "——視為管道壞掉（非量測結果），exit 1"
        )
    return 0 if (failed == 0 and planner_ok and not pipeline_broken) else 1


if __name__ == "__main__":
    raise SystemExit(main())
