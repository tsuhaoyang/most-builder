"""敘事（中英雙語）：E6 display_rule 三態、A_move 手度翻轉、repeat ×N（純函數，免 DB）。

三層斷言，各擋一種迴歸：

1. **中文字面**（`test_zh_*`）——ADR-032 I2：中文輸出不得因英文化而改變。這裡刻意
   綁字面字串，因為要守的性質就是「一個字都不能動」。
2. **雙語語意不變式**（`test_both_*`，`locale ∈ {zh, en}` 參數化）——ADR-032 D8：
   兩套樣板＝兩份維護面積，未來改一條敘事規則（例如再加一個 `display_rule` 值）
   很可能只改中文那套。斷言綁在**結構性質**（可見詞出現/不出現/出現幾次）而非字面
   用詞上，所以英文換個說法不會假紅，但只改一邊會缺一項不變式而真紅。
3. **英文字面**（`test_en_adr_case_*`）——ADR-032 D7.4 的四個語序案例是 ADR 明文給的
   期望輸出，可以也應該逐字斷言。
"""
from __future__ import annotations

import re
from typing import get_args

import pytest

from ddm_v2.most_engine.narrative import build_narrative
from ddm_v2.most_engine.narrative_en import build_narrative_en
from ddm_v2.schemas.v2.rule_set_options import PAddonIn

pytestmark = pytest.mark.unit

LABELS = {
    "g": {"g_grasp": {"label": "抓握", "sentence": "抓握",
                      "label_en": "Grasp", "sentence_en": "grasp"}},
    "p_base": {"p_place_none": {"label": "放(無方向)", "sentence": "放",
                                "label_en": "Place (no direction)", "sentence_en": "place it"},
               "p_hold": {"label": "保持住", "sentence": "保持住",
                          "label_en": "Hold in place", "sentence_en": "hold it in place"}},
    "p_addon": {
        "a_align": {"label": "對準(精度<4mm)", "sentence": "對準",
                    "label_en": "Align (precision <4mm)", "sentence_en": "aligned to within 4 mm",
                    "display_rule": "prefix_visible_term"},
        "a_insert": {"label": "插入", "sentence": "插入",
                     "label_en": "Insert", "sentence_en": "insert it", "display_rule": "show_self"},
        "a_snap": {"label": "卡合", "sentence": "卡合",
                   "label_en": "Snap fit", "sentence_en": "snap it into place", "display_rule": "show_self"},
        "a_hard": {"label": "較難處理", "sentence": "",
                   "label_en": "Difficult to handle", "sentence_en": "", "display_rule": "hidden"},
        "a_press": {"label": "施加壓力", "sentence": "",
                    "label_en": "Apply pressure", "sentence_en": "", "display_rule": "hidden"},
    },
    # `m_hand`／`m_foot` 照**真實 DB 形狀**給：`sentence_text_zh` 是 NULL、`sentence_text_en`
    # 是空字串、兩語標籤都有值。少了這兩條就驗不到「不入句」——`_sent()` 的回退鏈
    # （句面→標籤，英文再退中文）一被走到就會把「手度」／"Hand turn" 漏進句子。
    "m_verb": {"m_push": {"label": "推", "sentence": "推",
                          "label_en": "Push", "sentence_en": "push it",
                          "pricing_kind": "ladder"},
               "m_hand": {"label": "手度", "sentence": None,
                          "label_en": "Hand turn", "sentence_en": "",
                          "pricing_kind": "hand"},
               "m_foot": {"label": "腳步", "sentence": None,
                          "label_en": "Foot step", "sentence_en": "",
                          "pricing_kind": "foot"}},
    # `x_none`／`i_none` 照**真實 DB 形狀**給（V2 實測）：句面兩語皆空、標籤兩語皆有值。
    # 少了這兩條，「哨兵不入句」的斷言就是空頭——守衛拿掉後 `_sent(None)` 仍回 ""，
    # 突變測試四個變體全部存活（2026-08-19 實測）。有了這兩條，回退鏈
    # （句面→標籤／英文再退中文）一被走到就會把標籤漏進句子。
    "x": {"x_press": {"label": "並壓合機台", "sentence": "並壓合機台",
                      "label_en": "Press-fit machine", "sentence_en": "press-fitting on the machine"},
          "x_none": {"label": "無機台等待", "sentence": None,
                     "label_en": "No machine wait", "sentence_en": ""}},
    "i": {"i_check": {"label": "並檢查(正常視線範圍)", "sentence": "並檢查",
                      "label_en": "Check (normal vision)", "sentence_en": "checked"},
          "i_none": {"label": "不額外對齊", "sentence": None,
                     "label_en": "No additional alignment", "sentence_en": ""}},
}
VOCAB = {"object": "主板", "from": "料架", "to": "治具", "hand": "右手"}
# 英文 vocab 的 hand 給的是**原始代碼**（祈使句前綴），不是顯示字串——見 narrative_en 檔頭。
VOCAB_EN = {"object": "Main board", "from": "Rack", "to": "Test fixture", "hand": "RH"}

# 「同一個東西的兩種說法」：不變式斷言查的詞，逐語系各給一個。
TERMS = {
    "object": {"zh": "主板", "en": "main board"},
    "from": {"zh": "料架", "en": "rack"},
    "to": {"zh": "治具", "en": "test fixture"},
    "a_hard": {"zh": "較難處理", "en": "Difficult to handle"},
    "a_press": {"zh": "施加壓力", "en": "Apply pressure"},
    "a_align": {"zh": "對準", "en": "aligned to within 4 mm"},
    "m_hand": {"zh": "手度", "en": "Hand turn"},
    "m_foot": {"zh": "腳步", "en": "Foot step"},
}
LOCALES = ("zh", "en")


def render(locale: str, cycle: dict) -> str:
    if locale == "zh":
        return build_narrative(cycle, LABELS, VOCAB)
    return build_narrative_en(cycle, LABELS, VOCAB_EN)


def render_with(locale: str, cycle: dict, **vocab_overrides) -> str:
    """`render()` 的可覆寫 vocab 版：空白邊界要餵髒詞彙名，兩語各自的 vocab 基底不同。"""
    base = VOCAB if locale == "zh" else VOCAB_EN
    vocab = dict(base, **vocab_overrides)
    if locale == "zh":
        return build_narrative(cycle, LABELS, vocab)
    return build_narrative_en(cycle, LABELS, vocab)


def occurrences(text: str, term: str) -> int:
    """大小寫不敏感——英文樣板會把受詞降格（Main board → the main board），
    語意不變式不該因為這種呈現層細節而紅。"""
    return text.lower().count(term.lower())


def _gm_cycle(p_addons=None, twist=0, p_repeat=None, p_base="p_place_none"):
    p5 = {"p_base_code": p_base, "p_addon_codes": p_addons or []}
    if p_repeat:
        p5["repeat_count"] = p_repeat
    return {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25, "twist_deg": twist}, "p5": p5}


def _cm_cycle(**overrides):
    cm = {"seq": "CM", "a0": {"reach_cm": 25}, "g2": {"g_code": "g_grasp"},
          "m3": {"m_components": [{"verb_code": "m_push"}], "repeat_count": 16},
          "x4": {"x_code": "x_press"}, "i5": {"i_code": "i_check"}}
    cm.update(overrides)
    return cm


# ── 1. 中文字面（I2：位元級不變）────────────────────────────────────

def test_zh_p_show_self_replaces_base():
    s = build_narrative(_gm_cycle(["a_insert"]), LABELS, VOCAB)
    assert "「插入」放置" in s and "「放」" not in s


def test_zh_p_prefix_align():
    s = build_narrative(_gm_cycle(["a_align", "a_insert"]), LABELS, VOCAB)
    assert "「對準插入」放置" in s


def test_zh_p_hidden_not_in_sentence():
    s = build_narrative(_gm_cycle(["a_hard"]), LABELS, VOCAB)
    assert "較難處理" not in s and "「放」放置" in s


def test_zh_a_move_twist_inserts_flip():
    s = build_narrative(_gm_cycle(twist=90), LABELS, VOCAB)
    assert "翻轉「主板」" in s


def test_zh_repeat_suffix():
    s = build_narrative(_gm_cycle(p_repeat=3), LABELS, VOCAB)
    assert "放置×3" in s


def test_zh_cm_x_i_sentences_and_none_skipped():
    s = build_narrative(_cm_cycle(), LABELS, VOCAB)
    assert "以推×16實施移動" in s and "並壓合機台" in s and "並檢查" in s
    s2 = build_narrative(
        _cm_cycle(x4={"x_code": "x_none"}, i5={"i_code": "i_none"}, m3={"m_components": []}),
        LABELS, VOCAB)
    assert "並壓合機台" not in s2 and "並檢查" not in s2


# ── 2. 雙語語意不變式（D8：防止中英樣板漂移）──────────────────────

# `display_rule` 的**值域權威**＝ schema 的 `Literal`（DB 的
# `ck_rule_p_addons_ck_rule_p_addons_display_rule` 與之逐字一致）。從權威取值而不是
# 在測試裡再抄一份清單，是為了讓「新增第四個值」這件事無法只發生在一邊：
# 值一加，下面那條測試就多出一組參數，缺 fixture 或缺行為斷言都會紅（D8）。
DISPLAY_RULES = sorted(get_args(PAddonIn.model_fields["display_rule"].annotation))

# base 一律取 `p_hold`：`p_place_none` 的中文句面「放」是樣板固定字「放置」的子字串，
# 用它當 base 會讓「base 已被取代」的斷言假紅（同 test_both_show_self_replaces_base_verb）。
_BASE_CODE = "p_hold"


def _visible_terms(entry: dict, locale: str) -> list[str]:
    """該選項在 locale 下**任何**可能被寫進句子的字串（句面優先，句面空則看標籤）。

    hidden 的兩條 addon 句面刻意是空字串——只查句面等於查空字串（`str.count("")`
    恆為正），必須連標籤一起查，因為 `_sent()` 的回退鏈在句面空時就是拿標籤頂上。
    """
    keys = ("sentence", "label") if locale == "zh" else ("sentence_en", "label_en")
    return [entry[k] for k in keys if entry.get(k)]


def _expect_hidden(locale: str, out: str, addon: dict) -> None:
    """只計 TMU、不入句；base 動詞原樣留著。"""
    for term in _visible_terms(addon, locale):
        assert occurrences(out, term) == 0, f"hidden 的可見詞 {term!r} 入句了：{out}"
    assert occurrences(out, _visible_terms(LABELS["p_base"][_BASE_CODE], locale)[0]) == 1, out


def _expect_show_self(locale: str, out: str, addon: dict) -> None:
    """取代 base 動詞：addon 的可見詞出現一次、base 的不再出現。"""
    assert occurrences(out, _visible_terms(addon, locale)[0]) == 1, out
    assert occurrences(out, _visible_terms(LABELS["p_base"][_BASE_CODE], locale)[0]) == 0, (
        f"show_self 應取代 base 動詞：{out}")


def _expect_prefix_visible_term(locale: str, out: str, addon: dict) -> None:
    """修飾 base 而**不**取代它：兩者各出現一次（位置中英不同，刻意不斷言位置）。"""
    assert occurrences(out, _visible_terms(addon, locale)[0]) == 1, out
    assert occurrences(out, _visible_terms(LABELS["p_base"][_BASE_CODE], locale)[0]) == 1, (
        f"prefix_visible_term 不該取代 base 動詞：{out}")


DISPLAY_RULE_BEHAVIOUR = {
    "hidden": _expect_hidden,
    "show_self": _expect_show_self,
    "prefix_visible_term": _expect_prefix_visible_term,
}


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("rule", DISPLAY_RULES)
def test_both_every_display_rule_has_defined_bilingual_behaviour(locale, rule):
    """D8 的機械化守門：`display_rule` 的**每一個**合法值，中英兩套樣板都有行為斷言。

    這條測試刻意把「值域完備性」與「行為覆蓋」綁成同一條——不是先 `assert covered ==
    declared` 再另外寫死幾條斷言。分開寫會留一個中間態：作者被完備性檢查逼著補了
    fixture，卻沒補行為斷言，測試轉綠而新規則其實只有中文那套實作。這裡缺任一邊都紅。

    新增第四個 `display_rule` 值時要做的事：`LABELS["p_addon"]` 補一條該規則的選項，
    `DISPLAY_RULE_BEHAVIOUR` 補一個描述「它在中英兩套樣板各自怎麼影響可見詞」的函式。
    """
    code = next((c for c, a in LABELS["p_addon"].items() if a["display_rule"] == rule), None)
    check = DISPLAY_RULE_BEHAVIOUR.get(rule)
    assert code is not None and check is not None, (
        f"display_rule={rule!r} 是合法值（schemas/v2/rule_set_options.py 的 Literal）"
        f"但本檔沒有它的 fixture 選項（{code!r}）或雙語行為斷言（{check!r}）——"
        "只改中文樣板的變更會因此完全不被察覺，違反 ADR-032 D8"
    )
    check(locale, render(locale, _gm_cycle([code], p_base=_BASE_CODE)), LABELS["p_addon"][code])


@pytest.mark.parametrize("locale", LOCALES)
def test_both_hidden_addon_never_appears(locale):
    """`display_rule='hidden'` 的 addon 只計 TMU、不入句——兩語皆然。

    **兩個 hidden addon 都要斷言**：只查其中一個時，「hidden 被當成 show_self」
    這個迴歸會被後一個 addon 覆蓋掉前一個而逃過檢查（突變測試實測會綠）。
    """
    out = render(locale, _gm_cycle(["a_hard", "a_press"]))
    for code in ("a_hard", "a_press"):
        assert occurrences(out, TERMS[code][locale]) == 0, f"{locale} 的 {code} 不該入句"


@pytest.mark.parametrize("locale", LOCALES)
def test_both_prefix_visible_term_appears_exactly_once(locale):
    """`prefix_visible_term` 的可見詞出現且僅出現一次。

    **位置刻意不斷言**：中文是前綴（「以『對準插入』放置」）、英文是後綴
    （"insert it, aligned to within 4 mm"）——同一個欄位值在兩套樣板被解讀成不同
    位置，正是 ADR-032 D7.3.2 的重點。綁位置會把這個設計判定成 bug。
    """
    out = render(locale, _gm_cycle(["a_align", "a_insert"]))
    assert occurrences(out, TERMS["a_align"][locale]) == 1


@pytest.mark.parametrize("locale", LOCALES)
def test_both_show_self_replaces_base_verb(locale):
    """show_self 取代 base 動詞：base 的可見詞不再出現，addon 的出現。

    base 取 `p_hold`（保持住）而非 `p_place_none`：後者的中文句面是單字「放」，
    它是中文樣板固定字「放置」的子字串——base 明明已被取代，子字串比對仍會命中，
    測試會為了一個呈現層巧合而假紅。
    """
    out = render(locale, _gm_cycle(["a_snap"], p_base="p_hold"))
    base = LABELS["p_base"]["p_hold"]
    addon = LABELS["p_addon"]["a_snap"]
    key = "sentence" if locale == "zh" else "sentence_en"
    assert occurrences(out, addon[key]) == 1
    assert occurrences(out, base[key]) == 0


@pytest.mark.parametrize("locale", LOCALES)
def test_both_repeat_marker_appears_once(locale):
    """`repeat_count=N` 在兩語輸出各出現一次重複標記（中文 `×3`／英文 `(×3)`，
    共同的可斷言核心是 `×3`）。"""
    out = render(locale, _gm_cycle(p_repeat=3))
    assert out.count("×3") == 1


@pytest.mark.parametrize("locale", LOCALES)
def test_both_vocab_object_from_to_all_present(locale):
    """物件名／來源／目的地在兩語輸出中皆出現。"""
    out = render(locale, _gm_cycle())
    for key in ("object", "from", "to"):
        assert occurrences(out, TERMS[key][locale]) >= 1, f"{locale} 少了 {key}"


@pytest.mark.parametrize("locale", LOCALES)
def test_both_twist_mentions_the_object(locale):
    """A_move 帶手度 → 句中出現翻轉語，且點名受詞（v3 dependency 規則）。"""
    plain = render(locale, _gm_cycle())
    twisted = render(locale, _gm_cycle(twist=90))
    assert len(twisted) > len(plain)
    assert occurrences(twisted, TERMS["object"][locale]) > occurrences(plain, TERMS["object"][locale])


@pytest.mark.parametrize("locale", LOCALES)
def test_both_cm_x_and_i_present_and_none_skipped(locale):
    """CM 的 X／I 有值時入句；`x_none`／`i_none` 一律不入句（不得回退成標籤）。"""
    key = "sentence" if locale == "zh" else "sentence_en"
    x_term = LABELS["x"]["x_press"][key]
    i_term = LABELS["i"]["i_check"][key]
    out = render(locale, _cm_cycle())
    assert occurrences(out, x_term) == 1 and occurrences(out, i_term) == 1

    none_out = render(locale, _cm_cycle(x4={"x_code": "x_none"}, i5={"i_code": "i_none"}))
    assert occurrences(none_out, x_term) == 0
    assert occurrences(none_out, i_term) == 0
    # **查哨兵自己的標籤**：`x_none`／`i_none` 在真實 DB 是「句面空、標籤有值」，
    # 所以不入句只能靠哨兵守衛達成——守衛一失守，`_sent()` 的回退鏈就會拿標籤當句面，
    # 句子裡冒出「無機台等待」／"No additional alignment"。
    # （查 `i_check` 的標籤是恆真的：這個 cycle 的 `i_code` 本來就不是它。）
    lbl = "label" if locale == "zh" else "label_en"
    assert occurrences(none_out, LABELS["x"]["x_none"][lbl]) == 0, none_out
    assert occurrences(none_out, LABELS["i"]["i_none"][lbl]) == 0, none_out


# M 的伴隨維度（`pricing_kind` ∈ {hand, foot}）不入句。
#
# 為什麼還要測「只有伴隨維度」這種輸入——引擎已經用 `M_COMPANION_WITHOUT_VERB` 擋掉它了：
# 歷史 `most_cycles.slot_inputs` 裡就有這種列（回放鐵則下不改資料，實測 2 筆），而敘事
# 仍有多條**重新產生**的路徑會吃到它：motion module 版本讀取時即時組句（該表沒有
# `narrative_en` 欄位）、日後的敘事重算腳本。這些路徑產出的 M 子句必須整段消失，
# 而不是長出一句「以手度實施移動」——那句話宣稱有移動，但那一格是 0 TMU。
# （worksheet 的 `narrative_zh`／`narrative_en` 是**存檔時**落盤的快照、讀取不重算，
#  所以那 2 筆既有列的舊敘事不會自動消失；清理要靠獨立的重算腳本，見 ADR-032 D7.6。）

# 標點：子句之間才有分隔符，句首不得有（既有缺陷，D7.6 之後這條路更常被走到）。


@pytest.mark.parametrize("locale", LOCALES)
def test_both_cm_clause_has_no_leading_separator(locale):
    """CM 第二句沒有地點、也沒有 M 動詞時，第一個子句前面不得留分隔符。

    中文舊寫法逐句 `s += "，" + 子句`，於是吐出「…伸手約25公分。，並壓合機台，並檢查。」；
    英文一開始就是 `parts` list ＋ join，沒有這個問題——本條把兩語釘在同一個形狀（R3）。
    """
    cyc = _cm_cycle(m3={"m_components": [{"verb_code": "m_hand", "angle_deg": 0}]})
    out = render_with(locale, cyc, to="")
    assert "。，" not in out and ". ," not in out, out
    # 子句本身照常出現（不是靠整段消失來過關）
    assert occurrences(out, LABELS["x"]["x_press"]["sentence" if locale == "zh" else "sentence_en"]) == 1


@pytest.mark.parametrize("locale", LOCALES)
def test_both_cm_clause_absent_leaves_no_empty_sentence(locale):
    """整個 CM 子句都沒有內容（無地點／無動詞／X、I 皆哨兵）→ 不得留下空句子。"""
    cyc = _cm_cycle(m3={"m_components": []}, x4={"x_code": "x_none"}, i5={"i_code": "i_none"})
    out = render_with(locale, cyc, to="")
    assert "。。" not in out and ".." not in out, out
    assert "。，" not in out and ". ," not in out, out


M_COMPANION_ONLY = [
    pytest.param([{"verb_code": "m_hand", "angle_deg": 0}], "m_hand", id="hand"),
    pytest.param([{"verb_code": "m_foot", "distance_cm": 0}], "m_foot", id="foot"),
]


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("comps,code", M_COMPANION_ONLY)
def test_both_m_companion_only_produces_no_move_clause(locale, comps, code):
    """只有伴隨維度時，M 子句整段不出現（兩語皆然），其餘子句原封不動。"""
    out = render(locale, _cm_cycle(m3={"m_components": comps}))
    assert occurrences(out, TERMS[code][locale]) == 0, f"{locale} 的 {code} 不該入句：{out}"
    # 對照：同一條 cycle 換成真動詞就會有 M 子句 → 上面的 0 不是因為整句話本來就沒東西
    with_verb = render(locale, _cm_cycle(m3={"m_components": [{"verb_code": "m_push"}]}))
    assert len(with_verb) > len(out)
    # X／I 兩段不受影響
    key = "sentence" if locale == "zh" else "sentence_en"
    assert occurrences(out, LABELS["x"]["x_press"][key]) == 1
    assert occurrences(out, LABELS["i"]["i_check"][key]) == 1


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("comps,code", M_COMPANION_ONLY)
def test_both_m_companion_never_appears_beside_a_real_verb(locale, comps, code):
    """正當併用（真動詞＋伴隨維度）：動詞入句、伴隨維度仍然不入句。

    這是黃金測試裡那些多分量案例的敘事面——TMU 取 max 要看兩顆，句子只講動詞。
    動詞排在第一顆，所以這條**擋的是「伴隨維度被額外接一段」**；「認不出伴隨維度」
    這個迴歸由下一條（伴隨維度排前面）擋，順序遮蔽的問題在那裡說明。
    """
    key = "sentence" if locale == "zh" else "sentence_en"
    out = render(locale, _cm_cycle(m3={"m_components": [{"verb_code": "m_push"}] + comps}))
    assert occurrences(out, LABELS["m_verb"]["m_push"][key]) == 1, out
    assert occurrences(out, TERMS[code][locale]) == 0, out


@pytest.mark.parametrize("locale", LOCALES)
def test_both_m_companion_first_still_picks_the_verb(locale):
    """順序無關：伴隨維度排在動詞**前面**時，句子取的仍是動詞而不是第一顆分量。"""
    key = "sentence" if locale == "zh" else "sentence_en"
    out = render(locale, _cm_cycle(
        m3={"m_components": [{"verb_code": "m_hand", "angle_deg": 180},
                             {"verb_code": "m_push", "distance_cm": 45}]}))
    assert occurrences(out, LABELS["m_verb"]["m_push"][key]) == 1, out
    assert occurrences(out, TERMS["m_hand"][locale]) == 0, out


# ── 3. 英文字面：ADR-032 D7.4 的四個語序案例 ──────────────────────
#
# ADR 的案例 1 與 2 出自同一個示意 cycle，但案例 2 的期望輸出把受詞寫成通稱
# "the part"（案例 1 寫的是 "the dummy DIMM"）。這裡照 ADR 逐字斷言，故兩案各自
# 給自己的 vocab——差別在 ADR 的行文，不在樣板行為。

_ADR_LABELS = {
    "g": {"g_grasp": {"sentence_en": "grasp"}},
    "p_base": {"p_hold": {"sentence_en": "hold it in place"}},
    "p_addon": {},
    "m_verb": {"m_push": {"sentence_en": "push it"}},
    "x": {"x_glue": {"sentence_en": "dispensing glue"}},
    "i": {"i_align1": {"sentence_en": "aligned to the point"}},
}


def test_en_adr_case_1_source_phrase_moves_after_the_object():
    """案例 1：中文來源片語**前置於動詞**（「從料架」），英文**後置於受詞**。"""
    cycle = {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
             "a3": {}, "p5": {}}
    out = build_narrative_en(cycle, _ADR_LABELS,
                             {"object": "dummy DIMM", "from": "rack", "to": "", "hand": "RH"})
    assert out.startswith("RH: grasp the dummy DIMM from the rack, reaching ~20 cm.")


def test_en_adr_case_2_gm_modifier_order_differs_from_zh():
    """案例 2：GM 三個修飾語的相對順序——中文距離→手度→目的地、英文距離→目的地→分詞片語。"""
    cycle = {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
             "a3": {"reach_cm": 15, "twist_deg": 90},
             "p5": {"p_base_code": "p_hold", "p_addon_codes": []}}
    out = build_narrative_en(cycle, _ADR_LABELS,
                             {"object": "part", "from": "rack", "to": "line", "hand": "RH"})
    assert "Then move ~15 cm to the line, turning the part over, and hold it in place." in out


def test_en_adr_case_3_connectives_come_from_the_template_not_the_data():
    """案例 3：連接詞在**樣板**裡（中文在資料裡的「並」）；X 用 while、I 用過去分詞。"""
    cycle = {"seq": "CM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
             "m3": {"m_components": [{"verb_code": "m_push"}]},
             "x4": {"x_code": "x_glue"}, "i5": {"i_code": "i_align1"}}
    out = build_narrative_en(cycle, _ADR_LABELS,
                             {"object": "part", "from": "", "to": "", "hand": "RH"})
    assert ", while dispensing glue, aligned to the point." in out
    # 資料端維持乾淨動詞片語：樣板不得對 I 也補一個 while
    assert "while aligned" not in out


def test_en_adr_case_4_imperative_with_hand_prefix():
    """案例 4：祈使句＋手別前綴，不是 "The right hand grasps…" 這種主謂結構。"""
    cycle = {"seq": "GM", "a0": {}, "g2": {"g_code": "g_grasp"}, "a3": {}, "p5": {}}
    out = build_narrative_en(cycle, _ADR_LABELS,
                             {"object": "part", "from": "", "to": "", "hand": "RH"})
    assert out.startswith("RH: grasp the part.")
    assert "hand grasps" not in out.lower()

    # 無手別時退為句首大寫的祈使句（仍不是主謂結構）
    no_hand = build_narrative_en(cycle, _ADR_LABELS,
                                 {"object": "part", "from": "", "to": "", "hand": ""})
    assert no_hand.startswith("Grasp the part.")


# ── 4. 英文素材缺漏時的降級（ADR-032 D10：只能回退中文，不得留空動詞）──

def test_en_falls_back_to_zh_material_when_english_is_missing():
    zh_only = {"g": {"g_grasp": {"label": "抓握", "sentence": "抓握"}},
               "p_base": {}, "p_addon": {}, "m_verb": {}, "x": {}, "i": {}}
    out = build_narrative_en(_gm_cycle(), zh_only, VOCAB_EN)
    assert "抓握 the main board" in out


def test_en_acronym_object_names_keep_their_capitalisation():
    """降格只動「首字除第一個字母外全小寫」的詞——縮寫不得變成 dIMM。"""
    labels = {"g": {"g_grasp": {"sentence_en": "grasp"}},
              "p_base": {}, "p_addon": {}, "m_verb": {}, "x": {}, "i": {}}
    cycle = {"seq": "GM", "a0": {}, "g2": {"g_code": "g_grasp"}, "a3": {}, "p5": {}}
    out = build_narrative_en(cycle, labels,
                             {"object": "DIMM slot", "from": "", "to": "", "hand": "RH"})
    assert "the DIMM slot" in out


# ── 5. 空白／空值詞彙名（H-1：讀取時組句的毒源）──────────────────────

# 全形空白（U+3000）與 nbsp（U+00A0）不是湊數：`str.strip()` 是 Unicode-aware 的，
# 現行實作本來就擋得住——但 fixture 只有 ASCII 的話，日後有人把它收窄成
# `.strip(" \t\n")` 或 regex `^[ \t]+$`，ASCII 案例照樣全綠而全形空白靜默回歸。
# 全形空白是中文輸入法極易打出、且肉眼與半形無異的字元（工廠詞彙的實際毒源）。
BLANK_NAMES = ["   ", "\t", "\n", " \t ", "", "\u3000", "\xa0", "\u3000 \xa0"]

TAIL = {"zh": "最後收束返回。", "en": "Finally, return to the start position."}

# 空白蒸發後各語系「不該留下什麼」——中文的殘骸長相與英文完全不同（前置介詞 vs 冠詞），
# 所以照本檔 `_expect_*` 的慣例逐語系派工，而不是拿英文的 regex 硬套中文。
DEBRIS = {
    "zh": (
        r"「\s*」",        # 空白受詞：「   」原樣入句（strip 前的實際輸出）
        r"從\s*[，。]",     # 來源蒸發後留下的孤兒「從」
        r"到\s*[，。]",     # 目的地蒸發後留下的孤兒「到」
        r"在\s*一側",       # CM 的「在『to』一側」整段該消失
    ),
    "en": (
        r"\b(the|from|to|at)\s*[.,]",
    ),
}


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("blank", BLANK_NAMES)
@pytest.mark.parametrize("slot", ["object", "from", "to"])
def test_both_blank_vocab_name_does_not_crash(slot, blank, locale):
    """三個 vocab 槽在英文都會經過 `_noun()`——純空白曾在 `split(maxsplit=1)[0]` 拋 IndexError。

    Phase C 之後敘事是讀取時產生的：一筆空白詞彙名＝**任何人**（含 viewer）讀模組/版本/
    工作表都 500，且改被讀的那筆資料修不好。所以這裡守的是「絕不拋例外」，不是輸出長相。
    """
    for cycle in (_gm_cycle(["a_align"], twist=90), _gm_cycle(p_repeat=3), _cm_cycle()):
        assert render_with(locale, cycle, **{slot: blank}).endswith(TAIL[locale])


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("blank", BLANK_NAMES)
@pytest.mark.parametrize("slot", ["object", "from", "to"])
def test_both_blank_vocab_name_leaves_no_dangling_phrase(slot, blank, locale):
    """空白詞要整段消失，不能留下 "the  " / "from ." 或「   」/ 孤兒「從」這種殘骸。"""
    for cycle in (_gm_cycle(["a_align"], twist=90), _cm_cycle()):
        out = render_with(locale, cycle, **{slot: blank})
        assert "\t" not in out and "\n" not in out
        assert "\u3000" not in out and "\xa0" not in out, out  # 全形空白/nbsp 同樣不得留在句中
        assert "  " not in out, out                            # 受詞蒸發後不得留下雙空格
        for pattern in DEBRIS[locale]:
            assert re.search(pattern, out) is None, (pattern, out)


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("blank", BLANK_NAMES)
@pytest.mark.parametrize("slot", ["object", "from", "to"])
def test_both_empty_and_blank_vocab_name_render_identically(slot, blank, locale):
    """空字串與純空白必須產出**完全相同**的句子。

    這是「先 strip 再套回退」的等價性保證：順序寫反（`vocab.get(x) or "part"` 再 strip）
    時 `"   "` 是 truthy，回退不生效、受詞整個蒸發，而 `""` 走回退拿到泛稱——
    同一種「沒填」在兩條路徑上分岔（Phase C 英文側殘留的 L-1 不一致）。
    """
    for cycle in (_gm_cycle(["a_align"], twist=90), _cm_cycle()):
        assert render_with(locale, cycle, **{slot: blank}) == render_with(locale, cycle, **{slot: ""})


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("blank", BLANK_NAMES)
def test_both_object_name_padded_with_spaces_is_trimmed(blank, locale):
    """反向：有內容但前後帶空白的名字要被 trim，而不是連著空白塞進句子。"""
    name = VOCAB["object"] if locale == "zh" else VOCAB_EN["object"]
    out = render_with(locale, _gm_cycle(), object=f"{blank}{name}{blank}")
    assert TERMS["object"][locale] in out.lower() and "  " not in out
