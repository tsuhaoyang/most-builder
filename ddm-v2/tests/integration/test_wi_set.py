"""wi-set-projects 端點測試（F-02a：伺服器端快照）。

涵蓋：
- 正常流程：建專案 → wi_template_id-only 加條目 → 快照由伺服器回填非零
- 值權威：client 同時給快照值 → 伺服器值覆蓋
- 邊界：template 不存在 → 404；手動條目缺名稱 → 422
- 手動條目（無 template）→ 沿用 client 快照
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _get_rule_set_id(client) -> str | None:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        return None
    return r.json()[0]["id"]


async def _make_project(client) -> str:
    sfx = uuid.uuid4().hex[:8]
    r = await client.post("/api/v2/wi-set-projects", json={
        "project_code": f"UT-WISET-{sfx}",
        "name": f"測試專案-{sfx}",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _make_published_module(client, rs_id: str) -> tuple[str, float, float]:
    """建 module 並發布一版（GM 單列），回 (module_id, total_tmu, total_seconds)。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-WiSet-模組-{sfx}",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
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
    body = pub.json()
    return mid, float(body["total_tmu"]), float(body["total_seconds"])


# ── 正常流程 ─────────────────────────────────────────────────────────

async def test_add_item_template_only_server_snapshot(client):
    """wi_template_id-only 建條目 → 快照被伺服器回填非零。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    pid = await _make_project(client)
    mid, tmu, seconds = await _make_published_module(client, rs_id)

    r = await client.post(f"/api/v2/wi-set-projects/{pid}/items", json={
        "wi_template_id": mid,
    })
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["wi_template_id"] == mid
    assert item["wi_name_snapshot"].startswith("UT-WiSet-模組-")
    assert item["wi_code_snapshot"] is None
    assert item["action_count_snapshot"] == 1
    assert item["total_tmu_snapshot"] == pytest.approx(tmu)
    assert item["total_tmu_snapshot"] > 0
    # 值權威：total_seconds 直接比對引擎 publish 時算好的 version.total_seconds
    assert item["total_seconds_snapshot"] == pytest.approx(seconds)
    assert item["total_seconds_snapshot"] > 0


async def test_add_item_template_overrides_client_snapshot(client):
    """值權威：template 有值時忽略 client 快照，一律伺服器算。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    pid = await _make_project(client)
    mid, tmu, _seconds = await _make_published_module(client, rs_id)

    r = await client.post(f"/api/v2/wi-set-projects/{pid}/items", json={
        "wi_template_id": mid,
        "wi_name_snapshot": "client 竄改名稱",
        "total_tmu_snapshot": 99999.0,
        "total_seconds_snapshot": 99999.0,
        "action_count_snapshot": 42,
    })
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["wi_name_snapshot"] != "client 竄改名稱"
    assert item["total_tmu_snapshot"] == pytest.approx(tmu)
    assert item["action_count_snapshot"] == 1


async def test_add_item_manual_uses_client_snapshot(client):
    """手動條目（無 template）→ 沿用 client 快照。"""
    pid = await _make_project(client)
    r = await client.post(f"/api/v2/wi-set-projects/{pid}/items", json={
        "wi_name_snapshot": "手動 WI",
        "total_tmu_snapshot": 28.0,
        "total_seconds_snapshot": 1.008,
        "action_count_snapshot": 3,
    })
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["wi_name_snapshot"] == "手動 WI"
    assert item["total_tmu_snapshot"] == pytest.approx(28.0)
    assert item["action_count_snapshot"] == 3


# ── 邊界 ─────────────────────────────────────────────────────────────

async def test_add_item_template_not_found(client):
    """wi_template_id 指向不存在的模組 → 404。"""
    pid = await _make_project(client)
    r = await client.post(f"/api/v2/wi-set-projects/{pid}/items", json={
        "wi_template_id": str(uuid.uuid4()),
    })
    assert r.status_code == 404, r.text


async def test_add_item_manual_missing_name_422(client):
    """手動條目缺 wi_name_snapshot → 422。"""
    pid = await _make_project(client)
    r = await client.post(f"/api/v2/wi-set-projects/{pid}/items", json={
        "notes": "沒有名稱",
    })
    assert r.status_code == 422, r.text


async def test_add_item_unpublished_module_zero_snapshot(client):
    """template 尚無發布版本（current_version=0）→ 快照計數/TMU 為 0，名稱仍回填。"""
    pid = await _make_project(client)
    sfx = uuid.uuid4().hex[:6]
    m = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-未發布-{sfx}",
        "scope": "global",
    })
    assert m.status_code == 201, m.text
    r = await client.post(f"/api/v2/wi-set-projects/{pid}/items", json={
        "wi_template_id": m.json()["id"],
    })
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["wi_name_snapshot"] == f"UT-未發布-{sfx}"
    assert item["action_count_snapshot"] == 0
    assert item["total_tmu_snapshot"] == 0
    assert item["total_seconds_snapshot"] == 0


# ── RBAC ─────────────────────────────────────────────────────────────

async def test_rbac_viewer_cannot_add_item(client):
    """viewer 不可加條目 → 403。"""
    pid = await _make_project(client)
    h = {"X-Username": "ZZZWISETVIEWER9"}
    r = await client.post(
        f"/api/v2/wi-set-projects/{pid}/items",
        json={"wi_name_snapshot": "viewer 嘗試"},
        headers=h,
    )
    assert r.status_code == 403, r.text
