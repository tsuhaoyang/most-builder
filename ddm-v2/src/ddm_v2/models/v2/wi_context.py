"""正式工序 context（R3a / ADR-027 §4 / domain-evolution §7.2）。

加法 metadata；不取代 wi_rows 欄位、不進 slot_inputs／Level／AI operational。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk

_SOURCE_CK = "source IN ('manual','imported','ai_assisted','system')"


class WiRowContext(Base, TimestampMixin):
    __tablename__ = "wi_row_contexts"

    id: Mapped[UUID] = uuid_pk()
    wi_row_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wi_rows.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    context_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    context_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    created_by: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("wi_row_id", name="uq_wi_row_contexts_wi_row_id"),
        CheckConstraint(_SOURCE_CK, name="source"),
        Index("ix_wi_row_contexts_schema_version", "schema_version"),
    )
