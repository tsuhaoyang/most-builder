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
