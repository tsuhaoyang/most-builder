"""Planner 段評測（text → plan）單元測試。

涵蓋：指標數學（exact counts，防「恆報 1.0」）、gold 標註缺損偵測（含缺欄位
的具名錯誤，不 traceback）、兩邊皆無 span 不給分（防獎勵棄權）、
normalized_text 不可比的誠實計分、**自我指涉排除**（plan_origin=planner 預標註
且 ie_modified≠true 者不得計入 Plan 層指標——含橡皮圖章回歸：把草稿只改身分
欄位轉正，指標不得動；把 summarize 的排除邏輯拆掉，這兩條必轉紅）、
seed gold 基線釘值、CLI 報告兩段皆在（防 planner 段被靜默跳過）、CLI 退出碼
守門（壞 gold → 1、compile 失敗 → 1、gold 輸入不可用 → 2——這三條是 mutation
證據：把 `wi_ai_eval.py` 的 `all(r.ok)` 或 `failed == 0` 拆掉必轉紅）、
未核准案例混入 gold_dir 時報告降級 wi-draft-*（拆掉 prefix 判斷必轉紅）。
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
    RULE_PLANNER_NAME,
    evaluate_planner_all,
    evaluate_planner_case,
    load_gold_cases_checked,
    planner_preannotation_origin,
    rule_based_plan,
    summarize_planner_results,
)

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

# D3-022 後的 Plan 層基線（seed 3 筆＋ie_modified=true 轉正 3 筆＝分母 6）：
# accuracy＝2/6（g01/g05 對；g02 與重切 3 筆 rule planner 恆單 action 必錯）；
# boundary micro＝tp2 fp4 fn9 → F1 4/17。分數自 seed 基線 2/3、4/7 下降是
# **預期且誠實**（真 ground truth 進了分母），不是迴歸。
PLAN_METRICS_N = SEED_GOLD_N + IE_MODIFIED_GOLD_N
PLAN_ACCURACY = 2 / 6
BOUNDARY_MICRO = (2, 4, 9)  # (tp, fp, fn)
BOUNDARY_F1 = 4 / 17
# ie_modified=true 的轉正 gold（計入 Plan 層指標；錯誤排除即紅）
IE_MODIFIED_GOLD_IDS = {
    "g30_pick_dummy_dimm_debag",
    "g31_confirm_points_press_handle",
    "g32_pick_board_debag_place_bench",
}

# wi_ai_eval 的核准判定與 dataset_note（R4/R6 守門直接打函式，不繞 CLI）
sys.path.insert(0, str(ROOT / "scripts"))
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

    D3-019/D3-021 轉正的 25 筆全部 `ie_modified: false`（原樣核准）→ 排除出
    Plan 層指標；**D3-022 重切轉正的 3 筆 `ie_modified: true`（IE 改過 plan＝
    真實 ground truth）→ 計入**。分母 3→6、分數自 seed 基線 2/3、4/7 降為
    2/6、4/17 是**預期且誠實**（rule planner 恆單 action，對多 action gold
    必然拿 0）——ie_modified=true 案例被錯誤排除（plan_metrics_n 回落、分數
    回跳基線）即紅。
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
    # D3-022 重切 gold 逐筆：計入分母、rule planner 必然拿 0（誠實的預期分數）
    for gid in sorted(IE_MODIFIED_GOLD_IDS):
        r = by_id[gid]
        assert r.ie_modified is True, f"{gid}：ie_modified 宣告遺失（會被錯誤排除）"
        assert r.action_count_match is False, f"{gid}：rule planner 恆單 action"
        assert r.boundary_span_f1 == 0.0, f"{gid}：整句 span 對重切 gold 必為 0"

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


# ── CLI：兩段並列輸出；退出碼守門（0/1/2）────────────────────────────────────


def _run_cli(*extra: str, out_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
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

    assert report["report_schema_version"] == "wi-gold-report-v4"
    assert report["unapproved_cases"] == []
    # 向後相容：頂層 summary/cases（compile 段）維持 v1 形狀
    assert report["summary"] == {"total": GOLD_TOTAL_N, "passed": GOLD_TOTAL_N, "failed": 0}
    assert len(report["cases"]) == GOLD_TOTAL_N
    assert report["gold_load_errors"] == []

    planner = report["planner_eval"]
    assert planner["db_required"] is False
    assert planner["summary"]["n"] == GOLD_TOTAL_N
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

    # dataset_note 動態生成（不寫死「未達 50 筆」字串）；轉正後頭條句必須
    # 自帶「原樣核准不計 planner 段證據力」的但書（R4）
    assert f"n={GOLD_TOTAL_N}" in report["dataset_note"]
    assert "seed" in report["dataset_note"]
    assert f"IE 核准 {PROMOTED_GOLD_N}/50" in report["dataset_note"]
    assert "不計 planner 段證據力" in report["dataset_note"]

    assert "[planner]" in proc.stdout
    assert "[compile]" in proc.stdout


def test_cli_fails_on_empty_gold_dir(tmp_path: Path):
    """n=0＝gold 輸入不可用 → exit 2（與「eval 跑完發現問題」的 1 區分）。"""
    empty = tmp_path / "gold"
    empty.mkdir()
    proc = _run_cli("--gold-dir", str(empty), out_dir=tmp_path / "out")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "n=0" in proc.stdout


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
