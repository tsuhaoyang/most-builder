"""工序表級寬放（impl-02 §3 / OQ-002）：most_worksheets.allowance_percent。

standard_seconds = normal_seconds × (1 + allowance_percent/100)，僅讀取/匯出投影，不落列級欄。
與 level_entries.coefficient（列級難度係數，LB 用）語意分離。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0010"
down_revision = "v2_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("most_worksheets", sa.Column("allowance_percent", sa.Numeric(6, 3), nullable=True))
    op.create_check_constraint("ck_most_worksheets_allowance_nonneg", "most_worksheets",
                               "allowance_percent IS NULL OR allowance_percent >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_most_worksheets_allowance_nonneg", "most_worksheets", type_="check")
    op.drop_column("most_worksheets", "allowance_percent")
