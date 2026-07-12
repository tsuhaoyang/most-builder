"""WI Set Project API 契約（Pydantic v2）。

涵蓋 A-3 ~ A-7 所有 schema：建立 / 更新 / 條目 / 輸出 / 排序。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── 專案建立 / 更新 ──────────────────────────────────────────────────

class WiSetProjectCreate(BaseModel):
    """POST /wi-set-projects body。name 必填，其餘選填。"""

    project_code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=300)
    site: str | None = None
    bu: str | None = None
    process: str | None = None
    family: str | None = None
    model: str | None = None
    description: str | None = None


class WiSetProjectUpdate(BaseModel):
    """PUT /wi-set-projects/{id} body（全選填）。"""

    project_code: str | None = Field(None, min_length=1, max_length=100)
    name: str | None = Field(None, min_length=1, max_length=300)
    site: str | None = None
    bu: str | None = None
    process: str | None = None
    family: str | None = None
    model: str | None = None
    description: str | None = None
    status: str | None = None


# ── 條目建立 ────────────────────────────────────────────────────────

class WiSetItemCreate(BaseModel):
    """POST /wi-set-projects/{id}/items body。"""

    wi_template_id: uuid.UUID | None = None
    wi_code_snapshot: str | None = None
    wi_name_snapshot: str = Field(..., min_length=1, max_length=300)
    action_count_snapshot: int = Field(0, ge=0)
    total_tmu_snapshot: float = Field(0.0, ge=0)
    total_seconds_snapshot: float = Field(0.0, ge=0)
    notes: str | None = None


# ── 輸出 ─────────────────────────────────────────────────────────────

class WiSetItemOut(BaseModel):
    """WI 條目輸出（含 id / project_id / seq_no / timestamps）。"""

    id: uuid.UUID
    project_id: uuid.UUID
    seq_no: int
    wi_template_id: uuid.UUID | None
    wi_code_snapshot: str | None
    wi_name_snapshot: str
    action_count_snapshot: int
    total_tmu_snapshot: float
    total_seconds_snapshot: float
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WiSetProjectOut(BaseModel):
    """WI 專案輸出（含 id / items list / timestamps）。"""

    id: uuid.UUID
    project_code: str
    name: str
    site: str | None
    bu: str | None
    process: str | None
    family: str | None
    model: str | None
    description: str | None
    status: str
    created_by: str
    items: list[WiSetItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── 排序請求 ─────────────────────────────────────────────────────────

class ReorderRequest(BaseModel):
    """PUT /wi-set-projects/{id}/items/reorder body。"""

    ordered_ids: list[uuid.UUID] = Field(..., min_length=1)
