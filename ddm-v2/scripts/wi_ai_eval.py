#!/usr/bin/env python3
"""WI AI gold-plan eval CLI（L3-3 骨架）。

用法（於 ddm-v2/）：
  PYTHONPATH=src python scripts/wi_ai_eval.py
  PYTHONPATH=src python scripts/wi_ai_eval.py --gold-dir tests/gold/wi_plans --out docs/llm/eval-reports

退出碼：有任一例失敗 → 1；全部通過 → 0。
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

from ddm_v2.nlp.gold_eval import GOLD_SCHEMA_VERSION, evaluate_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate WI AI gold plans")
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
    args = parser.parse_args()

    results = asyncio.run(evaluate_all(args.gold_dir))
    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")

    report = {
        "report_kind": "wi-gold-eval",
        "gold_schema_version": GOLD_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "gold_dir": str(args.gold_dir),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
        },
        "cases": [r.to_dict() for r in results],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / f"wi-gold-{stamp}.json"
    latest = args.out / "wi-gold-latest.json"
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    out_path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")

    print(f"gold eval: {passed}/{len(results)} passed → {out_path}")
    for r in results:
        mark = "OK" if r.ok else "FAIL"
        print(f"  [{mark}] {r.case_id}  routing={r.routing_status}  actions={r.action_count}")
        if not r.ok:
            for e in r.errors[:8]:
                print(f"       - {e}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
