"""v2_0030: modeling/level policy manifests + worksheet FKs（R2a / ADR-027 §3）

Revision ID: v2_0030
Revises: v2_0029
Create Date: 2026-08-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0030"
down_revision = "v2_0029"
branch_labels = None
depends_on = None

# Fixed factory V1 ids（與 policy_service / policy_seed 對齊）
_MODELING_V1 = "a1000000-0000-4000-8000-000000000001"
_LEVEL_V1 = "a2000000-0000-4000-8000-000000000001"
_MODELING_HASH = "a76b79a92cf0b2072c6cb91918d8b1b3736522b383f60d7929f1bf2b0f4132a5"
_LEVEL_HASH = "6e214aee3cfc02bbb83732f235588b4ad474b17064b9809fd9fbd9a0662c39aa"


def upgrade() -> None:
    op.create_table(
        "modeling_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("process_type", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("compiler_contract_version", sa.Text(), nullable=False),
        sa.Column(
            "policy_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("published_by", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('draft','published','retired')",
            name="ck_modeling_policy_versions_status",
        ),
        sa.CheckConstraint("version_no >= 1", name="ck_modeling_policy_versions_version_no_pos"),
        sa.UniqueConstraint("code", "version_no", name="uq_modeling_policy_versions_code_version_no"),
    )
    op.create_index(
        "ix_modeling_policy_versions_content_hash",
        "modeling_policy_versions",
        ["content_hash"],
    )

    op.create_table(
        "level_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("validator_revision", sa.Text(), nullable=False),
        sa.Column("output_contract_version", sa.Text(), nullable=False),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("published_by", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','retired')",
            name="ck_level_policy_versions_status",
        ),
        sa.CheckConstraint("version_no >= 1", name="ck_level_policy_versions_version_no_pos"),
        sa.UniqueConstraint("code", "version_no", name="uq_level_policy_versions_code_version_no"),
    )
    op.create_index(
        "ix_level_policy_versions_content_hash",
        "level_policy_versions",
        ["content_hash"],
    )

    # Seed V1 published manifests（現行保守行為；不改引擎）
    op.execute(
        sa.text(
            f"""
            INSERT INTO modeling_policy_versions
                (id, code, version_no, name, status, site_id, process_type,
                 schema_version, compiler_contract_version, policy_json, content_hash,
                 created_by, published_by, published_at)
            VALUES
                (
                    '{_MODELING_V1}'::uuid,
                    'MODELING_FACTORY',
                    1,
                    'MODELING_FACTORY_V1',
                    'published',
                    NULL,
                    NULL,
                    'modeling-policy-v1',
                    'compiler-v1',
                    '{{"auto_generate_release_return": false, "inspect_merge_into_prior_cm": false, "quantity_policy": "conservative", "simo_auto_assign": false}}'::jsonb,
                    '{_MODELING_HASH}',
                    'system',
                    'system',
                    NOW()
                )
            ON CONFLICT (code, version_no) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO level_policy_versions
                (id, code, version_no, name, status,
                 schema_version, validator_revision, output_contract_version,
                 config_json, content_hash, created_by, published_by, published_at)
            VALUES
                (
                    '{_LEVEL_V1}'::uuid,
                    'LEVEL_FACTORY',
                    1,
                    'LEVEL_FACTORY_V1',
                    'published',
                    'level-input-v1',
                    'ddm_v2.most_engine.level@r1-r9-v1',
                    'lb-output-v1',
                    '{{"notes": "現行 most_engine.level；尚未 DSL 化", "rules": "r1-r9-canonical"}}'::jsonb,
                    '{_LEVEL_HASH}',
                    'system',
                    'system',
                    NOW()
                )
            ON CONFLICT (code, version_no) DO NOTHING
            """
        )
    )

    op.add_column(
        "most_worksheets",
        sa.Column("modeling_policy_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "most_worksheets",
        sa.Column("level_policy_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_most_worksheets_modeling_policy_version_id",
        "most_worksheets",
        "modeling_policy_versions",
        ["modeling_policy_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_most_worksheets_level_policy_version_id",
        "most_worksheets",
        "level_policy_versions",
        ["level_policy_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Backfill：不猜 site override，一律掛 factory V1
    op.execute(
        sa.text(
            f"""
            UPDATE most_worksheets
            SET modeling_policy_version_id = '{_MODELING_V1}'::uuid
            WHERE modeling_policy_version_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE most_worksheets
            SET level_policy_version_id = '{_LEVEL_V1}'::uuid
            WHERE level_policy_version_id IS NULL
            """
        )
    )

    # L4 預留欄位：補上真正 FK（仍可 NULL）
    op.create_foreign_key(
        "fk_ai_parse_jobs_modeling_policy_version_id",
        "ai_parse_jobs",
        "modeling_policy_versions",
        ["modeling_policy_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ai_parse_jobs_modeling_policy_version_id",
        "ai_parse_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_most_worksheets_level_policy_version_id",
        "most_worksheets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_most_worksheets_modeling_policy_version_id",
        "most_worksheets",
        type_="foreignkey",
    )
    op.drop_column("most_worksheets", "level_policy_version_id")
    op.drop_column("most_worksheets", "modeling_policy_version_id")
    op.drop_index("ix_level_policy_versions_content_hash", table_name="level_policy_versions")
    op.drop_table("level_policy_versions")
    op.drop_index("ix_modeling_policy_versions_content_hash", table_name="modeling_policy_versions")
    op.drop_table("modeling_policy_versions")
