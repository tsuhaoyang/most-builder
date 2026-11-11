"""v2_0024：移除死表 audit_log（D12 / ADR-018 後續清理）。

## 為什麼移除

`audit_log` 是 v2_0003 建立的通用稽核表，已被 `workflow_audit_log`（ADR-018 裁決 3，
append-only、DB 層 trigger 強制不可變）完整取代。稽核事實顯示它是死表：

- 資料 0 筆；
- `AuditLog` model 在全 src 零實例化（僅存定義本身與 __init__ 的 export）；
- 無任何 service / route 讀寫（`api/routes/v2/audit_log.py`「audit_log」路由查的是
  `WorkflowAuditLog`，與本表同名不同物，不受影響）；
- v2_0018 的不可變 trigger 綁在 `workflow_audit_log` 上，不在本表，DROP 不觸及。

使用者於 D12 裁決移除。**本 migration 只移除 audit_log 一張**；`bom_imports`、
`bom_items`（BOM 匯入待開發，使用者明示保留）與 `code_prefix_registry`
（同性質 schema 佔位，協調者裁決保守保留）皆不動。

## 雙邊

同步移除 `models/v2/audit.py` 的 `AuditLog` 定義與 `models/v2/__init__.py` 的 export
（repo 硬規則：DB 改動 model + migration 兩邊都改）。

## downgrade

對稱重建 `audit_log` 空表，還原至 v2_0023 時的形狀（actor_id 已於 v2_0004 由
UUID 轉為 text＝員工編號），保持可逆。資料不還原（原本即 0 筆）。

Revision ID: v2_0024
Revises: v2_0023
Create Date: 2026-07-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0024"
down_revision = "v2_0023"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.drop_index("ix_audit_log_entity_type_entity_id", table_name="audit_log")
    op.drop_table("audit_log")


def downgrade() -> None:
    # 對稱重建 v2_0023 當下的空表（含 v2_0004 的 actor_id→text 轉換結果）。
    op.create_table(
        "audit_log",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("actor_id", sa.Text()),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", _UUID),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("changes", postgresql.JSONB()),
        sa.Column("created_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_entity_type_entity_id", "audit_log", ["entity_type", "entity_id"])
