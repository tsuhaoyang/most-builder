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


# ── security F3：idempotency key 以 import 為範圍 ──────────────────────────────
# mutation：create_parse_job 的查詢拿掉 import_id 條件 → 本測試紅（B 拿到 A 的 job）

@pytest.mark.asyncio
async def test_idempotency_key_scoped_per_import(client, db_session):
    import_a, _ = await _seed_mapped_import(db_session, n_rows=1)
    import_b, _ = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    key = f"shared-{uuid.uuid4().hex}"  # client 可控、跨 import 相同

    ra = await client.post(
        f"/api/v2/imports/{import_a}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": key},
    )
    assert ra.status_code == 201, ra.text
    rb = await client.post(
        f"/api/v2/imports/{import_b}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": key},
    )
    assert rb.status_code == 201, rb.text
    # 相同 key、不同 import → 各自的 job（不得回別人的）
    assert rb.json()["id"] != ra.json()["id"]
    assert rb.json()["import_id"] == str(import_b)
    # 相同 key、相同 import → 冪等命中同一 job
    ra2 = await client.post(
        f"/api/v2/imports/{import_a}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": key},
    )
    assert ra2.json()["id"] == ra.json()["id"]


# ── security F2：per-user 在途 job 配額 ────────────────────────────────────────
# mutation：create_parse_job 的配額檢查拿掉 → 本測試紅（第 2 個 job 201）

@pytest.mark.asyncio
async def test_inflight_job_quota_429(client, db_session, monkeypatch):
    from ddm_v2.services.v2 import parse_job_service as svc

    monkeypatch.setattr(svc, "MAX_INFLIGHT_JOBS_PER_USER", 1)
    import_a, _ = await _seed_mapped_import(db_session, n_rows=1)
    import_b, _ = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    key_a = f"quota-a-{uuid.uuid4().hex}"

    ra = await client.post(
        f"/api/v2/imports/{import_a}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": key_a},
    )
    assert ra.status_code == 201, ra.text  # 第 1 個在途 job

    rb = await client.post(
        f"/api/v2/imports/{import_b}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": f"quota-b-{uuid.uuid4().hex}"},
    )
    assert rb.status_code == 429, rb.text

    # 冪等重打（同 import 同 key）不受配額限制——命中既有 job 不是開新 job
    ra2 = await client.post(
        f"/api/v2/imports/{import_a}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": key_a},
    )
    assert ra2.status_code == 201, ra2.text
    assert ra2.json()["id"] == ra.json()["id"]


# ── Blocker 1a：超長描述標 review、不進 parser ─────────────────────────────────
# mutation：tick_job 的長度守衛拿掉 → 本測試紅（item 進 parser、last_error 非 TextTooLong）

@pytest.mark.asyncio
async def test_overlong_description_routed_to_review(client, db_session):
    from sqlalchemy import select

    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.models.v2.import_staging import ExcelImport, ImportRow
    from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS

    rec = ExcelImport(
        id=uuid.uuid4(),
        source_name="l4-overlong.xlsx",
        status="mapped",
        raw_payload={"sheets": []},
        sheet="Sheet1",
        header_row=0,
        column_map={"description": 0},
        time_unit="sec",
        staged_rows=[{"_row": 1, "description": "拿" * (MAX_PARSE_TEXT_CHARS + 1)}],
        imported_by="TEST",
    )
    db_session.add(rec)
    await db_session.commit()
    code = await _get_rs_code(client)
    r = await client.post(
        f"/api/v2/imports/{rec.id}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": f"overlong-{uuid.uuid4().hex}"},
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    t = await client.post(
        f"/api/v2/imports/{rec.id}/parse-jobs/{job_id}/tick", json={"limit": 4}
    )
    assert t.status_code == 200, t.text
    body = t.json()
    assert body["job"]["review"] == 1
    assert body["job"]["status"] in {"completed", "partial"}

    item = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == uuid.UUID(job_id))
        )
    ).scalar_one()
    assert item.status == "review"
    assert item.ai_parse_run_id is None  # 沒進 parser
    assert item.last_error["error_type"] == "TextTooLong"
    row = await db_session.get(ImportRow, item.import_row_id)
    assert row.status == "review"
