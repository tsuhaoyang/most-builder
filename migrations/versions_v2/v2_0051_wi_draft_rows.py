"""v2_0051: 工作區編輯區（ADR-038 D2／D3，W1）＋ wi_rows.provenance 加 'ai_external'（ADR-037 D5）

## 做兩件事

1. 新表 `wi_draft_rows`：編輯區的草稿列，一列＝一個 motion（ADR-038 D2「審核單位是 motion」）。
   - 屬於一份工時表（`worksheet_id`，工時表刪除時連帶刪除）。
   - `content` 是一列的完整輸入（形狀同 `WiRowSaveIn` 去掉 id／seq_no／level，由 `schemas/v2/wi_draft.py` 驗證）。
   - `source`：manual｜ai_service｜rule_based｜imported；`status`：pending｜confirmed｜committed。
   - 同一句拆出的 motion 共用 `group_key`，組內順序 `order_in_group`；編輯區整體順序 `sort_order`。
   - 已寫入工時表的草稿保留（status=committed），記 `committed_wi_row_id`（軟參考：存檔是整份取代、
     列 id 由前端穩定保存，FK 會被整份取代的刪除擋住或連帶刪掉）。
   - 出處：`ai_parse_run_id`（FK，SET NULL）、`import_row_id`（FK，SET NULL）、`source_revision`。
2. `wi_rows.provenance` 的 CHECK 加 `'ai_external'`（ADR-037 D5：寫入工時表的 AI 列由伺服器標示）。
   實際約束名是 **`ck_wi_rows_provenance`**：v2_0001 建的雙前綴名 `ck_wi_rows_ck_wi_rows_provenance` 已被 v2_0015
   以 raw SQL 刪掉、改用單前綴名重建（2026-11-23 在測試 DB 以 pg_constraint 確認）。兩個名字都先 DROP IF EXISTS，
   再以單前綴名重建，確保只剩一條約束——只刪其中一個會留下舊約束把新值擋掉。

## downgrade：有資料就拒絕，不刪資料

有任何 `wi_draft_rows` 列（含已寫入的紀錄），或有 `wi_rows.provenance='ai_external'` 的列，就 `RuntimeError`。
理由同 v2_0050：靜默刪除會丟掉「這一列是誰、從哪裡確認進來的」紀錄。

Revision ID: v2_0051
Revises: v2_0050
Create Date: 2026-11-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0051"
down_revision = "v2_0050"
branch_labels = None
depends_on = None

# 下列常數會組進 DDL（DDL 無法 bind 參數），必須維持字面常數，不得改成外部輸入。
_PROV_CK = "ck_wi_rows_provenance"
_PROV_CK_LEGACY = "ck_wi_rows_ck_wi_rows_provenance"
_PROV_NEW = "provenance IN ('manual','bom_draft','imported','ai_external')"
_PROV_OLD = "provenance IN ('manual','bom_draft','imported')"

SQL_COUNT_DRAFTS = "SELECT COUNT(*) FROM wi_draft_rows"
SQL_COUNT_AI_EXTERNAL_ROWS = "SELECT COUNT(*) FROM wi_rows WHERE provenance = 'ai_external'"


def upgrade() -> None:
    op.create_table(
        "wi_draft_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "worksheet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("most_worksheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("group_key", sa.Text(), nullable=False),
        sa.Column("order_in_group", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("ai_candidates", postgresql.JSONB(), nullable=True),
        sa.Column(
            "ai_parse_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_parse_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "import_row_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_rows.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_revision", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("confirmed_by", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_by", sa.Text(), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_wi_row_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('manual','ai_service','rule_based','imported')", name="source"
        ),
        sa.CheckConstraint("status IN ('pending','confirmed','committed')", name="status"),
        # 狀態與時間戳一致：confirmed 一定有確認者；committed 一定有寫入者與寫入的列
        sa.CheckConstraint(
            "status = 'pending' OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="confirmed_has_actor",
        ),
        sa.CheckConstraint(
            "status <> 'committed' OR (committed_by IS NOT NULL AND committed_at IS NOT NULL "
            "AND committed_wi_row_id IS NOT NULL)",
            name="committed_has_actor",
        ),
    )
    op.create_index("ix_wi_draft_rows_worksheet_status", "wi_draft_rows", ["worksheet_id", "status"])
    op.create_index("ix_wi_draft_rows_worksheet_sort", "wi_draft_rows", ["worksheet_id", "sort_order"])

    op.execute(sa.text(f"ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS {_PROV_CK}"))
    op.execute(sa.text(f"ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS {_PROV_CK_LEGACY}"))
    op.execute(sa.text(f"ALTER TABLE wi_rows ADD CONSTRAINT {_PROV_CK} CHECK ({_PROV_NEW})"))


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("LOCK TABLE wi_rows IN SHARE ROW EXCLUSIVE MODE"))
    drafts = bind.execute(sa.text(SQL_COUNT_DRAFTS)).scalar_one()
    ai_rows = bind.execute(sa.text(SQL_COUNT_AI_EXTERNAL_ROWS)).scalar_one()
    if drafts or ai_rows:
        raise RuntimeError(
            f"v2_0051 downgrade refused: {drafts} wi_draft_rows row(s) and {ai_rows} wi_rows row(s) with "
            "provenance='ai_external' exist. Dropping them would silently lose who confirmed what into the "
            "worksheet. Export or remove these rows deliberately, then downgrade again."
        )
    op.execute(sa.text(f"ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS {_PROV_CK}"))
    op.execute(sa.text(f"ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS {_PROV_CK_LEGACY}"))
    op.execute(sa.text(f"ALTER TABLE wi_rows ADD CONSTRAINT {_PROV_CK} CHECK ({_PROV_OLD})"))
    op.drop_index("ix_wi_draft_rows_worksheet_sort", table_name="wi_draft_rows")
    op.drop_index("ix_wi_draft_rows_worksheet_status", table_name="wi_draft_rows")
    op.drop_table("wi_draft_rows")
