"""匯出「IE 手填、v3 匯入」的 MOST sequence（motion_modules.category='action', keywords 含 v3-import）為 CSV。

資料來源：make v3-migrate 匯入的 v3 IE 手填資料（published_by=IEC141289）。
TMU 一律由單一權威引擎（most_engine.compute_cycle）就地重算，與落庫值對帳；漂移即標記。
用法：
    PYTHONPATH=src DATABASE_URL=... python scripts/export_ie_v3_sequences.py [out.csv]
"""
from __future__ import annotations

import asyncio
import csv
import sys

from sqlalchemy import select

from ddm_v2.database import get_session_maker
from ddm_v2.models.v2.motion_module import MotionModule, MotionModuleVersion
from ddm_v2.most_engine import compute_cycle, load_rule_set_from_db
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine

TOL = 0.0015


async def main(out_path: str) -> None:
    sessionmaker = get_session_maker()
    rows_out: list[dict] = []
    async with sessionmaker() as session:
        result = await session.execute(
            select(MotionModule, MotionModuleVersion)
            .join(MotionModuleVersion, MotionModuleVersion.module_id == MotionModule.id)
            .where(
                MotionModule.category == "action",
                MotionModule.keywords.contains(["v3-import"]),
                MotionModuleVersion.version_no == MotionModule.current_version,
            )
            .order_by(MotionModule.name_zh)
        )
        pairs = result.all()

        n = 0
        rs_cache: dict[str, object] = {}
        for mod, ver in pairs:
            for ri, row in enumerate(ver.rows):
                n += 1
                cycle_json = row["cycle"]
                cycle = CycleIn.model_validate(cycle_json)
                code = cycle.rule_set_code
                if code not in rs_cache:
                    rs = await load_rule_set_from_db(session, code)
                    rs.validate_complete()
                    rs_cache[code] = rs
                res = compute_cycle(cycle_in_to_engine(cycle), rs_cache[code])

                stored_tmu = float(ver.total_tmu)
                drift = "" if abs(res.total_tmu - stored_tmu) <= TOL else f"DRIFT(stored={stored_tmu})"

                rows_out.append(
                    {
                        "no": n,
                        "module_name_zh": mod.name_zh,
                        "row_index": ri,
                        "hand": row.get("hand", ""),
                        "seq_kind": cycle.seq,
                        "narrative_zh": row.get("narrative_zh") or mod.name_zh,
                        "rule_set_code": code,
                        "tech_line": res.tech_line,
                        "total_tmu": res.total_tmu,
                        "total_seconds": res.total_seconds,
                        "published_by": ver.published_by,
                        "status": mod.status,
                        "drift_check": drift,
                    }
                )

    fields = [
        "no", "module_name_zh", "row_index", "hand", "seq_kind", "narrative_zh",
        "rule_set_code", "tech_line", "total_tmu", "total_seconds",
        "published_by", "status", "drift_check",
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    drifts = [r for r in rows_out if r["drift_check"]]
    print(f"count={len(rows_out)}  published_by={rows_out[0]['published_by'] if rows_out else 'N/A'}  "
          f"drift={len(drifts)}")
    for r in rows_out:
        print(f"{r['no']:>2} [{r['seq_kind']}] {r['hand']:<3} TMU={r['total_tmu']:>8.3f} "
              f"sec={r['total_seconds']:>6.3f}  {r['module_name_zh'][:34]}  {r['drift_check']}")
    print(f"\nCSV 已寫出：{out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "ie_v3_sequences.csv"
    asyncio.run(main(out))
