"""v2 codes/bom/audit (2c)：external_code 前綴治理、BOM staging/料表、稽核。

依據 data-model-and-storage-spec §4/§5/§8。

Revision ID: v2_0003
Revises: v2_0002
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0003"
down_revision = "v2_0002"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("NOW()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "code_prefix_registry",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("next_seq", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("issuer_role", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_code_prefix_registry"),
        sa.UniqueConstraint("prefix", name="uq_code_prefix_registry_prefix"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("actor_id", _UUID),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", _UUID),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("changes", postgresql.JSONB()),
        sa.Column("created_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_entity_type_entity_id", "audit_log", ["entity_type", "entity_id"])

    op.create_table(
        "bom_imports",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("sku_id", _UUID, nullable=False),
        sa.Column("source_system", sa.Text(), server_default=sa.text("'plm'"), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("imported_by", _UUID),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_bom_imports"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_bom_imports_sku_id_skus", ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('pending','validated','merged','failed')", name="ck_bom_imports_status"),
    )

    op.create_table(
        "bom_items",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("sku_id", _UUID, nullable=False),
        sa.Column("parent_item_id", _UUID),
        sa.Column("component_vocab_id", _UUID, nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), server_default=sa.text("1"), nullable=False),
        sa.Column("bom_level", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_bom_items"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_bom_items_sku_id_skus", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_item_id"], ["bom_items.id"], name="fk_bom_items_parent_item_id_bom_items", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_vocab_id"], ["work_vocab_items.id"], name="fk_bom_items_component_vocab_id_work_vocab_items", ondelete="RESTRICT"),
    )


def downgrade() -> None:
    for tbl in ("bom_items", "bom_imports", "audit_log", "code_prefix_registry"):
        op.drop_table(tbl)
