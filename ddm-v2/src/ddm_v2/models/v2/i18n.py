"""i18n 覆核狀態側表（ADR-032 D5）。

只存「關於譯文的事實」，不存譯文本身——譯文留在原欄（`label_en` / `name_en`），
理由見 ADR-032 D5「為什麼譯文不搬進側表」與 v2_0040 migration 檔頭。

`scope_key` 的設計是本表的重點，不是細節（D5）：
- entity_type='rule_option' → `'{parameter}:{option_code}'`（例 'g:g_grasp'），
  **刻意不含 rule_set_id**——`replace_children` 每次存草稿會刪除並重建子表列，
  主鍵會換；且英文譯文的正確性不隨 TMU 版本而變。
- entity_type∈{'vocab_item','motion_template'} → 該列 id 的字串（主數據無 clone
  行為，id 穩定）。

`source_sha256`：翻譯當下「中文來源字串」正規化後（`ddm_v2.nlp.normalization.normalize`）
的 sha256，與 gold review 的 `norm_sha256` 手法同構——中文來源變了、英文還沒
跟上即視為過期（stale），見 `services/v2/i18n_service.py`。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk

ENTITY_TYPES = ("rule_option", "vocab_item", "motion_template")
FIELDS = ("label", "sentence", "name")
LOCALES = ("en",)
SOURCES = ("machine", "human", "legacy_seed")

_ENTITY_TYPE_CK = "entity_type IN ('rule_option','vocab_item','motion_template')"
_FIELD_CK = "field IN ('label','sentence','name')"
_LOCALE_CK = "locale IN ('en')"
_SOURCE_CK = "source IN ('machine','human','legacy_seed')"
# D5：`reviewed_by` 在 `source='human'` 時必填——DB CHECK 承擔（見 v2_0040 檔頭：
# 這個不變式必須對任何寫入路徑成立，不只是走過某一支 service 函式的呼叫）。
_REVIEWED_BY_CK = "(source <> 'human') OR (reviewed_by IS NOT NULL)"


class I18nReviewState(Base):
    """`i18n_review_state` 表。"""

    __tablename__ = "i18n_review_state"

    id: Mapped[UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    translated_by: Mapped[str | None] = mapped_column(Text)
    translated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "entity_type", "scope_key", "field", "locale",
            name="uq_i18n_review_state_entity_type_scope_key_field_locale",
        ),
        CheckConstraint(_ENTITY_TYPE_CK, name="entity_type"),
        CheckConstraint(_FIELD_CK, name="field"),
        CheckConstraint(_LOCALE_CK, name="locale"),
        CheckConstraint(_SOURCE_CK, name="source"),
        CheckConstraint(_REVIEWED_BY_CK, name="reviewed_by_required_for_human"),
        Index("ix_i18n_review_state_entity_type", "entity_type"),
    )
