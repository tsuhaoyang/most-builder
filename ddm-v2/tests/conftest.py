"""v2 測試共用 fixtures。

- 單元測試（unit/）：純引擎，免 DB。
- 整合測試（integration/）：用 httpx ASGITransport 打 v2 app，需 PostgreSQL（DATABASE_URL）。
  DB 不可用時自動 skip。

注意：pytest-asyncio 每個測試用獨立 event loop，而 database.get_session_maker() 會快取
engine/sessionmaker（綁在第一個 loop）。故每個整合測試前後都把該快取清掉，讓 engine 在
當前 loop 重建，避免 asyncpg「another operation is in progress」。
"""
from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from ddm_v2.most_engine import build_from_seed, build_from_seed_v2


@pytest.fixture(scope="session")
def rs():
    """工廠 rule-set V2（v3 IE 認證字典，ADR-014；自 seed 建，免 DB）——黃金測試主錨。"""
    return build_from_seed_v2()


@pytest.fixture(scope="session")
def rs_v1():
    """工廠 rule-set V1（歷史回放：快照隔離證明；含 gating/precision/舊階梯語意）。"""
    return build_from_seed()


@pytest_asyncio.fixture
async def client():
    """以 admin 身分（gateway header）打 v2 app；DB 不可用則 skip。"""
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL 未設定，略過整合測試")
    os.environ.setdefault("AUTH_DEV_USER", "IEC141289")

    import ddm_v2.database as db

    db._async_session_maker = None  # 在當前 loop 重建
    from ddm_v2.database import get_engine

    try:
        eng = get_engine()
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await eng.dispose()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"PostgreSQL 連不上，略過整合測試：{e}")

    from ddm_v2.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"X-Username": "IEC141289"}) as c:
        yield c

    db._async_session_maker = None  # 清掉，避免殘留到下個 loop
