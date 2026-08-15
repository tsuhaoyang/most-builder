"""delete_module 的 search_documents 投影清理（孤兒防治）整合測試。

背景：search_documents 無 ORM model、ref_id 無 FK（v2_0013），模組刪除若不在
同交易清投影，/api/v2/search 會持續回傳指向已刪模組的結果（dev 機曾量到
81 筆孤兒，v2_0036 已清）。

涵蓋：
- publish 產生投影 → delete → 投影同交易被清（零孤兒）
- 刪除後 /api/v2/search 不再回傳該模組
- clone 產生的投影在 clone 品被刪時一樣被清
mutation 證據：把 delete_module 內的 DELETE FROM search_documents 拿掉，
前兩條測試必紅（見交付回報）。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _get_rule_set_id(client) -> str | None:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        return None
    return r.json()[0]["id"]


def _gm_row() -> dict:
    """publish-ready GM row（V2 rule-set，全認證代碼；38 TMU）。"""
    return {
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


async def _count_docs(db_session, module_id: str) -> int:
    q = await db_session.execute(
        text(
            "SELECT count(*) FROM search_documents"
            " WHERE doc_type = 'motion_module' AND ref_id = :rid"
        ),
        {"rid": module_id},
    )
    return int(q.scalar_one())


async def _publish_module(client, name_zh: str) -> str:
    """建 global 模組並 publish 一版（觸發 search 投影 upsert），回傳 module id。"""
    rs_id = await _get_rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set，略過")
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": name_zh,
        "category": "action",
        "scope": "global",
        "keywords": ["搜尋投影測試"],
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    pub = await client.post(
        f"/api/v2/motion-modules/{mid}/publish",
        json={"rule_set_id": rs_id, "rows": [_gm_row()]},
    )
    assert pub.status_code == 201, pub.text
    return mid


async def test_delete_module_purges_search_projection(client, db_session):
    """publish 建投影 → delete → 同交易零孤兒。"""
    sfx = uuid.uuid4().hex[:6]
    mid = await _publish_module(client, f"投影清理測試{sfx}")

    # Arrange 驗證：publish 後投影存在（否則後半斷言空泛）
    assert await _count_docs(db_session, mid) == 1

    d = await client.delete(f"/api/v2/motion-modules/{mid}")
    assert d.status_code == 204, d.text

    # 核心斷言：模組刪除後投影同交易被清，零孤兒
    assert await _count_docs(db_session, mid) == 0


async def test_search_does_not_return_deleted_module(client):
    """刪除後 /api/v2/search 不得再回傳該模組（孤兒的使用者可見症狀）。"""
    sfx = uuid.uuid4().hex[:6]
    name = f"獨特搜尋詞彙{sfx}"
    mid = await _publish_module(client, name)

    before = await client.get("/api/v2/search", params={"q": name})
    assert before.status_code == 200
    assert mid in {h["ref_id"] for h in before.json()["hits"]}, (
        "前置條件失敗：publish 後搜尋必須先找得到，否則後半斷言空泛"
    )

    d = await client.delete(f"/api/v2/motion-modules/{mid}")
    assert d.status_code == 204, d.text

    after = await client.get("/api/v2/search", params={"q": name})
    assert after.status_code == 200
    assert mid not in {h["ref_id"] for h in after.json()["hits"]}


async def test_delete_cloned_module_purges_its_projection(client, db_session):
    """clone 也寫投影（clone 後 upsert）；刪 clone 品時投影一樣要清。"""
    sfx = uuid.uuid4().hex[:6]
    src = await _publish_module(client, f"複製來源{sfx}")

    c = await client.post(f"/api/v2/motion-modules/{src}/clone")
    assert c.status_code == 201, c.text
    clone_id = c.json()["id"]
    assert await _count_docs(db_session, clone_id) == 1

    d = await client.delete(f"/api/v2/motion-modules/{clone_id}")
    assert d.status_code == 204, d.text
    assert await _count_docs(db_session, clone_id) == 0
    # 來源模組的投影不受影響
    assert await _count_docs(db_session, src) == 1


# ── 常設守衛（code-reviewer #6）────────────────────────────────────────────────

async def test_no_orphan_motion_module_search_documents(db_session):
    """零孤兒常設守衛：任何路徑（service 刪除、cleanup 腳本、手動 SQL）留下的
    motion_module 孤兒投影都會讓本測試紅。

    v2_0036 已清既存孤兒、delete_module 同交易清投影、cleanup_test_data.py 亦
    同步 DELETE 投影——三個來源都堵上後，這裡守住「不再回來」。
    """
    n = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM search_documents sd"
                " WHERE sd.doc_type = 'motion_module'"
                " AND NOT EXISTS (SELECT 1 FROM motion_modules m WHERE m.id = sd.ref_id)"
            )
        )
    ).scalar_one()
    assert n == 0, f"發現 {n} 筆 motion_module 孤兒 search_documents（來源需排查）"
