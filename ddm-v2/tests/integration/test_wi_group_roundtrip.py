"""B1（ADR-035 D10）：wi_rows.wi_group 存→讀→clone roundtrip；content_hash 隨 wi_group 變。"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"


def _row(wi_group):
    return {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": 1, "narrative": "裝 HDD 第一步", "wi_group": wi_group,
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}}


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def test_wi_group_roundtrip_and_clone(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_row("裝 HDD")]})
    assert r.status_code == 200, r.text
    rd = (await client.get(f"/api/v2/worksheets/{new}")).json()
    assert rd["rows"][0]["wi_group"] == "裝 HDD"
    # clone 複製 wi_group
    cloned = (await client.post(f"/api/v2/worksheets/{new}/clone")).json()["new_worksheet_id"]
    cd = (await client.get(f"/api/v2/worksheets/{cloned}")).json()
    assert cd["rows"][0]["wi_group"] == "裝 HDD"


async def test_content_hash_changes_with_wi_group(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    row = _row("裝 HDD")
    h1 = (await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row]})).json()["content_hash"]
    # 同 id、只改 wi_group → hash 必變
    row2 = dict(row, wi_group="鎖螺絲")
    h2 = (await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row2]})).json()["content_hash"]
    assert h1 != h2


async def test_wi_group_empty_normalized_to_null(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_row("   ")]})
    assert r.status_code == 200, r.text
    rd = (await client.get(f"/api/v2/worksheets/{new}")).json()
    assert rd["rows"][0]["wi_group"] is None
