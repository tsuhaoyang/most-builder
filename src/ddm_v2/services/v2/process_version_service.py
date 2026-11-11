"""ProcessVersion 版本號配號（併發安全）。

`version_no` 為 TEXT `v{n}`；`uq_process_versions_sku_id_version_no` 是 (sku_id, version_no) 複合唯一。
併發對同一 sku 配號會踩 read-modify-write 競態（兩交易讀到相同 count → 撞唯一鍵 → 500）。
以 **同交易 advisory lock**（per sku）序列化配號：鎖到 commit 才釋放，故必須與 insert 在同一交易，
且呼叫端配號後不得先 commit 再 insert。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.worksheet import ProcessVersion


async def next_version_no(session: AsyncSession, sku_id: uuid.UUID) -> str:
    """回下一個 version_no（`v{count+1}`）。同交易 advisory lock 序列化同 sku 的配號。"""
    # xact advisory lock：同 sku 的併發配號序列化（鎖到本交易 commit/rollback 釋放）
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": str(sku_id)}
    )
    count = (
        await session.execute(
            select(func.count()).select_from(ProcessVersion).where(ProcessVersion.sku_id == sku_id)
        )
    ).scalar_one()
    return f"v{int(count) + 1}"


__all__ = ["next_version_no"]
