"""Worksheet 持久化 + SOP 版本：save→read roundtrip / versions / clone+publish / RBAC。"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"


def _gm_row():
    return {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": 1, "narrative": "ut roundtrip",
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}}


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def test_save_and_read_roundtrip(client):
    """存整表 → 讀回，TMU 由引擎算（GM 黃金=28）。用 clone 隔離，不動 demo 表。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()]})
    assert r.status_code == 200, r.text
    assert r.json()["total_tmu"] == 28
    rd = await client.get(f"/api/v2/worksheets/{new}")
    assert rd.status_code == 200
    rows = rd.json()["rows"]
    assert len(rows) == 1 and rows[0]["cycle"]["total_tmu"] == 28


async def test_allowance_roundtrip_standard_seconds(client):
    """impl-02 §3：allowance=10 → standard = normal × 1.1；未帶 allowance 再存不清除既有值。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()], "allowance_percent": 10})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["allowance_percent"] == 10
    assert j["normal_seconds"] > 0
    assert j["standard_seconds"] == pytest.approx(j["normal_seconds"] * 1.1, abs=1e-4)
    # 讀回同值
    rd = (await client.get(f"/api/v2/worksheets/{new}")).json()
    assert rd["allowance_percent"] == 10
    assert rd["standard_seconds"] == pytest.approx(rd["normal_seconds"] * 1.1, abs=1e-4)
    # 加法相容：payload 不帶 allowance_percent 再存 → 既有值不動
    r2 = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()]})
    assert r2.status_code == 200 and r2.json()["allowance_percent"] == 10


async def test_allowance_null_means_no_standard(client):
    """OQ-002：allowance 未設（null）→ standard_seconds 為 null（不得以 normal 假充 standard）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()], "allowance_percent": None})
    assert r.status_code == 200, r.text
    assert r.json()["allowance_percent"] is None
    assert r.json()["standard_seconds"] is None


async def test_allowance_negative_rejected(client):
    """邊界：allowance_percent < 0 → 422。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    r = await client.put(f"/api/v2/worksheets/{WS}", json={"rows": [_gm_row()], "allowance_percent": -5})
    assert r.status_code == 422


async def test_versions(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    j = (await client.get(f"/api/v2/worksheets/{WS}/versions")).json()
    assert "versions" in j and any(v["is_current"] for v in j["versions"])


async def test_clone_then_publish(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    assert (await client.post(f"/api/v2/worksheets/{new}/publish")).status_code == 200
    assert (await client.post(f"/api/v2/worksheets/{new}/publish")).status_code == 409  # 已發布再發布


async def test_rbac_viewer_cannot_clone(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    r = await client.post(f"/api/v2/worksheets/{WS}/clone", headers={"X-Username": "ZZZWSVIEWER"})
    assert r.status_code == 403


async def test_publish_analyst_returns_403(client):
    """analyst 身分（level=1）無法 publish；require_role("approver") 守門。

    F-06 RBAC 驗收：approver gate 對 analyst 確實回 403（非 200/409）。
    """
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    # admin（IEC141289）clone demo 表，取一個可操作的 draft
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    # 建立 analyst 用戶（roles=["analyst"]，level=1 < approver level=2）
    analyst_user = "GAPTEST_ANALYST_WS_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": analyst_user,
        "display_name": "Gap Test Analyst WS",
        "roles": ["analyst"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    # analyst 嘗試 publish → require_role("approver") 攔截 → 403
    r = await client.post(f"/api/v2/worksheets/{new}/publish", headers={"X-Username": analyst_user})
    assert r.status_code == 403, r.text


async def test_retire_happy_path(client):
    """admin clone → publish → retire → status=retired。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    assert (await client.post(f"/api/v2/worksheets/{new}/publish")).status_code == 200
    r = await client.post(f"/api/v2/worksheets/{new}/retire")
    assert r.status_code == 200, r.text
    j = r.json()
    cur = next(v for v in j["versions"] if v["is_current"])
    assert cur["status"] == "retired"


async def test_retire_non_approved_returns_409(client):
    """非 approved 狀態（draft）退役 → 409。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    # draft 直接 retire → 409
    r = await client.post(f"/api/v2/worksheets/{new}/retire")
    assert r.status_code == 409, r.text


async def test_retire_approver_returns_403(client):
    """approver（非 admin）不可 retire → 403。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    assert (await client.post(f"/api/v2/worksheets/{new}/publish")).status_code == 200
    # 建立 approver 用戶
    approver_user = f"GAP_APPROVER_RETIRE_{uuid.uuid4().hex[:6]}"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": approver_user,
        "display_name": "Gap Approver Retire Test",
        "roles": ["approver"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    r = await client.post(f"/api/v2/worksheets/{new}/retire", headers={"X-Username": approver_user})
    assert r.status_code == 403, r.text


async def test_publish_creates_audit_log(client, db_session):
    """publish → workflow_audit_log 有一筆 entity_type=process_version, action=approve。

    F-06 / ADR-018 裁決 3 驗收：publish 操作必須寫入不可變稽核記錄。
    用 conftest 的 db_session（與 client 同 connection/transaction）直接查 DB——
    不得自建 engine 打 DATABASE_URL（會繞過隔離、汙染真實 DB）。
    日後 GET /api/v2/audit-log 端點完成（impl-06c）後可改為 API 斷言。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2.audit import WorkflowAuditLog

    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")

    # 取一個乾淨 draft worksheet
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]

    # 執行 publish（admin 身分已在 client fixture 注入）
    r = await client.post(f"/api/v2/worksheets/{new}/publish")
    assert r.status_code == 200, r.text

    # 直接查 DB：確認稽核記錄已寫入（無 GET /api/v2/audit-log endpoint；impl-06c 補）
    entries = (await db_session.execute(
        select(WorkflowAuditLog).where(
            WorkflowAuditLog.action == "approve",
            WorkflowAuditLog.entity_type == "process_version",
        )
    )).scalars().all()

    assert len(entries) >= 1, "publish 後 workflow_audit_log 應有至少一筆 action=approve 記錄"
    last = entries[-1]
    assert last.entity_type == "process_version"
    assert last.to_status == "approved"
    assert last.actor != "", "actor 不應為空字串（publish 由 admin 執行，actor=IEC141289）"
