"""v2_0055: 距離建議與建模政策的明確預設（ADR-038 D5.6 修訂，W7b）

1. `wi_row_distance_suggestions`：依區域座標算出的距離建議，一列一格（a0／a3／m3／a6）。
   - 是**建議**（ADR-031 I4）：不進 TMU 路徑；使用者按「套用」才經整份存檔寫進工時表，並把該列距離狀態設為 confirmed。
   - 記錄出處：兩端點（物件、區域、座標、`zone_center`｜`object_coordinate`、DSX `point_source`）、快照 id、
     使用的門檻與人端偏移、建模政策版本。
   - `wi_row_id` 是軟參考（沒有 FK）：整份存檔會刪除重建 wi_rows（id 沿用），有 FK 的話每次存檔都會連帶刪掉建議
     （同 wi_draft_rows.committed_wi_row_id）。列被刪後留下的建議由讀取時過濾、下次計算時清掉。
   - 唯一鍵含 worksheet_id：列 id 由前端產生，不同工時表不得互相影響。
2. `modeling_policy_defaults`：新建工時表用哪個建模政策版本，由 admin **明確指定**（R2a 禁止以 MAX(version_no) 隱式選版）。
   種入 MODELING_FACTORY → V1（與原本寫死的預設相同）。admin 發布新的距離設定時建新版本並把預設指過去；
   既有工時表記住自己的版本，不受影響（ADR-038 D5.6 (b)）。

3. 修正 v2_0054 的 CHECK 約束名：當時把完整名稱傳給 `CheckConstraint`，命名慣例又加了一次前綴
   （`ck_sku_zones_ck_sku_zones_center_complete`）。這裡改回與 ORM 一致的名稱（`ck_sku_zones_center_complete`），
   只在舊名存在時改。CHECK 只傳短名（`slot`），由命名慣例補前綴。

downgrade：有任何距離建議、或預設不是 V1 就拒絕。

Revision ID: v2_0055
Revises: v2_0054
Create Date: 2026-11-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "v2_0055"
down_revision = "v2_0054"
branch_labels = None
depends_on = None

MODELING_FACTORY_CODE = "MODELING_FACTORY"
MODELING_FACTORY_V1_ID = "a1000000-0000-4000-8000-000000000001"

# v2_0054 的約束名修正：(table, 錯誤名, 正確名)
_CK_RENAMES = (
    ("zone_categories", "ck_zone_categories_ck_zone_categories_code_format", "ck_zone_categories_code_format"),
    ("sku_zones", "ck_sku_zones_ck_sku_zones_center_complete", "ck_sku_zones_center_complete"),
    ("sku_object_zones", "ck_sku_object_zones_ck_sku_object_zones_object_complete",
     "ck_sku_object_zones_object_complete"),
)

SQL_COUNT_BLOCKERS = (
    "SELECT (SELECT COUNT(*) FROM wi_row_distance_suggestions) + "
    "(SELECT COUNT(*) FROM modeling_policy_defaults WHERE version_id <> CAST(:v1 AS uuid))"
)


def _rename_constraints(pairs) -> None:
    # 名稱都是本檔常數（DDL 無法 bind 參數）；只在來源名存在時改，重跑或新庫都安全
    for table, src, dst in pairs:
        op.execute(sa.text(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '" + src + "') THEN "
            "ALTER TABLE " + table + " RENAME CONSTRAINT " + src + " TO " + dst + "; END IF; END $$"
        ))


def upgrade() -> None:
    _rename_constraints(_CK_RENAMES)
    op.create_table(
        "wi_row_distance_suggestions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "worksheet_id", PG_UUID(as_uuid=True), sa.ForeignKey("most_worksheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("wi_row_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=True),
        sa.Column("distance_cm", sa.Numeric(8, 1), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("endpoints", JSONB(), nullable=False),
        sa.Column(
            "snapshot_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("sku_placement_snapshots.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("threshold_cm", sa.Numeric(8, 1), nullable=False),
        sa.Column("person_offset_cm", JSONB(), nullable=False),
        sa.Column(
            "modeling_policy_version_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("modeling_policy_versions.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("computed_by", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("applied_by", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("worksheet_id", "wi_row_id", "slot", name="uq_wi_row_distance_suggestions_ws_row_slot"),
        sa.CheckConstraint("slot IN ('a0','a3','m3','a6')", name="slot"),
        sa.CheckConstraint(
            "status IN ('suggested','needs_ie','unavailable')", name="status"
        ),
        sa.CheckConstraint(
            "field IS NULL OR field IN ('reach_cm','foot_cm','distance_cm')", name="field"
        ),
        sa.CheckConstraint(
            "status <> 'suggested' OR (field IS NOT NULL AND distance_cm IS NOT NULL)",
            name="suggested_has_value",
        ),
    )
    op.create_index(
        "ix_wi_row_distance_suggestions_worksheet", "wi_row_distance_suggestions", ["worksheet_id", "wi_row_id"]
    )
    op.create_table(
        "modeling_policy_defaults",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column(
            "version_id", PG_UUID(as_uuid=True), sa.ForeignKey("modeling_policy_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("set_by", sa.Text(), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    # V1 由 v2_0030 種入；空庫（測試）也有。用 INSERT…SELECT，V1 不存在時不種（解析時 fail closed，同既有行為）
    op.execute(sa.text(
        "INSERT INTO modeling_policy_defaults (code, version_id, set_by) "
        "SELECT :code, id, 'system' FROM modeling_policy_versions WHERE id = CAST(:v1 AS uuid)"
    ).bindparams(code=MODELING_FACTORY_CODE, v1=MODELING_FACTORY_V1_ID))


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("LOCK TABLE wi_row_distance_suggestions, modeling_policy_defaults IN SHARE ROW EXCLUSIVE MODE"))
    n = bind.execute(sa.text(SQL_COUNT_BLOCKERS), {"v1": MODELING_FACTORY_V1_ID}).scalar_one()
    if n:
        raise RuntimeError(
            f"v2_0055 downgrade refused: {n} distance suggestion(s) or a non-V1 modeling policy default exist. "
            "Without the default table, new worksheets would silently fall back to V1. Clear them first."
        )
    op.drop_table("modeling_policy_defaults")
    _rename_constraints([(t, dst, src) for t, src, dst in _CK_RENAMES])
    op.drop_index("ix_wi_row_distance_suggestions_worksheet", table_name="wi_row_distance_suggestions")
    op.drop_table("wi_row_distance_suggestions")
