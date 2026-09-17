"""LB 回寫消費快照（ADR-036 D4 / B1-B2）。

每次取得 LB `lb-most-writeback-v1` 回寫存一筆 snapshot（含原始 payload，契約升版後仍可解讀）
＋逐列 placement。回寫是唯讀快照，不是即時鏡像；屬性回流只有 offline（走 MOST 正門，B6）。
source_wi_row_id 不設 FK：可能指向已刪除或別份 worksheet 的列，比對在應用層（D7）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk


class LbWritebackSnapshot(Base):
    __tablename__ = "lb_writeback_snapshots"

    id: Mapped[UUID] = uuid_pk()
    worksheet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("most_worksheets.id", ondelete="CASCADE"), nullable=False
    )
    contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    lb_project_id: Mapped[str] = mapped_column(Text, nullable=False)
    lb_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    lb_result_id: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    unattended_machine_policy: Mapped[str] = mapped_column(Text, nullable=False)
    unattended_machine_policy_source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    # B6 套用紀錄（apply-offline）：未套用為 NULL。
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_rows: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_lb_writeback_snapshots_worksheet_fetched",
              "worksheet_id", text("fetched_at DESC")),
    )


class LbRowPlacement(Base):
    __tablename__ = "lb_row_placements"

    id: Mapped[UUID] = uuid_pk()
    snapshot_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("lb_writeback_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_wi_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False)
    line_index: Mapped[int | None] = mapped_column(Integer)
    station_index: Mapped[int | None] = mapped_column(Integer)
    workers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    units: Mapped[list | None] = mapped_column(JSONB)
    offline_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        Index("ix_lb_row_placements_snapshot", "snapshot_id"),
        Index("ix_lb_row_placements_snapshot_source", "snapshot_id", "source_wi_row_id"),
    )
