#!/usr/bin/env python3
"""一鍵跑 MOST 兩個核心邏輯驗證器並彙總（供 harness skill 呼叫）。

exit 0 = 全部通過；非 0 = 有失敗或執行錯誤。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"  # ddm-v2/src（供 engine 測試 import ddm_v2）
VALIDATORS = [
    ("MiniMOST Sequence Model (standalone spec)", HERE / "minimost_sequence_validator.py"),
    ("Level System (standalone spec)", HERE / "level_system_validator.py"),
    ("most_engine golden (讀 DB 資料引擎)", HERE / "engine_golden_test.py"),
]


def main() -> int:
    overall = 0
    summary: list[tuple[str, str]] = []
    env = {**os.environ, "PYTHONPATH": str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    for name, path in VALIDATORS:
        print(f"\n{'#' * 60}\n# {name}  ({path.name})\n{'#' * 60}")
        proc = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, env=env)
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        result_line = next((ln for ln in proc.stdout.splitlines() if "passed" in ln), "(無結果列)")
        status = "PASS" if proc.returncode == 0 else "FAIL"
        summary.append((f"{name}: {status}", result_line.strip()))
        overall |= proc.returncode

    print(f"\n{'=' * 60}\n總彙總\n{'=' * 60}")
    for status, line in summary:
        print(f"  {status}  —  {line}")
    print(f"\n整體：{'✅ 全部通過' if overall == 0 else '❌ 有失敗'}")
    return 0 if overall == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
