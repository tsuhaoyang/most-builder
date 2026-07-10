"""稽核日誌 API 契約（impl-06c）。

AuditLogEntry  — 單筆 workflow_audit_log 紀錄的輸出 schema。
AuditLogListOut — GET /api/v2/audit-log 的分頁回應。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    from_status: str | None
    to_status: str | None
    actor: str
    comment: str | None
    payload: dict[str, Any] | None
    created_at: datetime


class AuditLogListOut(BaseModel):
    total: int
    items: list[AuditLogEntry]
