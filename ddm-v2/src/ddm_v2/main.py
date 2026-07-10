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

# v2 定點重建路由
from ddm_v2.api.routes.v2.admin_users import router as v2_admin_router
from ddm_v2.api.routes.v2.calculate import router as v2_calculate_router
from ddm_v2.api.routes.v2.catalog import router as v2_catalog_router
from ddm_v2.api.routes.v2.export import router as v2_export_router
from ddm_v2.api.routes.v2.import_excel import router as v2_import_router
from ddm_v2.api.routes.v2.motion_module import router as v2_motion_module_router
from ddm_v2.api.routes.v2.motion_template import router as v2_motion_template_router
from ddm_v2.api.routes.v2.nl_draft import router as v2_nl_draft_router
from ddm_v2.api.routes.v2.rule_set import router as v2_ruleset_router
from ddm_v2.api.routes.v2.search import router as v2_search_router
from ddm_v2.api.routes.v2.synonyms import router as v2_synonyms_router
from ddm_v2.api.routes.v2.vocab import router as v2_vocab_router
from ddm_v2.api.routes.v2.worksheet import router as v2_worksheet_router
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


def create_app(settings: Settings | None = None) -> FastAPI:
    """建立 FastAPI app（middleware / v2 routers / 例外處理）。"""
    app_settings = settings or get_settings()

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
        error_code = "CONFLICT"
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

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=ErrorDetail(code="INTERNAL_ERROR", message=exc.message, detail=exc.detail)).model_dump(),
        )


app = create_app()
