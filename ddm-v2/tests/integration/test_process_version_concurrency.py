"""併發配號序列化（advisory lock）：兩個獨立 session 同時 clone 同一 worksheet → 皆成功、
version_no 相異且連續。修 TICKET_clone_concurrency_version_no（uq_process_versions_sku_id_version_no 競態）。

⚠️ 例外：本檔自建 engine（兩條真實連線）以驗併發——conftest 的 db_ctx 單連線無法表達併發
（同連線併發會踩 asyncpg「another operation in progress」）。僅此檔、只為此併發語意。
無 DATABASE_URL → skip。
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def own_engine():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL 未設定，略過整合測試")
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _seed_worksheet(engine) -> tuple[str, str]:
    """自建最小案件，回 (worksheet_id, sku_id)；獨立交易 commit（本檔清理靠 CONCUR_ 前綴人工可查）。"""
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion

    sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    tag = uuid.uuid4().hex[:8]
    async with sm() as s:
        site = Site(name_zh=f"CONCUR_SITE_{tag}")
        s.add(site)
        await s.flush()
        product = Product(site_id=site.id, name_zh=f"CONCUR_PROD_{tag}")
        s.add(product)
        await s.flush()
        sku = Sku(product_id=product.id, sku_code=f"CONCUR_SKU_{tag}", name_zh=f"併發 {tag}")
        s.add(sku)
        await s.flush()
        pv = ProcessVersion(sku_id=sku.id, version_no="v1", status="draft")
        s.add(pv)
        await s.flush()
        ws = MostWorksheet(process_version_id=pv.id, model_label="CONCUR", status="draft")
        s.add(ws)
        await s.flush()
        await s.commit()
        return str(ws.id), str(sku.id)


async def test_concurrent_clone_serialized_version_no(own_engine):
    from ddm_v2.services.v2.worksheet_service import clone_worksheet

    ws_id, sku_id = await _seed_worksheet(own_engine)
    sm = async_sessionmaker(bind=own_engine, class_=AsyncSession, expire_on_commit=False)

    async def _clone() -> str:
        async with sm() as s:
            out = await clone_worksheet(s, uuid.UUID(ws_id))
            await s.commit()
            return out["version_no"]

    # 兩個獨立 session（獨立連線）同時 clone → advisory lock 序列化配號
    v1, v2 = await asyncio.gather(_clone(), _clone())
    assert {v1, v2} == {"v2", "v3"}, f"版本號應相異且連續，實得 {v1}, {v2}"

    # DB 端確認三個版本（v1 seed + v2 + v3），無重複
    async with own_engine.connect() as conn:
        n = (await conn.execute(
            text("SELECT count(*) FROM process_versions WHERE sku_id = :s"), {"s": sku_id}
        )).scalar_one()
    assert n == 3
