"""「取必有放」lint 守門（D3-014 裁決 2；不需 DB）。

守什麼：

1. **不變式**：plan 含 acquire 而其後（同 plan 內）無任何收尾 action
   （move_place／release_return／controlled_move）＝命中 `acquire_without_place`。
2. **判定用 action_type 序列，不用文字啟發式**——R1 的教訓：動詞面會被名詞擊穿
   （「DIMM壓合治具」的「壓合」）；lint 完全不讀 normalized_text。
3. **WARN 邊界**：controlled_move 算收尾——CM 序列**無 P 參數**
   （`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：A B G M X I A），
   推/拉到位即完成取的閉合；且裁決 1 明言 acquire＋controlled_move 兩個 action
   是合法建模，標它「取而無放」會跟裁決 1 打架。composite_unknown **不算**收尾
   （判不出型不能宣稱「有放」）。
4. **單一出處**：preannotate 的旗標、覆核表的「取而無放」提問、schema 守門
   （tests/unit/test_gold_draft_schema.py）共用 `acquire_without_place` 同一函式。

mutation 證據（CI_GATES 規則 7）：把 `acquire_without_place` 的「其後」序列判定
拆掉（永遠回 False）→ 本檔真值表與 `test_question_shares_predicate` 必紅；把
`_questions_for` 的取而無放題改成自寫條件 → 條件漂移時 `test_question_shares_predicate`
必紅；把 `_CAVEAT_ZH` 的旗標說明刪掉 → `test_caveat_text_registered` 必紅。
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
    _questions_for,
    acquire_without_place,
    detect_challenge_tags,
)


def _a(action_type: str, order: int) -> dict[str, Any]:
    return {"action_id": f"a{order}", "action_type": action_type, "sequence_order": order}


# ── 1+3：真值表 ──────────────────────────────────────────────────────────────


def test_lone_acquire_is_flagged():
    """單一 acquire、無下游——正是「放在哪？」要問的情境（WARN，非必錯：g01 型）。"""
    assert acquire_without_place([_a("acquire", 1)]) is True


def test_acquire_then_move_place_is_closed():
    assert acquire_without_place([_a("acquire", 1), _a("move_place", 2)]) is False


def test_acquire_then_release_return_is_closed():
    assert acquire_without_place([_a("acquire", 1), _a("release_return", 2)]) is False


def test_acquire_then_controlled_move_is_closed():
    """裁決 1：acquire＋controlled_move 是合法建模（CM 無 P，M 即閉合）——不得誤標。"""
    assert acquire_without_place([_a("acquire", 1), _a("controlled_move", 2)]) is False


def test_acquire_then_process_or_inspect_still_open():
    assert acquire_without_place([_a("acquire", 1), _a("process", 2)]) is True
    assert acquire_without_place([_a("acquire", 1), _a("inspect", 2)]) is True


def test_composite_unknown_is_not_a_closer():
    """判不出型的 action 不能拿來宣稱「有放」。"""
    assert acquire_without_place([_a("acquire", 1), _a("composite_unknown", 2)]) is True


def test_closer_before_acquire_does_not_count():
    """「其後」是序列語意：放在取**之前**不算收尾（最後的取仍開著）。"""
    assert acquire_without_place([_a("move_place", 1), _a("acquire", 2)]) is True


def test_each_acquire_needs_downstream_closer():
    """拿A放X、再拿B（無收尾）→ 最後的 acquire 未閉合。"""
    assert (
        acquire_without_place([_a("acquire", 1), _a("move_place", 2), _a("acquire", 3)]) is True
    )
    # 拿A、拿B、放X：兩個 acquire 下游都有收尾 → 不命中
    assert (
        acquire_without_place([_a("acquire", 1), _a("acquire", 2), _a("move_place", 3)]) is False
    )


def test_no_acquire_no_flag():
    assert acquire_without_place([]) is False
    assert acquire_without_place([_a("move_place", 1), _a("inspect", 2)]) is False
    assert acquire_without_place([_a("composite_unknown", 1)]) is False


def test_sequence_order_not_list_order():
    """判定依 sequence_order 排序，不依 list 順序（IE 手編 JSON 順序不保證）。"""
    assert acquire_without_place([_a("move_place", 2), _a("acquire", 1)]) is False
    assert acquire_without_place([_a("acquire", 2), _a("move_place", 1)]) is True


# ── 2：不用文字啟發式 ────────────────────────────────────────────────────────


def test_lint_ignores_text_entirely():
    """同一 action 序列，句面有沒有「放」字都不影響——lint 只看 action_type。"""
    assert acquire_without_place(
        [{"action_id": "a1", "action_type": "acquire", "sequence_order": 1, "notes": "放置放置放置"}]
    ) is True


# ── 4：單一出處（旗標／提問共用同一判定）────────────────────────────────────


def _draft_stub(actions: list[dict[str, Any]]) -> dict[str, Any]:
    raw = "拿取排線"
    norm = normalize(raw)
    for a in actions:
        a.setdefault("evidence", [{"start": 0, "end": len(norm), "text": norm}])
    return {
        "plan": {"normalized_text": norm, "actions": actions},
        "challenge_tags": detect_challenge_tags(raw, norm),
        "expected": {"routing_status": "review"},
        "preannotation": {"routing_reasons": []},
    }


def test_question_shares_predicate():
    qs = "\n".join(_questions_for(_draft_stub([_a("acquire", 1)])))
    assert "取而無放" in qs
    assert "放」在哪" in qs

    qs = "\n".join(_questions_for(_draft_stub([_a("acquire", 1), _a("move_place", 2)])))
    assert "取而無放" not in qs


def test_caveat_text_registered():
    """旗標必須有中文說明（覆核表不得 fallback 成裸 key），且說清楚 WARN 邊界。"""
    text = _CAVEAT_ZH["acquire_without_place"]
    assert "取最後一定有放" in text
    assert "WARN" in text
    assert "下一句/下一列" in text, "邊界必須寫明：單句 acquire 可能合法"


async def test_preannotate_emits_flag_for_acquire_plan(monkeypatch):
    """preannotate 的旗標發射路徑（把 lint call 從 preannotate 拆掉 → 本測試紅）。

    誠實聲明：現行 rule planner 的 adapter 只會產 move_place／controlled_move／
    composite_unknown，**永遠不出 acquire**——所以本輪 60 筆草稿 0 命中是結構
    使然，不是 lint 沒作用。此測試 patch 掉 pipeline、餵一個 acquire plan，
    直接驗 preannotate 會掛旗標（IE 改 plan 後的 --recompile 同步另有
    test_gold_harvest_recompile 覆蓋）。"""
    import gold_harvest as gh

    from ddm_v2.nlp.contracts import (
        EvidenceSpan,
        PlannedAction,
        SourceRef,
        WorkInstructionPlan,
    )

    raw = "拿取排線"
    norm = normalize(raw)
    plan = WorkInstructionPlan(
        source_text=raw,
        normalized_text=norm,
        language="zh",
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={},
                evidence=[EvidenceSpan(start=0, end=len(norm), text=norm)],
            )
        ],
        dependencies=[],
        unresolved=[],
    )

    async def fake_pipeline(source_text, synonyms, rs):
        return plan, [], [], "review", []

    monkeypatch.setattr(gh, "run_pipeline", fake_pipeline)
    cand = gh.Candidate(norm=norm, raw=raw)
    cand.sources = [
        gh.SourceRecord(
            priority=2, table="wi_rows", row_id="w-1", detail="sub_activity",
            group_key="worksheet:ws-1", timestamp=None, raw=raw,
        )
    ]
    cand.tags = detect_challenge_tags(raw, norm)
    draft = await gh.preannotate(
        cand, synonyms=[], draft_id="d999_test", rs=None,
        split_component="worksheet:ws-1", module_structure={},
    )
    assert "acquire_without_place" in draft["preannotation_caveat"]
