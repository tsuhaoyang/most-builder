"""WI AI Planner / LLM client ports。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ddm_v2.nlp.contracts import ParseContext, PlannerOutput


@dataclass(frozen=True)
class LLMRawResponse:
    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    response_format_mode: str = "json_object"


class LLMClientPort(Protocol):
    async def structured_completion(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        temperature: float,
        timeout_s: float,
        few_shots: list[tuple[str, str]] | None = None,
    ) -> LLMRawResponse: ...


class PlanParserPort(Protocol):
    async def plan(
        self, normalized_text: str, context: ParseContext
    ) -> tuple[PlannerOutput, LLMRawResponse | None]: ...


class PlannerError(Exception):
    """LLM/schema 失敗，呼叫端應 fallback。

    `errors` 帶 `validate_planner_output()` 的具名錯誤（例 ``evidence_offset_oor:a2``），
    讓評測端不必字串剖析訊息就能統計失敗形態（`planner_eval._planner_error_codes`）。
    """

    def __init__(
        self,
        message: str,
        *,
        raw: LLMRawResponse | None = None,
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw = raw
        self.errors = list(errors or [])
