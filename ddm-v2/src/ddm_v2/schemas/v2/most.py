"""v2 MOST API 契約（Pydantic）：cycle DTO（前端 conform 的接縫）+ 計算/Level 回應。

slot 以各 rule-set 表的 code 參照（穩定）。GM/CM 變體以可選 slot 欄表達；
cycle_in_to_engine() 依 seq 只取相關 slot，轉成 most_engine.compute_cycle 的 cycle dict。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DEFAULT_RULE_SET = "MINIMOST_FACTORY_V2"  # ADR-014：v3 IE 認證字典；V1 僅供既有 cycle 回放


# ── slot 輸入 ──
class ManualOverride(BaseModel):
    """E7：人工覆寫（值取代＋留痕）。"""

    tmu: float
    reason: str
    by: str | None = None


class ASlot(BaseModel):
    reach_cm: float = 0
    twist_deg: float = 0
    foot_cm: float = 0
    repeat_count: int | None = None  # passthrough：A 格禁 repeat，由引擎 _no_repeat 擋（REPEAT_INVALID）
    manual_override: ManualOverride | None = None


class BSlot(BaseModel):
    b_code: str | None = None
    repeat_count: int | None = None  # passthrough：B 格禁 repeat，由引擎 _no_repeat 擋（REPEAT_INVALID）
    manual_override: ManualOverride | None = None


class GSlot(BaseModel):
    g_code: str | None = None
    modifiers: dict[str, bool] = Field(default_factory=dict)  # V1 gating 用；V2 資料下無作用
    repeat_count: int | None = None  # 範圍驗證權威＝引擎 _repeat（REPEAT_INVALID）
    manual_override: ManualOverride | None = None


class MComponent(BaseModel):
    verb_code: str | None = None
    distance_cm: float = 0
    angle_deg: float = 0
    revolutions: int = 1
    diameter_cm: float = 0


class MSlot(BaseModel):
    m_components: list[MComponent] = Field(default_factory=list)
    repeat_count: int | None = None  # 只乘動詞分量再 max（E4）；範圍驗證權威＝引擎
    manual_override: ManualOverride | None = None


class XSlot(BaseModel):
    x_code: str | None = None
    x_seconds: float = 0
    repeat_count: int | None = None  # 範圍驗證權威＝引擎
    manual_override: ManualOverride | None = None


class PSlot(BaseModel):
    p_base_code: str | None = None
    p_addon_codes: list[str] = Field(default_factory=list)
    precision: bool = False  # V1 對準精度 gating 用；V2 資料下無作用
    repeat_count: int | None = None  # 範圍驗證權威＝引擎
    manual_override: ManualOverride | None = None


class ISlot(BaseModel):
    i_code: str | None = None
    repeat_count: int | None = None  # 範圍驗證權威＝引擎
    manual_override: ManualOverride | None = None


class CycleIn(BaseModel):
    """一條 GM/CM cycle。GM 用 a3/b4/p5；CM 用 m3/x4/i5（依 seq 取用）。"""

    seq: Literal["GM", "CM"]
    rule_set_code: str = DEFAULT_RULE_SET
    a0: ASlot = Field(default_factory=ASlot)
    b1: BSlot = Field(default_factory=BSlot)
    g2: GSlot = Field(default_factory=GSlot)
    a3: ASlot | None = None
    m3: MSlot | None = None
    b4: BSlot | None = None
    x4: XSlot | None = None
    p5: PSlot | None = None
    i5: ISlot | None = None
    a6: ASlot = Field(default_factory=ASlot)
    frequency: float = 1
    simo_group_id: str | None = None


def cycle_in_to_engine(c: CycleIn) -> dict[str, Any]:
    """轉成 most_engine 的 cycle dict（依 seq 只放相關 slot，跨模型欄位自然不傳）。"""
    slots: dict[int, dict[str, Any]] = {
        0: c.a0.model_dump(),
        1: c.b1.model_dump(),
        2: c.g2.model_dump(),
        6: c.a6.model_dump(),
    }
    if c.seq == "GM":
        slots[3] = (c.a3 or ASlot()).model_dump()
        slots[4] = (c.b4 or BSlot()).model_dump()
        slots[5] = (c.p5 or PSlot()).model_dump()
    else:
        slots[3] = (c.m3 or MSlot()).model_dump()
        slots[4] = (c.x4 or XSlot()).model_dump()
        slots[5] = (c.i5 or ISlot()).model_dump()
    return {"seq": c.seq, "slots": slots}


# ── 計算回應 ──
class SlotBreakdown(BaseModel):
    letter: str
    tmu: float


class CalculateResponse(BaseModel):
    seq: str
    rule_set_code: str
    total_tmu: float
    total_seconds: float
    tech_line: str
    breakdown: list[SlotBreakdown]


# ── Level 驗證契約 ──
class LevelRowIn(BaseModel):
    content: str
    raw_seconds: float = 1
    coefficient: float = 1
    number: str | None = None
    number_count: int | None = None
    ascription: str | None = None
    level: str | None = None
    countersignature: str | None = None
    parent_countersignature: str | None = None
    order: int | None = None


class LevelIssueOut(BaseModel):
    code: str
    row_index: int
    message: str


class LevelValidateResponse(BaseModel):
    valid: bool
    issues: list[LevelIssueOut]


class LevelOutputResponse(BaseModel):
    nodes: list[dict[str, Any]]               # 每 node 含 levels/level_min/level_max/variable（自由度）
    precedence_edges: list[dict[str, str]]
    groups: list[dict[str, Any]]              # sub/cub 完整語意（type/parent/same_station/movable/members）
    cub_groups: dict[str, list[str]]
    sub_groups: dict[str, list[str]]
    group_parents: dict[str, str]
    number_constraints: dict[str, dict[str, Any]]
