"""parse_job_worker 單元測試（無 DB；pass／loop 以 stub 注入）。

涵蓋（對應 impl 硬約束）：
- 預設值：worker 預設開啟（「守門存在≠守門有在跑」——預設關閉沒人會開等於沒做）
- 迴圈存活：單輪 pass 爆炸（infra 例外）→ log 後下一輪繼續，worker 不死
- shutdown 乾淨：cancel 立即生效、CancelledError 不被吞、不卡住
- lifespan 佈線：enabled 起 task、shutdown cancel；disabled 完全不起
- 失敗分類（Blocker 2）：結構性例外才判死；infra 例外重試、連續達上限才判死
- worker 先死（Blocker 3）：shutdown 不炸、dispose 必達、死亡有 ERROR log
- backlog 立即續跑（小項 13）／batch 超上限 clamp＋警告（小項 12）

mutation 對應（證據見交付回報）：
- run_worker_loop 的 pass 層 try/except 拿掉 → test_loop_survives_pass_failure 紅
- lifespan 忘記 cancel → test_lifespan_starts_and_cancels_worker 紅
- 失敗分類拿掉（全部判死）→ test_infra_failure_retries_not_kills 紅
- fail_job 只標 job 不收尾 items → integration 的 poison 測試紅
- lifespan finally 的 except Exception 拿掉 → test_lifespan_survives_worker_predeath 紅
- 無條件 sleep（改回舊行為）→ test_loop_continues_immediately_on_progress 紅
- add_done_callback 拿掉 → test_worker_death_logged_while_app_still_running 紅
  （斷言全程在 lifespan context 內＝shutdown finally 的那句 log 救不了場；
  predeath 測試的斷言在 context 退出後，兩個機制在那裡無法區分）
- 啟動 log 降為 info/debug → test_startup_message_emitted_at_warning_level 紅
  （uvicorn 預設 root logger 只出 WARNING+，INFO 在 docker logs 看不見——
  這行是「worker 有沒有在跑」唯一的啟動證據）
"""
from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy.exc import OperationalError

from ddm_v2.services.v2 import parse_job_service as svc
from ddm_v2.services.v2 import parse_job_worker
from ddm_v2.settings import get_settings

pytestmark = pytest.mark.unit


class _FakeSession:
    async def commit(self) -> None:
        return None


class _FakeSessionMaker:
    """最小 async_sessionmaker 替身（測試 stub 掉 _runnable_jobs／tick_job 後不觸 DB）。"""

    def __call__(self):
        return self

    async def __aenter__(self) -> _FakeSession:
        return _FakeSession()

    async def __aexit__(self, *exc) -> bool:
        return False


# ── settings 預設值 ──────────────────────────────────────────────────

def test_worker_enabled_by_default(monkeypatch):
    """未設環境變數（＝compose 部署現況）時 worker 必須是開的。

    conftest 為測試確定性設了 DDM_PARSE_WORKER_ENABLED=0，此處刪掉模擬
    「沒人設定」的部署環境。
    """
    monkeypatch.delenv("DDM_PARSE_WORKER_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.parse_worker_enabled is True
        assert s.parse_worker_interval_s == 3.0
        assert s.parse_worker_batch == 4
    finally:
        get_settings.cache_clear()  # 別把「enabled」快取漏給其他測試


def test_worker_disabled_via_env(monkeypatch):
    monkeypatch.setenv("DDM_PARSE_WORKER_ENABLED", "0")
    get_settings.cache_clear()
    try:
        assert get_settings().parse_worker_enabled is False
    finally:
        get_settings.cache_clear()


# ── 迴圈存活與 shutdown ──────────────────────────────────────────────

async def test_loop_survives_pass_failure(monkeypatch):
    """第一輪 pass 丟例外 → loop 必須 log 後繼續跑下一輪（worker 不死）。"""
    calls: list[int] = []
    third_pass = asyncio.Event()

    async def flaky_pass(session_maker, *, batch, worker_id, failure_counts=None):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("simulated infra failure")
        if len(calls) >= 3:
            third_pass.set()
        return 0

    monkeypatch.setattr(parse_job_worker, "run_worker_pass", flaky_pass)
    task = asyncio.create_task(
        parse_job_worker.run_worker_loop(
            object(),  # type: ignore[arg-type]  # stub 不觸 DB
            interval_s=0.01,
            batch=1,
            worker_id="ut-worker",
        )
    )
    try:
        # 第 1 輪爆炸後仍到得了第 3 輪 ⇒ 錯誤被隔離、迴圈存活
        await asyncio.wait_for(third_pass.wait(), timeout=2)
    finally:
        task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) >= 3


async def test_loop_cancel_is_prompt_and_not_swallowed(monkeypatch):
    """cancel 發出後 loop 必須立刻結束（不卡住），且 CancelledError 往上拋。"""
    entered = asyncio.Event()

    async def slow_pass(session_maker, *, batch, worker_id, failure_counts=None):
        entered.set()
        await asyncio.sleep(3600)  # 模擬 tick 進行中被 shutdown
        return 0

    monkeypatch.setattr(parse_job_worker, "run_worker_pass", slow_pass)
    task = asyncio.create_task(
        parse_job_worker.run_worker_loop(
            object(),  # type: ignore[arg-type]
            interval_s=0.01,
            batch=1,
            worker_id="ut-worker",
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    # 若 loop 吞掉 CancelledError（或繼續睡），wait_for 會逾時 → 測試紅
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)


# ── lifespan 佈線 ────────────────────────────────────────────────────

async def test_lifespan_starts_and_cancels_worker(monkeypatch):
    """enabled → lifespan 起 task；shutdown → cancel 且不吞其他例外。"""
    from ddm_v2.main import create_app

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_loop(session_maker=None, *, interval_s, batch, worker_id=None):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(parse_job_worker, "run_worker_loop", fake_loop)
    monkeypatch.setenv("DDM_PARSE_WORKER_ENABLED", "1")
    get_settings.cache_clear()
    try:
        app = create_app()
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(started.wait(), timeout=2)
            task = app.state.parse_worker_task
            assert not task.done()
        # lifespan 退出（shutdown）後：worker 已被 cancel 且乾淨結束
        assert cancelled.is_set()
        assert task.cancelled()
    finally:
        get_settings.cache_clear()


async def test_lifespan_disabled_starts_no_worker(monkeypatch):
    """disabled（測試環境的預設）→ 完全不起背景 task。"""
    from ddm_v2.main import create_app

    monkeypatch.setenv("DDM_PARSE_WORKER_ENABLED", "0")
    get_settings.cache_clear()
    try:
        app = create_app()
        async with app.router.lifespan_context(app):
            assert getattr(app.state, "parse_worker_task", None) is None
    finally:
        get_settings.cache_clear()


# ── 失敗分類（Blocker 2）────────────────────────────────────────────────────────

def _uuid():
    import uuid

    return uuid.uuid4()


async def test_structural_failure_fails_job_immediately(monkeypatch):
    """JobNotFound（job 資料壞了）→ 第一次就判死收尾，不重試。"""
    job_id = _uuid()
    failed: list = []

    async def fake_runnable(session):
        return [(job_id, _uuid())]

    async def boom_tick(session, **kw):
        raise svc.JobNotFound(str(job_id))

    async def spy_fail(session_maker, jid, *, reason):
        failed.append((jid, reason))

    monkeypatch.setattr(parse_job_worker, "_runnable_jobs", fake_runnable)
    monkeypatch.setattr(svc, "tick_job", boom_tick)
    monkeypatch.setattr(parse_job_worker, "_fail_job_isolated", spy_fail)

    counts: dict = {}
    await parse_job_worker.run_worker_pass(
        _FakeSessionMaker(), batch=1, worker_id="ut", failure_counts=counts
    )
    assert [j for j, _ in failed] == [job_id]
    assert job_id not in counts  # 判死後不留殘鍵


async def test_infra_failure_retries_not_kills(monkeypatch):
    """OperationalError（DB 斷線等暫時性）→ 不判死；連續達上限才判死。

    mutation：把 infra 分支改成也走判死 → 第一輪 failed 非空 → 紅。
    """
    job_id = _uuid()
    failed: list = []

    async def fake_runnable(session):
        return [(job_id, _uuid())]

    async def flaky_tick(session, **kw):
        raise OperationalError("SELECT 1", None, Exception("connection reset"))

    async def spy_fail(session_maker, jid, *, reason):
        failed.append(jid)

    monkeypatch.setattr(parse_job_worker, "_runnable_jobs", fake_runnable)
    monkeypatch.setattr(svc, "tick_job", flaky_tick)
    monkeypatch.setattr(parse_job_worker, "_fail_job_isolated", spy_fail)

    counts: dict = {}
    for i in range(parse_job_worker.MAX_CONSECUTIVE_JOB_FAILURES - 1):
        await parse_job_worker.run_worker_pass(
            _FakeSessionMaker(), batch=1, worker_id="ut", failure_counts=counts
        )
        assert failed == [], f"第 {i + 1} 次暫時性失敗不得判死"
        assert counts[job_id] == i + 1

    # 連續失敗達上限 → 判死
    await parse_job_worker.run_worker_pass(
        _FakeSessionMaker(), batch=1, worker_id="ut", failure_counts=counts
    )
    assert failed == [job_id]
    assert job_id not in counts


async def test_infra_counter_resets_on_success(monkeypatch):
    """失敗計數是「連續」語意：一次成功就歸零，間歇性失敗永不判死。"""
    job_id = _uuid()
    failed: list = []
    fail_next = {"v": True}

    async def fake_runnable(session):
        return [(job_id, _uuid())]

    async def alternating_tick(session, **kw):
        if fail_next["v"]:
            fail_next["v"] = False
            raise OperationalError("SELECT 1", None, Exception("blip"))
        fail_next["v"] = True
        return {"processed_now": 1}

    async def spy_fail(session_maker, jid, *, reason):
        failed.append(jid)

    monkeypatch.setattr(parse_job_worker, "_runnable_jobs", fake_runnable)
    monkeypatch.setattr(svc, "tick_job", alternating_tick)
    monkeypatch.setattr(parse_job_worker, "_fail_job_isolated", spy_fail)

    counts: dict = {}
    for _ in range(parse_job_worker.MAX_CONSECUTIVE_JOB_FAILURES * 2):
        await parse_job_worker.run_worker_pass(
            _FakeSessionMaker(), batch=1, worker_id="ut", failure_counts=counts
        )
    assert failed == []


# ── backlog 立即續跑（小項 13）＋ batch clamp（小項 12）──────────────────────────

async def test_loop_continues_immediately_on_progress(monkeypatch):
    """有推進（n>0）不睡 interval；interval=3600 下 2 秒內必須跑到第 3 輪。"""
    calls: list[int] = []
    third = asyncio.Event()

    async def busy_pass(session_maker, *, batch, worker_id, failure_counts=None):
        calls.append(1)
        if len(calls) >= 3:
            third.set()
        return 1  # 每輪都有推進

    monkeypatch.setattr(parse_job_worker, "run_worker_pass", busy_pass)
    task = asyncio.create_task(
        parse_job_worker.run_worker_loop(
            object(),  # type: ignore[arg-type]
            interval_s=3600,  # 無條件睡的話（mutation）永遠到不了第 2 輪
            batch=1,
            worker_id="ut-worker",
        )
    )
    try:
        await asyncio.wait_for(third.wait(), timeout=2)
    finally:
        task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_loop_clamps_batch_above_tick_limit(monkeypatch, caplog):
    """DDM_PARSE_WORKER_BATCH 超過 tick 上限 → 以上限執行並 WARNING，不靜默截斷。"""
    seen: list[int] = []
    got = asyncio.Event()

    async def spy_pass(session_maker, *, batch, worker_id, failure_counts=None):
        seen.append(batch)
        got.set()
        return 0

    monkeypatch.setattr(parse_job_worker, "run_worker_pass", spy_pass)
    with caplog.at_level("WARNING", logger="ddm_v2.services.v2.parse_job_worker"):
        task = asyncio.create_task(
            parse_job_worker.run_worker_loop(
                object(),  # type: ignore[arg-type]
                interval_s=0.01,
                batch=32,
                worker_id="ut-worker",
            )
        )
        try:
            await asyncio.wait_for(got.wait(), timeout=2)
        finally:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert seen[0] == svc.MAX_TICK_LIMIT
    assert any("超過 tick 上限" in r.message for r in caplog.records)


# ── 啟動證據必須是 WARNING 級（可觀測性）────────────────────────────────────────

async def test_startup_message_emitted_at_warning_level(monkeypatch, caplog):
    """啟動訊息必須以 WARNING 級發出——那是部署環境唯一看得見的「worker 在跑」證據。

    以 DEBUG 級捕捉再斷言 levelno：mutation 把 logger.warning 降成 info/debug 時
    紀錄仍會被捕捉到，但 levelno 斷言紅（只斷言「有訊息」抓不到降級）。
    """
    got = asyncio.Event()

    async def idle_pass(session_maker, *, batch, worker_id, failure_counts=None):
        got.set()
        return 0

    monkeypatch.setattr(parse_job_worker, "run_worker_pass", idle_pass)
    with caplog.at_level(logging.DEBUG, logger="ddm_v2.services.v2.parse_job_worker"):
        task = asyncio.create_task(
            parse_job_worker.run_worker_loop(
                object(),  # type: ignore[arg-type]
                interval_s=0.01,
                batch=1,
                worker_id="ut-worker",
            )
        )
        try:
            await asyncio.wait_for(got.wait(), timeout=2)
        finally:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    startup = [r for r in caplog.records if "parse worker 啟動" in r.message]
    assert startup, "缺啟動訊息（worker 是否在跑將完全不可觀測）"
    assert startup[0].levelno == logging.WARNING, (
        f"啟動訊息是 {startup[0].levelname}——uvicorn 預設只出 WARNING+，"
        "降級後 docker logs 看不見"
    )


# ── worker 先死（Blocker 3）────────────────────────────────────────────────────

async def test_lifespan_survives_worker_predeath(monkeypatch, caplog):
    """worker 在 shutdown 前已死：shutdown 不得炸、engine.dispose 必達、死因有 ERROR log。

    最小重現（checkpoint 證實）：task 已完成時 cancel() 是 no-op、await 重拋
    → 舊版 finally 只接 CancelledError → dispose 永不執行、shutdown 炸。
    """
    from ddm_v2 import main as main_mod

    disposed = asyncio.Event()

    class _FakeEngine:
        async def dispose(self):
            disposed.set()

    died = asyncio.Event()

    async def doomed_loop(session_maker=None, *, interval_s, batch, worker_id=None):
        died.set()
        raise RuntimeError("simulated worker crash before shutdown")

    monkeypatch.setattr(main_mod, "get_engine", lambda: _FakeEngine())
    monkeypatch.setattr(parse_job_worker, "run_worker_loop", doomed_loop)
    monkeypatch.setenv("DDM_PARSE_WORKER_ENABLED", "1")
    get_settings.cache_clear()
    try:
        app = main_mod.create_app()
        with caplog.at_level("ERROR", logger="ddm_v2.main"):
            async with app.router.lifespan_context(app):
                await asyncio.wait_for(died.wait(), timeout=2)
                # 讓 task 真正結束、done callback 觸發
                await asyncio.sleep(0)
            # lifespan 正常退出（mutation：拿掉 except Exception → 這裡直接炸）
        assert disposed.is_set(), "worker 先死不得跳過 engine.dispose()"
        assert any(
            "意外終止" in r.message or "異常終止" in r.message for r in caplog.records
        ), "worker 死亡必須有 ERROR 級紀錄（否則死亡靜默）"
    finally:
        get_settings.cache_clear()


async def test_worker_death_logged_while_app_still_running(monkeypatch, caplog):
    """done callback 的獨有價值：**app 還在跑（未進 shutdown）時**就報告 worker 死亡。

    上面 predeath 測試的斷言在 lifespan context 退出後——lifespan finally 的
    「shutdown 前已異常終止」log 用另一個機制也能滿足它。此處斷言全程在 context
    內完成（shutdown 尚未發生、finally 那句還沒機會出現）：mutation 拆掉
    add_done_callback 時沒有任何機制能在 app 運行中留下 ERROR 紀錄 → 紅。
    """
    from ddm_v2 import main as main_mod

    died = asyncio.Event()

    async def doomed_loop(session_maker=None, *, interval_s, batch, worker_id=None):
        died.set()
        raise RuntimeError("simulated mid-flight worker crash")

    monkeypatch.setattr(parse_job_worker, "run_worker_loop", doomed_loop)
    monkeypatch.setenv("DDM_PARSE_WORKER_ENABLED", "1")
    get_settings.cache_clear()
    try:
        app = main_mod.create_app()
        with caplog.at_level(logging.ERROR, logger="ddm_v2.main"):
            async with app.router.lifespan_context(app):
                await asyncio.wait_for(died.wait(), timeout=2)
                task = app.state.parse_worker_task
                # 等 task 真正結束（asyncio.wait 不重拋例外），再讓出 loop
                # 幾次給 call_soon 排程的 done callback 執行
                await asyncio.wait({task}, timeout=2)
                for _ in range(10):
                    if any("意外終止" in r.message for r in caplog.records):
                        break
                    await asyncio.sleep(0)
                # ↓ 斷言在 shutdown 之前：此刻 lifespan 的 finally 尚未執行，
                #   「shutdown 前已異常終止」那句不可能救場
                death_logs = [r for r in caplog.records if "意外終止" in r.message]
                assert death_logs, (
                    "worker 死亡必須在 app 運行中即有 ERROR log（done callback）——"
                    "等到 shutdown 才知道＝停擺期間完全靜默"
                )
                assert death_logs[0].levelno == logging.ERROR
    finally:
        get_settings.cache_clear()
