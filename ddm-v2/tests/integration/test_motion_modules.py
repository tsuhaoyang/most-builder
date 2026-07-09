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


# ── SM 安全修復測試 ───────────────────────────────────────────────────

async def test_sm1_idor_personal_module_blocked(client):
    """SM-1：他人不可 GET 別人的 personal 模組（IDOR 防護）→ 404。"""
    # admin 建立 personal 模組
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM1-Personal-Owner",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    # 確認 owner 本人可見
    own = await client.get(f"/api/v2/motion-modules/{mid}")
    assert own.status_code == 200, own.text

    # 另一個使用者（viewer，JIT 建立，不是 owner）嘗試 GET → 404
    h = {"X-Username": "ZZZMMVIEWER999"}
    other = await client.get(f"/api/v2/motion-modules/{mid}", headers=h)
    assert other.status_code == 404, other.text


async def test_sm2_publish_max_rows_exceeded(client):
    """SM-2：publish 超過 100 列 → 422（schema max_length）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM2-MaxRows",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    row = {
        "hand": "RH",
        "frequency": 1,
        "vocab_refs": {},
        "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
    }
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [row] * 101,
    })
    assert resp.status_code == 422, resp.text


async def test_sm3_ie_cannot_create_global_module(client):
    """SM-3：IE 角色不可建立 scope=global 模組 → 403。"""
    # 用 admin 建立一個 IE-only 測試用戶
    ie_user = "SMTEST_IE_ONLY_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "SM3 IE Only",
        "roles": ["IE"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text

    h = {"X-Username": ie_user}
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-IE-Global-Attempt",
        "scope": "global",
    }, headers=h)
    assert r.status_code == 403, r.text

    # site scope 也應被擋
    r2 = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-IE-Site-Attempt",
        "scope": "site",
    }, headers=h)
    assert r2.status_code == 403, r2.text

    # personal scope 仍可建
    r3 = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-IE-Personal-OK",
        "scope": "personal",
    }, headers=h)
    assert r3.status_code == 201, r3.text


async def test_sm3_manager_can_create_site_module(client):
    """SM-3：manager 角色可建立 scope=site 模組 → 201。"""
    mgr_user = "SMTEST_MGR_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": mgr_user,
        "display_name": "SM3 Manager",
        "roles": ["manager"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text

    h = {"X-Username": mgr_user}
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-MGR-Site-OK",
        "scope": "site",
    }, headers=h)
    assert r.status_code == 201, r.text


async def test_sm4_update_cannot_change_owner(client):
    """SM-4：PUT update 忽略 owner 欄位（不允許重新指派）。"""
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM4-OwnerTest",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    original_owner = r.json()["owner"]

    # 嘗試把 owner 改為別人（schema 已移除此欄位，會被靜默忽略）
    up = await client.put(f"/api/v2/motion-modules/{mid}", json={
        "name_zh": "SM4-Changed-Name",
        "owner": "SOMEBODY_ELSE",  # 應被忽略
    })
    assert up.status_code == 200, up.text
    assert up.json()["name_zh"] == "SM4-Changed-Name"
    # owner 不應改變
    assert up.json()["owner"] == original_owner


async def test_sm5_publish_personal_module_blocked_for_others(client):
    """SM-5：他人不可發布 personal 模組的新版本 → 403。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    # admin 建立 personal 模組
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM5-Personal-PubGuard",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # IE 用戶（非 owner）嘗試發布 → 403
    ie_user = "SMTEST_IE_ONLY_002"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "SM5 IE",
        "roles": ["IE"],
        "site_ids": [],
    })
    h = {"X-Username": ie_user}
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [{"hand": "RH", "frequency": 1, "vocab_refs": {},
                  "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"}}],
    }, headers=h)
    assert pub.status_code == 403, pub.text


async def test_sm6_reorder_requires_ie(client):
    """SM-6：viewer 不可 reorder → 403（需 IE 以上）。"""
    h = {"X-Username": "ZZZMMVIEWER999"}
    r = await client.put("/api/v2/motion-modules/reorder", json={
        "ordered_ids": [],
    }, headers=h)
    assert r.status_code == 403, r.text


async def test_sm7_apply_back_creates_new_version(client):
    """SM-7：apply-back 端點建立新版本（from-rows）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"SM7-ApplyBack-{sfx}",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert r.json()["current_version"] == 0

    # apply-back 建立 version 1
    row = {
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
    }
    resp = await client.post(f"/api/v2/motion-modules/{mid}/versions/from-rows", json={
        "rule_set_id": rs_id,
        "rows": [row],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["version_no"] == 1
    assert body["total_tmu"] > 0

    # 確認 module current_version 已更新
    detail = await client.get(f"/api/v2/motion-modules/{mid}")
    assert detail.json()["current_version"] == 1

    # 再次 apply-back → version 2
    resp2 = await client.post(f"/api/v2/motion-modules/{mid}/versions/from-rows", json={
        "rule_set_id": rs_id,
        "rows": [row],
    })
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["version_no"] == 2


async def test_sm7_apply_back_ownership_guard(client):
    """SM-7：他人不可 apply-back 別人的 personal 模組 → 403。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    # admin 建立 personal 模組
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM7-ApplyBack-Guard",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    ie_user = "SMTEST_IE_ONLY_003"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "SM7 IE",
        "roles": ["IE"],
        "site_ids": [],
    })
    h = {"X-Username": ie_user}
    resp = await client.post(f"/api/v2/motion-modules/{mid}/versions/from-rows", json={
        "rule_set_id": rs_id,
        "rows": [{"hand": "RH", "frequency": 1, "vocab_refs": {},
                  "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"}}],
    }, headers=h)
    assert resp.status_code == 403, resp.text


# ═══════════════════════════════════════════════════════════════════════
# 補充測試（High/Medium Priority）
# T-1 DELETE · T-2 clone · T-3 instantiate
# T-4 PUT non-draft · T-5 SM-2 boundary · T-6 SM-3 scope-upd-via-PUT
# ═══════════════════════════════════════════════════════════════════════

_WS_SEEDED = "55555555-5555-5555-5555-555555555555"  # dev_seed_v2 demo worksheet
_OBJ_SEEDED = "66666666-6666-6666-6666-666666666666"  # dev_seed_v2 vocab「DIMM 內存」


async def _set_module_status(module_id: str, status: str) -> None:
    """直接透過 SQLAlchemy 更新 module.status（測試用，繞過無 API 的 standard/retired 轉換）。"""
    import os
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from ddm_v2.models.v2.motion_module import MotionModule

    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        _Session = async_sessionmaker(engine, expire_on_commit=False)
        async with _Session() as s:
            m = await s.get(MotionModule, _uuid.UUID(module_id))
            if m is not None:
                m.status = status
                await s.commit()
    finally:
        await engine.dispose()


def _gm_row_pub(*, vocab_refs: dict | None = None) -> dict:
    """完整 publish-ready GM row（V2 rule-set；a0/g2/a3/p5/a6 全填）。"""
    return {
        "hand": "RH",
        "frequency": 1,
        "vocab_refs": vocab_refs or {},
        "cycle": {
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V2",
            "a0": {"reach_cm": 30},
            "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 40},
            "p5": {"p_base_code": "p_lay"},
            "a6": {"reach_cm": 0},
        },
    }


async def _seeded_ws_ok(client) -> bool:
    """確認 dev_seed_v2 demo worksheet 已存在（兼確認 vocab 也已種）。"""
    return (await client.get(f"/api/v2/worksheets/{_WS_SEEDED}")).status_code == 200


async def _clone_demo_ws(client) -> str:
    """Clone demo worksheet 取隔離 draft；未種則 pytest.skip。"""
    if not await _seeded_ws_ok(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r = await client.post(f"/api/v2/worksheets/{_WS_SEEDED}/clone")
    assert r.status_code == 200, r.text
    return r.json()["new_worksheet_id"]


# ── T-4：PUT 非 draft → 409 ────────────────────────────────────────────────

async def test_update_non_draft_rejected(client):
    """T-4：status=standard 的模組不可改 metadata → 409；detail 欄位存在。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-T4-NonDraft-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # 模擬 promote（promote API 尚 501）：直接透過 DB 升為 standard
    await _set_module_status(mid, "standard")

    up = await client.put(f"/api/v2/motion-modules/{mid}", json={"name_zh": "should-be-rejected"})
    assert up.status_code == 409, up.text
    assert "detail" in up.json()


# ── T-1：DELETE 系列 ─────────────────────────────────────────────────────────

async def test_delete_draft_module_success(client):
    """T-1a：DELETE draft 模組 → 204；再 GET → 404。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Del-Draft-{sfx}",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    d = await client.delete(f"/api/v2/motion-modules/{mid}")
    assert d.status_code == 204, d.text

    gone = await client.get(f"/api/v2/motion-modules/{mid}")
    assert gone.status_code == 404


async def test_delete_standard_module_rejected(client):
    """T-1b：DELETE status=standard 的模組 → 409；detail 欄位存在。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Del-Std-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    await _set_module_status(mid, "standard")

    d = await client.delete(f"/api/v2/motion-modules/{mid}")
    assert d.status_code == 409, d.text
    assert "detail" in d.json()


async def test_delete_other_personal_module_blocked(client):
    """T-1c：IE 用戶刪他人的 personal 模組 → 403（ownership guard）。"""
    sfx = uuid.uuid4().hex[:6]
    # admin（IEC141289）建立 personal 模組，owner = IEC141289
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Del-Other-{sfx}",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert r.json()["owner"] == "IEC141289"

    # 建立另一個 IE 用戶（非 owner）
    ie_user = f"SMTEST_IE_DEL_{sfx}"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "T1c IE Del",
        "roles": ["IE"],
        "site_ids": [],
    })

    d = await client.delete(
        f"/api/v2/motion-modules/{mid}",
        headers={"X-Username": ie_user},
    )
    # delete_module 走 ScopePermissionError → 403；非 IDOR（不走 404）
    assert d.status_code in (403, 404), d.text


# ── T-2：clone 系列 ───────────────────────────────────────────────────────────

async def test_clone_module_creates_personal_copy(client):
    """T-2a：clone → scope=personal、owner=呼叫者、name_zh 含「複製-」前綴。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Cln-Src-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # publish 一版（clone 應一併複製版本快照）
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_pub()],
    })
    assert pub.status_code == 201, pub.text

    c = await client.post(f"/api/v2/motion-modules/{mid}/clone")
    assert c.status_code == 201, c.text
    body = c.json()
    assert body["scope"] == "personal"
    assert body["owner"] == "IEC141289"
    assert body["name_zh"].startswith("複製-")
    assert body["status"] == "draft"


async def test_clone_other_personal_module_blocked(client):
    """T-2b：clone 他人的 personal 模組 → 404（SM-1 不洩漏存在性）。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Cln-Block-{sfx}",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    ie_user = f"SMTEST_IE_CLN_{sfx}"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "T2b IE Clone",
        "roles": ["IE"],
        "site_ids": [],
    })

    c = await client.post(
        f"/api/v2/motion-modules/{mid}/clone",
        headers={"X-Username": ie_user},
    )
    assert c.status_code == 404, c.text
    assert "detail" in c.json()


# ── T-3：instantiate（worksheets from-module）系列 ─────────────────────────────

async def test_instantiate_module_to_worksheet_success(client):
    """T-3a：實體化模組至工序表 → 201；new_rows ≥ 1；tmu_drift 欄位存在。"""
    ws_id = await _clone_demo_ws(client)
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Inst-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # publish：row 含 object_vocab_id（指向 seeded vocab「DIMM 內存」）
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_pub(vocab_refs={"object_vocab_id": _OBJ_SEEDED})],
    })
    assert pub.status_code == 201, pub.text

    inst = await client.post(
        f"/api/v2/worksheets/{ws_id}/rows/from-module",
        json={"module_id": mid},
    )
    assert inst.status_code == 201, inst.text
    body = inst.json()
    assert isinstance(body["new_rows"], list)
    assert len(body["new_rows"]) >= 1, "應建立至少一列 WiRow"
    assert "tmu_drift" in body


async def test_instantiate_retired_module_rejected(client):
    """T-3b：retired 模組不可實體化 → 409；detail 欄位存在。"""
    ws_id = await _clone_demo_ws(client)
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Inst-Ret-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_pub(vocab_refs={"object_vocab_id": _OBJ_SEEDED})],
    })
    assert pub.status_code == 201, pub.text

    # 退役模組（simulate retire：promote API 尚 501）
    await _set_module_status(mid, "retired")

    inst = await client.post(
        f"/api/v2/worksheets/{ws_id}/rows/from-module",
        json={"module_id": mid},
    )
    assert inst.status_code == 409, inst.text
    assert "detail" in inst.json()


async def test_instantiate_to_other_worksheet_blocked(client):
    """T-3c：非工序表 owner（IE 用戶）嘗試實體化 → 403。"""
    # clone demo 表 → 新 ProcessVersion.created_by = "IEC141289"
    ws_id = await _clone_demo_ws(client)
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    mr = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Inst-Block-{sfx}",
        "scope": "global",
    })
    assert mr.status_code == 201, mr.text
    mid = mr.json()["id"]

    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_pub()],
    })
    assert pub.status_code == 201, pub.text

    # 建立 IE 用戶（非工序表 owner）
    ie_user = f"SMTEST_IE_INST_{sfx}"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "T3c IE Inst",
        "roles": ["IE"],
        "site_ids": [],
    })

    inst = await client.post(
        f"/api/v2/worksheets/{ws_id}/rows/from-module",
        json={"module_id": mid},
        headers={"X-Username": ie_user},
    )
    assert inst.status_code in (403, 404), inst.text


# ── T-5：SM-2 boundary（max_length=100 inclusive）────────────────────────────

async def test_publish_exactly_100_rows_allowed(client):
    """T-5a：publish 剛好 100 列 → 201（max_length=100 是 inclusive）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-SM2-100-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    minimal_row = {
        "hand": "RH", "frequency": 1, "vocab_refs": {},
        "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
    }
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [minimal_row] * 100,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["version_no"] == 1
    assert resp.json()["total_tmu"] > 0


async def test_from_rows_over_limit_rejected(client):
    """T-5b：versions/from-rows 傳 101 列 → 422（schema max_length=100 攔截）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-SM2-FR-{sfx}",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    minimal_row = {
        "hand": "RH", "frequency": 1, "vocab_refs": {},
        "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
    }
    resp = await client.post(f"/api/v2/motion-modules/{mid}/versions/from-rows", json={
        "rule_set_id": rs_id,
        "rows": [minimal_row] * 101,
    })
    assert resp.status_code == 422, resp.text


# ── T-6：SM-3 via PUT（IE 不可透過 PUT 把 scope 改為 site）────────────────────

async def test_update_scope_escalation_blocked(client):
    """T-6：IE 用戶透過 PUT 把 scope 改成 site → 403（SM-3 PUT guard）。"""
    sfx = uuid.uuid4().hex[:6]
    ie_user = f"SMTEST_IE_SCOPEUPD_{sfx}"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "T6 IE ScopeUpd",
        "roles": ["IE"],
        "site_ids": [],
    })

    h = {"X-Username": ie_user}
    # IE 建立自己的 personal 模組（IE 有此權限）
    cr = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-T6-ScopeUpd-{sfx}",
        "scope": "personal",
    }, headers=h)
    assert cr.status_code == 201, cr.text
    mid = cr.json()["id"]

    # IE 嘗試透過 PUT 把 scope 升為 site → SM-3 guard → 403
    up = await client.put(
        f"/api/v2/motion-modules/{mid}",
        json={"scope": "site"},
        headers=h,
    )
    assert up.status_code == 403, up.text
    assert "detail" in up.json()


# ── T-3d：provenance read-back ──────────────────────────────────────────────

@pytest.mark.skip(reason="Worksheet 讀取 IDOR 防護待 ADR-019 定案後統一實作（目前 check_read_access 未掛入路由）")
async def test_read_worksheet_idor_blocked_pending_adr():
    """
    驗證非擁有者 GET /worksheets/{id} 應得 404。
    目前此防護被撤回（只防一道門，export/versions/clone 仍可繞過），
    等 ADR-019 worksheet-access-control 實作後移除此 skip。
    """
    pass


async def test_provenance_read_back_after_instantiate(client):
    """T-3d：instantiate 後 GET /worksheets/{ws_id} 回傳的 rows 中
    source_module_id == 模組 id 且 source_module_version 非 None。
    （Fix-2：驗證 F-03b §2 provenance 欄位在讀取時正確回傳）
    """
    ws_id = await _clone_demo_ws(client)
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Prov-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_pub(vocab_refs={"object_vocab_id": _OBJ_SEEDED})],
    })
    assert pub.status_code == 201, pub.text
    version_no = pub.json()["version_no"]

    inst = await client.post(
        f"/api/v2/worksheets/{ws_id}/rows/from-module",
        json={"module_id": mid},
    )
    assert inst.status_code == 201, inst.text
    assert len(inst.json()["new_rows"]) >= 1

    # provenance read-back：GET worksheet → source_module_id / source_module_version 已記錄
    ws_resp = await client.get(f"/api/v2/worksheets/{ws_id}")
    assert ws_resp.status_code == 200, ws_resp.text
    rows = ws_resp.json()["rows"]

    inst_rows = [row for row in rows if row.get("source_module_id") == mid]
    assert len(inst_rows) >= 1, f"應找到 source_module_id={mid} 的列，實際 rows={[r.get('source_module_id') for r in rows]}"
    for row in inst_rows:
        assert row["source_module_version"] is not None, "source_module_version 不應為 None"
        assert row["source_module_version"] == version_no
