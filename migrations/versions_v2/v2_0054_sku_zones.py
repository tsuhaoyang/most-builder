"""v2_0054: SKU 標準工作站的區域、DSX 座標快照、物件歸區（ADR-038 D5.1–D5.5，W7a）

1. `zone_categories`：區域類別。固定清單（本 migration 種入，`builtin=true`），admin 可新增。
2. `sku_zones`：按 SKU 的區域（類別、名稱、綁定的 DSX 物件 id、中心座標 3D 公分）。中心座標只由「同步」寫入，
   記錄來自哪一份快照（`center_snapshot_id`）。
3. `sku_placement_snapshots`：使用者按「從 DSX 同步」時拉到的座標快照（DSX `placement_revision`、同步者、時間）。
   之後所有距離都用快照算（ADR-038 I6），不即時查 DSX。每個 SKU 保留最近 20 份（服務層清理）。
4. `sku_object_zones`：(SKU, 物件) → 區域，按 SKU 記住；物件是 `work_vocab_items`。物件座標欄位預留（D5.5，可空）。
   區域必須屬於同一個 SKU（複合 FK），刪除區域前必須先取消歸區（RESTRICT）。

downgrade：有任何區域、快照、歸區或非內建類別就拒絕（不靜默丟掉使用者的設定）。

Revision ID: v2_0054
Revises: v2_0053
Create Date: 2026-11-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "v2_0054"
down_revision = "v2_0053"
branch_labels = None
depends_on = None

# 內建類別（code, name_zh, name_en, sort_order）。code 是穩定鍵，名稱可在之後的 migration 調整。
BUILTIN_CATEGORIES = (
    ("work_surface", "作業區", "Work surface", 10),
    ("incoming", "來料區", "Incoming material", 20),
    ("outgoing", "放料區", "Finished parts", 30),
    ("tool", "工具區", "Tools", 40),
    ("fixture", "治具區", "Fixtures", 50),
    ("other", "其他", "Other", 90),
)

SQL_COUNT_USER_DATA = (
    "SELECT (SELECT COUNT(*) FROM sku_zones) + (SELECT COUNT(*) FROM sku_placement_snapshots) "
    "+ (SELECT COUNT(*) FROM sku_object_zones) + (SELECT COUNT(*) FROM zone_categories WHERE NOT builtin)"
)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()"))


def _coord(prefix: str) -> list[sa.Column]:
    return [sa.Column(f"{prefix}_{a}", sa.Numeric(10, 2), nullable=True) for a in ("x", "y", "z")]


def upgrade() -> None:
    op.create_table(
        "zone_categories",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name_zh", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Text(), nullable=False),
        _ts("created_at"),
        sa.UniqueConstraint("code", name="uq_zone_categories_code"),
        sa.CheckConstraint("code ~ '^[a-z][a-z0-9_]{0,39}$'", name="ck_zone_categories_code_format"),
    )
    op.create_table(
        "sku_placement_snapshots",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_id", PG_UUID(as_uuid=True), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dsx_station_id", sa.Text(), nullable=False),
        sa.Column("placement_revision", sa.Integer(), nullable=False),
        # [{object_id, x, y, z, point_source}]：站內局部座標（公分，原點＝作業員站位），DSX 的量測點；
        # point_source＝anchor（DSX anchor_cm）｜station_local（DSX 沒給 anchor_cm 時的物件原點）
        sa.Column("placements", JSONB(), nullable=False),
        sa.Column("placement_count", sa.Integer(), nullable=False),
        sa.Column("synced_by", sa.Text(), nullable=False),
        _ts("synced_at"),
    )
    op.create_index("ix_sku_placement_snapshots_sku_synced", "sku_placement_snapshots", ["sku_id", "synced_at"])
    op.create_table(
        "sku_zones",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_id", PG_UUID(as_uuid=True), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "category_id", PG_UUID(as_uuid=True), sa.ForeignKey("zone_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("dsx_object_id", sa.Text(), nullable=True),
        *_coord("center"),
        sa.Column(
            "center_snapshot_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("sku_placement_snapshots.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        _ts("created_at"),
        sa.Column("updated_by", sa.Text(), nullable=True),
        _ts("updated_at"),
        sa.UniqueConstraint("sku_id", "name", name="uq_sku_zones_sku_name"),
        sa.UniqueConstraint("id", "sku_id", name="uq_sku_zones_id_sku"),
        sa.CheckConstraint(
            "(center_x IS NULL) = (center_y IS NULL) AND (center_y IS NULL) = (center_z IS NULL)",
            name="ck_sku_zones_center_complete",
        ),
    )
    op.create_table(
        "sku_object_zones",
        sa.Column("sku_id", PG_UUID(as_uuid=True), sa.ForeignKey("skus.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "vocab_item_id", PG_UUID(as_uuid=True), sa.ForeignKey("work_vocab_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("zone_id", PG_UUID(as_uuid=True), nullable=False),
        *_coord("object"),
        sa.Column("assigned_by", sa.Text(), nullable=False),
        _ts("assigned_at"),
        sa.ForeignKeyConstraint(
            ["zone_id", "sku_id"], ["sku_zones.id", "sku_zones.sku_id"],
            name="fk_sku_object_zones_zone_same_sku", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(object_x IS NULL) = (object_y IS NULL) AND (object_y IS NULL) = (object_z IS NULL)",
            name="ck_sku_object_zones_object_complete",
        ),
    )
    op.create_index("ix_sku_object_zones_zone", "sku_object_zones", ["zone_id"])

    cats = sa.table(
        "zone_categories",
        sa.column("code", sa.Text), sa.column("name_zh", sa.Text), sa.column("name_en", sa.Text),
        sa.column("sort_order", sa.Integer), sa.column("builtin", sa.Boolean), sa.column("created_by", sa.Text),
    )
    op.bulk_insert(cats, [
        {"code": c, "name_zh": zh, "name_en": en, "sort_order": o, "builtin": True, "created_by": "system"}
        for c, zh, en, o in BUILTIN_CATEGORIES
    ])


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text(
        "LOCK TABLE zone_categories, sku_zones, sku_placement_snapshots, sku_object_zones IN SHARE ROW EXCLUSIVE MODE"
    ))
    n = bind.execute(sa.text(SQL_COUNT_USER_DATA)).scalar_one()
    if n:
        raise RuntimeError(
            f"v2_0054 downgrade refused: {n} zone / snapshot / assignment / custom category row(s) exist. "
            "Dropping them would silently lose users' station setup. Export or delete them first."
        )
    op.drop_index("ix_sku_object_zones_zone", table_name="sku_object_zones")
    op.drop_table("sku_object_zones")
    op.drop_table("sku_zones")
    op.drop_index("ix_sku_placement_snapshots_sku_synced", table_name="sku_placement_snapshots")
    op.drop_table("sku_placement_snapshots")
    op.drop_table("zone_categories")
