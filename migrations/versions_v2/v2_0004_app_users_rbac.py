"""v2 RBAC：app_users（本地授權）+ *_by 欄改 text(員工編號)。

依據 rbac-spec §5。認證委派 Traefik ForwardAuth；此表只管授權。

Revision ID: v2_0004
Revises: v2_0003
Create Date: 2026-06-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0004"
down_revision = "v2_0003"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)

# (table, column) 的 *_by 欄：UUID → text(員工編號)
_BY_COLS = [
    ("process_versions", "created_by"),
    ("process_versions", "published_by"),
    ("rule_sets", "published_by"),
    ("bom_imports", "imported_by"),
    ("audit_log", "actor_id"),
]


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("employee_no", sa.Text(), nullable=False),
        sa.Column("external_user_id", sa.Text()),
        sa.Column("display_name", sa.Text()),
        sa.Column("roles", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("site_ids", postgresql.ARRAY(_UUID), server_default=sa.text("'{}'::uuid[]"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("created_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_app_users"),
        sa.UniqueConstraint("employee_no", name="uq_app_users_employee_no"),
    )
    for table, col in _BY_COLS:
        op.alter_column(table, col, type_=sa.Text(), existing_type=_UUID, postgresql_using=f"{col}::text", existing_nullable=True)


def downgrade() -> None:
    for table, col in _BY_COLS:
        op.alter_column(table, col, type_=_UUID, existing_type=sa.Text(), postgresql_using=f"{col}::uuid", existing_nullable=True)
    op.drop_table("app_users")
