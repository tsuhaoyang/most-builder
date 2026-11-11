"""v2_0038: 同義詞一面多 code（IE 方向變體裁決）

背景（D3-017）：IE 裁決「放至/放置」按情境對應兩個 P 選項——
`p_place_single`（機構件對準情境，priority 0＝預設）與 `p_place_none`
（盤面無方向情境，priority 1）。原 UNIQUE(rule_set_id, parameter, synonym_norm)
禁止同一詞面掛兩個 code，使 `priority` 欄的既定用途（同面多 code 時的排序，
見 docs/llm/gold-review/synonym-candidates.md）形同虛設。

變更：UNIQUE 放寬為 (rule_set_id, parameter, synonym_norm, option_code)——
仍擋「同一映射重複登記」，但允許 IE 核可的方向變體並存；同面多 code 的
選擇順序由 priority 決定（數字小者優先，0＝預設；parser 端 tie-break 見
src/ddm_v2/nlp/lexicon.py build_lexicon）。

同義詞僅影響建議層、不影響工時（ADR-023）；引擎與 rule-set 值零改動。

Revision ID: v2_0038
Revises: v2_0037
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op

revision = "v2_0038"
down_revision = "v2_0037"
branch_labels = None
depends_on = None

_OLD_UQ = "uq_rule_option_synonyms_rule_set_id_parameter_synonym_norm"
# 舊命名慣例（表_全欄位）在此會超過 PostgreSQL 63 字元識別字上限——縮寫欄位段
_NEW_UQ = "uq_rule_option_synonyms_rs_param_norm_code"


def upgrade() -> None:
    op.drop_constraint(_OLD_UQ, "rule_option_synonyms", type_="unique")
    op.create_unique_constraint(
        _NEW_UQ,
        "rule_option_synonyms",
        ["rule_set_id", "parameter", "synonym_norm", "option_code"],
    )


def downgrade() -> None:
    # 破壞性 downgrade（有紀錄）：重新收緊前必須先移除同面多 code 的變體列，
    # 只保留每組 (rule_set_id, parameter, synonym_norm) 中 priority 最小
    # （＝預設；再以 option_code 決勝）的那一列，否則舊 UNIQUE 建不回去。
    op.execute(
        """
        DELETE FROM rule_option_synonyms s
        USING rule_option_synonyms keep
        WHERE keep.rule_set_id = s.rule_set_id
          AND keep.parameter = s.parameter
          AND keep.synonym_norm = s.synonym_norm
          AND (keep.priority, keep.option_code) < (s.priority, s.option_code)
        """
    )
    op.drop_constraint(_NEW_UQ, "rule_option_synonyms", type_="unique")
    op.create_unique_constraint(
        _OLD_UQ,
        "rule_option_synonyms",
        ["rule_set_id", "parameter", "synonym_norm"],
    )
