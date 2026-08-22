"""LLMPlannerAdapter：structured plan + 一次 schema retry；失敗拋 PlannerError。"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ddm_v2.nlp.contracts import ParseContext, PlannerOutput, sanitize_planner_output, validate_planner_output
from ddm_v2.nlp.planner_ports import LLMClientPort, LLMRawResponse, PlannerError
from ddm_v2.nlp.prompts import plan_v1

# (phase, reasons) — phase ∈ {"initial", "retry"}；見 LLMPlannerAdapter.__init__
SanitizeObserver = Callable[[str, list[str]], None]


class LLMPlannerAdapter:
    def __init__(
        self,
        client: LLMClientPort,
        *,
        timeout_s: float = 8.0,
        on_sanitize: SanitizeObserver | None = None,
    ) -> None:
        """`on_sanitize`：把 `sanitize_planner_output` 的 reasons 送給觀測端。

        reasons 原本被丟棄，於是「模型多常數錯 evidence offset」這件事沒有任何
        地方量得到（成功的案例連 PlannerError.errors 都沒有）。用 callback 而非
        改 `plan()` 的回傳型別，是因為 `PlanParserPort.plan` 的
        `(PlannerOutput, LLMRawResponse | None)` 是 wi_ai_service 也吃的契約；
        觀測需求不該去動它。預設 None＝完全不影響既有呼叫端。
        """
        self._client = client
        self._timeout_s = timeout_s
        self._on_sanitize = on_sanitize

    def _observe(self, phase: str, reasons: list[str]) -> None:
        if self._on_sanitize is not None:
            self._on_sanitize(phase, reasons)

    async def plan(
        self, normalized_text: str, context: ParseContext
    ) -> tuple[PlannerOutput, LLMRawResponse]:
        schema = PlannerOutput.model_json_schema()
        user = plan_v1.build_user_message(normalized_text, context.model_dump())
        raw = await self._client.structured_completion(
            system=plan_v1.SYSTEM_PROMPT,
            user=user,
            json_schema=schema,
            temperature=0.0,
            timeout_s=self._timeout_s,
            few_shots=plan_v1.FEW_SHOTS,
        )
        output, errors, reasons = _parse_sanitize_validate(raw.content, normalized_text)
        self._observe("initial", reasons)
        if not errors and output is not None:
            return output, raw

        retry_user = (
            user
            + "\n\n# Validation errors from previous attempt\n"
            + json.dumps(errors, ensure_ascii=False)
            + "\nPlease output corrected JSON only."
        )
        raw2 = await self._client.structured_completion(
            system=plan_v1.SYSTEM_PROMPT,
            user=retry_user,
            json_schema=schema,
            temperature=0.0,
            timeout_s=self._timeout_s,
            few_shots=plan_v1.FEW_SHOTS,
        )
        output2, errors2, reasons2 = _parse_sanitize_validate(raw2.content, normalized_text)
        self._observe("retry", reasons2)
        if errors2 or output2 is None:
            raise PlannerError(
                f"planner_schema_invalid:{errors2}",
                raw=raw2,
                errors=errors2,
            )
        return output2, raw2


def _parse_sanitize_validate(
    content: str, normalized_text: str
) -> tuple[PlannerOutput | None, list[str], list[str]]:
    """回傳 (output|None, validate_errors, sanitize_reasons)。

    sanitize_reasons 一律回傳（含 JSON 解析就失敗的空 list），讓觀測端可以把
    「這次呼叫修了幾個 offset」與「這次呼叫的成敗」對起來看。
    """
    try:
        data: Any = json.loads(content)
        output = PlannerOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        return None, [f"json_or_schema:{exc}"], []
    sanitized, reasons = sanitize_planner_output(output, normalized_text=normalized_text)
    errs = validate_planner_output(sanitized, normalized_text=normalized_text)
    if errs:
        return None, errs, reasons
    if not sanitized.actions and output.actions:
        # 全部被剔除 → 結構上視為失敗，觸發 retry/fallback
        return None, ["all_actions_sanitized_away"], reasons
    return sanitized, [], reasons
