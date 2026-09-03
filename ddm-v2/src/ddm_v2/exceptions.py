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


class PayloadTooLargeError(DomainError):
    """Request payload exceeds the allowed limit (HTTP 413).

    ADR-034 §A4：上傳位元組超限（import_excel security F2 上限）收斂至此子類。
    """

    pass
