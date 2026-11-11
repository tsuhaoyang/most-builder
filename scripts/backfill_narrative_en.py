"""backfill_narrative_en.py — 為既有 `most_cycles` 補 `narrative_en`（ADR-032 D7.5）。

用法：
  DATABASE_URL=postgresql+asyncpg://... PYTHONPATH=src python scripts/backfill_narrative_en.py
  DATABASE_URL=... PYTHONPATH=src python scripts/backfill_narrative_en.py --dry-run

冪等：只補 `narrative_en IS NULL` 的列；已有值的不動（重跑不覆寫）。

**I4：本腳本不得重算 TMU。** 兩道機制保證：

1. **只讀 `slot_inputs`、只寫 `narrative_en`。** 完全不呼叫 `compute_cycle`／
   `compute_table`，連 `RuleSetData` 都不載入——載入的是 `load_options_by_rule_set_id`
   （標籤／句面），那是敘事素材，不是計價表。
2. **標籤以每列自己的 `most_cycles.rule_set_id` 載入**，不是 active 版。
   `rule_set_id` 是回放的唯一依據；拿現行 active 字典去重新詮釋歷史 cycle，
   等於把兩年前的案件按今天的字典改寫（CLAUDE.md〈No error bypass〉等級的靜默污染）。

**零改動的自我證明**：commit 之前，腳本把所有 cycle 的 TMU 相關欄位
（`seq_kind`／`total_tmu`／`total_seconds`／`computed`／`slot_inputs`／`rule_set_id`）
在**同一個交易內**重新查一次，與開跑前的快照逐列比對；有任何一格不同就 rollback 並
非 0 結束。這比事後人工 diff 可靠：人工 diff 只證明「這次跑完沒變」，這裡是「不同就
不准 commit」。外部驗證方式見檔尾 `VERIFY_SQL`。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

# 讓腳本能 import ddm_v2（無需 pip install -e .）
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from ddm_v2.database import get_session_maker  # noqa: E402
from ddm_v2.models.v2.vocab import WorkVocabItem  # noqa: E402
from ddm_v2.models.v2.worksheet import MostCycle, WiRow  # noqa: E402
from ddm_v2.most_engine.narrative_en import build_narrative_en  # noqa: E402
from ddm_v2.most_engine.providers import (  # noqa: E402
    build_label_map,
    load_options_by_rule_set_id,
)

# 外部驗證用（跑腳本前後各執行一次，輸出必須逐字相同）：
VERIFY_SQL = (
    "SELECT id, seq_kind, rule_set_id, total_tmu, total_seconds, computed, slot_inputs "
    "FROM most_cycles ORDER BY id"
)

# 「TMU 相關」的定義＝這些欄位。narrative_zh／narrative_en 刻意不在內（前者不該被動、
# 後者正是本腳本要寫的）。
_TMU_COLUMNS = (
    MostCycle.id,
    MostCycle.seq_kind,
    MostCycle.rule_set_id,
    MostCycle.total_tmu,
    MostCycle.total_seconds,
    MostCycle.computed,
    MostCycle.slot_inputs,
)


class TmuChanged(SystemExit):
    """回填動到了 TMU 相關欄位——I4 違反，交易已 rollback。"""


async def _tmu_snapshot(session: AsyncSession) -> dict[str, str]:
    """全表 TMU 相關欄位的快照：`cycle_id → 正規化 JSON`（可逐列比對、可印出差異）。"""
    rows = (await session.execute(select(*_TMU_COLUMNS).order_by(MostCycle.id))).all()
    return {
        str(r.id): json.dumps(
            [r.seq_kind, str(r.rule_set_id), str(r.total_tmu), str(r.total_seconds),
             r.computed, r.slot_inputs],
            sort_keys=True, ensure_ascii=False, default=str,
        )
        for r in rows
    }


def _diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    problems = [f"消失的 cycle {k}" for k in before.keys() - after.keys()]
    problems += [f"憑空出現的 cycle {k}" for k in after.keys() - before.keys()]
    problems += [
        f"cycle {k} 的 TMU 欄位被改動：\n    before={before[k]}\n    after ={after[k]}"
        for k in before.keys() & after.keys()
        if before[k] != after[k]
    ]
    return problems


async def backfill(dry_run: bool) -> None:
    session_maker = get_session_maker()
    async with session_maker() as session:
        before = await _tmu_snapshot(session)

        pending = list((await session.execute(
            select(MostCycle).where(MostCycle.narrative_en.is_(None)).order_by(MostCycle.id)
        )).scalars().all())
        if not pending:
            print(f"沒有 narrative_en IS NULL 的 cycle（全表 {len(before)} 列），無需回填。")
            return
        print(f"全表 {len(before)} 列，其中 {len(pending)} 列待回填"
              f"{'（dry-run，不寫入）' if dry_run else ''}。")

        # 每列以**自己的** rule_set_id 載標籤（I4）；同版本只載一次。
        labels_cache: dict[uuid.UUID, dict[str, dict[str, Any]] | None] = {}

        wi_rows = {
            r.id: r for r in (await session.execute(
                select(WiRow).where(WiRow.id.in_([c.wi_row_id for c in pending]))
            )).scalars().all()
        }
        vids = {
            vid for r in wi_rows.values()
            for vid in (r.object_vocab_id, r.from_vocab_id, r.to_vocab_id) if vid
        }
        vname_en: dict[uuid.UUID, str] = {}
        if vids:
            for v in (await session.execute(
                select(WorkVocabItem).where(WorkVocabItem.id.in_(vids))
            )).scalars().all():
                vname_en[v.id] = v.name_en or v.name_zh

        filled = 0
        skipped_no_rule_set: list[str] = []
        by_rule_set: dict[str, int] = {}
        for cyc in pending:
            if cyc.rule_set_id not in labels_cache:
                opts = await load_options_by_rule_set_id(session, cyc.rule_set_id)
                labels_cache[cyc.rule_set_id] = build_label_map(opts) if opts else None
            labels = labels_cache[cyc.rule_set_id]
            if labels is None:
                # rule_set_id 有 FK，理論上查得到；查不到就是資料異常，記錄後跳過，
                # 不用 active 版頂替（那正是 I4 禁止的靜默重新詮釋）。
                skipped_no_rule_set.append(str(cyc.id))
                continue
            wr = wi_rows.get(cyc.wi_row_id)
            voc = {
                "object": vname_en.get(wr.object_vocab_id, "") if wr and wr.object_vocab_id else "",
                "from": vname_en.get(wr.from_vocab_id, "") if wr and wr.from_vocab_id else "",
                "to": vname_en.get(wr.to_vocab_id, "") if wr and wr.to_vocab_id else "",
                "hand": (wr.hand if wr else "") or "",
            }
            cyc.narrative_en = build_narrative_en(cyc.slot_inputs, labels, voc)
            filled += 1
            key = str(cyc.rule_set_id)
            by_rule_set[key] = by_rule_set.get(key, 0) + 1

        await session.flush()
        problems = _diff(before, await _tmu_snapshot(session))
        if problems:
            await session.rollback()
            raise TmuChanged(
                "回填動到了 TMU 相關欄位（ADR-032 I4），交易已 rollback：\n  - "
                + "\n  - ".join(problems)
            )

        if dry_run:
            await session.rollback()
            print(f"✓ dry-run：{filled} 列可回填，TMU 欄位零改動（已 rollback）。")
        else:
            await session.commit()
            print(f"✓ 回填 {filled} 列 narrative_en，TMU 欄位零改動（同交易內逐列比對通過）。")
        print(f"  依 rule_set_id：{by_rule_set}")
        if skipped_no_rule_set:
            print(f"✗ {len(skipped_no_rule_set)} 列的 rule_set_id 查無對應版本，已跳過"
                  f"（不以 active 版頂替）：{skipped_no_rule_set}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只計算、不寫入")
    asyncio.run(backfill(ap.parse_args().dry_run))


if __name__ == "__main__":
    main()
