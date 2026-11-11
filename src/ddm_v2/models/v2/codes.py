"""external_code 治理：code_prefix_registry（前綴發碼）。

依據 data-model-and-storage-spec §5。external_code 本身存在各實體欄位；本表管前綴與流水號。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class CodePrefixRegistry(Base, TimestampMixin):
    __tablename__ = "code_prefix_registry"

    id: Mapped[UUID] = uuid_pk()
    prefix: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # SITE/PRD/OBJ/CMP/TOL/LOC...
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # 對應實體/詞彙 kind
    description: Mapped[str | None] = mapped_column(Text)
    next_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    issuer_role: Mapped[str | None] = mapped_column(Text)  # 發碼權責，建議 manager+
