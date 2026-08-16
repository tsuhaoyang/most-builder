"""`gold_harvest.py --recompile` 的正式 gold 守衛（P1-4；不需 DB）。

守什麼：已核准 gold 的 expected_* 是鎖點——「引擎改壞 → gold 紅 → --recompile
→ 綠」不准零摩擦（No error bypass）。落在 wi_plans/ 的路徑預設拒絕；顯式
`--relock-approved --reason "..."` 才放行，且 reason 寫進檔案 notes 留痕。

mutation 證據（CI_GATES 規則 7）：把 `assert_recompile_targets_safe` 的守衛
拆掉（或 `cmd_recompile` 不再呼叫它）→ `test_recompile_refuses_formal_gold_dir`
必轉紅；把 notes 留痕拆掉 → `test_relock_with_reason_writes_notes` 必轉紅。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _seed_gold_baseline import G01_TOTAL_TMU

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gold_harvest.py"
GOLD_DIR = ROOT / "tests" / "gold" / "wi_plans"


def _run(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    env.pop("DATABASE_URL", None)  # recompile 不碰 DB——連得上也不准用
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _copy_g01_into(dir_: Path) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    src = GOLD_DIR / "g01_acquire_dimm.json"
    dst = dir_ / src.name
    dst.write_bytes(src.read_bytes())
    return dst


def test_recompile_refuses_formal_gold_dir(tmp_path: Path):
    """wi_plans/ 底下的檔案：預設拒絕、檔案一個 byte 都不准動。"""
    target = _copy_g01_into(tmp_path / "wi_plans")
    before = target.read_bytes()

    proc = _run("--recompile", str(target))
    assert proc.returncode != 0
    assert "拒絕 recompile 正式 gold" in (proc.stdout + proc.stderr)
    assert target.read_bytes() == before, "拒絕之後不得留下任何改寫"


def test_recompile_refuses_batch_containing_gold_before_touching_anything(tmp_path: Path):
    """整批先驗再動手：批次裡混一個 gold 路徑 → 全部拒絕，草稿也不得被半改。"""
    draft = _copy_g01_into(tmp_path / "drafts")
    gold = _copy_g01_into(tmp_path / "wi_plans")
    draft_before, gold_before = draft.read_bytes(), gold.read_bytes()

    proc = _run("--recompile", str(draft), str(gold))
    assert proc.returncode != 0
    assert draft.read_bytes() == draft_before
    assert gold.read_bytes() == gold_before


def test_relock_requires_reason(tmp_path: Path):
    target = _copy_g01_into(tmp_path / "wi_plans")
    before = target.read_bytes()
    proc = _run("--recompile", str(target), "--relock-approved")
    assert proc.returncode != 0
    assert "--reason" in (proc.stdout + proc.stderr)
    assert target.read_bytes() == before


def test_relock_with_reason_writes_notes(tmp_path: Path):
    """顯式核可 → 放行，且 reason 寫進檔案 notes（留痕，不是無聲改寫）。"""
    target = _copy_g01_into(tmp_path / "wi_plans")
    reason = "rule-set v2→v3 版本重鎖（測試）"
    proc = _run("--recompile", str(target), "--relock-approved", "--reason", reason)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    data = json.loads(target.read_text(encoding="utf-8"))
    assert f"relock_approved: {reason}" in (data.get("notes") or "")
    # g01 是綠的 gold：重算後 expected 應維持一致（引擎沒變，重鎖不改值）。
    # 釘值唯一出處＝tests/unit/_seed_gold_baseline.py（與 test_planner_eval 共用）
    assert data["expected_cycles"][0]["complete"] is True
    assert data["expected_cycles"][0]["total_tmu"] == G01_TOTAL_TMU


def test_recompile_draft_dir_needs_no_flags(tmp_path: Path):
    """非 gold 目錄（草稿工作流）不受守衛影響——守衛只鎖 wi_plans/。"""
    draft = _copy_g01_into(tmp_path / "drafts")
    proc = _run("--recompile", str(draft))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(draft.read_text(encoding="utf-8"))
    assert "relock_approved" not in (data.get("notes") or ""), "非 gold 路徑不寫 relock 留痕"


def test_recompile_syncs_acquire_without_place_flag(tmp_path: Path):
    """D3-014 裁決 2：`acquire_without_place` 是 plan 的函數——IE 改完 plan 跑
    --recompile 時同步（補了「放」旗標摘掉、改出「取而無放」旗標掛上），
    不留過時 WARN 誤導覆核。mutation：把 cmd_recompile 的同步段拆掉 → 本測試紅。"""
    draft = _copy_g01_into(tmp_path / "drafts")
    data = json.loads(draft.read_text(encoding="utf-8"))
    assert data["plan"]["actions"][0]["action_type"] == "acquire", "前提：g01 是 acquire-only"
    data["preannotation_caveat"] = []  # 模擬草稿欄位存在但旗標缺漏
    draft.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    proc = _run("--recompile", str(draft))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(draft.read_text(encoding="utf-8"))
    assert "acquire_without_place" in data["preannotation_caveat"], (
        "acquire 無下游收尾——recompile 必須掛上旗標"
    )

    # IE 補上 move_place 收尾 → 再 recompile → 旗標摘掉
    a1 = data["plan"]["actions"][0]
    data["plan"]["actions"].append({
        "action_id": "a2",
        "action_type": "move_place",
        "sequence_order": 2,
        "roles": {},
        "evidence": list(a1["evidence"]),
        "notes": None,
    })
    draft.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proc = _run("--recompile", str(draft))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(draft.read_text(encoding="utf-8"))
    assert "acquire_without_place" not in data["preannotation_caveat"], (
        "已有 move_place 收尾——旗標必須摘掉"
    )


def test_recompile_does_not_invent_caveat_key(tmp_path: Path):
    """檔案本無 `preannotation_caveat`（如正式 gold 形狀）→ recompile 不憑空加 key
    （lint 同步只作用於草稿工作流的旗標清單）。"""
    draft = _copy_g01_into(tmp_path / "drafts")
    assert "preannotation_caveat" not in json.loads(draft.read_text(encoding="utf-8"))
    proc = _run("--recompile", str(draft))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "preannotation_caveat" not in json.loads(draft.read_text(encoding="utf-8"))
