"""案件清單 API schema。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CaseVersionBrief(BaseModel):
    """案件歷史折疊用的版本摘要（按版本序＝created_at 由舊到新）。"""

    process_version_id: uuid.UUID
    worksheet_id: uuid.UUID
    version_no: str
    status: str
    total_tmu: float | None
    created_at: datetime
    approved_at: datetime | None


class CaseOut(BaseModel):
    """一筆＝一個案件（聚合鍵 sku_id × model_label），欄位取自代表版（最新版）。"""

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
    model_label: str | None = None       # 聚合鍵之一（MostWorksheet.model_label）
    version_count: int = 1               # 此案件的版本總數
    versions: list[CaseVersionBrief] = []  # 完整版本歷史（含代表版）


class CaseListOut(BaseModel):
    total: int  # 案件數（非版本數）
    items: list[CaseOut]
