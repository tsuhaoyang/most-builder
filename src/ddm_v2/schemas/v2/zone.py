"""區域、DSX 物件清單、座標同步、物件歸區（ADR-038 D5，W7a）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_ZONES_PER_SKU = 200
MAX_ASSIGNMENTS_PER_REQUEST = 500


def _strip(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class ZoneCategoryOut(BaseModel):
    id: uuid.UUID
    code: str
    name_zh: str
    name_en: str
    sort_order: int
    builtin: bool


class ZoneCategoryIn(BaseModel):
    """admin 新增類別（D5.3：固定清單可新增）。內建類別不能改。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name_zh: str = Field(min_length=1, max_length=50)
    name_en: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(default=100, ge=0, le=10_000)

    _s = field_validator("name_zh", "name_en", mode="before")(_strip)


class Point3(BaseModel):
    x: float
    y: float
    z: float


class ZoneOut(BaseModel):
    id: uuid.UUID
    sku_id: uuid.UUID
    category_id: uuid.UUID
    name: str
    dsx_object_id: str | None
    # 站內局部座標（公分，原點＝作業員站位）；沒同步過或 DSX 沒有這個物件時為 null
    center: Point3 | None
    center_snapshot_id: uuid.UUID | None
    updated_at: datetime


class ZoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    dsx_object_id: str | None = Field(default=None, min_length=1, max_length=200)

    _s = field_validator("name", "dsx_object_id", mode="before")(_strip)


class ZonePatchIn(BaseModel):
    """改了 `dsx_object_id` 會清掉中心座標，要重新同步。"""

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    dsx_object_id: str | None = Field(default=None, min_length=1, max_length=200)

    _s = field_validator("name", "dsx_object_id", mode="before")(_strip)


class ZoneListOut(BaseModel):
    sku_id: uuid.UUID
    zones: list[ZoneOut]
    # 最近一次同步（沒同步過為 null）
    last_snapshot: SnapshotOut | None = None


class DsxObjectOut(BaseModel):
    id: str
    label_zh: str
    vocab_code: str | None
    visible: bool


DsxUnavailable = Literal["integration_disabled", "dsx_unreachable"]


class DsxObjectListOut(BaseModel):
    """DSX 連不到時 `available=false` 並帶原因，不會回空清單假裝沒有物件（D5.3）。"""

    available: bool
    reason: DsxUnavailable | None = None
    objects: list[DsxObjectOut] = Field(default_factory=list)


class SnapshotOut(BaseModel):
    id: uuid.UUID
    sku_id: uuid.UUID
    dsx_station_id: str
    placement_revision: int
    synced_by: str
    synced_at: datetime
    placement_count: int


class SyncOut(BaseModel):
    snapshot: SnapshotOut
    # 前一份快照（第一次同步為 null）：DSX 站別或版本和上次不同時，畫面要提示（D5.4：同步進哪個 SKU 靠使用者）
    previous_snapshot: SnapshotOut | None = None
    zones: list[ZoneOut]
    # 綁了 DSX 物件、但快照裡沒有那個物件的區域（中心座標已清空）
    missing_zone_ids: list[uuid.UUID]
    # 沒綁 DSX 物件的區域
    unbound_zone_ids: list[uuid.UUID]


class ObjectZoneOut(BaseModel):
    vocab_item_id: uuid.UUID
    zone_id: uuid.UUID
    object_point: Point3 | None
    assigned_by: str
    assigned_at: datetime


class ObjectZoneItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vocab_item_id: uuid.UUID
    zone_id: uuid.UUID | None  # null＝取消歸區


class ObjectZonesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ObjectZoneItemIn] = Field(min_length=1, max_length=MAX_ASSIGNMENTS_PER_REQUEST)


class ObjectZoneListOut(BaseModel):
    sku_id: uuid.UUID
    items: list[ObjectZoneOut]


class WorksheetObjectOut(BaseModel):
    """這份 WI 用到的物件（去重）與目前的歸區（D5.2 步驟 3）。"""

    vocab_item_id: uuid.UUID
    kind: str
    name_zh: str
    name_en: str | None
    # 在哪些欄位出現（object／from／to／tool）與出現的列數
    roles: list[Literal["object", "from", "to", "tool"]]
    row_count: int
    zone_id: uuid.UUID | None


class WorksheetObjectsOut(BaseModel):
    worksheet_id: uuid.UUID
    sku_id: uuid.UUID
    objects: list[WorksheetObjectOut]


ZoneListOut.model_rebuild()
