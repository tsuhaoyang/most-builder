"""v2_0020：rule_sets 加 is_active（單一啟用版本）＋ provenance（認證血緣）。

ADR-023 §3.2/§3.3/§3.5：
- is_active：治理旗標，全庫恆有且僅有一個 true（partial unique index 於 DB 層擋併發雙 activate）。
- provenance ∈ {certified_import, manual, cloned}：certified_import 為 IE 認證匯入版本（ADR-014），
  D2 起任何選項級寫入一律 409。
- 資料遷移：V2 設為 active（ADR-014 值權威）；V1 保持 published + inactive（回放版本，永遠可載入）。

⚠️ 回放鐵則（ADR-023 §3.4）：load_rule_set_from_db 不得依 status/is_active 過濾。
本 migration 只加治理欄位，不動任何 FK 與計算路徑。

Revision ID: v2_0020
Revises: v2_0019
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0020"
down_revision = "v2_0019"
branch_labels = None
depends_on = None

_ACTIVE_CODE = "MINIMOST_FACTORY_V2"
_CERTIFIED_CODES = ("MINIMOST_FACTORY_V1", "MINIMOST_FACTORY_V2")


def upgrade() -> None:
    op.add_column(
        "rule_sets",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "rule_sets",
        sa.Column("provenance", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
    )
    # 名稱與 model 端命名慣例 ck_%(table_name)s_%(constraint_name)s 對齊（name="provenance"）。
    op.create_check_constraint(
        "ck_rule_sets_provenance",
        "rule_sets",
        "provenance IN ('certified_import','manual','cloned')",
    )

    # 全庫僅一個 is_active=true：partial unique index on 常數表示式。
    # 併發兩筆 activate 會撞 unique（一成功一失敗），而非靜默雙 active。
    op.execute(
        "CREATE UNIQUE INDEX uq_rule_sets_single_active ON rule_sets ((true)) WHERE is_active"
    )

    # 資料遷移：V2＝active；V1/V2＝certified_import（V1 保持 published + inactive）。
    op.execute(
        sa.text("UPDATE rule_sets SET is_active = true WHERE code = :code").bindparams(
            code=_ACTIVE_CODE
        )
    )
    op.execute(
        sa.text(
            "UPDATE rule_sets SET provenance = 'certified_import' WHERE code IN (:v1, :v2)"
        ).bindparams(v1=_CERTIFIED_CODES[0], v2=_CERTIFIED_CODES[1])
    )

    # 後置自癒：上面兩條 UPDATE 匹配 0 列也算成功（既有環境若改過 code 就會如此），
    # 那會留下「零 active」→ create_worksheet/calculate 上線後才 runtime 500。
    # 故障要在 migration 當下浮現：表內有 published 版本卻無 active → 啟用最舊的 published。
    # 表為空（全新 DB，seed 尚未跑）則放行，由 dev_seed_v2.py 負責啟用。
    conn = op.get_bind()
    has_active = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM rule_sets WHERE is_active)")).scalar()
    if not has_active:
        fallback = conn.execute(
            sa.text("SELECT code FROM rule_sets WHERE status = 'published' ORDER BY created_at LIMIT 1")
        ).scalar()
        if fallback is not None:
            conn.execute(
                sa.text("UPDATE rule_sets SET is_active = true WHERE code = :code").bindparams(code=fallback)
            )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_rule_sets_single_active")
    op.drop_constraint("ck_rule_sets_provenance", "rule_sets", type_="check")
    op.drop_column("rule_sets", "provenance")
    op.drop_column("rule_sets", "is_active")
