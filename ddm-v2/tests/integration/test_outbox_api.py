"""R3b：outbox_events 與 review／save 同交易寫入。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"


async def _get_rs_code(client) -> str:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set，略過")
    return r.json()[0]["code"]


async def _make_run(client) -> str:
    code = await _get_rs_code(client)
    r = await client.post(
        "/api/v2/worksheets/nl-draft",
        json={"text": f"outbox審核{uuid.uuid4().hex[:6]}拿起DIMM", "rule_set_code": code},
    )
    assert r.status_code == 200, r.text
    return r.json()["ai"]["run_id"]


async def test_post_review_enqueues_outbox(client, db_session):
    from ddm_v2.models.v2.outbox import OutboxEvent
    from ddm_v2.services.v2.outbox_service import EVENT_REVIEW_RECORDED

    run_id = await _make_run(client)
    body = {
        "events": [{"event_type": "accept_all"}],
        "ui_version": "test@r3b",
    }
    r = await client.post(f"/api/v2/nl-drafts/{run_id}/reviews", json=body)
    assert r.status_code == 201, r.text
    event_ids = r.json()["event_ids"]

    rows = (
        await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.event_type == EVENT_REVIEW_RECORDED)
        )
    ).scalars().all()
    # 可能有其他測試寫入；找含此 run 的
    matched = [x for x in rows if (x.payload_json or {}).get("run_id") == run_id]
    assert len(matched) == 1
    ev = matched[0]
    assert ev.status == "pending"
    assert ev.payload_schema_version == "wi_ai.review_recorded.v1"
    assert ev.payload_json["review_event_ids"] == event_ids
    assert ev.aggregate_type in ("worksheet", "ai_parse_run")
    assert ev.event_no >= 1


async def test_save_enqueues_worksheet_saved(client, db_session):
    from ddm_v2.models.v2.outbox import OutboxEvent
    from ddm_v2.services.v2.outbox_service import EVENT_WORKSHEET_SAVED

    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    rev = (await client.get(f"/api/v2/worksheets/{new}")).json()["revision_no"]
    s = await client.put(f"/api/v2/worksheets/{new}", json={"base_revision": rev, "rows": []})
    assert s.status_code == 200, s.text
    new_rev = s.json()["revision_no"]

    rows = (
        await db_session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == EVENT_WORKSHEET_SAVED,
                OutboxEvent.aggregate_id == uuid.UUID(new),
            )
        )
    ).scalars().all()
    assert len(rows) >= 1
    last = max(rows, key=lambda x: x.event_no)
    assert last.status == "pending"
    assert last.aggregate_revision == new_rev
    assert last.payload_json["worksheet_id"] == new


async def test_claim_pending_and_mark_published(client, db_session):
    from ddm_v2.services.v2.outbox_service import (
        EVENT_REVIEW_RECORDED,
        claim_pending,
        mark_published,
    )

    run_id = await _make_run(client)
    r = await client.post(
        f"/api/v2/nl-drafts/{run_id}/reviews",
        json={"events": [{"event_type": "mark_missing"}], "ui_version": "t"},
    )
    assert r.status_code == 201, r.text

    claimed = await claim_pending(db_session, limit=50)
    ours = [c for c in claimed if c.event_type == EVENT_REVIEW_RECORDED
            and (c.payload_json or {}).get("run_id") == run_id]
    assert len(ours) == 1
    await mark_published(db_session, ours[0].id)
    await db_session.flush()

    claimed2 = await claim_pending(db_session, limit=50)
    again = [c for c in claimed2 if c.id == ours[0].id]
    assert again == []
