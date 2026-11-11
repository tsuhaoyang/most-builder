"""Rule-set 端點：list / options / full（規則表檢視 + 計算依據）。

涵蓋：
- 正常路徑：list / options / full（11 區塊有資料）
- RBAC 邊界：analyst 無法 publish rule-set（require_role("approver") 守門）

⚠️ ADR-023：檢視類斷言讀 active 版本（V2）；任何會改狀態的操作（clone/publish/activate/retire）
一律走 `throwaway_rule_set` fixture 的專用版本，**不得**對 V1/V2 動手——它們是回放基準版本
（V1 尤其：TMU 快照回放的證據，見 test_rule_set_replay_isolation.py）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration

CODE = "MINIMOST_FACTORY_V2"  # active 版本（唯讀檢視用）


@pytest_asyncio.fixture
async def throwaway_rule_set(db_session) -> str:
    """clone 出一個拋棄式 draft 版本供狀態變更測試使用（隔離 transaction 內，測後 rollback）。"""
    from ddm_v2.services.v2 import rule_set_service as svc

    code = f"UT_RS_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, CODE, code, "拋棄式測試版")
    await db_session.commit()
    return code


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


async def test_publish_analyst_returns_403(client, throwaway_rule_set):
    """analyst 身分（level=1）無法 publish rule-set；require_role("approver") 守門。

    F-06 RBAC 驗收：approver gate 對 analyst 確實回 403。
    role check 先於業務邏輯，但仍打拋棄式 draft，確保即使守門失效也不會污染 V1/V2。
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
    r = await client.post(f"/api/v2/rule-sets/{throwaway_rule_set}/publish", headers=h)
    assert r.status_code == 403, r.text


async def test_activate_retire_analyst_returns_403(client, db_session, throwaway_rule_set):
    """ADR-023 §3.2：activate/retire 是本批權限最高的新操作 → approver gate 必須守住。

    analyst（level=1）打這兩個端點一律 403，且**狀態不得有任何變動**
    （403 若只擋回應卻已改 DB，等於守門失效）。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.services.v2 import rule_set_service as svc

    # 拋棄式版本先 publish（由 admin 身分），讓 activate 的業務前置條件成立——
    # 這樣 403 一定來自 RBAC 守門，而不是「因為它還是 draft」。
    await svc.publish(db_session, throwaway_rule_set, actor="UT_RBAC")
    await db_session.commit()

    analyst_user = "GAPTEST_ANALYST_RS_002"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": analyst_user,
        "display_name": "Gap Test Analyst Activate",
        "roles": ["analyst"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    h = {"X-Username": analyst_user}

    before = (await db_session.execute(
        select(RuleSet.code).where(RuleSet.is_active.is_(True)))).scalars().all()

    ra = await client.post(f"/api/v2/rule-sets/{throwaway_rule_set}/activate", headers=h)
    assert ra.status_code == 403, ra.text
    rr = await client.post(f"/api/v2/rule-sets/{throwaway_rule_set}/retire", headers=h)
    assert rr.status_code == 403, rr.text

    target = (await db_session.execute(
        select(RuleSet).where(RuleSet.code == throwaway_rule_set))).scalar_one()
    await db_session.refresh(target)
    assert target.is_active is False, "403 後不得留下任何啟用副作用"
    assert target.status == "published", "403 後不得留下任何下架副作用"
    after = (await db_session.execute(
        select(RuleSet.code).where(RuleSet.is_active.is_(True)))).scalars().all()
    assert after == before, "被拒的請求不得改動 active 版本"
