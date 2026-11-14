"""WI AI planner ports。

ADR-037（2026-11-14）：MOST 內的 LLM client port（舊的 LLM client protocol）已移除；LLM 呼叫歸 ai_service。
外部 planner 的接入點改由 ADR-037 D2 的 `WiParserPort` 承接（實作計畫 S2）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ddm_v2.nlp.contracts import ParseContext, PlannerOutput


@dataclass(frozen=True)
class PlannerRawResponse:
    """外部 planner 的原始回應（評測留痕與失敗回報用）。

    舊名 `LLMRawResponse`；`ai_parse_runs.llm_raw_response` 的既有欄位形狀
    （content／model／usage／response_format_mode／prompt_version）不變，舊列照樣讀得回。
    """

    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    response_format_mode: str = "json_object"


class PlanParserPort(Protocol):
    async def plan(
        self, normalized_text: str, context: ParseContext
    ) -> tuple[PlannerOutput, PlannerRawResponse | None]: ...


class PlannerError(Exception):
    """planner／schema 失敗，呼叫端應 fallback。

    `errors` 帶 `validate_planner_output()` 的具名錯誤（例 ``evidence_offset_oor:a2``），
    讓評測端不必字串剖析訊息就能統計失敗形態（`planner_eval._planner_error_codes`）。
    """

    def __init__(
        self,
        message: str,
        *,
        raw: PlannerRawResponse | None = None,
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw = raw
        self.errors = list(errors or [])
