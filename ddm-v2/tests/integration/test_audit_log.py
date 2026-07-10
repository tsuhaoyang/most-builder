"""稽核日誌 API 整合測試（impl-06c）。

涵蓋：
- RBAC：analyst 以下無法查詢（403）
- 正常查詢：publish worksheet 後 audit-log 至少有一筆 action='approve'
- 過濾：?entity_type=process_version 只回 process_version 筆
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

# 固定的 demo worksheet id（與 test_worksheet.py 相同；需先跑 dev_seed_v2.py）
WS = "55555555-5555-5555-5555-555555555555"


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


# ── RBAC 守門 ────────────────────────────────────────────────────────

async def test_list_requires_approver(client):
    """analyst（或更低）查 audit-log → 403。

    以 IEC141289 admin 建立一個 analyst 使用者，再用該使用者的 X-Username 存取。
    """
    analyst_emp = f"UT_AUDIT_ANALYST_{uuid.uuid4().hex[:6]}"

    # 先用 admin 建立 analyst 使用者
    r = await client.post(
        "/api/v2/admin/users",
        json={"employee_no": analyst_emp, "display_name": "UT Analyst", "roles": ["analyst"]},
    )
    assert r.status_code == 200, f"建立 analyst 使用者失敗：{r.text}"

    # analyst 查 audit-log → 403
    r = await client.get("/api/v2/audit-log", headers={"X-Username": analyst_emp})
    assert r.status_code == 403, f"預期 403，得到 {r.status_code}：{r.text}"


# ── 正常查詢 ─────────────────────────────────────────────────────────

async def test_list_returns_entries(client):
    """publish 一個 worksheet → audit-log 至少有一筆 action='approve'。

    IEC141289 為 admin（approver 以上），可查詢 audit-log。
    """
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")

    # clone 一個 draft 以確保有 draft 可 publish（不動原始 demo 狀態）
    clone_r = await client.post(f"/api/v2/worksheets/{WS}/clone")
    assert clone_r.status_code == 200, f"clone 失敗：{clone_r.text}"
    new_ws_id = clone_r.json()["new_worksheet_id"]

    # publish → 觸發 log_audit(action='approve', entity_type='process_version')
    pub_r = await client.post(f"/api/v2/worksheets/{new_ws_id}/publish")
    assert pub_r.status_code == 200, f"publish 失敗：{pub_r.text}"

    # 查 audit-log（admin 身分，有 approver 以上）
    r = await client.get("/api/v2/audit-log")
    assert r.status_code == 200, f"GET audit-log 失敗：{r.text}"
    body = r.json()
    assert "total" in body and "items" in body
    assert body["total"] >= 1

    # 至少有一筆 action='approve'
    actions = {item["action"] for item in body["items"]}
    assert "approve" in actions, f"items 中找不到 action='approve'：{actions}"


# ── entity_type 過濾 ──────────────────────────────────────────────────

async def test_list_filter_entity_type(client):
    """?entity_type=process_version 只回 process_version 筆，其他 entity_type 不出現。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")

    # 確保 audit-log 中有 process_version 紀錄（publish 一次）
    clone_r = await client.post(f"/api/v2/worksheets/{WS}/clone")
    assert clone_r.status_code == 200, clone_r.text
    new_ws_id = clone_r.json()["new_worksheet_id"]
    await client.post(f"/api/v2/worksheets/{new_ws_id}/publish")

    # 過濾 entity_type=process_version
    r = await client.get("/api/v2/audit-log", params={"entity_type": "process_version"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["entity_type"] == "process_version", (
            f"過濾後不應出現 entity_type={item['entity_type']}"
        )

    # 反向驗證：entity_type=motion_module 結果只含 motion_module（即使有其他類型資料）
    r2 = await client.get("/api/v2/audit-log", params={"entity_type": "motion_module"})
    assert r2.status_code == 200, r2.text
    for item in r2.json()["items"]:
        assert item["entity_type"] == "motion_module"
