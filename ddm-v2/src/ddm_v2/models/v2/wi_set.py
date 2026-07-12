"""WI Set Project：跨工序表「專案包」聚合模型。

WiSetProject  — 專案頭（metadata + status 生命週期）。
WiSetItem     — 專案內各 WI 項目（快照 + 排序 seq_no）。

設計原則：
- wi_template_id 為 soft ref（nullable UUID），不加 FK，避免刪版本時連帶刪包。
- 快照欄（wi_code/name/action_count/total_tmu/total_seconds）在加入時由 service 填入，
  之後獨立儲存——原 WI 改版不影響已入包的快照。
- seq_no 由 service 管理：max+1 新增、陣列重寫 reorder。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class WiSetProject(Base, TimestampMixin):
    """WI 集合專案（專案頭）。"""

    __tablename__ = "wi_set_projects"

    id: Mapped[UUID] = uuid_pk()
    project_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    site: Mapped[str | None] = mapped_column(Text)
    bu: Mapped[str | None] = mapped_column(Text)
    process: Mapped[str | None] = mapped_column(Text)
    family: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'draft'")
    )  # draft / active / archived
    created_by: Mapped[str] = mapped_column(Text, nullable=False)

    items: Mapped[list[WiSetItem]] = relationship(
        back_populates="project",
        order_by="WiSetItem.seq_no",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_wi_set_projects_status_valid",
        ),
    )


class WiSetItem(Base, TimestampMixin):
    """專案內 WI 條目（快照 + 排序）。"""

    __tablename__ = "wi_set_items"

    id: Mapped[UUID] = uuid_pk()
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wi_set_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # soft ref — 不加 FK 避免版本刪除時 cascade 破壞包
    wi_template_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    wi_code_snapshot: Mapped[str | None] = mapped_column(Text)
    wi_name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    action_count_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_tmu_snapshot: Mapped[float] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("0")
    )
    total_seconds_snapshot: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=text("0")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped[WiSetProject] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "seq_no", name="uq_wi_set_items_project_id_seq_no"
        ),
    )
