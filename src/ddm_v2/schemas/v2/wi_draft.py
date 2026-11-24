"""工作區編輯區（ADR-038 D2／D3）的請求與回應形狀。"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ddm_v2.schemas.v2.most import CycleIn
from ddm_v2.schemas.v2.worksheet import DistanceStatus

DraftSource = Literal["manual", "ai_service", "rule_based", "imported"]
DraftStatus = Literal["pending", "confirmed", "committed"]
StaleReason = Literal["rule_set_changed", "import_row_changed"]
Hand = Literal["LH", "RH", "BH"]

MAX_DRAFTS_PER_REQUEST = 200
# 一列草稿內容序列化後的上限：CycleIn 的子物件（m_components、p_addon_codes、modifiers…）本身沒有長度上限，
# 草稿又會持久化、在寫入時再算一次，所以在入口擋住超大內容
MAX_CONTENT_BYTES = 16_384


def _non_finite_path(value: Any, path: str = "") -> str | None:
    """回傳第一個 NaN／±Inf 的位置；都有限則 None。JSONB 存不下非有限數，引擎拿到也會算出 nan TMU。"""
    if isinstance(value, float) and not math.isfinite(value):
        return path or "."
    if isinstance(value, dict):
        for k, v in value.items():
            hit = _non_finite_path(v, f"{path}.{k}" if path else str(k))
            if hit:
                return hit
    if isinstance(value, list):
        for i, v in enumerate(value):
            hit = _non_finite_path(v, f"{path}[{i}]")
            if hit:
                return hit
    return None


class WiDraftContent(BaseModel):
    """一列草稿的內容：同 `WiRowSaveIn`，去掉 id／seq_no（寫入時才決定）與 level（寫入時留空，ADR-037 D5）。"""

    model_config = ConfigDict(extra="forbid")

    sub_activity: str | None = Field(default=None, max_length=500)
    key_parts: str | None = Field(default=None, max_length=500)
    hand: Hand | None = None
    object_vocab_id: uuid.UUID | None = None
    from_vocab_id: uuid.UUID | None = None
    to_vocab_id: uuid.UUID | None = None
    tool_vocab_id: uuid.UUID | None = None
    frequency: float = Field(default=1, gt=0, le=10_000)
    wi_group: str | None = Field(default=None, max_length=200)
    narrative: str | None = Field(default=None, max_length=2000)
    distance_status: DistanceStatus | None = None  # ADR-038 D6；寫入時帶到工時表
    cycle: CycleIn

    @field_validator("wi_group", mode="before")
    @classmethod
    def _norm_wi_group(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @model_validator(mode="after")
    def _bounded_and_finite(self) -> WiDraftContent:
        dumped = self.model_dump(mode="python")
        bad = _non_finite_path(dumped)
        if bad:
            raise ValueError(f"non-finite number at {bad}")
        if len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False)) > MAX_CONTENT_BYTES:
            raise ValueError(f"draft content exceeds {MAX_CONTENT_BYTES} bytes")
        return self


class WiDraftCreateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: WiDraftContent
    # 同一句拆出的 motion 共用；沒給就自成一組
    group_key: str | None = Field(default=None, min_length=1, max_length=200)
    order_in_group: int = Field(default=0, ge=0, le=10_000)


class WiDraftCreateIn(BaseModel):
    """手動新增草稿列（ADR-038 D2：手動列也進編輯區）。AI／匯入的草稿由後端產生（W3），不經此端點。"""

    model_config = ConfigDict(extra="forbid")

    items: list[WiDraftCreateItem] = Field(min_length=1, max_length=MAX_DRAFTS_PER_REQUEST)


class WiDraftPatchIn(BaseModel):
    """修改一列；改了內容就回到 pending（要重新確認）。"""

    model_config = ConfigDict(extra="forbid")

    content: WiDraftContent


class WiDraftConfirmIn(BaseModel):
    """確認一些列或一整組。`draft_ids` 與 `group_key` 擇一。"""

    model_config = ConfigDict(extra="forbid")

    draft_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=MAX_DRAFTS_PER_REQUEST)
    group_key: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _exactly_one(self) -> WiDraftConfirmIn:
        if (self.draft_ids is None) == (self.group_key is None):
            raise ValueError("exactly one of draft_ids or group_key is required")
        return self


class WiDraftCommitIn(BaseModel):
    """寫入工時表：把所有已確認的列追加到表尾。必帶 `base_revision`（樂觀鎖，ADR-027 §2）。"""

    model_config = ConfigDict(extra="forbid")

    base_revision: int = Field(ge=1)


class WiDraftOut(BaseModel):
    id: uuid.UUID
    worksheet_id: uuid.UUID
    group_key: str
    order_in_group: int
    sort_order: int
    source: DraftSource
    status: DraftStatus
    content: dict[str, Any]
    ai_candidates: dict[str, Any] | None = None
    ai_parse_run_id: uuid.UUID | None = None
    import_row_id: uuid.UUID | None = None
    source_revision: int | None = None
    created_by: str
    created_at: datetime
    updated_by: str | None = None
    updated_at: datetime
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    committed_by: str | None = None
    committed_at: datetime | None = None
    committed_wi_row_id: uuid.UUID | None = None
    # W3（v2_0053）
    source_rule_set_id: uuid.UUID | None = None
    parse_snapshot: dict[str, Any] | None = None  # 解析當下的 complete／issues 等；人工草稿為 null
    stale_reason: StaleReason | None = None


class WiDraftListOut(BaseModel):
    worksheet_id: uuid.UUID
    items: list[WiDraftOut]


class WiDraftCommitOut(BaseModel):
    worksheet_id: uuid.UUID
    revision_no: int
    committed: list[WiDraftOut]


class WiDraftFromSentenceIn(BaseModel):
    """單句解析後寫進編輯區（ADR-038 D2 情境 2）。規則版本取工時表的，不由前端指定。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    # MOST 已知的手別（使用者輸入）；給了才和 ai_service 的手別提示比對，不採信 ai_service 的值
    hand: Hand | None = None
    # 作業名稱；沒給就用原句（ADR-037 D5：Excel 欄 → 使用者輸入 → 原句）
    wi_group: str | None = Field(default=None, max_length=200)


class WiDraftDegradeReason(BaseModel):
    """AI 為什麼沒有結果（`status=degraded` 時）。只含 MOST 的分類代碼；維運細節（設定、金鑰）只在 run 與 log。

    `error_kind` 是 `AiServiceErrorKind` 的值，或 MOST 端的 `misconfigured`／`internal_error`／`empty_result`／
    `unknown`；前端依它顯示 zh-TW／en 文案，不認得的顯示通用說明。這不是錯誤回應（請求本身成功），所以不走
    ADR-034 錯誤信封碼。
    """

    error_kind: str
    upstream_code: str | None = None


class WiDraftParseInfo(BaseModel):
    run_id: uuid.UUID | None = None
    status: Literal["ai_service", "degraded", "rule_based"]
    reason: WiDraftDegradeReason | None = None
    routing_status: str
    routing_reasons: list[str]


class WiDraftFromSentenceOut(BaseModel):
    worksheet_id: uuid.UUID
    group_key: str
    items: list[WiDraftOut]
    ai: WiDraftParseInfo


class WiDraftBlankFromImportIn(BaseModel):
    """沒有產生草稿的 Excel 列 → 空白草稿（ADR-038 W5）。"""

    model_config = ConfigDict(extra="forbid")

    import_row_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_DRAFTS_PER_REQUEST)
