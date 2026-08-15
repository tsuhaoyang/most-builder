"""ai_parse_jobs 背景 worker（docs/llm/wi-ai-parser-implementation-spec.md §12–13；
部署拓撲決策見 ADR-030；驅動 parse_job_service.tick_job）。

背景：L4 交付了 tick 邏輯與 4 個端點，但 lifespan 沒起任何背景任務——批次 job
建了不會自己跑，只能靠 API 手動 tick。本模組補上驅動器；**計算與狀態機語意
全部沿用 parse_job_service.tick_job，此處只負責排程**。

設計要點：

- **啟動/關閉**：main.lifespan 以 asyncio.Task 起 `run_worker_loop`；shutdown 時
  cancel 並 await。loop 任何一層都不吞 `CancelledError`（一律往上拋），
  shutdown 不會卡住、也不會把 cancel 誤當錯誤。
- **錯誤隔離（兩層）＋失敗分類**：
  1. job 層：結構性例外（job/rule-set 遺失、bundle 缺失＝RuntimeError）→ 立即
     判死並收尾 items（svc.fail_job）。其他例外視為 infra 暫時性（pool 逾時、
     DB 斷線、死鎖）→ 只 log 下輪重試；同一 job **連續**失敗達
     MAX_CONSECUTIVE_JOB_FAILURES 才判死——暫時性故障不得把 job 判死刑
     （否則 items 卡 queued、import_rows 卡 processing，idempotency 命中回
     failed job，整批 import 死透）。
  2. pass 層：撿 job 清單本身失敗（DB 短暫斷線等）→ log 後下一輪重試。
- **多實例／多 tick 的鎖語意（誠實版）**：item 認領用 `FOR UPDATE SKIP LOCKED`
  ＋ lease（CLAIM_SQL），兩實例各拿不相交的 items。但 job 挑選層**不是免鎖分工**
  ——tick 交易內對 ai_parse_jobs 的任何 UPDATE（queued→running、計數遞增）都握
  該列 row lock 直到 commit，期間另一實例的計數 UPDATE 與使用者的 Cancel 都會
  被擋。緩解：計數已改為交易尾端一次性遞增（鎖窗縮到 LLM 呼叫之後）；殘餘窗
  ＝首次 tick 的 queued→running 旗標，上限 ≈ batch×llm_timeout_s（4×8s=32s，
  預設 LLM 關閉時為毫秒級）。徹底解法（job 挑選 SKIP LOCKED／LLM 移出交易）
  留給 dedicated worker 抽離（ADR-030 觸發條件）。
- **開關/間隔**：settings（DDM_PARSE_WORKER_ENABLED / _INTERVAL_S / _BATCH）。
  預設開啟——compose 部署路徑不另設環境變數就會跑。有推進（processed>0）時
  立即續跑下一輪清 backlog，空轉才睡 interval。
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ddm_v2.models.v2.ai_ops import AiParseJob
from ddm_v2.models.v2.auth import AppUser
from ddm_v2.services.v2 import parse_job_service as svc
from ddm_v2.services.v2 import synonym_service as syn_svc

logger = logging.getLogger(__name__)

# 單輪最多撿幾個 job（防一輪吃太久；下一輪自然接續）
MAX_JOBS_PER_PASS = 20

# 同一 job 連續 infra 失敗達此數才判死：單次 pool 逾時/斷線是暫時性，
# 但「每輪都失敗」代表持續性問題（毒資料觸發非結構性例外等），不能無限重炸。
MAX_CONSECUTIVE_JOB_FAILURES = 5

# 結構性例外＝job 本身壞了，重試不可能好：判死並收尾。
# RuntimeError＝tick_job 對 pinned bundle 缺失的既定訊號（見 tick_job）。
STRUCTURAL_EXCEPTIONS = (svc.JobNotFound, syn_svc.RuleSetNotFound, RuntimeError)


def default_worker_id() -> str:
    """每個 app 實例唯一的 lease owner 標記（診斷 lease_owner 欄用）。"""
    return f"{svc.WORKER_ID_DEFAULT}-{socket.gethostname()}-{os.getpid()}"


async def _runnable_jobs(session: AsyncSession) -> list[tuple[UUID, UUID]]:
    """撿可推進的 job（FIFO）。回傳 [(job_id, import_id)]。

    security F4（最小集）：requester 已停權（app_users.is_active=False）的 job
    跳過——撤權即中止其在途工作。無 app_users 列者視同 active（JIT 建檔前的
    歷史 job 不因此卡死）。完整物件級授權（imported_by/site scope）見 worklog
    已知缺口。
    """
    rows = await session.execute(
        select(AiParseJob.id, AiParseJob.import_id)
        .join(AppUser, AppUser.employee_no == AiParseJob.requested_by, isouter=True)
        .where(
            AiParseJob.status.in_(svc.RUNNABLE_JOB_STATUSES),
            or_(AppUser.is_active.is_(True), AppUser.id.is_(None)),
        )
        .order_by(AiParseJob.created_at)
        .limit(MAX_JOBS_PER_PASS)
    )
    return [(r[0], r[1]) for r in rows.all()]


async def _fail_job_isolated(
    session_maker: async_sessionmaker[AsyncSession], job_id: UUID, *, reason: str
) -> None:
    """結構性失敗收尾：獨立 session 走 svc.fail_job（tick session 可能已髒/已 rollback）。

    fail_job 會一併收尾 active items 與 import_rows，並經 _finalize_job_status
    計算終態——不得寫出「終態 job ＋ active items」的組合。此函式自身失敗
    （DB 斷線）只 log：worker 存活優先，下一輪該 job 會再被 tick、再失敗、
    再嘗試收尾。
    """
    try:
        async with session_maker() as session:
            await svc.fail_job(session, job_id=job_id, reason=reason)
            await session.commit()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("parse worker：無法收尾 job=%s（下一輪重試）", job_id)


async def run_worker_pass(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    batch: int,
    worker_id: str,
    failure_counts: dict[UUID, int] | None = None,
) -> int:
    """跑一輪：撿 runnable jobs、逐 job 各開一個 session/transaction tick。

    回傳本輪 processed 件數。**單 job 失敗不得中斷本輪**（錯誤隔離第 1 層）；
    CancelledError 一律往上拋。``failure_counts`` 由 run_worker_loop 持有，
    跨輪累計同一 job 的連續 infra 失敗（成功即歸零）。
    """
    async with session_maker() as session:
        jobs = await _runnable_jobs(session)

    if failure_counts is not None:
        # 只保留仍 runnable 的 job（其他實例收尾掉的不留殘鍵）
        current = {job_id for job_id, _ in jobs}
        for stale in [k for k in failure_counts if k not in current]:
            failure_counts.pop(stale, None)

    processed = 0
    for job_id, import_id in jobs:
        try:
            async with session_maker() as session:
                out = await svc.tick_job(
                    session,
                    import_id=import_id,
                    job_id=job_id,
                    limit=batch,
                    worker_id=worker_id,
                )
                await session.commit()
            processed += int(out.get("processed_now") or 0)
            if failure_counts is not None:
                failure_counts.pop(job_id, None)
        except asyncio.CancelledError:
            raise
        except STRUCTURAL_EXCEPTIONS as exc:
            # job 本身壞了（pinned rule-set/bundle 遺失、job 資料損壞）：
            # 重試不可能變好 → 判死並收尾 items/rows。
            logger.exception("parse worker：job=%s 結構性失敗，判死並收尾", job_id)
            await _fail_job_isolated(
                session_maker, job_id, reason=f"{type(exc).__name__}: {exc}"
            )
            if failure_counts is not None:
                failure_counts.pop(job_id, None)
        except Exception as exc:
            # infra 暫時性（pool 逾時、DB 斷線、死鎖…）：判死是錯的——job 沒壞，
            # 環境壞了。只 log 下輪重試；連續失敗達上限才視為持續性問題判死。
            count = 1
            if failure_counts is not None:
                count = failure_counts.get(job_id, 0) + 1
                failure_counts[job_id] = count
            if count >= MAX_CONSECUTIVE_JOB_FAILURES:
                logger.exception(
                    "parse worker：job=%s 連續失敗 %s 次（上限 %s），判死並收尾",
                    job_id,
                    count,
                    MAX_CONSECUTIVE_JOB_FAILURES,
                )
                await _fail_job_isolated(
                    session_maker,
                    job_id,
                    reason=(
                        f"連續失敗 {count} 次（最後：{type(exc).__name__}）"
                    ),
                )
                if failure_counts is not None:
                    failure_counts.pop(job_id, None)
            else:
                logger.exception(
                    "parse worker：job=%s tick 失敗（第 %s 次，暫時性；下輪重試）",
                    job_id,
                    count,
                )
    return processed


async def run_worker_loop(
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    *,
    interval_s: float,
    batch: int,
    worker_id: str | None = None,
) -> None:
    """週期驅動 pending jobs 直到被 cancel（lifespan shutdown）。

    session_maker 可注入（測試用）；預設用全域 get_session_maker()。
    有推進時立即續跑（backlog 不等 interval），空轉才睡。
    """
    if session_maker is None:
        from ddm_v2.database import get_session_maker

        session_maker = get_session_maker()
    wid = worker_id or default_worker_id()
    if batch > svc.MAX_TICK_LIMIT:
        # tick_job 為保 lease 窗（LEASE_SECONDS vs 批次耗時）以 MAX_TICK_LIMIT 封頂；
        # 顯式 clamp + 警告，不靜默吞掉設定值。
        logger.warning(
            "parse worker：DDM_PARSE_WORKER_BATCH=%s 超過 tick 上限 %s，以上限執行",
            batch,
            svc.MAX_TICK_LIMIT,
        )
        batch = svc.MAX_TICK_LIMIT
    # WARNING 級：uvicorn 預設 root logger 只出 WARNING+（INFO 在 docker logs
    # 完全看不見），這行是「worker 有沒有在跑」唯一的啟動證據，必須可觀測。
    logger.warning(
        "parse worker 啟動：interval=%ss batch=%s worker_id=%s", interval_s, batch, wid
    )
    failure_counts: dict[UUID, int] = {}
    while True:
        progressed = False
        try:
            n = await run_worker_pass(
                session_maker, batch=batch, worker_id=wid, failure_counts=failure_counts
            )
            progressed = n > 0
            if n:
                logger.info("parse worker：本輪推進 %s 筆", n)
        except asyncio.CancelledError:
            raise  # shutdown：不吞、不 log 成錯誤
        except Exception:
            # 錯誤隔離第 2 層：撿 job 清單等 infra 例外（DB 短暫斷線）。
            # job 層失敗已在 run_worker_pass 內隔離，不會走到這裡。
            logger.exception("parse worker：本輪失敗，%ss 後重試", interval_s)
        if not progressed:
            # backlog 清空（或本輪失敗）才睡；有推進就立即續跑，清空 backlog
            # 不用等 interval × 批次數。
            await asyncio.sleep(interval_s)
        else:
            # 立即續跑仍必須讓出 loop 一次：連續推進的 pass 若都不 suspend，
            # while True 會餓死同 loop 的其他 task（含 HTTP handler）。
            await asyncio.sleep(0)
