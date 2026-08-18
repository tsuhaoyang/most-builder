"""v2 API 整合測試（httpx ASGITransport 打 app；需 PostgreSQL，否則自動 skip）。

涵蓋：身分、Level 驗證端點、動作範本 CRUD+治理+比對、RBAC、calculate（rule-set 已種時）。
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_me_returns_identity(client):
    r = await client.get("/api/v2/me")
    assert r.status_code == 200
    body = r.json()
    assert body["employee_no"] == "IEC141289"
    assert body["level"] >= 1
    # ADR-032 D3.1：未設定 locale 的既有測試使用者 → 回傳解析後的系統預設，不是 null。
    assert body["locale"] == "zh-TW"


async def test_patch_my_locale_self_service(client):
    """ADR-032 D3.1：PATCH /me/locale 本人自助、無需 admin，且立即反映在 /me。"""
    r = await client.patch("/api/v2/me/locale", json={"locale": "en"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"

    r = await client.get("/api/v2/me")
    assert r.json()["locale"] == "en"

    # 改回 zh-TW（避免污染同 fixture 下的其他測試）
    r = await client.patch("/api/v2/me/locale", json={"locale": "zh-TW"})
    assert r.status_code == 200 and r.json()["locale"] == "zh-TW"


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
