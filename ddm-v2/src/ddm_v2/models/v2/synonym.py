"""NL 同義詞表（v2_0014）。

IE 為每個 rule-set 的各參數選項登記自然語言同義詞，供 NL draft parser 最長匹配。
UNIQUE(rule_set_id, parameter, synonym_norm) 確保同參數內無歧義（DB 層防線）。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base


class RuleOptionSynonym(Base):
    """rule_option_synonyms 表。"""

    __tablename__ = "rule_option_synonyms"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_set_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rule_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    parameter: Mapped[str] = mapped_column(Text, nullable=False)
    option_code: Mapped[str] = mapped_column(Text, nullable=False)
    synonym_raw: Mapped[str] = mapped_column(Text, nullable=False)
    synonym_norm: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "parameter IN ('A','B','G','P','M','X','I','vocab')",
            name="ck_rule_option_synonyms_parameter",
        ),
        UniqueConstraint(
            "rule_set_id", "parameter", "synonym_norm",
            name="uq_rule_option_synonyms_rule_set_id_parameter_synonym_norm",
        ),
        sa.Index(
            "ix_rule_option_synonyms_rule_set_id_parameter",
            "rule_set_id",
            "parameter",
        ),
    )
