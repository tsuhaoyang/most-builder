"""匯出整合測試：wi-preview / excel / lb-csv / lb-api。

特別守住「openpyxl 等 runtime 依賴漏宣告」這類回歸——excel 端點會載 openpyxl，
依賴缺失時會 500。需 demo worksheet（dev_seed_v2 的 5555…）；未種則 skip。
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"


async def _seeded(client) -> bool:
    r = await client.get(f"/api/v2/worksheets/{WS}/export/wi-preview")
    return r.status_code == 200


async def test_wi_preview(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r = await client.get(f"/api/v2/worksheets/{WS}/export/wi-preview")
    assert r.status_code == 200
    assert "total_tmu" in r.json()


async def test_export_excel(client):
    """守 openpyxl：缺依賴會 500。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    r = await client.get(f"/api/v2/worksheets/{WS}/export/excel")
    assert r.status_code == 200, f"excel 匯出失敗（檢查 openpyxl 是否在 runtime 依賴）：{r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "octet-stream" in ct, ct


async def test_export_lb_csv(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    r = await client.get(f"/api/v2/worksheets/{WS}/export/lb-csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "") or len(r.content) > 0


async def test_export_lb_api_dry_run(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    r = await client.post(f"/api/v2/worksheets/{WS}/export/lb-api")
    assert r.status_code == 200
    assert "payload" in r.json()
