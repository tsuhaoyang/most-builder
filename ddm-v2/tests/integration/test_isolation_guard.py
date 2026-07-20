"""測試隔離迴歸保險絲（CI_GATES 3b：integration 測試永不落真實 DB）。

背景：`docs/v3/v2-authoritative-model-guide.md` §1「版本爆量事後剖析」——
隔離改造（17661cc）之前，integration 的 clone 直接落盤，demo SKU 累積到 279 版
（268 筆具測試簽名）。本檔是防止再犯的保險絲：只要 conftest 的
「外層 transaction + savepoint + teardown rollback」被改壞，這裡立刻紅燈。

**兩條寫入路徑各測一次**（隔離機制不同，壞法也不同）：
1. `client` → app dependency override（`_txn_session`）——測 clone 端點；
2. `db_session` → 測試自己 ORM insert + commit——測 fixture 路徑。
兩條都必須「transaction 內看得到、真實 DB 看不到」。每條都重複寫入 N 次，
隔離破損時外部計數會 +N，訊號明確。

**不依賴 dev_seed**：被寫入的資料全由測試自建（GUARDTEST_% 簽名）。
保險絲不該有「沒接上」的靜默狀態——乾淨 CI DB 上也照樣生效。

⚠️ 例外說明：conftest 明令「測試內不得自行 create_async_engine」，因為那會繞過
隔離。本檔是該規則的**唯一例外且只讀不寫**——要證明「外面看不到」，就必須從
外面看。任何其他測試都不該複製這個模式。
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

WRITE_ROUNDS = 3  # 重複寫入次數：隔離破損時外部計數 +N


@pytest_asyncio.fixture
async def outside():
    """獨立唯讀連線：看「真實 DB」的狀態（測試 transaction 之外）。"""
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL 未設定，略過整合測試")
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)

    async def _scalar(sql: str) -> int:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql))).scalar_one()

    try:
        yield _scalar
    finally:
        await engine.dispose()


async def _make_guard_worksheet(db_session) -> tuple[str, str]:
    """自建一條可 clone 的最小案件（不依賴 dev_seed）。回傳 (worksheet_id, sku_id)。"""
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion

    tag = uuid.uuid4().hex[:8]
    site = Site(name_zh=f"GUARDTEST_SITE_{tag}")
    db_session.add(site)
    await db_session.flush()
    product = Product(site_id=site.id, name_zh=f"GUARDTEST_PROD_{tag}")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(product_id=product.id, sku_code=f"GUARDTEST_SKU_{tag}", name_zh=f"保險絲 {tag}")
    db_session.add(sku)
    await db_session.flush()
    pv = ProcessVersion(sku_id=sku.id, version_no="v1", status="draft")
    db_session.add(pv)
    await db_session.flush()
    ws = MostWorksheet(process_version_id=pv.id, model_label="GUARDTEST", status="draft")
    db_session.add(ws)
    await db_session.flush()
    await db_session.commit()
    return str(ws.id), str(sku.id)


async def test_clone_writes_never_reach_real_db(client, db_session, outside):
    """端點寫入路徑：連續 clone N 次，真實 DB 的 process_versions 計數不得改變。"""
    ws_id, sku_id = await _make_guard_worksheet(db_session)
    before = await outside("SELECT count(*) FROM process_versions")

    for _ in range(WRITE_ROUNDS):
        r = await client.post(f"/api/v2/worksheets/{ws_id}/clone")
        assert r.status_code in (200, 201), r.text

    # 前置條件：transaction 內確實寫進去了（否則這保險絲是空測）
    inside = (await client.get("/api/v2/cases?limit=200")).json()
    mine = [it for it in inside["items"] if it["sku_id"] == sku_id]
    assert len(mine) == 1, "自建案件應在 transaction 內可見"
    assert mine[0]["version_count"] == 1 + WRITE_ROUNDS, (
        f"clone {WRITE_ROUNDS} 次後應有 {1 + WRITE_ROUNDS} 版，實得 {mine[0]['version_count']}"
    )

    # 真實 DB（獨立連線）：完全看不到這些寫入
    after = await outside("SELECT count(*) FROM process_versions")
    assert after == before, (
        f"隔離破損：integration 測試落了真實 DB（process_versions {before} → {after}，"
        f"clone 了 {WRITE_ROUNDS} 次）。檢查 tests/conftest.py 的 db_ctx / client "
        "dependency override（CI_GATES 3b）。"
    )


async def test_fixture_writes_never_reach_real_db(db_session, outside):
    """fixture 寫入路徑：測試自己 ORM insert + commit N 次也不得落盤。

    與上一條互補——`db_session.commit()` 走 savepoint 語意，若
    `join_transaction_mode='create_savepoint'` 被改掉，commit 會真的落盤，
    而端點路徑可能仍看似正常。
    """
    from ddm_v2.models.v2.worksheet import MostWorksheet

    sql = "SELECT count(*) FROM sites WHERE name_zh LIKE 'GUARDTEST\\_%'"
    before = await outside(sql)

    made = [await _make_guard_worksheet(db_session) for _ in range(WRITE_ROUNDS)]

    # 前置條件：transaction 內看得到（commit 已 RELEASE SAVEPOINT）
    for ws_id, _ in made:
        assert await db_session.get(MostWorksheet, uuid.UUID(ws_id)) is not None

    after = await outside(sql)
    assert after == before == 0, (
        f"隔離破損：測試 fixture 的 commit 落了真實 DB（GUARDTEST sites {before} → {after}，"
        f"建了 {WRITE_ROUNDS} 筆）。檢查 conftest db_ctx 的 "
        "join_transaction_mode='create_savepoint' 與 teardown rollback。"
    )


async def test_no_test_signature_residue_in_real_db(outside):
    """真實 DB 不得有本套測試的簽名殘留（含歷史殘留）。

    殘留清理：`scripts/cleanup_test_data.py`（預設 dry-run）。
    """
    for sql, label in (
        ("SELECT count(*) FROM sites WHERE name_zh LIKE 'AGGTEST\\_%'", "AGGTEST sites"),
        ("SELECT count(*) FROM sites WHERE name_zh LIKE 'GUARDTEST\\_%'", "GUARDTEST sites"),
        ("SELECT count(*) FROM products WHERE name_zh LIKE 'AGGTEST\\_%'", "AGGTEST products"),
        ("SELECT count(*) FROM products WHERE name_zh LIKE 'GUARDTEST\\_%'", "GUARDTEST products"),
        ("SELECT count(*) FROM skus WHERE sku_code LIKE 'AGGTEST\\_%'", "AGGTEST skus"),
        ("SELECT count(*) FROM skus WHERE sku_code LIKE 'GUARDTEST\\_%'", "GUARDTEST skus"),
    ):
        n = await outside(sql)
        assert n == 0, f"真實 DB 有測試殘留：{label} = {n}（跑 scripts/cleanup_test_data.py 清理）"
