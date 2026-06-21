"""Common schemas shared across all API endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class AuditAction(str, Enum):
    """Audit log action types (used by legacy JSON-store routes)."""

    create = "CREATE"
    update = "UPDATE"
    delete = "DELETE"
    review = "REVIEW"
    publish = "PUBLISH"
    reset = "RESET"


class ErrorDetail(BaseModel):
    """Error response detail structure."""

    code: str = Field(..., description="Machine-readable error code (e.g., VERSION_PUBLISHED)")
    message: str = Field(..., description="Human-readable error message")
    detail: dict[str, Any] = Field(default_factory=dict, description="Additional context for the error")


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: ErrorDetail


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response structure.

    Used for all list endpoints that support pagination.
    """

    items: list[T] = Field(..., description="List of items in the current page")
    total: int = Field(..., ge=0, description="Total number of items across all pages")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
