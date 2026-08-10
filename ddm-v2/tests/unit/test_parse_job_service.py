"""parse_job_service 單元測試（無 DB）。"""
from __future__ import annotations

from ddm_v2.services.v2 import parse_job_service as svc


def test_row_text_and_source_row_no():
    assert svc._row_text({"description": "  拿起  "}) == "拿起"
    assert svc._row_text({}) == ""
    assert svc._source_row_no({"_row": 7}, 0) == 7
    assert svc._source_row_no({}, 2) == 3


def test_job_to_dict_maps_review_count():
    class _J:
        id = __import__("uuid").uuid4()
        import_id = __import__("uuid").uuid4()
        idempotency_key = "k"
        status = "queued"
        total = 1
        processed = 0
        succeeded = 0
        review_count = 3
        failed = 0
        deployment_bundle_id = __import__("uuid").uuid4()
        rule_set_id = __import__("uuid").uuid4()
        requested_by = "IEC"
        cancel_requested_at = None
        started_at = None
        completed_at = None
        created_at = None

    d = svc.job_to_dict(_J())  # type: ignore[arg-type]
    assert d["review"] == 3
    assert "review_count" not in d


def test_claim_sql_reclaims_expired_leases():
    sql = " ".join(svc.CLAIM_SQL.split())
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "lease_expires_at < now()" in sql
    assert "status IN ('leased', 'running')" in sql


def test_classify_outcome_buckets():
    assert (
        svc._classify_outcome(
            routing_status="review", routing_reasons=[], has_complete_draft=True
        )[0]
        == "review"
    )
    assert (
        svc._classify_outcome(
            routing_status="auto", routing_reasons=[], has_complete_draft=True
        )[0]
        == "succeeded"
    )
    assert (
        svc._classify_outcome(
            routing_status="abstain", routing_reasons=[], has_complete_draft=False
        )[0]
        == "review"
    )
