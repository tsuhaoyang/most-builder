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
