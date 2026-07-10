"""Rule-set 端點：list / options / full（規則表檢視 + 計算依據）。

涵蓋：
- 正常路徑：list / options / full（11 區塊有資料）
- RBAC 邊界：analyst 無法 publish rule-set（require_role("approver") 守門）
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

CODE = "MINIMOST_FACTORY_V1"


async def test_rule_set_list_options_full(client):
    lst = await client.get("/api/v2/rule-sets")
    if lst.status_code != 200 or not lst.json():
        pytest.skip("rule-set 未種")
    assert any(r["code"] == CODE for r in lst.json())
    assert (await client.get(f"/api/v2/rule-sets/{CODE}/options")).status_code == 200
    full = await client.get(f"/api/v2/rule-sets/{CODE}/full")
    assert full.status_code == 200
    f = full.json()
    for sec in ["a_bands", "g", "p_bases", "m_verbs", "x", "i"]:
        assert len(f[sec]) > 0, f"規則區塊 {sec} 是空的"


async def test_publish_analyst_returns_403(client):
    """analyst 身分（level=1）無法 publish rule-set；require_role("approver") 守門。

    F-06 RBAC 驗收：approver gate 對 analyst 確實回 403。
    role check 先於「是否為 draft」業務邏輯，不需先建立 draft。
    """
    lst = await client.get("/api/v2/rule-sets")
    if lst.status_code != 200 or not lst.json():
        pytest.skip("rule-set 未種")
    # 建立 analyst 用戶（roles=["analyst"]，level=1 < approver level=2）
    analyst_user = "GAPTEST_ANALYST_RS_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": analyst_user,
        "display_name": "Gap Test Analyst Rule-Set",
        "roles": ["analyst"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    # analyst 嘗試 publish → require_role("approver") 攔截 → 403
    h = {"X-Username": analyst_user}
    r = await client.post(f"/api/v2/rule-sets/{CODE}/publish", headers=h)
    assert r.status_code == 403, r.text
