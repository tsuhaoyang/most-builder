"""gold_harvest 的 v3 結構回填守門（D3-014 裁決 3 → 裁決 1 逐案化；不需 DB）。

守什麼：

1. **來源單位的 cycle 容器語意**（2026-08-16 查證 src/ddm_v2/models/v2）：
   - `motion_module_versions.rows[]` 一列＝一個 cycle（rows[*].cycle 單一 CycleIn）；
   - `motion_modules.name_zh` ＝發布版 rows 列數（IE 把這段話切成幾個 cycle）；
   - `wi_rows` 一列＝一個 cycle 容器（most_cycles.wi_row_id UNIQUE），**但 v3 搬遷
     不寫 wi_rows**——非 v3 遷移資料，不餵 hint；
   - `motion_templates` 同理（seed 腳本種入，非 v3）。
2. **hint 決策規則**：v3 來源全數同 n → single_cycle / multi_cycle_n；矛盾 →
   ambiguous(conflicting_v3_structures)；無 v3 訊號 → ambiguous(no_v3_structure_signal)。
3. **確認題 vs 開放題**：有結構答案的配對題改成確認題（預設依 v3 結構、IE 可推翻）；
   缺失/矛盾維持開放題並列證據——與草稿旗標共用同一 hint 欄位，不另判一次。
4. **警語降級**：likely_multi＋single_cycle hint ⇒「幾乎必然低估」降級
   （`_caveat_line_zh` 是唯一出處，checklist 直接呼叫）。

mutation 證據（CI_GATES 規則 7）：把 `v3_structure_backfill` 的 v3_migrated 過濾
拆掉 → `test_non_v3_sources_do_not_feed_hint`／`test_wi_rows_only_gives_no_signal`
必紅；把矛盾判定改成「取第一個」→ `test_conflicting_structures_ambiguous` 必紅；
把 `_questions_for` 的確認題改回無條件開放題 → `test_gm_pair_confirmation_question`
必紅；把 `_caveat_line_zh` 的降級分支拆掉 → `test_likely_multi_caveat_downgraded` 必紅。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ddm_v2.nlp.normalization import normalize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from gold_harvest import (  # noqa: E402
    _CAVEAT_ZH,
    _LIKELY_MULTI_DOWNGRADED_ZH,
    STRUCTURE_HINT_AMBIGUOUS,
    STRUCTURE_HINT_SINGLE,
    Candidate,
    SourceRecord,
    _caveat_line_zh,
    _questions_for,
    _structure_evidence_for_source,
    detect_challenge_tags,
    structure_hint_multi,
    v3_structure_backfill,
)

# ── fixture helpers ──────────────────────────────────────────────────────────

MODULES: dict[str, dict[str, Any]] = {
    "m-single": {"category": "action", "v3_import": True, "current_version": 1, "n_rows": 1},
    "m-multi3": {"category": "wi-template", "v3_import": True, "current_version": 1, "n_rows": 3},
    "m-unpublished": {
        "category": "wi-template", "v3_import": True, "current_version": 0, "n_rows": None,
    },
    "m-not-v3": {"category": "action", "v3_import": False, "current_version": 1, "n_rows": 1},
}


def _rec(table: str, row_id: str, detail: str, group_key: str) -> SourceRecord:
    return SourceRecord(
        priority=1, table=table, row_id=row_id, detail=detail,
        group_key=group_key, timestamp=None, raw="佔位原文",
    )


def _cand(*recs: SourceRecord) -> Candidate:
    c = Candidate(norm="佔位", raw="佔位原文")
    c.sources = list(recs)
    return c


def _module_name_rec(module_id: str) -> SourceRecord:
    return _rec("motion_modules", module_id, "name_zh (category=x)", f"module:{module_id}")


def _version_row_rec(module_id: str, version_id: str = "v-1", idx: int = 0) -> SourceRecord:
    return _rec(
        "motion_module_versions", version_id, f"rows[{idx}].sub_activity", f"module:{module_id}"
    )


# ── 1+2：來源語意與 hint 決策規則 ────────────────────────────────────────────


def test_module_version_row_is_one_cycle():
    ev = _structure_evidence_for_source(_version_row_rec("m-single"), MODULES)
    assert ev["cycles"] == 1
    assert ev["v3_migrated"] is True

    hint, evidence = v3_structure_backfill(_cand(_version_row_rec("m-single")), MODULES)
    assert hint == STRUCTURE_HINT_SINGLE
    assert "reason" not in evidence


def test_module_name_maps_to_published_rows_count():
    """一個 module 幾列＝IE 把這段話切成幾個 cycle。"""
    ev = _structure_evidence_for_source(_module_name_rec("m-multi3"), MODULES)
    assert ev["cycles"] == 3

    hint, _ = v3_structure_backfill(_cand(_module_name_rec("m-multi3")), MODULES)
    assert hint == structure_hint_multi(3) == "multi_cycle_3"

    hint, _ = v3_structure_backfill(_cand(_module_name_rec("m-single")), MODULES)
    assert hint == STRUCTURE_HINT_SINGLE


def test_conflicting_structures_ambiguous():
    """同句出現在不同結構的多個來源（實例：「雙手抓握主板組至機箱」同時是
    3 列 wi-template 的名稱與單列 action module）→ ambiguous，矛盾證據全列。"""
    cand = _cand(_module_name_rec("m-multi3"), _version_row_rec("m-single"))
    hint, evidence = v3_structure_backfill(cand, MODULES)
    assert hint == STRUCTURE_HINT_AMBIGUOUS
    assert evidence["reason"] == "conflicting_v3_structures"
    assert sorted(e["cycles"] for e in evidence["sources"]) == [1, 3]


def test_wi_rows_only_gives_no_signal():
    """wi_rows 一列＝一個 cycle 容器（結構語意成立），但 v3 搬遷不寫 wi_rows——
    非 v3 遷移資料，不餵 hint（實例：d045「拿取排線並對準接頭」）。"""
    rec = _rec("wi_rows", "w-1", "sub_activity", "worksheet:ws-1")
    ev = _structure_evidence_for_source(rec, MODULES)
    assert ev["cycles"] == 1, "結構語意：一列一 cycle 容器"
    assert ev["v3_migrated"] is False, "但不是 v3 遷移資料"

    hint, evidence = v3_structure_backfill(_cand(rec), MODULES)
    assert hint == STRUCTURE_HINT_AMBIGUOUS
    assert evidence["reason"] == "no_v3_structure_signal"


def test_motion_templates_do_not_feed_hint():
    rec = _rec("motion_templates", "t-1", "name_zh", "template:t-1")
    ev = _structure_evidence_for_source(rec, MODULES)
    assert ev["cycles"] == 1
    assert ev["v3_migrated"] is False

    hint, evidence = v3_structure_backfill(_cand(rec), MODULES)
    assert hint == STRUCTURE_HINT_AMBIGUOUS
    assert evidence["reason"] == "no_v3_structure_signal"


def test_unpublished_module_is_missing_signal_not_zero():
    """current_version=0 的 module：cycles=None（訊號缺失），不是 0 個 cycle。"""
    ev = _structure_evidence_for_source(_module_name_rec("m-unpublished"), MODULES)
    assert ev["cycles"] is None

    hint, evidence = v3_structure_backfill(_cand(_module_name_rec("m-unpublished")), MODULES)
    assert hint == STRUCTURE_HINT_AMBIGUOUS
    assert evidence["reason"] == "no_v3_structure_signal"


def test_non_v3_sources_do_not_feed_hint():
    """keywords 無 v3-import 的 module 不是 IE 的 v3 裁決——結構訊號不採計。"""
    hint, evidence = v3_structure_backfill(_cand(_module_name_rec("m-not-v3")), MODULES)
    assert hint == STRUCTURE_HINT_AMBIGUOUS
    assert evidence["reason"] == "no_v3_structure_signal"
    assert evidence["sources"][0]["v3_migrated"] is False


def test_consistent_multi_source_agreement():
    """多個 v3 來源同 n → 不因來源數量誤判矛盾。"""
    cand = _cand(
        _version_row_rec("m-single", "v-1", 0),
        _version_row_rec("m-multi3", "v-2", 1),
        _module_name_rec("m-single"),
    )
    hint, evidence = v3_structure_backfill(cand, MODULES)
    assert hint == STRUCTURE_HINT_SINGLE
    assert "reason" not in evidence


def test_backfill_output_carries_no_expected_keys():
    """誠實邊界：hint 是證據不是判決——backfill 輸出不含任何 expected 期望值
    （不得把結構答案直接寫進 expected.action_count 之類）。"""
    hint, evidence = v3_structure_backfill(_cand(_module_name_rec("m-multi3")), MODULES)
    assert set(evidence) == {"note", "sources"} or set(evidence) == {"note", "sources", "reason"}
    assert "expected" not in evidence
    assert "action_count" not in evidence


# ── 3：確認題 vs 開放題（與旗標共用同一 hint 欄位）──────────────────────────

GM_PAIR_TEXT = "雙手抓握主板放至DIMM壓合治具"
CM_PAIR_TEXT = "雙手接觸DIMM壓合治具推至規定位置"
MULTI_TEXT = "右手抓握电动起子保持住至機箱"


def _draft_stub(raw: str, hint: str | None = None, reason: str | None = None) -> dict[str, Any]:
    norm = normalize(raw)
    stub: dict[str, Any] = {
        "plan": {
            "normalized_text": norm,
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "move_place",
                    "sequence_order": 1,
                    "evidence": [{"start": 0, "end": len(norm), "text": norm}],
                }
            ],
        },
        "challenge_tags": detect_challenge_tags(raw, norm),
        "expected": {"routing_status": "review"},
        "preannotation": {"routing_reasons": []},
    }
    if hint is not None:
        stub["v3_structure_hint"] = hint
        evidence: dict[str, Any] = {
            "note": "test",
            "sources": [
                {
                    "table": "motion_modules",
                    "id": "abcdef12-0000",
                    "detail": "name_zh (category=wi-template)",
                    "cycles": 2,
                    "v3_migrated": True,
                    "basis": "test",
                }
            ],
        }
        if reason:
            evidence["reason"] = reason
        stub["v3_structure_evidence"] = evidence
    return stub


def test_gm_pair_confirmation_question():
    """single_cycle hint → 取放建模改成確認題（預設單一 GM、IE 可推翻）。"""
    qs = "\n".join(_questions_for(_draft_stub(GM_PAIR_TEXT, hint=STRUCTURE_HINT_SINGLE)))
    assert "取放建模（確認題）" in qs
    assert "預設建成單一 GM" in qs
    assert "還是 acquire + move_place" not in qs, "確認題不得同時保留開放題句式"
    assert "可推翻" in qs, "覆核表必須明寫 IE 可推翻（hint 是證據不是判決）"


def test_gm_pair_multi_confirmation_question():
    qs = "\n".join(_questions_for(_draft_stub(GM_PAIR_TEXT, hint=structure_hint_multi(2))))
    assert "取放建模（確認題）" in qs
    assert "2 個" in qs
    assert "預設依此切成" in qs


def test_gm_pair_ambiguous_keeps_open_question():
    qs = "\n".join(
        _questions_for(
            _draft_stub(
                GM_PAIR_TEXT, hint=STRUCTURE_HINT_AMBIGUOUS, reason="conflicting_v3_structures"
            )
        )
    )
    assert "取放建模：" in qs, "ambiguous 必須維持開放題"
    assert "取放建模（確認題）" not in qs
    assert "conflicting_v3_structures" in qs, "矛盾證據要列給 IE"


def test_gm_pair_without_hint_keeps_open_question():
    """向後相容：無 hint 欄位（非本輪回填對象）→ 原開放題。"""
    qs = "\n".join(_questions_for(_draft_stub(GM_PAIR_TEXT)))
    assert "取放建模：" in qs
    assert "取放建模（確認題）" not in qs


def test_cm_pair_confirmation_question():
    qs = "\n".join(_questions_for(_draft_stub(CM_PAIR_TEXT, hint=STRUCTURE_HINT_SINGLE)))
    assert "取移建模（確認題）" in qs
    assert "預設建成單一 CM" in qs
    assert "取放建模" not in qs


def test_split_question_prefilled_from_hint():
    """likely_multi 的切分題：single_cycle hint 預填「預設依此」；ambiguous 維持開放。"""
    qs = _questions_for(_draft_stub(MULTI_TEXT, hint=STRUCTURE_HINT_SINGLE))
    assert "【v3 結構】" in qs[0] and "單一 cycle" in qs[0] and "預設依此" in qs[0]

    qs = _questions_for(
        _draft_stub(MULTI_TEXT, hint=STRUCTURE_HINT_AMBIGUOUS, reason="no_v3_structure_signal")
    )
    assert "維持開放題" in qs[0]

    qs = _questions_for(_draft_stub(MULTI_TEXT))
    assert "【v3 結構】" not in qs[0], "無 hint 不得憑空預填"


# ── 4：likely_multi 警語降級 ─────────────────────────────────────────────────


def test_likely_multi_caveat_downgraded():
    """v3 結構顯示單一 cycle ⇒「幾乎必然低估」對該筆降級（裁決 3 的 User 原話）。"""
    with_hint = _draft_stub(MULTI_TEXT, hint=STRUCTURE_HINT_SINGLE)
    line = _caveat_line_zh("likely_multi_action_undercounted", with_hint)
    assert line == _LIKELY_MULTI_DOWNGRADED_ZH
    assert "降級" in line and "單一 cycle" in line
    assert "幾乎必然低估" not in line or "降級" in line


def test_likely_multi_caveat_not_downgraded_without_single_hint():
    base = _CAVEAT_ZH["likely_multi_action_undercounted"]
    assert _caveat_line_zh("likely_multi_action_undercounted", _draft_stub(MULTI_TEXT)) == base
    assert (
        _caveat_line_zh(
            "likely_multi_action_undercounted",
            _draft_stub(MULTI_TEXT, hint=structure_hint_multi(3)),
        )
        == base
    ), "multi_cycle_n 不降級——多列結構反而支持「該切多個」"
    assert (
        _caveat_line_zh(
            "likely_multi_action_undercounted",
            _draft_stub(MULTI_TEXT, hint=STRUCTURE_HINT_AMBIGUOUS, reason="x"),
        )
        == base
    )


def test_other_caveats_untouched_by_hint():
    d = _draft_stub(MULTI_TEXT, hint=STRUCTURE_HINT_SINGLE)
    for c in ("take_place_pair_may_be_single_gm", "empty_lexicon_no_slot_candidates"):
        assert _caveat_line_zh(c, d) == _CAVEAT_ZH[c]
