"""motion_modules API 契約（Pydantic v2）。

impl-04：組件庫 CRUD + 版本發布 + 工序表實體化。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ddm_v2.schemas.v2.most import CycleIn


# ── 模組列（版本 rows JSONB 的單元素） ───────────────────────────────
class ModuleRowIn(BaseModel):
    """一個模組列（publish 時送入，存成 rows JSONB 元素）。"""

    sub_activity: str | None = None
    hand: str = Field(..., pattern="^(LH|RH|BH)$")
    frequency: int = Field(1, ge=1)
    simo_pair_index: int | None = None   # 指向 rows 陣列內的主列（0-based）；宣告者＝從屬列，貢獻 0（ADR-020）
    vocab_refs: dict[str, Any] = Field(default_factory=dict)
    # 必含 object_vocab_id（UUID str）供實體化時填 WiRow；
    # 其餘 from_vocab_id / to_vocab_id / tool_vocab_id 選填。
    cycle: CycleIn


# ── 發布請求 ─────────────────────────────────────────────────────────
class PublishRequest(BaseModel):
    """POST /motion-modules/{id}/publish body。

    rule_set_id / rule_set_code 恰好擇一（F-01 契約）：
    - rule_set_id：直接指定規則版本 UUID。
    - rule_set_code：由 service 解析成 id（找不到 → 404）。
    """

    # SM-2：max_length=100 防止惡意發布數千列導致引擎 OOM。
    rows: list[ModuleRowIn] = Field(..., min_length=1, max_length=100)
    rule_set_id: uuid.UUID | None = None      # 發布當下使用的規則版本 ID
    rule_set_code: str | None = None          # 或以 code 指定（service 解析）

    @model_validator(mode="after")
    def _exactly_one_rule_set_ref(self) -> "PublishRequest":
        if (self.rule_set_id is None) == (self.rule_set_code is None):
            raise ValueError("rule_set_id 與 rule_set_code 必須恰好提供一個")
        return self


# ── apply-back 請求（工序表同步回模組庫） ────────────────────────────
class VersionFromRowsRequest(BaseModel):
    """POST /motion-modules/{id}/versions/from-rows body。

    語義（F-03b §3）：把已修改的 rows 同步回模組，建立新版本；
    不改 module.status，讓使用者自行決定是否 promote。
    """

    # SM-2：同 publish 限制，防 OOM。
    rows: list[ModuleRowIn] = Field(..., min_length=1, max_length=100)
    rule_set_id: uuid.UUID           # 驗算使用的規則版本 ID


# ── 實體化請求（工序表 from-module）───────────────────────────────────
class FromModuleRequest(BaseModel):
    """POST /worksheets/{wid}/rows/from-module body。"""

    module_id: uuid.UUID
    version_no: int | None = None    # None → 使用 current_version


# ── 模組建立 / 更新 ──────────────────────────────────────────────────
class MotionModuleCreate(BaseModel):
    """POST /motion-modules body。"""

    name_zh: str = Field(..., min_length=1, max_length=200)
    category: str | None = None
    keywords: list[str] = Field(default_factory=list)
    scope: Literal["personal", "site", "global"] = "personal"
    owner: str | None = None      # personal scope 時自動填 current_user；可覆寫
    site_id: uuid.UUID | None = None


class MotionModuleUpdate(BaseModel):
    """PUT /motion-modules/{id} body（全選填，只送想改的欄位）。

    SM-4：owner 欄位已移除，不允許呼叫方重新指派 owner；
    owner 在 create 時由 service 設定，之後不可更改。
    """

    name_zh: str | None = Field(None, min_length=1, max_length=200)
    category: str | None = None
    keywords: list[str] | None = None
    scope: Literal["personal", "site", "global"] | None = None
    site_id: uuid.UUID | None = None


# ── 版本回應 ─────────────────────────────────────────────────────────
class MotionModuleVersionResponse(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    version_no: int
    rule_set_id: uuid.UUID
    rows: list[dict[str, Any]]
    narrative_zh: str | None
    total_tmu: float
    total_seconds: float
    published_by: str
    published_at: datetime

    model_config = {"from_attributes": True}


# ── 模組回應 ─────────────────────────────────────────────────────────
class MotionModuleResponse(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID | None
    name_zh: str
    category: str | None
    keywords: list[str]
    scope: str
    owner: str | None
    status: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    current_version_detail: MotionModuleVersionResponse | None = None
    # F-02b 輕量摘要欄（自 current version 回填；尚無發布版本時 None）
    total_tmu: float | None = None
    action_count: int | None = None
    # 摘要欄：取 current version rows[0] 的 cycle seq（"GM"/"CM"）與 hand（"LH"/"RH"/"BH"）；
    # 無版本/無 rows → None。
    seq_kind: str | None = None
    hand: str | None = None

    model_config = {"from_attributes": True}


# ── 實體化回應 ───────────────────────────────────────────────────────
class InstantiatedRowOut(BaseModel):
    wi_row_id: uuid.UUID
    seq_no: int
    sub_activity: str | None
    hand: str | None
    frequency: float
    simo_group_id: str | None
    source_module_id: uuid.UUID
    source_module_version: int
    total_tmu: float
    total_seconds: float


class InstantiateResponse(BaseModel):
    new_rows: list[InstantiatedRowOut]
    tmu_drift: list[dict[str, Any]] = Field(default_factory=list)
    # 每個 drift 項目：{"row_index": int, "module_tmu": float, "actual_tmu": float, "delta": float}
    skipped_vocab_missing: int = 0
    # 因 vocab_refs.object_vocab_id 缺失而跳過的列數（WiRow.object_vocab_id NOT NULL 不可省）


# ── 排序請求（stub） ──────────────────────────────────────────────────
class ReorderRequest(BaseModel):
    """PUT /motion-modules/reorder body。

    ordered_ids: 前端期望的新排序（UUID 字串清單）。
    本 iteration 不持久化至 DB（motion_modules 無 seq_no 欄位）；
    前端在 local state 管理顯示順序。
    """

    ordered_ids: list[str]  # UUID strings in new order
