"""v2 baseline (定點重建) — 核心聚合 + 詞彙庫 + rule_set 表頭 (2a).

依據：docs/specs/data-model-and-storage-spec.md（§1.5 儲存策略、§2 階層、§3 詞彙）。
全新 schema 基線：舊 DB 可 drop 重建（測試資料可棄）。
2b 補 rule_set 子表（A 三分量/B 1205 值/G/P/M/X/I）；2c 補 codes/bom/audit + RBAC FK。

Revision ID: v2_0001
Revises:
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0001"
down_revision = None
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
    # ── rule_sets（表頭；子表見 2b）──
    op.create_table(
        "rule_sets",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name_zh", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("system_tmu_multiplier", sa.Numeric(10, 4), server_default=sa.text("1"), nullable=False),
        sa.Column("effective_from", _TS),
        sa.Column("effective_to", _TS),
        sa.Column("published_by", _UUID),
        sa.Column("published_at", _TS),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_rule_sets"),
        sa.UniqueConstraint("code", name="uq_rule_sets_code"),
        sa.CheckConstraint("status IN ('draft','published','retired')", name="ck_rule_sets_status"),
    )

    # ── sites ──
    op.create_table(
        "sites",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("external_code", sa.Text()),
        sa.Column("name_zh", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_sites"),
        sa.UniqueConstraint("external_code", name="uq_sites_external_code"),
    )

    # ── products ──
    op.create_table(
        "products",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("site_id", _UUID, nullable=False),
        sa.Column("external_code", sa.Text()),
        sa.Column("name_zh", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("external_code", name="uq_products_external_code"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], name="fk_products_site_id_sites", ondelete="RESTRICT"),
    )

    # ── work_vocab_items（詞彙庫主數據）──
    op.create_table(
        "work_vocab_items",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("external_code", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name_zh", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text()),
        sa.Column("site_id", _UUID),
        sa.Column("source_system", sa.Text(), server_default=sa.text("'local'"), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("deleted_at", _TS),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_work_vocab_items"),
        sa.UniqueConstraint("external_code", name="uq_work_vocab_items_external_code"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], name="fk_work_vocab_items_site_id_sites", ondelete="RESTRICT"),
        sa.CheckConstraint("kind IN ('object','component','tool','from','to','hand')", name="ck_work_vocab_items_kind"),
        sa.CheckConstraint("source_system IN ('local','mes','erp','plm')", name="ck_work_vocab_items_source_system"),
    )

    # ── skus ──
    op.create_table(
        "skus",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("sku_code", sa.Text(), nullable=False),
        sa.Column("name_zh", sa.Text()),
        sa.Column("name_en", sa.Text()),
        sa.Column("attributes", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_skus"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_skus_product_id_products", ondelete="RESTRICT"),
        sa.UniqueConstraint("product_id", "sku_code", name="uq_skus_product_id_sku_code"),
    )

    # ── process_versions（版本/輕量 SOP；含另存新檔血緣）──
    op.create_table(
        "process_versions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("sku_id", _UUID, nullable=False),
        sa.Column("version_no", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("source_version_id", _UUID),
        sa.Column("effective_from", _TS),
        sa.Column("effective_to", _TS),
        sa.Column("created_by", _UUID),
        sa.Column("published_by", _UUID),
        sa.Column("published_at", _TS),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_process_versions"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_process_versions_sku_id_skus", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_version_id"], ["process_versions.id"], name="fk_process_versions_source_version_id_process_versions", ondelete="SET NULL"),
        sa.UniqueConstraint("sku_id", "version_no", name="uq_process_versions_sku_id_version_no"),
        sa.CheckConstraint("status IN ('draft','published','retired')", name="ck_process_versions_status"),
    )

    # ── most_worksheets（WI 表頭；1:1 process_version）──
    op.create_table(
        "most_worksheets",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("process_version_id", _UUID, nullable=False),
        sa.Column("model_label", sa.Text()),
        sa.Column("analyst", sa.Text()),
        sa.Column("study_date", sa.Date()),
        sa.Column("default_rule_set_id", _UUID),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_most_worksheets"),
        sa.ForeignKeyConstraint(["process_version_id"], ["process_versions.id"], name="fk_most_worksheets_process_version_id_process_versions", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_rule_set_id"], ["rule_sets.id"], name="fk_most_worksheets_default_rule_set_id_rule_sets", ondelete="RESTRICT"),
        sa.UniqueConstraint("process_version_id", name="uq_most_worksheets_process_version_id"),
        sa.CheckConstraint("status IN ('draft','published','retired')", name="ck_most_worksheets_status"),
    )

    # ── wi_rows（方法步；穩定 id）──
    op.create_table(
        "wi_rows",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("worksheet_id", _UUID, nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("sub_activity", sa.Text()),
        sa.Column("key_parts", sa.Text()),
        sa.Column("hand", sa.Text()),
        sa.Column("object_vocab_id", _UUID, nullable=False),
        sa.Column("from_vocab_id", _UUID),
        sa.Column("to_vocab_id", _UUID),
        sa.Column("tool_vocab_id", _UUID),
        sa.Column("frequency", sa.Numeric(10, 3), server_default=sa.text("1"), nullable=False),
        sa.Column("simo_group_id", sa.Text()),
        sa.Column("provenance", sa.Text(), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("source_row_id", _UUID),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_wi_rows"),
        sa.ForeignKeyConstraint(["worksheet_id"], ["most_worksheets.id"], name="fk_wi_rows_worksheet_id_most_worksheets", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["object_vocab_id"], ["work_vocab_items.id"], name="fk_wi_rows_object_vocab_id_work_vocab_items", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_vocab_id"], ["work_vocab_items.id"], name="fk_wi_rows_from_vocab_id_work_vocab_items", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_vocab_id"], ["work_vocab_items.id"], name="fk_wi_rows_to_vocab_id_work_vocab_items", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tool_vocab_id"], ["work_vocab_items.id"], name="fk_wi_rows_tool_vocab_id_work_vocab_items", ondelete="RESTRICT"),
        sa.UniqueConstraint("worksheet_id", "seq_no", name="uq_wi_rows_worksheet_id_seq_no"),
        sa.CheckConstraint("hand IS NULL OR hand IN ('LH','RH','BH')", name="ck_wi_rows_hand"),
        sa.CheckConstraint("provenance IN ('manual','bom_draft')", name="ck_wi_rows_provenance"),
        sa.CheckConstraint("frequency > 0", name="ck_wi_rows_frequency_pos"),
    )

    # ── level_entries（second 為 GENERATED 欄）──
    op.create_table(
        "level_entries",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("wi_row_id", _UUID, nullable=False),
        sa.Column("worksheet_id", _UUID, nullable=False),
        sa.Column("raw_seconds", sa.Numeric(12, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("coefficient", sa.Numeric(6, 3), server_default=sa.text("1"), nullable=False),
        sa.Column("second", sa.Numeric(12, 4), sa.Computed("raw_seconds * coefficient", persisted=True)),
        sa.Column("number", sa.Text()),
        sa.Column("number_count", sa.Integer()),
        sa.Column("ascription", sa.Text()),
        sa.Column("level", sa.Text()),
        sa.Column("countersignature", sa.Text()),
        sa.Column("order_in_group", sa.Integer()),
        sa.Column("machine_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("manpower", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_level_entries"),
        sa.ForeignKeyConstraint(["wi_row_id"], ["wi_rows.id"], name="fk_level_entries_wi_row_id_wi_rows", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worksheet_id"], ["most_worksheets.id"], name="fk_level_entries_worksheet_id_most_worksheets", ondelete="CASCADE"),
        sa.UniqueConstraint("wi_row_id", name="uq_level_entries_wi_row_id"),
        sa.CheckConstraint("coefficient > 0", name="ck_level_entries_coefficient_pos"),
        sa.CheckConstraint("ascription IS NULL OR ascription = 'main'", name="ck_level_entries_ascription"),
        sa.CheckConstraint("machine_count >= 1 AND manpower >= 1", name="ck_level_entries_resources_pos"),
    )

    # ── most_cycles（slot_inputs JSONB + 升欄）──
    op.create_table(
        "most_cycles",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("wi_row_id", _UUID, nullable=False),
        sa.Column("seq_kind", sa.Text(), nullable=False),
        sa.Column("rule_set_id", _UUID, nullable=False),
        sa.Column("slot_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("computed", postgresql.JSONB()),
        sa.Column("narrative_zh", sa.Text()),
        sa.Column("total_tmu", sa.Numeric(12, 3)),
        sa.Column("total_seconds", sa.Numeric(12, 4)),
        sa.Column("computed_at", _TS),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_most_cycles"),
        sa.ForeignKeyConstraint(["wi_row_id"], ["wi_rows.id"], name="fk_most_cycles_wi_row_id_wi_rows", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"], name="fk_most_cycles_rule_set_id_rule_sets", ondelete="RESTRICT"),
        sa.UniqueConstraint("wi_row_id", name="uq_most_cycles_wi_row_id"),
        sa.CheckConstraint("seq_kind IN ('GM','CM')", name="ck_most_cycles_seq_kind"),
    )

    # 查詢用索引（依儲存策略：促進常用查詢）
    op.create_index("ix_wi_rows_worksheet_id", "wi_rows", ["worksheet_id"])
    op.create_index("ix_most_cycles_rule_set_id", "most_cycles", ["rule_set_id"])
    op.create_index("ix_level_entries_worksheet_id", "level_entries", ["worksheet_id"])
    op.create_index("ix_work_vocab_items_kind", "work_vocab_items", ["kind"])


def downgrade() -> None:
    for tbl in (
        "most_cycles",
        "level_entries",
        "wi_rows",
        "most_worksheets",
        "process_versions",
        "skus",
        "work_vocab_items",
        "products",
        "sites",
        "rule_sets",
    ):
        op.drop_table(tbl)
