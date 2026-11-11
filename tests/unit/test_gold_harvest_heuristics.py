"""gold_harvest 啟發式與期望形狀的單元守門（R1/R2/R3；不需 DB）。

守什麼：

1. **R1 幽靈命中**：「DIMM壓合治具」的「壓合」是名詞內動詞面，不是動詞——
   動詞命中緊接設備名詞（治具/機台…）時排除；但真動詞（「放置工作台」
   「放至料架」）不得被反向擊穿。
2. **R2 CM 配對**：「接觸…推至/拉至」是標準單一 CM 候選
   （`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：
   CM＝A B G M X I A，G 與 M 同 cycle）——發中性旗標 take_move_pair_may_be_single_cm，
   不是 likely_multi_action_undercounted。
3. **判定單一出處**：覆核表的「取放/取移建模」題與 take_place_pair/take_move_pair
   共用同一函式——兩邊條件各寫一份曾經自相矛盾（掛「幾乎必然低估」的節同時
   出「多半建單一 GM cycle」的題）。
4. **R3 引擎拒絕期望**：complete 但引擎拒絕的 cycle，期望寫
   `expected_engine_rejected: true`；gold_eval 重放驗「引擎仍拒絕」——
   舊形狀（complete:true 無 TMU）在重放必回「expected engine_result」紅燈
   （產出即紅）。本檔用 stub 複現舊踩雷情境並證明修法有效。

mutation 證據（CI_GATES 規則 7）：把 `_action_verb_hits` 的設備名詞排除拆掉 →
`test_ghost_verb_hit_excluded`／六筆點名案例必紅；把 `_check_cycle` 的
`expected_engine_rejected` 分支拆掉 → `test_engine_rejected_expectation_replays_green`
必紅；把 `_questions_for` 的配對題改回自寫條件 → `test_pair_question_shares_predicate`
在條件漂移時必紅。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ddm_v2.nlp.gold_eval import _check_cycle
from ddm_v2.nlp.normalization import normalize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from gold_harvest import (  # noqa: E402
    _ACTION_VERBS,
    ZERO_TMU_CAVEAT,
    _action_verb_hits,
    _longest_first_hits,
    _questions_for,
    detect_challenge_tags,
    expected_cycle_from_draft,
    has_zero_tmu_complete_cycle,
    take_move_pair,
    take_place_pair,
)

# 複審點名的 6 筆（以原文釘住，不依賴草稿檔名——重產後流水號會變）
GM_PAIR_TEXTS = [
    "雙手抓握主板放至DIMM壓合治具",        # d001
    "拿取主板放置於DIMM壓合治具",          # d005
    "左手抓握DIMM壓合治具的把手放至對應的點位",  # d021
]
CM_PAIR_TEXTS = [
    "雙手接觸DIMM壓合治具推至規定位置",      # d007
    "雙手接觸DIMM壓合治具拉至規定位置",      # d010
    "右手接觸DIMM壓合治具的底板拉至對應的點位",  # d023
]


# ── R1：幽靈命中排除；真動詞不得被反向擊穿 ──────────────────────────────────


def test_ghost_verb_hit_excluded():
    """「壓合治具」的「壓合」：未排除版有命中、排除版沒有——證明 delta 就是排除。"""
    norm = normalize("雙手抓握主板放至DIMM壓合治具")
    raw_hits = _longest_first_hits(norm, _ACTION_VERBS)
    assert "壓合" in raw_hits, "前提：名詞內動詞面確實會被裸命中"
    hits = _action_verb_hits(norm)
    assert "壓合" not in hits
    assert hits == ["抓握", "放至"]


def test_genuine_verbs_before_bench_rack_not_excluded():
    """工作台/料架/垃圾桶不在排除名單：語料中它們常作真動詞的直接受詞。"""
    assert "放置" in _action_verb_hits(normalize("將主板放置工作台"))
    assert "放至" in _action_verb_hits(normalize("左手重新抓握主板的包装袋放至料架"))
    assert "丟至" in _action_verb_hits(normalize("左手抓握假DIMM的包裝袋丟至垃圾桶"))


def test_genuine_verb_with_nonadjacent_fixture_noun_kept():
    """「按壓功能測試治具」：治具不緊接動詞（隔著「功能測試」）→ 按壓是真動詞。"""
    assert "按壓" in _action_verb_hits(normalize("按壓功能測試治具"))


# ── R1+R2：六筆點名案例的配對判定與 multi_action 中和 ────────────────────────


def test_named_gm_pair_cases():
    for raw in GM_PAIR_TEXTS:
        norm = normalize(raw)
        assert take_place_pair(norm), f"{raw!r} 應為取＋放配對"
        assert not take_move_pair(norm)
        tags = detect_challenge_tags(raw, norm)
        assert tags["multi_action"] is False, f"{raw!r} 不得再標 multi_action"


def test_named_cm_pair_cases():
    for raw in CM_PAIR_TEXTS:
        norm = normalize(raw)
        assert take_move_pair(norm), f"{raw!r} 應為取/觸＋推/拉配對"
        assert not take_place_pair(norm)
        tags = detect_challenge_tags(raw, norm)
        assert tags["multi_action"] is False, f"{raw!r} 不得再標 multi_action"


def test_three_verbs_or_connective_still_multi_action():
    """配對中和只限「恰好兩動詞且無連接詞」：三動詞/含連接詞照樣 multi_action。"""
    for raw in [
        "拿取主板，去除包裝袋，將主板放置工作台",   # 3 動詞（含取＋放）
        "雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位",  # 接觸＋推至＋確認
        "確認DIMM點位，並按壓DIMM壓合治具的把手",   # 幽靈排除後仍 2 真動詞（確認＋按壓）
    ]:
        norm = normalize(raw)
        assert not take_place_pair(norm)
        assert not take_move_pair(norm)
        assert detect_challenge_tags(raw, norm)["multi_action"] is True


def _draft_stub_for_questions(raw: str) -> dict[str, Any]:
    norm = normalize(raw)
    return {
        "plan": {
            "normalized_text": norm,
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "move_place",
                    "evidence": [{"start": 0, "end": len(norm), "text": norm}],
                }
            ],
        },
        "challenge_tags": detect_challenge_tags(raw, norm),
        "expected": {"routing_status": "review"},
        "preannotation": {"routing_reasons": []},
    }


def test_pair_question_shares_predicate():
    """覆核表配對題與旗標判定同一出處：GM 配對出「取放建模」、CM 配對出
    「取移建模」；多動詞句（即使含取＋放）**不出**配對題——那正是先前
    「掛必然低估又出多半建單一 GM」的自相矛盾來源。"""
    for raw in GM_PAIR_TEXTS:
        qs = "\n".join(_questions_for(_draft_stub_for_questions(raw)))
        assert "取放建模" in qs, raw
        assert "取移建模" not in qs
    for raw in CM_PAIR_TEXTS:
        qs = "\n".join(_questions_for(_draft_stub_for_questions(raw)))
        assert "取移建模" in qs, raw
        assert "取放建模" not in qs
    # 舊矛盾案例：取＋放存在但共 3 動詞 → multi_action，配對題不得出現
    qs = "\n".join(
        _questions_for(_draft_stub_for_questions("拿取主板，去除包裝袋，將主板放置工作台"))
    )
    assert "取放建模" not in qs
    assert "取移建模" not in qs


# ── D3-018 M1：TMU=0.0 非真值——判定單一出處＋覆核表逐筆提問 ─────────────────


def test_zero_tmu_predicate_only_fires_on_complete_zero():
    """has_zero_tmu_complete_cycle：complete＋TMU=0.0 才觸發——真值 TMU、
    incomplete、引擎拒絕（無 total_tmu 鍵）都不觸發。"""
    assert has_zero_tmu_complete_cycle(
        [{"action_id": "a1", "complete": True, "seq": "CM", "total_tmu": 0.0}]
    )
    assert not has_zero_tmu_complete_cycle(
        [{"action_id": "a1", "complete": True, "seq": "GM", "total_tmu": 28.0}]
    )
    assert not has_zero_tmu_complete_cycle(
        [{"action_id": "a1", "complete": False, "cycle": None}]
    )
    # 引擎拒絕的期望（expected_engine_rejected）沒有 total_tmu 鍵——不觸發
    assert not has_zero_tmu_complete_cycle(
        [{"action_id": "a1", "complete": True, "expected_engine_rejected": True}]
    )
    # 混合：任一 complete cycle 為 0.0 即觸發（一個 0.0 就是一個非真值）
    assert has_zero_tmu_complete_cycle(
        [
            {"action_id": "a1", "complete": True, "seq": "GM", "total_tmu": 28.0},
            {"action_id": "a2", "complete": True, "seq": "CM", "total_tmu": 0.0},
        ]
    )


def test_zero_tmu_caveat_gets_per_draft_question():
    """覆核表逐筆問（M1）：帶 zero_tmu 旗標的草稿必出「補距離或判定資訊不足」
    的具體問題；無旗標不出——把 `_questions_for` 的提問拆掉即紅。"""
    draft = _draft_stub_for_questions("雙手接觸DIMM壓合治具推至規定位置")
    draft["preannotation_caveat"] = [ZERO_TMU_CAVEAT]
    qs = "\n".join(_questions_for(draft))
    assert "TMU=0.0" in qs
    assert "非真值" in qs
    assert "補距離" in qs and "資訊不足" in qs

    draft["preannotation_caveat"] = []
    qs = "\n".join(_questions_for(draft))
    assert "TMU=0.0" not in qs


# ── R3：引擎拒絕的期望形狀（stub 複現踩雷情境） ──────────────────────────────


@dataclass
class _StubCycleDraft:
    action_id: str = "a1"
    complete: bool = True
    cycle: dict | None = None
    engine_result: dict | None = None
    issues: list[str] = field(default_factory=list)


def _gm_cycle() -> dict:
    return {
        "seq": "GM",
        "g2": {"g_code": "g_grasp"},
        "p5": {"p_base_code": "p_place"},
        "frequency": 1,
    }


def test_engine_rejected_expectation_replays_green():
    """修法驗證：complete＋engine_result=None 的草稿 → 期望帶
    expected_engine_rejected → 重放（引擎仍拒絕）綠。"""
    rejected = _StubCycleDraft(cycle=_gm_cycle(), engine_result=None)
    exp = expected_cycle_from_draft(rejected)
    assert exp["complete"] is True
    assert exp["expected_engine_rejected"] is True
    assert "total_tmu" not in exp

    check = _check_cycle(rejected, exp)
    assert check.ok, f"引擎仍拒絕＝期望成立，不得紅：{check.errors}"


def test_old_expectation_shape_was_a_time_bomb():
    """踩雷情境複現：舊 harvest 對此類寫 complete:true 無 TMU、無旗標——
    重放必回「expected engine_result」。此測試釘死「旗標拿掉＝紅」的因果。"""
    rejected = _StubCycleDraft(cycle=_gm_cycle(), engine_result=None)
    exp = expected_cycle_from_draft(rejected)
    exp.pop("expected_engine_rejected")  # 模擬舊輸出形狀
    check = _check_cycle(rejected, exp)
    assert not check.ok
    assert any("expected engine_result" in e for e in check.errors)


def test_engine_now_accepting_trips_stale_rejection_expectation():
    """引擎改為接受（規則變了）→ expected_engine_rejected 期望過時，必須紅。"""
    accepted = _StubCycleDraft(
        cycle=_gm_cycle(),
        engine_result={"total_tmu": 28.0, "tech_line": "A6 B0 G6 A10 B0 P6 A0"},
    )
    rejected_exp = expected_cycle_from_draft(
        _StubCycleDraft(cycle=_gm_cycle(), engine_result=None)
    )
    check = _check_cycle(accepted, rejected_exp)
    assert not check.ok
    assert any("engine accepted" in e for e in check.errors)


def test_accepted_cycle_expectation_unchanged():
    """迴歸：引擎接受的 cycle 期望形狀不變（TMU/tech_line 照驗）。"""
    accepted = _StubCycleDraft(
        cycle=_gm_cycle(),
        engine_result={"total_tmu": 28.0, "tech_line": "A6 B0 G6 A10 B0 P6 A0"},
    )
    exp = expected_cycle_from_draft(accepted)
    assert "expected_engine_rejected" not in exp
    assert exp["total_tmu"] == 28.0
    assert _check_cycle(accepted, exp).ok

    # 引擎轉為拒絕 → 照舊紅（expected engine_result）
    now_rejected = _StubCycleDraft(cycle=_gm_cycle(), engine_result=None)
    check = _check_cycle(now_rejected, exp)
    assert not check.ok
    assert any("expected engine_result" in e for e in check.errors)


# ── D3-023：unknown 卡點分類與生產判型同源（_verb_seq；X/I 收進 CM 訊號）────
#
# unknown_block_reason 曾自寫一份 has_m/has_p 判定——X/I 擴充後那就是平行
# 判定路徑（單一引擎原則）；改用生產端 _verb_seq 後，以下測試釘住：
# mutation 證據＝把 unknown_block_reason 的 verb 判定改回「只認 M」→
# test_unknown_block_xi_mixed_is_verb_mixed_abstain 必紅（X+P 句會被誤分類
# 成 unregistered_verbs/single_verb_insufficient）。


def _syn_row(param: str, code: str, norm: str) -> dict:
    return {"parameter": param, "option_code": code, "synonym_norm": norm, "priority": 0}


def test_unknown_block_xi_mixed_is_verb_mixed_abstain():
    """X＋P／I＋P 同句＝跨模型混合 → verb_mixed_abstain（與生產棄權同源）。"""
    from gold_harvest import unknown_block_reason

    syns = [
        _syn_row("X", "x_screw_fix", "鎖附"),
        _syn_row("I", "i_confirm", "確認"),
        _syn_row("P", "p_place_single", "放至"),
    ]
    reason, missing = unknown_block_reason("鎖附螺絲後放至料盒", "鎖附螺絲後放至料盒", syns)
    assert (reason, missing) == ("verb_mixed_abstain", [])
    reason2, _ = unknown_block_reason("確認點位後放至流水線", "確認點位後放至流水線", syns)
    assert reason2 == "verb_mixed_abstain"


def test_unknown_block_noun_cm_verb_gm_still_detected():
    """既有 ※2 象限（名詞 CM × 動詞 G+P）分類不因 X/I 擴充而漂移。"""
    from gold_harvest import unknown_block_reason

    syns = [
        _syn_row("G", "g_grasp", "抓握"),
        _syn_row("P", "p_place_single", "放至"),
    ]
    reason, _ = unknown_block_reason("雙手抓握主板放至機台", "雙手抓握主板放至機台", syns)
    assert reason == "noun_cm_verb_gm_abstain"


def test_unknown_block_reason_not_reached_for_xi_typed():
    """X/I 單獨命中已被生產判型收為 CM（不再是 composite_unknown）——
    分類函式對這類句子不會再被呼叫；此處驗生產端同一句確實 typed。"""
    from ddm_v2.nlp.rule_based import RuleBasedParser

    syns = [_syn_row("X", "x_screw_fix", "鎖附")]
    r = RuleBasedParser(syns).parse("鎖附主機板固定螺絲 x6")
    assert r.suggested_seq == "CM"
