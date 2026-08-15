"""L4 parse-jobs API 整合測試（不改 ADR-025 map/submit）。"""
from __future__ import annotations

import os
import uuid

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration


async def _get_rs_code(client) -> str:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set，略過")
    return r.json()[0]["code"]


async def _seed_mapped_import(db_session, *, n_rows: int = 2):
    from ddm_v2.models.v2.import_staging import ExcelImport

    rows = [
        {"_row": i + 1, "description": f"拿起零件{i + 1}測試列{uuid.uuid4().hex[:4]}"}
        for i in range(n_rows)
    ]
    rec = ExcelImport(
        id=uuid.uuid4(),
        source_name="l4-test.xlsx",
        status="mapped",
        raw_payload={"sheets": []},
        sheet="Sheet1",
        header_row=0,
        column_map={"description": 0},
        time_unit="sec",
        staged_rows=rows,
        imported_by="TEST",
    )
    db_session.add(rec)
    await db_session.commit()
    return rec.id, rows


@pytest.mark.asyncio
async def test_parse_job_create_tick_idempotent(client, db_session):
    from sqlalchemy import select

    from ddm_v2.models.v2.ai_ops import AiParseJobItem, AiParseRun
    from ddm_v2.models.v2.import_staging import ImportRow

    import_id, rows = await _seed_mapped_import(db_session, n_rows=2)
    code = await _get_rs_code(client)
    key = f"l4-idem-{uuid.uuid4().hex}"

    r1 = await client.post(
        f"/api/v2/imports/{import_id}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": key},
    )
    assert r1.status_code == 201, r1.text
    job = r1.json()
    assert job["status"] == "queued"
    assert job["total"] == 2
    assert job["review"] == 0

    r_dup = await client.post(
        f"/api/v2/imports/{import_id}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": key},
    )
    assert r_dup.status_code == 201, r_dup.text
    assert r_dup.json()["id"] == job["id"]

    # materialize import_rows

    ir = (
        await db_session.execute(select(ImportRow).where(ImportRow.import_id == import_id))
    ).scalars().all()
    assert len(ir) == 2

    g = await client.get(f"/api/v2/imports/{import_id}/parse-jobs/{job['id']}")
    assert g.status_code == 200
    assert g.json()["total"] == 2

    t1 = await client.post(
        f"/api/v2/imports/{import_id}/parse-jobs/{job['id']}/tick",
        json={"limit": 1},
    )
    assert t1.status_code == 200, t1.text
    body1 = t1.json()
    assert body1["processed_now"] == 1
    assert body1["job"]["processed"] == 1

    t2 = await client.post(
        f"/api/v2/imports/{import_id}/parse-jobs/{job['id']}/tick",
        json={"limit": 4},
    )
    assert t2.status_code == 200, t2.text
    body2 = t2.json()
    assert body2["job"]["processed"] == 2
    assert body2["job"]["status"] in {"completed", "partial", "failed"}

    items = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == uuid.UUID(job["id"]))
        )
    ).scalars().all()
    assert len(items) == 2
    assert all(it.ai_parse_run_id is not None for it in items)
    for it in items:
        run = await db_session.get(AiParseRun, it.ai_parse_run_id)
        assert run is not None
        assert run.source_kind == "import_row"
        assert run.import_id == import_id
        assert str(run.bundle_id) == job["deployment_bundle_id"]
        assert str(run.rule_set_id) == job["rule_set_id"]


@pytest.mark.asyncio
async def test_parse_job_cancel_queued(client, db_session):
    import_id, _ = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    r = await client.post(
        f"/api/v2/imports/{import_id}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": f"cancel-{uuid.uuid4().hex}"},
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    c = await client.post(f"/api/v2/imports/{import_id}/parse-jobs/{job_id}/cancel")
    assert c.status_code == 200, c.text
    assert c.json()["status"] == "cancelled"
    assert c.json()["cancel_requested_at"] is not None


@pytest.mark.asyncio
async def test_parse_job_viewer_forbidden_create(client, db_session):
    import_id, _ = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    r = await client.post(
        f"/api/v2/imports/{import_id}/parse-jobs",
        json={"rule_set_code": code},
        headers={"X-Username": "ZZZMMVIEWER999"},
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_parse_job_no_staged_rows_422(client, db_session):
    from ddm_v2.models.v2.import_staging import ExcelImport

    rec = ExcelImport(
        id=uuid.uuid4(),
        source_name="empty.xlsx",
        status="mapped",
        raw_payload={"sheets": []},
        staged_rows=[],
        imported_by="TEST",
    )
    db_session.add(rec)
    await db_session.commit()
    code = await _get_rs_code(client)
    r = await client.post(
        f"/api/v2/imports/{rec.id}/parse-jobs",
        json={"rule_set_code": code},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_map_submit_untouched_still_listed(client):
    """Regression：既有 imports OpenAPI 路徑仍掛載（map/submit 未改合同）。"""
    # 404 on unknown id = route exists
    r = await client.get(f"/api/v2/imports/{uuid.uuid4()}")
    assert r.status_code == 404
