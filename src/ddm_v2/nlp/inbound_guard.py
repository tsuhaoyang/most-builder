"""入站防腐層：把外部 planner 的原始 JSON 解析、剝除、驗證成 `PlannerOutput`。

由舊 `nlp/llm_planner.py` 搬來（ADR-037 D1：MOST 內的 LLM 呼叫移除，但防腐邏輯保留，
供 ai_service 回應進 MOST 前使用）。

ADR-033 D6（spec §7.5.1）：**嚴格屬於契約，寬容屬於邊界**。本檔就是那個邊界——剝未知鍵、
剝數值、丟壞 dependency、算 evidence offset 一律逐項記名，**不讓整份語意正確的切分被丟掉**。
整筆失敗只剩三種：JSON／schema 解析失敗、`actions` 全空、`sequence_order` 不連續。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ddm_v2.nlp.contracts import (
    PlannerOutput,
    StripDetail,
    prepare_planner_payload,
    sanitize_planner_output,
    validate_planner_output,
)

# (phase, reasons, details)。
#
# `details` 與 `reasons` 是**兩條分開的路**，不可合併：reasons 的代碼前綴會經
# `plan.unresolved` 落 DB 並回 API，所以裡面**不放外部可控字串**；`details` 帶的正是
# 那些字串（被剝掉的 role text／evidence 片語），只給評測報告訂閱。
# ⚠️ 這**不代表** `plan.unresolved` 是乾淨的——`PlannerOutput.unresolved` 本身就是
# 外部可控的 `list[str]` 且被逐字沿用（既有 S-5，未修）。更正與理由見
# `contracts.StripDetail` 的 docstring。生產路徑不得訂閱（守衛：
# `tests/unit/test_production_no_sanitize_observer.py`）。
SanitizeObserver = Callable[[str, list[str], list["StripDetail"]], None]


def sequence_orders_contiguous(output: PlannerOutput) -> bool:
    orders = [a.sequence_order for a in output.actions]
    return orders == list(range(1, len(orders) + 1))


def parse_sanitize_validate(
    content: str, normalized_text: str
) -> tuple[PlannerOutput | None, list[str], list[str], list[StripDetail]]:
    """回傳 (output|None, fatal_errors, sanitize_reasons, strip_details)。

    `fatal_errors` 非空＝整筆作廢。ADR-033 D6 之後**只有三種情形**會走到這裡：

    1. `json_or_schema`：JSON 解不開，或 pydantic 拒收（`prepare_planner_payload`
       之後仍過不了——例如 `action_type` 不在列舉、`roles` 不是物件）。
    2. `actions_empty` / `all_actions_sanitized_away`：一個 action 都不剩。
       前者是來源直接回空，後者是全部被語意防線剔除（幻覺／無 evidence）。
    3. `sequence_order_not_contiguous`：對**原始輸出**判——sanitize 會重新
       編號，判在它之後就永遠是綠的，等於這條規則失效。

    其餘一切（未知角色鍵、數值、壞 dependency、算錯的 offset、原文裡找不到的
    片語）在 `prepare_planner_payload`／`sanitize_planner_output` 逐項剝除並記名，
    reason 經 `unresolved` 進 routing 擋 auto。

    最後那次 `validate_planner_output` 是**防禦性斷言**：sanitize 之後結構應該
    已經自洽，還有殘留錯誤代表 sanitize 有漏（不是來源的問題），fail-closed。

    sanitize_reasons 一律回傳（含 JSON 解析就失敗的空 list），讓觀測端可以把
    「這次呼叫剝了什麼」與「這次呼叫的成敗」對起來看。

    strip_details 是**被剝掉的值本身**（`StripDetail`，外部可控字串），與 reasons
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
    if not sequence_orders_contiguous(output):
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
