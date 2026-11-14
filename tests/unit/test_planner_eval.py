"""Planner 段評測（text → plan）單元測試。

涵蓋：指標數學（exact counts，防「恆報 1.0」）、gold 標註缺損偵測（含缺欄位
的具名錯誤，不 traceback）、兩邊皆無 span 不給分（防獎勵棄權）、
normalized_text 不可比的誠實計分、**自我指涉排除**（plan_origin=planner 預標註
且 ie_modified≠true 者不得計入 Plan 層指標——含橡皮圖章回歸：把草稿只改身分
欄位轉正，指標不得動；把 summarize 的排除邏輯拆掉，這兩條必轉紅）、
seed gold 基線釘值、CLI 報告兩段皆在（防 planner 段被靜默跳過）、CLI 退出碼
守門（壞 gold → 1、compile 失敗 → 1、gold 輸入不可用 → 2——這三條是 mutation
證據：把 `wi_ai_eval.py` 的 `all(r.ok)` 或 `failed == 0` 拆掉必轉紅）、
未核准案例混入 gold_dir 時報告降級 wi-draft-*（拆掉 prefix 判斷必轉紅）、
**報告的執行來源自述**（v7 `planner_run`：rule 路徑 model/prompt_version 恆 null
且不需要 LLM 設定；ADR-037 後 llm 路徑已移除）、
**例外訊息的 URL 遮蔽**（`planner_error` 會把 httpx 訊息裡的 endpoint 連同
userinfo 寫進要入版控的報告——遮蔽後憑證不得出現，但 Pydantic 的診斷細節必須留著）、
**`model_served` 是遠端可控字串**（控制字元與超長值不得進報告或終端機，但合法 tag
不得被誤殺；分岐與截斷的端到端測試隨 LLM 路徑移除，單元層仍在）、
**被拒回應留存**（v8 `planner_raw_rejected`：失敗且帶得出回應才有值、沒有回應時為
null 且與「回了空字串」分得開；遮 URL 與已知憑證、超長截斷留痕；ADR-037 前另有走真的 HTTP 呼叫的
憑證 sentinel 探針，隨 LLM 路徑移除）
＋ `gold_dir` 為 repo 相對路徑（不得夾帶本機絕對路徑）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ddm_v2.nlp.contracts import WorkInstructionPlan
from ddm_v2.nlp.planner_eval import (
    PLANNER_RAW_REJECTED_MAX_LEN,
    RULE_PLANNER_NAME,
    evaluate_planner_all,
    evaluate_planner_case,
    load_gold_cases_checked,
    planner_pipeline_broken,
    planner_preannotation_origin,
    rule_based_plan,
    summarize_planner_results,
)
from ddm_v2.nlp.planner_ports import PlannerError

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "tests" / "gold" / "wi_plans"
DRAFT_DIR = ROOT / "tests" / "gold" / "wi_plans_draft"

# gold 基線釘值的唯一出處＝tests/unit/_seed_gold_baseline.py
# （與 test_gold_harvest_recompile.py 共用；不得在本檔另寫死）。
from _seed_gold_baseline import (  # noqa: E402
    GOLD_TOTAL_N,
    IE_MODIFIED_GOLD_N,
    PROMOTED_GOLD_N,
    SEED_GOLD_N,
)

# D3-028 後的 Plan 層基線（seed 3 筆＋ie_modified=true 轉正 6 筆＝分母 9）：
# accuracy＝5/9（g01/g05＋D3-028 判型答案 g55/g56/g57 對；g02 與 D3-022 重切
# 3 筆 rule planner 恆單 action 必錯）；boundary micro＝tp5 fp4 fn9 → F1 10/23。
#
# 兩次變動都是真 ground truth 進分母的合法結果，方向相反且都不是迴歸：
#   seed 基線 2/3、4/7 → D3-022 後 2/6、4/17（重切多 action gold 進來，**降**）
#                      → D3-028 後 5/9、10/23（單 action 判型答案進來，**升**）
# 誠實邊界：g55–g57 的 IE 修改是 action_type，evidence span 與 action 數維持
# planner 輸出——那 3 分 boundary 是「planner 自己的 span 經 IE 覆核未改」，
# 證據力弱於 IE 重新劃界的案例（引用時要連這句一起講）。
PLAN_METRICS_N = SEED_GOLD_N + IE_MODIFIED_GOLD_N
PLAN_ACCURACY = 5 / 9
BOUNDARY_MICRO = (5, 4, 9)  # (tp, fp, fn)
BOUNDARY_F1 = 10 / 23
# ie_modified=true 的轉正 gold（計入 Plan 層指標；錯誤排除即紅），依 IE 改了
# 什麼分兩族——兩族的預期分數相反，合併成一句斷言會說謊（見基線測試）
IE_MODIFIED_RESEG_GOLD_IDS = {   # D3-022：IE 重切（多 action）
    "g30_pick_dummy_dimm_debag",
    "g31_confirm_points_press_handle",
    "g32_pick_board_debag_place_bench",
}
IE_MODIFIED_TYPING_GOLD_IDS = {  # D3-028：IE 判型答案（單 action、span 未動）
    "g55_pick_screw_x1",
    "g56_place_heatsink_on_cpu",
    "g57_lh_pick_screw_from_box",
}
IE_MODIFIED_GOLD_IDS = IE_MODIFIED_RESEG_GOLD_IDS | IE_MODIFIED_TYPING_GOLD_IDS

# wi_ai_eval 的核准判定與 dataset_note（R4/R6 守門直接打函式，不繞 CLI）
sys.path.insert(0, str(ROOT / "scripts"))
import wi_ai_eval  # noqa: E402
from wi_ai_eval import _case_is_approved, _dataset_note  # noqa: E402


def _action(aid: str, atype: str, order: int, spans: list[tuple[int, int]], norm: str) -> dict:
    return {
        "action_id": aid,
        "action_type": atype,
        "sequence_order": order,
        "roles": {},
        "evidence": [{"start": s, "end": e, "text": norm[s:e]} for s, e in spans],
        "notes": None,
    }


def _gold_case(case_id: str, source_text: str, norm: str, actions: list[dict]) -> dict:
    return {
        "id": case_id,
        "source_text": source_text,
        "gold_schema_version": "wi-gold-v1",
        "approved_by": "seed",
        "plan": {
            "schema_version": "wi-plan-v1",
            "source_text": source_text,
            "normalized_text": norm,
            "language": "zh",
            "source_ref": {"kind": "interactive"},
            "actions": actions,
            "dependencies": [],
            "unresolved": [],
        },
        "synthetic_synonyms": [],
    }


def _plan_fn_returning(plan_dict: dict):
    async def fn(_data: dict) -> WorkInstructionPlan:
        return WorkInstructionPlan.model_validate(plan_dict)

    return fn


# ── 指標數學（exact counts；比對邏輯改壞必轉紅） ─────────────────────────────


async def test_perfect_planner_scores_one():
    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    gold = _gold_case(
        "syn_perfect",
        "拿取電動起子，依圖示鎖附兩顆螺絲",
        norm,
        [
            _action("a1", "acquire", 1, [(0, 6)], norm),
            _action("a2", "process", 2, [(10, 16)], norm),
        ],
    )
    result = await evaluate_planner_case(gold, _plan_fn_returning(gold["plan"]))
    assert result.ok
    assert result.action_count_match is True
    assert (result.boundary_tp, result.boundary_fp, result.boundary_fn) == (2, 0, 0)
    assert result.boundary_span_f1 == 1.0
    assert result.boundary_trivially_empty is False

    summary = summarize_planner_results([result], planner="test")
    assert summary["action_count_accuracy"] == 1.0
    assert summary["boundary_span"]["micro"]["f1"] == 1.0


async def test_count_mismatch_and_span_penalty_exact_counts():
    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    gold = _gold_case(
        "syn_mismatch",
        "拿取電動起子，依圖示鎖附兩顆螺絲",
        norm,
        [
            _action("a1", "acquire", 1, [(0, 6)], norm),
            _action("a2", "process", 2, [(10, 16)], norm),
        ],
    )
    pred = dict(gold["plan"])
    pred["actions"] = [_action("a1", "composite_unknown", 1, [(0, 16)], norm)]
    result = await evaluate_planner_case(gold, _plan_fn_returning(pred))
    assert result.ok  # 分數差 ≠ 評測不成立
    assert result.action_count_match is False
    assert (result.boundary_tp, result.boundary_fp, result.boundary_fn) == (0, 1, 2)
    assert result.boundary_span_f1 == 0.0

    summary = summarize_planner_results([result], planner="test")
    assert summary["action_count_accuracy"] == 0.0
    assert summary["boundary_span"]["micro"] == {
        "tp": 0,
        "fp": 1,
        "fn": 2,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }


async def test_partial_span_overlap_is_not_a_match():
    """嚴格 (start,end) 相等：部分重疊不算 TP。"""
    norm = "abcdef"
    gold = _gold_case("syn_partial", "abcdef", norm, [_action("a1", "acquire", 1, [(0, 6)], norm)])
    pred = dict(gold["plan"])
    pred["actions"] = [_action("a1", "acquire", 1, [(0, 5)], norm)]
    result = await evaluate_planner_case(gold, _plan_fn_returning(pred))
    assert (result.boundary_tp, result.boundary_fp, result.boundary_fn) == (0, 1, 1)
    assert result.boundary_span_f1 == 0.0


# ── gold 標註缺損偵測（不硬湊、不靜默、不 traceback） ────────────────────────


async def test_boundary_unannotated_case_flagged_and_excluded():
    norm = "拿起dimm"
    gold = _gold_case("syn_unannotated", "拿起DIMM", norm, [_action("a1", "acquire", 1, [], norm)])
    result = await evaluate_planner_case(gold, rule_based_plan)
    assert result.ok is False
    assert result.boundary_annotated is False
    assert result.boundary_span_f1 is None
    assert any("missing plan.actions[].evidence" in e for e in result.errors)

    summary = summarize_planner_results([result], planner="test")
    assert summary["boundary_span"]["annotated_cases"] == 0
    assert summary["boundary_span"]["unannotated_cases"] == ["syn_unannotated"]
    assert summary["boundary_span"]["micro"]["f1"] is None
    # action-count 仍可算（不依賴 evidence）
    assert summary["action_count_accuracy"] == 1.0


async def test_gold_offset_out_of_range_detected():
    """g05 曾有 end=12 > len(norm)=11 的越界 offset；slice clamp 藏不住。"""
    norm = "依照sop完成其餘作業"  # len 11
    gold = _gold_case("syn_oor", "依照SOP完成其餘作業", norm, [])
    gold["plan"]["actions"] = [
        {
            "action_id": "a1",
            "action_type": "composite_unknown",
            "sequence_order": 1,
            "roles": {},
            "evidence": [{"start": 0, "end": 12, "text": norm}],
            "notes": None,
        }
    ]
    result = await evaluate_planner_case(gold, rule_based_plan)
    assert result.ok is False
    assert result.boundary_annotated is False
    assert any(e.startswith("gold_evidence_offset_out_of_range:a1") for e in result.errors)


async def test_gold_evidence_text_mismatch_detected():
    norm = "拿起dimm"
    gold = _gold_case("syn_textmis", "拿起DIMM", norm, [])
    gold["plan"]["actions"] = [
        {
            "action_id": "a1",
            "action_type": "acquire",
            "sequence_order": 1,
            "roles": {},
            "evidence": [{"start": 0, "end": 2, "text": "dimm"}],
            "notes": None,
        }
    ]
    result = await evaluate_planner_case(gold, rule_based_plan)
    assert result.ok is False
    assert any(e.startswith("gold_evidence_text_mismatch:a1") for e in result.errors)


async def test_gold_evidence_missing_start_end_is_named_error_not_keyerror():
    """evidence 缺 start/end：具名 gold_evidence_missing_field，不能 KeyError traceback。"""
    norm = "拿起dimm"
    gold = _gold_case("syn_missing_field", "拿起DIMM", norm, [])
    gold["plan"]["actions"] = [
        {
            "action_id": "a1",
            "action_type": "acquire",
            "sequence_order": 1,
            "roles": {},
            "evidence": [{"start": 0, "text": "拿起"}],  # 缺 end
            "notes": None,
        }
    ]
    result = await evaluate_planner_case(gold, rule_based_plan)
    assert result.ok is False
    assert result.boundary_annotated is False
    assert any(e.startswith("gold_evidence_missing_field:a1") for e in result.errors)


async def test_source_text_integrity_mismatch():
    norm = "拿起dimm"
    gold = _gold_case("syn_src", "拿起DIMM", norm, [_action("a1", "acquire", 1, [(0, 6)], norm)])
    gold["source_text"] = "別的字"
    result = await evaluate_planner_case(gold, rule_based_plan)
    assert result.ok is False
    assert any(e.startswith("gold_case_invalid:") for e in result.errors)


async def test_composite_unknown_both_empty_is_trivially_empty_not_scored():
    """兩邊皆無 span：不給 f1=1.0——那會讓「全面棄權、不給 evidence」拿滿分。"""
    norm = "依照sop完成其餘作業"
    gold = _gold_case(
        "syn_cu", "依照SOP完成其餘作業", norm, [_action("a1", "composite_unknown", 1, [], norm)]
    )
    pred = dict(gold["plan"])
    pred["actions"] = [_action("a1", "composite_unknown", 1, [], norm)]
    result = await evaluate_planner_case(gold, _plan_fn_returning(pred))
    assert result.ok  # composite_unknown 合法無 evidence，非標註缺損
    assert result.boundary_annotated is True
    assert result.boundary_trivially_empty is True
    assert result.boundary_span_f1 is None
    assert (result.boundary_tp, result.boundary_fp, result.boundary_fn) == (0, 0, 0)

    summary = summarize_planner_results([result], planner="test")
    assert summary["boundary_span"]["annotated_cases"] == 1
    assert summary["boundary_span"]["scored_cases"] == 0
    assert summary["boundary_span"]["trivially_empty_cases"] == ["syn_cu"]
    assert summary["boundary_span"]["micro"]["f1"] is None


async def test_normalized_text_mismatch_counts_fp_fn():
    norm = "拿起dimm"
    gold = _gold_case("syn_norm", "拿起DIMM", norm, [_action("a1", "acquire", 1, [(0, 6)], norm)])
    pred = dict(gold["plan"])
    pred["normalized_text"] = "完全不同的字串"
    pred["actions"] = [_action("a1", "acquire", 1, [(0, 3)], "完全不同的字串")]
    result = await evaluate_planner_case(gold, _plan_fn_returning(pred))
    assert result.ok  # planner 品質問題，不是評測不成立
    assert result.boundary_comparable is False
    assert (result.boundary_tp, result.boundary_fp, result.boundary_fn) == (0, 1, 1)
    assert any(e.startswith("normalized_text_mismatch") for e in result.errors)


# ── 自我指涉排除（P0-1）：planner 不得給自己打分 ─────────────────────────────


def _self_ref_case(case_id: str, *, ie_modified) -> dict:
    norm = "拿起dimm"
    gold = _gold_case(case_id, "拿起DIMM", norm, [_action("a1", "acquire", 1, [(0, 6)], norm)])
    gold["approved_by"] = "IEC141289"
    gold["review_status"] = "approved"
    gold["plan_origin"] = planner_preannotation_origin(RULE_PLANNER_NAME)
    if ie_modified is not ...:
        gold["ie_modified"] = ie_modified
    return gold


async def test_unmodified_preannotation_excluded_from_plan_metrics():
    """plan_origin=本 planner 且 ie_modified=false → Plan 層指標排除、名單進 summary。"""
    gold = _self_ref_case("syn_selfref", ie_modified=False)
    result = await evaluate_planner_case(gold, _plan_fn_returning(gold["plan"]))
    assert result.plan_origin == planner_preannotation_origin(RULE_PLANNER_NAME)
    assert result.ie_modified is False

    summary = summarize_planner_results([result], planner=RULE_PLANNER_NAME)
    assert summary["n"] == 1
    assert summary["plan_metrics_n"] == 0
    assert summary["self_referential_excluded"]["count"] == 1
    assert summary["self_referential_excluded"]["cases"] == ["syn_selfref"]
    assert "零證據力" in summary["self_referential_excluded"]["reason"]
    # 排除後無可計分案例：指標 None，不是 1.0
    assert summary["action_count_accuracy"] is None
    assert summary["boundary_span"]["micro"]["f1"] is None


async def test_ie_modified_promotion_is_real_ground_truth():
    """ie_modified=true＝IE 改過＝真實 ground truth，照常計入。"""
    gold = _self_ref_case("syn_ie_edited", ie_modified=True)
    result = await evaluate_planner_case(gold, _plan_fn_returning(gold["plan"]))
    summary = summarize_planner_results([result], planner=RULE_PLANNER_NAME)
    assert summary["plan_metrics_n"] == 1
    assert summary["self_referential_excluded"]["count"] == 0
    assert summary["action_count_accuracy"] == 1.0


async def test_missing_ie_modified_is_conservatively_excluded():
    """有 plan_origin 但缺 ie_modified（或非 bool）→ 保守排除（缺欄不能當通行證）。"""
    gold = _self_ref_case("syn_missing_flag", ie_modified=...)
    result = await evaluate_planner_case(gold, _plan_fn_returning(gold["plan"]))
    assert result.ie_modified is None
    summary = summarize_planner_results([result], planner=RULE_PLANNER_NAME)
    assert summary["self_referential_excluded"]["cases"] == ["syn_missing_flag"]


async def test_other_planner_not_excluded_by_rule_preannotation_origin():
    """排除是「本 planner」對「本 planner 的預標註」——評 llm 時 rule 預標註不排除。"""
    gold = _self_ref_case("syn_cross", ie_modified=False)
    result = await evaluate_planner_case(gold, _plan_fn_returning(gold["plan"]))
    summary = summarize_planner_results([result], planner="llm")
    assert summary["self_referential_excluded"]["count"] == 0
    assert summary["plan_metrics_n"] == 1


async def test_rubber_stamp_promotion_does_not_move_plan_metrics(tmp_path: Path):
    """橡皮圖章實驗（P0-1 驗收）：把全部草稿只改身分欄位「轉正」，Plan 層指標
    必須與 3 筆 seed gold 的基線完全相同——未修改的預標註對 planner 指標零證據力。

    mutation 證據：把 summarize_planner_results 的 is_self_referential 排除拆掉，
    accuracy 會從 2/3 跳到 (2+N)/(3+N)（審查實測 0.9811）→ 本測試必紅。
    """
    from gold_harvest import REVIEW_STATE_FILENAME

    # review-state.json 是 IE 覆核狀態檔（D3-015），不是草稿——橡皮圖章實驗不搬它
    draft_files = sorted(
        p for p in DRAFT_DIR.glob("*.json") if p.name != REVIEW_STATE_FILENAME
    )
    if not draft_files:
        pytest.skip("wi_plans_draft 目前沒有草稿（可能全數已轉正）——實驗無素材")

    gold = tmp_path / "wi_plans"
    gold.mkdir()
    for p in sorted(GOLD_DIR.glob("*.json")):
        shutil.copy(p, gold / p.name)
    for p in draft_files:
        d = json.loads(p.read_text(encoding="utf-8"))
        # 橡皮圖章：只動身分欄位，內容一字不改
        d.update(
            approved_by="IEC_RUBBER_STAMP",
            review_status="approved",
            split="test",
            ie_modified=False,
        )
        (gold / p.name).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    _base_results, base = await evaluate_planner_all(GOLD_DIR)
    _results, stamped = await evaluate_planner_all(gold)

    assert stamped["n"] == base["n"] + len(draft_files)
    # 基線 gold 本身已含 D3-019 轉正的自我指涉排除（PROMOTED_GOLD_N 筆）；
    # 橡皮圖章再加 len(draft_files) 筆
    assert (
        stamped["self_referential_excluded"]["count"]
        == base["self_referential_excluded"]["count"] + len(draft_files)
    )
    assert stamped["plan_metrics_n"] == base["plan_metrics_n"]
    # Plan 層指標不得因未修改的轉正而動（更不得往 1.0 跳）
    assert stamped["action_count_accuracy"] == base["action_count_accuracy"]
    assert stamped["boundary_span"]["micro"] == base["boundary_span"]["micro"]


# ── gold 載入層：檔案壞掉 → 具名 gold_case_invalid（不 traceback） ────────────


def test_load_gold_cases_checked_flags_malformed_and_missing_plan(tmp_path: Path):
    (tmp_path / "a_malformed.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "b_missing_plan.json").write_text(
        json.dumps({"id": "x", "source_text": "拿起DIMM"}), encoding="utf-8"
    )
    (tmp_path / "c_bad_plan_schema.json").write_text(
        json.dumps({"id": "y", "source_text": "s", "plan": {"schema_version": "wi-plan-v1"}}),
        encoding="utf-8",
    )
    cases, errors = load_gold_cases_checked(tmp_path)
    assert cases == []
    by_file = {e.file: e.error for e in errors}
    assert by_file["a_malformed.json"].startswith("gold_case_invalid:malformed_json:")
    assert by_file["b_missing_plan.json"].startswith("gold_case_invalid:missing_plan:")
    assert by_file["c_bad_plan_schema.json"].startswith("gold_case_invalid:plan_schema:")


def test_load_gold_cases_checked_passes_valid_gold():
    cases, errors = load_gold_cases_checked(GOLD_DIR)
    assert errors == []
    assert len(cases) == GOLD_TOTAL_N


# ── gold 基線（seed 3＋D3-019 轉正 21；rule_based planner 的實際分數釘值） ───


async def test_seed_gold_baseline_pinned():
    """基線釘值：planner 改進時同步更新（如同黃金值）。

    也同時殺掉兩類 mutation：accuracy 恆 1.0（數值不符）與 planner 段恆空
    （n≠GOLD_TOTAL_N）。

    `ie_modified: false` 的轉正（原樣核准）→ 排除出 Plan 層指標；
    **`ie_modified: true`（IE 改過 plan＝真實 ground truth）→ 計入**。分母
    3（seed）→6（D3-022 重切 3 筆）→9（D3-028 判型答案 3 筆）；分數
    2/3、4/7 →2/6、4/17 →5/9、10/23 **兩個方向都是預期且誠實的**：
    重切族是多 action（rule planner 恆單 action → 必然拿 0，分數下降）、
    判型族是單 action 且 span 未動（必然拿 1，分數上移）。ie_modified=true
    案例被錯誤排除（plan_metrics_n 回落、分數回跳前一輪）即紅。
    """
    results, summary = await evaluate_planner_all(GOLD_DIR)
    assert summary["planner"] == RULE_PLANNER_NAME
    assert summary["n"] == GOLD_TOTAL_N
    # seed gold 不是預標註轉正（無 plan_origin）——不觸發自我指涉排除；
    # ie_modified=false 的轉正全數排除、ie_modified=true 的重切轉正計入
    assert summary["plan_metrics_n"] == PLAN_METRICS_N
    assert (
        summary["self_referential_excluded"]["count"]
        == PROMOTED_GOLD_N - IE_MODIFIED_GOLD_N
    )
    assert all(
        c.startswith("g") for c in summary["self_referential_excluded"]["cases"]
    )
    # mutation 證據（D3-022）：ie_modified=true 的重切 gold 不得進排除名單
    assert not (
        IE_MODIFIED_GOLD_IDS & set(summary["self_referential_excluded"]["cases"])
    ), "ie_modified=true 的真 ground truth 被錯誤排除出 Plan 層指標"
    assert all(r.ok for r in results), [r.errors for r in results]

    # rule_based_v1 永遠單 action：g01/g05 數對、g02（2 actions）與 D3-022
    # 重切 3 筆（2/2/3 actions）數錯
    assert summary["action_count_accuracy"] == pytest.approx(PLAN_ACCURACY)
    micro = summary["boundary_span"]["micro"]
    assert (micro["tp"], micro["fp"], micro["fn"]) == BOUNDARY_MICRO
    assert micro["f1"] == pytest.approx(BOUNDARY_F1)
    assert summary["boundary_span"]["annotated_cases"] == PLAN_METRICS_N
    assert summary["boundary_span"]["scored_cases"] == PLAN_METRICS_N
    assert summary["boundary_span"]["unannotated_cases"] == []
    assert summary["boundary_span"]["trivially_empty_cases"] == []

    by_id = {r.case_id: r for r in results}
    assert by_id["g01_acquire_dimm"].boundary_span_f1 == 1.0
    assert by_id["g02_screwdriver_screw_x2"].boundary_span_f1 == 0.0
    assert by_id["g05_composite_unknown"].boundary_span_f1 == 1.0
    assert by_id["g02_screwdriver_screw_x2"].action_count_match is False
    # ie_modified=true 的 gold 分兩族，逐族釘**相反**的預期分數——合成一句
    # 「全部拿 0」會在 D3-028 這種單 action 判型答案進來時整片說謊：
    # - D3-022 重切族（多 action）：rule planner 恆單 action → 必然 0；
    # - D3-028 判型族（單 action、span 未動）：必然 1（IE 改的是 action_type）。
    for gid in sorted(IE_MODIFIED_RESEG_GOLD_IDS):
        r = by_id[gid]
        assert r.ie_modified is True, f"{gid}：ie_modified 宣告遺失（會被錯誤排除）"
        assert r.action_count_match is False, f"{gid}：rule planner 恆單 action"
        assert r.boundary_span_f1 == 0.0, f"{gid}：整句 span 對重切 gold 必為 0"
    for gid in sorted(IE_MODIFIED_TYPING_GOLD_IDS):
        r = by_id[gid]
        assert r.ie_modified is True, f"{gid}：ie_modified 宣告遺失（會被錯誤排除）"
        # IE 改的是 action_type，action 數與 evidence span 維持 planner 輸出——
        # 這兩分是「planner 自己的切分經 IE 覆核未改」，證據力弱於重切族
        assert r.action_count_match is True, f"{gid}：單 action 判型答案，數應相符"
        assert r.boundary_span_f1 == 1.0, f"{gid}：span 未經 IE 改動，應完全相符"

    # 未達 §19 P2 門檻——量測管道在，分數如實呈現
    # （spec＝docs/architecture/wi-ai-parser-system-spec.md；key 是 boundary_span_f1，
    #   不是 §14.4 的「boundary/dependency F1」整列——dependency 未實作）
    assert summary["spec_targets"] == {
        "action_count_exact_match": 0.95,
        "boundary_span_f1": 0.90,
    }
    assert summary["dependency_f1"] is None
    assert "未實作" in summary["dependency_f1_note"]
    # rule 路徑分數是退化的（gold 集形狀，非 planner 能力）——報告必須點明
    assert summary["degenerate_planner_note"]


async def test_non_rule_planner_has_no_degenerate_note():
    norm = "拿起dimm"
    gold = _gold_case("syn_x", "拿起DIMM", norm, [_action("a1", "acquire", 1, [(0, 6)], norm)])
    result = await evaluate_planner_case(gold, _plan_fn_returning(gold["plan"]))
    summary = summarize_planner_results([result], planner="llm")
    assert summary["degenerate_planner_note"] is None


# ── planner 個案失敗隔離（v5）──────────────────────────────────────────────


def _plan_fn_raising(exc: BaseException):
    async def fn(_data: dict):
        raise exc

    return fn


async def test_planner_case_failure_is_isolated_not_fatal():
    """單案 planner 失敗 → 記成該案的錯誤並回傳結果，不讓整批 traceback。"""
    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    gold = _gold_case(
        "syn_fail",
        "拿取電動起子，依圖示鎖附兩顆螺絲",
        norm,
        [
            _action("a1", "acquire", 1, [(0, 6)], norm),
            _action("a2", "process", 2, [(7, 16)], norm),
        ],
    )
    exc = PlannerError(
        "planner_schema_invalid:['evidence_offset_oor:a2']",
        errors=["evidence_offset_oor:a2"],
    )
    result = await evaluate_planner_case(gold, _plan_fn_raising(exc))

    assert result.planner_failed is True
    # gold 沒有缺損 → ok 維持 True（退出碼契約不因 planner 品質而變）
    assert result.ok is True
    assert result.planner_error is not None
    assert "evidence_offset_oor" in result.planner_error
    assert result.planner_error_codes == ["evidence_offset_oor"]
    # 錯誤訊息必須進逐案 errors（報告與 stdout 都看得到，不是靜默吸收）
    assert any(e.startswith("planner_failed:") for e in result.errors)


async def test_planner_case_failure_scored_as_miss_not_excluded():
    """失敗案例記為漏：pred 0 個 action、gold span 全 FN、F1=0——不是排除。

    mutation 證據：若改成排除（不計入分母或給 None），本測試轉紅。排除會讓
    「難的案例崩潰」表現為分數上升。
    """
    norm = "拿取電動起子,依圖示鎖附兩顆螺絲"
    gold = _gold_case(
        "syn_fail_score",
        "拿取電動起子，依圖示鎖附兩顆螺絲",
        norm,
        [
            _action("a1", "acquire", 1, [(0, 6)], norm),
            _action("a2", "process", 2, [(7, 16)], norm),
        ],
    )
    result = await evaluate_planner_case(gold, _plan_fn_raising(RuntimeError("boom")))

    assert result.pred_action_count == 0
    assert result.action_count_match is False
    assert (result.boundary_tp, result.boundary_fp, result.boundary_fn) == (0, 0, 2)
    assert result.boundary_span_f1 == 0.0
    assert result.boundary_trivially_empty is False
    assert result.planner_error_codes == ["RuntimeError"]

    summary = summarize_planner_results([result], planner="llm")
    assert summary["plan_metrics_n"] == 1  # 仍在分母
    assert summary["action_count_accuracy"] == 0.0
    assert summary["boundary_span"]["scored_cases"] == 1
    assert summary["boundary_span"]["micro"]["f1"] == 0.0


async def test_planner_failures_are_summarized_with_error_codes():
    """失敗形態要能統計：count/rate/cases/error_codes 進 summary。"""
    norm = "拿起dimm"
    gold_ok = _gold_case("syn_ok", "拿起DIMM", norm, [_action("a1", "acquire", 1, [(0, 6)], norm)])
    gold_bad = _gold_case("syn_bad", "拿起DIMM", norm, [_action("a1", "acquire", 1, [(0, 6)], norm)])

    ok_result = await evaluate_planner_case(gold_ok, _plan_fn_returning(gold_ok["plan"]))
    bad_result = await evaluate_planner_case(
        gold_bad,
        _plan_fn_raising(
            PlannerError(
                "planner_schema_invalid:['evidence_offset_oor:a2', 'evidence_text_mismatch:a1']",
                errors=["evidence_offset_oor:a2", "evidence_text_mismatch:a1"],
            )
        ),
    )
    summary = summarize_planner_results([ok_result, bad_result], planner="llm")

    failures = summary["planner_failures"]
    assert failures["count"] == 1
    assert failures["rate"] == 0.5
    assert failures["cases"] == ["syn_bad"]
    assert failures["error_codes"] == {"evidence_offset_oor": 1, "evidence_text_mismatch": 1}
    assert summary["planner_latency_ms"]["total"] >= 0


def test_planner_pipeline_broken_only_when_all_cases_fail():
    """全滅＝管道壞掉（CLI exit 1）；部分失敗是量測結果（不影響退出碼）。"""
    from ddm_v2.nlp.planner_eval import PlannerCaseResult

    def _r(failed: bool) -> PlannerCaseResult:
        return PlannerCaseResult(
            case_id="x",
            ok=True,
            gold_action_count=1,
            pred_action_count=0 if failed else 1,
            action_count_match=not failed,
            boundary_annotated=True,
            boundary_comparable=not failed,
            boundary_trivially_empty=False,
            boundary_tp=0,
            boundary_fp=0,
            boundary_fn=1,
            boundary_span_f1=0.0,
            planner_failed=failed,
        )

    assert planner_pipeline_broken([]) is False
    assert planner_pipeline_broken([_r(True), _r(True)]) is True
    assert planner_pipeline_broken([_r(True), _r(False)]) is False


# ── 例外訊息的 URL 遮蔽（憑證不得進入要入版控的報告）──────────────────────────

_CRED_URL = "http://svc-account:hunter2-SECRET@llm-endpoint.invalid:11434/v1/chat/completions"


def _http_status_error(url: str = _CRED_URL) -> Exception:
    """真的用 httpx 產生的 401 HTTPStatusError（訊息格式以 httpx 實作為準，不自己編）。"""
    import httpx

    request = httpx.Request("POST", url)
    try:
        httpx.Response(401, request=request).raise_for_status()
    except httpx.HTTPStatusError as exc:
        return exc
    raise AssertionError("raise_for_status 沒有拋出——httpx 行為變了")


def _plan_fn_raising(exc: Exception):
    async def fn(_data: dict):
        raise exc

    return fn


@pytest.mark.asyncio
async def test_planner_error_redacts_endpoint_credentials():
    """httpx 的 `HTTPStatusError` 訊息內嵌完整 request URL **連同 userinfo**，而
    `planner_error` 會被寫進要入版控的評測報告——帳密不得留在裡面。

    觸發條件是日常的（401 key 錯／過期、404、429、5xx），且 endpoint 設錯正是
    「跑一次、失敗、修好再跑」的時候，那批報告最可能被一起 commit。
    mutation 證據：把 `_redact_urls()` 從 `planner_error` 上拿掉，本測試必轉紅。
    """
    data = _load_g01()
    result = await evaluate_planner_case(data, _plan_fn_raising(_http_status_error()))

    assert result.planner_failed is True
    blob = result.planner_error + " " + " ".join(result.errors)
    assert "hunter2-SECRET" not in blob
    assert "svc-account" not in blob
    assert "llm-endpoint.invalid" not in blob
    assert "<redacted-url>" in result.planner_error
    # 診斷力不得被犧牲：類名、狀態碼與原因短語都還在
    assert result.planner_error.startswith("HTTPStatusError:")
    assert "401 Unauthorized" in result.planner_error
    assert result.planner_error_codes == ["HTTPStatusError"]


@pytest.mark.asyncio
async def test_planner_error_keeps_schema_diagnostics_while_redacting():
    """遮蔽只吃 URL：schema 失敗訊息裡的 `input_value='多顆'` 這類線索必須留著。

    這條是防「修法過當」的反向守衛——把整段訊息換成錯誤碼（或只留狀態碼）會讓
    `g48`（quantity 收到字串「多顆」）那類敗因從報告裡消失。
    """
    from ddm_v2.nlp.planner_ports import PlannerError

    msg = (
        "planner_schema_invalid:[\"json_or_schema:1 validation error for PlannerOutput\\n"
        "  Input should be a valid number, unable to parse string as a number "
        "[type=float_parsing, input_value='多顆', input_type=str]\\n"
        "  For further information visit https://errors.pydantic.dev/2.11/v/float_parsing\"]"
    )
    result = await evaluate_planner_case(
        _load_g01(), _plan_fn_raising(PlannerError(msg, errors=["json_or_schema:float_parsing"]))
    )

    assert "input_value='多顆'" in result.planner_error
    assert "float_parsing" in result.planner_error
    assert "errors.pydantic.dev" not in result.planner_error  # URL 仍被遮
    assert result.planner_error_codes == ["json_or_schema"]





# ── 被拒回應留存（T-12；ADR-033 §4.4）────────────────────────────────────────
#
# 為什麼要留：只記錯誤碼的話，「那份被拒的輸出切分得對不對」事後無從回答。
# ADR-033 §1.4(c) 的 g07／g23／g46 都輸出了 `a2` 而 gold 是單一 action——契約放寬
# 後它們會從「硬失敗」變成「切分錯誤」，而那正是要量的東西。

# 被拒回應的樣子：模型加了散文前綴（JSON 解析就失敗）＋切成兩個 action
_REJECTED_TWO_ACTION_JSON = (
    '{"language":"zh-TW","actions":['
    '{"action_id":"a1","action_type":"acquire","sequence_order":1,"roles":{},"evidence":[]},'
    '{"action_id":"a2","action_type":"process","sequence_order":2,"roles":{},"evidence":[]}'
    '],"dependencies":[],"unresolved":[]}'
)


def _planner_error_with_raw(content: str) -> PlannerError:
    """帶 `raw` 的 PlannerError＝schema retry 用盡的真實形狀（舊 LLM adapter 掛 raw2）。"""
    from ddm_v2.nlp.planner_ports import PlannerRawResponse

    return PlannerError(
        "planner_schema_invalid:['json_or_schema:Expecting value']",
        raw=PlannerRawResponse(content=content, model="eval-selftest-model:0b"),
        errors=["json_or_schema:Expecting value"],
    )


async def test_rejected_raw_response_is_preserved_when_case_fails():
    """失敗案例要留下**被拒絕的原始回應**——否則切分對錯事後答不出來。

    mutation 證據：把 `planner_raw_rejected` 從 `PlannerCaseResult` 拿掉、或不在
    except 分支填值，本測試必轉紅。
    """
    data = _load_g01()
    result = await evaluate_planner_case(
        data, _plan_fn_raising(_planner_error_with_raw(_REJECTED_TWO_ACTION_JSON))
    )

    assert result.planner_failed is True
    assert result.planner_raw_rejected == _REJECTED_TWO_ACTION_JSON
    # 這個欄位存在的目的：看得出模型把它切成幾段（此例 a1+a2，gold 是單一 action）
    assert '"a2"' in result.planner_raw_rejected
    assert result.gold_action_count == 1


async def test_rejected_raw_is_null_when_case_succeeds():
    """成功的案例沒有「被拒回應」——欄位必須是 null，不得拿成功的輸出充數。"""
    data = _load_g01()
    result = await evaluate_planner_case(data, _plan_fn_returning(data["plan"]))

    assert result.planner_failed is False
    assert result.planner_raw_rejected is None


async def test_rejected_raw_distinguishes_no_response_from_empty_response():
    """`null`＝這次失敗沒有回應可留；`""`＝伺服器真的回了空字串。兩者不可混為一談
    （混掉的話「模型到底吐了什麼」會退化成「不知道」）。"""
    data = _load_g01()

    # timeout／連線失敗：例外根本不帶回應
    no_resp = await evaluate_planner_case(data, _plan_fn_raising(RuntimeError("boom")))
    assert no_resp.planner_failed is True
    assert no_resp.planner_raw_rejected is None

    # PlannerError 但沒帶 raw（例如 wi_ai_service 自行拋的）
    bare = await evaluate_planner_case(
        data, _plan_fn_raising(PlannerError("planner_schema_invalid:[]", errors=["x:y"]))
    )
    assert bare.planner_raw_rejected is None

    # 伺服器回了空字串：留 ""（可判讀為「模型什麼都沒說」），不是 null
    empty = await evaluate_planner_case(data, _plan_fn_raising(_planner_error_with_raw("")))
    assert empty.planner_raw_rejected == ""


async def test_rejected_raw_redacts_urls_and_known_secrets():
    """被拒回應是**遠端可控字串**而報告要入版控：URL 與已知憑證都不得留在裡面。

    兩個來源都是真的：URL 進得來（回聲式 proxy 把 upstream 抄進回應本文，或模型
    自己吐一個），api key 進得來（伺服器拿得到我們送出的 `Authorization: Bearer`）。
    `_redact_urls` 只擋內嵌 URL，擋不到裸 token——所以兩層都要。

    mutation 證據：把 `_sanitize_rejected_raw` 的 `_redact_urls()` 或
    `_redact_secrets()` 任一拿掉，本測試必轉紅。
    """
    api_key = "sk-t12-unit-sentinel-MUST-NOT-APPEAR"
    content = (
        f"upstream=http://svc-account:hunter2-SECRET@llm-endpoint.invalid:11434/v1 "
        f"auth=Bearer {api_key}\n" + _REJECTED_TWO_ACTION_JSON
    )
    result = await evaluate_planner_case(
        _load_g01(), _plan_fn_raising(_planner_error_with_raw(content)), secrets=(api_key,)
    )

    raw = result.planner_raw_rejected
    assert raw is not None
    for secret in ("hunter2-SECRET", "svc-account", "llm-endpoint.invalid", api_key):
        assert secret not in raw
    assert "<redacted-url>" in raw
    assert "<redacted-secret>" in raw
    # 遮蔽不得把回應變成看不出切分（那會摧毀本欄位存在的目的）
    assert '"a2"' in raw
    assert '"action_type":"process"' in raw


async def test_rejected_raw_is_truncated_with_a_visible_trace():
    """回應長度無界（外部 planner 回應不可信，未設 response size limit）——截斷且**留痕**。

    留痕是重點：一份被截斷卻裝成完整的「原始回應」，會讓事後判讀切分時得出錯的結論。

    mutation 證據：把 `_sanitize_rejected_raw` 的截斷拿掉，本測試必轉紅。
    """
    content = _REJECTED_TWO_ACTION_JSON + "填" * 50_000
    result = await evaluate_planner_case(
        _load_g01(), _plan_fn_raising(_planner_error_with_raw(content))
    )

    raw = result.planner_raw_rejected
    assert raw is not None
    assert len(raw) < len(content)
    assert raw.startswith(_REJECTED_TWO_ACTION_JSON[:50])  # 前段（切分證據）保住
    assert f"[truncated from {len(content)} chars]" in raw
    assert len(raw) <= PLANNER_RAW_REJECTED_MAX_LEN + 40  # 上限＋留痕標記

    # 未超長者一個字都不得動（截斷不能變成無條件加工）
    short = await evaluate_planner_case(
        _load_g01(), _plan_fn_raising(_planner_error_with_raw(_REJECTED_TWO_ACTION_JSON))
    )
    assert short.planner_raw_rejected == _REJECTED_TWO_ACTION_JSON


async def test_secret_straddling_the_truncation_point_is_still_redacted():
    """遮蔽必須在截斷**之前**：先截斷會把橫跨切點的 api key 剖成兩半，前半留在報告裡
    而完整值不再被字面比對命中（截掉尾巴的 key 仍是大部分的祕密材料）。

    mutation 證據：把 `_sanitize_rejected_raw` 改成「先截斷、再對 head 遮蔽」，
    本測試必轉紅（其餘遮蔽測試都抓不到這個順序錯誤——它們的內容都不超長）。
    ⚠️ 順序保護的是**憑證字面值**，不是 URL：`_URL_RE` 沒有結尾要求，被攔腰切斷的
    URL 照樣整段匹配得到。
    """
    api_key = "sk-" + "K" * 40
    # key 起點落在切點之前、終點在切點之後 → 先截斷就會只留下 key 的前 20 字元
    content = "填" * (PLANNER_RAW_REJECTED_MAX_LEN - 20) + api_key + "尾" * 100
    result = await evaluate_planner_case(
        _load_g01(), _plan_fn_raising(_planner_error_with_raw(content)), secrets=(api_key,)
    )

    raw = result.planner_raw_rejected
    assert raw is not None
    assert "[truncated from" in raw  # 確實走到截斷這條路（否則本測試是空跑）
    assert api_key not in raw
    assert api_key[:20] not in raw, "截斷把 key 剖半後前半殘留＝遮蔽順序錯了"
    assert "<redacted-secret>" in raw


async def test_degenerate_secrets_do_not_carpet_the_text():
    """反向守衛：空字串／過短的「憑證」不得被當成 secret 抹除。

    `"".replace("", x)` 會在**每個字元之間**插入標記，一兩個字元的值則會把正常文字
    打成馬賽克——遮蔽過當同樣摧毀本欄位的診斷價值。`MIN_REDACTABLE_SECRET_LEN`
    以下不處理是**刻意取捨**（真實 api key 遠長於此），不是漏看。
    """
    result = await evaluate_planner_case(
        _load_g01(),
        _plan_fn_raising(_planner_error_with_raw(_REJECTED_TWO_ACTION_JSON)),
        secrets=("", "ab"),
    )
    assert result.planner_raw_rejected == _REJECTED_TWO_ACTION_JSON
















def test_legit_model_tags_survive_sanitizing():
    """反向守衛：合法 tag 含 `:` `/` `.` `-`、也可能非 ASCII——一個字元都不得被動到。

    誤殺的後果是「報告說不出自己跑了哪顆模型」，正好摧毀 `model_served` 存在的目的
    （所以這裡刻意**不能**用字元白名單實作）。
    """
    for name in ("qwen2.5:14b-instruct-q4_K_M", "org/model.v2", "gpt-4o-2024-08-06", "模型-中文"):
        assert wi_ai_eval._sanitize_model_name(name) == name



# ── CLI：兩段並列輸出；退出碼守門（0/1/2）────────────────────────────────────


def _run_cli(
    *extra: str, out_dir: Path, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "wi_ai_eval.py"), "--out", str(out_dir), *extra],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _load_g01() -> dict:
    return json.loads((GOLD_DIR / "g01_acquire_dimm.json").read_text(encoding="utf-8"))


def _write_gold(gold_dir: Path, name: str, data: dict) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    (gold_dir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_cli_report_contains_both_segments(tmp_path: Path):
    proc = _run_cli(out_dir=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    latest = tmp_path / "wi-gold-latest.json"
    assert latest.exists()
    report = json.loads(latest.read_text(encoding="utf-8"))

    assert report["report_schema_version"] == "wi-gold-report-v10"
    assert report["unapproved_cases"] == []
    # 向後相容：頂層 summary/cases（compile 段）維持 v1 形狀
    assert report["summary"] == {"total": GOLD_TOTAL_N, "passed": GOLD_TOTAL_N, "failed": 0}
    assert len(report["cases"]) == GOLD_TOTAL_N
    assert report["gold_load_errors"] == []

    planner = report["planner_eval"]
    assert planner["db_required"] is False
    assert planner["summary"]["n"] == GOLD_TOTAL_N
    # v8：報告自帶 `planner_raw_rejected` 的值域說明——讀報告的人未必拿得到 repo，
    # 值域（null vs ""）、只留 retry 那次、遮蔽與截斷上限都必須寫在報告裡
    note = planner["raw_rejected_note"]
    assert "planner_raw_rejected" in note
    assert "null" in note and "retry" in note
    assert "<redacted-url>" in note and "<redacted-secret>" in note
    assert str(PLANNER_RAW_REJECTED_MAX_LEN) in note
    assert planner["summary"]["planner"] == RULE_PLANNER_NAME
    assert len(planner["cases"]) == GOLD_TOTAL_N
    # ie_modified=false 的轉正全數自我指涉排除；D3-022 重切 3 筆（true）計入
    # → 分數＝誠實的新基線（見 PLAN_ACCURACY/BOUNDARY_F1 注記）
    assert planner["summary"]["plan_metrics_n"] == PLAN_METRICS_N
    assert (
        planner["summary"]["self_referential_excluded"]["count"]
        == PROMOTED_GOLD_N - IE_MODIFIED_GOLD_N
    )
    assert planner["summary"]["action_count_accuracy"] == pytest.approx(PLAN_ACCURACY)
    assert planner["summary"]["boundary_span"]["micro"]["f1"] == pytest.approx(BOUNDARY_F1)
    # 缺口要寫在報告裡，不是靠人記得：dependency F1 未實作、rule 分數退化
    assert planner["summary"]["dependency_f1"] is None
    assert "未實作" in planner["summary"]["dependency_f1_note"]
    assert "退化" in planner["summary"]["degenerate_planner_note"]
    # v5：個案失敗隔離的觀測欄位必須恆在（rule planner 正常時應為 0 筆）
    assert planner["summary"]["planner_failures"]["count"] == 0
    assert planner["summary"]["planner_failures"]["error_codes"] == {}
    assert planner["summary"]["planner_latency_ms"]["total"] >= 0
    assert all(c["planner_failed"] is False for c in planner["cases"])
    # v6：sanitize 觀測區塊恆在；rule planner 不經 sanitize → 三個統計都空
    sanitize = planner["sanitize_reasons"]
    assert sanitize["by_code"] == {}
    assert sanitize["by_phase"] == {}
    assert sanitize["by_case"] == {}
    assert "evidence_offset_repaired" in sanitize["note"]

    # dataset_note 動態生成（不寫死「未達 50 筆」字串）；轉正後頭條句必須
    # 自帶「原樣核准不計 planner 段證據力」的但書（R4）。
    # D3-028 起 PROMOTED_GOLD_N ≥ 50 → 走「已達前置」分支（P0 的 50 筆門檻
    # 已跨過）；分支選擇由釘值決定，斷言跟著釘值走、不寫死其中一句。
    assert f"n={GOLD_TOTAL_N}" in report["dataset_note"]
    assert "seed" in report["dataset_note"]
    if PROMOTED_GOLD_N < 50:
        assert f"IE 核准 {PROMOTED_GOLD_N}/50，未達" in report["dataset_note"]
    else:
        assert f"IE 核准 {PROMOTED_GOLD_N} 筆，已達" in report["dataset_note"]
        assert "50 筆前置" in report["dataset_note"]
    assert "不計 planner 段證據力" in report["dataset_note"]

    assert "[planner]" in proc.stdout
    assert "[compile]" in proc.stdout


def test_cli_report_self_attests_rule_planner_run(tmp_path: Path):
    """T-1（rule 路徑）＋S-6：報告要能自己佐證「誰跑的、跑的是哪個 gold」。

    在 v7 之前，報告不記 model 也不記 prompt 版本，版本歸屬只能靠人工命名的
    檔名；`gold_dir` 則是含 OS 使用者名的本機絕對路徑。這裡同時釘住：
    ⑴ rule planner 的來源欄恆 null（它不碰 LLM）；⑵ **rule 路徑不因為要填這些
    欄位而變成需要任何外部設定**（ADR-037 前以清空 LLM 設定跑來證明；該設定已移除），
    必須 exit 0；⑶ gold_dir 是 repo 相對路徑。

    mutation 證據：把 `planner_run` 拿掉、或把 `_repo_relative()` 換回
    `str(args.gold_dir)`，本測試必轉紅。
    """
    out = tmp_path / "out"
    proc = _run_cli(out_dir=out)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    text = (out / "wi-gold-latest.json").read_text(encoding="utf-8")
    report = json.loads(text)

    run = report["planner_run"]
    assert run["planner"] == RULE_PLANNER_NAME
    assert run["model_requested"] is None
    assert run["model_served"] is None
    assert run["model_served_variants"] == []
    assert run["prompt_version"] is None
    assert run["llm_timeout_s"] is None
    assert "不碰 LLM" in run["note"]
    # 報告內的 planner 名稱兩處必須一致（summary 那個是 v6 起就有的）
    assert run["planner"] == report["planner_eval"]["summary"]["planner"]

    # S-6：相對於 ddm-v2/，且整份報告不得夾帶本機絕對路徑
    assert report["gold_dir"] == "tests/gold/wi_plans"
    assert not Path(report["gold_dir"]).is_absolute()
    assert "/home/" not in text

    # 終端機讀的那一份同樣看得到（不是只有 JSON 裡有）
    assert f"planner={RULE_PLANNER_NAME}" in proc.stdout
    assert "model_requested=n/a" in proc.stdout
    assert "gold_dir=tests/gold/wi_plans" in proc.stdout




def test_cli_fails_on_empty_gold_dir(tmp_path: Path):
    """n=0＝gold 輸入不可用 → exit 2（與「eval 跑完發現問題」的 1 區分）。"""
    empty = tmp_path / "gold"
    empty.mkdir()
    proc = _run_cli("--gold-dir", str(empty), out_dir=tmp_path / "out")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "n=0" in proc.stdout


def test_cli_all_planner_cases_failed_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """全案 planner 失敗＝管道壞掉（非量測結果）→ exit 1，且**不得 traceback**。

    ADR-037 移除 `--planner llm` 之前，這條以連不上的 LLM endpoint 製造全滅；現在改為
    in-process 把 rule planner 換成必拋例外的版本。mutation 證據：拆掉
    `planner_pipeline_broken` 判定會轉紅——那等於讓「planner 全程失敗」也回報 exit 0。
    同時證明逐案隔離生效（有報告、有逐案錯誤碼可看）。
    """
    gold = tmp_path / "gold"
    _write_gold(gold, "g01.json", _load_g01())
    out = tmp_path / "out"

    async def _always_fails(data: dict):  # noqa: ARG001
        raise ConnectionError("planner endpoint unreachable (selftest)")

    monkeypatch.setattr(wi_ai_eval, "rule_based_plan", _always_fails)
    monkeypatch.setattr(sys, "argv", ["wi_ai_eval.py", "--gold-dir", str(gold), "--out", str(out)])
    assert wi_ai_eval.main() == 1
    stdout = capsys.readouterr().out
    assert "管道壞掉" in stdout
    assert "[PLANNER-FAIL]" in stdout

    report = json.loads((out / "wi-gold-latest.json").read_text(encoding="utf-8"))
    failures = report["planner_eval"]["summary"]["planner_failures"]
    assert failures["count"] == 1
    assert failures["cases"] == ["g01_acquire_dimm"]
    assert sum(failures["error_codes"].values()) >= 1


def test_cli_gold_annotation_defect_exits_1(tmp_path: Path):
    """B11b：非法 offset 的 gold 必須 exit 1，不能滑過 CI。

    mutation 證據：把 `wi_ai_eval.py` 的 `planner_ok = all(r.ok ...)` 拆掉，
    本測試必轉紅（該 gold 的 compile 段照樣全過，只有 planner 段守門在擋）。
    """
    gold = tmp_path / "gold"
    data = _load_g01()
    data["plan"]["actions"][0]["evidence"][0]["end"] = 99  # 越界；compile 段不讀 offset
    _write_gold(gold, "g01_bad_offset.json", data)

    proc = _run_cli("--gold-dir", str(gold), out_dir=tmp_path / "out")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "gold_evidence_offset_out_of_range" in proc.stdout
    # 證明失敗確實來自 planner 段守門，不是 compile 段順帶擋下
    assert "[compile]  1/1 passed" in proc.stdout


def test_cli_compile_failure_exits_1(tmp_path: Path):
    """B11c：compile 段失敗必須 exit 1。

    mutation 證據：把 `wi_ai_eval.py` 回傳條件中的 `failed == 0` 拆掉，
    本測試必轉紅（planner 段對此 gold 完全 ok，只有 compile 段在擋）。
    """
    gold = tmp_path / "gold"
    data = _load_g01()
    data["expected_cycles"][0]["total_tmu"] = 999.0  # 與引擎實算不符 → compile 段 FAIL
    _write_gold(gold, "g01_wrong_tmu.json", data)

    proc = _run_cli("--gold-dir", str(gold), out_dir=tmp_path / "out")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[FAIL]" in proc.stdout
    # planner 段無 gold 標註錯誤：失敗只能來自 compile 段
    assert "GOLD-ERR" not in proc.stdout


def test_cli_invalid_gold_files_exit_2_and_still_report(tmp_path: Path):
    """malformed JSON／缺 plan → 具名 gold_case_invalid（點名檔案、進報告、exit 2），
    其餘有效案例仍被評測；不能是 unhandled traceback。"""
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "a_malformed.json").write_text("{not json", encoding="utf-8")
    (gold / "b_missing_plan.json").write_text(
        json.dumps({"id": "x", "source_text": "拿起DIMM"}), encoding="utf-8"
    )
    _write_gold(gold, "g01_ok.json", _load_g01())

    out = tmp_path / "out"
    proc = _run_cli("--gold-dir", str(gold), out_dir=out)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr
    assert "a_malformed.json" in proc.stdout
    assert "gold_case_invalid:malformed_json" in proc.stdout
    assert "b_missing_plan.json" in proc.stdout
    assert "gold_case_invalid:missing_plan" in proc.stdout

    report = json.loads((out / "wi-gold-latest.json").read_text(encoding="utf-8"))
    assert len(report["gold_load_errors"]) == 2
    # 有效案例仍被評測、進報告
    assert report["summary"]["total"] == 1
    assert report["planner_eval"]["summary"]["n"] == 1


def test_dataset_note_headline_carries_rubber_stamp_caveat():
    """R4：給主管看的「IE 核准 N 筆，已達 P0 前置」必須自帶但書——原樣核准的
    預標註（ie_modified≠true）不計 planner 段證據力。"""

    def _approved(i: int, *, ie_modified) -> tuple[Path, dict]:
        return (
            Path(f"g{i:02d}.json"),
            {
                "id": f"g{i:02d}",
                "approved_by": "IEC141289",
                "review_status": "approved",
                "plan_origin": "rule_based_v1_preannotation",
                "ie_modified": ie_modified,
            },
        )

    # 55 筆原樣核准 → 頭條句達標，但但書必須跟在同一句 note 裡
    cases = [_approved(i, ie_modified=False) for i in range(55)]
    note = _dataset_note(cases)
    assert "IE 核准 55 筆，已達" in note
    assert "ie_modified≠true 的預標註 55 筆" in note
    assert "不計 planner 段證據力" in note

    # IE 真的改過（ie_modified=true）→ 不掛但書
    cases_real = [_approved(i, ie_modified=True) for i in range(55)]
    note_real = _dataset_note(cases_real)
    assert "IE 核准 55 筆，已達" in note_real
    assert "不計 planner 段證據力" not in note_real


def test_seed_approval_pinned_to_whitelist():
    """R6：approved_by=seed 只認白名單 3 筆——非白名單 seed 不算核准，
    dataset_note 也要單獨點名（不得混進 seed 或 IE 核准數）。"""
    real_seed = {"id": "g01_acquire_dimm", "approved_by": "seed"}
    fake_seed = {"id": "d001_rubber", "approved_by": "seed"}
    assert _case_is_approved(real_seed) is True
    assert _case_is_approved(fake_seed) is False

    note = _dataset_note([(Path("a.json"), real_seed), (Path("b.json"), fake_seed)])
    assert "seed 1 筆" in note
    assert "approved_by=seed 但非白名單 1 筆（不計核准）" in note


def test_cli_fake_seed_demotes_report_to_draft(tmp_path: Path):
    """R6 CLI 面：gold_dir 混入非白名單 seed → 視同未核准，官方報告拒寫、
    降級 wi-draft-*（拆掉 _case_is_approved 的白名單判斷必轉紅）。"""
    gold = tmp_path / "gold"
    _write_gold(gold, "g01_ok.json", _load_g01())
    fake = _load_g01()
    fake["id"] = "d777_fake_seed"  # approved_by 維持 "seed"，但 id 不在白名單
    _write_gold(gold, "d777_fake_seed.json", fake)

    out = tmp_path / "out"
    proc = _run_cli("--gold-dir", str(gold), out_dir=out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (out / "wi-gold-latest.json").exists()
    report = json.loads((out / "wi-draft-latest.json").read_text(encoding="utf-8"))
    assert report["unapproved_cases"] == ["d777_fake_seed.json"]
    assert "非白名單" in report["dataset_note"]


def test_cli_unapproved_cases_demote_report_to_draft(tmp_path: Path):
    """P2-9：gold_dir 含未核准案例 → 拒寫 wi-gold-latest.json，改寫 wi-draft-latest.json
    （防覆核期間污染官方報告）。

    mutation 證據：把 `wi_ai_eval.py` 的 prefix 降級判斷拆掉，本測試必轉紅。
    """
    gold = tmp_path / "gold"
    _write_gold(gold, "g01_ok.json", _load_g01())
    pending = _load_g01()
    pending["id"] = "d999_pending"
    pending["approved_by"] = None
    pending["review_status"] = "pending_ie"
    _write_gold(gold, "d999_pending.json", pending)

    out = tmp_path / "out"
    proc = _run_cli("--gold-dir", str(gold), out_dir=out)
    # eval 本身照跑（覆核期間仍要能看報告）——只降級檔名，不改退出碼語意
    assert proc.returncode == 0, proc.stdout + proc.stderr

    assert not (out / "wi-gold-latest.json").exists(), "未核准案例混入時不得寫官方報告"
    assert not list(out.glob("wi-gold-*.json"))
    latest = out / "wi-draft-latest.json"
    assert latest.exists()
    report = json.loads(latest.read_text(encoding="utf-8"))
    assert report["unapproved_cases"] == ["d999_pending.json"]
    assert "wi-draft-latest.json" in proc.stdout


# ── v10：被剝除的值進報告（ADR-033 P1 觀察期補測）────────────────────────
#
# ⚠️ ADR-037 後沒有任何 planner 會產生 `stripped_values`（rule planner 不經 sanitize，
# 舊 LLM adapter 已移除），原本起 HTTP 伺服器逼這條路徑執行的端到端探針隨之移除。
# 下面保留的是 `sanitize_stripped_value`／`SanitizeLog` 的單元測試；外部 planner adapter
# 接上（實作計畫 S2）時，要補回一條「真的經 sanitize 再進報告」的端到端探針。






def test_stripped_value_over_the_cap_is_truncated_with_a_trace():
    """超長的被剝值要截斷並**留痕**——截過卻裝成完整值會讓事後判讀得出錯的結論。

    上限（200）遠小於被拒回應的 4000，因為存的東西不同：這裡是單一 role 的片語
    （gold 全 55 案最長 6 個字）。留 200 是給改寫／幻覺空間，不是給一整份回應。
    """
    from ddm_v2.nlp.planner_eval import STRIPPED_VALUE_MAX_LEN, sanitize_stripped_value

    long_value = "字" * (STRIPPED_VALUE_MAX_LEN + 50)
    out = sanitize_stripped_value(long_value, ())
    assert out.startswith("字" * STRIPPED_VALUE_MAX_LEN)
    assert out.endswith(f"…[truncated from {STRIPPED_VALUE_MAX_LEN + 50} chars]")

    short = "記憶體模組"
    assert sanitize_stripped_value(short, ()) == short, "正常長度不得被動到"


def test_stripped_value_redacts_before_truncating():
    """順序不可對調：先截斷會把橫跨切點的憑證剖成兩半、前半留在報告裡。"""
    from ddm_v2.nlp.planner_eval import STRIPPED_VALUE_MAX_LEN, sanitize_stripped_value

    secret = "sk-" + "z" * 40
    # 讓憑證正好橫跨截斷點
    value = "字" * (STRIPPED_VALUE_MAX_LEN - 10) + secret
    out = sanitize_stripped_value(value, (secret,))
    assert secret not in out
    assert secret[:20] not in out, "憑證前半段留在報告裡＝大部分的祕密材料還在"
    # 標記本身可能被上限切斷（此例只剩 `<redacted-`）——那是**顯示**的小瑕疵，
    # 不是洩漏：憑證在截斷之前就已經被換掉了。記在這裡免得日後被當成 bug 修錯方向。
    assert "<redacted-" in out
    assert "[truncated from" in out


# ── 資安複審 2026-08-23：本批新開的路自己漏掉的兩個欄位 ────────────────────


def test_role_key_goes_through_redaction_and_truncation():
    """`role_key` **也是模型可控的**，不得繞過遮蔽與截斷。

    會漏是因為直覺把它當「欄位名」——但 `role_key_dropped` 那一類的鍵**依定義是
    模型自創的**（不在 `ROLE_KEYS` 內，正因如此才被剝掉），封閉集合的保證在這一類
    上剛好不成立。資安席實測：同一份 payload，走 `text` 的被遮成 228 字，走
    `role_key` 的 5046 字、含密碼、未截斷地寫進要 commit 的 JSON。

    mutation：把 `_stripped_to_dict` 的 `role_key` 改回 `detail.role_key` → 本測轉紅。
    """
    from ddm_v2.nlp.contracts import StripDetail
    from ddm_v2.nlp.planner_eval import STRIPPED_VALUE_MAX_LEN

    secret = "hunter2-" + "x" * 30
    # URL 與長填充之間留空白：`_URL_RE` 在空白處停住，否則 5000 個 A 會被整段吞進
    # `<redacted-url>`，測不到截斷那一層（第一版就踩到這個，留言免得再踩）
    hostile_key = f"object_ref_{secret} http://internal.host/admin " + "A" * 5000
    row = wi_ai_eval._stripped_to_dict(
        "initial",
        StripDetail(
            action_id="a1", reason="role_key_dropped", role_key=hostile_key, text="治具"
        ),
        (secret,),
    )
    assert secret not in row["role_key"]
    assert "<redacted-secret>" in row["role_key"]
    assert "<redacted-url>" in row["role_key"]
    assert len(row["role_key"]) < STRIPPED_VALUE_MAX_LEN + 60, "未截斷"
    assert "[truncated from" in row["role_key"]


def test_our_own_fields_are_not_mangled_by_redaction():
    """反向控制：我方產生的欄位不得被遮蔽改寫（遮過當＝報告失去診斷價值）。"""
    from ddm_v2.nlp.contracts import StripDetail

    row = wi_ai_eval._stripped_to_dict(
        "initial",
        StripDetail(
            action_id="a1",
            reason="role_numeric_stripped",
            role_key="distance",
            value=450,
            unit="cm",
        ),
        ("some-secret-value",),
    )
    assert (row["phase"], row["action_id"], row["reason"]) == (
        "initial",
        "a1",
        "role_numeric_stripped",
    )
    assert (row["role_key"], row["value"], row["unit"]) == ("distance", 450, "cm")


def test_non_finite_value_fails_loud_instead_of_writing_invalid_json():
    """`value=NaN` 不得產生**非法 JSON**（RFC 8259 不允許裸 `NaN`）。

    `RoleValue.value` 進 `StripDetail` 的時間點**早於** D1 的剝除（那正是這個欄位的
    用途），所以剝除擋不到它。後果不是洩漏而是**版控檔壞掉**：用標準 parser 讀的
    下游工具會炸，而且是 commit 之後才發現。寫檔那一刻 fail-loud 才對——這裡炸掉
    是一次跑壞，寫出去是版控裡一份讀不了的證據。

    ⚠️ 這條驗的是**寫檔那一刻的旗標**（`allow_nan=False`），所以它保護的是報告的
    **所有**數值欄位，不只 `stripped_values.value`。

    mutation：拿掉 `json.dumps(...)` 的 `allow_nan=False` → 本測轉紅（改為產出
    含裸 `NaN` 的字串，而 `json.loads` 在 `parse_constant` 下會拒收）。
    """
    from ddm_v2.nlp.contracts import StripDetail

    log = wi_ai_eval.SanitizeLog()
    log.bind("g01")
    log.observe(
        "initial",
        ["role_numeric_stripped:a1:distance"],
        [
            StripDetail(
                action_id="a1",
                reason="role_numeric_stripped",
                role_key="distance",
                value=float("nan"),
            )
        ],
    )
    report = {"planner_eval": {"sanitize_reasons": log.to_dict(())}}

    # 預設（allow_nan=True）產出的是**非法 JSON**：嚴格 parser 拒收
    lenient = json.dumps(report, ensure_ascii=False)
    assert "NaN" in lenient
    with pytest.raises(ValueError):
        json.loads(lenient, parse_constant=_reject_json_constant)

    # 我們寫檔用的旗標：在寫出去之前就炸
    with pytest.raises(ValueError):
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)


def _reject_json_constant(name: str):
    """RFC 8259 沒有 NaN／Infinity；嚴格 parser 會在這裡拒收。"""
    raise ValueError(f"invalid JSON constant: {name}")


def test_report_writer_refuses_to_write_non_finite_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """**行為**測試：報告裡出現 NaN 時，`main()` 在寫檔前就炸，不產出非法 JSON。

    走真正的寫檔路徑（在行程內跑 `main()`），把 NaN 從 `sanitize_reasons` 注入進去
    ——那是真實入口：`RoleValue.value` 進 `StripDetail` 的時間點早於 D1 的剝除。

    ⚠️ 為什麼不用 `inspect.getsource(main)` 抓字串：第一版就是那樣寫的，而它**抓不到
    mutation**——`allow_nan=False` 這幾個字也出現在同一段的**註解**裡，把呼叫上的旗標
    拿掉之後斷言照樣通過。字串比對不分程式碼與註解，是假的守衛。

    mutation：拿掉寫檔那行的 `allow_nan=False` → 本測轉紅（會寫出含裸 `NaN` 的檔）。
    """
    gold = tmp_path / "gold"
    _write_gold(gold, "g01.json", _load_g01())
    out = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv", ["wi_ai_eval.py", "--gold-dir", str(gold), "--out", str(out)]
    )

    original = wi_ai_eval.SanitizeLog.to_dict

    def _with_nan(self, secrets=()):
        payload = original(self, secrets)
        payload["stripped_values"] = {
            "g01_acquire_dimm": [
                {"phase": "initial", "reason": "role_numeric_stripped", "value": float("nan")}
            ]
        }
        return payload

    monkeypatch.setattr(wi_ai_eval.SanitizeLog, "to_dict", _with_nan)
    with pytest.raises(ValueError):
        wi_ai_eval.main()
    assert not list(out.glob("*.json")), "炸掉之前不得已經寫出壞檔"


def test_report_writer_still_writes_normal_reports(tmp_path: Path):
    """反向控制：旗標不得誤傷合法數值——正常報告照樣寫得出來，且是**合法 JSON**
    （用拒收 NaN／Infinity 的嚴格 parser 讀一次）。"""
    proc = _run_cli(out_dir=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = (tmp_path / "wi-gold-latest.json").read_text(encoding="utf-8")
    json.loads(text, parse_constant=_reject_json_constant)
