"""「清潔」情境條件守門（D3-021；不需 DB）。

IE 第四輪裁決（2026-08-17，User 親答）：「清潔」→ `x_blow_clean` **僅限吹風
情境**（語料 4 筆全是風槍/吹風）。同義詞表是全域映射、不帶情境——情境守門在
harvest（仿 p_direction 情境規則模式）：lexicon 配出「清潔→x_blow_clean」而
句面無風槍/吹風脈絡 ⇒ 掛 `x_clean_context_unverified` 交 IE，**不無條件套用**；
該旗標無確認機制（IE 未裁非吹風情境的建法），轉正 fail-closed 擋下。

守什麼：

1. 判定單一出處 `x_clean_context_missing`：命中＋無脈絡 ⇒ True；有脈絡或
   無命中 ⇒ False（無命中時句面就算沒脈絡也不旗——沒有映射就沒有情境問題）。
2. preannotate 的旗標發射路徑：把旗標 call 拆掉 → `test_preannotate_emits_*` 紅。
3. 覆核表提問與 `_CAVEAT_ZH` 說明存在（旗標不是啞的）。
4. 轉正 fail-closed：帶旗標的草稿被 `caveat_resolution_blockers` 擋下。
5. repo 對應的同進同出守門在 test_gold_draft_schema.py（5i）——語料現況
   （2 筆「清潔」全在風槍脈絡）0 旗標是**判定的輸出**，不是旗標沒接。

mutation 證據（CI_GATES 規則 7）：
- 把 preannotate 的 `x_clean_context_missing` call（清潔情境旗標）拆掉 →
  `test_preannotate_emits_x_clean_flag_without_context` 紅。
- 把 `x_clean_context_missing` 的脈絡條件拆掉（無條件旗標/無條件套用）→
  `test_x_clean_no_flag_with_blow_context`（與 schema 5i 對 repo 草稿）紅。
- 把 `caveat_resolution_blockers` 的 fail-closed 分支拆掉 →
  `test_promotion_fail_closed_on_x_clean_flag` 紅。
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
    X_CLEAN_CONTEXT_CAVEAT,
    X_CLEAN_CONTEXT_TERMS,
    caveat_resolution_blockers,
    x_clean_context_missing,
)

_X_CLEAN_ENTRY = {
    "parameter": "X",
    "option_code": "x_blow_clean",
    "synonym_norm": "清潔",
    "priority": 0,
}
_G_ENTRY = {
    "parameter": "G",
    "option_code": "g_pick_sel",
    "synonym_norm": "拿取",
    "priority": 0,
}


# ── 1. 判定單一出處 ──────────────────────────────────────────────────────────


def test_x_clean_flag_when_hit_without_context():
    """映射命中＋句面無風槍/吹風 ⇒ 旗標（IE 只裁了吹風情境）。"""
    assert x_clean_context_missing(normalize("清潔外殼"), [_X_CLEAN_ENTRY]) is True


def test_x_clean_no_flag_with_blow_context():
    """句面有風槍或吹風脈絡 ⇒ 情境成立，不旗（語料 4 筆全屬此類）。"""
    for ctx in X_CLEAN_CONTEXT_TERMS:
        assert (
            x_clean_context_missing(normalize(f"拿取{ctx}清潔DIMM卡槽"), [_X_CLEAN_ENTRY])
            is False
        ), ctx


def test_x_clean_no_flag_without_mapping_hit():
    """沒配出「清潔→x_blow_clean」就沒有情境問題——句面無脈絡也不旗。"""
    assert x_clean_context_missing(normalize("清潔外殼"), []) is False
    assert x_clean_context_missing(normalize("清潔外殼"), [_G_ENTRY]) is False
    other_code = dict(_X_CLEAN_ENTRY, option_code="x_press")
    assert x_clean_context_missing(normalize("清潔外殼"), [other_code]) is False


# ── 2. preannotate 旗標發射路徑（pipeline patch，同 acquire lint 測試手法）──


def _fake_plan(raw: str):
    from ddm_v2.nlp.contracts import (
        EvidenceSpan,
        PlannedAction,
        SourceRef,
        WorkInstructionPlan,
    )

    norm = normalize(raw)
    return WorkInstructionPlan(
        source_text=raw,
        normalized_text=norm,
        language="zh",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="composite_unknown",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=len(norm), text=norm)],
            )
        ],
        dependencies=[],
        unresolved=[],
    )


async def _preannotate(raw: str, synonyms: list[dict[str, Any]], monkeypatch):
    import gold_harvest as gh

    plan = _fake_plan(raw)

    async def fake_pipeline(source_text, syns, rs):
        return plan, [], [], "review", []

    monkeypatch.setattr(gh, "run_pipeline", fake_pipeline)
    norm = normalize(raw)
    cand = gh.Candidate(norm=norm, raw=raw)
    cand.sources = [
        gh.SourceRecord(
            priority=2, table="wi_rows", row_id="w-1", detail="sub_activity",
            group_key="worksheet:ws-1", timestamp=None, raw=raw,
        )
    ]
    cand.tags = gh.detect_challenge_tags(raw, norm)
    return await gh.preannotate(
        cand, synonyms=synonyms, draft_id="d999_test", rs=None,
        split_component="worksheet:ws-1", module_structure={},
    )


async def test_preannotate_emits_x_clean_flag_without_context(monkeypatch):
    draft = await _preannotate("清潔外殼", [_X_CLEAN_ENTRY], monkeypatch)
    assert X_CLEAN_CONTEXT_CAVEAT in draft["preannotation_caveat"]


async def test_preannotate_no_flag_with_context_or_without_mapping(monkeypatch):
    draft = await _preannotate("拿取風槍清潔DIMM卡槽", [_X_CLEAN_ENTRY, _G_ENTRY], monkeypatch)
    assert X_CLEAN_CONTEXT_CAVEAT not in draft["preannotation_caveat"]
    draft = await _preannotate("清潔外殼", [], monkeypatch)
    assert X_CLEAN_CONTEXT_CAVEAT not in draft["preannotation_caveat"]


# ── 3. 旗標不是啞的：說明與提問 ──────────────────────────────────────────────


def test_x_clean_caveat_has_zh_and_question():
    text = _CAVEAT_ZH[X_CLEAN_CONTEXT_CAVEAT]
    assert "吹風情境" in text and "D3-021" in text
    from gold_harvest import _questions_for

    draft = {
        "plan": {
            "normalized_text": "清潔外殼",
            "actions": [
                {"action_id": "a1", "action_type": "composite_unknown"}
            ],
        },
        "challenge_tags": {},
        "preannotation_caveat": [X_CLEAN_CONTEXT_CAVEAT],
        "preannotation": {"routing_reasons": []},
        "expected": {"routing_status": "review"},
    }
    qs = _questions_for(draft)
    assert any(q.startswith("清潔情境：") for q in qs), "旗標必須帶覆核表提問"


# ── 4. 轉正 fail-closed ──────────────────────────────────────────────────────


def test_promotion_fail_closed_on_x_clean_flag():
    blockers = caveat_resolution_blockers(
        {"preannotation_caveat": [X_CLEAN_CONTEXT_CAVEAT], "ie_review": {}}
    )
    assert blockers and X_CLEAN_CONTEXT_CAVEAT in blockers[0]
    assert "吹風" in blockers[0]
