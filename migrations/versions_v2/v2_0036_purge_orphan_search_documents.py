"""v2_0036: purge orphan motion_module search_documents (data migration)

背景：`delete_module` 過去只刪 motion_modules 列。search_documents 沒有 ORM
model（v2_0013 raw SQL 建表），`ref_id` 是裸 uuid 且無 FK——模組刪除後投影列
殘留，/api/v2/search 會回傳指向不存在模組的結果。service 端已修
（delete_module 同交易清投影）；本 migration 清既存孤兒。

為何用 data migration 而非一次性腳本：所有部署路徑（compose 啟動、CI、本機
dev）都會跑 `alembic upgrade head`，每個環境自動清一次，不依賴人工記得在各環境
跑腳本。DELETE 僅及孤兒（NOT EXISTS motion_modules），idempotent、重跑無害。

Downgrade：no-op。被刪的是懸空投影（對應模組已不存在），無資料可回復也無需
回復；如需全量重建索引另有 scripts/rebuild_search_index.py。schema 未動。

Revision ID: v2_0036
Revises: v2_0035
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op

revision = "v2_0036"
down_revision = "v2_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM search_documents sd
        WHERE sd.doc_type = 'motion_module'
          AND NOT EXISTS (
            SELECT 1 FROM motion_modules m WHERE m.id = sd.ref_id
          )
        """
    )


def downgrade() -> None:
    # 資料清理不可逆：孤兒列無對應模組，也不承載任何可回復的業務事實。
    # schema 未變更 → downgrade 為 no-op（刻意，非遺漏）。
    pass
