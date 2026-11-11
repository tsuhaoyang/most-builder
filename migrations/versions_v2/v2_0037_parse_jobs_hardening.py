"""v2_0037: ai_parse_jobs 硬化——idempotency 以 import 為範圍 + 在途 partial index

1. `uq_ai_parse_jobs_idempotency_key`（全域唯一）→
   `uq_ai_parse_jobs_import_idempotency_key (import_id, idempotency_key)`。
   security F3：idempotency key 是 client 可控字串，全域唯一時跨 import 撞 key
   會命中**別人的 job**（回應含 requested_by 員編，且受害者的 import 永不解析）。
   既有資料相容：舊約束是新約束的子集（全域唯一 ⇒ (import_id, key) 唯一），
   upgrade 不可能違反新約束。

2. partial index `ix_ai_parse_jobs_active_created (created_at) WHERE status IN
   ('queued','running')`：背景 worker 每 interval 掃 runnable jobs（status 過濾
   + created_at 排序），終態列只增不減，partial index 讓輪詢成本只跟在途量走。

Downgrade：反向重建。注意：若 downgrade 時已存在「不同 import、相同 key」的列
（新約束允許、舊約束不允許），恢復全域 UNIQUE 會失敗——這是誠實的失敗（資料
已依新語意寫入，舊 schema 裝不下），需先人工處置重複 key 再降版。

Revision ID: v2_0037
Revises: v2_0036
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op

revision = "v2_0037"
down_revision = "v2_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_ai_parse_jobs_idempotency_key", "ai_parse_jobs", type_="unique"
    )
    op.create_unique_constraint(
        "uq_ai_parse_jobs_import_idempotency_key",
        "ai_parse_jobs",
        ["import_id", "idempotency_key"],
    )
    op.create_index(
        "ix_ai_parse_jobs_active_created",
        "ai_parse_jobs",
        ["created_at"],
        postgresql_where="status IN ('queued','running')",
    )


def downgrade() -> None:
    op.drop_index("ix_ai_parse_jobs_active_created", table_name="ai_parse_jobs")
    op.drop_constraint(
        "uq_ai_parse_jobs_import_idempotency_key", "ai_parse_jobs", type_="unique"
    )
    op.create_unique_constraint(
        "uq_ai_parse_jobs_idempotency_key", "ai_parse_jobs", ["idempotency_key"]
    )
