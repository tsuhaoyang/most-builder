"""R2a：worksheet 讀／clone 暴露 policy snapshot；create 綁定 factory V1。"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
SKU = "33333333-3333-3333-3333-333333333333"
MODELING_V1 = "a1000000-0000-4000-8000-000000000001"
LEVEL_V1 = "a2000000-0000-4000-8000-000000000001"


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def test_read_exposes_policy_snapshot(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 alembic v2_0030 + dev_seed_v2）")
    rd = await client.get(f"/api/v2/worksheets/{WS}")
    assert rd.status_code == 200, rd.text
    j = rd.json()
    assert j["modeling_policy"] is not None
    assert j["modeling_policy"]["code"] == "MODELING_FACTORY"
    assert j["modeling_policy"]["version_no"] == 1
    assert j["modeling_policy"]["status"] == "published"
    assert j["level_policy"] is not None
    assert j["level_policy"]["code"] == "LEVEL_FACTORY"
    assert j["level_policy"]["version_no"] == 1
    assert j["level_policy"]["validator_revision"]
    assert j["level_policy"]["output_contract_version"] == "lb-output-v1"


async def test_clone_copies_policy_fks(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    src = (await client.get(f"/api/v2/worksheets/{WS}")).json()
    new_id = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    cloned = (await client.get(f"/api/v2/worksheets/{new_id}")).json()
    assert cloned["modeling_policy"]["id"] == src["modeling_policy"]["id"]
    assert cloned["level_policy"]["id"] == src["level_policy"]["id"]


async def test_create_snapshots_factory_v1(client):
    if not await _seeded(client):
        pytest.skip("demo sku 未種")
    r = await client.post(
        f"/api/v2/skus/{SKU}/worksheets",
        json={"model_label": f"r2a-{uuid.uuid4().hex[:8]}", "analyst": "r2a"},
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["modeling_policy_version_id"] == MODELING_V1
    assert j["level_policy_version_id"] == LEVEL_V1
    assert j.get("revision_no") == 1
    rd = (await client.get(f"/api/v2/worksheets/{j['worksheet_id']}")).json()
    assert rd["modeling_policy"]["id"] == MODELING_V1
    assert rd["level_policy"]["id"] == LEVEL_V1
