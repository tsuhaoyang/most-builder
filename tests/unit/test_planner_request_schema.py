"""**索取 schema** 的守衛（ADR-033 P2）：公告面與解析面必須分開，而且各守各的。

## 這支測試存在的理由

`llm_planner` 把 `model_json_schema()` 同時送進 `response_format={"type":"json_schema"}`
與（`json_object`／`none` 模式下）附進 system message。**送出去的 schema 就是一份公告**。

P2 之前送的是 `contracts.PlannerOutput.model_json_schema()`，於是 prompt 一邊用規則說
「別輸出 status／數值／字元位置」，schema 一邊公告 `value`／`unit`／`status`／`start`／
`end` 這幾個欄位可以放東西。**模型會照 schema 走**——只改 prompt 不改 schema，P2 等於沒做。

## 兩個方向都要驗，缺一邊就是只驗了一半

| 方向 | 斷言 | 少了它會怎樣 |
|---|---|---|
| **不索取** | 請求 schema 不得公告 `value`／`unit`／`status`／`start`／`end` | 收窄沒有真的發生，prompt 說了不算 |
| **仍接受** | `PlannerOutput.model_validate` 照樣收得下那些欄位 | 變成 ADR-011 禁止的破壞性收窄：既有 `ai_parse_runs.plan`／gold 讀不回來 |

第二個方向不是多餘的保險——**它是 D6「逐項降級」的前提**。模型仍會偶爾吐數值，
adapter 邊界要能收下來才剝得掉並記名（`role_numeric_stripped`）；解析端一起收窄的話，
那些輸出會在 pydantic 就整筆炸掉，回到 P1 之前「語意正確的切分被整份丟掉」的病。
"""
from __future__ import annotations

import json
import re
from typing import Any, get_args

import pytest

from ddm_v2.nlp.contracts import (
    DependencyType,
    EvidenceSpan,
    PlannedAction,
    PlannerOutput,
    RoleValue,
)
from ddm_v2.nlp.prompts import plan_v1
from ddm_v2.nlp.prompts.plan_v2_schema import (
    PlannerRequest,
    RequestedDependencyType,
    request_json_schema,
)

pytestmark = pytest.mark.unit


# ADR-033 D1（`value`／`unit`）、D3（`status`）、D4（`start`／`end`）：
# 這五個欄位名一律不得出現在**送給模型的** schema 裡。
_MUST_NOT_BE_ANNOUNCED = frozenset({"value", "unit", "status", "start", "end"})

# 反掏空：把 schema 換成 `{}` 或把模型欄位刪光，上面那條會恆綠（空集合沒有交集）。
# 這一組是「索取範圍不得憑空縮水」的下界——真的要拿掉任何一個，得先有 ADR 裁決。
_MUST_BE_ANNOUNCED = frozenset(
    {
        "language",
        "actions",
        "dependencies",
        "unresolved",
        "action_id",
        "action_type",
        "sequence_order",
        "roles",
        "evidence",
        "text",
        "action_ref",
        "from_action",
        "to_action",
        "type",
    }
)


def _property_names(node: Any) -> set[str]:
    """遞迴收集 JSON Schema 裡**真正的欄位名**（`properties` 的 key）。

    ⚠️ 刻意不對整份 schema 做子字串比對：`"dependencies"` 裡含有 `end`，
    naive 的 `"end" in json.dumps(schema)` 會假陽性，而修法會變成放寬判準。
    """
    found: set[str] = set()
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            found |= set(props.keys())
        for value in node.values():
            found |= _property_names(value)
    elif isinstance(node, list):
        for item in node:
            found |= _property_names(item)
    return found


def _strings(node: Any) -> list[str]:
    """schema 裡所有字串值（`description`／`title`／enum 值…）——散文洩漏的檢查面。"""
    out: list[str] = []
    if isinstance(node, dict):
        for value in node.values():
            out += _strings(value)
    elif isinstance(node, list):
        for item in node:
            out += _strings(item)
    elif isinstance(node, str):
        out.append(node)
    return out


# ── 方向一：請求 schema 不得公告收窄掉的欄位 ─────────────────────────────


def test_request_schema_does_not_announce_unasked_fields():
    """D1／D3／D4：`value`／`unit`／`status`／`start`／`end` 不得出現在索取 schema。"""
    announced = _property_names(request_json_schema())
    leaked = sorted(_MUST_NOT_BE_ANNOUNCED & announced)
    assert leaked == [], (
        f"索取 schema 公告了 ADR-033 收窄掉的欄位：{leaked}"
        "——prompt 說「別輸出」而 schema 說「這裡可以放」，模型會照 schema 走"
    )


def test_request_schema_still_announces_what_we_do_ask_for():
    """反掏空：schema 被清空時上一條會恆綠（空集合沒有交集），只有這條會紅。"""
    announced = _property_names(request_json_schema())
    missing = sorted(_MUST_BE_ANNOUNCED - announced)
    assert missing == [], f"索取 schema 少了該公告的欄位：{missing}"


def test_request_schema_carries_no_prose_that_names_unasked_fields():
    """pydantic 會把**類別 docstring** 放進 `description`，而這份 schema 會送給模型。

    在 `RequestedRoleValue` 的 docstring 裡寫「沒有 value／unit／status」等於在公告面
    重新提起那三個字——與收窄的目的相反（同 prompt 側不點名
    `hand`／`distance`／`quantity` 的理由）。實測踩過：第一版把理由寫成類別 docstring，
    schema 裡就出現了那五個詞。

    ⚠️ 這一條**只掃字串值**，所以它會連 `description` 與 enum 值一起看；
    欄位名那一層由 `test_request_schema_does_not_announce_unasked_fields` 守。

    ⚠️ 比對用 `\\b` 詞邊界而不是子字串：pydantic 自動產生的 title `"Dependencies"`
    含有 `end`，用 `in` 會假陽性，而修法會變成把 `end` 從清單裡拿掉——那等於為了
    讓測試變綠而放棄守 D4 的一半。
    """
    prose = " ".join(_strings(request_json_schema()))
    leaked = sorted(
        f
        for f in _MUST_NOT_BE_ANNOUNCED
        if re.search(rf"\b{re.escape(f)}\b", prose, re.IGNORECASE)
    )
    assert leaked == [], (
        f"索取 schema 的散文（description／title）提到了收窄掉的欄位：{leaked}"
        "——把說明改寫成 `#` 註解，別放在類別 docstring 裡"
    )


def test_requested_dependency_types_drop_precedes_only():
    """D5：索取三個 type，契約仍有四個。

    兩個方向都釘：索取集合必須是契約集合的**真子集**（少了 `precedes`），
    而且不得索取一個契約收不下的值——那才是真的錯。
    """
    requested = set(get_args(RequestedDependencyType))
    legal = set(get_args(DependencyType))
    assert requested <= legal, (
        f"索取了契約收不下的 dependency type：{sorted(requested - legal)}"
    )
    assert sorted(legal - requested) == ["precedes"], (
        f"索取與契約的差集不是只有 precedes：{sorted(legal - requested)}"
        "——D5 只把 precedes 移出索取；其它值要退出必須先有 ADR 裁決"
    )


# ── 方向二：解析端**維持寬鬆**（D6 的前提；ADR-011 的相容性） ─────────────


def test_parser_still_accepts_the_fields_we_stopped_asking_for():
    """模型仍吐 `value`／`unit`／`status`／`start`／`end` 時，解析端必須收得下來。

    收窄的是**索取**，不是**容忍**。兩者一起收窄的後果有兩層：
    ⑴ 既有 `ai_parse_runs.plan` 與 `tests/gold/wi_plans/*.json`（5 個帶 `status` 的
       role value）在 `model_validate` 就炸掉——ADR-011 明文禁止的破壞性變更；
    ⑵ D6 的逐項降級失效：收不下來就剝不掉，語意正確的切分會整份被丟回 rule parser。
    """
    payload = {
        "language": "zh",
        "actions": [
            {
                "action_id": "a1",
                "action_type": "controlled_move",
                "sequence_order": 1,
                "roles": {
                    "object": {"text": "治具", "status": "explicit"},
                    "distance": {"value": 45, "unit": "cm", "status": "explicit"},
                },
                "evidence": [{"start": 0, "end": 4, "text": "推動治具"}],
            }
        ],
        "dependencies": [],
        "unresolved": [],
    }
    output = PlannerOutput.model_validate(payload)
    role = output.actions[0].roles["distance"]
    assert (role.value, role.unit, role.status) == (45, "cm", "explicit")
    assert (output.actions[0].evidence[0].start, output.actions[0].evidence[0].end) == (0, 4)


def test_contract_models_still_declare_the_unasked_fields():
    """上一條驗「收得下來」，這條驗「欄位真的還在契約模型上」。

    差別很實際：pydantic 預設**忽略**未宣告的欄位，所以就算有人把 `RoleValue.value`
    刪掉，上一條的 `model_validate` 仍然不會炸——只會靜靜地把值丟掉，而
    `assert role.value == 45` 才會紅。這條把「欄位存在」直接寫成斷言，
    失敗訊息才指得到真正的原因。
    """
    for field in ("text", "value", "unit", "status", "action_ref"):
        assert field in RoleValue.model_fields, f"RoleValue 少了欄位 {field}（ADR-011 只增不改）"
    for field in ("start", "end", "text"):
        assert field in EvidenceSpan.model_fields, f"EvidenceSpan 少了欄位 {field}"


def test_request_shaped_output_parses_as_the_contract():
    """索取形狀必須是解析形狀的子集：模型照 schema 產出的 JSON 不需任何轉換。

    這條擋的是「索取 schema 漂到契約收不下的形狀」——例如把 `evidence` 改成
    `list[str]`、把 `roles` 改成 list。那種改動不會被上面任何一條抓到
    （欄位名沒少、也沒多），但會讓每一份輸出都在 `model_validate` 炸掉。
    """
    request = PlannerRequest.model_validate(
        {
            "language": "zh",
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "acquire",
                    "sequence_order": 1,
                    "roles": {"tool": {"text": "電動起子"}, "tool_ref": {"action_ref": "a1"}},
                    "evidence": [{"text": "拿取電動起子"}],
                }
            ],
            "dependencies": [
                {"from_action": "a1", "to_action": "a1", "type": "tool_held_for"}
            ],
            "unresolved": ["next_operation"],
        }
    )
    output = PlannerOutput.model_validate(request.model_dump())
    assert output.actions[0].roles["tool"].text == "電動起子"
    assert output.actions[0].roles["tool_ref"].action_ref == "a1"
    assert output.actions[0].evidence[0].text == "拿取電動起子"
    assert output.dependencies[0].type == "tool_held_for"


def test_request_schema_field_names_are_a_subset_of_contract_field_names():
    """索取的每一個欄位名，契約都要有——否則模型照著填的東西會被 pydantic 丟掉。"""
    contract_fields = (
        set(PlannerOutput.model_fields)
        | set(PlannedAction.model_fields)
        | set(RoleValue.model_fields)
        | set(EvidenceSpan.model_fields)
        | {"from_action", "to_action", "type"}
    )
    extra = sorted(_property_names(request_json_schema()) - contract_fields)
    assert extra == [], f"索取 schema 有契約沒有的欄位名：{extra}"


# ── 這份 schema 真的是送出去的那一份嗎 ──────────────────────────────────


class _FakeLLMClient:
    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    async def structured_completion(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        from ddm_v2.nlp.planner_ports import LLMRawResponse

        return LLMRawResponse(content=self._payload, model="fake-model", latency_ms=1.0)


@pytest.mark.asyncio
async def test_llm_planner_sends_the_request_schema_not_the_contract_schema():
    """把「公告面已經換掉」釘在**實際送出的參數**上，而不是常數的相等比較。

    只斷言 `plan_v1.REQUEST_JSON_SCHEMA == request_json_schema()` 是不夠的——
    `llm_planner` 完全可以繼續送 `PlannerOutput.model_json_schema()`，那條斷言照樣綠。
    這裡攔的是 client 真正收到的 `json_schema`。
    """
    from ddm_v2.nlp.contracts import ParseContext
    from ddm_v2.nlp.llm_planner import LLMPlannerAdapter

    norm = "拿起dimm"
    payload = json.dumps(
        {
            "language": "zh",
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "acquire",
                    "sequence_order": 1,
                    "roles": {"object": {"text": "dimm"}},
                    "evidence": [{"text": norm}],
                }
            ],
            "dependencies": [],
            "unresolved": [],
        },
        ensure_ascii=False,
    )
    client = _FakeLLMClient(payload)
    await LLMPlannerAdapter(client).plan(norm, ParseContext(rule_set_code="X"))

    sent = client.calls[0]["json_schema"]
    assert sent == request_json_schema(), "送出去的不是索取 schema"
    announced = _property_names(sent)
    leaked = sorted(_MUST_NOT_BE_ANNOUNCED & announced)
    assert leaked == [], (
        f"實際送給模型的 schema 仍公告了收窄掉的欄位：{leaked}"
        "——常數換了但呼叫端沒換，是最容易漏的一步"
    )
    # 負向對照：契約 schema 確實還帶著那些欄位，所以上面那條不是恆真。
    assert _MUST_NOT_BE_ANNOUNCED <= _property_names(PlannerOutput.model_json_schema()), (
        "`PlannerOutput` 的 schema 已經不公告那些欄位了——那本測試的對照組不成立，"
        "請確認契約沒有被一起收窄（ADR-011）"
    )


def test_prompt_module_exposes_the_same_request_schema():
    """`plan_v1.REQUEST_JSON_SCHEMA` 是 import 時算的常數，必須與函式產出的一致。"""
    assert plan_v1.REQUEST_JSON_SCHEMA == request_json_schema()
