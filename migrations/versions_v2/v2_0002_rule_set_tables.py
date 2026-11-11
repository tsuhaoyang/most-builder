"""v2 rule_set 子表 (2b)：A 三分量 / B(1205) / G / P / M / X / I。

依據 minimost-sequence-model-core-logic-spec §4。引擎讀此計算（演算法骨架在程式、表值在此）。

Revision ID: v2_0002
Revises: v2_0001
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0002"
down_revision = "v2_0001"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def _rs_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"], name=f"fk_{table}_rule_set_id_rule_sets", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "rule_a_bands",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("component", sa.Text(), nullable=False),
        sa.Column("max_value", sa.Numeric(10, 3)),
        sa.Column("index_value", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_a_bands"),
        _rs_fk("rule_a_bands"),
        sa.CheckConstraint("component IN ('reach','twist','foot')", name="ck_rule_a_bands_component"),
    )
    op.create_index("ix_rule_a_bands_rule_set_id", "rule_a_bands", ["rule_set_id"])

    op.create_table(
        "rule_b_options",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_zh", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text()),
        sa.Column("index_value", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_b_options"),
        _rs_fk("rule_b_options"),
        sa.UniqueConstraint("rule_set_id", "code", name="uq_rule_b_options_rule_set_id_code"),
    )

    op.create_table(
        "rule_g_actions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_zh", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text()),
        sa.Column("modifier_key", sa.Text()),
        sa.Column("requires_modifier", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("base_tmu", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_g_actions"),
        _rs_fk("rule_g_actions"),
        sa.UniqueConstraint("rule_set_id", "code", name="uq_rule_g_actions_rule_set_id_code"),
    )

    op.create_table(
        "rule_p_bases",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_zh", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text()),
        sa.Column("category", sa.Text()),
        sa.Column("direction_mode", sa.Text()),
        sa.Column("base_tmu", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_p_bases"),
        _rs_fk("rule_p_bases"),
        sa.UniqueConstraint("rule_set_id", "code", name="uq_rule_p_bases_rule_set_id_code"),
    )

    op.create_table(
        "rule_p_addons",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_zh", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text()),
        sa.Column("delta_tmu", sa.Integer(), nullable=False),
        sa.Column("needs_precision", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("max_select", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_p_addons"),
        _rs_fk("rule_p_addons"),
        sa.UniqueConstraint("rule_set_id", "code", name="uq_rule_p_addons_rule_set_id_code"),
    )

    op.create_table(
        "rule_m_ladder_bands",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("max_cm", sa.Numeric(10, 3)),
        sa.Column("tmu", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_m_ladder_bands"),
        _rs_fk("rule_m_ladder_bands"),
    )
    op.create_index("ix_rule_m_ladder_bands_rule_set_id", "rule_m_ladder_bands", ["rule_set_id"])

    op.create_table(
        "rule_m_verbs",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_zh", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text()),
        sa.Column("pricing_kind", sa.Text(), nullable=False),
        sa.Column("fixed_tmu", sa.Integer()),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_m_verbs"),
        _rs_fk("rule_m_verbs"),
        sa.UniqueConstraint("rule_set_id", "code", name="uq_rule_m_verbs_rule_set_id_code"),
        sa.CheckConstraint("pricing_kind IN ('fixed','ladder','foot','hand','rotate')", name="ck_rule_m_verbs_pricing_kind"),
    )

    op.create_table(
        "rule_m_rotation_bands",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("max_diameter_cm", sa.Numeric(10, 3)),
        sa.Column("revolutions", sa.Integer(), nullable=False),
        sa.Column("tmu", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_m_rotation_bands"),
        _rs_fk("rule_m_rotation_bands"),
    )

    op.create_table(
        "rule_m_hand_bands",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("max_deg", sa.Numeric(10, 3)),
        sa.Column("tmu", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_m_hand_bands"),
        _rs_fk("rule_m_hand_bands"),
    )

    op.create_table(
        "rule_x_options",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_zh", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text()),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("fixed_seconds", sa.Numeric(10, 4)),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_x_options"),
        _rs_fk("rule_x_options"),
        sa.UniqueConstraint("rule_set_id", "code", name="uq_rule_x_options_rule_set_id_code"),
        sa.CheckConstraint("mode IN ('zero','seconds','fixed')", name="ck_rule_x_options_mode"),
    )

    op.create_table(
        "rule_i_options",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_zh", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text()),
        sa.Column("index_value", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rule_i_options"),
        _rs_fk("rule_i_options"),
        sa.UniqueConstraint("rule_set_id", "code", name="uq_rule_i_options_rule_set_id_code"),
    )


def downgrade() -> None:
    for tbl in (
        "rule_i_options",
        "rule_x_options",
        "rule_m_hand_bands",
        "rule_m_rotation_bands",
        "rule_m_verbs",
        "rule_m_ladder_bands",
        "rule_p_addons",
        "rule_p_bases",
        "rule_g_actions",
        "rule_b_options",
        "rule_a_bands",
    ):
        op.drop_table(tbl)
