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
    BadRequestError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitedError,
    ServiceUnavailableError,
    UnauthorizedError,
    ValidationError,
)
from ddm_v2.schemas.common import ErrorDetail, ErrorResponse
from ddm_v2.services.v2.policy_service import NoDefaultPolicy
from ddm_v2.services.v2.rule_set_service import NoActiveRuleSet


def _envelope(code: str, message: str, detail: dict | None, status_code: int) -> JSONResponse:
    """共用信封收尾 + 過渡期相容鍵處理（ADR-034 §D1 + §7 KI-034-1 B 方案）。

    5 個 DomainError 家族 handler（NotFound/Validation/Conflict/Forbidden/Unauthorized）
    共用同一條收尾路徑，確保新信封 ``{error:{code,message,detail}}`` 形狀一致。

    **相容鍵機制（維持既有 integration 斷言不破壞）**：raise 點若在 ``detail`` 內放保留鍵
    ``"_compat_detail"``（值＝該端點歷史上頂層 ``detail`` 的內容，中文字串或 dict 皆可），
    本函式收尾時：
      1. ``payload = ErrorResponse(...).model_dump()`` 先產出新信封；
      2. ``compat = (detail or {}).get("_compat_detail")``；
      3. 若 ``compat`` 非 None，則把頂層 ``payload["detail"]`` 設為 ``compat``（還原歷史形狀），
         並從 ``payload["error"]["detail"]`` pop 掉 ``"_compat_detail"``——新信封不外露相容鍵。

    待階段 C 前端全數遷移到 ``error`` 信封後，移除相容鍵（追蹤見 ADR-034 §7 KI-034-1）。
    """
    payload = ErrorResponse(error=ErrorDetail(code=code, message=message, detail=detail or {})).model_dump()
    compat = (detail or {}).get("_compat_detail")
    if compat is not None:
        payload["detail"] = compat
        payload["error"]["detail"].pop("_compat_detail", None)
    return JSONResponse(status_code=status_code, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    """把 domain 例外對映到 HTTP 狀態 + 統一錯誤格式。"""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        error_code = (exc.detail or {}).get("code") or ErrorCode.NOT_FOUND
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_404_NOT_FOUND)

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        error_code = (exc.detail or {}).get("code") or ErrorCode.VALIDATION_ERROR
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
        # ADR-034 §D3/A3：code 一律由 raise 點顯式攜帶（exc.detail["code"]），
        # 不再靠 message.lower() 反推——訊息 i18n 化後字串比對會失配（§1.2）。
        error_code = (exc.detail or {}).get("code") or ErrorCode.CONFLICT
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_409_CONFLICT)

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        error_code = (exc.detail or {}).get("code") or ErrorCode.FORBIDDEN
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_403_FORBIDDEN)

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_error_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
        error_code = (exc.detail or {}).get("code") or ErrorCode.UNAUTHORIZED
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_401_UNAUTHORIZED)

    @app.exception_handler(RateLimitedError)
    async def rate_limited_handler(request: Request, exc: RateLimitedError) -> JSONResponse:
        """ADR-034 §A4：429（配額/速率限制）。走 _envelope 享頂層 detail 相容。"""
        error_code = (exc.detail or {}).get("code") or ErrorCode.RATE_LIMITED
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_429_TOO_MANY_REQUESTS)

    @app.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
        """ADR-034 §A4：503（設定錯誤，可重試）。走 _envelope 享頂層 detail 相容。"""
        error_code = (exc.detail or {}).get("code") or ErrorCode.SERVICE_UNAVAILABLE
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_503_SERVICE_UNAVAILABLE)

    @app.exception_handler(PayloadTooLargeError)
    async def payload_too_large_handler(request: Request, exc: PayloadTooLargeError) -> JSONResponse:
        """ADR-034 §A4：413（上傳超限）。走 _envelope 享頂層 detail 相容。"""
        error_code = (exc.detail or {}).get("code") or ErrorCode.PAYLOAD_TOO_LARGE
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    @app.exception_handler(BadRequestError)
    async def bad_request_handler(request: Request, exc: BadRequestError) -> JSONResponse:
        """ADR-034 §A4 batch 5：400（payload 語意錯誤／狀態機非法轉移）。

        rule-set 版本級端點歷史上以 400 表達帶界/區塊鍵/multiplier 非法與 activate/retire
        的非法狀態轉移；收斂至此子類以位元級保留既有狀態碼（I2）。走 _envelope 享頂層
        detail 相容。
        """
        error_code = (exc.detail or {}).get("code") or ErrorCode.BAD_REQUEST
        return _envelope(error_code, exc.message, exc.detail, status.HTTP_400_BAD_REQUEST)

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
