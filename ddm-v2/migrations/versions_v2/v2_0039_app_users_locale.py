"""v2_0039: app_users.locale（ADR-032 D3.1——使用者個人語言偏好，加法）

`locale text NULL`，`CHECK (locale IN ('zh-TW','en'))`。NULL 的語意是「未設定」，
不是「無語言」——回退到系統預設（目前 `zh-TW`），由讀取端（`/api/v2/me`）解析，
不在資料庫層寫死 `NOT NULL DEFAULT 'zh-TW'`：這樣日後若改系統預設，未表態的既有
使用者會自動套用新預設，不需要一次性 UPDATE 既有列。

語系碼與欄位後綴的對照（`zh-TW`→`_zh`、`en`→`_en`）固定，見 ADR-032 I6——本欄
只存語系碼本身，不是後綴。

Revision ID: v2_0039
Revises: v2_0038
Create Date: 2026-08-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0039"
down_revision = "v2_0038"
branch_labels = None
depends_on = None

_CK_NAME = "ck_app_users_locale"


def upgrade() -> None:
    op.add_column("app_users", sa.Column("locale", sa.Text(), nullable=True))
    op.create_check_constraint(_CK_NAME, "app_users", "locale IN ('zh-TW','en')")


def downgrade() -> None:
    op.drop_constraint(_CK_NAME, "app_users", type_="check")
    op.drop_column("app_users", "locale")
