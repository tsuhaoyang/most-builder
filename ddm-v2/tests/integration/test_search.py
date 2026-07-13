"""search API 端點整合測試（impl-03）。

涵蓋：
- 正常流程：GET /api/v2/search 有結果（需 search_documents 有資料）
- 空查詢：min_length=1 → 422
- 未授權：無 X-Username → 401
- types 過濾：只回指定 doc_type
- semantic=false（NullProvider 降級）
- q 過長：max_length=200 → 422
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_search_unauthorized(client, monkeypatch):
    """無授權 header → 401（借 ASGITransport 送空 header）。

    conftest 會設 AUTH_DEV_USER（dev fallback 身分）——此處必須拿掉，
    否則匿名請求被解析成 dev 使用者而回 200。
    """
    import httpx
    from ddm_v2.main import create_app

    monkeypatch.delenv("AUTH_DEV_USER", raising=False)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        r = await anon.get("/api/v2/search", params={"q": "test"})
    assert r.status_code == 401


async def test_search_empty_q_rejected(client):
    """q 為空字串 → 422（min_length=1 FastAPI validation）。"""
    r = await client.get("/api/v2/search", params={"q": ""})
    assert r.status_code == 422


async def test_search_q_too_long_rejected(client):
    """q 超過 200 字元 → 422。"""
    long_q = "a" * 201
    r = await client.get("/api/v2/search", params={"q": long_q})
    assert r.status_code == 422


async def test_search_returns_valid_structure(client):
    """正常請求，search_documents 可能空白，但結構必須正確。"""
    r = await client.get("/api/v2/search", params={"q": "測試"})
    assert r.status_code == 200
    body = r.json()
    assert "hits" in body
    assert "semantic" in body
    assert isinstance(body["hits"], list)
    assert isinstance(body["semantic"], bool)
    # NullProvider（預設）不會啟動 embedding，semantic 必定 False
    assert body["semantic"] is False


async def test_search_invalid_types_filtered(client):
    """types 包含非法值時，非法值被過濾掉（不 422）。"""
    r = await client.get("/api/v2/search", params={"q": "取料", "types": ["invalid_type"]})
    # 非法 type 全過濾後 fallback 為 motion_module，仍正常回 200
    assert r.status_code == 200
    body = r.json()
    assert body["semantic"] is False


async def test_search_limit_boundary(client):
    """limit 邊界：ge=1, le=50。"""
    # 上界 50 OK
    r = await client.get("/api/v2/search", params={"q": "壓合", "limit": 50})
    assert r.status_code == 200
    # 超出上界 → 422
    r2 = await client.get("/api/v2/search", params={"q": "壓合", "limit": 51})
    assert r2.status_code == 422
    # 下界 1 OK
    r3 = await client.get("/api/v2/search", params={"q": "壓合", "limit": 1})
    assert r3.status_code == 200
    # 低於下界 → 422
    r4 = await client.get("/api/v2/search", params={"q": "壓合", "limit": 0})
    assert r4.status_code == 422
