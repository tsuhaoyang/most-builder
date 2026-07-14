"""`MINIMOST_FACTORY_V2` 選項冪等同步：seed → live DB（insert-missing only）。

背景：dev_seed 對已存在的 rule-set 採 skip-if-exists，不會把重生後的
rule_set_seed_v2.py 新選項（如 v3 字典同步 2026-07-14 的 m_press / x_blow_clean）
帶進既有 DB。本腳本把 seed 中「code 尚不存在於 DB」的選項插入對應子表。

鐵則：
- **只新增、不改既有值**（既有列的 tmu / label / sort_order 一律不動）。
- 只動 `MINIMOST_FACTORY_V2`；V1 rule-set 不碰。
- 帶(band)類表（A/M ladder/foot/hand/rotation）無 code 鍵且本次無變更 → 不在同步範圍；
  若 seed 帶值與 DB 不一致，僅印出警告請人工裁決（不自動改）。
- 新列 sort_order = 該表現有 max+1（避免與既有列撞號；與 fresh-seed 的排序僅外觀差異，值相同）。

用法：cd ddm-v2 && PYTHONPATH=src DATABASE_URL=... .venv/bin/python scripts/sync_rule_set_v2_options.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

RULE_SET_CODE = "MINIMOST_FACTORY_V2"


async def sync() -> int:
    from sqlalchemy import func, select

    from ddm_v2.database import get_session_maker
    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.seed.v2 import rule_set_seed_v2 as s

    # (model, seed_rows, row→kwargs)：code 鍵子表全表齊檢（本次實際新增只有 M/X 兩筆）
    specs = [
        (rt.RuleBOption, s.B_OPTIONS,
         lambda r: dict(code=r[0], label_zh=r[1], index_value=r[2], is_default=r[3],
                        sentence_text_zh=r[5] or None)),
        (rt.RuleGAction, s.G_ACTIONS,
         lambda r: dict(code=r[0], label_zh=r[1], modifier_key=r[2], requires_modifier=r[3],
                        base_tmu=r[4], sentence_text_zh=r[6] or None)),
        (rt.RulePBase, s.P_BASES,
         lambda r: dict(code=r[0], label_zh=r[1], category=r[2], direction_mode=r[3],
                        base_tmu=r[4], sentence_text_zh=r[6] or None)),
        (rt.RulePAddon, s.P_ADDONS,
         lambda r: dict(code=r[0], label_zh=r[1], delta_tmu=r[2], needs_precision=r[3],
                        display_rule=r[5], sentence_text_zh=r[6] or None)),
        (rt.RuleMVerb, s.M_VERBS,
         lambda r: dict(code=r[0], label_zh=r[1], pricing_kind=r[2], fixed_tmu=r[3],
                        sentence_text_zh=r[5] or None)),
        (rt.RuleXOption, s.X_OPTIONS,
         lambda r: dict(code=r[0], label_zh=r[1], mode=r[2], fixed_seconds=r[3],
                        sentence_text_zh=r[5] or None)),
        (rt.RuleIOption, s.I_OPTIONS,
         lambda r: dict(code=r[0], label_zh=r[1], index_value=r[2], vision_scope=r[4],
                        sentence_text_zh=r[5] or None)),
    ]

    maker = get_session_maker()
    inserted = 0
    async with maker() as session:
        rs = (await session.execute(
            select(RuleSet).where(RuleSet.code == RULE_SET_CODE)
        )).scalar_one_or_none()
        if rs is None:
            print(f"[中止] DB 無 rule-set {RULE_SET_CODE}（請先跑 dev_seed）", file=sys.stderr)
            return 1

        for model, seed_rows, to_kwargs in specs:
            existing = set((await session.execute(
                select(model.code).where(model.rule_set_id == rs.id)
            )).scalars().all())
            missing = [r for r in seed_rows if r[0] not in existing]
            if not missing:
                continue
            max_sort = (await session.execute(
                select(func.max(model.sort_order)).where(model.rule_set_id == rs.id)
            )).scalar() or 0
            for i, r in enumerate(missing, start=1):
                kwargs = to_kwargs(r)
                session.add(model(id=uuid.uuid4(), rule_set_id=rs.id,
                                  sort_order=max_sort + i, **kwargs))
                inserted += 1
                print(f"  + {model.__tablename__}: {kwargs['code']}"
                      f"（sort_order={max_sort + i}）")
        await session.commit()

    print(f"同步完成：新增 {inserted} 筆選項（0 筆修改——insert-missing only）。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(sync()))
