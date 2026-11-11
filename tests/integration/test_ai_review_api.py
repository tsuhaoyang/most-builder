"""AI review API 整合測試。"""
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


async def _make_run(client) -> str:
    code = await _get_rs_code(client)
    payload = {
        "text": f"審核測試{uuid.uuid4().hex[:6]}拿起DIMM重抓",
        "rule_set_code": code,
    }
    r = await client.post("/api/v2/worksheets/nl-draft", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["ai"]["run_id"]


async def test_post_review_replace_candidate_creates_synonym(client, db_session):
    from ddm_v2.models.v2.ai_ops import AiFeedbackCandidate

    run_id = await _make_run(client)
    body = {
        "events": [
            {
                "event_type": "replace_candidate",
                "target": {"action_id": "a1", "parameter": "G", "field": "g2.g_code"},
                "before": {"option_code": None, "review_reason": "no_candidate"},
                "after": {"option_code": "g_regrasp", "surface_text": "重抓"},
                "reason": "此站為重抓",
            }
        ],
        "ui_version": "test@l3",
    }
    r = await client.post(f"/api/v2/nl-drafts/{run_id}/reviews", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["event_ids"]
    assert data["candidate_ids"]

    cand = await db_session.get(AiFeedbackCandidate, uuid.UUID(data["candidate_ids"][0]))
    assert cand is not None
    assert cand.kind == "synonym"
    assert cand.status == "candidate"

    listed = await client.get(f"/api/v2/nl-drafts/{run_id}/reviews")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["event_type"] == "replace_candidate"


async def test_post_review_viewer_forbidden(client):
    run_id = await _make_run(client)
    body = {
        "events": [{"event_type": "accept_all"}],
        "ui_version": "test",
    }
    r = await client.post(
        f"/api/v2/nl-drafts/{run_id}/reviews",
        json=body,
        headers={"X-Username": "ZZZMMVIEWER999"},
    )
    assert r.status_code == 403, r.text


async def test_post_review_empty_events_422(client):
    run_id = await _make_run(client)
    r = await client.post(f"/api/v2/nl-drafts/{run_id}/reviews", json={"events": []})
    assert r.status_code == 422, r.text


async def test_post_review_unknown_run_404(client):
    body = {"events": [{"event_type": "accept_all"}]}
    r = await client.post(
        f"/api/v2/nl-drafts/{uuid.uuid4()}/reviews",
        json=body,
    )
    assert r.status_code == 404, r.text
