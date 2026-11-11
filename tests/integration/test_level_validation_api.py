"""R2b：level_validation_runs + publish gate。"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"


def _bad_level_row():
    """缺 main → R1 失敗。"""
    return {
        "id": str(uuid.uuid4()),
        "seq_no": 1,
        "hand": "RH",
        "frequency": 1,
        "narrative": "bad level",
        "cycle": {
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V1",
            "a0": {"reach_cm": 20},
            "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25},
            "p5": {"p_base_code": "p_place_none"},
        },
        "level": {"level": "1"},  # 無 ascription=main
    }


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def test_clone_then_publish_has_validation_evidence(client):
    """clone 會寫 revalidate run → publish 可過 gate。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    v = await client.post(f"/api/v2/worksheets/{new}/level/validate")
    assert v.status_code == 200, v.text
    assert v.json()["valid"] is True
    assert v.json()["worksheet_revision"] == 1
    p = await client.post(f"/api/v2/worksheets/{new}/publish")
    assert p.status_code == 200, p.text


async def test_publish_without_validation_run_409(client, db_session):
    """手動建 worksheet（無 run）→ publish 409 LEVEL_VALIDATION_REQUIRED。"""
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
    from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    site = Site(id=uuid.uuid4(), external_code=f"R2B-{uuid.uuid4().hex[:6]}", name_zh="R2b")
    db_session.add(site)
    await db_session.flush()
    product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="P")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(id=uuid.uuid4(), product_id=product.id, sku_code=f"S-{uuid.uuid4().hex[:6]}")
    db_session.add(sku)
    await db_session.flush()
    rs = await get_active_rule_set(db_session)
    pv = ProcessVersion(id=uuid.uuid4(), sku_id=sku.id, version_no="v1", status="draft")
    ws = MostWorksheet(
        id=uuid.uuid4(),
        process_version_id=pv.id,
        status="draft",
        default_rule_set_id=rs.id,
        modeling_policy_version_id=MODELING_FACTORY_V1_ID,
        level_policy_version_id=LEVEL_FACTORY_V1_ID,
        revision_no=1,
    )
    db_session.add(pv)
    db_session.add(ws)
    await db_session.commit()

    r = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert r.status_code == 409, r.text
    body = r.json()
    code = body.get("error", {}).get("code") or body.get("detail")
    assert code == "LEVEL_VALIDATION_REQUIRED" or "LEVEL_VALIDATION_REQUIRED" in str(body)


async def test_save_invalid_level_then_publish_422(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    # 讀 revision
    rev = (await client.get(f"/api/v2/worksheets/{new}")).json()["revision_no"]
    s = await client.put(
        f"/api/v2/worksheets/{new}",
        json={"base_revision": rev, "rows": [_bad_level_row()]},
    )
    assert s.status_code == 200, s.text
    assert s.json().get("revision_no") == rev + 1
    # save 已寫 invalid run → publish 422
    p = await client.post(f"/api/v2/worksheets/{new}/publish")
    assert p.status_code == 422, p.text
    err = p.json().get("error", {})
    assert err.get("code") == "LEVEL_VALIDATION_FAILED"
