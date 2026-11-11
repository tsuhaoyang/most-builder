"""v2 API 整合測試（httpx ASGITransport 打 app；需 PostgreSQL，否則自動 skip）。

涵蓋：身分、Level 驗證端點、動作範本 CRUD+治理+比對、RBAC、calculate（rule-set 已種時）。
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def _set_stored_locale(db_session, value: str | None) -> None:
    """把測試使用者的 `app_users.locale` 原始值 arrange 成指定狀態（None = 未設定）。

    走 conftest 的 savepoint 隔離連線，測試結束隨外層 transaction rollback；
    共用開發庫零殘留。
    """
    from sqlalchemy import update as sa_update

    from ddm_v2.models.v2.auth import AppUser

    await db_session.execute(
        sa_update(AppUser).where(AppUser.employee_no == "IEC141289").values(locale=value)
    )
    await db_session.flush()


async def _stored_locale(db_session) -> str | None:
    """讀 `app_users.locale` 的**原始值**（可能 NULL）——用來區分「未設定」與「顯式 zh-TW」。"""
    from sqlalchemy import select as sa_select

    from ddm_v2.models.v2.auth import AppUser

    return (
        await db_session.execute(
            sa_select(AppUser.locale).where(AppUser.employee_no == "IEC141289")
        )
    ).scalar_one()


async def test_me_returns_identity(client, db_session):
    """身分欄位，含 ADR-032 D3.1：locale 未設定（NULL）→ 回傳解析後的系統預設。

    「未設定」這個前提由測試自己 arrange，不依賴共用開發庫該列的當下值
    （CI_GATES 硬性規則 7：不得依賴環境既存資料）——實機在 UI 切一次語言就會
    把該列寫成 'en'，靠既存狀態的版本會無故變紅。
    """
    await _set_stored_locale(db_session, None)
    assert await _stored_locale(db_session) is None, "arrange 失敗：欄位不是「未設定」"

    r = await client.get("/api/v2/me")
    assert r.status_code == 200
    body = r.json()
    assert body["employee_no"] == "IEC141289"
    assert body["level"] >= 1
    assert body["locale"] == "zh-TW"  # DEFAULT_LOCALE；解析在讀取端，欄位仍是 NULL
    assert await _stored_locale(db_session) is None, "讀取端解析不得回寫欄位"


async def test_me_locale_reflects_explicitly_stored_value(client, db_session):
    """對照組：欄位存了非預設值 → /me 回那個值。

    與上一條合起來，才證得到「zh-TW 是解析出來的預設」而不是端點寫死的常數。
    """
    await _set_stored_locale(db_session, "en")
    body = (await client.get("/api/v2/me")).json()
    assert body["locale"] == "en"


async def test_patch_my_locale_self_service(client, db_session):
    """ADR-032 D3.1：PATCH /me/locale 本人自助、無需 admin，且立即反映在 /me。"""
    await _set_stored_locale(db_session, None)

    r = await client.patch("/api/v2/me/locale", json={"locale": "en"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"

    r = await client.get("/api/v2/me")
    assert r.json()["locale"] == "en"
    assert await _stored_locale(db_session) == "en"

    # 改回 zh-TW：欄位存的是**顯式** 'zh-TW'，不是回到「未設定」——兩者在 /me 回應上
    # 長得一樣，只有查原始欄位才分得出來（表態過的使用者不隨系統預設改變而漂移）。
    r = await client.patch("/api/v2/me/locale", json={"locale": "zh-TW"})
    assert r.status_code == 200 and r.json()["locale"] == "zh-TW"
    assert await _stored_locale(db_session) == "zh-TW"
    # 本測試的寫入全在 savepoint 內，teardown 一併 rollback，不需要（也不能靠）手動清理。


async def test_patch_my_locale_rejects_unknown_value(client):
    """ADR-032 I6：語系碼值域固定為 zh-TW／en，第三種寫法一律拒絕（422）。"""
    r = await client.patch("/api/v2/me/locale", json={"locale": "zh-CN"})
    assert r.status_code == 422


async def test_level_validate_endpoint(client):
    good = [{"content": "A", "ascription": "main", "level": "1"},
            {"content": "B", "ascription": "main", "level": "2", "countersignature": "sub1", "order": 1},
            {"content": "C", "countersignature": "sub1", "order": 2}]
    r = await client.post("/api/v2/level/validate", json=good)
    assert r.status_code == 200 and r.json()["valid"] is True

    bad = [{"content": "A", "ascription": "main", "level": "3"},
           {"content": "B", "ascription": "main", "level": "1"}]
    r = await client.post("/api/v2/level/validate", json=bad)
    assert r.json()["valid"] is False


async def test_motion_template_lifecycle(client):
    # 建草稿 → 提升標準 → 比對命中 → 刪
    body = {"name_zh": "ut-範本", "seq_kind": "GM", "keywords": ["zzzutkw"],
            "cycle_template": {"seq": "GM", "g2": {"g_code": "g_grasp"}}}
    r = await client.post("/api/v2/motion-templates", json=body)
    assert r.status_code == 201
    t = r.json()
    assert t["status"] == "draft" and t["owner"] == "IEC141289"

    # 草稿不被 match（只比標準）
    m = await client.post("/api/v2/motion-templates/match", json={"description": "do zzzutkw now"})
    assert all(h["template"]["id"] != t["id"] for h in m.json())

    # admin（>=manager）提升為標準
    p = await client.post(f"/api/v2/motion-templates/{t['id']}/promote")
    assert p.status_code == 200 and p.json()["status"] == "standard"

    # 標準會被 match
    m = await client.post("/api/v2/motion-templates/match", json={"description": "do zzzutkw now"})
    assert any(h["template"]["id"] == t["id"] for h in m.json())

    d = await client.delete(f"/api/v2/motion-templates/{t['id']}")
    assert d.status_code == 204


async def test_rbac_viewer_cannot_create_template(client):
    # 換成未授權身分（JIT viewer）→ 建範本應 403
    body = {"name_zh": "ut-viewer", "seq_kind": "GM", "cycle_template": {"seq": "GM", "g2": {"g_code": "g_grasp"}}}
    r = await client.post("/api/v2/motion-templates", json=body, headers={"X-Username": "ZZZUTVIEWER"})
    assert r.status_code == 403


async def test_calculate_gm_golden_if_seeded(client):
    cycle = {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
             "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
             "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}
    r = await client.post("/api/v2/minimost/calculate", json=cycle)
    if r.status_code != 200:
        pytest.skip(f"rule-set 未種入（status {r.status_code}）")
    assert r.json()["total_tmu"] == 28
