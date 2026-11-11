#!/usr/bin/env python3
"""lb_projection_check.py — 跨 repo 冒煙檢查：把投影層產出的 task CSV 餵給 LB 端真程式。

驗證 LB 端能吃我們的 CSV：reader → validate_quantity_contract(MULTI_LINE) → GroupValidator →
is_general_candidate → merge 候選偵測。印 groups／atomic／general／merge 候選（以 task_id 列出）。

用法：
    lb_projection_check.py --csv <path> [--lb-repo /home/howard/workspace/line-balance_stream-weaver_v2]

- 以 `<lb-repo>/test/.venv/bin/python`（reader/validator）與 `middle-earth-pkg/.venv`（merge）跑內嵌腳本，PYTHONPATH=src。
- reader 讀 CSV 時會在檔案旁建 backup/ → 先複製 CSV 到暫存目錄再讀。
- detect_merge_candidates 回傳型別可能是 list 或 MergeDetection → 用 getattr(result,"candidate_groups",result) 兩者都接。
- LB repo 不存在 → 印 SKIP、exit 0（CI 不強制，跨 repo）。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_LB_REPO = "/home/howard/workspace/line-balance_stream-weaver_v2"

# reader + 契約/群組/general 驗證（在 <lb>/test/.venv、PYTHONPATH=<lb>/src 執行）
_READER_SCRIPT = r'''
import sys
csv_path = sys.argv[1]
from optimization.io.reader import read_problem_from_csv
from optimization.features.quantity.policy import validate_quantity_contract
from optimization.features.grouping.group_validator import GroupValidator
from optimization.features.general_task.processor import is_general_candidate

problem = read_problem_from_csv(csv_path)
tasks = problem.tasks
group_map = problem.group_map
atomic_map = problem.atomic_group_map

validate_quantity_contract(tasks, group_map, mode="MULTI_LINE")
GroupValidator().validate(group_map, tasks)
GroupValidator().validate_atomic_groups(atomic_map, group_map, tasks)

generals = sorted(tid for tid, t in tasks.items() if is_general_candidate(t))

print("READER_OK")
print("GROUPS", {int(k): sorted(v) for k, v in group_map.items()})
print("ATOMIC", {int(k): sorted(v) for k, v in atomic_map.items()})
print("GENERAL", generals)
'''

# merge 候選偵測（在 middle-earth-pkg/.venv、PYTHONPATH=<lb>/middle-earth-pkg/src 執行）
_MERGE_SCRIPT = r'''
import sys, csv
csv_path = sys.argv[1]
from multi_line_solver.domain.models import Task, TaskComplexity, ToolAction
from multi_line_solver.solver.merge_candidate_detector import detect_merge_candidates

rows = list(csv.DictReader(open(csv_path)))
id_to_idx = {int(r["task_id"]): i for i, r in enumerate(rows)}

def _tool_action(v):
    if not v:
        return None
    return ToolAction(v.strip().lower())

tasks = []
for r in rows:
    preds = [id_to_idx[int(p)] for p in r["predecessors"].split(",") if p.strip()]
    tasks.append(Task(
        id=int(r["task_id"]),
        duration=int(r["duration"]),
        predecessors=sorted(preds),
        offline_flag=int(r["offline_flag"] or 0),
        adjustable=int(r["adjustable"] or 0),
        action_type=r["action_type"] or "",
        complexity_level=TaskComplexity.EASY,
        part_id=r["part_id"] or "",
        tool_id=(r["tool_id"] or None),
        tool_action=_tool_action(r["tool_action"]),
        atomic_group=(int(r["atomic_group"]) if r["atomic_group"] else None),
        quantity=int(r["quantity"] or 1),
    ))

result = detect_merge_candidates(tasks=tasks, ratio=0.5)
groups = getattr(result, "candidate_groups", result)  # list 或 MergeDetection 皆接
# 以 task_id 列出每組
out = []
by_idx = {i: t.id for i, t in enumerate(tasks)}
for g in groups:
    ids = getattr(g, "task_ids", None) or getattr(g, "member_ids", None) or list(g)
    norm = sorted(by_idx.get(x, x) for x in ids)
    out.append(norm)
print("MERGE_GROUPS", out)
'''


def _run(venv_python: Path, src: Path, script: str, csv_path: str) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    return subprocess.run(
        [str(venv_python), "-c", script, csv_path],
        capture_output=True, text=True, env=env,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--lb-repo", default=DEFAULT_LB_REPO)
    args = ap.parse_args()

    lb = Path(args.lb_repo)
    if not lb.is_dir():
        print(f"SKIP: LB repo not found at {lb}")
        return 0

    test_py = lb / "test" / ".venv" / "bin" / "python"
    lb_src = lb / "src"
    mep_py = lb / "middle-earth-pkg" / ".venv" / "bin" / "python"
    mep_src = lb / "middle-earth-pkg" / "src"
    if not test_py.exists():
        print(f"SKIP: LB test venv not found at {test_py}")
        return 0

    # reader 會在檔案旁建 backup/ → 複製到暫存目錄再讀
    with tempfile.TemporaryDirectory() as td:
        tmp_csv = Path(td) / "tasks.csv"
        shutil.copyfile(args.csv, tmp_csv)

        rc = _run(test_py, lb_src, _READER_SCRIPT, str(tmp_csv))
        print(rc.stdout.strip())
        if rc.returncode != 0:
            print("READER/VALIDATOR FAILED:", file=sys.stderr)
            print(rc.stderr.strip(), file=sys.stderr)
            return 1

        if mep_py.exists():
            rm = _run(mep_py, mep_src, _MERGE_SCRIPT, str(tmp_csv))
            print(rm.stdout.strip())
            if rm.returncode != 0:
                print("MERGE DETECTION FAILED (non-fatal, LB WP-L2 in flux):", file=sys.stderr)
                print(rm.stderr.strip(), file=sys.stderr)
        else:
            print("MERGE_SKIP: middle-earth-pkg venv not found")

    print("LB_PROJECTION_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
