"""few-shot 守衛：prompt 裡的示範必須自己通過 planner 契約。

為什麼需要這支測試：`prompts/plan_v1.py` 的 few-shot 是模型唯一看得到的正確樣本，
模型會連同示範裡的錯誤一起學。2026-08-22 之前，4 則示範共 5 個 evidence span 裡
有 3 個 offset 算錯（2 個越界），等於在 in-context 教模型數錯位置、還教它越界——
而**沒有任何測試會紅**，因為既有測試只驗模型輸出、沒有人驗教材。

本檔把「教材必須符合契約」變成可執行的斷言：把每一則 few-shot 的 assistant JSON
當成一份 `PlannerOutput`，用 `validate_planner_output()` 對它自己的 user message
驗一次。任何手改示範（改字、改 offset、加自創角色鍵）都會在這裡紅。

負向控制在 `test_guard_catches_shifted_offset`：offset 位移 2 個字元必須被抓到，
否則守衛本身是死的。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

import pytest
from _contract_freeze_v1 import FROZEN_DEPENDENCY_TYPE, FROZEN_ROLE_KEYS

from ddm_v2.nlp.contracts import (
    ROLE_KEYS,
    DependencyType,
    PlannerOutput,
    sanitize_planner_output,
    validate_planner_output,
)
from ddm_v2.nlp.normalization import normalize
from ddm_v2.nlp.prompts import plan_v1

pytestmark = pytest.mark.unit

_WI_TEXT_RE = re.compile(r"<wi_text>\n(.*)\n</wi_text>\Z", re.DOTALL)


def _wi_text(user_message: str) -> str:
    """從 few-shot 的 user message 取回 <wi_text> 內容。

    刻意不從 `build_user_message` 的輸入變數拿——守衛要驗的是「模型實際看到的
    那份文字」與 offset 座標系一致，從訊息本身反解才是獨立的檢查。
    """
    m = _WI_TEXT_RE.search(user_message)
    assert m is not None, f"few-shot user message 沒有 <wi_text> 區塊：{user_message!r}"
    return m.group(1)


def _shots() -> list[tuple[int, str, PlannerOutput]]:
    out = []
    for i, (user, assistant) in enumerate(plan_v1.FEW_SHOTS):
        text = _wi_text(user)
        out.append((i, text, PlannerOutput.model_validate(json.loads(assistant))))
    return out


@pytest.mark.parametrize("idx", range(len(plan_v1.FEW_SHOTS)))
def test_few_shot_wi_text_is_already_normalized(idx: int):
    """示範的 wi_text 必須是 `normalize()` 的不動點。

    推論時餵給模型的是 normalized 文字（`LLMPlannerAdapter.plan`），示範若用未
    normalize 的原文（全形逗號、大寫英文…），offset 座標系與推論時不同——教出來的
    數法就是錯的。
    """
    text = _wi_text(plan_v1.FEW_SHOTS[idx][0])
    assert text == normalize(text), (
        f"few-shot #{idx + 1} 的 wi_text 不是 normalized 形式："
        f"{text!r} -> {normalize(text)!r}"
    )


@pytest.mark.parametrize("idx", range(len(plan_v1.FEW_SHOTS)))
def test_few_shot_passes_planner_validation(idx: int):
    """示範的 assistant JSON 必須通過 `validate_planner_output()`（含 evidence offset）。"""
    _i, text, output = _shots()[idx]
    errors = validate_planner_output(output, normalized_text=text)
    assert errors == [], f"few-shot #{idx + 1} 自己就違反契約：{errors}"


@pytest.mark.parametrize("idx", range(len(plan_v1.FEW_SHOTS)))
def test_few_shot_evidence_text_is_exact_substring(idx: int):
    """evidence.text 必須是 normalized 原文在 [start, end) 的**精確**切片。

    validate 已驗切片相等；這裡另外要求 text 在原文中真的存在（模型改寫原文、
    只是「意思對」的 text 不算證據），並把失敗訊息寫成可直接讀出正解的形式。
    """
    _i, text, output = _shots()[idx]
    for action in output.actions:
        for ev in action.evidence:
            assert ev.text in text, (
                f"few-shot #{idx + 1} {action.action_id}：evidence text {ev.text!r} "
                f"不是 wi_text 的子字串"
            )
            expected_start = text.find(ev.text)
            assert (ev.start, ev.end) == (expected_start, expected_start + len(ev.text)), (
                f"few-shot #{idx + 1} {action.action_id}：offset [{ev.start},{ev.end}) 錯，"
                f"正解 [{expected_start},{expected_start + len(ev.text)})"
                f"（wi_text 長度 {len(text)}）"
            )


# ADR-033 P1 起，契約比 prompt 早一階：`value`／`unit` 已在 adapter 邊界剝除
# （D1），而 prompt 維持 plan-v1.4、仍教模型輸出數量與距離（P2 才改，刻意分離
# 「契約放寬」與「prompt 改寫」兩個變因）。因此**只有** `role_numeric_stripped`
# 是這一階段可接受的示範剝除；清單只准變短——P2 把數值從示範拿掉之後，
# `test_pending_prompt_debt_is_not_stale` 會要求把它一起刪掉。
_PROMPT_LAGS_CONTRACT_REASON_PREFIXES = ("role_numeric_stripped:",)


@pytest.mark.parametrize("idx", range(len(plan_v1.FEW_SHOTS)))
def test_few_shot_needs_no_sanitize_repair(idx: int):
    """示範不得需要 sanitize 修補（`role_numeric_stripped` 除外，見上方註）。

    `sanitize_planner_output` 會替模型推導 offset、剔除無證據動作、降級非法
    tool_ref、剝除自創角色鍵與原文沒有的片語。示範若要靠這些修補才合法，
    模型學到的就是「被修過的版本」以外的東西——這些 reason 在評測報告裡的
    次數也會被自家教材墊高。
    """
    _i, text, output = _shots()[idx]
    _sanitized, reasons = sanitize_planner_output(output, normalized_text=text)
    unexpected = [
        r
        for r in reasons
        if not r.startswith(_PROMPT_LAGS_CONTRACT_REASON_PREFIXES)
    ]
    assert unexpected == [], f"few-shot #{idx + 1} 需要 sanitize 修補：{unexpected}"


def test_few_shot_numeric_roles_are_exactly_the_known_prompt_debt():
    """把「prompt 落後契約一階」釘成可數的事實，而不是一句註解。

    P1 只放寬契約、不動 prompt（ADR §5、U-7：這是唯一能把兩個變因分開量的機會）。
    代價是示範仍在教模型輸出 `value`／`unit`，而 adapter 一律剝除——這裡列出
    受影響的位置，P2 改 prompt 時應該全部消失。
    """
    stripped = [
        (i + 1, r)
        for i, text, output in _shots()
        for r in sanitize_planner_output(output, normalized_text=text)[1]
        if r.startswith("role_numeric_stripped:")
    ]
    assert stripped == [
        (1, "role_numeric_stripped:a2:quantity"),
        (4, "role_numeric_stripped:a1:distance"),
    ], f"示範的數值角色分布變了：{stripped}"


def test_pending_prompt_debt_is_not_stale():
    """P2 把數值從示範拿掉之後，上面的豁免必須跟著刪——否則守衛悄悄變寬。"""
    still_numeric = any(
        role.value is not None or role.unit is not None
        for _i, _text, output in _shots()
        for action in output.actions
        for role in action.roles.values()
    )
    assert still_numeric == bool(_PROMPT_LAGS_CONTRACT_REASON_PREFIXES), (
        "示範已經沒有數值角色了（或反之）——`_PROMPT_LAGS_CONTRACT_REASON_PREFIXES` "
        "與 `test_few_shot_numeric_roles_are_exactly_the_known_prompt_debt` 要一起更新"
    )


@pytest.mark.parametrize("idx", range(len(plan_v1.FEW_SHOTS)))
def test_few_shot_uses_no_invented_role_key(idx: int):
    """示範只能用 `ROLE_KEYS` 內的鍵；`tool_ref` 是唯一的 `_ref` 變體。

    模型把 `tool_ref` 的命名合理外推成 `object_ref`／`hand_ref` 曾是最大宗的失敗
    （55 案裡 19 案），因為示範只展示了 `tool_ref`、規則沒說「只有 tool 有 _ref」。
    示範若哪天自己長出第二個 `_ref`，這條會紅。
    """
    _i, _text, output = _shots()[idx]
    for action in output.actions:
        for key in action.roles:
            assert key in ROLE_KEYS, f"few-shot #{idx + 1} {action.action_id} 自創角色鍵：{key}"
            if key.endswith("_ref"):
                assert key == "tool_ref", (
                    f"few-shot #{idx + 1} {action.action_id}：`tool_ref` 應是唯一的 "
                    f"`_ref` 鍵，卻出現 {key}"
                )


def test_few_shots_demonstrate_non_tool_role_reuse():
    """至少一則示範要展示「非 tool 角色沿用」的正確寫法。

    規則寫了不等於學得會——`object: {status: inferred, action_ref: aN}` 必須有
    示範，否則模型只看得到 `tool_ref` 一種沿用形狀，又會外推出 `object_ref`。
    這條擋的是「有人把那則示範刪了／改成別的形狀」。
    """
    found = [
        (i + 1, a.action_id, key)
        for i, _text, output in _shots()
        for a in output.actions
        for key, role in a.roles.items()
        if key != "tool_ref" and role.status == "inferred" and role.action_ref
    ]
    assert found, (
        "沒有任何 few-shot 示範非 tool 角色的沿用寫法"
        "（object/hand 等以 status=inferred + action_ref 表達）"
    )


# 契約已有、prompt 尚未索取的角色鍵。ADR-033 §5.2.2 把 `return_to`（＝A6
# 「返回若有」）排在 P1 進契約、P2 進 prompt、P3 進 compiler 分支——P1 不動
# prompt 是刻意的（見上方 `_PROMPT_LAGS_CONTRACT_REASON_PREFIXES` 的理由）。
# 清單只准變短：寫進 prompt 之後 `test_pending_role_key_exemptions_are_not_stale`
# 會要求把它從這裡刪掉。
_PENDING_PROMPT_ROLE_KEYS = frozenset({"return_to"})


def test_system_prompt_enumerates_every_contract_role_key():
    """`ROLE_KEYS` 有的鍵，system prompt 必須都告訴模型。

    契約與教材同步的守衛：日後若真的新增角色鍵（ADR-011 的欄位只增不改），
    忘了寫進 prompt 這條會紅——模型不會用它不知道的鍵。

    ⚠️ 判準的**下界**不由 `ROLE_KEYS` 自己提供（見下一句斷言）：拿被測物當合法集合的
    來源，收窄時判準會跟著收窄——不但擋不住收窄，還會替收窄背書。
    """
    assert FROZEN_ROLE_KEYS <= set(ROLE_KEYS), (
        f"ROLE_KEYS 收窄了，少了 {sorted(FROZEN_ROLE_KEYS - set(ROLE_KEYS))}"
        "——本測試的合法集合會跟著縮，請先看 test_contract_enum_freeze。"
    )
    missing = sorted(
        k
        for k in ROLE_KEYS
        if k not in plan_v1.SYSTEM_PROMPT and k not in _PENDING_PROMPT_ROLE_KEYS
    )
    assert missing == [], f"system prompt 未列出的角色鍵：{missing}"


def test_pending_role_key_exemptions_are_not_stale():
    """豁免清單只准變短：鍵一旦進了 prompt，就得從清單移除。"""
    landed = sorted(k for k in _PENDING_PROMPT_ROLE_KEYS if k in plan_v1.SYSTEM_PROMPT)
    assert landed == [], f"這些鍵已寫進 prompt，請從 _PENDING_PROMPT_ROLE_KEYS 移除：{landed}"
    unknown = sorted(k for k in _PENDING_PROMPT_ROLE_KEYS if k not in ROLE_KEYS)
    assert unknown == [], f"豁免了不存在於 ROLE_KEYS 的鍵：{unknown}"


def test_system_prompt_enumerates_every_dependency_type():
    """`DependencyType` 有的值，system prompt 必須都告訴模型。

    與 `test_system_prompt_enumerates_every_contract_role_key` 同一個道理，來源也
    同一個：plan-v1.2 的評測裡模型自創 `same_hand`，整筆 json_or_schema 作廢——
    契約列了四個合法值，prompt 一個都沒列。日後 enum 增值忘了寫進 prompt，這條會紅。

    ⚠️ `get_args(DependencyType)` 是「目前的合法集合」，**不是下界**：enum 一收窄，
    這裡的 `legal` 也跟著縮，missing 恆為空＝守衛替收窄背書。下界由
    `_contract_freeze_v1.FROZEN_DEPENDENCY_TYPE`（凍結測試獨立保證）補上。
    """
    legal = get_args(DependencyType)
    assert FROZEN_DEPENDENCY_TYPE <= set(legal), (
        f"DependencyType 收窄了，少了 {sorted(FROZEN_DEPENDENCY_TYPE - set(legal))}"
        "——本測試的合法集合會跟著縮，請先看 test_contract_enum_freeze。"
    )
    missing = sorted(t for t in legal if t not in plan_v1.SYSTEM_PROMPT)
    assert missing == [], f"system prompt 未列出的 dependency type：{missing}"


def test_guard_catches_shifted_offset():
    """負向控制：把示範的 offset 位移 2 個字元，守衛必須抓到。

    沒有這條，上面所有斷言都可能因為「驗法與示範用同一套推導」而恆綠。
    """
    _i, text, output = _shots()[0]
    broken = output.model_copy(deep=True)
    ev = broken.actions[0].evidence[0]
    broken.actions[0].evidence[0] = ev.model_copy(
        update={"start": ev.start + 2, "end": ev.end + 2}
    )
    assert validate_planner_output(broken, normalized_text=text), (
        "offset 位移 2 竟然通過驗證——守衛是死的"
    )


def test_guard_catches_out_of_range_offset():
    """負向控制：越界（end > len）必須被抓到——這正是修好前 2 個 span 的形態。"""
    _i, text, output = _shots()[0]
    broken = output.model_copy(deep=True)
    ev = broken.actions[0].evidence[0]
    broken.actions[0].evidence[0] = ev.model_copy(update={"end": len(text) + 1})
    errors = validate_planner_output(broken, normalized_text=text)
    assert any(e.startswith("evidence_offset_oor") for e in errors), (
        f"越界 offset 未被辨識為 evidence_offset_oor：{errors}"
    )


def test_guard_catches_invented_ref_role_key():
    """負向控制：示範若寫成 `object_ref`，`unknown_role_key` 必須紅。"""
    _i, text, output = _shots()[0]
    broken = output.model_copy(deep=True)
    roles = dict(broken.actions[1].roles)
    roles["object_ref"] = roles.pop("tool_ref")
    broken.actions[1].roles = roles
    errors = validate_planner_output(broken, normalized_text=text)
    assert any(e.startswith("unknown_role_key") for e in errors), (
        f"自創 object_ref 未被辨識為 unknown_role_key：{errors}"
    )


# --- 切分慣例守衛（plan-v1.2） -------------------------------------------------
#
# 為什麼再加一層：上面所有斷言都只驗**結構**（契約通過、offset 正確、角色鍵合法），
# plan-v1.1 那則「取一顆螺絲,放入右側治具 → acquire + move_place」在結構上完全合法，
# 卻教錯了語意切分——boundary fp 15→36、兩輪都成功案例的 f1 0.73→0.64，而 25 條
# 結構守衛全綠。這一段把切分慣例編碼成可測的規則，讓「示範違反慣例」會紅
# （守的對象是 few-shot＝模型的教材；兩條檢查各自的證據力見下方 ⚠️）。
#
# 慣例：「（從 X）拿取 Y 放到 Z」＝**一個** move_place（取得→移動→放置是同一輪循環），
#   `acquire` 只用在文字停在取得、沒有交代終點時。
# 兩條檢查互補，缺一漏得掉：
#   (1) 子句內：同一子句同時出現取得動詞與放置動詞 → 該子句只能對到一個 move_place。
#   (2) 跨子句：`acquire` 緊接著一個「接續它」的 `move_place` → 本來就該是一個 move_place。
#       plan-v1.1 的壞示範把取與放拆到逗號兩邊，(1) 抓不到、只有 (2) 抓得到。
#       「接續它」有兩種形態：明說相連（action_ref／dependency／同一個 object.text），
#       或**不留任何連結、但 move_place 自己也沒有 object**——後者是前者的繞道，
#       兩種都算違規（見 `_adjacent_split_violations`）。
#
# ⚠️ 兩條檢查的**證據力不同**，不要混為一談（2026-08-22 實測 55 案 60 個 action）：
#   (1) 有 gold 背書：gold 命中 10 個「取＋放」子句，全部標成單一 move_place，零例外
#       （`test_gold_corpus_one_move_place_per_acquire_place_clause`，非空跑）。
#   (2) **沒有** gold 背書：gold 的相鄰 action 型別對只有 acquire→controlled_move 2、
#       acquire→process 1、inspect→controlled_move 1、controlled_move→move_place 1，
#       `acquire→move_place` **一次都沒有**——(2) 唯一會觸發的形狀在 gold 裡不存在，
#       `test_gold_corpus_never_splits_acquire_then_move_place` 對它是**空跑通過**。
#       (2) 的依據是 few-shot 的語意與 plan-v1.1 那次量到的迴歸，不是 gold 統計。
#       它守的對象也只是 few-shot（模型的教材），不是 gold 本身。
GOLD_DIR = Path(__file__).resolve().parents[1] / "gold" / "wi_plans"

# 動詞表只用來**定位需要檢查的子句**，不用來判定 action_type——判型是模型/IE 的事。
# 表若失效（詞彙改了、gold 換料）不會讓檢查悄悄變成空跑：
# `test_gold_corpus_one_move_place_per_acquire_place_clause` 斷言 gold 至少命中
# 若干子句，詞表死掉就是紅的。
ACQUIRE_VERBS = ("拿取", "拿起", "取出", "取用", "抓握", "拾取", "取")
PLACE_VERBS = ("放至", "放置", "放入", "放到", "放於", "組至", "置於", "擺放")
_CLAUSE_SEP_RE = re.compile(r"[,，;；。]")
# gold 目前命中的子句數（55 案裡 10 個）。設成下界而非等值：新增 gold 不該讓它紅。
_MIN_GOLD_CLAUSES_CHECKED = 10


def _clauses(text: str) -> list[tuple[int, int, str]]:
    """以標點切子句，回傳 (start, end, 子句文字)——座標與 evidence 同一套。"""
    out: list[tuple[int, int, str]] = []
    start = 0
    for m in _CLAUSE_SEP_RE.finditer(text):
        out.append((start, m.start(), text[start : m.start()]))
        start = m.end()
    out.append((start, len(text), text[start:]))
    return [(s, e, t) for s, e, t in out if t.strip()]


def _as_dicts(output: PlannerOutput) -> tuple[list[dict], list[dict]]:
    dumped = output.model_dump()
    return dumped["actions"], dumped["dependencies"]


def _clause_violations(normalized_text: str, actions: list[dict]) -> tuple[list[str], int]:
    """檢查 (1)：回傳 (違規訊息, 被檢查的子句數)。"""
    problems: list[str] = []
    checked = 0
    for c_start, c_end, clause in _clauses(normalized_text):
        if not any(v in clause for v in ACQUIRE_VERBS):
            continue
        if not any(v in clause for v in PLACE_VERBS):
            continue
        checked += 1
        inside = [
            a
            for a in actions
            if a["evidence"]
            and all(c_start <= ev["start"] and ev["end"] <= c_end for ev in a["evidence"])
        ]
        types = [a["action_type"] for a in inside]
        if types != ["move_place"]:
            problems.append(
                f"子句 {clause!r} 同時有取得與放置動詞，依慣例應是**一個** move_place，"
                f"實際切成 {types}（action_id={[a['action_id'] for a in inside]}）"
            )
    return problems, checked


def _link_between(acquire: dict, move_place: dict, dependencies: list[dict]) -> str | None:
    """兩個 action 是否**明說**指涉同一件東西。

    （「拿取起子,把主板放到治具」是 acquire(工具) + move_place(別的物件)，合法。）

    ⚠️ 這三個訊號可以被同時省略：move_place 只要不寫 object，就沒有 action_ref、
    沒有可比對的 object.text，模型也不會生 dependency——所以「有連結」是充分條件
    而非必要條件，另一半判準在 `_adjacent_split_violations`。
    """
    for key, role in (move_place["roles"] or {}).items():
        if role.get("action_ref") == acquire["action_id"]:
            return f"{key}.action_ref"
    for dep in dependencies:
        if dep["from_action"] == acquire["action_id"] and dep["to_action"] == move_place["action_id"]:
            return f"dependency:{dep['type']}"
    a_obj = (acquire["roles"] or {}).get("object") or {}
    m_obj = (move_place["roles"] or {}).get("object") or {}
    if a_obj.get("text") and a_obj.get("text") == m_obj.get("text"):
        return "同一個 object.text"
    return None


def _own_object(action: dict) -> bool:
    """該 action 是否**自己**交代了放的是什麼（原文字面提供，不是沿用前一個 action）。

    `explicit` 與 `explicit_unresolved` 都算——兩者都表示這一段文字自己提到了物件
    （後者是「內容在外部」，例如「依圖示」，仍然是原文有提）。`inferred`／`missing`／
    整個省略都不算：那三種寫法都是「放的東西要去別處找」。

    ⚠️ 這個判別只對 **roles 齊全的 plan**（few-shot、LLM 輸出）有意義。現行 gold 是
    rule parser 預標註，roles 幾乎全空——它對 gold 23 個 move_place 一律回 False。
    """
    obj = (action["roles"] or {}).get("object") or {}
    if obj.get("status") not in ("explicit", "explicit_unresolved"):
        return False
    return obj.get("text") is not None or obj.get("value") is not None


def _adjacent_split_violations(actions: list[dict], dependencies: list[dict]) -> list[str]:
    """檢查 (2)：`acquire` 緊接著一個「接續它」的 `move_place`。

    兩條判準，缺一就能被繞過：
    (2a) 兩者由 action_ref／dependency／同一個 object.text 相連 → 明說指涉同一件東西。
    (2b) **完全沒有連結，但該 move_place 也沒有自己的 explicit object** → 一樣違規。
         只有 (2a) 時守衛可以被「不留連結的拆分」整個繞過：模型在 move_place 上省略
         object、或標 `status: missing`（規則 4 正是這樣教的），三個連結訊號同時落空，
         守衛就看不見了。實測把 few-shot #2 改成這個形狀（`拿取治具蓋板` +
         `放置於工作臺`，無 object、無連結）——正是把 boundary fp 從 15 推到 36 的
         那個壞形狀——(2a) 一條都不紅。
         判準的依據：放置動作若真的與前一個 acquire 無關，它必然講得出自己放的是什麼
         （「拿取起子,把主板放到治具」）；講不出來就是在放前一個 acquire 拿到的東西。

    ⚠️ (2) 整條（含 (2a)）的證據力來自 **few-shot 語意**與 plan-v1.1 那次量到的迴歸，
    **不是** gold 統計——gold 一組 acquire→move_place 相鄰對都沒有，它在 gold 上零觸發。
    這個假設對 few-shot（模型教材，roles 齊全）成立；對 rule parser 預標註的 gold
    **不**成立（`_own_object()` 對 gold 23 個 move_place 全回 False），細節與屆時的
    處理方式見 `test_gold_corpus_never_splits_acquire_then_move_place` 的前瞻脆弱性段。
    """
    problems: list[str] = []
    for prev, nxt in zip(actions, actions[1:]):
        if prev["action_type"] != "acquire" or nxt["action_type"] != "move_place":
            continue
        link = _link_between(prev, nxt, dependencies)
        if link is not None:
            problems.append(
                f"{prev['action_id']}(acquire) 緊接 {nxt['action_id']}(move_place) 且兩者由 "
                f"{link} 相連——取得→移動→放置是同一輪循環，應併成一個 move_place"
            )
        elif not _own_object(nxt):
            problems.append(
                f"{prev['action_id']}(acquire) 緊接 {nxt['action_id']}(move_place)，"
                f"而 {nxt['action_id']} 沒有自己的 explicit object——放的就是 "
                f"{prev['action_id']} 取得的那件東西，應併成一個 move_place"
                f"（roles={sorted((nxt['roles'] or {}).keys())}）"
            )
    return problems


def _gold_plans() -> list[tuple[str, str, list[dict], list[dict]]]:
    out = []
    for path in sorted(GOLD_DIR.glob("g*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        plan = data.get("plan") or {}
        actions = plan.get("actions") or []
        if not actions:
            continue
        out.append(
            (data["id"], plan.get("normalized_text") or "", actions, plan.get("dependencies") or [])
        )
    return out


@pytest.mark.parametrize("idx", range(len(plan_v1.FEW_SHOTS)))
def test_few_shot_clause_with_acquire_and_place_is_one_move_place(idx: int):
    """檢查 (1)：示範的「一句取＋放」不得被切成多個 action。"""
    _i, text, output = _shots()[idx]
    actions, _deps = _as_dicts(output)
    problems, _checked = _clause_violations(text, actions)
    assert problems == [], f"few-shot #{idx + 1} 違反 gold 切分慣例：{problems}"


@pytest.mark.parametrize("idx", range(len(plan_v1.FEW_SHOTS)))
def test_few_shot_does_not_split_acquire_then_move_place(idx: int):
    """檢查 (2)：示範不得把「取得同一物件再放置」拆成 acquire + move_place。

    這正是 plan-v1.1 那則被換掉的示範（`取一顆螺絲,放入右側治具`）的形狀；
    連同它「不留連結」的變體（move_place 省略 object）——見
    `test_guard_catches_linkless_split_with_objectless_move_place`。
    """
    _i, _text, output = _shots()[idx]
    actions, deps = _as_dicts(output)
    problems = _adjacent_split_violations(actions, deps)
    assert problems == [], f"few-shot #{idx + 1} 違反 gold 切分慣例：{problems}"


def test_few_shots_demonstrate_single_action_move_place_cycle():
    """至少一則示範要**正面**示範「取得→移動→放置＝一個 move_place」。

    只擋壞示範不夠：move_place 佔 gold 動作的 38%（23/60），是最需要學會的形狀。
    這條擋的是「有人把那則示範刪了，模型又只剩 acquire 可以模仿」。
    """
    found = [
        (i + 1, a.action_id, ev.text)
        for i, _text, output in _shots()
        for a in output.actions
        if a.action_type == "move_place"
        for ev in a.evidence
        if any(v in ev.text for v in ACQUIRE_VERBS) and any(v in ev.text for v in PLACE_VERBS)
    ]
    assert found, (
        "沒有任何 few-shot 示範「一句取＋放＝一個 move_place」"
        "（gold 裡這是最常見的形狀，示範缺席等於放任模型自己猜切分）"
    )


# 既存汙染（plan-v1.2 之前就在，不是本次引入）：few-shot #1 與 #3 的原文分別逐字等於
# gold g02_screwdriver_screw_x2 與 g01_acquire_dimm。這兩案在評測時等於「答案在
# prompt 裡」，分數偏樂觀；planner_eval 目前也沒有把 few-shot 重疊的案例排除。
# 這裡先把它凍結成明確清單而不是修掉，理由是修法會動到另外兩則示範的文字，與本輪
# 「只改切分慣例」的量測混在一起就分不清誰造成的變化——待決策（見交付回報）。
_KNOWN_GOLD_TEXT_OVERLAP = frozenset({"拿取電動起子,依圖示鎖附兩顆螺絲", "拿起dimm"})


def test_few_shot_texts_add_no_new_gold_contamination():
    """示範原文不得（再）直接抄 gold——few-shot 與評測共用案例就是測資汙染。

    抄一句，那一案的 boundary F1 就變成背答案；分數會漂亮，但量不到真實能力。
    既存的兩則列在 `_KNOWN_GOLD_TEXT_OVERLAP`；清單只准變短（守衛見
    `test_known_gold_overlap_exemptions_are_not_stale`），新增的抄襲會紅。

    ⚠️ 已知限制（不修）：只比對**精確全等**。同一句 gold 多加一個字（`拿起dimm ` 、
    `拿起dimm材料`）就繞得過去，而就洩題而言 near-copy 的效果與全等幾乎相同。
    要真的擋住得做近似比對（編輯距離／n-gram 重疊），那會連帶要定閾值與例外，
    本輪不做——這裡只保證「逐字抄」會紅。
    """
    gold_texts = {text for _gid, text, _a, _d in _gold_plans() if text}
    copied = [
        (i + 1, text)
        for i, text, _o in _shots()
        if text in gold_texts and text not in _KNOWN_GOLD_TEXT_OVERLAP
    ]
    assert copied == [], f"few-shot 原文抄自 gold（測資汙染）：{copied}"


def test_known_gold_overlap_exemptions_are_not_stale():
    """豁免清單只准變短：汙染一旦消失，那一項就該刪掉。

    為什麼要**兩個**方向都查：豁免是「這一則示範抄了 gold」這個事實的紀錄，事實可以
    從兩邊消失，而真正的修復路徑是後者——
      - gold 改了／換料 → 該文字不再是 gold，重疊沒了。
      - **示範改了**（把抄來的原文換成自撰的）→ 汙染修好了，重疊也沒了。
    原本只查前者，於是實測：把 few-shot #3 改成非 gold 文字後，`拿起dimm` 仍留在清單裡
    而 40 passed 零提示——「清單只准變短」這個承諾對真正的修復路徑根本不成立，
    豁免可以永久存續，下一個人讀到清單還以為汙染還在。
    """
    gold_texts = {text for _gid, text, _a, _d in _gold_plans() if text}
    shot_texts = {text for _i, text, _o in _shots()}
    stale_vs_gold = sorted(_KNOWN_GOLD_TEXT_OVERLAP - gold_texts)
    stale_vs_shots = sorted(_KNOWN_GOLD_TEXT_OVERLAP - shot_texts)
    assert stale_vs_gold == [], (
        f"_KNOWN_GOLD_TEXT_OVERLAP 有不存在於 gold 的項目（gold 已改？）：{stale_vs_gold}"
        "——清單過期就該刪掉那幾項，別讓豁免無限期存續"
    )
    assert stale_vs_shots == [], (
        f"_KNOWN_GOLD_TEXT_OVERLAP 有不再出現在任何 few-shot 的項目：{stale_vs_shots}"
        "——那則示範已經修好了，把它從豁免清單刪掉"
    )


def test_gold_corpus_one_move_place_per_acquire_place_clause():
    """慣例的依據：IE 已核准的 gold 對檢查 (1) 零例外。

    這條把「慣例是查出來的、不是我編的」變成可執行的證據——**只為檢查 (1) 背書**。
    檢查 (2) 沒有這種背書：它在 gold 上零觸發、是空跑（見
    `test_gold_corpus_never_splits_acquire_then_move_place`）。哪天 IE 真的改了切分
    慣例，這裡會先紅——那是提醒去改 prompt 與示範，不是把這條測試刪掉。
    同時當動詞表的防腐劑：詞表失效導致一個子句都沒命中時，下界斷言會紅。
    """
    violations: list[str] = []
    checked = 0
    for gid, text, actions, _deps in _gold_plans():
        problems, n = _clause_violations(text, actions)
        checked += n
        violations += [f"{gid}: {p}" for p in problems]
    assert checked >= _MIN_GOLD_CLAUSES_CHECKED, (
        f"gold 只命中 {checked} 個「取＋放」子句（預期 ≥ {_MIN_GOLD_CLAUSES_CHECKED}）"
        "——動詞表可能已經失效，檢查變成空跑"
    )
    assert violations == [], f"gold 自己就違反切分慣例，慣例的前提要重新確認：{violations}"


def test_gold_corpus_never_splits_acquire_then_move_place():
    """gold 沒有把 acquire 與 move_place 前後相鄰的案例——對檢查 (2) 是**空跑通過**。

    ⚠️ 這條**不是**檢查 (2) 的依據，別把它讀成「(2) 的慣例是查出來的」。實測
    （2026-08-22，55 案 60 個 action）：相鄰 action 型別對只有 acquire→controlled_move 2、
    acquire→process 1、inspect→controlled_move 1、controlled_move→move_place 1，
    `acquire→move_place` **一次都沒有**——(2) 唯一會觸發的形狀在 gold 裡不存在，
    這裡的違規數 0 是「前置條件零命中」，不是「gold 逐案支持」。
    有 gold 背書的是檢查 (1)（10 個子句，見
    `test_gold_corpus_one_move_place_per_acquire_place_clause`）；(2) 的依據是 few-shot
    語意與 plan-v1.1 那次量到的迴歸（boundary fp 15→36），兩者不要混為一談。

    那還留著它做什麼：gold 哪天真的長出 acquire→move_place 相鄰對，這裡會先紅，逼人
    回來看下面那條脆弱性。（gold 唯一同時有 acquire 與 move_place 的案例是 g32——
    拿取主機板／去除包裝袋／將主機板放置工作臺——中間隔著性質不同的動作，所以規則
    寫成「相鄰」而不是「不准同時出現」。）

    ⚠️ 前瞻脆弱性（動 gold 回填流程前必看）：現在的 gold plan 多半是 rule parser 預標註
    後由 IE 覆核切分／型別（60 個 action 只有 3 個有任何 roles，全集只有 1 條
    dependency），23 個 move_place 對 `_own_object()` 是 **0/23 全 False**。所以 gold 若
    改成從已核准的 LLM plan 回填（roles 會有內容），或單純只是出現一組**合法**的
    acquire→move_place 相鄰，(2b) 就會對合法案例誤報——判準假設「講不出自己放什麼＝
    接續前一個 acquire」，而這個假設對「本來就不填 object」的 gold 格式不成立。
    屆時要處理的是「(2) 只套 few-shot、不套 gold」或把 gold 的 roles 補齊，**不是**
    加豁免、也不是放寬判準（判準對 few-shot 是對的）。
    """
    violations = [
        f"{gid}: {p}"
        for gid, _text, actions, deps in _gold_plans()
        for p in _adjacent_split_violations(actions, deps)
    ]
    assert violations == [], f"gold 自己就違反切分慣例，慣例的前提要重新確認：{violations}"


def test_guard_catches_the_plan_v11_mis_segmented_shot():
    """負向控制：把 plan-v1.1 那則被換掉的示範原樣放回來，守衛必須抓到。

    同時記錄兩條檢查為何缺一不可——這則壞示範把取與放拆到逗號兩邊，
    子句檢查 (1) **抓不到**（每個子句各只有一種動詞），只有相鄰檢查 (2) 抓得到。
    """
    text = "取一顆螺絲,放入右側治具"
    bad = PlannerOutput.model_validate(
        {
            "language": "zh",
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "acquire",
                    "sequence_order": 1,
                    "roles": {"object": {"text": "螺絲", "status": "explicit"}},
                    "evidence": [{"start": 0, "end": 5, "text": "取一顆螺絲"}],
                },
                {
                    "action_id": "a2",
                    "action_type": "move_place",
                    "sequence_order": 2,
                    "roles": {
                        "object": {"status": "inferred", "action_ref": "a1"},
                        "destination": {"text": "右側治具", "status": "explicit"},
                    },
                    "evidence": [{"start": 6, "end": 12, "text": "放入右側治具"}],
                },
            ],
            "dependencies": [{"from_action": "a1", "to_action": "a2", "type": "same_object"}],
            "unresolved": [],
        }
    )
    # 前提：它在**結構上**完全合法——這正是 25 條結構守衛當初全綠的原因。
    assert validate_planner_output(bad, normalized_text=text) == []
    actions, deps = _as_dicts(bad)
    clause_problems, _checked = _clause_violations(text, actions)
    assert clause_problems == [], (
        "壞示範竟被子句檢查抓到——那 test_guard_catches_clause_level_oversplit "
        "與這條的分工說明要重寫"
    )
    assert _adjacent_split_violations(actions, deps), (
        "plan-v1.1 的壞切分沒被相鄰檢查抓到——守衛是死的"
    )


# 繞過形狀的素材：跨逗號拆開、move_place 不寫自己的 object，於是 action_ref、
# dependency、object.text 三個連結訊號同時落空。`roles_patch` 是 a2 的 roles——
# 兩種寫法（整個省略 / `status: missing`）模型都會產出，規則 4 本身就在教後者。
_LINKLESS_SPLIT_TEXT = "拿取治具蓋板,放置於工作臺"
_LINKLESS_SPLIT_A2_ROLES = [
    pytest.param({"destination": {"text": "工作臺", "status": "explicit"}}, id="object_omitted"),
    pytest.param(
        {
            "object": {"status": "missing"},
            "destination": {"text": "工作臺", "status": "explicit"},
        },
        id="object_missing",
    ),
]


def _linkless_split_output(a2_roles: dict) -> PlannerOutput:
    return PlannerOutput.model_validate(
        {
            "language": "zh",
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "acquire",
                    "sequence_order": 1,
                    "roles": {"object": {"text": "治具蓋板", "status": "explicit"}},
                    "evidence": [{"start": 0, "end": 6, "text": "拿取治具蓋板"}],
                },
                {
                    "action_id": "a2",
                    "action_type": "move_place",
                    "sequence_order": 2,
                    "roles": a2_roles,
                    "evidence": [{"start": 7, "end": 13, "text": "放置於工作臺"}],
                },
            ],
            "dependencies": [],
            "unresolved": [],
        }
    )


@pytest.mark.parametrize("a2_roles", _LINKLESS_SPLIT_A2_ROLES)
def test_guard_catches_linkless_split_with_objectless_move_place(a2_roles: dict):
    """負向控制：「不留連結的拆分」必須被抓到——這是 (2a) 的繞道。

    實測過的繞過路徑：把 few-shot #2 改成這個形狀（正是把 boundary fp 從 15 推到 36
    的那個壞形狀），只有 `test_few_shots_demonstrate_single_action_move_place_cycle`
    會紅，而它紅只是因為 #2 恰好是唯一示範正確循環的那一則；補一則正確示範後
    47 passed 全綠——教錯切分的示範完全隱形。

    這條把「三個連結訊號同時落空」寫成可執行的前提：下面先斷言 (1) 抓不到、
    `_link_between` 是 None，再要求 (2) 抓到。任何一天有人把 (2b) 拿掉，這裡會紅。
    """
    text = _LINKLESS_SPLIT_TEXT
    bad = _linkless_split_output(a2_roles)
    # 前提一：結構完全合法（與 plan-v1.1 那則壞示範一樣，25 條結構守衛不會響）。
    assert validate_planner_output(bad, normalized_text=text) == []
    actions, deps = _as_dicts(bad)
    # 前提二：跨逗號，子句檢查 (1) 抓不到。
    clause_problems, _checked = _clause_violations(text, actions)
    assert clause_problems == []
    # 前提三：三個連結訊號全部落空——(2a) 單獨看不見這個形狀。
    assert _link_between(actions[0], actions[1], deps) is None
    assert _adjacent_split_violations(actions, deps), (
        "不留連結的 acquire→move_place 拆分沒被抓到——守衛可以被繞過"
    )


def test_split_guard_allows_unrelated_acquire_then_move_place():
    """(2b) 的收窄邊界：取工具→放另一件東西是合法的，不得誤報。

    「拿取電動起子,將主板放到治具」是 acquire(工具) + move_place(別的物件)，兩者
    本來就是兩個 action。這條與上一條配成一對：只有「move_place 講不出自己放的是
    什麼」才算違規，判準不是「相鄰就違規」。沒有這條，(2b) 可以靠「一律紅」假裝有效。
    """
    text = "拿取電動起子,將主板放到治具"
    ok = PlannerOutput.model_validate(
        {
            "language": "zh",
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "acquire",
                    "sequence_order": 1,
                    "roles": {"tool": {"text": "電動起子", "status": "explicit"}},
                    "evidence": [{"start": 0, "end": 6, "text": "拿取電動起子"}],
                },
                {
                    "action_id": "a2",
                    "action_type": "move_place",
                    "sequence_order": 2,
                    "roles": {
                        "object": {"text": "主板", "status": "explicit"},
                        "destination": {"text": "治具", "status": "explicit"},
                    },
                    "evidence": [{"start": 7, "end": 14, "text": "將主板放到治具"}],
                },
            ],
            "dependencies": [],
            "unresolved": [],
        }
    )
    assert validate_planner_output(ok, normalized_text=text) == []
    actions, deps = _as_dicts(ok)
    assert _adjacent_split_violations(actions, deps) == [], (
        "取工具→放別的東西被誤判為切錯——判準太寬，會逼出豁免清單"
    )


def test_guard_catches_clause_level_oversplit():
    """負向控制：把 gold 裡「一句取＋放＝一個 move_place」的案例硬切成兩個，(1) 必須紅。

    刻意拿 gold 真案（而不是 few-shot）當素材，兩個理由：這條才不會因為有人動了
    few-shot 就跟著失效；以及「原封不動時是綠的、切成兩個就紅」兩邊都測到，
    才排得掉「檢查恆紅」這種假守衛。（gold 原文只在測試裡當素材，不進 prompt，
    不構成 `test_few_shot_texts_add_no_new_gold_contamination` 擋的那種汙染。）
    """
    subject = next(
        (
            (gid, text, actions)
            for gid, text, actions, _deps in _gold_plans()
            for a in actions
            if a["action_type"] == "move_place"
            and a["evidence"]
            and any(v in a["evidence"][0]["text"] for v in ACQUIRE_VERBS)
            and any(v in a["evidence"][0]["text"] for v in PLACE_VERBS)
        ),
        None,
    )
    assert subject is not None, (
        "gold 裡找不到「一句取＋放＝一個 move_place」的案例——"
        "慣例的前提沒了，這整段守衛都要重新確認"
    )
    gid, text, actions = subject
    clean, checked = _clause_violations(text, actions)
    assert checked >= 1 and clean == [], f"{gid} 原樣就該是綠的，卻得到 {clean}"

    target = next(a for a in actions if a["action_type"] == "move_place")
    ev = target["evidence"][0]
    cut = ev["start"] + len(ev["text"]) // 2
    split = [
        dict(
            target,
            action_id="x1",
            action_type="acquire",
            evidence=[{"start": ev["start"], "end": cut, "text": text[ev["start"] : cut]}],
        ),
        dict(
            target,
            action_id="x2",
            action_type="move_place",
            evidence=[{"start": cut, "end": ev["end"], "text": text[cut : ev["end"]]}],
        ),
    ]
    broken = [a for a in actions if a is not target]
    broken[0:0] = split
    problems, checked = _clause_violations(text, broken)
    assert checked >= 1, "沒有任何子句被檢查——負向控制本身失效"
    assert problems, f"{gid} 的子句被切成兩個 action 竟然沒被抓到——守衛是死的"
