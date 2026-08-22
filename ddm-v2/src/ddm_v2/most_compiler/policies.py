"""Compiler policies（純函數、可版本化、無 IO）。"""
from __future__ import annotations

import math
import re
from typing import Literal

from ddm_v2.nlp.contracts import PlannedAction, WorkInstructionPlan
from ddm_v2.nlp.quantities import ZH_NUM, extract_counts, extract_distances

# 附錄 A2：核心 slot 參數（completeness 判準）
CORE_PARAM_BY_ACTION: dict[str, str] = {
    "acquire": "G",
    "move_place": "P",
    "controlled_move": "M",
    "process": "X",
    "inspect": "I",
    # release_return：放開→P；歸位當 move_place（compile 內細分）
    "release_return": "P",
}

SEQ_BY_ACTION: dict[str, str] = {
    "acquire": "GM",
    "move_place": "GM",
    "release_return": "GM",
    "controlled_move": "CM",
    "process": "CM",
    "inspect": "CM",
}

# ── S-2：無憑據數值旗標（EvidencedValuePolicyV1）─────────────────────────────
#
# 病灶：`RoleValue` 的數值（distance／quantity）是**模型的主張**，而 compiler
# 先前直接把它當觀測值餵給 TMU 檔位——distance→A 參數／M 分量，quantity→
# frequency（乘數）。`contracts.validate_planner_output` 的證據綁定擋不住這條路
# （只在 `status=="explicit"` **且** `role.text is not None` 才驗，且比對是雙向
# 子字串），實測三種形狀可零憑據直達 TMU：value-only 的 explicit、role.text 為
# evidence 超集、`inferred`＋合法 `action_ref`。
#
# **取捨：採用值但掛旗標，不靜默改值。** 丟掉無憑據的距離＝改用 0cm，那同樣是
# 憑空的數字（而且是往低估方向，錯誤的工時標準照樣流向 LineBalance），並且會
# 改變既有案例的 TMU＝改計算語意（需 IE 裁決）。S-2 的病是**靜默**不是數字本身：
# 旗標讓覆核者看得到，並顯式擋掉 auto（覆核者不看也不會自動落地）。要改成
# 「拒收」是 IE 級決策，不在本票範圍。
#
# ⚠️ **不要把這個判準說成「無憑據數值一律 fail-closed」。** 它實際問的是
# 「該 action 的 evidence 窗內找不找得到**相同的量**」（判準見
# `numeric_claim_is_evidenced`）——比對的是數，不是「這個數該不該是這個角色的
# 值」。已知穿得過去的形狀：同窗內兩個距離互相背書（A0／A3 對調）、捏造值恰好
# 等於窗內同 kind 的真實量。另外 `process_kind` 的秒數（`compile.py` 讀它、交給
# 引擎換算工時）**完全不經過這個判準**——同一種病的第三條路，另票處理。
DISTANCE_UNEVIDENCED_REVIEW = "distance_unevidenced_review"
QUANTITY_UNEVIDENCED_REVIEW = "quantity_unevidenced_review"

# 非有限值（NaN／±Infinity）在 compiler 邊界一律**拒收**（＝當作沒有值），
# 並留下這個旗標。它與 `*_unevidenced_review` 是不同的主張：那兩個說「數字沒有
# 出處」（值仍採用），這個說「這根本不是數量，已經被丟掉」。
#
# 為什麼是拒收而不是「照用＋掛旗標」（與 S-2 的取捨相反）：非有限值不是一個
# 過大或沒出處的**量**，它是「沒有量」。而且 NaN 會讓每個比較都是 False——
# 引擎的檔位查表（`most_engine` 的 `band_index`）因此一路落到溢位帶＝**最大** A
# 檔位（實測 `reach_cm=nan` → A24／30 TMU），`+Inf` 同樣落最大檔；nan 秒數
# 更直接讓引擎算出 nan 的 TMU 總計（非合規 JSON），inf 秒數讓 Decimal 丟
# `InvalidOperation`。放行等於讓「不是數量」變成**最貴的檔位**或 500。
NON_FINITE_VALUE_REJECTED = "non_finite_value_rejected"

_VALUE_TOL = 1e-6
_DIGITS_RE = re.compile(r"\d+(?:\.\d+)?")


def finite_or_reject(value: float | None, reasons: list[str]) -> float | None:
    """有限值原樣回；`NaN`／`±Inf` 回 None 並把 `non_finite_value_rejected` 記進 reasons。

    數值角色進 TMU 之前的**共用**有限值關卡（distance／quantity／process 秒數）。
    拒收要留痕：靜默丟掉一個值和靜默採用一個值一樣不可觀測。
    """
    if value is None or math.isfinite(value):
        return value
    if NON_FINITE_VALUE_REJECTED not in reasons:
        reasons.append(NON_FINITE_VALUE_REJECTED)
    return None


def _overlaps_evidence(action: PlannedAction, start: int, end: int) -> bool:
    """[start,end) 是否與本 action 的任一 evidence span 重疊（半開區間）。"""
    return any(not (end <= ev.start or start >= ev.end) for ev in action.evidence)


# ── 路徑 (2)：evidence 窗內的「帶單位數字」──────────────────────────────────
#
# 只判斷**像不像**該 kind 的單位，不做換算（換算是 `quantities.UNIT_TO_CM` 的
# 事）。這份表刻意比它寬：路徑 (2) 存在的理由就是接住抽取器漏掉的寫法（「厘米」
# 「三支」「16 pcs」「十六顆」）。
#
# 為什麼一定要「數字＋相稱單位」而不是裸數字：裸數字版實測會被本行日常詞彙誤觸
# ——`十字起子`（十→10）替捏造的 `10cm` 背書、`一體成型` 替 `1cm`、`3顆螺絲`
# 用**件數**替**距離**背書（跨 kind）、`45cm` 反過來替 `count=45` 背書。
# 「十字起子」是產線標準詞（前端 `ADistanceSelector.tsx` 就有），不是構造出來的例子。
#
# ⚠️ **這張表只認得「像不像距離單位」，不認得量級**——所以它**不得**收錄與 cm
# 不同量級、而且 `quantities.UNIT_TO_CM` 又抽不出來的單位。原因是分工：抽取器
# 認得的單位（cm／mm／毫米／公分／吋／英寸／inch）會進 `in_window`，由**矛盾
# 檢查**擋下量級錯誤（F3：`450mm` vs 主張 `450cm`）；抽取器不認得的單位進不了
# `in_window`，這裡就只剩裸數字比對、完全不看量級——`走3公尺至料架` ＋ 模型主張
# `3 unit="cm"`（差 **100 倍**）會靜默通過，與 F3 同構。
# 因此 `公尺`／`米`／`尺`／`公厘` 已移除，落回「無憑據→掛旗標」（fail-closed）。
# **它們現在會保守誤報，那是刻意的**：多一個覆核旗標，換掉一條靜默的 100 倍錯誤。
# `厘米` 保留——它等於 cm，量級相同，沒有這個問題。
# 正解是擴充 `quantities.UNIT_TO_CM` 讓抽取器認得這些單位（矛盾檢查就自動涵蓋
# 它們），那是另一票；在這裡補一張量級表等於重建一個抽取器。
_DISTANCE_UNIT_RE = re.compile(
    r"(公分|厘米|毫米|英寸|inches|inch|cm|mm|吋)", re.IGNORECASE
)
_COUNT_UNIT_RE = re.compile(
    r"(顆|件|個|次|支|片|條|根|台|組|套|張|塊|隻|只|枚|粒|盒|包|排|對|雙"
    r"|pcs|pc|sets|set|units|unit|times|time)",
    re.IGNORECASE,
)

# 中文數字：`quantities._COUNT_RE` 的中文分支只吃**單字元**，所以「十六顆」
# 「二十顆」抽不出來（實測 `quantity=16` ＋原文「十六顆」會被誤掛旗標）。
# 這裡自己組合 1–99，**只用於證據佐證**——不改 `quantities.py` 是因為那支的產出
# 會變成角色值／進 TMU，而這裡只回答「文字裡有沒有這個數」。
_ZH_DIGITS = {ch: n for ch, n in ZH_NUM.items() if n < 10}
_ZH_NUM_TOKEN_RE = re.compile("[" + "".join(ZH_NUM) + "]+")


def _zh_token_to_int(token: str) -> int | None:
    """「六」「十」「十六」「二十」「二十五」→ int（1–99）；其餘（「一二三」）回 None。"""
    if "十" not in token:
        return _ZH_DIGITS.get(token)  # 單字才算數；「一二三」不是一個數
    head, _, tail = token.partition("十")
    if "十" in tail:
        return None
    h = 1 if head == "" else _ZH_DIGITS.get(head)
    t = 0 if tail == "" else _ZH_DIGITS.get(tail)
    if h is None or t is None:
        return None
    return h * 10 + t


def _count_hit_value(hit_start: int, hit_value: float, normalized_text: str) -> float:
    """修回被 `_COUNT_RE` 單字元分支**截斷**的中文數量（「十六顆」只吃到「六顆」＝6）。

    F1：`quantities._COUNT_RE` 的中文分支只吃一個字，所以「十六顆」抽出 6、
    「二十顆」抽出 10。這個錯值有兩個後果：正確的 `quantity=16` 被判成與原文
    矛盾（誤掛旗標），而錯誤的 `quantity=6` 反而被背書。往左把完整的中文數字
    token 補回來再解析，兩邊同時修好。

    不改 `quantities._COUNT_RE` 本身：那支的產出是**抽取值**（未來會變成角色值／
    進 TMU），改它的語意與 span 屬另一票；這裡只影響「文字裡有沒有這個數」的判讀。
    """
    if hit_start >= len(normalized_text) or normalized_text[hit_start] not in ZH_NUM:
        return hit_value  # 阿拉伯數字／`×N` 分支不會被截斷
    start = hit_start
    while start > 0 and normalized_text[start - 1] in ZH_NUM:
        start -= 1
    if start == hit_start:
        return hit_value
    repaired = _zh_token_to_int(normalized_text[start : hit_start + 1])
    return float(repaired) if repaired is not None else hit_value


def _evidence_windows(action: PlannedAction, normalized_text: str) -> list[str]:
    """本 action 的 evidence 窗**從 `normalized_text` 切出來**的文字。

    刻意不讀 `ev.text`：那是模型給的字串，而 span 是可推導的座標——
    `contracts.repair_evidence_offsets` 的原則原話是「text 是可驗證的資料、
    offset 是可推導的座標，能推就不要信它算的」。讀 `ev.text` 會讓這個守衛倚賴
    `validate_planner_output`（`evidence_text_mismatch`）維持的不變量，而
    `compile_plan` 自己不驗它——實測 `ev.text="推動治具450公分"` 搭配
    `normalized_text="推動治具"` 可讓捏造值取得背書。守衛要自足。

    越界的 span 直接略過（＝空窗，fail-closed），不拋例外：切不出來就等於沒有
    可定位的文字。
    """
    out: list[str] = []
    for ev in action.evidence:
        if 0 <= ev.start < ev.end <= len(normalized_text):
            out.append(normalized_text[ev.start : ev.end])
    return out


def _quantities_in_own_evidence(
    action: PlannedAction, normalized_text: str, kind: Literal["distance", "count"]
) -> set[float]:
    """本 action **自己**的 evidence 窗內、**後面緊跟相稱單位**的數字。

    單位必須緊跟在數字之後（只容許空白）——這既是「這是一個獨立的量」的判準，
    也是 kind 的判準：`3顆` 不替距離背書，`45cm` 不替件數背書。
    """
    unit_re = _DISTANCE_UNIT_RE if kind == "distance" else _COUNT_UNIT_RE
    out: set[float] = set()
    for text in _evidence_windows(action, normalized_text):
        for m in _DIGITS_RE.finditer(text):
            if unit_re.match(text, _skip_spaces(text, m.end())):
                out.add(float(m.group(0)))
        for m in _ZH_NUM_TOKEN_RE.finditer(text):
            n = _zh_token_to_int(m.group(0))
            if n is not None and unit_re.match(text, _skip_spaces(text, m.end())):
                out.add(float(n))
    return out


def _skip_spaces(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in " \t\u3000":
        pos += 1
    return pos


def numeric_claim_is_evidenced(
    action: PlannedAction,
    plan: WorkInstructionPlan,
    *,
    value: float,
    kind: Literal["distance", "count"],
) -> bool:
    """這個數值**在本 action 的 evidence 窗內找不找得到相同的量**。

    ⚠️ 判準的實際語意就是上面這句，**不是**「無憑據的數值一律 fail-closed」。
    它比對的是「數」，不是「這個數該不該是這個角色的值」——同窗內的兩個距離
    可以互相背書（A0／A3 對調照樣通過）。宣稱得比實情強會誤導覆核者。

    判定順序：

    1. `extract_distances`／`extract_counts` 抽到**同一數量**且 span 與本 action
       的 evidence **重疊** → 有憑據（帶單位的正字標記）。
    2. **矛盾檢查**：同窗內抽到了同 kind 的量、但沒有一個對得上 → 直接判
       **無憑據**，不走下面的退路。這條是為了 mm↔cm 單位混淆——原文
       「推動治具450mm至定位」＋模型 `value=450 unit="cm"` ＝真值 45cm 的 10 倍
       （跨好幾個 A 檔位）。路徑 (1) 其實已經在同一窗抽到 45.0，把它救回去的
       正是裸數字退路。單位正規化是 LLM 最常見的數值錯誤形態，不是只有攻擊者
       才會做。
    3. 退路：該數字**帶著相稱單位**出現在本 action 的 evidence 窗內
       （`_quantities_in_own_evidence`）——抽取器漏掉的寫法（「45厘米」「三支」
       「十六顆」）。要求單位緊跟，才不會被「十字起子」「一體成型」這類本行
       日常詞彙誤觸，也才不會讓件數替距離背書。

    無 evidence span 的 action 一律回 False（fail-closed）——沒有可定位的窗，
    就沒有「定位得到」這回事。正常管線不會有這種 action（`sanitize_planner_output`
    會把無 evidence 的非 composite action 剔為 `planner_invented_action`）。

    非有限值同樣回 False，而且這一行是**承重**的：`abs(nan - x) > tol` 恆為
    False，少了它，下面的比對不會排除 NaN，只要句面有任一距離與 evidence
    重疊就會回 True——NaN 反而變成「有憑據」。呼叫端已先用 `finite_or_reject`
    拒收（compiler 邊界），這裡是第二道，不倚賴呼叫端。
    """
    if not math.isfinite(value):
        return False
    hits = (
        extract_distances(plan.normalized_text)
        if kind == "distance"
        else extract_counts(plan.normalized_text)
    )
    in_window = [h for h in hits if _overlaps_evidence(action, h.start, h.end)]
    for hit in in_window:
        measured = (
            hit.normalized_cm
            if kind == "distance"
            else _count_hit_value(hit.start, hit.value, plan.normalized_text)
        )
        if measured is not None and abs(measured - value) <= _VALUE_TOL:
            return True
    if in_window:
        # (2) 矛盾：窗內有同 kind 的量卻沒有一個對得上——主張與原文不符，
        # 不得再用裸數字／同數字的其他寫法把它救回來
        return False
    return any(
        abs(n - value) <= _VALUE_TOL
        for n in _quantities_in_own_evidence(action, plan.normalized_text, kind)
    )


def is_tool_held(
    action: PlannedAction,
    plan: WorkInstructionPlan,
) -> bool:
    """明示 tool_ref／tool_held_for／same_object／uses_tool → G 可留空（已持有＝0 TMU）。

    不依「較早有 acquire」自行推斷（附錄 A2：需 dependency／同物件證據）。
    """
    if action.roles.get("tool_ref") and action.roles["tool_ref"].action_ref:
        return True
    for dep in plan.dependencies:
        if dep.to_action != action.action_id:
            continue
        if dep.type in {"tool_held_for", "same_object", "uses_tool"}:
            prior = next((a for a in plan.actions if a.action_id == dep.from_action), None)
            if prior and prior.action_type == "acquire" and prior.sequence_order < action.sequence_order:
                return True
    return False


def resolve_frequency(action: PlannedAction, plan: WorkInstructionPlan) -> tuple[float, list[str]]:
    """QuantityPolicyV1：保守——quantity 掛在 process/move_place → frequency=N + review。

    其餘情境 frequency=1＋quantity_policy_review（若有 quantity）。

    S-2：`quantity.value` 是 frequency（＝TMU 乘數）的唯一輸入，與 distance 同病
    ——模型主張的數字直達 TMU。無法在本 action 的文字證據定位到該數量時，**照樣
    採用**（不靜默改成 1，理由同 `DISTANCE_UNEVIDENCED_REVIEW`）但加掛
    `quantity_unevidenced_review`：`quantity_policy_review` 講的是「N 該不該當
    frequency」，這一條講的是「N 有沒有出處」，兩個主張不同，不能合成一個。
    """
    reasons: list[str] = []
    qty = action.roles.get("quantity")
    n: float | None = None
    if qty is not None and qty.value is not None:
        try:
            n = float(qty.value)
        except (TypeError, ValueError):
            n = None
    # 有限值關卡必須在 `n <= 0` **之前**：`nan <= 0` 是 False，會一路走到下面的
    # `int(n)` 丟 `ValueError`（`inf` 則是 `OverflowError`）。那個拋出點在
    # `compile_plan` 裡，而 `wi_ai_service` 的 try/except 只包 LLM 呼叫、
    # `routes/v2/nl_draft.py` 只接 `RuleSetNotFound`／`RuntimeError` → HTTP 500。
    n = finite_or_reject(n, reasons)
    if n is None or n <= 0:
        return 1.0, reasons
    reasons.append("quantity_policy_review")
    if not numeric_claim_is_evidenced(action, plan, value=n, kind="count"):
        reasons.append(QUANTITY_UNEVIDENCED_REVIEW)
    if action.action_type in {"process", "move_place"} and n == int(n):
        return float(int(n)), reasons
    return 1.0, reasons


def holding_inferred_reason(
    action: PlannedAction,
    plan: WorkInstructionPlan,
) -> bool:
    return is_tool_held(action, plan) and action.action_type == "move_place"
