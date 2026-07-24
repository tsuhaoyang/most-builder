"""稽核記錄（E3）：誰、何時、對哪個實體做了什麼。

依據 data-model-and-storage-spec §8 E3。供 IE 治理與追溯（版本發布、規則改動、主數據異動）。
- WorkflowAuditLog：工作流狀態遷移專用，僅追加（ADR-018 裁決 3）。

註：舊有通用稽核表 `AuditLog`（表 `audit_log`）已於 v2_0024（D12）移除——
0 筆、零實例化、無讀寫，被 WorkflowAuditLog 完整取代。
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base


class WorkflowAuditLog(Base):
    """工作流稽核紀錄：僅追加，記錄狀態遷移（ADR-018 裁決 3）。

    entity_type: 'process_version' | 'motion_module' | 'rule_set' | 'motion_template'
    action:      'approve' | 'promote' | 'publish' | 'override' | 'retire'
    """

    __tablename__ = "workflow_audit_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),
    )
