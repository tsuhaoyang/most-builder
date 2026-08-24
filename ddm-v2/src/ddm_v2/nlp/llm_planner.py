"""LLMPlannerAdapter：structured plan + 一次 schema retry；失敗拋 PlannerError。

ADR-033 D6（spec §7.5.1）：**嚴格屬於契約，寬容屬於 adapter 邊界**。本檔就是那個
邊界——剝未知鍵、剝數值、丟壞 dependency、算 evidence offset 一律逐項記名，
**不讓整份語意正確的切分被丟掉**。整筆失敗（→ retry → `PlannerError` → rule
fallback）只剩三種：JSON／schema 解析失敗、`actions` 全空、`sequence_order` 不連續。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ddm_v2.nlp.contracts import (
    ParseContext,
    PlannerOutput,
    StripDetail,
    prepare_planner_payload,
    sanitize_planner_output,
    validate_planner_output,
)
from ddm_v2.nlp.planner_ports import LLMClientPort, LLMRawResponse, PlannerError
from ddm_v2.nlp.prompts import plan_v1

# (phase, reasons, details) — phase ∈ {"initial", "retry"}；見 LLMPlannerAdapter.__init__
#
# `details` 與 `reasons` 是**兩條分開的路**，不可合併：reasons 的代碼前綴會經
# `plan.unresolved` 落 DB 並回 API，所以裡面**不放模型可控字串**；`details` 帶的正是
# 那些字串（被剝掉的 role text／evidence 片語），只給訂閱者（評測報告）。
# ⚠️ 這**不代表** `plan.unresolved` 是乾淨的——`PlannerOutput.unresolved` 本身就是
# 模型可控的 `list[str]` 且被逐字沿用（既有 S-5，未修）。分開只是不再多開一條路，
# 更正與理由見 `contracts.StripDetail` 的 docstring。
SanitizeObserver = Callable[[str, list[str], list["StripDetail"]], None]


class LLMPlannerAdapter:
    def __init__(
        self,
        client: LLMClientPort,
        *,
        timeout_s: float = 8.0,
        on_sanitize: SanitizeObserver | None = None,
    ) -> None:
        """`on_sanitize`：把 sanitize 的 reasons **與被剝掉的值**送給觀測端。

        reasons 原本被丟棄，於是「模型多常數錯 evidence offset」這件事沒有任何
        地方量得到（成功的案例連 PlannerError.errors 都沒有）。用 callback 而非
        改 `plan()` 的回傳型別，是因為 `PlanParserPort.plan` 的
        `(PlannerOutput, LLMRawResponse | None)` 是 wi_ai_service 也吃的契約；
        觀測需求不該去動它。預設 None＝完全不影響既有呼叫端。

        第三個參數 `details`（`StripDetail`）是 ADR-033 P1 觀察期補的：契約放寬後
        「有問題的輸出」變成降級而非硬失敗，而 `planner_raw_rejected` **只在硬失敗時
        留存**——於是最有意思的案例反而什麼都沒留下，「模型幻覺」與「不變式過嚴」
        分不開（T-16）。details 帶的是**模型可控字串**，因此**只走這條 callback**，
        絕不進 reasons／`unresolved`／`routing_reasons`（那條路會落 DB 並回 API；
        ⚠️ 那條路本身不乾淨，更正見 `contracts.StripDetail`）。

        ⚠️ 措辭要準：生產路徑（`wi_ai_service`）不掛 observer 時，明細**照樣被收集**
        （`_parse_sanitize_validate` 一律建 `details` 並傳進 sanitize），被擋掉的是
        **發送**——`_observe` 在 `_on_sanitize is None` 時 no-op，那些值隨該次呼叫的
        區域變數一起丟棄，不會離開這個函式。實害接近零，但「不收集」與「不發送」
        是兩件事，寫錯會讓人以為有一道不存在的閘門。
        """
        self._client = client
        self._timeout_s = timeout_s
        self._on_sanitize = on_sanitize

    def _observe(self, phase: str, reasons: list[str], details: list[StripDetail]) -> None:
        if self._on_sanitize is not None:
            self._on_sanitize(phase, reasons, details)

    async def plan(
        self, normalized_text: str, context: ParseContext
    ) -> tuple[PlannerOutput, LLMRawResponse]:
        # ADR-033 P2：送出去的是**索取** schema（`plan_v2_schema.PlannerRequest`），
        # 不是解析端契約（`PlannerOutput`）。schema 與 prompt 是兩個公告面——
        # 舊版送 `PlannerOutput.model_json_schema()`，等於一邊用規則說「別輸出
        # status／數值／字元位置」、一邊用 schema 公告那些欄位可以放東西，而模型會
        # 照 schema 走。解析端**維持寬鬆不動**（D6 的逐項降級）。
        schema = plan_v1.REQUEST_JSON_SCHEMA
        user = plan_v1.build_user_message(normalized_text, context.model_dump())
        raw = await self._client.structured_completion(
            system=plan_v1.SYSTEM_PROMPT,
            user=user,
            json_schema=schema,
            temperature=0.0,
            timeout_s=self._timeout_s,
            few_shots=plan_v1.FEW_SHOTS,
        )
        output, errors, reasons, details = _parse_sanitize_validate(raw.content, normalized_text)
        self._observe("initial", reasons, details)
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
        output2, errors2, reasons2, details2 = _parse_sanitize_validate(raw2.content, normalized_text)
        self._observe("retry", reasons2, details2)
        if errors2 or output2 is None:
            raise PlannerError(
                f"planner_schema_invalid:{errors2}",
                raw=raw2,
                errors=errors2,
            )
        return output2, raw2


def _sequence_orders_contiguous(output: PlannerOutput) -> bool:
    orders = [a.sequence_order for a in output.actions]
    return orders == list(range(1, len(orders) + 1))


def _parse_sanitize_validate(
    content: str, normalized_text: str
) -> tuple[PlannerOutput | None, list[str], list[str], list[StripDetail]]:
    """回傳 (output|None, fatal_errors, sanitize_reasons, strip_details)。

    `fatal_errors` 非空＝整筆作廢（retry 一次，仍錯就 `PlannerError` → rule
    fallback）。ADR-033 D6 之後**只有三種情形**會走到這裡：

    1. `json_or_schema`：JSON 解不開，或 pydantic 拒收（`prepare_planner_payload`
       之後仍過不了——例如 `action_type` 不在列舉、`roles` 不是物件）。
    2. `actions_empty` / `all_actions_sanitized_away`：一個 action 都不剩。
       前者是模型直接回空，後者是全部被語意防線剔除（幻覺／無 evidence）。
    3. `sequence_order_not_contiguous`：對**模型原始輸出**判——sanitize 會重新
       編號，判在它之後就永遠是綠的，等於這條規則失效。

    其餘一切（未知角色鍵、數值、壞 dependency、算錯的 offset、原文裡找不到的
    片語）在 `prepare_planner_payload`／`sanitize_planner_output` 逐項剝除並記名，
    reason 經 `unresolved` 進 routing 擋 auto。

    最後那次 `validate_planner_output` 是**防禦性斷言**：sanitize 之後結構應該
    已經自洽，還有殘留錯誤代表 sanitize 有漏（不是模型的問題），fail-closed。

    sanitize_reasons 一律回傳（含 JSON 解析就失敗的空 list），讓觀測端可以把
    「這次呼叫剝了什麼」與「這次呼叫的成敗」對起來看。

    strip_details 是**被剝掉的值本身**（`StripDetail`，模型可控字串），與 reasons
    分開回傳並只交給 observer——理由見 `SanitizeObserver` 的註解。**失敗路徑也照樣
    回傳已收集到的部分**：降級與硬失敗都可能有東西被剝掉，只在成功時給等於挑好看的
    樣本回報。
    """
    details: list[StripDetail] = []
    try:
        data: Any = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        return None, [f"json_or_schema:{exc}"], [], details
    payload, prep_reasons = prepare_planner_payload(data)
    try:
        output = PlannerOutput.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        return None, [f"json_or_schema:{exc}"], prep_reasons, details
    if not output.actions:
        return None, ["actions_empty"], prep_reasons, details
    if not _sequence_orders_contiguous(output):
        return None, ["sequence_order_not_contiguous"], prep_reasons, details
    sanitized, reasons = sanitize_planner_output(
        output,
        normalized_text=normalized_text,
        carried_reasons=prep_reasons,
        details=details,
    )
    if not sanitized.actions:
        return None, ["all_actions_sanitized_away"], reasons, details
    residual = validate_planner_output(sanitized, normalized_text=normalized_text)
    if residual:
        return None, residual, reasons, details
    return sanitized, [], reasons, details
