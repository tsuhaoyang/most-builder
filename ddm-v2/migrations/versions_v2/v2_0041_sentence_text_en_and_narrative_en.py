"""v2_0041: sentence_text_en（7 張選項表）＋ most_cycles.narrative_en（ADR-032 D7.2，純加法）

`label_zh` 與 `sentence_text_zh` 是兩個不同語意的欄（標籤要能在下拉選單中辨義、句面要能
入句，見 ADR-032 1.2a），英文同樣需要兩欄——`label_en` 已於 v2_0002/v2_0009 存在，
本次補上句面欄。比照 v2_0009 建立 `sentence_text_zh` 的同一批 7 張表。

`most_cycles.narrative_en` 與既有 `narrative_zh` 對稱，同為**可重生快取**（NULL 表示
尚未產生，由 `scripts/backfill_narrative_en.py` 回填；回填以每列自己的 `rule_set_id`
載標籤，不重算 TMU——ADR-032 I4）。

`motion_module_versions` **刻意不加** `narrative_en`（ADR-032 D7.2）：該表是不可變版本
快照，為舊快照回填等於改寫不可變列。英文敘事改為讀取時以該版本 pin 的 `rule_set_id`
即時產生，不落盤。

Revision ID: v2_0041
Revises: v2_0040
Create Date: 2026-08-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0041"
down_revision = "v2_0040"
branch_labels = None
depends_on = None

# 與 v2_0009 的 `_SENTENCE_TABLES` 同一組表（該次建立 sentence_text_zh）。
_SENTENCE_TABLES = (
    "rule_b_options",
    "rule_g_actions",
    "rule_p_bases",
    "rule_p_addons",
    "rule_m_verbs",
    "rule_x_options",
    "rule_i_options",
)


def upgrade() -> None:
    for t in _SENTENCE_TABLES:
        op.add_column(t, sa.Column("sentence_text_en", sa.Text(), nullable=True))
    op.add_column("most_cycles", sa.Column("narrative_en", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("most_cycles", "narrative_en")
    for t in _SENTENCE_TABLES:
        op.drop_column(t, "sentence_text_en")
