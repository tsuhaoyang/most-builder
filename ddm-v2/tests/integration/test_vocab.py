"""主數據詞彙 CRUD + RBAC + 搜尋/分頁/is_active toggle + 名稱空白邊界。"""
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


# ── 名稱空白邊界（H-1 根因：空白詞彙名會讓英文敘事在讀取時 500）────────

# 含全形空白（U+3000）與 nbsp（U+00A0）——`str.strip()` 是 Unicode-aware 的，現行實作
# 擋得住；只放 ASCII 的話，日後把驗證收窄成 `.strip(" \t\n")` 不會有測試變紅，
# 而全形空白是中文輸入法最容易打出、肉眼與半形無異的那一種。
@pytest.mark.parametrize("blank", ["   ", "\t", "", " \t ", "\u3000", "\xa0"])
async def test_vocab_create_rejects_blank_name_zh(client, blank):
    r = await client.post("/api/v2/vocab", json={"kind": "object", "name_zh": blank})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("blank", ["   ", "\t", "", "\u3000", "\xa0"])
async def test_vocab_blank_name_en_is_stored_as_null(client, blank):
    """英文名不同於中文名：空白＝清掉英文名，正規化為 null 而不是 422。"""
    r = await client.post("/api/v2/vocab",
                          json={"kind": "object", "name_zh": " UT詞彙空白英文名 ", "name_en": blank})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["name_en"] is None
    assert body["name_zh"] == "UT詞彙空白英文名"        # 前後空白已 strip
    await client.delete(f"/api/v2/vocab/{body['id']}")


async def test_vocab_patch_blank_name_zh_rejected_and_name_en_cleared(client):
    r = await client.post("/api/v2/vocab",
                          json={"kind": "object", "name_zh": "UT詞彙補丁", "name_en": "Patch item"})
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    try:
        bad = await client.patch(f"/api/v2/vocab/{vid}", json={"name_zh": "   "})
        assert bad.status_code == 422, bad.text

        cleared = await client.patch(f"/api/v2/vocab/{vid}", json={"name_en": "  "})
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["name_en"] is None    # 送了鍵＝要清空，不是「沒送」
        assert cleared.json()["name_zh"] == "UT詞彙補丁"

        untouched = await client.patch(f"/api/v2/vocab/{vid}", json={"is_active": True})
        assert untouched.status_code == 200 and untouched.json()["name_zh"] == "UT詞彙補丁"
    finally:
        await client.delete(f"/api/v2/vocab/{vid}")

