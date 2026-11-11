"""v2 schema 的獨立宣告基底（與舊 models 隔離）。

v2 是「定點重建」的全新 schema 基線；用獨立的 DeclarativeBase / MetaData，
讓 v2 的 Alembic baseline 只看見 v2 表，不與舊 0001–0017 migration 糾纏。
依據：docs/architecture/data-model-and-storage-spec.md
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 命名慣例：讓 Alembic 產生穩定、可預期的 constraint/index 名稱。
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[UUID]:
    """UUID 主鍵（不用 server default gen_random_uuid，避免 ORM INSERT 略過 id）。"""
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
