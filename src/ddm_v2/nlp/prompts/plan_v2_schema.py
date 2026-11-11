"""**索取** schema：實際餵給模型的 `response_format` / system schema（ADR-033 P2）。

## 為什麼要有第二份模型，而不是直接用 `contracts.PlannerOutput`

`llm_planner` 把 `model_json_schema()` 同時送進 `response_format={"type":"json_schema"}`
與（`json_object`／`none` 模式下）附進 system message（`llm_client.py`）。也就是說
**送出去的 schema 就是一份公告**：欄位出現在裡面，等於告訴模型「這裡可以放東西」。

P2 之前送的是 `PlannerOutput.model_json_schema()`，於是：

- `RoleValue` 對模型公告了 `value`／`unit`／`status`／`action_ref`——正是 ADR-033
  **D1**（不產任何數值）與 **D3**（廢止 `status` 作為索取欄位）要停止索取的東西；
- `EvidenceSpan` 公告了 `start`／`end`——正是 **D4** 要停止索取的東西。

**prompt 說「別輸出」而 schema 說「這裡可以放」，模型會照 schema 走。**
只改 prompt 不改 schema，P2 等於沒做。

## 責任分界（與 `contracts.py` 的關係）

| | 這個檔 | `nlp/contracts.py` |
|---|---|---|
| 回答的問題 | **我們向模型索取什麼** | **我們願意接受什麼** |
| 版本軸 | `PROMPT_VERSION`（`plan-v2.0`），可隨 prompt 版本自由收窄 | `SCHEMA_VERSION`（`wi-plan-v1`），受 ADR-011 只增不改約束 |
| 落 DB／回 API | 否，只出現在對模型的請求裡 | 是（`ai_parse_runs.plan`、`/nl-draft` 回應） |

**解析端一律不動**：`PlannerOutput.model_validate` 維持寬鬆，模型若仍吐
`value`／`unit`／`status`／`start`／`end` 照樣收得下來，再由 adapter 邊界逐項剝除並記名
（D6 的逐項降級）。收窄的是**索取**，不是**容忍**——兩者同時收窄會讓既有
`ai_parse_runs.plan` 讀不回來，那是 ADR-011 明文禁止的破壞性變更。

守衛：`tests/unit/test_planner_request_schema.py`（兩個方向都要斷言——
「請求 schema 不公告」與「解析端仍接受」缺一邊就是只驗了一半）。

## ⚠️ 本檔的類別**刻意不寫 docstring**

pydantic 會把類別 docstring 原樣放進 JSON Schema 的 `description`，而這份 schema
**會被送給模型**。在 `RequestedRoleValue` 的 docstring 裡寫「沒有 value／unit／status」
等於在公告面上重新提起那三個字——與收窄的目的相反（同 prompt 側不點名
`hand`／`distance`／`quantity` 的理由：提到一個欄位，模型就會去填它）。
所以說明一律寫成 `#` 註解，留在原始碼裡、不進 schema。
守衛：`test_request_schema_carries_no_prose_that_names_unasked_fields`。

## ⚠️ `RequestedDependencyType` 為什麼不在 `_contract_freeze_v1` 的凍結表裡

它**不是對外列舉**：不落 DB、不回 API、沒有既存列帶著它，收窄它不會讓任何東西讀不回來。
它是「這一版 prompt 索取哪幾個 type」的宣告，本來就該隨 prompt 版本變動
（D5 讓 `precedes` 退出索取，就是靠這裡少列一個值）。落 DB 的那份是
`contracts.DependencyType`，四個值一個都沒少，凍結表守的是它。
`test_planner_request_schema` 另有斷言釘住「索取集合必須是契約集合的子集」——
索取一個契約收不下的值，才是真的錯。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ddm_v2.nlp.contracts import ActionType

# ADR-033 D5：`precedes` 零消費者、不再索取。契約端 `DependencyType` 仍有四個值
# （既存 plan JSON 帶著它），這裡只是不向模型要。
RequestedDependencyType = Literal["uses_tool", "tool_held_for", "same_object"]


# 角色片語：只有 `text`（ADR-033 D1／D2／D3）。
#
# `action_ref` 為什麼還在：`tool_ref` 需要它指出「用的是前面哪一個 acquire 拿到的
# 工具」（`policies.is_tool_held` → G 格留空＝0 TMU，是真實的 TMU 效果）。而 `roles`
# 在 JSON Schema 裡是 `additionalProperties`（鍵名可變），**沒辦法只對 `tool_ref`
# 這一個鍵宣告額外欄位**——所以 `action_ref` 只能整片公告，由 prompt 規則 7 限定
# 「只有 tool_ref 用得上」。教材面的守衛見
# `test_few_shots_use_action_ref_only_on_tool_ref`。
#
# 不在這裡的欄位（刻意，見模組 docstring 的兩個 ⚠️）：距離／數量／秒數的數值欄位
# （D1，另有來源），以及模型自我宣告的憑據欄位（D3，改由「text 是原文字面子字串」
# 這個可機械驗證的事實取代）。
class RequestedRoleValue(BaseModel):
    text: str | None = None
    action_ref: str | None = None


# 證據片語：只有 `text`（ADR-033 D4）。
#
# 模型不報字元座標——worklog §8 量到 `evidence_offset_repaired` 在 plan-v1.3 兩輪各
# 觸發 62／63 次（55 案），幾乎每一份輸出都要修。座標由
# `contracts.locate_evidence_spans` 推導。
class RequestedEvidence(BaseModel):
    text: str


# 與 `contracts.PlannedAction` 的差別只有一項：沒有 `notes`（零消費者、從未索取）。
class RequestedAction(BaseModel):
    action_id: str
    action_type: ActionType
    sequence_order: int
    roles: dict[str, RequestedRoleValue] = Field(default_factory=dict)
    evidence: list[RequestedEvidence] = Field(default_factory=list)


class RequestedDependency(BaseModel):
    from_action: str
    to_action: str
    type: RequestedDependencyType


# `model_json_schema()` 的來源——**這份形狀就是我們對模型的公告**。
#
# 刻意與 `PlannerOutput` 同名同層（`language`／`actions`／`dependencies`／`unresolved`），
# 差別只在**每個欄位少了什麼**：模型輸出的 JSON 照樣能被 `PlannerOutput.model_validate`
# 收下，不需要任何欄位改名或轉換。
class PlannerRequest(BaseModel):
    language: Literal["zh", "en", "mixed"]
    actions: list[RequestedAction]
    dependencies: list[RequestedDependency] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


def request_json_schema() -> dict:
    """送給模型的 JSON Schema（每次呼叫重新產生一份，不共用可變 dict）。

    ⚠️ 本函式的 docstring 不會進 schema（只有**類別** docstring 會），所以這裡可以
    正常說明。`plan_v1.REQUEST_JSON_SCHEMA` 在 import 時呼叫一次並持有結果；那份是
    唯讀慣例（與 `SYSTEM_PROMPT`／`FEW_SHOTS` 同級的常數），呼叫端不得就地修改。
    需要一份可以改的拷貝時，重新呼叫本函式。
    """
    return PlannerRequest.model_json_schema()
