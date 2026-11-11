"""NL 同義詞表（v2_0014；v2_0038 放寬 UNIQUE）。

IE 為每個 rule-set 的各參數選項登記自然語言同義詞，供 NL draft parser 最長匹配。
UNIQUE(rule_set_id, parameter, synonym_norm, option_code) 擋同一映射重複登記；
同一詞面可掛多個 code（IE 裁決的變體，如「放至」→ p_place_single/p_place_none，
D3-017），選擇順序由 priority 決定——**數字小者優先，0＝預設**（parser 端
tie-break 見 nlp/lexicon.py build_lexicon；同義詞僅影響建議層，ADR-023）。
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
            # 名稱縮寫欄位段：全欄位命名會超過 PostgreSQL 63 字元識別字上限
            "rule_set_id", "parameter", "synonym_norm", "option_code",
            name="uq_rule_option_synonyms_rs_param_norm_code",
        ),
        sa.Index(
            "ix_rule_option_synonyms_rule_set_id_parameter",
            "rule_set_id",
            "parameter",
        ),
    )
