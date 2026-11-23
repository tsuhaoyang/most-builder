"""v2_0052: 每列距離狀態與完成檢查（ADR-038 D6，W2）

1. `wi_rows.distance_status`（可空）：`confirmed`（系統算出或 DSX 查到、經人確認）｜`manual`（人工填）｜
   `not_applicable`（此動作無距離）。空值＝沒標示；既有列全部為空。
   以明確狀態判斷，不以數值判斷：A0（≤2.5 cm）是合法值，距離 0 可能是真的、也可能是沒填。
2. `most_worksheets.distance_check_required`（預設 false）：經新工作區寫入（`drafts/commit`）後設為 true，
   之後不自動關閉。為 true 時核准需要每一列都有距離狀態；既有工時表維持 false、不受影響。

downgrade：有任何列有距離狀態、或有任何工時表已開啟檢查，就拒絕（不靜默丟掉人工標示）。

Revision ID: v2_0052
Revises: v2_0051
Create Date: 2026-11-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0052"
down_revision = "v2_0051"
branch_labels = None
depends_on = None

# 組進 DDL 的字面常數（DDL 無法 bind 參數），不得改成外部輸入
_CK = "ck_wi_rows_distance_status"
_CK_DEF = "distance_status IS NULL OR distance_status IN ('confirmed','manual','not_applicable')"

SQL_COUNT_STATUSES = "SELECT COUNT(*) FROM wi_rows WHERE distance_status IS NOT NULL"
SQL_COUNT_REQUIRED = "SELECT COUNT(*) FROM most_worksheets WHERE distance_check_required"


def upgrade() -> None:
    op.add_column("wi_rows", sa.Column("distance_status", sa.Text(), nullable=True))
    op.execute(sa.text(f"ALTER TABLE wi_rows ADD CONSTRAINT {_CK} CHECK ({_CK_DEF})"))
    op.add_column(
        "most_worksheets",
        sa.Column("distance_check_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("LOCK TABLE wi_rows, most_worksheets IN SHARE ROW EXCLUSIVE MODE"))
    statuses = bind.execute(sa.text(SQL_COUNT_STATUSES)).scalar_one()
    required = bind.execute(sa.text(SQL_COUNT_REQUIRED)).scalar_one()
    if statuses or required:
        raise RuntimeError(
            f"v2_0052 downgrade refused: {statuses} wi_rows row(s) carry a distance_status and {required} "
            "worksheet(s) have distance_check_required. Dropping them would silently lose what people marked. "
            "Export or clear them deliberately, then downgrade again."
        )
    op.drop_column("most_worksheets", "distance_check_required")
    op.execute(sa.text(f"ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS {_CK}"))
    op.drop_column("wi_rows", "distance_status")
