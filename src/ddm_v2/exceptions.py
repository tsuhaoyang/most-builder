"""Domain exception hierarchy for DDM v2.

All domain-specific exceptions inherit from DomainError. These exceptions
are caught by centralized exception handlers in the FastAPI application
and translated to appropriate HTTP responses.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain exceptions."""

    def __init__(self, message: str, detail: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(DomainError):
    """Resource not found (HTTP 404)."""

    pass


class ValidationError(DomainError):
    """Request validation failed (HTTP 422)."""

    pass


class ConflictError(DomainError):
    """Resource state conflict (HTTP 409)."""

    pass


class ForbiddenError(DomainError):
    """User lacks permission for this operation (HTTP 403)."""

    pass


class UnauthorizedError(DomainError):
    """Authentication failed (HTTP 401)."""

    pass


class RateLimitedError(DomainError):
    """Too many requests / quota exceeded (HTTP 429).

    ADR-034 §A4：非 DomainError 家族的狀態碼子類。與家族子類同走
    ``error_handlers._envelope`` 收尾，享頂層 ``detail`` 相容鍵機制。
    """

    pass


class ServiceUnavailableError(DomainError):
    """Upstream/config not ready — retriable (HTTP 503).

    ADR-034 §A4：既有 route 以裸 ``HTTPException(status_code=503, detail=str(exc))``
    表達「設定錯誤（如 bundle 未 seed、integration 未設 base_url）」；收斂至此子類。
    """

    pass


class BadGatewayError(DomainError):
    """Upstream service unreachable / returned error (HTTP 502).

    ADR-034 §A4 加法：ADR-036 D7 的「LB 不可達／5xx」。與設定未就緒（503，
    ServiceUnavailableError）分開——502 是「上游確實連了但問不到／回錯」，可重試但成因在上游。
    原始上游狀態碼寫 log（見 lb_client），不放進對外 message。
    """

    pass


class GatewayTimeoutError(DomainError):
    """Upstream service timed out (HTTP 504).

    ADR-034 §A4 加法：ADR-036 D7 的「LB 逾時」（單次操作／總時限）。與 502（連不到／回錯）分開——
    504 是「上游還在回或太慢」，稍後再試可能成功。
    """

    pass


class PayloadTooLargeError(DomainError):
    """Request payload exceeds the allowed limit (HTTP 413).

    ADR-034 §A4：上傳位元組超限（import_excel security F2 上限）收斂至此子類。
    """

    pass


class BadRequestError(DomainError):
    """Malformed request / semantic input error (HTTP 400).

    ADR-034 §A4 batch 5：rule-set 版本級端點以裸 ``HTTPException(status_code=400,
    detail=str(exc))`` 表達「帶界／區塊鍵／multiplier 等 payload 語意錯誤、以及狀態機
    非法轉移（如 activate 非 published、retire 啟用中）」。這些歷史上就是 400（不是
    422 的 schema 級錯，也不是 409 的資源衝突），故收斂至此子類以**位元級保留既有狀態碼**
    （I2）。與家族子類同走 ``error_handlers._envelope`` 收尾，享頂層 ``detail`` 相容鍵機制。
    """

    pass
