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
    """**active** 版的 id——不是清單第一筆（CI_GATES 硬性規則 7 第一則）。

    `GET /rule-sets` 是 `ORDER BY created_at`，而 V1／V2 的 `created_at` 實測完全
    相同（見 CI_GATES 雙語敘事那一列），`[0]` 撈到哪一版不確定；本檔的黃金列
    註明是 V2（active 認證版）的值，撈到 V1 就是另一套值表。
    """
    r = await client.get("/api/v2/rule-sets/active")
    if r.status_code != 200:
        return None
    return r.json()["id"]


async def _make_project(client) -> str:
    sfx = uuid.uuid4().hex[:8]
    r = await client.post("/api/v2/wi-set-projects", json={
        "project_code": f"UT-WISET-{sfx}",
        "name": f"測試專案-{sfx}",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _make_published_module(
    client, rs_id: str, object_vocab_id: str | None = None
) -> tuple[str, float, float]:
    """建 module 並發布一版（GM 單列），回 (module_id, total_tmu, total_seconds)。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-WiSet-模組-{sfx}",
        "category": "wi-template",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id,
        "rows": [{
            "hand": "RH",
            "frequency": 1,
            "vocab_refs": {"object_vocab_id": object_vocab_id} if object_vocab_id else {},
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
        "category": "wi-template",
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


async def test_instantiate_project_creates_case_with_preview_rows(client):
    """WI 專案 → 分析案件 → WI 預覽共用同一份 worksheet rows。"""
    site = (await client.get("/api/v2/sites")).json()
    if not site:
        pytest.skip("無 site（先跑 dev_seed_v2.py）")
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    suffix = uuid.uuid4().hex[:8]
    product = await client.post("/api/v2/products", json={
        "site_id": site[0]["id"],
        "name_zh": f"UT WI Set 產品 {suffix}",
        "external_code": f"UT-WISET-{suffix}",
    })
    assert product.status_code == 201, product.text
    sku = await client.post("/api/v2/skus", json={
        "product_id": product.json()["id"],
        "sku_code": f"UT-WISET-{suffix}",
    })
    assert sku.status_code == 201, sku.text
    vocab = await client.post("/api/v2/vocab", json={
        "kind": "object",
        "name_zh": f"UT WI Set 物件 {suffix}",
    })
    assert vocab.status_code == 201, vocab.text

    project_id = await _make_project(client)
    module_id, _tmu, _seconds = await _make_published_module(
        client, rs_id, vocab.json()["id"]
    )
    added = await client.post(f"/api/v2/wi-set-projects/{project_id}/items", json={
        "wi_template_id": module_id,
    })
    assert added.status_code == 201, added.text

    created = await client.post(
        f"/api/v2/wi-set-projects/{project_id}/instantiate",
        json={"sku_id": sku.json()["id"], "model_label": f"LINE-{suffix}"},
    )
    assert created.status_code == 201, created.text
    result = created.json()
    assert result["imported_wi_count"] == 1
    assert result["imported_row_count"] == 1

    cases = await client.get("/api/v2/cases")
    assert cases.status_code == 200, cases.text
    assert any(item["worksheet_id"] == result["worksheet_id"] for item in cases.json()["items"])

    preview = await client.get(
        f"/api/v2/worksheets/{result['worksheet_id']}/export/wi-preview"
    )
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["rows"]) == 1
    assert preview.json()["total_tmu"] > 0


async def test_instantiate_project_with_multiple_wis(client):
    """專案含 ≥2 筆 WI（本功能存在的理由）：實體化迴圈必須跑完每一圈。

    P0 迴歸：實體化用 raw SQL bump revision，若 bump 清掉整個 session 快取，
    第 2 圈存取 `item` 就是 async lazy load → MissingGreenlet → 500。
    """
    site = (await client.get("/api/v2/sites")).json()
    if not site:
        pytest.skip("無 site（先跑 dev_seed_v2.py）")
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    suffix = uuid.uuid4().hex[:8]
    product = await client.post("/api/v2/products", json={
        "site_id": site[0]["id"],
        "name_zh": f"UT WI Set 多筆產品 {suffix}",
        "external_code": f"UT-WISET-M-{suffix}",
    })
    assert product.status_code == 201, product.text
    sku = await client.post("/api/v2/skus", json={
        "product_id": product.json()["id"],
        "sku_code": f"UT-WISET-M-{suffix}",
    })
    assert sku.status_code == 201, sku.text

    project_id = await _make_project(client)
    tmus = []
    for _ in range(3):
        module_id, tmu, _seconds = await _make_published_module(client, rs_id)
        added = await client.post(f"/api/v2/wi-set-projects/{project_id}/items", json={
            "wi_template_id": module_id,
        })
        assert added.status_code == 201, added.text
        tmus.append(tmu)

    created = await client.post(
        f"/api/v2/wi-set-projects/{project_id}/instantiate",
        json={"sku_id": sku.json()["id"], "model_label": f"MULTI-{suffix}"},
    )
    assert created.status_code == 201, created.text
    result = created.json()
    assert result["imported_wi_count"] == 3
    assert result["imported_row_count"] == 3

    worksheet_id = result["worksheet_id"]
    preview = await client.get(f"/api/v2/worksheets/{worksheet_id}/export/wi-preview")
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["rows"]) == 3

    # 每個 WI 各自 bump 一次 → 新建的 worksheet（revision 1）跑完 3 圈應為 4，
    # 且回傳的 revision_no 必須是 DB 真值（stale 快取會讓 client 拿到舊值 → 之後永遠 409）。
    read = await client.get(f"/api/v2/worksheets/{worksheet_id}")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["revision_no"] == 4
    assert [r["seq_no"] for r in body["rows"]] == [1, 2, 3]
    assert body["total_tmu"] == pytest.approx(sum(tmus))


async def test_instantiate_empty_project_does_not_create_worksheet(client):
    """不可轉換的專案要在建立 worksheet 前失敗，避免分析案件留下空殼。"""
    products = (await client.get("/api/v2/products")).json()
    if not products:
        pytest.skip("無 product（先跑 dev_seed_v2.py）")
    skus = (await client.get(f"/api/v2/skus?product_id={products[0]['id']}")).json()
    if not skus:
        pytest.skip("無 SKU（先跑 dev_seed_v2.py）")

    project_id = await _make_project(client)
    before = (await client.get(f"/api/v2/skus/{skus[0]['id']}/worksheets")).json()
    response = await client.post(
        f"/api/v2/wi-set-projects/{project_id}/instantiate",
        json={"sku_id": skus[0]["id"]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "EMPTY_PROJECT"
    after = (await client.get(f"/api/v2/skus/{skus[0]['id']}/worksheets")).json()
    assert len(after) == len(before)


async def test_instantiate_runtime_failure_rolls_back_worksheet_and_prior_rows(client):
    """第 2 筆 WI 實體化失敗時，worksheet 與第 1 筆已 flush 的 rows 必須整筆 rollback。"""
    products = (await client.get("/api/v2/products")).json()
    if not products:
        pytest.skip("無 product（先跑 dev_seed_v2.py）")
    skus = (await client.get(f"/api/v2/skus?product_id={products[0]['id']}")).json()
    if not skus:
        pytest.skip("無 SKU（先跑 dev_seed_v2.py）")
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")

    project_id = await _make_project(client)
    valid_module_id, _tmu, _seconds = await _make_published_module(client, rs_id)
    invalid_module_id, _tmu, _seconds = await _make_published_module(
        client, rs_id, "not-a-uuid"
    )
    for module_id in (valid_module_id, invalid_module_id):
        added = await client.post(
            f"/api/v2/wi-set-projects/{project_id}/items",
            json={"wi_template_id": module_id},
        )
        assert added.status_code == 201, added.text

    sku_id = skus[0]["id"]
    before = (await client.get(f"/api/v2/skus/{sku_id}/worksheets")).json()
    response = await client.post(
        f"/api/v2/wi-set-projects/{project_id}/instantiate",
        json={"sku_id": sku_id, "model_label": "ROLLBACK-MID-LOOP"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VOCAB_REF_INVALID"

    after = (await client.get(f"/api/v2/skus/{sku_id}/worksheets")).json()
    assert len(after) == len(before)
    assert all(row["model_label"] != "ROLLBACK-MID-LOOP" for row in after)
