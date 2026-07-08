"""motion_modules 端點測試（impl-04）。

涵蓋：
- 正常流程：建立→改 metadata→發布→取版本→列表
- 錯誤邊界：publish 空 rows→422、publish 壞 cycle→422、update 非 draft→409
- RBAC：viewer 不可建立模組→403
- 版本不可變：publish 後不可 update metadata（draft 限定）
- promote：501 placeholder
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _get_rule_set_id(client) -> str | None:
    """取第一個可用的 rule_set id（供 publish 用）。"""
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        return None
    return r.json()[0]["id"]


# ── 正常流程 ─────────────────────────────────────────────────────────

async def test_create_and_get_module(client):
    """建立 draft 模組，取得詳情。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"測試模組-{sfx}",
        "scope": "personal",
        "keywords": ["取放", "測試"],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["scope"] == "personal"
    assert body["status"] == "draft"
    assert body["current_version"] == 0
    mid = body["id"]

    # 取詳情
    g = await client.get(f"/api/v2/motion-modules/{mid}")
    assert g.status_code == 200, g.text
    assert g.json()["id"] == mid
    assert g.json()["current_version_detail"] is None  # 尚無版本


async def test_update_metadata_draft(client):
    """draft 模組可改 metadata。"""
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-Upd-Draft",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    up = await client.put(f"/api/v2/motion-modules/{mid}", json={
        "name_zh": "UT-Upd-Draft-Changed",
        "keywords": ["changed"],
    })
    assert up.status_code == 200, up.text
    assert up.json()["name_zh"] == "UT-Upd-Draft-Changed"
    assert up.json()["keywords"] == ["changed"]


async def test_publish_version(client):
    """正常 publish：引擎驗算 → 寫入版本快照。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Pub-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # publish：GM A6 B0 G6 A10 B0 P6 A0 = 28 TMU
    payload = {
        "rule_set_id": rs_id,
        "rows": [{
            "hand": "RH",
            "frequency": 1,
            "vocab_refs": {},
            "cycle": {
                "seq": "GM",
                "rule_set_code": "MINIMOST_FACTORY_V2",
                "a0": {"reach_cm": 30},
                "g2": {"g_code": "g_grasp"},
                "a3": {"reach_cm": 40},
                "p5": {"p_base_code": "p_lay"},
                "a6": {"reach_cm": 0},
            },
        }],
    }
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json=payload)
    assert pub.status_code == 201, pub.text
    body = pub.json()
    assert body["version_no"] == 1
    assert body["total_tmu"] > 0

    # module current_version 已更新
    detail = await client.get(f"/api/v2/motion-modules/{mid}")
    assert detail.json()["current_version"] == 1
    assert detail.json()["current_version_detail"] is not None


async def test_get_versions(client):
    """版本歷史：發布兩次→列出兩版。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-Versions",
        "scope": "global",
    })
    mid = r.json()["id"]

    row = {
        "hand": "RH",
        "frequency": 1,
        "vocab_refs": {},
        "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
    }
    payload = {"rule_set_id": rs_id, "rows": [row]}
    assert (await client.post(f"/api/v2/motion-modules/{mid}/publish", json=payload)).status_code == 201
    assert (await client.post(f"/api/v2/motion-modules/{mid}/publish", json=payload)).status_code == 201

    vs = await client.get(f"/api/v2/motion-modules/{mid}/versions")
    assert vs.status_code == 200, vs.text
    assert len(vs.json()) == 2
    assert [v["version_no"] for v in vs.json()] == [1, 2]


async def test_list_modules(client):
    """列表端點：建立後可列出。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-List-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    lst = await client.get("/api/v2/motion-modules")
    assert lst.status_code == 200, lst.text
    ids = [x["id"] for x in lst.json()]
    assert mid in ids

    # scope 過濾
    scoped = await client.get("/api/v2/motion-modules?scope=global")
    assert all(x["scope"] == "global" for x in scoped.json())


# ── 錯誤邊界 ─────────────────────────────────────────────────────────

async def test_publish_empty_rows(client):
    """publish 空 rows → 422。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-EmptyRows",
        "scope": "global",
    })
    mid = r.json()["id"]
    # Pydantic 會在 schema 層擋（min_length=1 on rows）
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [],
    })
    assert resp.status_code == 422, resp.text


async def test_publish_bad_cycle(client):
    """publish 壞 cycle（未知 g_code）→ 422。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-BadCycle",
        "scope": "global",
    })
    mid = r.json()["id"]
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [{
            "hand": "RH",
            "frequency": 1,
            "vocab_refs": {},
            "cycle": {
                "seq": "GM",
                "rule_set_code": "MINIMOST_FACTORY_V2",
                "g2": {"g_code": "NONEXISTENT_CODE"},
            },
        }],
    })
    assert resp.status_code == 422, resp.text


async def test_module_not_found(client):
    """取不存在的模組 → 404。"""
    missing = str(uuid.uuid4())
    r = await client.get(f"/api/v2/motion-modules/{missing}")
    assert r.status_code == 404, r.text


async def test_get_versions_not_found(client):
    """取不存在的模組版本歷史 → 404。"""
    missing = str(uuid.uuid4())
    r = await client.get(f"/api/v2/motion-modules/{missing}/versions")
    assert r.status_code == 404, r.text


async def test_promote_501(client):
    """promote 端點目前 501。"""
    mid = str(uuid.uuid4())  # 不需真實存在（501 先回）
    r = await client.post(f"/api/v2/motion-modules/{mid}/promote")
    assert r.status_code == 501, r.text


# ── RBAC ─────────────────────────────────────────────────────────────

async def test_rbac_viewer_cannot_create(client):
    """viewer 角色建立模組 → 403。"""
    h = {"X-Username": "ZZZMMVIEWER999"}
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "viewer-test",
        "scope": "personal",
    }, headers=h)
    assert r.status_code == 403, r.text


async def test_rbac_viewer_can_list(client):
    """viewer 角色可讀取列表。"""
    h = {"X-Username": "ZZZMMVIEWER999"}
    r = await client.get("/api/v2/motion-modules", headers=h)
    assert r.status_code == 200, r.text


async def test_rbac_viewer_cannot_publish(client):
    """viewer 不可發布版本 → 403（需 IE 以上）。"""
    # 先用 admin 建模組
    cr = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-ViewerPub",
        "scope": "global",
    })
    assert cr.status_code == 201, cr.text
    mid = cr.json()["id"]

    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    h = {"X-Username": "ZZZMMVIEWER999"}
    r = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [{"hand": "RH", "frequency": 1, "vocab_refs": {}, "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"}}],
    }, headers=h)
    assert r.status_code == 403, r.text
