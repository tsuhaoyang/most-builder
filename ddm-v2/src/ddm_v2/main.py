"""DDM v2 FastAPI application（純 v2 API；legacy 已移除）。

- Async database lifecycle
- Centralized exception handling
- CORS middleware
- v2 routers：MOST 引擎計算 / Level 驗證 / worksheet 持久化 / 詞彙 / 範本庫 / 匯出 / rule-set / 使用者管理
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# 例外 handler 與 v2 路由清單都抽在 api/ 底下：preview_server 共用同一份，不另抄
from ddm_v2.api.error_handlers import register_exception_handlers
from ddm_v2.api.route_registry import mount_v2_routers
from ddm_v2.auth.startup_checks import (  # noqa: F401  （TRUSTED_GATEWAY_ENV 對外沿用舊匯入路徑）
    TRUSTED_GATEWAY_ENV,
    warn_if_identity_config_insecure,
)
from ddm_v2.database import get_engine
from ddm_v2.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "ddm-v2-release-candidate-202603-rc1-secure-key"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動初始化 async engine + 背景 parse worker + 驗證安全設定；關閉時乾淨收尾。"""
    settings = get_settings()
    _validate_startup_security(settings)

    engine = get_engine()
    app.state.engine = engine

    # ai_parse_jobs 背景 worker（預設開啟；DDM_PARSE_WORKER_ENABLED=0 可關）。
    # 經 module attribute 呼叫（不 from-import 函式）讓測試可 monkeypatch。
    worker_task: asyncio.Task | None = None
    if settings.parse_worker_enabled:
        from ddm_v2.services.v2 import parse_job_worker

        worker_task = asyncio.create_task(
            parse_job_worker.run_worker_loop(
                interval_s=settings.parse_worker_interval_s,
                batch=settings.parse_worker_batch,
            ),
            name="ddm-parse-job-worker",
        )
        # 死亡不得靜默：worker 是無限迴圈，「非 cancel 的結束」一律是異常事件。
        # 沒有這個 callback 的話 task 例外無人 retrieve，app 看起來健康、job 永遠
        # 不動。ERROR/WARNING 級——uvicorn 預設 root logger 無 handler 時 INFO 會
        # 被丟（docker logs 實測看不見）。
        worker_task.add_done_callback(_log_worker_task_exit)
        app.state.parse_worker_task = worker_task

    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass  # 自己 cancel 的，屬預期
            except Exception:
                # worker 在 shutdown 前已死：task 完成後 cancel() 是 no-op，await
                # 會重拋它死時的例外——不接住的話 engine.dispose() 永遠不會執行、
                # shutdown 本身也會炸。死因已由 done callback 記錄過，這裡確保
                # dispose 必達。
                logger.exception("parse worker 於 shutdown 前已異常終止")
        await engine.dispose()


def _log_worker_task_exit(task: asyncio.Task) -> None:
    """背景 worker task 結束時記錄非預期死亡（並 retrieve 例外，避免靜默）。"""
    if task.cancelled():
        return  # shutdown 的正常路徑
    exc = task.exception()
    if exc is not None:
        logger.error("parse worker 意外終止（背景 job 已停擺，需重啟服務）", exc_info=exc)
    else:
        logger.warning("parse worker 迴圈非預期結束（無例外；背景 job 已停擺）")


def _validate_startup_security(settings) -> None:
    """偵測不安全設定時於 production raise、否則 warn。"""
    is_production = os.getenv("ENV", "development").lower() in {"production", "prod"}

    if settings.secret_key == _DEFAULT_SECRET:
        if is_production:
            raise RuntimeError(
                "DDM_SECRET_KEY must be changed before running in production. "
                "The default secret key is not secure."
            )
        logger.warning(
            "DDM_SECRET_KEY is using the default insecure value. "
            "Set DDM_SECRET_KEY environment variable before deploying to production."
        )

    if len(settings.secret_key) < 32:
        if is_production:
            raise RuntimeError(
                f"DDM_SECRET_KEY is too short ({len(settings.secret_key)} chars). "
                "Use at least 32 characters for production."
            )
        logger.warning(
            "DDM_SECRET_KEY is shorter than 32 characters. "
            "Use a longer, random secret for production."
        )


def _validate_cors_security(settings: Settings) -> None:
    """`allow_origins` 含萬用字元 ＋ `allow_credentials=True` → 啟動失敗（D7b · M-1）。

    Starlette 在這個組合下**不會**回 `Access-Control-Allow-Origin: *`，而是**鏡射請求的
    Origin** 並加 `Vary: Origin`——效果是「允許任意來源攜帶憑證」。在
    `DDM_AUTH_MODE=verify`（.env.example 建議值）下，受害者於 LB 登入後造訪惡意站，
    該站 `fetch(..., {credentials:'include'})` 就能讀走整份字典/worksheet/使用者清單，
    並發得出 PUT/DELETE。

    為什麼是 raise 而不是降級成 warn（或靜默拿掉 credentials）：
    - 設定未給時的 fallback 已在 `settings.py` 改成具體的 loopback 白名單，所以走到
      這個組合**只可能是有人顯式設了 `DDM_CORS_ALLOW_ORIGINS=*`**——那不是疏忽，是
      互斥的兩個要求同時被提出，沒有「作者其實想要哪個」可推測。
    - 靜默把 `allow_credentials` 改成 False 會讓合法的跨源登入在 runtime 才神秘失敗，
      屬於本 repo 硬規則禁止的「吞錯換通過」。
    與 secret key 的差別在於：預設值不安全是「沒設定」，可以在 dev 只 warn；這裡是
    「設定互相衝突」，無論哪個環境都無解，故一律 fail-closed。
    """
    if not settings.cors_allow_credentials:
        return
    if "*" not in settings.cors_allow_origins:
        return
    raise RuntimeError(
        "CORS 設定互斥：DDM_CORS_ALLOW_ORIGINS 含 '*' 且 DDM_CORS_ALLOW_CREDENTIALS=true。"
        "Starlette 在此組合下會鏡射任意 Origin 並允許攜帶憑證（等同對所有網站開放已登入的 API）。"
        "請改列出具體來源（例：DDM_CORS_ALLOW_ORIGINS=https://most.example.com），"
        "或在確實不需要 cookie/認證跨源時設 DDM_CORS_ALLOW_CREDENTIALS=false。"
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """建立 FastAPI app（middleware / v2 routers / 例外處理）。"""
    app_settings = settings or get_settings()
    warn_if_identity_config_insecure()
    _validate_cors_security(app_settings)

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allow_origins,
        allow_credentials=app_settings.cors_allow_credentials,
        allow_methods=app_settings.cors_allow_methods,
        allow_headers=app_settings.cors_allow_headers,
    )

    app.state.settings = app_settings

    # v2 路由：掛完會對帳（少一條就 raise）。沒有 API 的服務比啟動失敗更難察覺，
    # 且 FastAPI 0.141 已示範過「include_router 的結構會變」——見 route_registry docstring。
    mount_v2_routers(app)

    register_exception_handlers(app)

    # 服務已建置的 React 前端（src/frontend/dist）：有 build 就在根目錄出 SPA，否則導 /docs。
    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", response_model=None)
    def root():
        index = dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return RedirectResponse(url="/docs", status_code=302)

    return app


app = create_app()
