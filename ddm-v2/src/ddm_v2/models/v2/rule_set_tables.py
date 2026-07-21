"""rule_set 子表（2b）：計算引擎讀的版本化 MOST 規則資料。

依據 minimost-sequence-model-core-logic-spec §4（已確認核心）+ scripts/core_logic 驗證器常數。
原則：**表值＝資料**（隨 rule_set 版本而異），**演算法骨架＝程式**（max/gating/sum，由黃金測試鎖）。
slot_inputs 以各表的 `code` 作穩定參照（版本內不可變）。

涵蓋：
- A 三分量帶（reach/twist/foot，取 max）← 修掉舊單一距離帶
- B 身體動作（1205 值 0/10/32/42）
- G 取得、P base、P addon、M 階梯/動詞/旋轉/手度、X、I
overflow 帶以 max_* = NULL 表示「超過所有有限帶時採用」。

`is_active`（ADR-023 §3.3 / D2，v2_0021）——選項級啟用旗標，語意界線務必看清：
- **`load_rule_set_from_db` 永遠不得依 is_active 過濾**（與 §3.4 回放鐵則同源）。
  引擎載入不看治理狀態；否則停用一個選項會讓已存檔且引用它的 cycle 重算出不同 TMU。
- `is_active=false` 只影響 (1) UI 是否列為可選（`GET .../options?active_only=true`）、
  (2) publish 前完整性驗證（必要參數若全部選項停用 → 擋下發布，見
  `rule_set_service.validate_active_options`）。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base


def _rule_set_fk() -> Mapped[UUID]:
    return mapped_column(PG_UUID(as_uuid=True), ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False)


class RuleABand(Base):
    """A 三分量帶：component∈{reach,twist,foot}；取 max(各分量 index)。max_value NULL=overflow。"""

    __tablename__ = "rule_a_bands"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    component: Mapped[str] = mapped_column(Text, nullable=False)  # reach(cm)/twist(deg)/foot(cm)
    max_value: Mapped[float | None] = mapped_column(Numeric(10, 3))  # 上界（含）；NULL=overflow
    index_value: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (CheckConstraint("component IN ('reach','twist','foot')", name="component"),)


class RuleBOption(Base):
    """B 身體動作（單選，1205 值）。"""

    __tablename__ = "rule_b_options"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label_zh: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str | None] = mapped_column(Text)
    index_value: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    sentence_text_zh: Mapped[str | None] = mapped_column(Text)  # 敘事用字（V2；NULL 回退 label_zh）
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (UniqueConstraint("rule_set_id", "code", name="uq_rule_b_options_rule_set_id_code"),)


class RuleGAction(Base):
    """G 取得：requires_modifier 但未勾 → 計 0（gating 為程式邏輯）。"""

    __tablename__ = "rule_g_actions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label_zh: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str | None] = mapped_column(Text)
    modifier_key: Mapped[str | None] = mapped_column(Text)
    requires_modifier: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    base_tmu: Mapped[int] = mapped_column(Integer, nullable=False)
    sentence_text_zh: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (UniqueConstraint("rule_set_id", "code", name="uq_rule_g_actions_rule_set_id_code"),)


class RulePBase(Base):
    """P 放置 base（GM）。"""

    __tablename__ = "rule_p_bases"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label_zh: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    direction_mode: Mapped[str | None] = mapped_column(Text)
    base_tmu: Mapped[int] = mapped_column(Integer, nullable=False)
    sentence_text_zh: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (UniqueConstraint("rule_set_id", "code", name="uq_rule_p_bases_rule_set_id_code"),)


class RulePAddon(Base):
    """P 附加（≤max_select；對準 needs_precision 才 +delta）。"""

    __tablename__ = "rule_p_addons"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label_zh: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str | None] = mapped_column(Text)
    delta_tmu: Mapped[int] = mapped_column(Integer, nullable=False)
    needs_precision: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    max_select: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    display_rule: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'show_self'"))  # 敘事三態（E6）
    sentence_text_zh: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("display_rule IN ('show_self','hidden','prefix_visible_term')", name="ck_rule_p_addons_display_rule"),
        UniqueConstraint("rule_set_id", "code", name="uq_rule_p_addons_rule_set_id_code"),
    )


class RuleMLadderBand(Base):
    """M 距離階梯（ladder/foot 動詞共用）。max_cm NULL=overflow。"""

    __tablename__ = "rule_m_ladder_bands"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    max_cm: Mapped[float | None] = mapped_column(Numeric(10, 3))
    tmu: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class RuleMFootBand(Base):
    """M 腳步帶（V2 起與階梯分離——C2 定案採 v3 值）。V1 無資料時引擎回退 ladder（回放相容）。"""

    __tablename__ = "rule_m_foot_bands"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    max_cm: Mapped[float | None] = mapped_column(Numeric(10, 3))
    tmu: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (UniqueConstraint("rule_set_id", "sort_order", name="uq_rule_m_foot_bands_rule_set_id_sort"),)


class RuleMVerb(Base):
    """M 動詞與計價方式。pricing_kind∈{fixed,ladder,foot,hand,rotate}。"""

    __tablename__ = "rule_m_verbs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label_zh: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str | None] = mapped_column(Text)
    pricing_kind: Mapped[str] = mapped_column(Text, nullable=False)
    fixed_tmu: Mapped[int | None] = mapped_column(Integer)  # pricing_kind=fixed 時用
    sentence_text_zh: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("pricing_kind IN ('fixed','ladder','foot','hand','rotate')", name="pricing_kind"),
        UniqueConstraint("rule_set_id", "code", name="uq_rule_m_verbs_rule_set_id_code"),
    )


class RuleMRotationBand(Base):
    """M 旋轉：依直徑×圈數。max_diameter_cm NULL=overflow。"""

    __tablename__ = "rule_m_rotation_bands"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    max_diameter_cm: Mapped[float | None] = mapped_column(Numeric(10, 3))
    revolutions: Mapped[int] = mapped_column(Integer, nullable=False)
    tmu: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class RuleMHandBand(Base):
    """M 手度（角度）。max_deg NULL=overflow。"""

    __tablename__ = "rule_m_hand_bands"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    max_deg: Mapped[float | None] = mapped_column(Numeric(10, 3))
    tmu: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class RuleXOption(Base):
    """X 處理時間。mode∈{zero,seconds,fixed}；seconds→engine ceil(sec/0.036)；fixed 用 fixed_seconds。"""

    __tablename__ = "rule_x_options"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label_zh: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    fixed_seconds: Mapped[float | None] = mapped_column(Numeric(10, 4))
    sentence_text_zh: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("mode IN ('zero','seconds','fixed')", name="mode"),
        UniqueConstraint("rule_set_id", "code", name="uq_rule_x_options_rule_set_id_code"),
    )


class RuleIOption(Base):
    """I 對齊（單選）。"""

    __tablename__ = "rule_i_options"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[UUID] = _rule_set_fk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    label_zh: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str | None] = mapped_column(Text)
    index_value: Mapped[int] = mapped_column(Integer, nullable=False)
    vision_scope: Mapped[str | None] = mapped_column(Text)  # normal/outside（UI 分組；i_none 為 NULL）
    sentence_text_zh: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("vision_scope IN ('normal','outside')", name="ck_rule_i_options_vision_scope"),
        UniqueConstraint("rule_set_id", "code", name="uq_rule_i_options_rule_set_id_code"),
    )
