"""主數據詞彙 CRUD + RBAC + 搜尋/分頁/is_active toggle。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_vocab_create_list_delete(client):
    r = await client.post("/api/v2/vocab", json={"kind": "object", "name_zh": "UT詞彙X"})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    lst = await client.get("/api/v2/vocab")
    assert lst.status_code == 200 and any(v["id"] == vid for v in lst.json())
    d = await client.delete(f"/api/v2/vocab/{vid}")
    assert d.status_code in (200, 204)


async def test_vocab_rbac_viewer_cannot_create(client):
    r = await client.post("/api/v2/vocab", json={"kind": "object", "name_zh": "UT詞彙Y"},
                          headers={"X-Username": "ZZZVOCABVIEW"})
    assert r.status_code == 403


async def test_vocab_search_q(client):
    """q= 參數應過濾 name_zh。"""
    r = await client.post("/api/v2/vocab", json={"kind": "tool", "name_zh": "UT搜尋唯一詞"})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    try:
        lst = await client.get("/api/v2/vocab?q=UT搜尋唯一詞")
        assert lst.status_code == 200
        ids = [v["id"] for v in lst.json()]
        assert vid in ids, "q= 未命中剛建立的詞彙"
        # 無關詞彙不應出現
        lst2 = await client.get("/api/v2/vocab?q=ZZZNOMATCH_XYZABC")
        assert lst2.status_code == 200
        assert lst2.json() == []
    finally:
        await client.delete(f"/api/v2/vocab/{vid}")


async def test_vocab_pagination(client):
    """limit/offset 應分頁。"""
    # 先建 3 筆
    ids = []
    for i in range(3):
        r = await client.post("/api/v2/vocab", json={"kind": "component", "name_zh": f"UT分頁詞彙{i}"})
        assert r.status_code in (200, 201)
        ids.append(r.json()["id"])
    try:
        page1 = await client.get("/api/v2/vocab?kind=component&limit=2&offset=0")
        assert page1.status_code == 200
        assert len(page1.json()) <= 2
        page2 = await client.get("/api/v2/vocab?kind=component&limit=2&offset=2")
        assert page2.status_code == 200
    finally:
        for vid in ids:
            await client.delete(f"/api/v2/vocab/{vid}")


async def test_vocab_patch_is_active_toggle(client):
    """PATCH is_active=False 應停用詞彙（仍可在 list 中出現但 is_active=false）。"""
    r = await client.post("/api/v2/vocab", json={"kind": "object", "name_zh": "UT停用詞彙"})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    try:
        patch_r = await client.patch(f"/api/v2/vocab/{vid}", json={"is_active": False})
        assert patch_r.status_code == 200, patch_r.text
        assert patch_r.json()["is_active"] is False
        # 停用後再啟用
        patch_r2 = await client.patch(f"/api/v2/vocab/{vid}", json={"is_active": True})
        assert patch_r2.status_code == 200
        assert patch_r2.json()["is_active"] is True
    finally:
        await client.delete(f"/api/v2/vocab/{vid}")


async def test_vocab_patch_rbac_viewer_forbidden(client):
    """viewer 不可 PATCH。"""
    r = await client.post("/api/v2/vocab", json={"kind": "object", "name_zh": "UT RBAC詞彙"})
    assert r.status_code in (200, 201)
    vid = r.json()["id"]
    try:
        patch_r = await client.patch(
            f"/api/v2/vocab/{vid}", json={"name_zh": "改名"},
            headers={"X-Username": "ZZZVOCABVIEW"},
        )
        assert patch_r.status_code == 403
    finally:
        await client.delete(f"/api/v2/vocab/{vid}")


async def test_vocab_default_list_excludes_inactive(client):
    """Fix-H1：預設 GET /vocab 不回傳停用詞彙；include_inactive=true 才回傳。"""
    r = await client.post("/api/v2/vocab", json={"kind": "object", "name_zh": "UT停用可見測試"})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    try:
        # 先停用
        patch_r = await client.patch(f"/api/v2/vocab/{vid}", json={"is_active": False})
        assert patch_r.status_code == 200, patch_r.text

        # 預設清單不應包含停用詞彙
        lst = await client.get("/api/v2/vocab")
        assert lst.status_code == 200
        assert not any(v["id"] == vid for v in lst.json()), "停用詞彙不應出現在預設清單中"

        # include_inactive=true 應包含停用詞彙
        lst2 = await client.get("/api/v2/vocab?include_inactive=true")
        assert lst2.status_code == 200
        assert any(v["id"] == vid for v in lst2.json()), "include_inactive=true 應回傳停用詞彙"
    finally:
        await client.delete(f"/api/v2/vocab/{vid}")


async def test_vocab_delete_inactive_item_succeeds(client):
    """Fix-M1：停用（is_active=False）的詞彙仍可被軟刪除（deleted_at 判斷）。"""
    r = await client.post("/api/v2/vocab", json={"kind": "object", "name_zh": "UT停用後刪除"})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    # 停用
    patch_r = await client.patch(f"/api/v2/vocab/{vid}", json={"is_active": False})
    assert patch_r.status_code == 200, patch_r.text
    # 停用後仍可軟刪（Fix-M1）
    del_r = await client.delete(f"/api/v2/vocab/{vid}")
    assert del_r.status_code in (200, 204), f"停用後刪除應成功，實得 {del_r.status_code}: {del_r.text}"
    # 刪除後再刪應 404
    del_r2 = await client.delete(f"/api/v2/vocab/{vid}")
    assert del_r2.status_code == 404, "已刪除詞彙再刪應 404"


async def test_vocab_no_limit_returns_all(client):
    """Fix-H2：不帶 limit 時應回傳全部（不截斷）。"""
    # 建 5 筆同 kind
    kind = "hand"
    ids = []
    for i in range(5):
        r = await client.post("/api/v2/vocab", json={"kind": kind, "name_zh": f"UTnoLimit_{i}"})
        assert r.status_code in (200, 201)
        ids.append(r.json()["id"])
    try:
        lst = await client.get(f"/api/v2/vocab?kind={kind}")
        assert lst.status_code == 200
        returned_ids = {v["id"] for v in lst.json()}
        for vid in ids:
            assert vid in returned_ids, f"無上限時詞彙 {vid} 應在清單中"
    finally:
        for vid in ids:
            await client.delete(f"/api/v2/vocab/{vid}")
