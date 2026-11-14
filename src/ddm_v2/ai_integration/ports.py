"""`WiParserPort` 與輸入輸出型別（ADR-037 D2）。

port 的形狀刻意與 ai_service 的批量 flow 草案對齊（`items[]` 逐筆結果，ai_service ADR-011），
這樣 flow 落地後只換 adapter：第一個 adapter 逐句呼叫 `structured-completion`，下游不動。

## 輸出是「建議」，不是 plan

`MotionSuggestion` 只做了 allow-list 與上限檢查，**沒有**經過 MOST 的 link／compile／engine_gate，
也沒有 TMU。把它接進 `WorkInstructionPlan`（ADR-037 D3：code 放候選欄位、與 linker 結果比對）
是單句階段 S3 的工作，那時才會以加法擴充 `nlp/contracts`。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ddm_v2.ai_integration.errors import AiServiceErrorKind

SourceLang = Literal["zh", "en"]
Hand = Literal["LH", "RH", "BH"]
SeqKind = Literal["GM", "CM"]
AKind = Literal["reach", "foot", "twist", "return"]

# ADR-037 D7：外送只含 WI 語句與白名單內的 context。首輪白名單為空
# （`source_lang` 是獨立欄位，不放在 context 裡）；要加任何 context 欄位須修訂 ADR-037。
CONTEXT_WHITELIST: frozenset[str] = frozenset()

# allow-list 的鍵（與 `most_compiler.compile.allow_lists_from_rule_set` 同名）
AllowLists = Mapping[str, frozenset[str] | set[str]]


class WiParseRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str = Field(min_length=1, max_length=64)
    wi_statement: str = Field(min_length=1)
    source_lang: SourceLang
    context: dict[str, str] = Field(default_factory=dict)


class ASlotSuggestion(BaseModel):
    """A 位置：只有語意類別與**估計值提示**。估計值不得寫入 `role.value`（ADR-037 D3）。"""

    model_config = ConfigDict(frozen=True)

    kind: AKind
    magnitude_cm_hint: float | None = None
    magnitude_deg_hint: float | None = None


class PSlotSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    base: str | None
    addon: tuple[str, ...] = ()


class MotionSuggestion(BaseModel):
    """一個 motion 的建議。slot code 都已確認存在於目標 rule-set；不存在的已置 None 並記 issue。"""

    model_config = ConfigDict(frozen=True)

    index: int
    # 不採信（ADR-037 D3）：只作提示，MOST 另行判定
    hand_hint: Hand | None
    seq_kind_hint: SeqKind | None
    sub_activity: str
    object_text: str
    a0: ASlotSuggestion | None
    b1: str | None
    g2: str | None
    # GM 中段
    a3: ASlotSuggestion | None = None
    b4: str | None = None
    p5: PSlotSuggestion | None = None
    # CM 中段
    m3: str | None = None
    x4: str | None = None
    i5: str | None = None
    a6: ASlotSuggestion | None = None
    # ADR-037 D3／ADR-020：AI 不產生 SIMO；欄位存在只為了讓這件事可被斷言
    simo_group_id: None = None
    simo_with_row_id: None = None
    # 只含 MOST 自己的代碼（位置名、規則名），不含任何外部可控字串
    issues: tuple[str, ...] = ()


class WiParseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    status: Literal["ok", "failed"]
    motions: tuple[MotionSuggestion, ...] = ()
    issues: tuple[str, ...] = ()
    error_kind: AiServiceErrorKind | None = None
    # ai_service 的去敏 provenance（run_id、bundle、model、prompt_version）＋ MOST request id
    provenance: dict[str, str | int | float | None] | None = None


class WiParserPort(Protocol):
    async def parse(
        self,
        requests: Sequence[WiParseRequest],
        *,
        allow_lists: AllowLists,
        lane: Literal["interactive", "batch"],
    ) -> list[WiParseResult]:
        """逐筆回傳結果，順序與輸入相同。**不得因單筆失敗而拋例外**：失敗以
        `status="failed"`＋`error_kind` 表示，呼叫端據此降級到 rule_based（ADR-037 D2）。"""
        ...
