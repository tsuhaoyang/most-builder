"""Planner 段評測（text → plan）單元測試。

涵蓋：指標數學（exact counts，防「恆報 1.0」）、gold 標註缺損偵測（含缺欄位
的具名錯誤，不 traceback）、兩邊皆無 span 不給分（防獎勵棄權）、
normalized_text 不可比的誠實計分、seed gold 基線釘值、CLI 報告兩段皆在
（防 planner 段被靜默跳過）、CLI 退出碼守門（壞 gold → 1、compile 失敗 → 1、
gold 輸入不可用 → 2——這三條是 mutation 證據：把 `wi_ai_eval.py` 的
`all(r.ok)` 或 `failed == 0` 拆掉必轉紅）。
"""
from __future__ import annotations

import json
import os
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
    rule_based_plan,
    summarize_planner_results,
)

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "tests" / "gold" / "wi_plans"

# 目前 seed gold 集的筆數：**唯一出處**（基線釘值與 CLI 報告測試共用；
# 新增 gold case 時只改這裡與對應的分數釘值）。
SEED_GOLD_N = 3


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
    assert len(cases) == SEED_GOLD_N


# ── seed gold 基線（全 seed；rule_based planner 的實際分數釘值） ─────────────


async def test_seed_gold_baseline_pinned():
    """基線釘值：planner 改進時同步更新（如同黃金值）。

    也同時殺掉兩類 mutation：accuracy 恆 1.0（數值不符）與 planner 段恆空
    （n≠SEED_GOLD_N）。
    """
    results, summary = await evaluate_planner_all(GOLD_DIR)
    assert summary["planner"] == RULE_PLANNER_NAME
    assert summary["n"] == SEED_GOLD_N
    assert all(r.ok for r in results), [r.errors for r in results]

    # rule_based_v1 永遠單 action：g01/g05 數對、g02（2 actions）數錯
    assert summary["action_count_accuracy"] == pytest.approx(2 / 3)
    micro = summary["boundary_span"]["micro"]
    assert (micro["tp"], micro["fp"], micro["fn"]) == (2, 1, 2)
    assert micro["f1"] == pytest.approx(4 / 7)
    assert summary["boundary_span"]["annotated_cases"] == SEED_GOLD_N
    assert summary["boundary_span"]["scored_cases"] == SEED_GOLD_N
    assert summary["boundary_span"]["unannotated_cases"] == []
    assert summary["boundary_span"]["trivially_empty_cases"] == []

    by_id = {r.case_id: r for r in results}
    assert by_id["g01_acquire_dimm"].boundary_span_f1 == 1.0
    assert by_id["g02_screwdriver_screw_x2"].boundary_span_f1 == 0.0
    assert by_id["g05_composite_unknown"].boundary_span_f1 == 1.0
    assert by_id["g02_screwdriver_screw_x2"].action_count_match is False

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

    assert report["report_schema_version"] == "wi-gold-report-v3"
    # 向後相容：頂層 summary/cases（compile 段）維持 v1 形狀
    assert report["summary"] == {"total": SEED_GOLD_N, "passed": SEED_GOLD_N, "failed": 0}
    assert len(report["cases"]) == SEED_GOLD_N
    assert report["gold_load_errors"] == []

    planner = report["planner_eval"]
    assert planner["db_required"] is False
    assert planner["summary"]["n"] == SEED_GOLD_N
    assert planner["summary"]["planner"] == RULE_PLANNER_NAME
    assert len(planner["cases"]) == SEED_GOLD_N
    assert planner["summary"]["action_count_accuracy"] == pytest.approx(2 / 3)
    assert planner["summary"]["boundary_span"]["micro"]["f1"] == pytest.approx(4 / 7)
    # 缺口要寫在報告裡，不是靠人記得：dependency F1 未實作、rule 分數退化
    assert planner["summary"]["dependency_f1"] is None
    assert "未實作" in planner["summary"]["dependency_f1_note"]
    assert "退化" in planner["summary"]["degenerate_planner_note"]

    # dataset_note 動態生成（不寫死「未達 50 筆」字串）
    assert f"n={SEED_GOLD_N}" in report["dataset_note"]
    assert "seed" in report["dataset_note"]
    assert "0/50" in report["dataset_note"]

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
