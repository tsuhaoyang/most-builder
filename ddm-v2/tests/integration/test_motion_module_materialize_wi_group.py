"""B1（ADR-035 D10）：模組實體化的列 wi_group == 模組 name_zh。

註：實作書 §8.1 列於 unit，但 instantiate_to_worksheet 需 DB，故置於 integration（誠實分類）。
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
_OBJ_SEEDED = "66666666-6666-6666-6666-666666666666"


def _gm_row_pub(vocab_refs):
    return {"hand": "RH", "frequency": 1, "vocab_refs": vocab_refs,
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}}


async def _rule_set_id(client):
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200:
        return None
    items = r.json()
    for it in (items if isinstance(items, list) else items.get("items", [])):
        if it.get("code") == "MINIMOST_FACTORY_V2":
            return it.get("id")
    return None


async def test_materialized_rows_carry_module_name_as_wi_group(client):
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    rs_id = await _rule_set_id(client)
    if rs_id is None:
        pytest.skip("DB 無 rule_set")
    ws_id = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    name = f"裝 HDD-{uuid.uuid4().hex[:6]}"
    mid = (await client.post("/api/v2/motion-modules", json={
        "name_zh": name, "category": "action", "scope": "global"})).json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id, "rows": [_gm_row_pub({"object_vocab_id": _OBJ_SEEDED})]})
    assert pub.status_code == 201, pub.text
    inst = await client.post(f"/api/v2/worksheets/{ws_id}/rows/from-module", json={"module_id": mid})
    assert inst.status_code == 201, inst.text
    rd = (await client.get(f"/api/v2/worksheets/{ws_id}")).json()
    materialized = [r for r in rd["rows"] if r.get("wi_group") == name]
    assert materialized, f"實體化列應帶 wi_group=={name}；實得 {[r.get('wi_group') for r in rd['rows']]}"
