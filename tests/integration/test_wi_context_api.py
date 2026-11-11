"""R3a：wi_row_contexts API CRUD + CASCADE。"""
from __future__ import annotations

import os
import uuid

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"


def _gm_row():
    return {
        "id": str(uuid.uuid4()),
        "seq_no": 1,
        "hand": "RH",
        "frequency": 1,
        "narrative": "r3a context",
        "cycle": {
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V1",
            "a0": {"reach_cm": 20},
            "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25},
            "p5": {"p_base_code": "p_place_none"},
        },
        "level": {"ascription": "main", "level": "1"},
    }


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def _clone_with_row(client) -> tuple[str, str]:
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    rev = (await client.get(f"/api/v2/worksheets/{new}")).json()["revision_no"]
    row = _gm_row()
    s = await client.put(
        f"/api/v2/worksheets/{new}",
        json={"base_revision": rev, "rows": [row]},
    )
    assert s.status_code == 200, s.text
    return new, row["id"]


async def test_put_get_delete_context(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    _ws, row_id = await _clone_with_row(client)

    miss = await client.get(f"/api/v2/wi-rows/{row_id}/context")
    assert miss.status_code == 404

    put = await client.put(
        f"/api/v2/wi-rows/{row_id}/context",
        json={
            "schema_version": "wi-context-v1",
            "source": "manual",
            "context_data": {
                "safety_notes": ["戴手套"],
                "sop_refs": [{"code": "SOP-1"}],
            },
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["schema_version"] == "wi-context-v1"
    assert body["context_data"]["safety_notes"] == ["戴手套"]
    assert body["context_hash"]
    assert "tmu" not in body["context_data"]

    got = await client.get(f"/api/v2/wi-rows/{row_id}/context")
    assert got.status_code == 200
    assert got.json()["context_hash"] == body["context_hash"]

    bad = await client.put(
        f"/api/v2/wi-rows/{row_id}/context",
        json={"schema_version": "wi-context-v1", "context_data": {"slot_inputs": {}}},
    )
    assert bad.status_code == 422, bad.text

    deleted = await client.delete(f"/api/v2/wi-rows/{row_id}/context")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v2/wi-rows/{row_id}/context")).status_code == 404


async def test_context_cascades_when_row_deleted(client, db_session):
    from ddm_v2.models.v2.wi_context import WiRowContext

    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new, row_id = await _clone_with_row(client)
    put = await client.put(
        f"/api/v2/wi-rows/{row_id}/context",
        json={"context_data": {"business_tags": ["demo"]}},
    )
    assert put.status_code == 200, put.text
    ctx_id = put.json()["id"]

    rev = (await client.get(f"/api/v2/worksheets/{new}")).json()["revision_no"]
    # 整表取代清空 rows → CASCADE 刪 context
    s = await client.put(f"/api/v2/worksheets/{new}", json={"base_revision": rev, "rows": []})
    assert s.status_code == 200, s.text

    gone = await db_session.get(WiRowContext, uuid.UUID(ctx_id))
    assert gone is None


async def test_viewer_cannot_put_context(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    _ws, row_id = await _clone_with_row(client)
    r = await client.put(
        f"/api/v2/wi-rows/{row_id}/context",
        json={"context_data": {}},
        headers={"X-Username": "ZZZMMVIEWER999"},
    )
    assert r.status_code == 403, r.text


async def test_published_worksheet_context_frozen(client):
    """publish 後 PUT/DELETE context → 409 VERSION_PUBLISHED。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new, row_id = await _clone_with_row(client)
    # 先確保有 validation run（R2b gate）；clone/save 已寫
    p = await client.post(f"/api/v2/worksheets/{new}/publish")
    assert p.status_code == 200, p.text

    put = await client.put(
        f"/api/v2/wi-rows/{row_id}/context",
        json={"context_data": {"business_tags": ["nope"]}},
    )
    assert put.status_code == 409, put.text
    code = (put.json().get("error") or {}).get("code")
    assert code == "VERSION_PUBLISHED"

    deleted = await client.delete(f"/api/v2/wi-rows/{row_id}/context")
    assert deleted.status_code == 409, deleted.text

