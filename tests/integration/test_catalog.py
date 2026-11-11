"""目錄/結構：Site→Product→Sku→建立工序表；RBAC / 404 / 409。"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _a_site(client) -> str | None:
    r = await client.get("/api/v2/sites")
    assert r.status_code == 200
    sites = r.json()
    return sites[0]["id"] if sites else None


async def test_product_sku_worksheet_flow(client):
    site = await _a_site(client)
    if not site:
        pytest.skip("無 site（先跑 dev_seed_v2.py）")
    sfx = uuid.uuid4().hex[:8]
    # product
    p = await client.post("/api/v2/products", json={"site_id": site, "name_zh": "UT產品", "external_code": f"UTPRD-{sfx}"})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    assert p.json()["is_active"] is True
    # 停用 → 啟用
    assert (await client.patch(f"/api/v2/products/{pid}", json={"is_active": False})).json()["is_active"] is False
    assert (await client.patch(f"/api/v2/products/{pid}", json={"is_active": True})).json()["is_active"] is True
    # sku
    s = await client.post("/api/v2/skus", json={"product_id": pid, "sku_code": f"UTSKU-{sfx}", "name_zh": "UT機種"})
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    assert any(x["id"] == sid for x in (await client.get(f"/api/v2/skus?product_id={pid}")).json())
    # 重複 sku_code → 409
    assert (await client.post("/api/v2/skus", json={"product_id": pid, "sku_code": f"UTSKU-{sfx}"})).status_code == 409
    # 建立工序表
    w = await client.post(f"/api/v2/skus/{sid}/worksheets", json={"model_label": "UT-LINE", "analyst": "IEC141289"})
    assert w.status_code == 201, w.text
    wid = w.json()["worksheet_id"]
    assert w.json()["version_no"] == "v1"
    # 列出 + 可讀
    lst = await client.get(f"/api/v2/skus/{sid}/worksheets")
    assert any(x["worksheet_id"] == wid for x in lst.json())
    assert (await client.get(f"/api/v2/worksheets/{wid}")).status_code == 200


async def test_rbac_viewer_cannot_mutate(client):
    site = await _a_site(client)
    if not site:
        pytest.skip("無 site")
    h = {"X-Username": "ZZZCATVIEWER"}
    assert (await client.post("/api/v2/products", json={"site_id": site, "name_zh": "x"}, headers=h)).status_code == 403


async def test_notfound(client):
    missing = str(uuid.uuid4())
    assert (await client.post("/api/v2/skus", json={"product_id": missing, "sku_code": "x"})).status_code == 404
    assert (await client.get(f"/api/v2/skus/{missing}/worksheets")).status_code == 404
    assert (await client.post(f"/api/v2/skus/{missing}/worksheets", json={})).status_code == 404
