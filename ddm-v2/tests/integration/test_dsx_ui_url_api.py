"""GET /api/v2/dsx/ui-url——DSX 3D 擺放介面網址（給前端開 iframe modal 用）。

只驗端點走真的 DB session（`current_user` 的 JIT 建立/查詢）能正常回應；不需要
真的連到 DSX（這條端點只是把 `settings.dsx_ui_url` 原樣吐出來）。
"""
from __future__ import annotations

import os

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration


async def test_ui_url_returns_configured_value(client, monkeypatch):
    from ddm_v2.settings import get_settings

    monkeypatch.setenv("DDM_DSX_UI_URL", "http://172.32.3.60:8081/most.html")
    get_settings.cache_clear()
    try:
        resp = await client.get("/api/v2/dsx/ui-url")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"url": "http://172.32.3.60:8081/most.html"}
    finally:
        get_settings.cache_clear()


async def test_ui_url_returns_null_when_unset(client, monkeypatch):
    from ddm_v2.settings import get_settings

    monkeypatch.delenv("DDM_DSX_UI_URL", raising=False)
    get_settings.cache_clear()
    try:
        resp = await client.get("/api/v2/dsx/ui-url")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"url": None}
    finally:
        get_settings.cache_clear()


async def test_ui_url_requires_authentication(monkeypatch):
    """`current_user`：匿名（不帶認證）→ 401（照抄 test_dsx_a3_distance_api.py 慣例）。"""
    import httpx

    from ddm_v2.main import create_app

    monkeypatch.delenv("AUTH_DEV_USER", raising=False)
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        r = await anon.get("/api/v2/dsx/ui-url")
    assert r.status_code == 401, r.text
