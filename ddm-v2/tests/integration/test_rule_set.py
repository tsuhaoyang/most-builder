"""Rule-set 端點：list / options / full（規則表檢視 + 計算依據）。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

CODE = "MINIMOST_FACTORY_V1"


async def test_rule_set_list_options_full(client):
    lst = await client.get("/api/v2/rule-sets")
    if lst.status_code != 200 or not lst.json():
        pytest.skip("rule-set 未種")
    assert any(r["code"] == CODE for r in lst.json())
    assert (await client.get(f"/api/v2/rule-sets/{CODE}/options")).status_code == 200
    full = await client.get(f"/api/v2/rule-sets/{CODE}/full")
    assert full.status_code == 200
    f = full.json()
    for sec in ["a_bands", "g", "p_bases", "m_verbs", "x", "i"]:
        assert len(f[sec]) > 0, f"規則區塊 {sec} 是空的"
