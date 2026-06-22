"""Excel 匯入契約（Phase 2a，ADR-013）。"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

# 可對應的「我們的欄位」（小而可擴）。description 必填。
TARGET_FIELDS: list[str] = ["description", "part_no", "hand", "seconds", "quantity", "element_class", "notes"]
REQUIRED_FIELDS: list[str] = ["description"]


class SheetPreview(BaseModel):
    name: str
    grid: list[list[Any]]   # 已截斷的原始格（供選表頭/欄位）
    n_rows: int
    n_cols: int


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    sheet_hint: str | None
    header_row: int | None
    column_map: dict[str, int]
    time_unit: str | None
    owner: str | None


class UploadOut(BaseModel):
    import_id: uuid.UUID
    source_name: str | None
    target_fields: list[str] = Field(default_factory=lambda: list(TARGET_FIELDS))
    required_fields: list[str] = Field(default_factory=lambda: list(REQUIRED_FIELDS))
    sheets: list[SheetPreview]
    suggested_sheet: str | None
    suggested_header_row: int | None
    profiles: list[ProfileOut] = Field(default_factory=list)


class MapIn(BaseModel):
    sheet: str
    header_row: int
    column_map: dict[str, int]      # our_field -> 0-based 欄索引
    time_unit: str = "sec"          # 'sec' | 'min'


class PreviewOut(BaseModel):
    import_id: uuid.UUID
    fields: list[str]
    rows: list[dict[str, Any]]      # 正規化後的列（含 _row 原列號）
    n: int
    warnings: list[str]


class ProfileIn(BaseModel):
    name: str
    sheet_hint: str | None = None
    header_row: int | None = None
    column_map: dict[str, int]
    time_unit: str = "sec"
