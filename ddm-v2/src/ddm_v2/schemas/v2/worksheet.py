"""v2 worksheet 持久化契約：存整份 WI（rows = wi_row + cycle + level）。"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from ddm_v2.schemas.v2.most import CycleIn


class LevelFieldsIn(BaseModel):
    coefficient: float = 1
    ascription: str | None = None
    level: str | None = None
    countersignature: str | None = None
    parent_countersignature: str | None = None
    order: int | None = None
    number: str | None = None
    number_count: int | None = None
    machine_count: int = 1
    manpower: int = 1


class WiRowSaveIn(BaseModel):
    id: uuid.UUID                       # 前端生成的穩定 id（F4）
    seq_no: int
    sub_activity: str | None = None
    key_parts: str | None = None
    hand: str | None = None
    object_vocab_id: uuid.UUID
    from_vocab_id: uuid.UUID | None = None
    to_vocab_id: uuid.UUID | None = None
    tool_vocab_id: uuid.UUID | None = None
    frequency: float = 1
    simo_group_id: str | None = None            # SIMO 標記＋配對資訊（ADR-020：非空＝該列貢獻 0；主列不標記）
    simo_with_row_id: uuid.UUID | None = None   # 輸入形式（E5 配對，service 僅標記從屬列）
    narrative: str | None = None        # 敘述（前端合成；存 most_cycles.narrative_zh，供匯出 METHOD）
    cycle: CycleIn
    level: LevelFieldsIn = Field(default_factory=LevelFieldsIn)


class WorksheetSaveIn(BaseModel):
    rows: list[WiRowSaveIn] = Field(default_factory=list)
    # 工序表級寬放%（OQ-002）：選填；未帶＝不動既有值（加法相容），帶 null＝清除。
    allowance_percent: float | None = Field(default=None, ge=0)


class WorksheetReadOut(BaseModel):
    worksheet_id: uuid.UUID
    status: str
    rows: list[dict[str, Any]]
    total_tmu: float
    # 時間投影（impl-02 §3）：normal＝引擎輸出；standard＝normal×(1+allowance%/100)，allowance 未設時為 null（OQ-002）。
    normal_seconds: float
    allowance_percent: float | None = None
    standard_seconds: float | None = None
