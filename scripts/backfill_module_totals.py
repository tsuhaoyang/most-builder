"""backfill_module_totals.py — 補算 motion_module_versions.total_tmu = 0 的記錄。

migration v2_0012 為避免 migration→engine 耦合，將 total_tmu/total_seconds 暫置 0。
本腳本在 DB 已有 rule_set（MINIMOST_FACTORY_V2）且 seed 完成後執行，對引擎重算並回填。

用法：
  DATABASE_URL=postgresql+asyncpg://... PYTHONPATH=src python scripts/backfill_module_totals.py
  DATABASE_URL=... PYTHONPATH=src python scripts/backfill_module_totals.py --dry-run

冪等：只補 total_tmu = 0 的版本；已有值的版本不動。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 讓腳本能 import ddm_v2（無需 pip install -e .）
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sqlalchemy import select, update  # noqa: E402

from ddm_v2.database import get_session_maker  # noqa: E402
from ddm_v2.models.v2.motion_module import MotionModule, MotionModuleVersion  # noqa: E402
from ddm_v2.models.v2.rule_set import RuleSet  # noqa: E402
from ddm_v2.most_engine import SequenceError, compute_cycle  # noqa: E402
from ddm_v2.most_engine.providers import load_rule_set_from_db  # noqa: E402
from ddm_v2.most_engine.rule_set_data import TMU_TO_SEC  # noqa: E402
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine  # noqa: E402


async def backfill(dry_run: bool) -> None:
    """主邏輯：掃 total_tmu=0 的版本，重算並回填。"""
    session_maker = get_session_maker()
    async with session_maker() as session:
        # 1. 找所有 total_tmu = 0 的版本（placeholder 值）
        result = await session.execute(
            select(MotionModuleVersion)
            .where(MotionModuleVersion.total_tmu == 0)
            .order_by(MotionModuleVersion.module_id, MotionModuleVersion.version_no)
        )
        versions = list(result.scalars().all())

        if not versions:
            print("沒有 total_tmu=0 的版本，無需補算。")
            return

        print(f"找到 {len(versions)} 個 total_tmu=0 的版本{'（dry-run，不寫入）' if dry_run else ''}：")

        # rule_set 快取（避免重複載入相同 rule_set）
        rs_cache: dict[str, object] = {}

        updated_count = 0
        skipped_count = 0

        for ver in versions:
            # 取對應 rule_set code
            rs_row = (await session.execute(
                select(RuleSet).where(RuleSet.id == ver.rule_set_id)
            )).scalar_one_or_none()

            if rs_row is None:
                print(
                    f"  [WARN] version {ver.id} (module={ver.module_id} v{ver.version_no}): "
                    f"rule_set_id={ver.rule_set_id} 不存在，跳過。"
                )
                skipped_count += 1
                continue

            rs_code = rs_row.code
            if rs_code not in rs_cache:
                try:
                    rs_cache[rs_code] = await load_rule_set_from_db(session, rs_code)
                except Exception as exc:
                    print(
                        f"  [WARN] version {ver.id}: 無法載入 rule_set '{rs_code}': {exc}，跳過。"
                    )
                    skipped_count += 1
                    continue

            rsdata = rs_cache[rs_code]

            # 對每列 row 重算 total_tmu
            rows: list[dict] = list(ver.rows) if ver.rows else []
            if not rows:
                print(
                    f"  [WARN] version {ver.id} (module={ver.module_id} v{ver.version_no}): "
                    f"rows 為空，跳過。"
                )
                skipped_count += 1
                continue

            total_tmu = 0.0
            any_error = False

            for row_idx, row_data in enumerate(rows):
                cycle_dict = row_data.get("cycle") or {}
                frequency = float(row_data.get("frequency") or 1)

                if not cycle_dict:
                    print(
                        f"  [WARN] version {ver.id} row[{row_idx}]: cycle 為空，此列 tmu 記 0。"
                    )
                    continue

                try:
                    cycle_obj = CycleIn.model_validate(cycle_dict)
                    engine_cycle = cycle_in_to_engine(cycle_obj)
                    result_obj = compute_cycle(engine_cycle, rsdata)
                    row_tmu = result_obj.total_tmu * frequency
                    total_tmu += row_tmu
                except (SequenceError, ValueError, Exception) as exc:
                    print(
                        f"  [WARN] version {ver.id} row[{row_idx}]: 引擎計算失敗 ({exc})，"
                        f"此列 tmu 記 0，繼續下一列。"
                    )
                    any_error = True
                    # 繼續；不因單列失敗中止整個版本

            total_tmu = round(total_tmu, 3)
            total_seconds = round(total_tmu * TMU_TO_SEC, 4)

            error_note = " (部分列計算失敗，已略過)" if any_error else ""
            print(
                f"  version {ver.id} (module={ver.module_id} v{ver.version_no}): "
                f"total_tmu={total_tmu}, total_seconds={total_seconds}{error_note}"
            )

            if not dry_run:
                # 更新 motion_module_versions
                await session.execute(
                    update(MotionModuleVersion)
                    .where(MotionModuleVersion.id == ver.id)
                    .values(total_tmu=total_tmu, total_seconds=total_seconds)
                )

                # 若此版本是 module.current_version，同步更新 module.updated_at
                # （motion_modules 本身無 total_tmu 欄位，僅標記 updated_at 讓 cache 失效）
                module_row = (await session.execute(
                    select(MotionModule)
                    .where(
                        MotionModule.id == ver.module_id,
                        MotionModule.current_version == ver.version_no,
                    )
                )).scalar_one_or_none()

                if module_row is not None:
                    from datetime import datetime, timezone
                    module_row.updated_at = datetime.now(timezone.utc)

            updated_count += 1

        if not dry_run:
            await session.commit()

        action = "預計更新" if dry_run else "已更新"
        print(
            f"\n完成：{action} {updated_count} 個版本；跳過 {skipped_count} 個版本。"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="補算 motion_module_versions.total_tmu=0 的佔位記錄。"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只印出預計的更新，不實際寫入 DB。",
    )
    args = parser.parse_args()

    asyncio.run(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
