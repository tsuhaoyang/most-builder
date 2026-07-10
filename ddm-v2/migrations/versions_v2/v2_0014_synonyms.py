"""v2_0014: rule_option_synonyms table

同義詞表：IE 可為每個 rule-set 的各參數選項登記自然語言同義詞，
供 NL draft parser 做最長匹配。UNIQUE(rule_set_id, parameter, synonym_norm) 確保同參數無歧義。

Revision ID: v2_0014
Revises: v2_0013
Create Date: 2026-07-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0014"
down_revision = "v2_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_option_synonyms",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "rule_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parameter", sa.Text(), nullable=False),
        sa.Column("option_code", sa.Text(), nullable=False),
        sa.Column("synonym_raw", sa.Text(), nullable=False),
        sa.Column("synonym_norm", sa.Text(), nullable=False),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "parameter IN ('A','B','G','P','M','X','I','vocab')",
            name="ck_rule_option_synonyms_parameter",
        ),
        sa.UniqueConstraint(
            "rule_set_id",
            "parameter",
            "synonym_norm",
            name="uq_rule_option_synonyms_rule_set_id_parameter_synonym_norm",
        ),
    )
    op.create_index(
        "ix_rule_option_synonyms_rule_set_id_parameter",
        "rule_option_synonyms",
        ["rule_set_id", "parameter"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rule_option_synonyms_rule_set_id_parameter",
        table_name="rule_option_synonyms",
    )
    op.drop_table("rule_option_synonyms")
