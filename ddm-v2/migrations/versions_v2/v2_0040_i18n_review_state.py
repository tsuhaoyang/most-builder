"""v2_0040: i18n_review_state（ADR-032 D5——英文譯文的覆核狀態側表）

只存「關於譯文的事實」，**不存譯文本身**——譯文留在原欄（`label_en` / `name_en`，
均已存在，這是加法 migration）。理由見 ADR-032 D5「為什麼譯文不搬進側表」：
`label_en` 已是既有 API 契約（`/options`、`/full`、`paramSchema.ts` 編輯欄），
搬家等於改契約＋資料遷移，換來的只是「更整齊」。

`scope_key` 的設計是本表的重點（D5）：
- entity_type='rule_option' → `'{parameter}:{option_code}'`（例 'g:g_grasp'），
  **刻意不含 rule_set_id**——`replace_children` 每次存草稿會刪除並重建子表列，
  主鍵（id）會換；且英文譯文的正確性不隨 TMU 版本而變（「抓握=grasp」不會因為
  clone 出新版本而需要重審）。以版本無關的業務鍵為主鍵，覆核成果才會累積。
- entity_type∈{'vocab_item','motion_template'} → 該列 id 的字串（這兩者是主數據，
  無 clone 行為，id 穩定）。

`source_sha256`：翻譯當下「中文來源字串」正規化後（`ddm_v2.nlp.normalization.normalize`）
的 sha256——與 gold review 的 `norm_sha256` 手法同構，用來偵測「中文來源變了、
英文還沒跟上」（過期→ stale，見 `services/v2/i18n_service.py` 的待審清單查詢）。

`reviewed_by` 在 `source='human'` 時必填：以 **DB CHECK** 而非 application 層驗證
承擔——這個不變式必須對任何寫入路徑成立（service 層、未來的批次覆核工具、甚至
手動 SQL 修補），而不是只對走過某一支 service 函式的呼叫成立；DB CHECK 是唯一
保證「不管哪條路徑寫都不可能違反」的層級。

Revision ID: v2_0040
Revises: v2_0039
Create Date: 2026-08-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0040"
down_revision = "v2_0039"
branch_labels = None
depends_on = None

_UQ = "uq_i18n_review_state_entity_type_scope_key_field_locale"


def upgrade() -> None:
    op.create_table(
        "i18n_review_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.Text(), nullable=False),
        sa.Column("translated_by", sa.Text(), nullable=True),
        sa.Column(
            "translated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "entity_type", "scope_key", "field", "locale", name=_UQ,
        ),
        sa.CheckConstraint(
            "entity_type IN ('rule_option','vocab_item','motion_template')",
            name="ck_i18n_review_state_entity_type",
        ),
        sa.CheckConstraint(
            "field IN ('label','sentence','name')",
            name="ck_i18n_review_state_field",
        ),
        sa.CheckConstraint(
            "locale IN ('en')",
            name="ck_i18n_review_state_locale",
        ),
        sa.CheckConstraint(
            "source IN ('machine','human','legacy_seed')",
            name="ck_i18n_review_state_source",
        ),
        sa.CheckConstraint(
            "(source <> 'human') OR (reviewed_by IS NOT NULL)",
            name="ck_i18n_review_state_reviewed_by_required_for_human",
        ),
    )
    op.create_index("ix_i18n_review_state_entity_type", "i18n_review_state", ["entity_type"])


def downgrade() -> None:
    op.drop_index("ix_i18n_review_state_entity_type", table_name="i18n_review_state")
    op.drop_table("i18n_review_state")
