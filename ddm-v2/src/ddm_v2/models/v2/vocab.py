"""詞彙庫主數據（器具/從/到/物件/元件/手勢）。

依據 data-model-and-storage-spec §3.1。
- external_code：對外語言中立碼（可空，發碼前）。
- source_system：權威來源守門（local 外為唯讀）。
- 軟刪：被已發布 WI 引用者不可硬刪（E1）→ is_active + deleted_at。
- 對外取資料一律經 MasterDataProvider port（§6）；本表是 LocalDbProvider 的後援。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk

_KIND_CK = "kind IN ('object','component','tool','from','to','hand')"
_SOURCE_CK = "source_system IN ('local','mes','erp','plm')"


class WorkVocabItem(Base, TimestampMixin):
    __tablename__ = "work_vocab_items"

    id: Mapped[UUID] = uuid_pk()
    external_code: Mapped[str | None] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str | None] = mapped_column(Text)
    site_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"))  # NULL=全域
    source_system: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'local'"))
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_KIND_CK, name="kind"),
        CheckConstraint(_SOURCE_CK, name="source_system"),
    )
