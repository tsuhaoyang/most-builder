"""v2 測試共用 fixtures。

- 單元測試（unit/）：純引擎，免 DB。
- 整合測試（integration/）：用 httpx ASGITransport 打 v2 app，需 PostgreSQL（DATABASE_URL）。
  DB 不可用時自動 skip。

測試資料隔離（P0-0.2 汙染治理）：
    每個整合測試在「外層 connection transaction + nested savepoint」內執行——
    - `db_ctx` 開一條專用 connection 並 BEGIN 外層 transaction；
    - app 的 `get_db_session` 依賴被 override 成綁定該 connection 的 session
      （join_transaction_mode="create_savepoint"），service 層的 session.commit()
      只 RELEASE SAVEPOINT，不會真正落盤；
    - teardown 一律 ROLLBACK 外層 transaction → 測試寫入零殘留。
    需要直接查/改 DB 的測試請用 `db_session` fixture（同一條 connection，
    能看見 API 請求寫入的資料，也一起被 rollback）。
    ⚠️ 測試內不得自行 create_async_engine 連 DATABASE_URL——那會繞過隔離、
    汙染真實資料庫。
"""
from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ddm_v2.most_engine import build_from_seed, build_from_seed_v2


@pytest.fixture(autouse=True)
def _reset_global_session_cache():
    """清 database.get_session_maker() 的全域快取（engine 綁在建立時的 event loop）。

    多數整合測試走 client fixture 的 dependency override，不會碰全域快取；
    但直接 create_app() 而未 override 的測試（如匿名 401 測試）會，
    pytest-asyncio 每測試獨立 loop → 不清會炸「attached to a different loop」。
    """
    import ddm_v2.database as db

    db._async_session_maker = None
    yield
    db._async_session_maker = None


@pytest.fixture(scope="session")
def rs():
    """工廠 rule-set V2（v3 IE 認證字典，ADR-014；自 seed 建，免 DB）——黃金測試主錨。"""
    return build_from_seed_v2()


@pytest.fixture(scope="session")
def rs_v1():
    """工廠 rule-set V1（歷史回放：快照隔離證明；含 gating/precision/舊階梯語意）。"""
    return build_from_seed()


@pytest_asyncio.fixture
async def db_ctx():
    """外層 transaction 隔離：yield 綁定單一 connection 的 sessionmaker，teardown 全部 rollback。

    - sessionmaker 用 join_transaction_mode="create_savepoint"：session.commit()
      只提交 SAVEPOINT，資料在外層 transaction 內對「同 connection 的後續 session」可見，
      但測試結束 ROLLBACK 後資料庫零殘留。
    - engine 用 NullPool 且 per-test 建立：pytest-asyncio 每個測試獨立 event loop，
      避免跨 loop 共用 asyncpg 連線（"another operation is in progress"）。
    - ⚠️ 單一 connection 串所有請求；測試內勿用 asyncio.gather 併發呼叫 client，
      會踩 asyncpg「another operation is in progress」。
    """
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL 未設定，略過整合測試")

    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as e:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"PostgreSQL 連不上，略過整合測試：{e}")

    trans = await conn.begin()
    session_maker = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session_maker
    finally:
        try:
            await trans.rollback()
        finally:
            await conn.close()
            await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_ctx):
    """直接 DB 存取用 session（與 client 同 connection/transaction；一起被 rollback）。"""
    async with db_ctx() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_ctx):
    """以 admin 身分（gateway header）打 v2 app；所有 DB 寫入走 db_ctx 的 savepoint 隔離。"""
    os.environ.setdefault("AUTH_DEV_USER", "IEC141289")

    from ddm_v2.database import get_db_session
    from ddm_v2.main import create_app

    app = create_app()

    async def _txn_session():
        """鏡像 get_db_session 語意（commit on success / rollback on error），但綁隔離 connection。"""
        async with db_ctx() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _txn_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Username": "IEC141289"}
    ) as c:
        yield c
