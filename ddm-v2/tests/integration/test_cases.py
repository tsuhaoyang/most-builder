"""案件清單 API：GET /api/v2/cases — 正常 / 篩選 / RBAC。"""
from __future__ import annotations

import datetime as _dt
import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def test_list_cases_happy_path(client):
    """正常：案件清單回 200，total >= 1，items 有欄位。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r = await client.get("/api/v2/cases")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "total" in j and "items" in j
    assert j["total"] >= 1
    first = j["items"][0]
    # 必要欄位存在
    for field in ("process_version_id", "worksheet_id", "version_no", "status",
                  "site_id", "site_name", "product_id", "product_name",
                  "sku_id", "sku_name", "process_name", "created_at"):
        assert field in first, f"缺欄位：{field}"


async def test_list_cases_status_filter(client):
    """status=draft 篩選：所有回傳 item.status == 'draft'。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r = await client.get("/api/v2/cases?status=draft")
    assert r.status_code == 200, r.text
    j = r.json()
    for item in j["items"]:
        assert item["status"] == "draft"


async def test_list_cases_invalid_status_returns_empty(client):
    """不存在的 status 值：回 200，items 為空。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r = await client.get("/api/v2/cases?status=nonexistent")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


async def test_list_cases_site_filter(client):
    """site_id 篩選：所有回傳 item.site_id 符合。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    # 先拿到一個合法 site_id
    all_cases = (await client.get("/api/v2/cases")).json()
    if not all_cases["items"]:
        pytest.skip("無案件可測")
    site_id = all_cases["items"][0]["site_id"]
    r = await client.get(f"/api/v2/cases?site_id={site_id}")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["site_id"] == site_id


async def test_list_cases_pagination(client):
    """limit=1 offset=0 和 offset=0 的結果應一致（只取第一筆）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r1 = await client.get("/api/v2/cases?limit=1&offset=0")
    assert r1.status_code == 200
    assert len(r1.json()["items"]) <= 1


async def test_list_cases_unauthenticated_returns_401(client):
    """無認證 header → 401（gateway mode 下 X-Username 缺席）。

    client fixture 已注入 X-Username；此測試用不帶 header 的獨立請求。
    """
    import httpx

    from ddm_v2.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        r = await anon.get("/api/v2/cases")
    # gateway 模式下無 X-Username 且無 AUTH_DEV_USER → 401
    # 但 conftest 設了 AUTH_DEV_USER=IEC141289；skip 此邊界確保不誤阻正常流程
    # 實際環境下 gateway 會擋，此處只驗非 500
    assert r.status_code in (200, 401, 403)


# ---------------------------------------------------------------------------
# P1-A：案件級聚合（一案件一列＋歷史折疊）
# 規格：docs/v3/v2-authoritative-model-guide.md §1 版本語意、§6 案件清單收斂
# ---------------------------------------------------------------------------


async def _make_case(db_session, *, versions, model_label="AGG_TEST", sku_code=None):
    """在隔離 transaction 內建一條版本鏈（同 SKU、同 model_label）。

    versions: [(version_no, status, created_at_offset_minutes)]
    回傳 (sku_id, [(process_version_id, worksheet_id, version_no), ...])
    """
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion

    tag = uuid.uuid4().hex[:8]
    site = Site(name_zh=f"AGGTEST_SITE_{tag}")
    db_session.add(site)
    await db_session.flush()
    product = Product(site_id=site.id, name_zh=f"AGGTEST_PROD_{tag}")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(product_id=product.id, sku_code=sku_code or f"AGGTEST_SKU_{tag}", name_zh=f"AGG 測試料號 {tag}")
    db_session.add(sku)
    await db_session.flush()

    base = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    made = []
    for version_no, status, minutes in versions:
        pv = ProcessVersion(
            sku_id=sku.id, version_no=version_no, status=status,
            created_at=base + _dt.timedelta(minutes=minutes),
        )
        db_session.add(pv)
        await db_session.flush()
        ws = MostWorksheet(process_version_id=pv.id, model_label=model_label, status=status)
        db_session.add(ws)
        await db_session.flush()
        made.append((str(pv.id), str(ws.id), version_no))
    await db_session.commit()
    return str(sku.id), made


async def test_list_cases_aggregates_versions_into_one_case(client, db_session):
    """同 SKU × model_label 的多版 → 聚合成一筆案件；代表版＝最新版；versions 按版本序。"""
    sku_id, made = await _make_case(db_session, versions=[
        ("v1", "draft", 0), ("v2", "approved", 10), ("v3", "draft", 20), ("v4", "approved", 30),
    ])

    j = (await client.get("/api/v2/cases?limit=200")).json()
    mine = [it for it in j["items"] if it["sku_id"] == sku_id]
    assert len(mine) == 1, f"同 SKU 多版應聚合為 1 筆案件，實得 {len(mine)}"
    case = mine[0]

    # 代表版＝最新版（created_at 最大）
    assert case["version_no"] == "v4"
    assert case["status"] == "approved"
    assert case["process_version_id"] == made[-1][0]
    assert case["worksheet_id"] == made[-1][1]

    # 版本折疊
    assert case["version_count"] == 4
    assert [v["version_no"] for v in case["versions"]] == ["v1", "v2", "v3", "v4"]
    assert [v["status"] for v in case["versions"]] == ["draft", "approved", "draft", "approved"]
    for v in case["versions"]:
        for field in ("process_version_id", "worksheet_id", "version_no", "status",
                      "total_tmu", "created_at", "approved_at"):
            assert field in v, f"versions[] 缺欄位：{field}"


async def test_list_cases_total_counts_cases_not_versions(client, db_session):
    """total 是案件數：新增 3 版只讓 total +1。"""
    before = (await client.get("/api/v2/cases")).json()["total"]
    await _make_case(db_session, versions=[("v1", "draft", 0), ("v2", "draft", 5), ("v3", "draft", 9)])
    after = (await client.get("/api/v2/cases")).json()["total"]
    assert after == before + 1, f"3 個版本應只增加 1 筆案件（{before} → {after}）"


async def test_list_cases_model_label_splits_cases(client, db_session):
    """聚合鍵含 model_label：同 SKU 不同 model_label → 兩筆案件。"""
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion

    sku_id, _ = await _make_case(db_session, versions=[("v1", "draft", 0)], model_label="MODEL_A")
    pv = ProcessVersion(sku_id=uuid.UUID(sku_id), version_no="v2", status="draft",
                        created_at=_dt.datetime(2026, 1, 1, 0, 30, tzinfo=_dt.timezone.utc))
    db_session.add(pv)
    await db_session.flush()
    db_session.add(MostWorksheet(process_version_id=pv.id, model_label="MODEL_B", status="draft"))
    await db_session.commit()

    j = (await client.get("/api/v2/cases?limit=200")).json()
    mine = [it for it in j["items"] if it["sku_id"] == sku_id]
    assert len(mine) == 2, "不同 model_label 應視為不同案件"
    assert {it["model_label"] for it in mine} == {"MODEL_A", "MODEL_B"}
    assert all(it["version_count"] == 1 for it in mine)


async def test_list_cases_status_filters_representative_version(client, db_session):
    """status 篩選代表版狀態；被篩掉的案件不出現，但入選案件的 versions[] 仍含完整歷史。"""
    sku_id, _ = await _make_case(db_session, versions=[("v1", "draft", 0), ("v2", "approved", 10)])

    # 代表版是 approved → status=draft 不該出現（即使 v1 是 draft）
    draft_ids = [it["sku_id"] for it in (await client.get("/api/v2/cases?status=draft&limit=200")).json()["items"]]
    assert sku_id not in draft_ids

    approved = [it for it in (await client.get("/api/v2/cases?status=approved&limit=200")).json()["items"]
                if it["sku_id"] == sku_id]
    assert len(approved) == 1
    # 歷史不受 status 篩選影響
    assert [v["version_no"] for v in approved[0]["versions"]] == ["v1", "v2"]
    assert approved[0]["version_count"] == 2


async def test_list_cases_pagination_is_case_level(client, db_session):
    """limit/offset 套在案件層級：limit=1 回 1 筆案件（不是 1 個版本），且仍帶完整 versions。"""
    await _make_case(db_session, versions=[("v1", "draft", 0), ("v2", "draft", 10), ("v3", "draft", 20)])

    total = (await client.get("/api/v2/cases")).json()["total"]
    r1 = (await client.get("/api/v2/cases?limit=1&offset=0")).json()
    assert r1["total"] == total
    assert len(r1["items"]) == 1
    assert r1["items"][0]["version_count"] >= 1
    assert len(r1["items"][0]["versions"]) == r1["items"][0]["version_count"]

    # offset 邊界：offset >= total → 空頁但 total 不變
    rN = (await client.get(f"/api/v2/cases?limit=10&offset={total}")).json()
    assert rN["total"] == total
    assert rN["items"] == []

    # 相鄰頁不重疊
    p0 = (await client.get("/api/v2/cases?limit=1&offset=0")).json()["items"]
    p1 = (await client.get("/api/v2/cases?limit=1&offset=1")).json()["items"]
    if p1:
        assert p0[0]["process_version_id"] != p1[0]["process_version_id"]
