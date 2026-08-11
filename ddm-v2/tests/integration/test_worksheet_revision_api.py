"""R1 worksheet revision optimistic locking（integration）。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration


def _gm_row(row_id: str, rule_set_code: str) -> dict:
    # 對齊 test_worksheet._gm_row 的 CycleIn 形狀（引擎 GM=28 錨）
    return {
        "id": row_id,
        "seq_no": 1,
        "hand": "RH",
        "frequency": 1,
        "narrative": "r1 revision",
        "cycle": {
            "seq": "GM",
            "rule_set_code": rule_set_code,
            "a0": {"reach_cm": 20},
            "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25},
            "p5": {"p_base_code": "p_place_none"},
        },
        "level": {"ascription": "main", "level": "1"},
    }


async def _seed_ws(db_session, *, revision_no: int = 1):
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
    from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    site = Site(id=uuid.uuid4(), external_code=f"R1-{uuid.uuid4().hex[:6]}", name_zh="R1")
    db_session.add(site)
    await db_session.flush()
    product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="P")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(
        id=uuid.uuid4(),
        product_id=product.id,
        sku_code=f"S-{uuid.uuid4().hex[:6]}",
        name_zh="S",
    )
    db_session.add(sku)
    await db_session.flush()
    rs = await get_active_rule_set(db_session)
    pv = ProcessVersion(
        id=uuid.uuid4(),
        sku_id=sku.id,
        version_no="v1",
        status="draft",
        created_by="IEC141289",
    )
    ws = MostWorksheet(
        id=uuid.uuid4(),
        process_version_id=pv.id,
        status="draft",
        default_rule_set_id=rs.id,
        modeling_policy_version_id=MODELING_FACTORY_V1_ID,
        level_policy_version_id=LEVEL_FACTORY_V1_ID,
        revision_no=revision_no,
    )
    db_session.add(pv)
    db_session.add(ws)
    await db_session.commit()
    return ws, rs


@pytest.mark.asyncio
async def test_revision_conflict_second_save_409(client, db_session):
    """兩 client 同 base_revision：一成功、一 409；舊 rows 保留。"""
    from ddm_v2.models.v2.worksheet import WiRow

    ws, rs = await _seed_ws(db_session, revision_no=1)
    rid = str(uuid.uuid4())
    body1 = {"base_revision": 1, "rows": [_gm_row(rid, rs.code)]}
    r1 = await client.put(f"/api/v2/worksheets/{ws.id}", json=body1)
    assert r1.status_code == 200, r1.text
    assert r1.json()["revision_no"] == 2
    assert r1.json()["content_hash"]

    body_stale = {"base_revision": 1, "rows": []}
    r2 = await client.put(f"/api/v2/worksheets/{ws.id}", json=body_stale)
    assert r2.status_code == 409, r2.text
    err = r2.json()
    code = (err.get("error") or {}).get("code") or (err.get("detail") or {}).get("code")
    assert code == "WORKSHEET_REVISION_CONFLICT"

    await db_session.refresh(ws)
    assert int(ws.revision_no) == 2
    n_rows = (
        await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))
    ).scalars().all()
    assert len(n_rows) == 1

    r3 = await client.put(
        f"/api/v2/worksheets/{ws.id}",
        json={"base_revision": 2, "rows": []},
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["revision_no"] == 3
    assert r3.json()["rows"] == []


@pytest.mark.asyncio
async def test_clone_resets_revision_to_1(client, db_session):
    ws, _rs = await _seed_ws(db_session, revision_no=5)
    c = await client.post(f"/api/v2/worksheets/{ws.id}/clone")
    assert c.status_code == 200, c.text
    assert c.json()["revision_no"] == 1
    new_id = c.json()["new_worksheet_id"]
    g = await client.get(f"/api/v2/worksheets/{new_id}")
    assert g.status_code == 200
    assert g.json()["revision_no"] == 1


@pytest.mark.asyncio
async def test_publish_does_not_bump_revision(client, db_session):
    ws, _rs = await _seed_ws(db_session, revision_no=3)
    v = await client.post(f"/api/v2/worksheets/{ws.id}/level/validate")
    assert v.status_code == 200, v.text
    assert v.json()["valid"] is True
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert p.status_code == 200, p.text
    await db_session.refresh(ws)
    assert int(ws.revision_no) == 3
