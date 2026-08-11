"""DDM v2 schemas。

v2 契約在 `ddm_v2.schemas.v2.*`；此處僅保留共用錯誤/分頁封套（common）。
（legacy domain schemas 已移除；隨之 `AuditAction` 也一併移除——它只服務已刪除的
legacy JSON-store routes，v2 的稽核動作字串由各 service 直接寫入 `workflow_audit_log`。）
"""
from __future__ import annotations

from ddm_v2.schemas.common import ErrorDetail, ErrorResponse, PaginatedResponse

__all__ = ["ErrorDetail", "ErrorResponse", "PaginatedResponse"]
