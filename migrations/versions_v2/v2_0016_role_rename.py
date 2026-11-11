"""impl-06a：角色改名 IE→analyst、manager→approver。

app_users.roles 是 text[]，無 CHECK 約束（v2_0004 baseline 確認），
只需做陣列元素替換。無 role（singular）欄位，無需處理額外約束。

Revision ID: v2_0016
Revises: v2_0015
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "v2_0016"
down_revision = "v2_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # app_users.roles 是 text[]；逐元素替換 IE→analyst、manager→approver。
    op.execute(text(
        "UPDATE app_users "
        "SET roles = ARRAY("
        "    SELECT CASE"
        "        WHEN x = 'IE'      THEN 'analyst'"
        "        WHEN x = 'manager' THEN 'approver'"
        "        ELSE x"
        "    END"
        "    FROM unnest(roles) x"
        ") "
        "WHERE roles @> ARRAY['IE'] OR roles @> ARRAY['manager']"
    ))


def downgrade() -> None:
    op.execute(text(
        "UPDATE app_users "
        "SET roles = ARRAY("
        "    SELECT CASE"
        "        WHEN x = 'analyst'  THEN 'IE'"
        "        WHEN x = 'approver' THEN 'manager'"
        "        ELSE x"
        "    END"
        "    FROM unnest(roles) x"
        ") "
        "WHERE roles @> ARRAY['analyst'] OR roles @> ARRAY['approver']"
    ))
