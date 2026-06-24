"""Worksheet 持久化 + SOP 版本：save→read roundtrip / versions / clone+publish / RBAC。"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"


def _gm_row():
    return {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": 1, "narrative": "ut roundtrip",
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}}


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def test_save_and_read_roundtrip(client):
    """存整表 → 讀回，TMU 由引擎算（GM 黃金=28）。用 clone 隔離，不動 demo 表。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()]})
    assert r.status_code == 200, r.text
    assert r.json()["total_tmu"] == 28
    rd = await client.get(f"/api/v2/worksheets/{new}")
    assert rd.status_code == 200
    rows = rd.json()["rows"]
    assert len(rows) == 1 and rows[0]["cycle"]["total_tmu"] == 28


async def test_versions(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    j = (await client.get(f"/api/v2/worksheets/{WS}/versions")).json()
    assert "versions" in j and any(v["is_current"] for v in j["versions"])


async def test_clone_then_publish(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    assert (await client.post(f"/api/v2/worksheets/{new}/publish")).status_code == 200
    assert (await client.post(f"/api/v2/worksheets/{new}/publish")).status_code == 409  # 已發布再發布


async def test_rbac_viewer_cannot_clone(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    r = await client.post(f"/api/v2/worksheets/{WS}/clone", headers={"X-Username": "ZZZWSVIEWER"})
    assert r.status_code == 403
