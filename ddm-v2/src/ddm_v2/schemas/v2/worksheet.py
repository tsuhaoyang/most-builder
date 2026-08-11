"""v2 worksheet 持久化契約：存整份 WI（rows = wi_row + cycle + level）。"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from ddm_v2.schemas.v2.most import CycleIn


class LevelFieldsIn(BaseModel):
    coefficient: float = 1
    ascription: str | None = None
    level: str | None = None
    countersignature: str | None = None
    parent_countersignature: str | None = None
    order: int | None = None
    number: str | None = None
    number_count: int | None = None
    machine_count: int = 1
    manpower: int = 1


class WiRowSaveIn(BaseModel):
    id: uuid.UUID                       # 前端生成的穩定 id（F4）
    seq_no: int
    sub_activity: str | None = None
    key_parts: str | None = None
    hand: str | None = None
    object_vocab_id: uuid.UUID | None = None
    from_vocab_id: uuid.UUID | None = None
    to_vocab_id: uuid.UUID | None = None
    tool_vocab_id: uuid.UUID | None = None
    frequency: float = 1
    simo_group_id: str | None = None            # SIMO 標記＋配對資訊（ADR-020：非空＝該列貢獻 0；主列不標記）
    simo_with_row_id: uuid.UUID | None = None   # 輸入形式（E5 配對，service 僅標記從屬列）
    narrative: str | None = None        # 敘述（前端合成；存 most_cycles.narrative_zh，供匯出 METHOD）
    cycle: CycleIn
    level: LevelFieldsIn = Field(default_factory=LevelFieldsIn)


class WorksheetSaveIn(BaseModel):
    rows: list[WiRowSaveIn] = Field(default_factory=list)
    # 工序表級寬放%（data-model §2.5）：選填；未帶＝不動既有值（加法相容），帶 null＝清除。
    allowance_percent: float | None = Field(default=None, ge=0)
    # R1：樂觀鎖；過渡期可省略（legacy），前端應一律送。
    base_revision: int | None = Field(default=None, ge=1)


class DefaultRuleSetInfo(BaseModel):
    """工序表建立時凍結的 default rule-set 快照的**現況**狀態（ADR-023 §3.4-4 警示徽章用）。

    ⚠️ 純顯示層資料：僅供前端判斷「本工序表用的是不是已下架版本」以顯示徽章。
    不進計算路徑——cycle 的回放仍由各列快照的 rule_set_id 決定（回放鐵則）。
    """
    code: str
    status: str          # draft / published / retired
    is_active: bool


class PolicyVersionInfo(BaseModel):
    """Worksheet 建立／clone 時 snapshot 的 policy 現況（R2a；顯示／追溯，不進 MOST 計算）。"""

    id: uuid.UUID
    code: str
    version_no: int
    name: str
    status: str  # draft / published / retired
    validator_revision: str | None = None
    output_contract_version: str | None = None


class WorksheetReadOut(BaseModel):
    worksheet_id: uuid.UUID
    status: str
    rows: list[dict[str, Any]]
    total_tmu: float
    # 時間投影：normal＝引擎輸出；standard＝normal×(1+allowance%/100)，allowance 未設時為 null。
    normal_seconds: float
    allowance_percent: float | None = None
    standard_seconds: float | None = None
    # ADR-023 §3.4-4：default_rule_set_id 是建立時凍結的快照；此欄帶其現況狀態供警示徽章。
    # default_rule_set_id 可為 NULL → 此欄為 null，前端不顯示徽章。
    default_rule_set: DefaultRuleSetInfo | None = None
    # R2a：policy snapshot（遷移前可能 null）
    modeling_policy: PolicyVersionInfo | None = None
    level_policy: PolicyVersionInfo | None = None
    # R1 / ADR-027
    revision_no: int = 1
    content_hash: str | None = None
    last_edited_by: str | None = None
    last_edited_at: str | None = None
