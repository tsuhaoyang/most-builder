"""ADR-022 批次 A 端點測試：rows computed 持久化（A-1）＋ row 級操作（A-2）＋ category='action'（A-3）。

涵蓋：
- A-1：publish 後版本 rows[i].computed（total_tmu/total_seconds/eff_tmu/contribution_tmu）
        與 narrative_zh 持久化；SIMO 從屬列 contribution_tmu=0；sub_activity 不被覆蓋。
- A-2：PUT rows/{i}（編輯重算發新版）、POST rows/reorder（完整排列驗證＋SIMO 換算）、
        DELETE rows/{i}（刪除重算；刪到 0 列 422；SIMO 指向被刪列 422）；RBAC viewer 403。
- A-3：category='action' 可建立、可過濾。
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

_TMU_TO_SEC = 0.036


async def _get_rule_set_id(client) -> str | None:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        return None
    return r.json()[0]["id"]


def _gm28_row(*, frequency: int = 1, simo_pair_index: int | None = None,
              sub_activity: str | None = None) -> dict:
    """GM 黃金列（V2 rule-set，28 TMU）：a0=20 + g_grasp + a3=25 + p_place_none。"""
    row = {
        "hand": "RH",
        "frequency": frequency,
        "vocab_refs": {},
        "cycle": {
            "seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2",
            "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"},
        },
    }
    if simo_pair_index is not None:
        row["simo_pair_index"] = simo_pair_index
    if sub_activity is not None:
        row["sub_activity"] = sub_activity
    return row


def _gm38_row(**kw) -> dict:
    """GM 38 TMU 列（a0=30 → A10、a3=40 → A16）。"""
    row = _gm28_row(**kw)
    row["cycle"]["a0"] = {"reach_cm": 30}
    row["cycle"]["a3"] = {"reach_cm": 40}
    return row


async def _make_published_module(client, rs_id: str, rows: list[dict], prefix: str) -> str:
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"{prefix}-{sfx}", "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id, "rows": rows,
    })
    assert pub.status_code == 201, pub.text
    return mid


# ═════════ A-1：rows computed / narrative_zh 持久化 ═════════

async def test_publish_persists_computed_per_row(client):
    """publish 後每列帶 computed；值全來自引擎（28 黃金列）；GET detail 讀得到。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [
        _gm28_row(sub_activity="使用者自寫句", frequency=2),
    ], "A1-Computed")

    detail = await client.get(f"/api/v2/motion-modules/{mid}")
    assert detail.status_code == 200, detail.text
    ver = detail.json()["current_version_detail"]
    assert ver is not None
    row = ver["rows"][0]

    c = row["computed"]
    assert c["total_tmu"] == pytest.approx(28.0)
    assert c["total_seconds"] == pytest.approx(round(28.0 * _TMU_TO_SEC, 4))
    assert c["eff_tmu"] == pytest.approx(56.0)            # ×frequency
    assert c["contribution_tmu"] == pytest.approx(56.0)   # 非 SIMO＝eff
    # narrative_zh 每列寫入；sub_activity 使用者句保留不覆蓋
    assert row["narrative_zh"], row
    assert row["sub_activity"] == "使用者自寫句"
    # 版本合計＝引擎（28×2）
    assert float(ver["total_tmu"]) == pytest.approx(56.0)


async def test_publish_simo_row_contribution_zero(client):
    """SIMO 從屬列（宣告 simo_pair_index）：eff_tmu 照算、contribution_tmu=0（ADR-020）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [
        _gm28_row(),                                  # 主列
        _gm28_row(frequency=2, simo_pair_index=0),    # 從屬列
    ], "A1-SIMO")

    detail = await client.get(f"/api/v2/motion-modules/{mid}")
    ver = detail.json()["current_version_detail"]
    main_c, dep_c = ver["rows"][0]["computed"], ver["rows"][1]["computed"]
    assert main_c["contribution_tmu"] == pytest.approx(28.0)
    assert dep_c["total_tmu"] == pytest.approx(28.0)
    assert dep_c["eff_tmu"] == pytest.approx(56.0)
    assert dep_c["contribution_tmu"] == pytest.approx(0.0)   # SIMO 標記列貢獻 0
    assert float(ver["total_tmu"]) == pytest.approx(28.0)    # 總計＝主列


async def test_apply_back_persists_computed(client):
    """versions/from-rows（apply-back）同一路徑：rows 也帶 computed。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"A1-FromRows-{uuid.uuid4().hex[:6]}", "scope": "personal",
    })
    mid = r.json()["id"]
    resp = await client.post(f"/api/v2/motion-modules/{mid}/versions/from-rows", json={
        "rule_set_id": rs_id, "rows": [_gm28_row()],
    })
    assert resp.status_code == 201, resp.text
    row = resp.json()["rows"][0]
    assert row["computed"]["total_tmu"] == pytest.approx(28.0)
    assert row["narrative_zh"]


# ═════════ A-2：PUT rows/{i} ═════════

async def test_update_row_recomputes_and_bumps_version(client):
    """替換單列 → 引擎重算全表 → 新版本（total 與每列 computed 更新）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [_gm28_row(), _gm28_row()], "A2-Upd")

    # 把 row 1 換成 38 TMU 列（frequency=2）
    resp = await client.put(
        f"/api/v2/motion-modules/{mid}/rows/1",
        json=_gm38_row(frequency=2, sub_activity="微調後"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version_no"] == 2                       # 版本不可變：發新版
    assert float(body["total_tmu"]) == pytest.approx(28.0 + 76.0)
    assert body["rows"][1]["computed"]["total_tmu"] == pytest.approx(38.0)
    assert body["rows"][1]["computed"]["eff_tmu"] == pytest.approx(76.0)
    assert body["rows"][1]["sub_activity"] == "微調後"
    assert body["rows"][0]["computed"]["total_tmu"] == pytest.approx(28.0)  # 未動列照舊

    # module current_version 已推進；舊版本仍在（不可變）
    vs = await client.get(f"/api/v2/motion-modules/{mid}/versions")
    assert [v["version_no"] for v in vs.json()] == [1, 2]


async def test_update_row_out_of_range_404(client):
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [_gm28_row()], "A2-OOB")
    resp = await client.put(f"/api/v2/motion-modules/{mid}/rows/1", json=_gm28_row())
    assert resp.status_code == 404, resp.text


async def test_update_row_invalid_simo_422(client):
    """編輯列宣告自指 simo_pair_index → 422 SIMO_PAIR_INVALID（沿 _validate_simo_pairs）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [_gm28_row(), _gm28_row()], "A2-SIMO-Inv")
    resp = await client.put(
        f"/api/v2/motion-modules/{mid}/rows/0",
        json=_gm28_row(simo_pair_index=0),   # 自指
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "SIMO_PAIR_INVALID"


async def test_update_row_module_not_found_404(client):
    resp = await client.put(
        f"/api/v2/motion-modules/{uuid.uuid4()}/rows/0", json=_gm28_row(),
    )
    assert resp.status_code == 404, resp.text


async def test_row_ops_rbac_viewer_403(client):
    """RBAC：viewer 不可 row 級編輯/重排/刪除 → 403。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [_gm28_row(), _gm28_row()], "A2-RBAC")
    h = {"X-Username": "ZZZMMVIEWER999"}
    assert (await client.put(f"/api/v2/motion-modules/{mid}/rows/0",
                             json=_gm28_row(), headers=h)).status_code == 403
    assert (await client.post(f"/api/v2/motion-modules/{mid}/rows/reorder",
                              json={"ordered_indexes": [1, 0]}, headers=h)).status_code == 403
    assert (await client.delete(f"/api/v2/motion-modules/{mid}/rows/0",
                                headers=h)).status_code == 403


# ═════════ A-2：POST rows/reorder ═════════

async def test_reorder_rows_happy(client):
    """重排 [1,0] → 新版本 rows 對調；total 不變。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [
        _gm28_row(sub_activity="第一列"), _gm38_row(sub_activity="第二列"),
    ], "A2-Reorder")

    resp = await client.post(f"/api/v2/motion-modules/{mid}/rows/reorder", json={
        "ordered_indexes": [1, 0],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version_no"] == 2
    assert [r["sub_activity"] for r in body["rows"]] == ["第二列", "第一列"]
    assert float(body["total_tmu"]) == pytest.approx(28.0 + 38.0)
    assert body["rows"][0]["computed"]["total_tmu"] == pytest.approx(38.0)


async def test_reorder_remaps_simo_pair_index(client):
    """SIMO 從屬列的 simo_pair_index 隨重排換算為新位置；貢獻語義不變。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [
        _gm28_row(sub_activity="主列"),                             # idx0
        _gm28_row(sub_activity="從屬列", simo_pair_index=0),        # idx1 → 指向 0
        _gm38_row(sub_activity="尾列"),                             # idx2
    ], "A2-Reorder-SIMO")

    # 重排為 [尾列, 主列, 從屬列] → 主列新位置 1，從屬列 simo_pair_index 應變 1
    resp = await client.post(f"/api/v2/motion-modules/{mid}/rows/reorder", json={
        "ordered_indexes": [2, 0, 1],
    })
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert [r["sub_activity"] for r in rows] == ["尾列", "主列", "從屬列"]
    assert rows[2]["simo_pair_index"] == 1
    assert rows[2]["computed"]["contribution_tmu"] == pytest.approx(0.0)
    assert float(resp.json()["total_tmu"]) == pytest.approx(38.0 + 28.0)


async def test_reorder_invalid_permutation_422(client):
    """非 0..n-1 完整排列（缺項/重複/越界）→ 422 REORDER_INVALID。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [_gm28_row(), _gm28_row()], "A2-Reorder-Bad")
    for bad in ([0], [0, 0], [0, 2], [0, 1, 2]):
        resp = await client.post(f"/api/v2/motion-modules/{mid}/rows/reorder", json={
            "ordered_indexes": bad,
        })
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["detail"]["code"] == "REORDER_INVALID", bad


# ═════════ A-2：DELETE rows/{i} ═════════

async def test_delete_row_recomputes(client):
    """刪除一列 → 重算 → 新版本；total 扣除被刪列。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [
        _gm28_row(sub_activity="留"), _gm38_row(sub_activity="刪"),
    ], "A2-Del")
    resp = await client.delete(f"/api/v2/motion-modules/{mid}/rows/1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version_no"] == 2
    assert len(body["rows"]) == 1
    assert body["rows"][0]["sub_activity"] == "留"
    assert float(body["total_tmu"]) == pytest.approx(28.0)


async def test_delete_last_row_422(client):
    """刪到 0 列 → 422（WI 至少 1 動作）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [_gm28_row()], "A2-Del-Last")
    resp = await client.delete(f"/api/v2/motion-modules/{mid}/rows/0")
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "EMPTY_ROWS"


async def test_delete_simo_target_row_422(client):
    """刪除被 SIMO 從屬列指向的主列 → 422（需先解除配對，不得靜默改變貢獻語義）。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [
        _gm28_row(),                          # 主列（被指向）
        _gm28_row(simo_pair_index=0),         # 從屬列
    ], "A2-Del-SIMO")
    resp = await client.delete(f"/api/v2/motion-modules/{mid}/rows/0")
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "SIMO_PAIR_INVALID"

    # 刪從屬列本身則允許
    resp2 = await client.delete(f"/api/v2/motion-modules/{mid}/rows/1")
    assert resp2.status_code == 200, resp2.text
    assert len(resp2.json()["rows"]) == 1


async def test_delete_row_remaps_simo_after_shift(client):
    """刪除 SIMO 配對之前的列：simo_pair_index 依位移換算。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    mid = await _make_published_module(client, rs_id, [
        _gm38_row(sub_activity="頭列"),                       # idx0（刪）
        _gm28_row(sub_activity="主列"),                       # idx1
        _gm28_row(sub_activity="從屬列", simo_pair_index=1),  # idx2 → 指向 1
    ], "A2-Del-Shift")
    resp = await client.delete(f"/api/v2/motion-modules/{mid}/rows/0")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert [r["sub_activity"] for r in rows] == ["主列", "從屬列"]
    assert rows[1]["simo_pair_index"] == 0                # 1 → 0（位移換算）
    assert float(resp.json()["total_tmu"]) == pytest.approx(28.0)


async def test_delete_row_unpublished_module_404(client):
    """尚無發布版本（current_version=0）→ 404。"""
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"A2-Del-NoVer-{uuid.uuid4().hex[:6]}", "scope": "global",
    })
    mid = r.json()["id"]
    resp = await client.delete(f"/api/v2/motion-modules/{mid}/rows/0")
    assert resp.status_code == 404, resp.text


# ═════════ A-3：category='action' ═════════

async def test_category_action_create_and_filter(client):
    """category='action' 可建立、list ?category=action 可過濾出來。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"A3-Action-{sfx}", "scope": "global", "category": "action",
    })
    assert r.status_code == 201, r.text
    assert r.json()["category"] == "action"
    mid = r.json()["id"]

    lst = await client.get("/api/v2/motion-modules?category=action")
    assert lst.status_code == 200, lst.text
    assert mid in [x["id"] for x in lst.json()]
    assert all(x["category"] == "action" for x in lst.json())

    # 其他 category 過濾不含它
    lst2 = await client.get("/api/v2/motion-modules?category=wi-template")
    assert mid not in [x["id"] for x in lst2.json()]
