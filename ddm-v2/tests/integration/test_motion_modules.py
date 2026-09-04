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
    """**active** 版的 id——不是清單第一筆（CI_GATES 硬性規則 7 第一則）。

    `GET /rule-sets` 是 `ORDER BY created_at`，而 V1／V2 的 `created_at` 實測完全
    相同（見 CI_GATES 雙語敘事那一列），`[0]` 撈到哪一版不確定；本檔的黃金列
    註明是 V2（active 認證版）的值，撈到 V1 就是另一套值表。
    """
    r = await client.get("/api/v2/rule-sets/active")
    if r.status_code != 200:
        return None
    return r.json()["id"]


# ── 正常流程 ─────────────────────────────────────────────────────────

async def test_create_and_get_module(client):
    """建立 draft 模組，取得詳情。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"測試模組-{sfx}",
        "category": "action",
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
        "category": "action",
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
        "category": "action",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # publish：GM A10 B0 G6 A16 B0 P6 A0 = 38 TMU（全認證代碼；P=p_place_none 放無方向）
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
                "p5": {"p_base_code": "p_place_none"},
                "a6": {"reach_cm": 0},
            },
        }],
    }
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json=payload)
    assert pub.status_code == 201, pub.text
    body = pub.json()
    assert body["version_no"] == 1
    assert float(body["total_tmu"]) == 38.0, body

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
        "category": "action",
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
        "category": "action",
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
        "category": "action",
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
        "category": "action",
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
        "category": "action",
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
        "category": "action",
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
        "category": "action",
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
        "category": "action",
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
        "roles": ["analyst"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text

    h = {"X-Username": ie_user}
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-IE-Global-Attempt",
        "category": "action",
        "scope": "global",
    }, headers=h)
    assert r.status_code == 403, r.text

    # site scope 也應被擋
    r2 = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-IE-Site-Attempt",
        "category": "action",
        "scope": "site",
    }, headers=h)
    assert r2.status_code == 403, r2.text

    # personal scope 仍可建
    r3 = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-IE-Personal-OK",
        "category": "action",
        "scope": "personal",
    }, headers=h)
    assert r3.status_code == 201, r3.text


async def test_sm3_manager_can_create_site_module(client):
    """SM-3：manager 角色可建立 scope=site 模組 → 201。"""
    mgr_user = "SMTEST_MGR_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": mgr_user,
        "display_name": "SM3 Manager",
        "roles": ["approver"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text

    h = {"X-Username": mgr_user}
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM3-MGR-Site-OK",
        "category": "action",
        "scope": "site",
    }, headers=h)
    assert r.status_code == 201, r.text


async def test_sm4_update_cannot_change_owner(client):
    """SM-4：PUT update 忽略 owner 欄位（不允許重新指派）。"""
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "SM4-OwnerTest",
        "category": "action",
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
        "category": "action",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # IE 用戶（非 owner）嘗試發布 → 403
    ie_user = "SMTEST_IE_ONLY_002"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "SM5 IE",
        "roles": ["analyst"],
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
        "category": "action",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert r.json()["current_version"] == 0

    # apply-back 建立 version 1（GM A10 B0 G6 A16 B0 P6 A0 = 38 TMU）
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
            "p5": {"p_base_code": "p_place_none"},
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
    assert float(body["total_tmu"]) == 38.0, body

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
        "category": "action",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    ie_user = "SMTEST_IE_ONLY_003"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "SM7 IE",
        "roles": ["analyst"],
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


async def _set_module_status(db_session, module_id: str, status: str) -> None:
    """直接透過 SQLAlchemy 更新 module.status（測試用，繞過無 API 的 standard/retired 轉換）。

    用 conftest 的 db_session（與 client 同 connection/transaction）——
    不得自建 engine 打 DATABASE_URL，否則繞過隔離、汙染真實 DB。
    """
    import uuid as _uuid

    from ddm_v2.models.v2.motion_module import MotionModule

    m = await db_session.get(MotionModule, _uuid.UUID(module_id))
    assert m is not None, f"module {module_id} 應存在（同 transaction 內建立）"
    m.status = status
    await db_session.commit()


def _gm_row_pub(*, vocab_refs: dict | None = None) -> dict:
    """完整 publish-ready GM row（V2 rule-set；a0/g2/a3/p5/a6 全填）。

    引擎實算：A10 B0 G6 A16 B0 P6 A0 = 38 TMU（P=p_place_none 放無方向，認證代碼）。
    """
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
            "p5": {"p_base_code": "p_place_none"},
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

async def test_update_non_draft_rejected(client, db_session):
    """T-4：status=standard 的模組不可改 metadata → 409；detail 欄位存在。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-T4-NonDraft-{sfx}",
        "category": "action",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # 模擬 promote（promote API 尚 501）：直接透過 DB 升為 standard
    await _set_module_status(db_session, mid, "standard")

    up = await client.put(f"/api/v2/motion-modules/{mid}", json={"name_zh": "should-be-rejected"})
    assert up.status_code == 409, up.text
    assert "error" in up.json()


# ── T-1：DELETE 系列 ─────────────────────────────────────────────────────────

async def test_delete_draft_module_success(client):
    """T-1a：DELETE draft 模組 → 204；再 GET → 404。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Del-Draft-{sfx}",
        "category": "action",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    d = await client.delete(f"/api/v2/motion-modules/{mid}")
    assert d.status_code == 204, d.text

    gone = await client.get(f"/api/v2/motion-modules/{mid}")
    assert gone.status_code == 404


async def test_delete_standard_module_rejected(client, db_session):
    """T-1b：DELETE status=standard 的模組 → 409；detail 欄位存在。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Del-Std-{sfx}",
        "category": "action",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    await _set_module_status(db_session, mid, "standard")

    d = await client.delete(f"/api/v2/motion-modules/{mid}")
    assert d.status_code == 409, d.text
    assert "error" in d.json()


async def test_delete_other_personal_module_blocked(client):
    """T-1c：IE 用戶刪他人的 personal 模組 → 403（ownership guard）。"""
    sfx = uuid.uuid4().hex[:6]
    # admin（IEC141289）建立 personal 模組，owner = IEC141289
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Del-Other-{sfx}",
        "category": "action",
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
        "roles": ["analyst"],
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
        "category": "action",
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
        "category": "action",
        "scope": "personal",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    ie_user = f"SMTEST_IE_CLN_{sfx}"
    await client.post("/api/v2/admin/users", json={
        "employee_no": ie_user,
        "display_name": "T2b IE Clone",
        "roles": ["analyst"],
        "site_ids": [],
    })

    c = await client.post(
        f"/api/v2/motion-modules/{mid}/clone",
        headers={"X-Username": ie_user},
    )
    assert c.status_code == 404, c.text
    assert "error" in c.json()


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
        "category": "action",
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


async def test_instantiate_module_without_object_vocab_keeps_row(client):
    """object vocab 是敘述 metadata；省略時仍須完整實體化，不可靜默跳列。"""
    ws_id = await _clone_demo_ws(client)
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    suffix = uuid.uuid4().hex[:6]
    module = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Inst-NoObject-{suffix}",
        "category": "wi-template",
        "scope": "global",
    })
    assert module.status_code == 201, module.text
    module_id = module.json()["id"]
    published = await client.post(f"/api/v2/motion-modules/{module_id}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_pub(vocab_refs={})],
    })
    assert published.status_code == 201, published.text

    instantiated = await client.post(
        f"/api/v2/worksheets/{ws_id}/rows/from-module",
        json={"module_id": module_id},
    )
    assert instantiated.status_code == 201, instantiated.text
    assert len(instantiated.json()["new_rows"]) == 1
    assert instantiated.json()["skipped_vocab_missing"] == 0

    worksheet = await client.get(f"/api/v2/worksheets/{ws_id}")
    imported = next(
        row for row in worksheet.json()["rows"]
        if row["source_module_id"] == module_id
    )
    assert imported["object_vocab_id"] is None


async def test_instantiate_retired_module_rejected(client, db_session):
    """T-3b：retired 模組不可實體化 → 409；detail 欄位存在。"""
    ws_id = await _clone_demo_ws(client)
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Inst-Ret-{sfx}",
        "category": "action",
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
    await _set_module_status(db_session, mid, "retired")

    inst = await client.post(
        f"/api/v2/worksheets/{ws_id}/rows/from-module",
        json={"module_id": mid},
    )
    assert inst.status_code == 409, inst.text
    assert "error" in inst.json()


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
        "category": "action",
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
        "roles": ["analyst"],
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
        "category": "action",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_pub()] * 100,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["version_no"] == 1
    assert float(resp.json()["total_tmu"]) == 3800.0, resp.json()  # 100 列 × 38 TMU


async def test_from_rows_over_limit_rejected(client):
    """T-5b：versions/from-rows 傳 101 列 → 422（schema max_length=100 攔截）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-SM2-FR-{sfx}",
        "category": "action",
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
        "roles": ["analyst"],
        "site_ids": [],
    })

    h = {"X-Username": ie_user}
    # IE 建立自己的 personal 模組（IE 有此權限）
    cr = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-T6-ScopeUpd-{sfx}",
        "category": "action",
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
    assert "error" in up.json()


# ── T-3d：provenance read-back ──────────────────────────────────────────────

@pytest.mark.skip(reason="ADR-019 選定 Option A（讀=viewer+全開），此測試不再適用。若日後切換到 Option C（site scoping），移除此 skip 並實作防護。")
async def test_read_worksheet_idor_blocked_pending_adr():
    """ADR-019 已定案 Option A（讀=viewer+），此測試場景不再成立。日後切 Option C 時移除 skip 並實作對應防護。"""
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
        "category": "action",
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


# ── ADR-019 Option A 迴歸測試 ──────────────────────────────────────────────

async def test_viewer_can_read_any_worksheet(client):
    """ADR-019 Option A: 任何已登入使用者（viewer）可讀 worksheet（讀=viewer+全開）。

    迴歸防護：確保 ADR-019 Option A 決策不被回歸為 Option C（site scoping）或其他存取管控。
    若日後改為 Option C，此測試應與 test_read_worksheet_idor_blocked_pending_adr 一同重構。
    """
    ws_id = await _clone_demo_ws(client)
    # 用非擁有者的 viewer 身份讀取（ZZZMMVIEWER999 為 JIT viewer，與 worksheet 擁有者無關）
    h = {"X-Username": "ZZZMMVIEWER999"}
    r = await client.get(f"/api/v2/worksheets/{ws_id}", headers=h)
    assert r.status_code == 200, r.text


# ── GAP-1 補充：approver gate 負向測試 ───────────────────────────────────────

async def test_promote_analyst_returns_403(client):
    """analyst 身分（level=1）無法 promote；require_role("approver") 守門（role check 先於 501）。

    F-06 RBAC 驗收：promote endpoint 對 analyst 確實回 403，而非 501 或其他碼。
    admin（IEC141289）呼叫同一端點得 501（已由 test_promote_501 覆蓋）。
    """
    analyst_user = "GAPTEST_ANALYST_PROM_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": analyst_user,
        "display_name": "Gap Test Analyst Promote",
        "roles": ["analyst"],
        "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    mid = str(uuid.uuid4())  # 不需真實存在（role check 先於存在性檢查）
    h = {"X-Username": analyst_user}
    r = await client.post(f"/api/v2/motion-modules/{mid}/promote", headers=h)
    assert r.status_code == 403, r.text


# ── F-01：publish 接受 rule_set_code ─────────────────────────────────

async def test_publish_with_rule_set_code(client):
    """publish 以 rule_set_code 指定規則版本 → service 解析成 id。"""
    rs = await client.get("/api/v2/rule-sets/active")  # 不撈清單第一筆（硬性規則 7 第一則）
    if rs.status_code != 200:
        pytest.skip("DB 無 active rule_set，略過")
    rs_code = rs.json()["code"]
    rs_id = rs.json()["id"]

    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-Pub-ByCode",
        "category": "action",
        "scope": "global",
    })
    mid = r.json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_code": rs_code,
        "rows": [{
            "hand": "RH",
            "frequency": 1,
            "vocab_refs": {},
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
        }],
    })
    assert pub.status_code == 201, pub.text
    assert pub.json()["rule_set_id"] == rs_id  # code 已解析為 id


async def test_publish_with_unknown_rule_set_code_404(client):
    """publish 以不存在的 rule_set_code → 404。"""
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-Pub-BadCode",
        "category": "action",
        "scope": "global",
    })
    mid = r.json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_code": "NO_SUCH_RULE_SET",
        "rows": [{
            "hand": "RH",
            "frequency": 1,
            "vocab_refs": {},
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
        }],
    })
    assert pub.status_code == 404, pub.text


async def test_publish_with_both_id_and_code_422(client):
    """rule_set_id 與 rule_set_code 同時給 → 422（恰好擇一）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": "UT-Pub-Both",
        "category": "action",
        "scope": "global",
    })
    mid = r.json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rule_set_code": "MINIMOST_FACTORY_V2",
        "rows": [{
            "hand": "RH",
            "frequency": 1,
            "vocab_refs": {},
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
        }],
    })
    assert pub.status_code == 422, pub.text


# ── F-02b：list status 過濾 + 輕量摘要欄 ─────────────────────────────

async def test_list_status_filter_and_summary_fields(client):
    """list 支援 ?status= 過濾；有版本的模組回填 total_tmu / action_count。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-Summary-{sfx}",
        "category": "action",
        "scope": "global",
    })
    mid = r.json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
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
                "p5": {"p_base_code": "p_place_single"},
                "a6": {"reach_cm": 0},
            },
        }],
    })
    assert pub.status_code == 201, pub.text
    expected_tmu = float(pub.json()["total_tmu"])

    # status 過濾：draft 應包含此模組
    lst = await client.get("/api/v2/motion-modules?status=draft")
    assert lst.status_code == 200, lst.text
    assert all(x["status"] == "draft" for x in lst.json())
    target = next((x for x in lst.json() if x["id"] == mid), None)
    assert target is not None
    # 輕量摘要欄回填
    assert target["total_tmu"] == pytest.approx(expected_tmu)
    assert target["action_count"] == 1
    # ADR-022 E-2：base_tmu / frequency 摘要欄（rows[0].computed.total_tmu / rows[0].frequency）
    assert target["base_tmu"] == pytest.approx(expected_tmu)
    assert target["frequency"] == pytest.approx(1.0)
    # list 不帶完整版本內容（輕量）
    assert target["current_version_detail"] is None

    # status 過濾：retired 不應包含此模組
    lst2 = await client.get("/api/v2/motion-modules?status=retired")
    assert mid not in [x["id"] for x in lst2.json()]

    # detail 端點也回填摘要欄
    detail = await client.get(f"/api/v2/motion-modules/{mid}")
    assert detail.status_code == 200
    assert detail.json()["total_tmu"] == pytest.approx(expected_tmu)
    assert detail.json()["action_count"] == 1
    assert detail.json()["current_version_detail"] is not None


# ═══════════════════════════════════════════════════════════════════════
# SIMO（ADR-020）publish / instantiate 測試
# 對應 SIMO code-review Finding 1（互指靜默歸零）/ 2（零測試）/ 4（口徑一致）
# 注意：cycle 沿用 test_worksheet_v2_engine 的 28 TMU 黃金列（a0=20/a3=25 檔位，非 _gm_row_pub 的 38）
# ═══════════════════════════════════════════════════════════════════════


def _gm_row_simo(*, frequency: float = 1, simo_pair_index: int | None = None,
                 vocab_refs: dict | None = None) -> dict:
    """GM 黃金列（V2 rule-set，28 TMU）：a0=20 + g_grasp + a3=25 + p_place_none。"""
    row = {
        "hand": "RH",
        "frequency": frequency,
        "vocab_refs": vocab_refs or {},
        "cycle": {
            "seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2",
            "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"},
        },
    }
    if simo_pair_index is not None:
        row["simo_pair_index"] = simo_pair_index
    return row


async def _make_simo_module(client, prefix: str) -> str:
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"{prefix}-{sfx}",
        "category": "action",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _assert_simo_pair_invalid(resp) -> None:
    assert resp.status_code == 422, resp.text
    detail = resp.json()["error"]["detail"]
    assert detail["code"] == "SIMO_PAIR_INVALID", detail


async def test_publish_simo_self_reference_422(client):
    """(a) simo_pair_index 自指 → 422 SIMO_PAIR_INVALID。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_simo_module(client, "UT-SIMO-Self")
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_simo(simo_pair_index=0)],
    })
    _assert_simo_pair_invalid(resp)


async def test_publish_simo_out_of_bounds_422(client):
    """(a) simo_pair_index 越界（>= n 與負值）→ 422 SIMO_PAIR_INVALID。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_simo_module(client, "UT-SIMO-OOB")

    # 越界（2 列，index 2 不存在）
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_simo(), _gm_row_simo(simo_pair_index=2)],
    })
    _assert_simo_pair_invalid(resp)

    # 負值
    resp2 = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_simo(), _gm_row_simo(simo_pair_index=-1)],
    })
    _assert_simo_pair_invalid(resp2)


async def test_publish_simo_mutual_pair_422(client):
    """(a) Finding 1：互指配對（A→B 且 B→A）→ 422，不得靜默整組歸零。
    鏈式（A→B、B→C：主列 B 自身又宣告配對）同樣拒收。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_simo_module(client, "UT-SIMO-Mutual")

    # 互指
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_simo(simo_pair_index=1), _gm_row_simo(simo_pair_index=0)],
    })
    _assert_simo_pair_invalid(resp)

    # 鏈式：row0→row1、row1→row2（row1 被指為主列卻又宣告配對）
    resp2 = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [_gm_row_simo(simo_pair_index=1),
                 _gm_row_simo(simo_pair_index=2),
                 _gm_row_simo()],
    })
    _assert_simo_pair_invalid(resp2)


async def test_publish_simo_dependent_excluded_from_total(client):
    """(b) 合法配對：從屬列（含 frequency=2）不入 total → total_tmu == 主列 28。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_simo_module(client, "UT-SIMO-Total")
    resp = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [
            _gm_row_simo(),                                # 主列：28 TMU
            _gm_row_simo(frequency=2, simo_pair_index=0),  # 從屬列：貢獻 0（即使 freq=2）
        ],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert float(body["total_tmu"]) == 28.0, body
    # 版本快照保留 simo_pair_index（instantiate 依此還原標記）
    assert body["rows"][0].get("simo_pair_index") is None
    assert body["rows"][1].get("simo_pair_index") == 0


async def test_instantiate_simo_marks_dependent_and_total(client):
    """(c) instantiate 後：從屬列 simo_group_id 有值、主列 None、
    read_worksheet 總計＝主列全額 28（從屬列貢獻 0）。"""
    ws_id = await _clone_demo_ws(client)
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    # 清空 clone 出的表 → 總計基準為 0，之後可斷言具體數值
    clear = await client.put(f"/api/v2/worksheets/{ws_id}", json={"rows": []})
    assert clear.status_code == 200, clear.text
    assert clear.json()["total_tmu"] == 0

    mid = await _make_simo_module(client, "UT-SIMO-Inst")
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [
            _gm_row_simo(vocab_refs={"object_vocab_id": _OBJ_SEEDED}),                     # 主列
            _gm_row_simo(simo_pair_index=0, vocab_refs={"object_vocab_id": _OBJ_SEEDED}),  # 從屬列
        ],
    })
    assert pub.status_code == 201, pub.text

    inst = await client.post(
        f"/api/v2/worksheets/{ws_id}/rows/from-module",
        json={"module_id": mid},
    )
    assert inst.status_code == 201, inst.text
    new_rows = inst.json()["new_rows"]
    assert len(new_rows) == 2, new_rows
    main_row, dep_row = new_rows[0], new_rows[1]
    assert main_row["simo_group_id"] is None, main_row          # 主列不標記
    assert dep_row["simo_group_id"], dep_row                    # 從屬列標記
    assert float(main_row["total_tmu"]) == 28.0
    assert float(dep_row["total_tmu"]) == 28.0                  # 列自身 TMU 仍為 28（僅不入總計）

    # read_worksheet：標記持久化 + 總計＝主列全額 28
    rd = await client.get(f"/api/v2/worksheets/{ws_id}")
    assert rd.status_code == 200, rd.text
    body = rd.json()
    by_seq = {row["seq_no"]: row for row in body["rows"]}
    assert len(by_seq) == 2
    seqs = sorted(by_seq)
    assert by_seq[seqs[0]]["simo_group_id"] is None             # 主列
    assert by_seq[seqs[1]]["simo_group_id"] == dep_row["simo_group_id"]  # 從屬列
    assert body["total_tmu"] == 28.0


async def test_worksheet_put_mutual_simo_pair_422(client):
    """Finding 1（worksheet 路徑）：simo_with_row_id 互指 → 422 SIMO_PAIR_INVALID。"""
    ws_id = await _clone_demo_ws(client)
    r1_id, r2_id = str(uuid.uuid4()), str(uuid.uuid4())

    def _ws_row(rid: str, seq_no: int, pair_id: str) -> dict:
        return {"id": rid, "seq_no": seq_no, "hand": "RH", "object_vocab_id": _OBJ_SEEDED,
                "frequency": 1, "simo_with_row_id": pair_id,
                "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2",
                          "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                          "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
                "level": {"ascription": "main", "level": "1"}}

    r = await client.put(f"/api/v2/worksheets/{ws_id}", json={
        "rows": [_ws_row(r1_id, 1, r2_id), _ws_row(r2_id, 2, r1_id)],
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "SIMO_PAIR_INVALID"


async def test_list_summary_none_for_unpublished(client):
    """尚無發布版本的模組：total_tmu / action_count 為 None。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-NoVer-{sfx}",
        "category": "action",
        "scope": "global",
    })
    mid = r.json()["id"]
    lst = await client.get("/api/v2/motion-modules?status=draft")
    target = next((x for x in lst.json() if x["id"] == mid), None)
    assert target is not None
    assert target["total_tmu"] is None
    assert target["action_count"] is None
    assert target["base_tmu"] is None
    assert target["frequency"] is None
