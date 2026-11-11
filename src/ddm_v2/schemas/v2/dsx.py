"""DSX a3 距離查詢契約（DSX 整合 API 契約 v2 §3.1／§6）。"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

DsxUnavailableReason = Literal[
    "vocab_not_mapped", "dsx_object_not_found", "dsx_unreachable", "integration_disabled"
]


class A3DistanceIn(BaseModel):
    # wi_row_id：optional（2026-08-24 User 裁決，契約 §6）——workbench-v3/ 組新列時
    # （尚未存檔，id 只存在瀏覽器端）沒有真實 WiRow 可指。有值時寫入 §2.2 provenance
    # 快照（wi_row_dsx_suggestions）；None 時距離查詢照樣成立，只是不留出處紀錄。
    wi_row_id: UUID | None = None
    from_vocab_id: UUID
    to_vocab_id: UUID


class A3DistanceOut(BaseModel):
    available: bool
    distance_cm: float | None = None
    # DSX 已算好的水平／垂直分量原樣多傳一份給前端；MOST 端不判斷該填 reach_cm 還是
    # foot_cm（ADR-031 P1 未定案）。DSX 沒給就是 None，不代表查詢失敗。
    horizontal_cm: float | None = None
    vertical_cm: float | None = None
    provisional: bool | None = None
    measure_from_mode: str | None = None
    warnings: list[str] = Field(default_factory=list)
    queried_at: str | None = None
    reason: DsxUnavailableReason | None = None


class DsxUiUrlOut(BaseModel):
    """DSX 3D 擺放介面的網址（給前端開 iframe modal 用；未設定時為 null）。"""

    url: str | None = None
