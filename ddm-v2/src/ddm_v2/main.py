"""DDM v2 FastAPI application（純 v2 API；legacy 已移除）。

- Async database lifecycle
- Centralized exception handling
- CORS middleware
- v2 routers：MOST 引擎計算 / Level 驗證 / worksheet 持久化 / 詞彙 / 範本庫 / 匯出 / rule-set / 使用者管理
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

# v2 定點重建路由
from ddm_v2.api.routes.v2.admin_users import router as v2_admin_router
from ddm_v2.api.routes.v2.ai_review import router as v2_ai_review_router
from ddm_v2.api.routes.v2.audit_log import router as v2_audit_log_router
from ddm_v2.api.routes.v2.calculate import router as v2_calculate_router
from ddm_v2.api.routes.v2.cases import router as v2_cases_router
from ddm_v2.api.routes.v2.catalog import router as v2_catalog_router
from ddm_v2.api.routes.v2.export import router as v2_export_router
from ddm_v2.api.routes.v2.import_excel import router as v2_import_router
from ddm_v2.api.routes.v2.motion_module import router as v2_motion_module_router
from ddm_v2.api.routes.v2.motion_template import router as v2_motion_template_router
from ddm_v2.api.routes.v2.nl_draft import router as v2_nl_draft_router
from ddm_v2.api.routes.v2.parse_jobs import router as v2_parse_jobs_router
from ddm_v2.api.routes.v2.rule_set import router as v2_ruleset_router
from ddm_v2.api.routes.v2.search import router as v2_search_router
from ddm_v2.api.routes.v2.synonyms import router as v2_synonyms_router
from ddm_v2.api.routes.v2.vocab import router as v2_vocab_router
from ddm_v2.api.routes.v2.wi_set import router as v2_wi_set_router
from ddm_v2.api.routes.v2.worksheet import router as v2_worksheet_router
from ddm_v2.auth.startup_checks import (  # noqa: F401  （TRUSTED_GATEWAY_ENV 對外沿用舊匯入路徑）
    TRUSTED_GATEWAY_ENV,
    warn_if_identity_config_insecure,
)
from ddm_v2.database import get_engine
from ddm_v2.exceptions import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from ddm_v2.schemas.common import ErrorDetail, ErrorResponse
from ddm_v2.services.v2.rule_set_service import NoActiveRuleSet
from ddm_v2.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "ddm-v2-release-candidate-202603-rc1-secure-key"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動初始化 async engine + 驗證安全設定；關閉時釋放連線。"""
    settings = get_settings()
    _validate_startup_security(settings)

    engine = get_engine()
    app.state.engine = engine

    yield

    await engine.dispose()


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

    # v2 路由
    app.include_router(v2_calculate_router)
    app.include_router(v2_worksheet_router)
    app.include_router(v2_vocab_router)
    app.include_router(v2_motion_template_router)
    app.include_router(v2_motion_module_router)
    app.include_router(v2_export_router)
    app.include_router(v2_import_router)
    app.include_router(v2_ruleset_router)
    app.include_router(v2_admin_router)
    app.include_router(v2_catalog_router)
    app.include_router(v2_search_router)
    app.include_router(v2_synonyms_router)
    app.include_router(v2_nl_draft_router)
    app.include_router(v2_ai_review_router)
    app.include_router(v2_parse_jobs_router)
    app.include_router(v2_audit_log_router)
    app.include_router(v2_cases_router)
    app.include_router(v2_wi_set_router)

    _register_exception_handlers(app)

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


def _register_exception_handlers(app: FastAPI) -> None:
    """把 domain 例外對映到 HTTP 狀態 + 統一錯誤格式。"""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(error=ErrorDetail(code="NOT_FOUND", message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(error=ErrorDetail(code="VALIDATION_ERROR", message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
        error_code = (exc.detail or {}).get("code") or "CONFLICT"
        if error_code == "CONFLICT":
            if "published" in exc.message.lower():
                error_code = "VERSION_PUBLISHED"
            elif "time_source" in exc.message.lower():
                error_code = "TIME_SOURCE_IMMUTABLE"
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(error=ErrorDetail(code=error_code, message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=ErrorResponse(error=ErrorDetail(code="FORBIDDEN", message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_error_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=ErrorResponse(error=ErrorDetail(code="UNAUTHORIZED", message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(NoActiveRuleSet)
    async def no_active_rule_set_handler(request: Request, exc: NoActiveRuleSet) -> JSONResponse:
        """ADR-023 §3.5：無 active rule-set＝系統設定錯誤（非使用者錯誤）→ 500，不得靜默 fallback。"""
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=ErrorDetail(code="NO_ACTIVE_RULE_SET", message=str(exc))).model_dump(),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        """併發 activate 的敗方（撞 uq_rule_sets_single_active）→ 409 可重試，而非裸 500。

        ADR-023 §3.2：partial unique index 是「恆有且僅有一個 active」的 DB 防線；
        它被觸發代表另一交易剛搶先啟用，屬可重試的衝突，不是伺服器故障。
        其他 IntegrityError 維持既有 500 語意（不吞錯）。
        """
        if "uq_rule_sets_single_active" in str(exc.orig):
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(error=ErrorDetail(
                    code="RULE_SET_ACTIVATE_CONFLICT",
                    message="另一個規則版本剛被啟用，請重新整理後再試",
                )).model_dump(),
            )
        raise exc

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=ErrorDetail(code="INTERNAL_ERROR", message=exc.message, detail=exc.detail)).model_dump(),
        )


app = create_app()
