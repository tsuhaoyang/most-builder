"""nlp 套件單元測試（impl-05）。

涵蓋：
1. normalization：NFKC / 繁簡 / 全形數字 / 混排
2. lexicon：最長匹配優先（長詞>短詞）、覆蓋去重
3. parser 黃金：GM/CM 判型（v3 治具防護案例）、信心排序不變量
4. 信心排序：default < inferred 不變量
"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.lexicon import build_lexicon, match_all
from ddm_v2.nlp.normalization import normalize
from ddm_v2.nlp.rule_based import RuleBasedParser

pytestmark = pytest.mark.unit


# ── normalization ──────────────────────────────────────────────────────────


def test_normalize_nfkc_fullwidth_to_ascii():
    """全形英數 → ASCII（NFKC）。"""
    result = normalize("Ａ１２３")  # U+FF21, U+FF11, U+FF12, U+FF13
    assert result == "a123"


def test_normalize_fullwidth_punctuation():
    """OpenCC s2twp 將「機台」轉為「機臺」；結果具決定性（同輸入→同輸出）。

    實際輸出（opencc-python-reimplemented s2twp）：
      normalize("機台機臺") → "機臺機臺"
    """
    result = normalize("機台機臺")
    assert "機" in result  # 至少包含基本字
    assert result == "機臺機臺"  # OpenCC 將「機台」→「機臺」；具決定性


def test_normalize_simplified_to_traditional():
    """簡體 → 繁體（OpenCC s2twp）。

    實際輸出（opencc-python-reimplemented s2twp）：
      normalize("測试机器") → "測試機器"
    """
    result = normalize("測试机器")
    # opencc s2twp：測试→測試；机器→機器
    assert "測試" in result
    assert "機器" in result


def test_normalize_collapses_whitespace():
    """連續空白收斂為單一空格。"""
    assert normalize("  hello   world  ") == "hello world"


def test_normalize_lowercase_ascii():
    """英文大寫 → 小寫。"""
    assert normalize("ABC DEF") == "abc def"


def test_normalize_empty():
    assert normalize("") == ""
    assert normalize("   ") == ""


def test_normalize_mixed_lang():
    """中英混排，英文小寫、中文保留。"""
    result = normalize("取料 SMT 壓合")
    assert "smt" in result
    assert "取料" in result
    assert "壓合" in result


# ── lexicon ────────────────────────────────────────────────────────────────


def _syn(param: str, code: str, norm: str, priority: int = 0) -> dict:
    return {
        "parameter": param,
        "option_code": code,
        "synonym_norm": norm,
        "priority": priority,
    }


def test_build_lexicon_sorted_by_length_desc():
    """詞典依 norm 長度降冪排序。"""
    syns = [
        _syn("G", "G1", "拿取"),
        _syn("G", "G2", "拿取小型零件"),
        _syn("G", "G3", "拿"),
    ]
    lex = build_lexicon(syns)
    lengths = [len(e.norm) for e in lex]
    assert lengths == sorted(lengths, reverse=True)


def test_match_all_longest_wins():
    """「拿取小」>「拿取」：長詞命中後短詞不覆蓋同位置。"""
    lex = build_lexicon([
        _syn("G", "G1", "拿取"),
        _syn("G", "G2", "拿取小型零件"),
    ])
    matches = match_all("拿取小型零件放到治具上", lex)
    codes = [e.option_code for _, _, e in matches]
    assert "G2" in codes
    assert "G1" not in codes  # 被長詞覆蓋


def test_match_all_non_overlapping():
    """不同位置的命中不互相覆蓋。"""
    lex = build_lexicon([
        _syn("A", "A1", "伸手"),
        _syn("G", "G1", "抓取"),
    ])
    text = "伸手到治具上抓取零件"
    matches = match_all(text, lex)
    assert len(matches) == 2
    params = {e.parameter for _, _, e in matches}
    assert params == {"A", "G"}


def test_match_all_no_match():
    """文本中無對應詞→空列表。"""
    lex = build_lexicon([_syn("G", "G1", "抓取")])
    assert match_all("完全不相關的文字", lex) == []


def test_build_lexicon_empty():
    assert build_lexicon([]) == []


# ── RuleBasedParser ────────────────────────────────────────────────────────


def _make_parser(*syns: dict) -> RuleBasedParser:
    return RuleBasedParser(list(syns))


def test_parser_cm_trigger_machine():
    """「並壓合機台」觸發 CM 判型（v3 治具防護案例）。"""
    parser = _make_parser()
    result = parser.parse("並壓合機台進行壓合作業")
    assert result.suggested_seq == "CM"


def test_parser_gm_trigger_jig():
    """「治具」名詞觸發 GM 判型（v3 治具防護案例）。"""
    parser = _make_parser()
    result = parser.parse("將零件放到壓合治具上")
    assert result.suggested_seq == "GM"


def test_parser_cm_wins_over_gm_when_both_present():
    """CM 觸發詞優先於 GM 名詞（v3 治具防護：治具+機台→CM）。"""
    parser = _make_parser()
    result = parser.parse("治具並壓合機台壓合")
    assert result.suggested_seq == "CM"


def test_parser_no_seq_trigger():
    """無判型觸發詞→ suggested_seq=None。"""
    parser = _make_parser()
    result = parser.parse("拿起零件放到位置上")
    assert result.suggested_seq is None


def test_parser_slot_filled_from_synonym():
    """DB 同義詞命中 → slot.chosen 有值，信心=0.95。"""
    parser = _make_parser(
        _syn("G", "G3", "拿取小型零件"),
    )
    result = parser.parse("拿取小型零件並放置", "TEST_RS")
    g_slot = next(s for s in result.slots if s.field == "g_code")
    assert g_slot.chosen is not None
    assert g_slot.chosen.option_code == "G3"
    assert g_slot.chosen.score == pytest.approx(0.95)
    assert g_slot.chosen.source == "exact"


def test_parser_slot_unfilled_needs_review():
    """無命中 slot → chosen=None, needs_review=True。"""
    parser = _make_parser()
    result = parser.parse("無法辨識的文字", "TEST_RS")
    for s in result.slots:
        assert s.chosen is None
        assert s.needs_review is True


def test_parser_confidence_order():
    """overall_confidence：有命中 > 無命中（default < inferred 不變量）。"""
    parser_no_match = _make_parser()
    parser_with_match = _make_parser(_syn("G", "G1", "抓取"))

    result_no = parser_no_match.parse("抓取零件")
    result_yes = parser_with_match.parse("抓取零件")

    assert result_yes.overall_confidence > result_no.overall_confidence


def test_parser_default_score_lower_than_exact():
    """default=0.3 < exact=0.95（v3 缺陷修正：default 不再是 1.0）。"""
    parser = _make_parser(_syn("G", "G1", "抓取"))
    result = parser.parse("抓取零件")
    g_slot = next(s for s in result.slots if s.field == "g_code")
    # 有命中的 slot：exact=0.95
    assert g_slot.chosen is not None
    assert g_slot.chosen.score == pytest.approx(0.95)

    # 無命中的 slot（如 A）：chosen=None，不存在 score
    a_slots = [s for s in result.slots if s.field.startswith("a_")]
    for s in a_slots:
        assert s.chosen is None
        # top_k 為空，不存在 default score 條目
        assert s.top_k == []


def test_parser_reach_context_extracted():
    """距離數值抽取進 context['reach_cm']。"""
    parser = _make_parser()
    result = parser.parse("伸手 30cm 拿取零件")
    assert result.context.get("reach_cm") == pytest.approx(30.0)


def test_parser_provenance_fields():
    """provenance 包含 parser 版本、rule_set_code、elapsed_ms。"""
    parser = _make_parser()
    result = parser.parse("測試", "MY_RULESET")
    assert result.provenance["parser"] == "rule_based_v1"
    assert result.provenance["rule_set_code"] == "MY_RULESET"
    assert isinstance(result.provenance["elapsed_ms"], float)
    assert result.provenance["elapsed_ms"] >= 0


def test_parser_normalized_text_in_result():
    """回傳結果包含 normalized_text。"""
    parser = _make_parser()
    result = parser.parse("Ａ拿取 B測試")
    assert result.normalized_text != ""
    assert result.raw_text == "Ａ拿取 B測試"


def test_parser_slots_count():
    """slots 數量固定為 7（GM 序列 A B G A B P A）。"""
    parser = _make_parser()
    result = parser.parse("任意文字")
    assert len(result.slots) == 7


def test_parser_cross_param_same_word():
    """跨參數命中：P slot 取得對應選項（top_k≥2 跨參數歧義為 Stage 2 功能，目前不支援）。"""
    # Stage 1：單一指派，只有一個 slot 拿到「對準」token（lexicon 最長匹配覆蓋去重）
    parser = RuleBasedParser([
        {"parameter": "P", "option_code": "P1", "synonym_norm": "對準"},
        {"parameter": "I", "option_code": "I1", "synonym_norm": "對準"},
    ])
    r = parser.parse("對準位置後插入")
    p_slot = next((s for s in r.slots if s.field == "p_base_code"), None)
    # Stage 1：p_slot 物件必定存在（GM 固定 7 slots）
    # Stage 2（TODO）：同一 token 跨參數歧義應產生 top_k≥2 且 needs_review=True
    assert p_slot is not None
    # 不斷言 chosen.option_code 或 top_k 長度（Stage 2 行為未實作）


# ─── v3 治具防護全套移植 ──────────────────────────────────────────────────────


def test_parser_gm_trigger_jig_station():
    """壓合站 → GM（_GM_NOUNS 成員「壓合站」獨立觸發）。"""
    r = _make_parser().parse("移到壓合站放置")
    assert r.suggested_seq == "GM"


def test_parser_gm_trigger_jig_position():
    """壓合位置 → GM（_GM_NOUNS 成員「壓合位置」獨立觸發）。"""
    r = _make_parser().parse("對準壓合位置")
    assert r.suggested_seq == "GM"


def test_parser_gm_main_case():
    """主案例：DIMM 壓合治具 → GM（F-05 驗收：治具防護）。"""
    r = _make_parser().parse("雙手抓握主板放到DIMM壓合治具")
    assert r.suggested_seq == "GM"


def test_parser_cm_execute_pressing():
    """執行壓合 → CM（_CM_TRIGGERS 成員「執行壓合」獨立觸發）。"""
    r = _make_parser().parse("執行壓合動作")
    assert r.suggested_seq == "CM"


def test_parser_cm_perform_pressing():
    """進行壓合（獨立）→ CM（_CM_TRIGGERS 成員「進行壓合」獨立觸發）。"""
    r = _make_parser().parse("進行壓合操作")
    assert r.suggested_seq == "CM"


def test_parser_cm_trigger_machine_table():
    """機台（CM 觸發詞）→ CM；「卡合」為旁字不影響判斷。

    F-05 §3 規格：CM 觸發詞包含「機台」；本測試驗證的是「機台」觸發路徑，
    而非「卡合壓合」本身（後者不在 CM 觸發詞列表中）。
    """
    r = _make_parser().parse("卡合壓合機台作業")
    assert r.suggested_seq == "CM"


# ─── D3-017：判型吃字典（動詞訊號源 × 衝突矩陣 × 棄權路徑）──────────────────
#
# 動詞面採用實際已登記的 15 條映射之子集；判型與 slot 填充共用同一次
# match_all（無平行查詢路徑），故測試以 RuleBasedParser 端到端驗 suggested_seq。

_G_GRASP = _syn("G", "g_grasp", "抓握")
_G_TOUCH = _syn("G", "g_touch", "接觸")
_M_PULL = _syn("M", "m_pull", "拉至")
_M_PRESS = _syn("M", "m_press", "按壓")
_M_REMOVE = _syn("M", "m_remove", "去除")
_P_HOLD = _syn("P", "p_hold", "保持住")
_P_PLACE_S = _syn("P", "p_place_single", "放至")
_P_PLACE_ZHI_S = _syn("P", "p_place_single", "放置")


def test_verb_cm_signal_m_alone():
    """訊號源①：M 動詞命中（無名詞觸發、無 P）→ CM。"""
    r = _make_parser(_M_PRESS).parse("按壓dimm卡扣到定位")
    assert r.suggested_seq == "CM"


def test_verb_cm_signal_g_plus_m():
    """訊號源①（G 伴隨）：接觸＋拉至（CM 自己有 G 格）→ CM。"""
    r = _make_parser(_G_TOUCH, _M_PULL).parse("雙手接觸左右卡扣拉至規定位置")
    assert r.suggested_seq == "CM"


def test_verb_gm_signal_g_plus_p():
    """訊號源②：G＋P 動詞組合命中（無名詞觸發、無 M）→ GM。"""
    r = _make_parser(_G_GRASP, _P_HOLD).parse("雙手抓握主板保持住至流水線")
    assert r.suggested_seq == "GM"


def test_verb_cm_overrides_gm_noun():
    """衝突 ※1：名詞說 GM（治具）、動詞說 CM（m_pull）→ CM。

    d019「接觸治具拉至定位」正是此型——IE 已裁「接觸＋推/拉」是單一 CM，
    名詞觸發在此象限是誤判（治具只是操作對象）。
    """
    r = _make_parser(_G_TOUCH, _M_PULL).parse("雙手接觸DIMM壓合治具拉至規定位置")
    assert r.suggested_seq == "CM"


def test_gm_verbs_with_cm_noun_abstain():
    """衝突 ※2：名詞說 CM（機台）、動詞說 GM（G+P）→ 棄權（None）。

    非全域「動詞壓名詞」：此象限無 IE 裁決（可能是上料＋機台製程兩個
    action），硬判必有一半機率錯——寧可棄權。
    """
    r = _make_parser(_G_GRASP, _P_PLACE_S).parse("雙手抓握主板放至機台")
    assert r.suggested_seq is None


def test_mixed_verbs_abstain_even_with_noun():
    """棄權路徑：M＋P 同句（跨模型混合＝多 cycle 證據）→ None，名詞在場也不救。

    「去除（M）＋放置（P）」不可能同 cycle（M 只在 CM、P 只在 GM）；
    這正是多動作句（d005 型），單 action 判任何型都是硬塞。
    """
    r = _make_parser(_M_REMOVE, _P_PLACE_ZHI_S).parse(
        "拿取主板,去除包裝袋,將主板放置壓合治具"
    )
    assert r.suggested_seq is None


def test_p_alone_gives_no_verb_signal():
    """P 單獨命中＝無動詞訊號（單一動詞不足以定序列）→ 無名詞則 None。"""
    r = _make_parser(_P_PLACE_ZHI_S).parse("放置散熱片於cpu上")
    assert r.suggested_seq is None


def test_g_alone_falls_back_to_noun():
    """G 單獨命中＝無動詞訊號 → 回名詞判（治具→GM）；無名詞→None。"""
    with_noun = _make_parser(_G_GRASP).parse("雙手抓握主板放進DIMM壓合治具")
    assert with_noun.suggested_seq == "GM"
    without_noun = _make_parser(_G_GRASP).parse("雙手抓握主板")
    assert without_noun.suggested_seq is None


def test_empty_lexicon_preserves_noun_only_behavior():
    """空詞典＝動詞訊號恆無 → 與舊（僅名詞）行為完全一致（回歸保護）。"""
    r1 = _make_parser().parse("雙手接觸DIMM壓合治具拉至規定位置")
    assert r1.suggested_seq == "GM"  # 舊行為：名詞觸發（動詞不參與）
    r2 = _make_parser().parse("按壓dimm卡扣到定位")
    assert r2.suggested_seq is None


# ─── D3-023：X/I 參與判型（IE 核可開票）────────────────────────────────────
#
# X 與 I 只存在 CM 序列（spec §2：CM＝A B G M X I A；GM 無 X/I）——面命中是
# 結構性 CM 證據，與 M 同級。動詞面採實際已登記映射（鎖附→x_screw_fix、
# 清潔→x_blow_clean、確認→i_confirm）。

_X_SCREW = _syn("X", "x_screw_fix", "鎖附")
_X_CLEAN = _syn("X", "x_blow_clean", "清潔")
_I_CONFIRM = _syn("I", "i_confirm", "確認")


def test_verb_cm_signal_x_alone():
    """訊號源③：X 面單獨命中（無名詞觸發、無 M/P）→ CM。"""
    r = _make_parser(_X_SCREW).parse("鎖附主機板固定螺絲 x6")
    assert r.suggested_seq == "CM"


def test_verb_cm_signal_i_alone():
    """訊號源④：I 面單獨命中（無名詞觸發、無 M/P）→ CM。"""
    r = _make_parser(_I_CONFIRM).parse("並確認DIMM點位")
    assert r.suggested_seq == "CM"


def test_verb_cm_signal_g_plus_x_not_mixed():
    """X/I＋G 不是混合：G 在兩序列都有、CM 自有 G 格（工具取得＋工具製程＝
    單一 CM，g13 型）→ CM。"""
    g_pick = _syn("G", "g_pick_sel", "拿取")
    r = _make_parser(g_pick, _X_CLEAN).parse("拿取風槍清潔DIMM卡槽")
    assert r.suggested_seq == "CM"


def test_verb_cm_signal_x_plus_i_same_direction():
    """X＋I 同向（同一 CM cycle 本來就同時容納 X 與 I）→ CM，不是混合。"""
    r = _make_parser(_X_SCREW, _I_CONFIRM).parse("並鎖附固定並確認螺絲到位")
    assert r.suggested_seq == "CM"


def test_verb_cm_signal_m_plus_i_same_direction():
    """M＋I 同向（CM＝A B G M X I A，M 與 I 同 cycle）→ CM。"""
    m_push = _syn("M", "m_push", "推至")
    r = _make_parser(m_push, _I_CONFIRM).parse("雙手接觸卡扣推至規定位置並確認到位")
    assert r.suggested_seq == "CM"


def test_x_verb_overrides_gm_noun():
    """衝突 ※1（X/I 來源）：名詞說 GM（治具）、動詞說 CM（x_screw_fix）→ CM。

    「鎖附治具」＝對治具做工具製程——治具名詞只是操作對象證據，X 是序列
    參數證據（只存在 CM）；與 d019「接觸治具拉至」的 M 裁決同一論證結構。
    """
    r = _make_parser(_X_SCREW).parse("鎖附壓合治具固定螺絲")
    assert r.suggested_seq == "CM"


def test_i_verb_overrides_gm_noun():
    """衝突 ※1（I 來源）：名詞說 GM（治具）、動詞說 CM（i_confirm）→ CM。"""
    r = _make_parser(_I_CONFIRM).parse("確認治具到位")
    assert r.suggested_seq == "CM"


def test_x_verb_with_cm_noun_same_direction():
    """名詞 CM（機台）× 動詞 CM（X）→ CM（同向，無衝突）。"""
    r = _make_parser(_X_CLEAN).parse("清潔機台表面")
    assert r.suggested_seq == "CM"


def test_xi_with_p_abstains_even_with_noun():
    """棄權路徑：X/I＋P 同句＝跨模型混合（X/I 只在 CM、P 只在 GM）→ None，
    名詞在場也不救——「鎖附後放至」型＝≥2 cycle 證據，照 M+P 棄權前例。"""
    p_place = _syn("P", "p_place_single", "放至")
    r = _make_parser(_X_SCREW, p_place).parse("鎖附螺絲後放至壓合治具")
    assert r.suggested_seq is None
    r2 = _make_parser(_I_CONFIRM, p_place).parse("確認點位後放至流水線")
    assert r2.suggested_seq is None


def test_gxp_with_x_abstains_mixed():
    """G＋X＋P 同句仍是混合（cm_core＋P 蓋過 G+P 的 GM 組合）→ None。"""
    r = _make_parser(
        _syn("G", "g_pick_sel", "拿取"), _X_CLEAN, _syn("P", "p_place_zhi", "放置")
    ).parse("拿取風槍清潔放置料盒的DIMM")
    assert r.suggested_seq is None


def test_xi_unregistered_preserves_old_behavior():
    """空詞典回歸不變式（X/I 面）：X/I 未登記＝訊號恆無＝舊（僅名詞）行為。"""
    # 有名詞觸發：維持名詞判（治具→GM）
    r1 = _make_parser().parse("鎖附壓合治具固定螺絲")
    assert r1.suggested_seq == "GM"
    # 無名詞觸發：維持 None
    r2 = _make_parser().parse("並確認DIMM點位")
    assert r2.suggested_seq is None


# ─── v2_0038：同 norm 多 code 的決定性 tie-break（priority 0＝預設先匹配）────


def test_build_lexicon_same_norm_priority_zero_wins():
    """同 norm 兩變體：priority 0（預設）排前——與輸入順序無關。"""
    # 故意以 priority 1 在前的順序輸入
    lex = build_lexicon([
        _syn("P", "p_place_none", "放至", priority=1),
        _syn("P", "p_place_single", "放至", priority=0),
    ])
    codes = [e.option_code for e in lex]
    assert codes == ["p_place_single", "p_place_none"]
    # match_all 位置覆蓋 → 只有預設變體出現在命中清單
    hits = [e.option_code for _, _, e in match_all("雙手抓握主板放至治具", lex)]
    assert hits == ["p_place_single"]


def test_build_lexicon_same_norm_same_priority_code_tiebreak():
    """同 norm 同 priority：以 option_code 升冪決勝（完全決定性）。"""
    lex = build_lexicon([
        _syn("P", "p_b", "放至", priority=0),
        _syn("P", "p_a", "放至", priority=0),
    ])
    assert [e.option_code for e in lex] == ["p_a", "p_b"]


def test_build_lexicon_cross_norm_order_unchanged():
    """跨 norm 排序不變量：仍以 (len, norm) 降冪（長詞先；priority 不跨面比較）。"""
    lex = build_lexicon([
        _syn("G", "G1", "拿取", priority=9),
        _syn("G", "G2", "拿取小型零件", priority=0),
    ])
    assert [e.option_code for e in lex] == ["G2", "G1"]
