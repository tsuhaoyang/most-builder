"""對外列舉的**契約凍結**（ADR-011）：只准長，不准縮。

## 這在守什麼

凍結的東西**收窄後果不同**，措辭必須分開寫——說成同一件事會讓人以為守得比實際多。
三類：

**(a) 過 pydantic 的 Literal ＝既存列讀不回來。** `nlp/contracts.py` 五個別名與模型欄位
上的 inline 兄弟、`schemas/v2` 的 `SourceLiteral`／`VocabKind`／`EntityType`／
`FieldName`／`ReviewSource`。值落進 `ai_parse_runs.plan` / `routing_status`、
`wi_contexts.source`、`vocab_items.kind`、`i18n_review_state.{entity_type,field,source}`，
讀取端要經 `model_validate`：**收窄一個成員，既存列就反序列化失敗。**

**(b) `ROLE_KEYS` ＝靜默降級，不是讀不回來。** 它是 `frozenset` 不是 Literal，
`PlannedAction.roles` 的型別是 `dict[str, RoleValue]`——未知鍵**不會**讓
`model_validate` 失敗。收窄的後果是那個角色被 `sanitize_planner_output` 當自創鍵丟掉、
記一筆 `role_key_dropped`，資料照樣讀得回來。**沒有閘門，只有降級**，所以更難察覺。

**(c) 沒有反序列化閘門的宣告面。** `routing.ROUTING_REASONS`：`routing_reasons` 是
JSONB `list[str]`，沒有任何地方拿這個集合驗過它（S-5：宣告了卻不執行），收窄壞的是
**前端依 key 顯示中文文案**，以及 `test_eligible_auto_blocked_reasons_are_all_declared`
的判準（那條守衛拿它當宣告面的下界）。`schemas/v2.i18n.PendingStatus` 同類但更輕：
它**不是 DB 欄**（`models/v2/i18n.py` 沒有對應欄位也沒有 CHECK），只在 response 模型，
收窄壞的是 **API 回應形狀**。

## ⚠️ 涵蓋範圍（v1）

只涵蓋 wi-plan-v1 與 i18n／vocab／wi_context 三支 schema。全樹另有 4 個模組級別名與
13 個 `schemas/v2` inline Literal 欄位**尚未凍結**（票 G-3）——清單與理由見
`_contract_freeze_v1.py` 檔頭。**沒列進表裡的對外列舉，收窄時不會有任何東西紅。**

## 為什麼非要有這一支（實測，2026-08-23）

把 `contracts.RoleStatus` 拿掉 `"default"` → `pytest tests/unit` **1385 passed 全綠**。
唯一會紅的成員是 `"explicit_unresolved"`，而那是**偶然**：只因為今天剛好有 production
code 會產出它。沒有 producer 的成員（`default`、`precedes`、`return_to`）在收窄時完全無聲，
而它們正是 ADR-033 明文為了相容性才保留的那幾個。

實害紀錄：同一輪有 agent 的 mutation 因 Bash 逾時中斷，把收窄後的 `RoleStatus` 留在磁碟上，
測試全綠、差一點被 commit。

## 判準與失效模式

判準是 **基準 ⊆ 實際**（下界表在 `_contract_freeze_v1.py`，不是從 `get_args()` 取的——
從契約自己取下界的守衛會跟著契約一起收窄，等於替收窄背書）。改名＝舊成員消失，一樣紅。
新增成員維持綠（ADR-011 明文允許加法）。

這類凍結最典型的失效模式是**空跑**：型別別名被改成 `str`（或別的非 Literal 形式）時
`get_args()` 回空 tuple。空集合下「基準 ⊆ 實際」會直接失敗，但失敗訊息會誤導（看起來像
「少了全部成員」），所以另有 `test_*_is_still_a_literal` 顯式釘住形式與成員數下界。
`_contract_freeze_v1` 那份表被掏空的情形由 `test_freeze_tables_are_not_gutted` 擋。

檢查器自己的負向控制在 `test_missing_members_detects_*` / `test_literal_members_*`。
"""
from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

import pytest
from _contract_freeze_v1 import (
    ADR_011,
    EXPECTED_FROZEN_ALIAS_MEMBERS,
    EXPECTED_FROZEN_ALIASES,
    EXPECTED_FROZEN_FIELD_MEMBERS,
    EXPECTED_FROZEN_FIELDS,
    EXPECTED_FROZEN_ROLE_KEYS,
    EXPECTED_FROZEN_ROUTING_REASONS,
    EXPECTED_FROZEN_SCAN_MODULES,
    FROZEN_ALIAS_MEMBERS,
    FROZEN_ALIAS_SCAN_MODULES,
    FROZEN_FIELD_MEMBERS,
    FROZEN_ROLE_KEYS,
    FROZEN_ROUTING_REASONS,
)
from pydantic import BaseModel

from ddm_v2.nlp import contracts, routing
from ddm_v2.nlp.routing import ROUTING_REASONS

pytestmark = pytest.mark.unit


# ── 檢查器 ───────────────────────────────────────────────────────────


def literal_members(annotation: Any) -> frozenset[str]:
    """取出 annotation 裡所有 `Literal` 成員；不是 Literal（含 `str`）回空集合。

    要遞迴進 union，因為 `RoleValue.status` 的型別是 `RoleStatus | None`——
    只看最外層 origin 會把它判成「沒有 Literal」而靜默放過。
    """
    origin = get_origin(annotation)
    if origin is Literal:
        return frozenset(str(a) for a in get_args(annotation))
    if origin in (Union, UnionType):
        out: set[str] = set()
        for arg in get_args(annotation):
            out |= literal_members(arg)
        return frozenset(out)
    return frozenset()


def missing_members(baseline: frozenset[str], actual: frozenset[str]) -> list[str]:
    """基準有、實際沒有的成員（＝被收窄掉的）。排序以便訊息穩定。"""
    return sorted(baseline - actual)


def _fail_message(label: str, baseline: frozenset[str], actual: frozenset[str]) -> str:
    return (
        f"{label} 收窄了：少了 {missing_members(baseline, actual)}"
        f"（凍結基準 {sorted(baseline)}；目前實際 {sorted(actual)}）。\n{ADR_011}"
    )


def _module_level_literal_aliases(module_name: str) -> dict[str, Any]:
    """AST 掃「這個檔裡**定義**的」模組級 `X = Literal[...]`。

    用 AST 而非掃 runtime namespace：後者分不出「本檔定義」與「從別處 import 進來」，
    同一個別名會在每個 re-export 的模組各記一筆，凍結表變成要為 import 記帳。
    """
    module = importlib.import_module(module_name)
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    found: dict[str, Any] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        if not isinstance(value, ast.Subscript):
            continue
        base = value.value
        base_name = (
            base.id if isinstance(base, ast.Name)
            else base.attr if isinstance(base, ast.Attribute)
            else None
        )
        if base_name != "Literal":
            continue
        for target in targets:
            found[target.id] = getattr(module, target.id)
    return found


# ── 模組級 Literal 別名 ──────────────────────────────────────────────


@pytest.mark.parametrize("qualname", sorted(FROZEN_ALIAS_MEMBERS))
def test_frozen_alias_still_exists(qualname: str):
    """別名本身還在（整個刪掉／改名 → ImportError 前先在這裡紅，訊息才有指向性）。"""
    module_name, _, name = qualname.rpartition(".")
    module = importlib.import_module(module_name)
    assert hasattr(module, name), (
        f"對外別名 {qualname} 不見了（刪除或改名皆屬破壞性）。\n{ADR_011}"
    )


@pytest.mark.parametrize("qualname", sorted(FROZEN_ALIAS_MEMBERS))
def test_frozen_alias_is_still_a_literal(qualname: str):
    """形式守衛：仍是 `Literal[...]`、且成員數不低於基準。

    這條擋的是**空跑**：`RoleStatus = str` 之類的改法讓 `get_args()` 回 `()`，
    任何「拿 get_args 當集合」的檢查都會變成對空集合做集合運算。
    """
    module_name, _, name = qualname.rpartition(".")
    alias = getattr(importlib.import_module(module_name), name)
    baseline = FROZEN_ALIAS_MEMBERS[qualname]
    assert get_origin(alias) is Literal, (
        f"{qualname} 已不是 Literal（實際 {alias!r}）——凍結守衛會因 get_args() 回空而失效。"
        f"\n{ADR_011}"
    )
    actual = frozenset(str(a) for a in get_args(alias))
    assert len(actual) >= len(baseline), (
        f"{qualname} 成員數 {len(actual)} < 凍結下界 {len(baseline)}。\n{ADR_011}"
    )


@pytest.mark.parametrize("qualname", sorted(FROZEN_ALIAS_MEMBERS))
def test_frozen_alias_members_only_grow(qualname: str):
    """判準：**基準 ⊆ 實際**。少任何一個成員（含改名造成的消失）就紅。"""
    module_name, _, name = qualname.rpartition(".")
    alias = getattr(importlib.import_module(module_name), name)
    baseline = FROZEN_ALIAS_MEMBERS[qualname]
    actual = frozenset(str(a) for a in get_args(alias))
    assert missing_members(baseline, actual) == [], _fail_message(qualname, baseline, actual)


@pytest.mark.parametrize("module_name", FROZEN_ALIAS_SCAN_MODULES)
def test_every_module_level_literal_alias_is_frozen(module_name: str):
    """涵蓋率：掃到的別名都必須在凍結表裡。

    沒有這條，新加的對外別名會**靜默地不受凍結保護**——而「有一支凍結測試」會讓人
    以為全部都被守著。私有別名（`_` 開頭）不算對外契約，排除。
    """
    scanned = {
        f"{module_name}.{name}"
        for name in _module_level_literal_aliases(module_name)
        if not name.startswith("_")
    }
    unfrozen = sorted(scanned - set(FROZEN_ALIAS_MEMBERS))
    assert unfrozen == [], (
        f"這些對外 Literal 別名沒有凍結基準：{unfrozen}。"
        f"請在 tests/unit/_contract_freeze_v1.py 的 FROZEN_ALIAS_MEMBERS 補上下界。\n{ADR_011}"
    )
    stale = sorted(
        q for q in FROZEN_ALIAS_MEMBERS
        if q.rpartition(".")[0] == module_name and q not in scanned
    )
    assert stale == [], (
        f"凍結表列了 {module_name} 裡不存在的別名：{stale}"
        f"（別名被刪或改名＝破壞性變更；不是把表改短的理由）。\n{ADR_011}"
    )


# ── wi-plan-v1 模型欄位上的 Literal ─────────────────────────────────


def _contract_models() -> dict[str, type[BaseModel]]:
    return {
        name: obj
        for name, obj in vars(contracts).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == contracts.__name__
    }


@pytest.mark.parametrize("field_path", sorted(FROZEN_FIELD_MEMBERS))
def test_frozen_field_literals_only_grow(field_path: str):
    """模型欄位層的同一條判準。

    別名層守不到 inline Literal（`SourceRef.kind`、`WorkInstructionPlan.language`
    沒有模組級名字），而它們一樣是落進 `ai_parse_runs.plan` 的值。
    """
    model_name, _, field_name = field_path.partition(".")
    model = _contract_models().get(model_name)
    assert model is not None, f"契約模型 {model_name} 不見了。\n{ADR_011}"
    field = model.model_fields.get(field_name)
    assert field is not None, f"契約欄位 {field_path} 不見了。\n{ADR_011}"
    baseline = FROZEN_FIELD_MEMBERS[field_path]
    actual = literal_members(field.annotation)
    assert actual, (
        f"{field_path} 的型別已不含 Literal（實際 {field.annotation!r}）"
        f"——凍結會因空集合而失效。\n{ADR_011}"
    )
    assert missing_members(baseline, actual) == [], _fail_message(field_path, baseline, actual)


def test_every_literal_field_in_contracts_is_frozen():
    """涵蓋率：`nlp/contracts.py` 內每個帶 Literal 的模型欄位都要有下界。"""
    scanned = {
        f"{model_name}.{field_name}"
        for model_name, model in _contract_models().items()
        for field_name, field in model.model_fields.items()
        if literal_members(field.annotation)
    }
    unfrozen = sorted(scanned - set(FROZEN_FIELD_MEMBERS))
    assert unfrozen == [], (
        f"這些契約欄位的 Literal 沒有凍結基準：{unfrozen}。"
        f"請在 FROZEN_FIELD_MEMBERS 補上下界。\n{ADR_011}"
    )
    stale = sorted(set(FROZEN_FIELD_MEMBERS) - scanned)
    assert stale == [], (
        f"凍結表列了不存在（或已不是 Literal）的欄位：{stale}。\n{ADR_011}"
    )


# ── 非 Literal 的封閉集合 ────────────────────────────────────────────


def test_role_keys_only_grow():
    """`ROLE_KEYS` 收窄＝既存 plan 的角色被當自創鍵**靜默丟棄**（降級不是失敗）。"""
    actual = frozenset(contracts.ROLE_KEYS)
    assert missing_members(FROZEN_ROLE_KEYS, actual) == [], _fail_message(
        "contracts.ROLE_KEYS", FROZEN_ROLE_KEYS, actual
    )


def test_routing_reasons_only_grow():
    """`ROUTING_REASONS` 收窄＝前端文案表對不上既存 `routing_reasons`。

    ⚠️ 這個白名單目前**宣告了卻不執行**（S-5，生產端零引用）。它守的是「值域的
    對外宣告」，不是執行期過濾——S-5 落地那天值域若要變，那是**有裁決的**變動。
    """
    actual = frozenset(ROUTING_REASONS)
    assert missing_members(FROZEN_ROUTING_REASONS, actual) == [], _fail_message(
        "routing.ROUTING_REASONS", FROZEN_ROUTING_REASONS, actual
    )


# `_eligible_auto` 裡那個 function-local `blocked` 集合的成員數**下界**。
#
# 它刻意叫 `MIN_` 而不是 `EXPECTED_`（對照 `_contract_freeze_v1` 的 `EXPECTED_FROZEN_*`
# 那組 exact parity）：那組守的是**測試側的下界表**，動表就該改數字；這個守的是
# **產品碼**，合法新增擋 auto 的旗標時不該逼人改測試常數。
#
# `>=` 之所以夠用，前提是抽取器**完整**——見 `_eligible_auto_blocked_elts` 的
# 「驗證不過濾」。抽取器若會靜默丟掉元素，這個地板數的是「丟完還剩幾個」，
# 結構上不可能發現自己漏了東西。
_MIN_BLOCKED_REASONS = 14

# `ROUTING_REASONS` 有、`blocked` **刻意沒有**的旗標，以及各自的理由。
#
# ⚠️ 這不是「冗餘、補不補都無害」的清單，**前兩個是承重的設計決定**：補進 `blocked`
# 會改變 auto 語意。今天 `wi_ai_auto_enabled` 預設 False，爆炸半徑小；但這份清單存在的
# 全部意義就是「旗標打開那天要是對的」。
# 防掏空：兩個斷言對**空 dict 同時恆真**（`stale` 是空清單、交集是空集合），
# 掏空它 ＋ 把那四個補進 `blocked` 實測 **95 passed 全綠**——F3 的保護整個消失，
# 而 F1 那條照樣綠（那四個都在 `ROUTING_REASONS` 裡，宣告一致性沒被違反）。
# 與本檔其他表一致：動表就改這個數字（合法移除照樣走得通，只是多改一個數字）。
_EXPECTED_INTENTIONALLY_UNBLOCKED = 4

_INTENTIONALLY_UNBLOCKED: dict[str, str] = {
    "fallback_rule_based": (
        "由 `wi_ai_service` 經 `extra_reasons` 進 reasons，**不走 unresolved**；"
        "補進 blocked ＝所有 rule fallback 的列一律不得 auto——那是語意變更，不是補漏"
    ),
    "composite_unknown": (
        "經 draft issues 逐字併入 reasons。**混合**計畫（不是全 composite，不會走"
        " `compute_routing` 的 abstain 早退）只要某個 draft 帶這個 issue，就會從可 auto"
        " 變不可 auto——語意變更，不是補漏"
    ),
    "planner_invented_action": (
        "走 `plan.unresolved`（`sanitize_planner_output` 把 reason 裸前綴併進去），"
        "`_eligible_auto` 第一行 `if plan.unresolved: return False` 擋得更早也更硬＝冗餘"
    ),
    "tool_state_violation": (
        "同上，走 `plan.unresolved`，被第一行擋掉＝冗餘"
    ),
}


def _describe_node(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return f"Name({node.id})"
    if isinstance(node, ast.Constant):
        return f"Constant({node.value!r})"
    if isinstance(node, ast.Starred):
        return "Starred(*...)"
    return type(node).__name__


def _describe_binding(node: ast.AST) -> str:
    line = getattr(node, "lineno", "?")
    if isinstance(node, ast.Assign):
        return f"L{line} Assign(blocked = ...)"
    if isinstance(node, ast.AugAssign):
        op = type(node.op).__name__
        return f"L{line} AugAssign(blocked {op}= ...)"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return f"L{line} Call(blocked.{node.func.attr}(...))"
    return f"L{line} {type(node).__name__}"


def _eligible_auto_blocked_bindings() -> list[ast.AST]:
    """收集 `_eligible_auto` 內**所有**會改動 `blocked` 的節點——不提早 return。

    ⚠️ 前一版掃到**第一個** `blocked = {...}` 就 return，於是之後的再賦值完全不設防。
    實測：在字面量之後加一句 `blocked |= {"secret_augmented_flag"}` → **1469 passed
    全綠**。那個旗標 runtime 確實在 `blocked` 裡、確實擋 auto、確實沒被宣告——正是本
    守衛存在的唯一理由；`_MIN_BLOCKED_REASONS >= 14` 也擋不住，因為字面量那 14 個一個
    沒少。同類漏法還有 `blocked = blocked | X`（第二個 Assign）、`blocked.update(X)`
    （`ast.Expr(Call)`，舊迴圈根本不看）、`if cond: blocked = {...}`（`ast.walk` 是 BFS，
    必定先撞到淺的那個）。

    三種形式一起收：`Assign`、`AugAssign`、以及任何 `blocked.<method>(...)` 的 `Call`
    （`r in blocked` 是 `Compare` 不是 `Call`，不會誤收）。呼叫端要求**恰好一個**。
    """
    source = Path(inspect.getfile(routing)).read_text(encoding="utf-8")
    fn = next(
        (
            n
            for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.FunctionDef) and n.name == "_eligible_auto"
        ),
        None,
    )
    if fn is None:
        return []
    bindings: list[ast.AST] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "blocked" for t in node.targets
        ):
            bindings.append(node)
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "blocked"
        ):
            bindings.append(node)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "blocked"
        ):
            bindings.append(node)
    return bindings


def _blocked_reasons() -> frozenset[str]:
    """驗證式抽取：要嘛回完整集合，要嘛大聲壞掉。"""
    bindings = _eligible_auto_blocked_bindings()
    assert len(bindings) == 1, (
        f"`blocked` 在 `_eligible_auto` 裡被賦值／改動 {len(bindings)} 次"
        f"（{[_describe_binding(b) for b in bindings]}）——本抽取器只讀得懂**單一集合"
        "字面量**。多次賦值（`|=`、`blocked = blocked | X`、`blocked.update(X)`、"
        "條件分支各賦一次）的值 runtime 確實會擋 auto，但抽取器讀不出來，"
        "宣告一致性檢查會靜默失去對象。請維持單一字面量，或改寫 "
        "`_eligible_auto_blocked_bindings` 讓它讀得懂新形式。"
    )
    node = bindings[0]
    assert isinstance(node, ast.Assign) and isinstance(node.value, ast.Set), (
        f"`blocked` 的唯一綁定不是集合字面量（{_describe_binding(node)}）"
        "——被改寫成 `frozenset({...})`／推導式／單一運算式了。"
        "請同步改寫 `_eligible_auto_blocked_bindings`，不要讓它靜默回空"
        "（那會讓下面的差集恆空而假綠）。"
    )
    elts = list(node.value.elts)
    non_literal = [_describe_node(e) for e in elts if not isinstance(e, ast.Constant)]
    non_literal += [
        _describe_node(e)
        for e in elts
        if isinstance(e, ast.Constant) and not isinstance(e.value, str)
    ]
    assert non_literal == [], (
        f"`blocked` 含非字串字面量的元素：{non_literal}。"
        "本抽取器**只保證得了字串字面量的完整性**；有間接引用（常數名、拼接、星號展開）"
        "時它讀不出實際值，卻又擋不住——那個值會有執行語意卻不受宣告檢查。"
        "請維持純字串字面量，或改寫 `_eligible_auto_blocked_bindings` 讓它讀得懂新形式。"
    )
    return frozenset(e.value for e in elts)  # type: ignore[union-attr]


def _stale_keys(intent: dict[str, str], declared: frozenset[str]) -> list[str]:
    """`_INTENTIONALLY_UNBLOCKED` 指向了宣告集合裡不存在的 reason（＝清單過期）。

    抽成純函數是為了讓過期偵測能**隔離**驗證：要在真實資料上驗它，得從
    `ROUTING_REASONS` 刪一個成員，那會同時觸發 `test_routing_reasons_only_grow`，
    分不出是哪一條在守。負向控制見 `test_stale_keys_detects_removed_reason`。
    """
    return sorted(k for k in intent if k not in declared)


def test_eligible_auto_blocked_reasons_are_all_declared():
    """**真正在執行的**封閉集合，必須被 `ROUTING_REASONS` 宣告到。判準只有單向。

    `ROUTING_REASONS` 是宣告，`_eligible_auto` 的 `blocked` 才是**有執行語意**的集合
    （命中就擋掉自動落地）。兩者先前零守衛，實際已經漂開：`template_hint` 在
    `compute_routing` 被寫進 reasons、在 `blocked` 裡擋 auto，卻不在 `ROUTING_REASONS`
    ——凍結表照抄宣告，所以也漏掉它。**表與宣告的雙向 diff 照不到這種洞，因為錯的是
    宣告本身。**

    反方向**不是** `ROUTING_REASONS ⊆ blocked`——那會把正確設計判成錯。刻意的不對稱
    由 `test_intentionally_unblocked_reasons_stay_unblocked` 釘住（連理由一起），
    不靠這段 docstring 說服人。
    """
    blocked = _blocked_reasons()
    assert len(blocked) >= _MIN_BLOCKED_REASONS, (
        f"只從 `_eligible_auto` 抽到 {len(blocked)} 個 blocked reason"
        f"（下界 {_MIN_BLOCKED_REASONS}）——抽取器壞了，下面的差集會恆空而假綠。"
    )
    undeclared = sorted(blocked - set(ROUTING_REASONS))
    assert undeclared == [], (
        f"這些 reason 在 `_eligible_auto` 的 `blocked` 裡**有執行語意**（擋 auto），"
        f"卻沒有被 `routing.ROUTING_REASONS` 宣告：{undeclared}。"
        "前端依 `ROUTING_REASONS` 這份 key 清單顯示文案，漏宣告＝覆核者看到一個沒有"
        "文案的代碼，而且凍結表會照抄這個漏洞。"
    )


def test_intentionally_unblocked_reasons_stay_unblocked():
    """刻意的不對稱是**設計決定**，不是漏——所以寫成斷言，不是寫成 docstring。

    `ROUTING_REASONS ⊆ blocked` 這個「順手補齊」的動作，實測補完 **1468 全綠**、
    `test_routing.py` 16 支也全綠——沒有任何東西會擋。但其中兩個補進去會**改變 auto
    語意**（見 `_INTENTIONALLY_UNBLOCKED` 的逐條理由），另外兩個才是冗餘。

    這條紅的時候不是「你寫錯了」，而是「你正在動一個設計決定」——訊息會當場把理由
    攤開。真要改，改的就是這裡，而且會留下痕跡。
    """
    assert len(_INTENTIONALLY_UNBLOCKED) == _EXPECTED_INTENTIONALLY_UNBLOCKED, (
        f"`_INTENTIONALLY_UNBLOCKED` 有 {len(_INTENTIONALLY_UNBLOCKED)} 筆 ≠ "
        f"{_EXPECTED_INTENTIONALLY_UNBLOCKED}；掏空它會讓本測試的兩個斷言**同時恆真**"
        "（空清單、空交集），保護無聲消失。動表就改常數。"
    )
    stale = _stale_keys(_INTENTIONALLY_UNBLOCKED, frozenset(ROUTING_REASONS))
    assert stale == [], (
        f"清單指向了 `ROUTING_REASONS` 裡不存在的 reason：{stale}"
        "——清單過期了（reason 被刪或改名），先確認那個旗標的去向。"
    )
    blocked = _blocked_reasons()
    newly_blocked = sorted(set(_INTENTIONALLY_UNBLOCKED) & blocked)
    detail = "；".join(f"`{k}`：{_INTENTIONALLY_UNBLOCKED[k]}" for k in newly_blocked)
    assert newly_blocked == [], (
        f"這些 reason 被加進了 `_eligible_auto` 的 `blocked`，但它們是**刻意不在**的："
        f"{detail}。若這是有意識的語意變更，請改 `_INTENTIONALLY_UNBLOCKED` 並在 ADR／"
        "worklog 留下裁決；若只是「看起來少了就補齊」，請退回。"
    )


# ── 表自己的下界（防掏空）────────────────────────────────────────────


def test_freeze_tables_are_not_gutted():
    """把下界表刪空 → 「基準 ⊆ 實際」對空集合恆真 → 凍結**無聲失效**。

    更陰險的是被 `@pytest.mark.parametrize` 消費的那幾張表：清空之後那些斷言不是變紅，
    是**整批 skipped**——不存在的測試不會紅。實測掏空 `FROZEN_ALIAS_MEMBERS` 得到
    5 failed ＋ **3 skipped**，那 3 條就是消失的凍結斷言。

    ⚠️ 判準是 **`==`**：`>=` 會讓數字在表合法長大後沉默鬆弛（表 60 個成員、常數還是 50
    時，一次刪 10 個仍全綠）。動表就改數字，這個摩擦是刻意的。
    """
    _SHARED = (
        "⚠️ `FROZEN_ROLE_STATUS`（別名表＋`RoleValue.status`）與 `FROZEN_LANGUAGE`"
        "（兩個 language 欄位）是**共用的 frozenset**：加一個成員會同時打破兩個數字，"
        "兩個都要改。"
    )
    alias_members = sum(len(v) for v in FROZEN_ALIAS_MEMBERS.values())
    field_members = sum(len(v) for v in FROZEN_FIELD_MEMBERS.values())
    assert len(FROZEN_ALIAS_MEMBERS) == EXPECTED_FROZEN_ALIASES, (
        f"凍結別名 {len(FROZEN_ALIAS_MEMBERS)} 筆 ≠ EXPECTED_FROZEN_ALIASES"
        f"（{EXPECTED_FROZEN_ALIASES}）；動表就改常數"
    )
    assert alias_members == EXPECTED_FROZEN_ALIAS_MEMBERS, (
        f"別名成員總數 {alias_members} ≠ EXPECTED_FROZEN_ALIAS_MEMBERS"
        f"（{EXPECTED_FROZEN_ALIAS_MEMBERS}）；動表就改常數。{_SHARED}"
    )
    assert len(FROZEN_FIELD_MEMBERS) == EXPECTED_FROZEN_FIELDS, (
        f"凍結欄位 {len(FROZEN_FIELD_MEMBERS)} 筆 ≠ EXPECTED_FROZEN_FIELDS"
        f"（{EXPECTED_FROZEN_FIELDS}）；動表就改常數"
    )
    assert field_members == EXPECTED_FROZEN_FIELD_MEMBERS, (
        f"欄位成員總數 {field_members} ≠ EXPECTED_FROZEN_FIELD_MEMBERS"
        f"（{EXPECTED_FROZEN_FIELD_MEMBERS}）；動表就改常數。{_SHARED}"
    )
    assert len(FROZEN_ROLE_KEYS) == EXPECTED_FROZEN_ROLE_KEYS, (
        f"ROLE_KEYS 凍結 {len(FROZEN_ROLE_KEYS)} 個 ≠ EXPECTED_FROZEN_ROLE_KEYS"
        f"（{EXPECTED_FROZEN_ROLE_KEYS}）；動表就改常數"
    )
    assert len(FROZEN_ROUTING_REASONS) == EXPECTED_FROZEN_ROUTING_REASONS, (
        f"ROUTING_REASONS 凍結 {len(FROZEN_ROUTING_REASONS)} 個 ≠ "
        f"EXPECTED_FROZEN_ROUTING_REASONS（{EXPECTED_FROZEN_ROUTING_REASONS}）；動表就改常數"
    )
    assert all(FROZEN_ALIAS_MEMBERS.values()), "有別名的凍結基準是空集合＝那條沒在守"
    assert all(FROZEN_FIELD_MEMBERS.values()), "有欄位的凍結基準是空集合＝那條沒在守"


def test_scan_module_list_is_not_gutted():
    """`FROZEN_ALIAS_SCAN_MODULES` 也要有下界——它先前是唯一的例外。

    它被 `@pytest.mark.parametrize` 直接消費，清空之後
    `test_every_module_level_literal_alias_is_frozen` 的 4 個 case（連同 body 裡的
    `stale` 反向檢查）一起變成 skipped，**而且沒有任何其他斷言蓋得住它**——
    `FROZEN_ALIAS_MEMBERS` 那次至少還有 5 條紅陪著。

    第二句把兩張表互相釘死：凍結表裡有的模組，掃描清單一定要涵蓋，否則那個模組的
    「新別名不得逃過凍結」就沒人在守。
    """
    assert len(FROZEN_ALIAS_SCAN_MODULES) == EXPECTED_FROZEN_SCAN_MODULES, (
        f"掃描模組清單長度 {len(FROZEN_ALIAS_SCAN_MODULES)} ≠ {EXPECTED_FROZEN_SCAN_MODULES}"
        "；動清單就改常數（清空它會讓涵蓋率檢查 skipped 而非 failed）"
    )
    frozen_modules = {q.rpartition(".")[0] for q in FROZEN_ALIAS_MEMBERS}
    unscanned = sorted(frozen_modules - set(FROZEN_ALIAS_SCAN_MODULES))
    assert unscanned == [], (
        f"這些模組有凍結別名卻不在掃描清單裡：{unscanned}"
        "——該模組新增的對外別名不會被要求凍結。"
    )


# ── 凍結表不得腐爛（實際 ⊆ 基準）────────────────────────────────
#
# 上面那組守的是 ADR-011 的**收窄禁令**（基準 ⊆ 實際）。它對「新增成員」永遠是綠的
# ——**包括「加了成員但忘了登記進凍結表」**。那個新成員於是不受保護，日後被拿掉時
# 沒有任何東西會紅：凍結表會隨時間腐爛，而且**腐爛的過程全綠**。今天 base == actual
# 只是因為表是今天寫的；第一個合法新增就會打開第一個缺口。
#
# 所以另立一組，判準相反、訊息也不同。兩組合起來等於相等，但**刻意不寫成相等**：
# 一組答「誰違反了 ADR-011」，一組答「誰忘了登記」，混成一條會讓錯誤訊息失去指向性。


def _unregistered(baseline: frozenset[str], actual: frozenset[str]) -> list[str]:
    """實際有、基準沒登記的成員（＝新增後忘了進凍結表，因此不受保護）。"""
    return sorted(actual - baseline)


def _rot_message(label: str, new_members: list[str]) -> str:
    return (
        f"{label} 新增了 {new_members}，但沒有登記進凍結表＝**這些新成員不受保護**"
        "（日後被拿掉不會有任何東西紅）。請補進 tests/unit/_contract_freeze_v1.py"
        "，並同步調整對應的 MIN_ 常數。"
    )


@pytest.mark.parametrize("qualname", sorted(FROZEN_ALIAS_MEMBERS))
def test_no_unfrozen_alias_members(qualname: str):
    module_name, _, name = qualname.rpartition(".")
    alias = getattr(importlib.import_module(module_name), name)
    actual = frozenset(str(a) for a in get_args(alias))
    new_members = _unregistered(FROZEN_ALIAS_MEMBERS[qualname], actual)
    assert new_members == [], _rot_message(qualname, new_members)


@pytest.mark.parametrize("field_path", sorted(FROZEN_FIELD_MEMBERS))
def test_no_unfrozen_field_members(field_path: str):
    model_name, _, field_name = field_path.partition(".")
    model = _contract_models()[model_name]
    actual = literal_members(model.model_fields[field_name].annotation)
    new_members = _unregistered(FROZEN_FIELD_MEMBERS[field_path], actual)
    assert new_members == [], _rot_message(field_path, new_members)


def test_no_unfrozen_role_keys():
    new_members = _unregistered(FROZEN_ROLE_KEYS, frozenset(contracts.ROLE_KEYS))
    assert new_members == [], _rot_message("contracts.ROLE_KEYS", new_members)


def test_no_unfrozen_routing_reasons():
    new_members = _unregistered(FROZEN_ROUTING_REASONS, frozenset(ROUTING_REASONS))
    assert new_members == [], _rot_message("routing.ROUTING_REASONS", new_members)


# ── 檢查器的負向控制 ────────────────────────────────────────────────


def test_stale_keys_detects_removed_reason():
    """清單指向不存在的 reason → 必須指名它（完全隔離，不動 `ROUTING_REASONS`）。"""
    assert _stale_keys({"ghost": "…"}, frozenset({"real"})) == ["ghost"]


def test_stale_keys_is_quiet_when_all_declared():
    """全部都在宣告集合裡 → 空清單（否則上面那條可能是恆真的）。"""
    assert _stale_keys({"real": "…"}, frozenset({"real", "other"})) == []


def test_missing_members_detects_removal():
    """收窄一個成員 → 檢查器必須指名它。"""
    assert missing_members(frozenset({"a", "b", "c"}), frozenset({"a", "b"})) == ["c"]


def test_missing_members_allows_growth():
    """加成員維持綠（ADR-011 明文允許加法）。"""
    assert missing_members(frozenset({"a"}), frozenset({"a", "b"})) == []


def test_missing_members_detects_rename():
    """改名＝舊成員消失，一樣要紅。"""
    assert missing_members(frozenset({"old"}), frozenset({"new"})) == ["old"]


def test_literal_members_unwraps_optional():
    """`X | None` 必須挖得出 Literal，否則 `RoleValue.status` 會被判成「沒有 Literal」。"""
    assert literal_members(Literal["a", "b"] | None) == frozenset({"a", "b"})


def test_literal_members_returns_empty_for_non_literal():
    """非 Literal 回空集合——這正是空跑的形狀，欄位測試靠 `assert actual` 擋。"""
    assert literal_members(str) == frozenset()


def test_module_level_literal_alias_scan_is_not_empty():
    """AST 掃描器自己不得空跑：`nlp/contracts.py` 至少掃得到那五個別名。"""
    scanned = _module_level_literal_aliases("ddm_v2.nlp.contracts")
    assert {"ActionType", "RoleStatus", "DependencyType", "CandidateSource", "RoutingStatus"} <= set(
        scanned
    ), f"AST 掃描器抓不到已知別名（實際掃到 {sorted(scanned)}）——涵蓋率測試會恆綠"
