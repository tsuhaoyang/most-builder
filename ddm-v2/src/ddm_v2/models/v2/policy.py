"""Modeling / Level policy manifests（R2a / ADR-027 §3）。

Immutable versioned manifests：`(code, version_no)` 唯一；status = draft/published/retired。
第一版**不**定義 `is_active`（避免在 resolver precedence 未決前複製 rule-set active 機制）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk

_STATUS_CK = "status IN ('draft','published','retired')"


class ModelingPolicyVersion(Base):
    """非 TMU 的 compile 決策（quantity / tool / SIMO / inspect / defaults）。"""

    __tablename__ = "modeling_policy_versions"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    site_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT")
    )
    process_type: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    compiler_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    published_by: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("code", "version_no", name="uq_modeling_policy_versions_code_version_no"),
        CheckConstraint(_STATUS_CK, name="status"),
        CheckConstraint("version_no >= 1", name="version_no_pos"),
        Index("ix_modeling_policy_versions_content_hash", "content_hash"),
    )


class LevelPolicyVersion(Base):
    """Level validator revision + LB output contract 識別（不把 R1–R9 重寫成 DSL）。"""

    __tablename__ = "level_policy_versions"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    validator_revision: Mapped[str] = mapped_column(Text, nullable=False)
    output_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    published_by: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("code", "version_no", name="uq_level_policy_versions_code_version_no"),
        CheckConstraint(_STATUS_CK, name="status"),
        CheckConstraint("version_no >= 1", name="version_no_pos"),
        Index("ix_level_policy_versions_content_hash", "content_hash"),
    )
