"""i18n 覆核狀態 API 契約（ADR-032 D6）。

給下一輪前端用：`I18nReviewSummaryOut` 供頁首顯示「英文覆核 n/總數」，
`I18nPendingItemOut` 供覆核頁面列表（可指派、可標記完成——標記完成的
mutation 端點不在本輪範圍，本輪只保證讀取正確）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EntityType = Literal["rule_option", "vocab_item", "motion_template"]
PendingStatus = Literal["never_translated", "unreviewed", "stale"]
ReviewSource = Literal["machine", "human", "legacy_seed"]


class I18nReviewSummaryOut(BaseModel):
    """`{total, reviewed, pending}`——`entity_type` 未指定時為全體（rule_option ＋
    vocab_item ＋ motion_template）合計；指定時為該類別單獨的統計。
    """

    total: int
    reviewed: int
    pending: int


class I18nPendingItemOut(BaseModel):
    entity_type: EntityType
    scope_key: str
    field: str
    status: PendingStatus
    rule_set_code: str | None
    source_zh: str
    target_en: str | None
    source_changed: bool = Field(
        description=(
            "S6：現行中文來源是否已與這筆翻譯依據的來源不同（`review_sha256` 比對）。"
            "`status='unreviewed'` 本身無法區分「剛翻好、中文沒變過」與「翻過，但中文"
            "後來又改了、它還沒被人看過」——這個欄位把後者標出來，不影響 `status` 本身"
            "的分類（見 ADR-032 D6 補記）。"
        )
    )
    review_source: ReviewSource | None
    translated_by: str | None
    translated_at: datetime | None
    reviewed_by: str | None
    reviewed_at: datetime | None
