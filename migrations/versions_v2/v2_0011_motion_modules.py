"""motion_modules：持久組件庫（impl-04 / ADR-017）。

建立 motion_modules 與 motion_module_versions 兩張表；
並為 wi_rows 加入 source_module_id / source_module_version 追溯欄。

downgrade：反向刪 FK→欄→兩表。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "v2_0011"
down_revision = "v2_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── motion_modules ────────────────────────────────────────────────
    op.create_table(
        "motion_modules",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name_zh", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("keywords", ARRAY(sa.Text), nullable=False,
                  server_default=sa.text("'{}'::text[]")),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("owner", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default=sa.text("'draft'")),
        sa.Column("current_version", sa.Integer, nullable=False,
                  server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "scope IN ('personal','site','global')",
            name="ck_motion_modules_scope_valid",
        ),
        sa.CheckConstraint(
            "status IN ('draft','standard','retired')",
            name="ck_motion_modules_status_valid",
        ),
        sa.CheckConstraint(
            "scope != 'personal' OR owner IS NOT NULL",
            name="ck_motion_modules_personal_owner",
        ),
    )

    # ── motion_module_versions ────────────────────────────────────────
    op.create_table(
        "motion_module_versions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("module_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("motion_modules.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("rule_set_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("rule_sets.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("rows", JSONB, nullable=False),
        sa.Column("narrative_zh", sa.Text, nullable=True),
        sa.Column("total_tmu", sa.Numeric(12, 3), nullable=False),
        sa.Column("total_seconds", sa.Numeric(12, 4), nullable=False),
        sa.Column("published_by", sa.Text, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "module_id", "version_no",
            name="uq_motion_module_versions_module_id_version_no",
        ),
    )

    # ── wi_rows 追溯欄 ────────────────────────────────────────────────
    op.add_column(
        "wi_rows",
        sa.Column("source_module_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "wi_rows",
        sa.Column("source_module_version", sa.Integer, nullable=True),
    )
    op.create_foreign_key(
        "fk_wi_rows_source_module_id_motion_modules",
        "wi_rows", "motion_modules",
        ["source_module_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_wi_rows_source_module_id_motion_modules", "wi_rows", type_="foreignkey"
    )
    op.drop_column("wi_rows", "source_module_version")
    op.drop_column("wi_rows", "source_module_id")
    op.drop_table("motion_module_versions")
    op.drop_table("motion_modules")
