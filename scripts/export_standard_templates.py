"""匯出「IE 認證／廠標準」動作範本（motion_templates.status='standard'）為 CSV。

TMU 一律由單一權威引擎計算（most_engine.compute_cycle），不手算。
用法：
    PYTHONPATH=src DATABASE_URL=... python scripts/export_standard_templates.py [out.csv]
"""
from __future__ import annotations

import asyncio
import csv
import sys

from sqlalchemy import select

from ddm_v2.database import get_session_maker
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.most_engine import compute_cycle, load_rule_set_from_db
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine
from ddm_v2.services.v2.rule_set_service import get_active_rule_set_code


async def main(out_path: str) -> None:
    sessionmaker = get_session_maker()
    rows_out: list[dict] = []
    async with sessionmaker() as session:
        active_code = await get_active_rule_set_code(session)
        rs = await load_rule_set_from_db(session, active_code)
        rs.validate_complete()

        result = await session.execute(
            select(MotionTemplate)
            .where(MotionTemplate.status == "standard", MotionTemplate.is_active.is_(True))
            .order_by(MotionTemplate.seq_kind, MotionTemplate.name_zh)
        )
        templates = result.scalars().all()

        for i, t in enumerate(templates, start=1):
            cycle = CycleIn.model_validate(t.cycle_template)
            res = compute_cycle(cycle_in_to_engine(cycle), rs)
            rows_out.append(
                {
                    "no": i,
                    "seq_kind": t.seq_kind,
                    "name_zh": t.name_zh,
                    "name_en": t.name_en or "",
                    "category": t.category or "",
                    "keywords": "|".join(t.keywords or []),
                    "rule_set_code": active_code,
                    "tech_line": res.tech_line,
                    "total_tmu": res.total_tmu,
                    "total_seconds": res.total_seconds,
                    "status": t.status,
                }
            )

    fields = [
        "no", "seq_kind", "name_zh", "name_en", "category", "keywords",
        "rule_set_code", "tech_line", "total_tmu", "total_seconds", "status",
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    # 同時印到 stdout 供檢視
    print(f"rule_set(active)={rows_out[0]['rule_set_code'] if rows_out else 'N/A'}  count={len(rows_out)}")
    for r in rows_out:
        print(f"{r['no']:>2} [{r['seq_kind']}] {r['name_zh']:<12} {r['tech_line']:<28} "
              f"TMU={r['total_tmu']:>8.3f}  sec={r['total_seconds']:>7.3f}")
    print(f"\nCSV 已寫出：{out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "standard_templates.csv"
    asyncio.run(main(out))
