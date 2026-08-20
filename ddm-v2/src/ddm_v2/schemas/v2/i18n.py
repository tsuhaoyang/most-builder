"""i18n 覆核狀態 API 契約（ADR-032 D6）。

`I18nReviewSummaryOut` 供頁首顯示「英文覆核 n/總數」，`I18nReviewItemOut` 供覆核頁面
列表與 mutation 的回應（同一個形狀，讓「標記完成後這一列變成什麼」可以直接就地替換，
前端不需要兩套映射）。`I18nPendingItemOut` 是它在待審清單裡的收窄版：清單只回
`status` 非空的列，故該欄位的型別在那裡是三態 Literal 而不是可空。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ddm_v2.schemas.v2.rule_set_options import MAX_EN_LABEL_LEN, MAX_EN_SENTENCE_LEN

EntityType = Literal["rule_option", "vocab_item", "motion_template"]
FieldName = Literal["label", "sentence", "name"]
PendingStatus = Literal["never_translated", "unreviewed", "stale"]
ReviewSource = Literal["machine", "human", "legacy_seed", "untranslated"]


class I18nReviewSummaryOut(BaseModel):
    """`{total, reviewed, pending}`——`entity_type` 未指定時為全體（rule_option ＋
    vocab_item ＋ motion_template）合計；指定時為該類別單獨的統計。
    """

    total: int
    reviewed: int
    pending: int


class I18nReviewItemOut(BaseModel):
    """一個可譯欄位的現況。`status is None` ＝已覆核且未過期（不在待審清單裡）。"""

    entity_type: EntityType
    scope_key: str
    field: str
    status: PendingStatus | None
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
    target_changed: bool = Field(
        default=False,
        description=(
            "英文譯文在覆核之後被改過（`target_sha256` 比對，v2_0043）。與 "
            "`source_changed` 正交：兩者都會讓 `status` 變成 `stale`，但「中文改了、"
            "譯文要跟上」與「有人動了譯文、要重新確認」對覆核者是兩件事。從未覆核過"
            "（`target_sha256` 為 NULL）一律 `false`——沒有基準可比較。"
        ),
    )
    source_is_fallback: bool = Field(
        default=False,
        description=(
            "`source_zh` 是回退來的、不是這一列自己的中文——只有 `field='sentence'` 且"
            "中文句面（`sentence_text_zh`）為空時為真（那時 `source_zh` 顯示的是標籤）。"
            "用途是讓前端能事前分辨「英文句面留空」屬於 D7.6「刻意不入句」（合法，"
            "active 版共 7 條）還是把有中文的句子標成沒英文（會被 422 "
            "`I18N_REVIEW_TARGET_MISSING` 擋下）。**不可用「`source_zh` 等於標籤」反推**"
            "——句面剛好等於標籤時那會誤判；這裡回的是服務層算的同一個布林。"
        ),
    )
    review_source: ReviewSource | None
    translated_by: str | None
    translated_at: datetime | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    assigned_to: str | None = None
    assigned_at: datetime | None = None


class I18nPendingItemOut(I18nReviewItemOut):
    """待審清單的一列——`status` 必為三態之一（清單依定義只回 `status` 非空的列）。"""

    status: PendingStatus


class _ReviewTargetIn(BaseModel):
    """mutation 端點共用的「指哪一列」欄位。

    `rule_set_code` 只對 `rule_option` 有意義：同一個 `scope_key` 可能同時存在於
    active 與多個 draft（D5 刻意讓 scope_key 不含 rule_set_id）。**未指定時以 active
    版為準**；若該 code 只存在於某個 draft，必須顯式帶上——服務層不會靜默改挑一個
    （`ReviewRowNotFound` → 404）。
    """

    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    scope_key: str = Field(min_length=1)
    field: FieldName
    rule_set_code: str | None = None


# `target_en` 的長度上限依 `field` 而定——同一個欄位承載三種目標
# （`label_en`／`sentence_text_en`／`name_en`），值域必須與 `_en` 專用端點一致，
# 否則「覆核順手改譯文」會變成繞過 `OptionEnTextIn` 上限的旁門（2026-08-20 覆核修正）。
# `name` 取標籤的上限：與 `import_service` 對 vocab 名稱的既有處理（截到 200）同一個數。
_MAX_TARGET_EN_BY_FIELD: dict[str, int] = {
    "label": MAX_EN_LABEL_LEN,
    "sentence": MAX_EN_SENTENCE_LEN,
    "name": MAX_EN_LABEL_LEN,
}


class I18nMarkReviewedIn(_ReviewTargetIn):
    """標記已覆核；可選在同一個請求裡順手修正譯文（同交易）。

    `target_en=None` ＝不改譯文（沿用現有的 `_en`）。**把既有譯文清成空請走 `_en`
    專用寫入端點**（`PATCH /rule-sets/{code}/params/{param}/options/{code}/en`）——
    「覆核」與「把譯文清成空」是兩個相反的動作，不該共用一個請求。

    **唯一的例外是句面（`field='sentence'`）且該列中文句面本身為空**（D7.6「刻意
    不入句」，active 版 7 條）：那時空字串**就是**要覆核的那個值，`target_en=''`
    走這裡是對的。判準在 `_is_reviewable_target`（`_BLANK_OK_FIELDS` ＋ 該列的
    `source_is_fallback`），不是「只要是句面就放行」；`None` 對這種列代表「沿用現有
    的 NULL」→ 仍會被 `I18N_REVIEW_TARGET_MISSING` 擋下，所以前端必須顯式送 `''`。

    **`target_en` 一律 strip**（與 `schemas/v2/vocab.py` 的 `NameEn` 同一個語意，
    以及 `OptionEnTextIn` 的兩欄）：這條路徑會寫進 `name_en`／`label_en`／
    `sentence_text_en` 三種欄位，其中主數據那兩種先前是裸 `setattr`，實測同一個
    字串經覆核路徑存成 `'   Padded   '`、經 `PATCH /api/v2/vocab/{id}` 存成
    `'Padded'`——同一份資料兩個入口兩種結果。`vocab.py` 檔頭明講「字串一律 strip，
    在入口擋掉」，這條新入口補上。
    """

    target_en: Annotated[str, StringConstraints(strip_whitespace=True)] | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _cap_target_en_by_field(self) -> "I18nMarkReviewedIn":
        cap = _MAX_TARGET_EN_BY_FIELD[self.field]
        if self.target_en is not None and len(self.target_en) > cap:
            raise ValueError(f"target_en 超過 field={self.field} 的長度上限 {cap} 字元")
        return self


class I18nAssignIn(_ReviewTargetIn):
    """指派一條待審項給某人。`assigned_to=None`／空白 ＝取消指派。"""

    assigned_to: str | None = None
