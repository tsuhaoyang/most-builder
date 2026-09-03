"""domain 例外 → HTTP 狀態 + 統一錯誤格式的唯一註冊入口。

原本這組 handler 只寫在 `main.create_app()` 裡（module 私有），`scripts/preview_server.py`
自建 app 時沒有它——同一個請求在正式 app 回 422 ＋ `I18N_REVIEW_TARGET_MISSING`，在預覽／
e2e 環境回裸 `500 Internal Server Error`。結果是「後端拒絕時要給清楚訊息」這件事在開發時
**永遠測不到**，前端只拿得到一句 Internal Server Error。

抽成獨立模組（而不是讓 preview_server 匯入 `main`）的理由：`main` 在 module 尾端就
`app = create_app()`，匯入它等於在預覽程序裡多建一個 app、順帶跑 CORS/安全設定驗證。
與 `route_registry` 同一個模式：**共用的東西只留一份，兩邊都呼叫它**。
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from ddm_v2.schemas.common import ErrorDetail, ErrorResponse
from ddm_v2.services.v2.policy_service import NoDefaultPolicy
from ddm_v2.services.v2.rule_set_service import NoActiveRuleSet


def register_exception_handlers(app: FastAPI) -> None:
    """把 domain 例外對映到 HTTP 狀態 + 統一錯誤格式。"""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(error=ErrorDetail(code=ErrorCode.NOT_FOUND, message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        error_code = (exc.detail or {}).get("code") or ErrorCode.VALIDATION_ERROR
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(error=ErrorDetail(code=error_code, message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
        # ADR-034 §D3/A3：code 一律由 raise 點顯式攜帶（exc.detail["code"]），
        # 不再靠 message.lower() 反推——訊息 i18n 化後字串比對會失配（§1.2）。
        error_code = (exc.detail or {}).get("code") or ErrorCode.CONFLICT
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(error=ErrorDetail(code=error_code, message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=ErrorResponse(error=ErrorDetail(code=ErrorCode.FORBIDDEN, message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_error_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=ErrorResponse(error=ErrorDetail(code=ErrorCode.UNAUTHORIZED, message=exc.message, detail=exc.detail)).model_dump(),
        )

    @app.exception_handler(NoActiveRuleSet)
    async def no_active_rule_set_handler(request: Request, exc: NoActiveRuleSet) -> JSONResponse:
        """ADR-023 §3.5：無 active rule-set＝系統設定錯誤（非使用者錯誤）→ 500，不得靜默 fallback。"""
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=ErrorDetail(code=ErrorCode.NO_ACTIVE_RULE_SET, message=str(exc))).model_dump(),
        )

    @app.exception_handler(NoDefaultPolicy)
    async def no_default_policy_handler(request: Request, exc: NoDefaultPolicy) -> JSONResponse:
        """R2a：缺 factory default published policy＝設定錯誤 → 500，不得靜默 NULL。"""
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=ErrorDetail(code=ErrorCode.NO_DEFAULT_POLICY, message=str(exc))).model_dump(),
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
                    code=ErrorCode.RULE_SET_ACTIVATE_CONFLICT,
                    message="另一個規則版本剛被啟用，請重新整理後再試",
                )).model_dump(),
            )
        raise exc

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """ADR-034 §D5/A2：把 FastAPI 預設 422 收斂進 {error:{code,message,detail}} 信封。

        預設 422 形狀是頂層 ``{detail: [...]}`` 且 msg 為英文（§1.2 中英夾雜的來源）。
        統一為 code=VALIDATION_ERROR；原始 loc/msg/type 陣列**原封不動**放進 detail.errors，
        供前端依 code + 結構化參數重組在地化訊息（§D1）。

        **過渡期向後相容（ADR-034 §5 + KNOWN-ISSUE KI-034-1）**：本 handler 改變了
        Pydantic request 驗證 422 的形狀——既有 integration 測試與前端呼叫點多處把頂層
        ``detail`` 當**陣列**讀（`for e in resp.json()["detail"]`）。為避免破壞既有契約，
        回應**同時保留頂層 ``detail`` 為原始 errors 陣列**（與 FastAPI 預設等價），
        與新的 ``error`` 信封並存。待 A4／前端 catalog 完成、呼叫點全數遷移到 ``error``
        後，於後續階段移除此頂層相容欄位（追蹤見 ADR-034 §7 KI-034-1）。
        """
        errors = jsonable_encoder(exc.errors())
        content = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message="請求驗證失敗",
                detail={"errors": errors},
            )
        ).model_dump()
        # 過渡期相容欄位：頂層 detail = 原始 errors 陣列（FastAPI 預設形狀）。
        content["detail"] = errors
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=content,
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error=ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message=exc.message, detail=exc.detail)).model_dump(),
        )
