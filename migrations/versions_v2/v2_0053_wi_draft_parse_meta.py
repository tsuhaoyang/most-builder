"""v2_0053: 編輯區草稿的解析紀錄與過期判斷（ADR-038 D3、ADR-037 D3／D5，W3）

`wi_draft_rows` 加三欄（皆可空，加法）：
1. `source_rule_set_id`：草稿建立（或最後一次確認）時目標工時表的規則版本。工時表改綁規則版本後，
   已確認的草稿在寫入時轉為過期（ADR-037 D5 stale 條件）。
2. `parse_snapshot`：解析產生的草稿（單句 AI、整份上傳）在建立當下的紀錄：`complete`、`issues`、
   `cycle_hash`（建立時 cycle 的雜湊，判斷人有沒有補過）、`import_input_hash`（Excel 列的輸入雜湊）、`ai_status`。
   寫入檢查（ADR-037 D3「可接受的 motion」）靠它；人工建的草稿為空。
3. `stale_reason`：過期原因（`rule_set_changed`｜`import_row_changed`）。轉過期時草稿回到 pending，再確認時清除。

downgrade：有任何尚未寫入的草稿帶 `parse_snapshot` 或 `stale_reason` 就拒絕——丟掉它們會讓未完整的 AI 草稿通過寫入檢查。

Revision ID: v2_0053
Revises: v2_0052
Create Date: 2026-11-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "v2_0053"
down_revision = "v2_0052"
branch_labels = None
depends_on = None

# 組進 DDL 的字面常數（DDL 無法 bind 參數），不得改成外部輸入
_CK = "ck_wi_draft_rows_stale_reason"
_CK_DEF = "stale_reason IS NULL OR stale_reason IN ('rule_set_changed','import_row_changed')"
_FK = "fk_wi_draft_rows_source_rule_set_id_rule_sets"

# 已寫入的草稿是紀錄，丟掉它的 parse_snapshot 不影響寫入檢查，所以不計
SQL_COUNT_META = (
    "SELECT COUNT(*) FROM wi_draft_rows WHERE status <> 'committed' "
    "AND (parse_snapshot IS NOT NULL OR stale_reason IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column("wi_draft_rows", sa.Column("source_rule_set_id", PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(_FK, "wi_draft_rows", "rule_sets", ["source_rule_set_id"], ["id"], ondelete="SET NULL")
    op.add_column("wi_draft_rows", sa.Column("parse_snapshot", JSONB(), nullable=True))
    op.add_column("wi_draft_rows", sa.Column("stale_reason", sa.Text(), nullable=True))
    op.execute(sa.text(f"ALTER TABLE wi_draft_rows ADD CONSTRAINT {_CK} CHECK ({_CK_DEF})"))
    # 既有草稿以目前工時表的規則版本為基準（不會因為這次 migration 被判過期）
    op.execute(sa.text(
        "UPDATE wi_draft_rows d SET source_rule_set_id = w.default_rule_set_id "
        "FROM most_worksheets w WHERE w.id = d.worksheet_id"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("LOCK TABLE wi_draft_rows IN SHARE ROW EXCLUSIVE MODE"))
    n = bind.execute(sa.text(SQL_COUNT_META)).scalar_one()
    if n:
        raise RuntimeError(
            f"v2_0053 downgrade refused: {n} wi_draft_rows row(s) carry a parse_snapshot or stale_reason. "
            "Without them, incomplete AI drafts would pass the commit check. Commit or delete those uncommitted drafts first."
        )
    op.execute(sa.text(f"ALTER TABLE wi_draft_rows DROP CONSTRAINT IF EXISTS {_CK}"))
    op.drop_column("wi_draft_rows", "stale_reason")
    op.drop_column("wi_draft_rows", "parse_snapshot")
    op.drop_constraint(_FK, "wi_draft_rows", type_="foreignkey")
    op.drop_column("wi_draft_rows", "source_rule_set_id")
