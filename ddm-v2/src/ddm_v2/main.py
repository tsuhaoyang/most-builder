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
from ddm_v2.api.routes.v2.cases import router as v2_cases_router
from ddm_v2.api.routes.v2.wi_set import router as v2_wi_set_router
from ddm_v2.api.routes.v2.audit_log import router as v2_audit_log_router
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


# 營運者用來「宣告本服務只經可信 gateway 可達」的環境變數。設了就不再發 C-1 警告。
# 刻意只當旗標、不做來源 IP/CIDR 比對：本專案的部署防線是拓撲（Traefik ForwardAuth ＋
# 只綁 loopback 的 port），在 app 內再加一層 IP 比對會讓本機開發與 CI 破功，收益卻有限。
TRUSTED_GATEWAY_ENV = "DDM_TRUSTED_GATEWAY"


def _warn_if_gateway_trust_unconfirmed() -> None:
    """gateway 模式且未宣告可信來源 → WARNING（ADR-023 D7 / C-1）。

    gateway 模式的身分**完全**來自入站的 `X-Username` header（見 auth/identity.py），
    它的安全性 100% 依賴「本服務只能經 gateway 進來」這個部署前提。前提一旦不成立
    （例如 app port 綁到 0.0.0.0），任何人都能零憑證取得 admin。這個前提在程式碼裡
    看不出來，所以至少要在啟動時講出來。

    **純 log**：不擋啟動、不改變任何行為——本機開發與 CI 都必須照常跑。
    """
    if os.getenv("DDM_AUTH_MODE", "gateway").lower() != "gateway":
        return
    if os.getenv(TRUSTED_GATEWAY_ENV):
        return
    logger.warning(
        "DDM_AUTH_MODE=gateway：本服務**信任入站的 X-Username header** 作為身分來源，"
        "沒有任何憑證檢查。請確認本服務只經 gateway（Traefik ForwardAuth）可達；"
        "若 app port 曝露到 loopback 以外，等同開放無認證的 admin 存取。"
        f"確認後設 {TRUSTED_GATEWAY_ENV}=1 可關閉本警告；"
        "需直接對外請改用 DDM_AUTH_MODE=verify。"
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """建立 FastAPI app（middleware / v2 routers / 例外處理）。"""
    app_settings = settings or get_settings()
    _warn_if_gateway_trust_unconfirmed()

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
