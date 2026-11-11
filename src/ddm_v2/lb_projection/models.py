"""投影層資料模型（pydantic v2）。

形狀＝黃金 fixture `server_node_worksheet.json` 的 `rows[]`（實作書 WP2、fixtures/README）。
`ProjectionRow` 是投影層的**唯一輸入型別**；adapter 從 `read_worksheet()` dict 或 fixture 產出它。

出處：Spec §1（名詞）、§2（粒度）、§3（乘數）、§6（欄位）。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VocabKind = Literal["object", "component", "tool", "from", "to", "hand"]
GeneralRole = Literal["take_unit", "scanner", "transport"]


class ProjectionVocab(BaseModel):
    """詞彙查表項：kind 決定是否為工具（Spec §1 tool-held、§4）；name_en → tool_id。"""

    model_config = ConfigDict(extra="forbid")
    kind: VocabKind
    name_en: str | None = None


class ProjectionCycle(BaseModel):
    """一個 motion 的七格 cycle 快照。

    `slot_tmus`：7 格 TMU（已含 repeat，＝引擎 `computed.breakdown[].tmu`）。
    `repeat_counts`：slot index 字串 → N（如 `{"3":8,"4":8,"5":8}`；G2/P5/M3/X4/I5）。
    `slot_inputs`：引擎路徑（WP3 `decompose_engine`）用；fixture 走靜態路徑可缺。
    """

    model_config = ConfigDict(extra="forbid")
    seq_kind: Literal["GM", "CM"]
    slot_tmus: list[float] = Field(min_length=7, max_length=7)
    repeat_counts: dict[str, int] = Field(default_factory=dict)
    x_seconds: float = 0.0
    total_tmu: float
    tech_line: str | None = None
    narrative_en: str | None = None
    narrative_zh: str | None = None
    slot_inputs: dict[str, Any] | None = None
    rule_set_code: str | None = None


class ProjectionLevel(BaseModel):
    """Level System 標註（`level_entries` 對應欄；Spec §5）。"""

    model_config = ConfigDict(extra="forbid")
    ascription: str | None = None
    level: str | None = None
    countersignature: str | None = None
    parent_countersignature: str | None = None
    order: int | None = None
    number: str | None = None
    number_count: int | None = None


class ProjectionTags(BaseModel):
    """LB 標記層（`level_entries` 七個 LB 標記欄；Spec §6、ADR-035 D7）。"""

    model_config = ConfigDict(extra="forbid")
    is_general: bool = False
    general_role: GeneralRole | None = None
    action_type: str | None = None  # IE 標定的動作類型（ruling B, 2026-09-12）；非 tool/general 列的 §6 ③ 級來源
    offline: bool = False
    worker_cub: str | None = None
    segment: str | None = None
    station_pin: int | None = None
    merge_lock: bool = False
    splittable: bool = False
    machine_unattended: bool | None = None  # 三態（ADR-035 D10 §3.4）


class ProjectionRow(BaseModel):
    """投影層輸入的一個 motion（＝一條七格 GM/CM cycle；Spec §1、§2）。"""

    model_config = ConfigDict(extra="forbid")
    wi_row_id: str
    seq_no: int
    letter: str | None = None  # fixture 標示（A/B/…），僅供人閱讀、不進投影邏輯
    sub_activity: str | None = None
    key_parts: str | None = None
    hand: str | None = None
    object_vocab: str | None = None  # vocab key（fixture）或 vocab_id（DB）
    tool_vocab: str | None = None
    frequency: float = 1.0
    simo_group_id: str | None = None
    cycle: ProjectionCycle
    level: ProjectionLevel
    lb_tags: ProjectionTags = Field(default_factory=ProjectionTags)


__all__ = [
    "ProjectionVocab",
    "ProjectionCycle",
    "ProjectionLevel",
    "ProjectionTags",
    "ProjectionRow",
    "VocabKind",
    "GeneralRole",
]
