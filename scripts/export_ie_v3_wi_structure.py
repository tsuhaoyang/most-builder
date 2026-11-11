"""匯出「IE 手填、v3 匯入」的 WI⊃motion 兩層結構為 CSV。

體現核心模型（.kiro/steering/wi-motion-core-structure.md）：
  - WI 層 = wi-template motion_module（一句 WI 語句，module.name_zh）
  - motion 層 = 該 module 當前版本 rows[] 的每一列（一個七格 MOST model）

每個 motion 帶：sub_activity（動作描述）、narrative_zh、七格 tech_line、
hand、frequency、SIMO 標記、該 motion 的 contribution_tmu（SIMO 從屬列貢獻 0）。
TMU 由單一權威引擎（most_engine）就地重算；WI 合計 = Σ contribution_tmu。

用法：
    PYTHONPATH=src DATABASE_URL=... python scripts/export_ie_v3_wi_structure.py [out.csv]
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


async def main(out_path: str) -> None:
    sessionmaker = get_session_maker()
    rows_out: list[dict] = []
    async with sessionmaker() as session:
        result = await session.execute(
            select(MotionModule, MotionModuleVersion)
            .join(MotionModuleVersion, MotionModuleVersion.module_id == MotionModule.id)
            .where(
                MotionModule.category == "wi-template",
                MotionModule.keywords.contains(["v3-import"]),
                MotionModuleVersion.version_no == MotionModule.current_version,
            )
            .order_by(MotionModule.name_zh)
        )
        pairs = result.all()

        rs_cache: dict[str, object] = {}
        wi_no = 0
        for mod, ver in pairs:
            wi_no += 1
            n_motions = len(ver.rows)
            for mi, row in enumerate(ver.rows, start=1):
                cycle = CycleIn.model_validate(row["cycle"])
                code = cycle.rule_set_code
                if code not in rs_cache:
                    rs = await load_rule_set_from_db(session, code)
                    rs.validate_complete()
                    rs_cache[code] = rs
                res = compute_cycle(cycle_in_to_engine(cycle), rs_cache[code])
                computed = row.get("computed") or {}
                rows_out.append(
                    {
                        "wi_no": wi_no,
                        "wi_statement": mod.name_zh,          # WI 層：一句 WI 語句
                        "wi_total_tmu": float(ver.total_tmu),
                        "wi_total_seconds": float(ver.total_seconds),
                        "motion_seq": f"{mi}/{n_motions}",    # 此 WI 底下第 mi 個 motion
                        "hand": row.get("hand", ""),
                        "seq_kind": cycle.seq,
                        "sub_activity": row.get("sub_activity", ""),   # motion 動作描述
                        "motion_narrative_zh": row.get("narrative_zh", ""),
                        "tech_line": res.tech_line,
                        "motion_tmu": res.total_tmu,          # 單一 motion 本身 TMU（引擎重算）
                        "frequency": row.get("frequency", 1),
                        "contribution_tmu": computed.get("contribution_tmu"),  # 計入 WI 合計的量（SIMO 從屬=0）
                        "simo_pair_index": row.get("simo_pair_index"),
                        "published_by": ver.published_by,
                        "rule_set_code": code,
                    }
                )

    fields = [
        "wi_no", "wi_statement", "wi_total_tmu", "wi_total_seconds",
        "motion_seq", "hand", "seq_kind", "sub_activity", "motion_narrative_zh",
        "tech_line", "motion_tmu", "frequency", "contribution_tmu", "simo_pair_index",
        "published_by", "rule_set_code",
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    n_wi = len({r["wi_no"] for r in rows_out})
    print(f"WI 語句={n_wi}  motions={len(rows_out)}  published_by="
          f"{rows_out[0]['published_by'] if rows_out else 'N/A'}\n")
    cur = None
    for r in rows_out:
        if r["wi_no"] != cur:
            cur = r["wi_no"]
            print(f"\n▶ WI#{r['wi_no']} 「{r['wi_statement']}」  "
                  f"= {r['wi_total_tmu']:.0f} TMU / {r['wi_total_seconds']:.3f}s")
        simo = f" [SIMO→{r['simo_pair_index']}]" if r["simo_pair_index"] is not None else ""
        freq = f" ×{r['frequency']}" if r["frequency"] not in (1, None) else ""
        print(f"    {r['motion_seq']:>5} [{r['seq_kind']}] {r['hand']:<3} "
              f"motion={r['motion_tmu']:>7.1f} contrib={r['contribution_tmu']}{freq}{simo}  "
              f"{r['sub_activity'][:30]}")
    print(f"\nCSV 已寫出：{out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "ie_v3_wi_structure.csv"
    asyncio.run(main(out))
