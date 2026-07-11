"""案件清單 API schema。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CaseOut(BaseModel):
    process_version_id: uuid.UUID
    worksheet_id: uuid.UUID
    version_no: str
    status: str  # draft / approved / retired
    site_id: uuid.UUID
    site_name: str
    product_id: uuid.UUID
    product_name: str
    sku_id: uuid.UUID
    sku_name: str
    process_name: str  # SKU.name_zh（ProcessVersion 無 process_name 欄）
    approved_at: datetime | None  # ProcessVersion.published_at
    created_at: datetime
    total_tmu: float | None


class CaseListOut(BaseModel):
    total: int
    items: list[CaseOut]
