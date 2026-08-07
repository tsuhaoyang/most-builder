"""LLMPlannerAdapter：structured plan + 一次 schema retry；失敗拋 PlannerError。"""
from __future__ import annotations

import json
from typing import Any

from ddm_v2.nlp.contracts import ParseContext, PlannerOutput, sanitize_planner_output, validate_planner_output
from ddm_v2.nlp.planner_ports import LLMClientPort, LLMRawResponse, PlannerError
from ddm_v2.nlp.prompts import plan_v1


class LLMPlannerAdapter:
    def __init__(self, client: LLMClientPort, *, timeout_s: float = 8.0) -> None:
        self._client = client
        self._timeout_s = timeout_s

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
        output, errors = _parse_sanitize_validate(raw.content, normalized_text)
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
        output2, errors2 = _parse_sanitize_validate(raw2.content, normalized_text)
        if errors2 or output2 is None:
            raise PlannerError(
                f"planner_schema_invalid:{errors2}",
                raw=raw2,
            )
        return output2, raw2


def _parse_sanitize_validate(
    content: str, normalized_text: str
) -> tuple[PlannerOutput | None, list[str]]:
    try:
        data: Any = json.loads(content)
        output = PlannerOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        return None, [f"json_or_schema:{exc}"]
    sanitized, _reasons = sanitize_planner_output(output)
    errs = validate_planner_output(sanitized, normalized_text=normalized_text)
    if errs:
        return None, errs
    if not sanitized.actions and output.actions:
        # 全部被剔除 → 結構上視為失敗，觸發 retry/fallback
        return None, ["all_actions_sanitized_away"]
    return sanitized, []
