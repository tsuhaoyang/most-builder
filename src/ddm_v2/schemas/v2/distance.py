"""距離建議與距離設定（ADR-038 D5.6 修訂，W7b）。"""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_APPLY_ROWS = 5000


class DistanceSuggestionOut(BaseModel):
    wi_row_id: uuid.UUID
    slot: Literal["a0", "a3", "m3", "a6"]
    status: Literal["suggested", "needs_ie", "unavailable"]
    field: Literal["reach_cm", "foot_cm", "distance_cm"] | None
    distance_cm: float | None
    # needs_ie：a6_over_threshold｜m_over_75｜m_component_missing｜m_components_multiple
    # unavailable：endpoint_missing｜not_assigned｜zone_not_synced
    reason: str | None
    # {"from": {...}, "to": {...}}：role、vocab_item_id、zone_id、point、source（person_offset｜zone_center｜
    # object_coordinate）、point_source（anchor｜station_local）、snapshot_id、reason
    endpoints: dict[str, Any]
    snapshot_id: uuid.UUID | None
    threshold_cm: float
    person_offset_cm: list[float]
    modeling_policy_version_id: uuid.UUID | None
    computed_by: str
    computed_at: datetime
    applied_by: str | None
    applied_at: datetime | None


class DistanceSuggestionListOut(BaseModel):
    worksheet_id: uuid.UUID
    items: list[DistanceSuggestionOut]


class DistanceApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: int = Field(ge=1)
    # 使用者看到的那一次計算（建議的 computed_at）；之後有人重新算過 → 409，不套用沒看過的值
    computed_at: datetime
    wi_row_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_APPLY_ROWS)


class DistanceSettingsIn(BaseModel):
    """admin 發布新的距離設定（建模政策新版本，之後新建的工時表才用；既有工時表不變）。"""

    model_config = ConfigDict(extra="forbid")

    reach_foot_threshold_cm: float = Field(gt=0, le=300)
    person_offset_cm: list[float] = Field(min_length=3, max_length=3)

    @field_validator("person_offset_cm")
    @classmethod
    def _bounded(cls, v: list[float]) -> list[float]:
        if any(not math.isfinite(x) or abs(x) > 300 or round(x, 1) != x for x in v):
            raise ValueError("each offset must be finite, within ±300 cm, with at most one decimal place")
        return v

    @field_validator("reach_foot_threshold_cm")
    @classmethod
    def _finite(cls, v: float) -> float:
        # 記錄欄位是 0.1 cm 精度；計算與記錄要一致，所以只接受到小數一位
        if not math.isfinite(v) or round(v, 1) != v:
            raise ValueError("threshold must be finite with at most one decimal place")
        return v


class DistanceSettingsOut(BaseModel):
    modeling_policy_version_id: uuid.UUID
    version_no: int
    reach_foot_threshold_cm: float
    person_offset_cm: list[float]
    # policy＝該版本有距離設定；default＝沒有，用預設值（70 cm、肩高 140 cm）
    source: Literal["policy", "default"]
