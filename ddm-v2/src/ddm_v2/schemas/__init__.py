"""DDM v2 schemas。

v2 契約在 `ddm_v2.schemas.v2.*`；此處僅保留共用錯誤/分頁封套（common）。
（legacy domain schemas 已移除。）
"""
from __future__ import annotations

from ddm_v2.schemas.common import AuditAction, ErrorDetail, ErrorResponse, PaginatedResponse

__all__ = ["AuditAction", "ErrorDetail", "ErrorResponse", "PaginatedResponse"]
