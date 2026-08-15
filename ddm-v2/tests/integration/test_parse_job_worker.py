"""parse_job_worker 整合測試（真 DB；worker 直接驅動，不走 API tick）。

涵蓋（對應 impl 硬約束）:
- worker 會撿起 queued job 並推進到終態（不再依賴 API 手動 tick）
- 單一 job tick 爆炸 → 迴圈存活、其他 job 照跑、poison job 被標 failed
- claim／lease 語意：lease 有效期間第二個 worker 認領不到同批 items；
  lease 過期後可 reclaim（多實例安全的可觀察契約）

mutation 對應（證據見交付回報）：
- run_worker_pass 的 per-job try/except 拿掉 → poison 測試紅（例外直接炸出）
- svc.fail_job 呼叫（_fail_job_isolated）拿掉 → poison 測試紅（job 停在 queued）
- fail_job 只標 job 不收尾 items → poison 測試紅（終態 job 帶 active items）
- CLAIM_SQL 的 status／lease 過濾破壞 → claim 測試紅（重複認領或 reclaim 失效）
- CLAIM_SQL 的 attempt_count 上限拿掉 → attempts-exhausted 測試紅（毒 item 被 reclaim）
- 失敗分類拿掉（infra 也判死）→ infra 測試紅（暫時性失敗 job 被標 failed）
- fail_job 繞過 _finalize_job_status 直寫 status="failed" → partial／cancelled
  兩條終態測試紅（n_rows=1 首 tick 毒殺的既有測試分不出「直寫」與「計算」——
  succeeded=0 時兩者同為 failed；這兩條讓旁路現形）

範圍註記：FOR UPDATE SKIP LOCKED 的「鎖層」語意需要兩條未提交交易（兩條實體
連線）才能演示，而 conftest 的 savepoint 隔離明令測試不得自建 engine 連真實
DB。本檔測的是同一份 CLAIM_SQL 的 status／lease 認領契約（跨實例在 commit 後
可觀察的行為）；鎖層由 unit 的 CLAIM_SQL 文字守衛
（test_claim_sql_reclaims_expired_leases）＋ PostgreSQL 語意涵蓋。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

TERMINAL = {"completed", "partial", "failed", "cancelled"}
MAX_PASSES = 10  # 迴圈保險絲：正常情況 2~3 輪內收斂


async def _get_rs_code(client) -> str:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set，略過")
    return r.json()[0]["code"]


async def _seed_mapped_import(db_session, *, n_rows: int = 2):
    from ddm_v2.models.v2.import_staging import ExcelImport

    rows = [
        {"_row": i + 1, "description": f"拿起零件{i + 1}worker測試{uuid.uuid4().hex[:4]}"}
        for i in range(n_rows)
    ]
    rec = ExcelImport(
        id=uuid.uuid4(),
        source_name="worker-test.xlsx",
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
    return rec.id


async def _create_job(client, import_id, code: str) -> str:
    r = await client.post(
        f"/api/v2/imports/{import_id}/parse-jobs",
        json={"rule_set_code": code, "idempotency_key": f"worker-{uuid.uuid4().hex}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_worker_pass_picks_up_and_advances_queued_job(client, db_ctx, db_session):
    """queued job 不再需要 API tick——worker pass 自己撿起並推進到終態。"""
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.services.v2 import parse_job_worker

    import_id = await _seed_mapped_import(db_session, n_rows=2)
    code = await _get_rs_code(client)
    job_id = await _create_job(client, import_id, code)

    body = None
    for _ in range(MAX_PASSES):
        await parse_job_worker.run_worker_pass(db_ctx, batch=4, worker_id="it-worker-1")
        g = await client.get(f"/api/v2/imports/{import_id}/parse-jobs/{job_id}")
        assert g.status_code == 200
        body = g.json()
        if body["status"] in TERMINAL:
            break
    assert body is not None
    assert body["status"] in {"completed", "partial"}, body
    assert body["processed"] == 2

    items = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == uuid.UUID(job_id))
        )
    ).scalars().all()
    assert len(items) == 2
    assert all(it.ai_parse_run_id is not None for it in items)


async def test_single_job_failure_isolated_and_marked_failed(
    client, db_ctx, db_session, monkeypatch
):
    """poison job（tick 直接爆炸）不得殺掉迴圈：其他 job 照跑、poison 標 failed。"""
    from ddm_v2.services.v2 import parse_job_service, parse_job_worker

    import_a = await _seed_mapped_import(db_session, n_rows=1)  # 先建 → FIFO 先被撿
    import_b = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    job_a = await _create_job(client, import_a, code)
    job_b = await _create_job(client, import_b, code)

    real_tick = parse_job_service.tick_job

    async def tick_with_poison(session, *, import_id, job_id, **kw):
        if str(job_id) == job_a:
            raise RuntimeError("boom: simulated structural tick failure")
        return await real_tick(session, import_id=import_id, job_id=job_id, **kw)

    monkeypatch.setattr(parse_job_service, "tick_job", tick_with_poison)

    body_b = None
    for _ in range(MAX_PASSES):
        # 錯誤隔離拿掉的話，RuntimeError 會從這裡炸出 → 測試紅
        await parse_job_worker.run_worker_pass(db_ctx, batch=4, worker_id="it-worker-2")
        gb = await client.get(f"/api/v2/imports/{import_b}/parse-jobs/{job_b}")
        body_b = gb.json()
        if body_b["status"] in TERMINAL:
            break

    # 同輪的其他 job 不受 poison 影響
    assert body_b is not None
    assert body_b["status"] in {"completed", "partial"}, body_b
    assert body_b["processed"] == 1

    # poison job 被標 failed（而非 worker 死掉或無限重炸）
    ga = await client.get(f"/api/v2/imports/{import_a}/parse-jobs/{job_a}")
    body_a = ga.json()
    assert body_a["status"] == "failed", body_a
    assert body_a["completed_at"] is not None

    # Blocker 2：判死必須收尾——不得出現「終態 job ＋ active items」的組合，
    # import_rows 也不得卡在 queued/processing（否則 idempotency 命中回 failed
    # job 後整批 import 死透）。
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.models.v2.import_staging import ImportRow
    from ddm_v2.services.v2 import parse_job_service as svc

    items_a = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == uuid.UUID(job_a))
        )
    ).scalars().all()
    assert items_a, "poison job 應已 materialize items"
    assert all(it.status not in svc.ACTIVE_ITEM for it in items_a), [
        it.status for it in items_a
    ]
    rows_a = (
        await db_session.execute(select(ImportRow).where(ImportRow.import_id == import_a))
    ).scalars().all()
    assert all(r.status not in {"queued", "processing"} for r in rows_a), [
        r.status for r in rows_a
    ]


async def test_claim_lease_semantics_no_double_claim(client, db_session):
    """多實例安全的認領契約：lease 有效不得重複認領；lease 過期可 reclaim。"""
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.services.v2 import parse_job_service

    import_id = await _seed_mapped_import(db_session, n_rows=2)
    code = await _get_rs_code(client)
    job_id = uuid.UUID(await _create_job(client, import_id, code))

    # worker A 認領全部
    got_a = await parse_job_service._claim_items(
        db_session, job_id=job_id, limit=4, worker_id="worker-A"
    )
    assert len(got_a) == 2

    # lease 有效期間，worker B 認領同一 job → 空手（不重複處理）
    got_b = await parse_job_service._claim_items(
        db_session, job_id=job_id, limit=4, worker_id="worker-B"
    )
    assert got_b == []

    # worker A 掛掉（lease 過期）→ worker B 必須能 reclaim，item 不得永久卡死
    await db_session.execute(
        update(AiParseJobItem)
        .where(AiParseJobItem.job_id == job_id)
        .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db_session.flush()
    got_b2 = await parse_job_service._claim_items(
        db_session, job_id=job_id, limit=4, worker_id="worker-B"
    )
    assert sorted(got_b2) == sorted(got_a)

    items = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == job_id)
        )
    ).scalars().all()
    assert all(it.lease_owner == "worker-B" for it in items)
    assert all(it.attempt_count == 2 for it in items)  # A 認領 +1、B reclaim +1


# ── Blocker 1c：attempt 耗盡的毒 item 有終點 ───────────────────────────────────

async def test_exhausted_poison_item_not_reclaimed_and_job_terminates(
    client, db_session
):
    """attempt 耗盡＋lease 過期的 item：不再被 claim、被收屍標 failed、job 到終態。

    情境＝毒 item 讓 worker「掛住而非丟例外」：每次都走 claim（attempt+1）然後
    卡死到 lease 過期，永遠不會進 tick 的 MAX_ATTEMPTS 例外路徑。
    """
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.models.v2.import_staging import ImportRow
    from ddm_v2.services.v2 import parse_job_service as svc

    import_id = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    job_id = uuid.UUID(await _create_job(client, import_id, code))

    # 模擬「已被 claim MAX_ATTEMPTS 次、每次都掛住到 lease 過期」的毒 item
    await db_session.execute(
        update(AiParseJobItem)
        .where(AiParseJobItem.job_id == job_id)
        .values(
            status="leased",
            attempt_count=svc.MAX_ATTEMPTS,
            lease_owner="dead-worker",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    await db_session.flush()

    # mutation 錨：CLAIM_SQL 拿掉 attempt 上限 → 這裡會撿回毒 item → 紅
    got = await svc._claim_items(
        db_session, job_id=job_id, limit=4, worker_id="worker-C"
    )
    assert got == [], "attempt 耗盡的 item 不得再被 reclaim"

    # tick 收屍：item → failed、row → failed、job 到終態（不再永遠 running）
    out = await svc.tick_job(
        db_session, import_id=import_id, job_id=job_id, limit=4, worker_id="worker-C"
    )
    assert out["job"]["status"] == "failed", out["job"]
    item = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == job_id)
        )
    ).scalar_one()
    assert item.status == "failed"
    assert item.last_error["error_type"] == "AttemptsExhausted"
    row = await db_session.get(ImportRow, item.import_row_id)
    assert row.status == "failed"


# ── Blocker 1b：CPU 段超時 → item 失敗、event loop 存活 ─────────────────────────

async def test_stuck_parse_times_out_item_fails_loop_alive(
    client, db_session, monkeypatch
):
    """同步 CPU 段掛住 → wait_for 超時、item 標 failed、tick 期間 loop 仍在轉。

    mutation：wi_ai_service 拿掉 run_in_executor（直接同步呼叫）→ heartbeat
    餓死（beats≈0）且不會有 TimeoutError → 紅；拿掉 wait_for → item 不會失敗 → 紅。
    """
    import asyncio
    import time as _time

    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.services.v2 import parse_job_service as svc
    from ddm_v2.services.v2 import wi_ai_service

    def _stuck_normalize(text):
        _time.sleep(0.5)
        return "x", [0]

    monkeypatch.setattr(wi_ai_service, "normalize_with_map", _stuck_normalize)
    monkeypatch.setattr(wi_ai_service, "PARSE_CPU_TIMEOUT_S", 0.15)
    monkeypatch.setattr(svc, "MAX_ATTEMPTS", 1)  # 首次失敗即終態，免等 backoff

    import_id = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    job_id = uuid.UUID(await _create_job(client, import_id, code))

    beats = 0

    async def _heartbeat():
        nonlocal beats
        while True:
            beats += 1
            await asyncio.sleep(0.01)

    hb = asyncio.create_task(_heartbeat())
    try:
        out = await svc.tick_job(
            db_session, import_id=import_id, job_id=job_id, limit=4, worker_id="hb-worker"
        )
    finally:
        hb.cancel()

    assert out["job"]["status"] == "failed", out["job"]
    item = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == job_id)
        )
    ).scalar_one()
    assert item.status == "failed"
    assert item.last_error["error_type"] == "TimeoutError"
    # 超時窗（0.15s）內 heartbeat 理論 ~15 次；同步阻塞（mutation）時 0~1 次
    assert beats >= 5, f"event loop 在 CPU 段被卡住（beats={beats}）"


# ── Blocker 2：infra 暫時性失敗不判死 ──────────────────────────────────────────

async def test_infra_failure_does_not_mark_job_failed(client, db_ctx, db_session, monkeypatch):
    """pool 逾時/斷線類失敗 → job 保持 runnable 等下輪，不得判死。"""
    from sqlalchemy.exc import OperationalError

    from ddm_v2.services.v2 import parse_job_service, parse_job_worker

    import_id = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    job_id = await _create_job(client, import_id, code)

    async def infra_boom(session, **kw):
        raise OperationalError("SELECT 1", None, Exception("connection reset by peer"))

    monkeypatch.setattr(parse_job_service, "tick_job", infra_boom)
    await parse_job_worker.run_worker_pass(db_ctx, batch=4, worker_id="it-worker-3")

    g = await client.get(f"/api/v2/imports/{import_id}/parse-jobs/{job_id}")
    body = g.json()
    # mutation 錨：失敗分類拿掉（infra 也判死）→ status 變 failed → 紅
    assert body["status"] == "queued", body
    assert body["completed_at"] is None


# ── fail_job 終態必須「經 _finalize_job_status 計算」而非直寫 failed ────────────
# 既有 poison 測試（n_rows=1、首 tick 即毒殺）succeeded=0，_finalize 算出來也是
# failed——與「繞過 _finalize 直寫 failed」無法區分。下面兩條建出 succeeded>0 與
# cancel_requested 兩種前置狀態，讓終態計算（partial／cancelled）與直寫分道揚鑣。
# mutation：fail_job 改為 job.status="failed" 直寫（不走 _finalize）→ 兩條皆紅。

async def test_structural_failure_after_progress_finalizes_partial(
    client, db_ctx, db_session, monkeypatch
):
    """先成功推進 1 筆（succeeded/review ≥1）再結構性失敗 → 終態必須是 partial。"""
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.services.v2 import parse_job_service, parse_job_worker
    from ddm_v2.services.v2 import parse_job_service as svc

    import_id = await _seed_mapped_import(db_session, n_rows=2)
    code = await _get_rs_code(client)
    job_id = await _create_job(client, import_id, code)

    # 第一階段：直接 tick 推進 1 筆（limit=1），確保 succeeded+review ≥ 1
    out = await parse_job_service.tick_job(
        db_session,
        import_id=import_id,
        job_id=uuid.UUID(job_id),
        limit=1,
        worker_id="it-partial-1",
    )
    assert out["processed_now"] == 1
    j = out["job"]
    assert j["succeeded"] + j["review"] == 1, j
    assert j["status"] == "running"  # 還有 1 個 active item，不得提前終態
    await db_session.commit()

    # 第二階段：同一 job 之後的 tick 結構性失敗 → worker 判死收尾
    real_tick = parse_job_service.tick_job
    target_id = out["job"]["id"]

    async def tick_with_poison(session, *, import_id, job_id, **kw):
        if str(job_id) == target_id:
            raise RuntimeError("boom: structural failure after partial progress")
        return await real_tick(session, import_id=import_id, job_id=job_id, **kw)

    monkeypatch.setattr(parse_job_service, "tick_job", tick_with_poison)
    await parse_job_worker.run_worker_pass(db_ctx, batch=4, worker_id="it-partial-2")

    g = await client.get(f"/api/v2/imports/{import_id}/parse-jobs/{job_id}")
    body = g.json()
    # mutation 錨：fail_job 直寫 failed（繞過 _finalize）→ 這裡是 failed 而非 partial
    assert body["status"] == "partial", body
    assert body["completed_at"] is not None
    assert body["succeeded"] + body["review"] == 1
    assert body["failed"] == 1

    items = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == uuid.UUID(job_id))
        )
    ).scalars().all()
    assert all(it.status not in svc.ACTIVE_ITEM for it in items), [
        it.status for it in items
    ]


async def test_structural_failure_after_cancel_request_finalizes_cancelled(
    client, db_ctx, db_session, monkeypatch
):
    """cancel_requested_at 已設、之後結構性失敗 → 終態必須是 cancelled（非 failed）。"""
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.services.v2 import parse_job_service, parse_job_worker
    from ddm_v2.services.v2 import parse_job_service as svc

    import_id = await _seed_mapped_import(db_session, n_rows=2)
    code = await _get_rs_code(client)
    job_id = await _create_job(client, import_id, code)
    jid = uuid.UUID(job_id)

    # 佔住 1 個 item（leased、lease 未過期）→ cancel 請求後仍有 active item，
    # job 不會在 request_cancel 當下就收斂成 cancelled（那樣就測不到 fail_job 路徑）
    got = await parse_job_service._claim_items(
        db_session, job_id=jid, limit=1, worker_id="it-cancel-holder"
    )
    assert len(got) == 1
    cancelled_view = await parse_job_service.request_cancel(
        db_session, import_id=import_id, job_id=jid
    )
    assert cancelled_view["cancel_requested_at"] is not None
    assert cancelled_view["status"] not in TERMINAL, cancelled_view  # 還有 leased item
    await db_session.commit()

    async def tick_poison(session, *, import_id, job_id, **kw):
        raise RuntimeError("boom: structural failure with cancel pending")

    monkeypatch.setattr(parse_job_service, "tick_job", tick_poison)
    await parse_job_worker.run_worker_pass(db_ctx, batch=4, worker_id="it-cancel-2")

    g = await client.get(f"/api/v2/imports/{import_id}/parse-jobs/{job_id}")
    body = g.json()
    # mutation 錨：fail_job 直寫 failed → 這裡是 failed 而非 cancelled
    assert body["status"] == "cancelled", body
    assert body["completed_at"] is not None

    items = (
        await db_session.execute(
            select(AiParseJobItem).where(AiParseJobItem.job_id == jid)
        )
    ).scalars().all()
    assert len(items) == 2
    assert all(it.status not in svc.ACTIVE_ITEM for it in items), [
        it.status for it in items
    ]
    assert {it.status for it in items} == {"failed", "cancelled"}


# ── security F4 最小集：撤權即中止在途 job ─────────────────────────────────────

async def test_revoked_requester_jobs_skipped(client, db_session):
    """requested_by 已停權（is_active=False）→ _runnable_jobs 跳過；無 app_users 列照跑。"""
    from sqlalchemy import update as sa_update

    from ddm_v2.models.v2.ai_ops import AiParseJob
    from ddm_v2.models.v2.auth import AppUser
    from ddm_v2.services.v2 import parse_job_worker

    import_a = await _seed_mapped_import(db_session, n_rows=1)
    import_b = await _seed_mapped_import(db_session, n_rows=1)
    code = await _get_rs_code(client)
    job_revoked = uuid.UUID(await _create_job(client, import_a, code))
    job_ghost = uuid.UUID(await _create_job(client, import_b, code))

    revoked_no = f"ZZZREVOKED{uuid.uuid4().hex[:6]}"
    db_session.add(
        AppUser(id=uuid.uuid4(), employee_no=revoked_no, roles=["analyst"], is_active=False)
    )
    await db_session.execute(
        sa_update(AiParseJob).where(AiParseJob.id == job_revoked).values(requested_by=revoked_no)
    )
    # 無 app_users 列的 requester（JIT 建檔前的歷史 job）→ 不得因 join 而被跳過
    ghost_no = f"ZZZGHOST{uuid.uuid4().hex[:6]}"
    await db_session.execute(
        sa_update(AiParseJob).where(AiParseJob.id == job_ghost).values(requested_by=ghost_no)
    )
    await db_session.flush()

    runnable = {j for j, _ in await parse_job_worker._runnable_jobs(db_session)}
    assert job_revoked not in runnable, "已停權 requester 的 job 不得續跑"
    assert job_ghost in runnable, "無 app_users 列不得誤傷"

    # 復權 → 恢復可跑（撤權是暫停不是銷毀）
    await db_session.execute(
        sa_update(AppUser).where(AppUser.employee_no == revoked_no).values(is_active=True)
    )
    await db_session.flush()
    runnable2 = {j for j, _ in await parse_job_worker._runnable_jobs(db_session)}
    assert job_revoked in runnable2
