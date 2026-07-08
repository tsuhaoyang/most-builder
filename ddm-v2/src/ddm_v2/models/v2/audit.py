"""稽核記錄（E3）：誰、何時、對哪個實體做了什麼。

依據 data-model-and-storage-spec §8 E3。供 IE 治理與追溯（版本發布、規則改動、主數據異動）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = uuid_pk()
    actor_id: Mapped[str | None] = mapped_column(Text)  # 員工編號（RBAC）
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)  # rule_set / process_version / work_vocab_item ...
    entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)  # create/update/delete/publish/import...
    changes: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    __table_args__ = (Index("ix_audit_log_entity_type_entity_id", "entity_type", "entity_id"),)
