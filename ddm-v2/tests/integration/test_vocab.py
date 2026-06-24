"""主數據詞彙 CRUD + RBAC。"""
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
