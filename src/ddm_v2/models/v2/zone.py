"""SKU 標準工作站的區域、DSX 座標快照、物件歸區（ADR-038 D5.1–D5.5；migration v2_0054）。

MOST 沒有工位：一個 SKU 一個標準工作站（D5.1），所以全部按 `skus.id` 保存，不按工序版本。
座標是站內局部座標（公分，原點＝作業員站位），只來自使用者按「同步」時拉到的 DSX 快照（D5.4、I6）。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk


def _now_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class ZoneCategory(Base):
    __tablename__ = "zone_categories"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now_col()

    __table_args__ = (
        UniqueConstraint("code", name="uq_zone_categories_code"),
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{0,39}$'", name="code_format"),
    )


class SkuPlacementSnapshot(Base):
    __tablename__ = "sku_placement_snapshots"

    id: Mapped[UUID] = uuid_pk()
    sku_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False)
    dsx_station_id: Mapped[str] = mapped_column(Text, nullable=False)
    placement_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    # [{object_id, x, y, z, point_source}]；point_source＝anchor｜station_local
    placements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    placement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    synced_by: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime] = _now_col()

    __table_args__ = (Index("ix_sku_placement_snapshots_sku_synced", "sku_id", "synced_at"),)


class SkuZone(Base):
    __tablename__ = "sku_zones"

    id: Mapped[UUID] = uuid_pk()
    sku_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("zone_categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dsx_object_id: Mapped[str | None] = mapped_column(Text)
    center_x: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    center_y: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    center_z: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    center_snapshot_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_placement_snapshots.id", ondelete="SET NULL")
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now_col()
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _now_col()

    __table_args__ = (
        UniqueConstraint("sku_id", "name", name="uq_sku_zones_sku_name"),
        UniqueConstraint("id", "sku_id", name="uq_sku_zones_id_sku"),
        CheckConstraint(
            "(center_x IS NULL) = (center_y IS NULL) AND (center_y IS NULL) = (center_z IS NULL)",
            name="center_complete",
        ),
    )


class SkuObjectZone(Base):
    __tablename__ = "sku_object_zones"

    sku_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), primary_key=True)
    vocab_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="CASCADE"), primary_key=True
    )
    zone_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    # D5.5 預留：物件自己的座標（有就優先用，否則用所屬區域中心）
    object_x: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    object_y: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    object_z: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    assigned_by: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_at: Mapped[datetime] = _now_col()

    __table_args__ = (
        ForeignKeyConstraint(
            ["zone_id", "sku_id"], ["sku_zones.id", "sku_zones.sku_id"],
            name="fk_sku_object_zones_zone_same_sku", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(object_x IS NULL) = (object_y IS NULL) AND (object_y IS NULL) = (object_z IS NULL)",
            name="object_complete",
        ),
        Index("ix_sku_object_zones_zone", "zone_id"),
    )
