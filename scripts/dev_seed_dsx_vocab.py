"""dev seed：DSX「MOST 單站情境」場景物件 → work_vocab_items.external_code 對照（一次性）。

DSX 整合 API 契約 v2 §2.3（User 2026-08-24 裁決）：mapping 責任在 MOST 端。
`external_code` 直接填 DSX **物件 id**（`data-service/config.yaml` 的 `objects[].id`，
非 `vocab_code` 佔位碼——DistanceQuery.from_id/to_id 吃的是前者，已對照
`dsx_ai_factory/scenarios/most-single-station/data-service/{config.yaml,vocab_map.py,store.py}`
原始碼核對過），是**真實資料**，非佔位資料。

⚠️ `work_vocab_items.kind` 是單值欄位（CHECK ∈ object/component/tool/from/to/hand），但 DSX
的 `vocab_kinds` 可以是多值（例如 `manual_workstation` 同時是 `[from, to]`——工作站既可取也
可放）。`external_code` 又是 unique，同一個 DSX 物件不能兩列共用同一個 `external_code`。

**裁決（User 2026-08-24）**：對這 5 個雙 kind 物件（`manual_workstation`／`conveyor`／
`material_shuttle`／`bin_yellow`／`bin_white`，已對照 DSX `config.yaml` 的 `vocab_kinds`
逐一核對），除了原本 `kind='from'` 那一列，**額外多種一列 `kind='to'`**，`external_code`
加上 `dsx_service.SYNTHETIC_TO_SUFFIX`（`"__to"`）後綴以繞過 unique 限制（例如
`manual_workstation` → `manual_workstation__to`）。這個後綴**只存在於 MOST 這一側**，DSX
不知道也不需要知道——`dsx_service._strip_synthetic_suffix()` 在送 `to_id` 給 DSX
`/api/v1/distance` 之前會先剝掉它，換回 DSX 認得的原始物件 id。這樣「到哪裡」下拉才會出現
這些可雙向的物件，同時查詢時送給 DSX 的 id 仍是真實值。

跑：DATABASE_URL=... PYTHONPATH=src python scripts/dev_seed_dsx_vocab.py
"""
from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import ddm_v2.models.v2 as M
from ddm_v2.services.v2.dsx_service import SYNTHETIC_TO_SUFFIX

# (external_code, kind, name_zh) —— 逐列來源：見模組 docstring。
DSX_OBJECTS: list[tuple[str, str, str]] = [
    ("human", "hand", "作業員"),
    ("manual_workstation", "from", "手動工作站"),
    ("conveyor", "from", "輸送帶作業位"),
    ("material_shuttle", "from", "料車"),
    ("tool_01", "tool", "工具 01"),
    ("tool_02", "tool", "工具 02"),
    # DSX 側 vocab_kinds=[]（不列入任何語句欄位：「螢幕不是取放對象」，config.yaml 原註）。
    # work_vocab_items.kind 無「無分類」選項，取最接近的通用桶 object。
    ("monitor", "object", "螢幕"),
    ("bin_yellow", "from", "料盒（黃）"),
    ("bin_white", "from", "料盒（白）"),
]

# DSX config.yaml 裡 vocab_kinds=[from, to] 的物件（見模組 docstring）。
# 對應 DSX_OBJECTS 裡的 external_code，額外多種一列 kind='to'。
DSX_DUAL_KIND_OBJECTS: frozenset[str] = frozenset(
    {"manual_workstation", "conveyor", "material_shuttle", "bin_yellow", "bin_white"}
)


def _extra_to_rows() -> list[tuple[str, str, str]]:
    return [
        (f"{external_code}{SYNTHETIC_TO_SUFFIX}", "to", f"{name_zh}（到）")
        for external_code, kind, name_zh in DSX_OBJECTS
        if external_code in DSX_DUAL_KIND_OBJECTS
    ]


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        for external_code, kind, name_zh in [*DSX_OBJECTS, *_extra_to_rows()]:
            existing = (
                await s.execute(
                    select(M.WorkVocabItem).where(M.WorkVocabItem.external_code == external_code)
                )
            ).scalar_one_or_none()
            if existing is None:
                s.add(
                    M.WorkVocabItem(
                        id=uuid.uuid4(),
                        external_code=external_code,
                        kind=kind,
                        name_zh=name_zh,
                        source_system="local",
                    )
                )
                print("  + WorkVocabItem", external_code, kind, name_zh)
            else:
                print("  exists:", external_code, "(kind=%s)" % existing.kind)
        await s.commit()
    await engine.dispose()
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
