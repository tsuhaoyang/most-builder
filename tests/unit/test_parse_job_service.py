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


# ── Blocker 1c：CLAIM_SQL 的 attempt 上限（毒 item 終點）────────────────────────
# mutation：把 `attempt_count < :max_attempts` 從 CLAIM_SQL 拿掉 → 本測試紅
# （整合面：test_parse_job_worker.py 的 attempts-exhausted 測試一併紅）


def test_claim_sql_has_attempt_cap():
    sql = " ".join(svc.CLAIM_SQL.split())
    assert "attempt_count < :max_attempts" in sql


# ── 單一權威常數（小項 10）─────────────────────────────────────────────────────


def test_job_status_constants_are_single_source():
    # runnable + terminal 必須不重疊且合併後涵蓋 model CheckConstraint 的全集
    runnable = set(svc.RUNNABLE_JOB_STATUSES)
    terminal = set(svc.TERMINAL_JOB_STATUSES)
    assert runnable == {"queued", "running"}
    assert terminal == {"completed", "partial", "failed", "cancelled"}
    assert not (runnable & terminal)
    assert svc.MAX_TICK_LIMIT == 4  # LEASE_SECONDS=60 vs 4×llm_timeout 的推導值


def test_inflight_quota_default_is_pinned():
    """security F2 配額預設值防漂移：改 MAX_INFLIGHT_JOBS_PER_USER 必須同步改這裡。

    機制（429／冪等豁免不計數）由 tests/integration/test_parse_jobs_api.py::
    test_inflight_job_quota_429 以 monkeypatch 常數驗證——證明檢查動態讀這個常數
    （單一權威）；本測試釘的是部署實際生效的預設值本身。5 的依據見常數旁註解
    （單一 import 正常只產生一個 job，5 已涵蓋多份 import 平行解析）；要調整就
    連這裡一起改＝顯性決策，不會被順手改掉而無人知曉。
    """
    assert svc.MAX_INFLIGHT_JOBS_PER_USER == 5


def test_worker_reuses_service_status_constants():
    """worker 不得自抄一份狀態集合（小項 10 的 mutation 錨）。"""
    import inspect

    from ddm_v2.services.v2 import parse_job_worker

    src = inspect.getsource(parse_job_worker)
    assert "RUNNABLE_JOB_STATUSES" in src
    assert 'RUNNABLE_STATUSES = ("queued", "running")' not in src


# ── security F5：last_error 白名單化 ───────────────────────────────────────────
# mutation：_sanitize_error 改回 {"message": str(exc)} → 兩條 sanitize 測試紅


def test_sanitize_error_redacts_sql_and_bound_params():
    from sqlalchemy.exc import DBAPIError

    secret = "使用者原文-機密工序描述"
    exc = DBAPIError(
        statement="INSERT INTO ai_parse_runs (raw_text) VALUES (%s)",
        params=(secret,),
        orig=Exception("connection reset"),
    )
    out = svc._sanitize_error(exc)
    dumped = str(out)
    assert secret not in dumped
    assert "INSERT INTO" not in dumped
    assert out["error_type"] == "DBAPIError"


def test_sanitize_error_truncates_generic_message():
    out = svc._sanitize_error(RuntimeError("x" * 5000))
    assert out["error_type"] == "RuntimeError"
    assert len(out["message"]) <= 300
