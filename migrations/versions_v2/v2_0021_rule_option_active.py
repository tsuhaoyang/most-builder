"""v2_0021：12 張 rule_* 子表統一加 is_active（選項級啟用旗標）。

ADR-023 §3.3 / D2：v3 的選項表有「啟用」toggle，v2 子表原本只有 sort_order。
本欄位讓 IE 能在 draft 內「停用」某選項而不必刪除（保留值與 code 供日後復用）。

⚠️ 語意界線（與 ADR-023 §3.4 回放鐵則同源）——
**`load_rule_set_from_db` 不得依 is_active 過濾。** 引擎載入不看治理狀態，
否則停用一個選項會讓「已存檔且引用該選項的 cycle」重算出不同 TMU（回放破裂）。
`is_active=false` 只影響兩件事：
  1. UI 是否把該選項列為可選（`GET .../options?active_only=true`）
  2. publish 前的完整性驗證（某必要參數若「全部選項都停用」→ 擋下發布）

預設 true：既有資料全部視為啟用，行為與 migration 前完全一致（零行為變更）。

Revision ID: v2_0021
Revises: v2_0020
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0021"
down_revision = "v2_0020"
branch_labels = None
depends_on = None

# 12 張子表（含 rule_m_foot_bands——V2 起 M 腳步獨立帶）
_TABLES = (
    "rule_a_bands",
    "rule_b_options",
    "rule_g_actions",
    "rule_p_bases",
    "rule_p_addons",
    "rule_m_verbs",
    "rule_m_ladder_bands",
    "rule_m_foot_bands",
    "rule_m_rotation_bands",
    "rule_m_hand_bands",
    "rule_x_options",
    "rule_i_options",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "is_active")
