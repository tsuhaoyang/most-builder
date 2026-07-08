"""rule-set v3 值權威對齊（ADR-014 / impl-01 §1）：

- 新表 rule_m_foot_bands（M 腳步帶與階梯分離——C2 定案）
- rule_p_addons 加 display_rule / sentence_text_zh（敘事三態 E6）
- rule_i_options 加 vision_scope / sentence_text_zh（視線外檔位）
- rule_b_options / rule_g_actions / rule_p_bases / rule_m_verbs / rule_x_options 加 sentence_text_zh

值資料（MINIMOST_FACTORY_V2）由 seed 於啟動時插入，不在 migration 內。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0009"
down_revision = "v2_0008"
branch_labels = None
depends_on = None

_SENTENCE_TABLES = ("rule_b_options", "rule_g_actions", "rule_p_bases", "rule_p_addons", "rule_m_verbs", "rule_x_options", "rule_i_options")


def upgrade() -> None:
    op.create_table(
        "rule_m_foot_bands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("max_cm", sa.Numeric(10, 3), nullable=True),
        sa.Column("tmu", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("rule_set_id", "sort_order", name="uq_rule_m_foot_bands_rule_set_id_sort"),
    )
    for t in _SENTENCE_TABLES:
        op.add_column(t, sa.Column("sentence_text_zh", sa.Text(), nullable=True))
    op.add_column("rule_p_addons", sa.Column("display_rule", sa.Text(), nullable=False, server_default=sa.text("'show_self'")))
    op.create_check_constraint("ck_rule_p_addons_display_rule", "rule_p_addons",
                               "display_rule IN ('show_self','hidden','prefix_visible_term')")
    op.add_column("rule_i_options", sa.Column("vision_scope", sa.Text(), nullable=True))
    op.create_check_constraint("ck_rule_i_options_vision_scope", "rule_i_options",
                               "vision_scope IN ('normal','outside')")


def downgrade() -> None:
    op.drop_constraint("ck_rule_i_options_vision_scope", "rule_i_options", type_="check")
    op.drop_column("rule_i_options", "vision_scope")
    op.drop_constraint("ck_rule_p_addons_display_rule", "rule_p_addons", type_="check")
    op.drop_column("rule_p_addons", "display_rule")
    for t in _SENTENCE_TABLES:
        op.drop_column(t, "sentence_text_zh")
    op.drop_table("rule_m_foot_bands")
