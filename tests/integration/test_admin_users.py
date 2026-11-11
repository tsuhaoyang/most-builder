"""使用者/角色管理（admin）+ 防呆 + RBAC。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_users_lifecycle_and_guards(client):
    emp = "UT_TESTUSER_1"
    assert (await client.get("/api/v2/admin/users")).status_code == 200
    r = await client.post("/api/v2/admin/users", json={"employee_no": emp, "display_name": "UT", "roles": ["analyst"]})
    assert r.status_code == 200 and "analyst" in r.json()["roles"]
    r = await client.patch(f"/api/v2/admin/users/{emp}", json={"roles": ["analyst", "approver"]})
    assert "approver" in r.json()["roles"]
    assert (await client.patch(f"/api/v2/admin/users/{emp}", json={"roles": ["wizard"]})).status_code == 422
    # 不可移除自己的 admin / 停用自己
    assert (await client.patch("/api/v2/admin/users/IEC141289", json={"roles": ["analyst"]})).status_code == 409
    assert (await client.patch("/api/v2/admin/users/IEC141289", json={"is_active": False})).status_code == 409
    assert (await client.patch("/api/v2/admin/users/NOPE_NOBODY", json={"roles": ["analyst"]})).status_code == 404


async def test_users_rbac_viewer_403(client):
    assert (await client.get("/api/v2/admin/users", headers={"X-Username": "ZZZADMVIEW"})).status_code == 403
