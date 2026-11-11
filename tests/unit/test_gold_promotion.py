"""草稿轉正（D3-019 首批 gold 轉正）的守門（不需 DB）。

守什麼：

1. **資格檢查是活的**（`promotion_blockers` 唯一出處）：切分未確認、判型/P
   方向/TMU=0 旗標未經 IE 確認、multi_cycle 確認但 plan 未重切、無實質內容
   （complete 帶 TMU>0 或顯式 expected_incomplete_reason）、S 檢失敗——任一
   即擋。合格案例通過（證明守門不是恆紅）。
2. **repo 現況自洽**：正式 gold 的非 seed 案例 ⟺ review-state 的
   `promoted_to` 標記**雙向一致**（搬走的 entry 標 promoted 不刪——軌跡保留；
   標記拆掉即紅）；每筆轉正案例重驗轉正不變量（caveat 全解、實質內容、
   結構一致、provenance、身分欄位、split 規則）。
3. **promoted_case_payload 是純轉換**：只動身分欄位、保留 plan/期望/覆核軌跡、
   草稿 id 進 notes 供追溯。

mutation 證據（CI_GATES 規則 7）：
- 把 `promotion_blockers` 的判型確認檢查拆掉 →
  `test_unconfirmed_typing_flag_blocks` 紅；未達標草稿混進轉正 →
  `test_repo_promoted_gold_passes_promotion_invariants` 紅。
- 把 state entry 的 `promoted_to` 標記拆掉（或正式 gold 多出無標記案例）→
  `test_repo_promoted_gold_matches_state_markers` 紅
  （`test_promoted_marker_removal_detected` 以 in-memory mutation 證明偵測活著）。
- 把 `substance_blockers` 的 `> 0` 改回 `is not None` →
  `test_zero_tmu_without_ruling_blocks` 紅。
- D3-022：ie_edited 草稿以未修改身分轉正 →
  `test_edited_draft_without_entry_declaration_blocks` 紅；重切 gold 的
  ie_modified 被改回 false（錯誤排除出 Plan 層指標）→
  `test_repo_ie_modified_promotions_pinned`＋test_planner_eval 分母釘值紅；
  d016（標題句不硬切）被轉正 →
  `test_repo_d016_title_sentence_stays_draft_not_promoted`／
  `test_resegmentation_ruling_blocks_promotion_fail_closed` 紅。
- D3-027（D3-026 複審 M2）：gold 端 reason 值要承重——
  `expected_incomplete_reason` 改壞值（複合 token 改序／自創 token／與裁決
  漂移）或 incomplete 案例的 issues_contain 清空 →
  `test_repo_expected_incomplete_reasons_bound_to_rulings` 紅
  （`test_reason_ruling_binding_mutations_detected` 以 in-memory mutation
  證明三種壞值逐一被抓；token 驗證與 state 檔共用
  `incomplete_ruling_canonical_error`，不抄第二份）。
- D3-027（D3-026 複審 L1）：轉正 notes 尾句硬寫「TMU=0 裁決見…」→
  `test_promoted_case_payload_notes_reflect_actual_aspects` 紅。
- D3-028：`acquire_without_place` 的裁決分支改成無條件放行 →
  `test_unresolved_lint_flag_blocks` 紅；分支刪掉（回到 else fail-closed，
  等於答了也沒用）→ `test_acquire_lint_clearing_rulings_resolve_flag` 紅；
  自創/已撤回裁決 token 被接受 →
  `test_acquire_lint_unknown_and_retracted_tokens_rejected` 紅。判型答案的
  gold（g55–g57）被錯當成重切族（或名單漂移）→
  `test_repo_ie_modified_promotions_pinned` 紅。
- D3-029（四類歸宿）：把 `genuinely_missing` 加進 `ACQUIRE_LINT_CLEARING_RULINGS`
  （或讓它落到放行路徑）→ `test_acquire_lint_genuinely_missing_still_blocks` 紅
  ——**建模錯誤的宣告不是通過條件**；四類名單漂移（改名/增減）→
  `test_acquire_lint_ruling_tokens_are_the_four_ie_categories` 紅；
  `tool_held` 自動推導（`acquire_lint_auto_ruling`）拆掉 →
  `test_acquire_lint_tool_held_auto_derived_from_dependency` 紅；反向驗證
  （`acquire_lint_tool_held_unexpressed`）拆掉、或把 `same_object`/`uses_tool`
  也當成工具持有證據 →
  `test_acquire_lint_tool_held_requires_dependency_when_expressible` 紅；
  反向驗證誤用在跨列持有（acquire 是 plan 最後一個 action）→
  `test_acquire_lint_tool_held_across_rows_not_blocked` 紅。
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ddm_v2.nlp.gold_eval import is_seed_gold_case
from ddm_v2.nlp.normalization import normalize

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "tests" / "gold" / "wi_plans"
DRAFT_DIR = ROOT / "tests" / "gold" / "wi_plans_draft"

sys.path.insert(0, str(ROOT / "scripts"))
from _seed_gold_baseline import IE_MODIFIED_GOLD_N, PROMOTED_GOLD_N  # noqa: E402
from gold_harvest import (  # noqa: E402
    ACQUIRE_LINT_CAVEAT,
    ACQUIRE_LINT_CLEARING_RULINGS,
    ACQUIRE_LINT_RETRACTED_RULINGS,
    ACQUIRE_LINT_RULING_GENUINELY_MISSING,
    ACQUIRE_LINT_RULING_TOKENS,
    ACQUIRE_LINT_RULING_TOOL_HELD,
    DRAFT_NOTES_BOILERPLATE,
    PROMOTION_SPLITS,
    RESEGMENTATION_RULING_TITLE_SENTENCE,
    REVIEW_SEGMENTATION_SOURCE_BATCH,
    REVIEW_STATE_FILENAME,
    TYPING_CHANGED_CAVEAT,
    ZERO_TMU_CAVEAT,
    ZERO_TMU_RULING_DISTANCE_UNSTATED,
    acquire_lint_auto_ruling,
    acquire_lint_tool_held_unexpressed,
    acquire_without_place,
    caveat_resolution_blockers,
    draft_sha8,
    incomplete_ruling_canonical_error,
    load_review_state,
    merge_review_state,
    promoted_case_payload,
    promotion_blockers,
    provenance_matches_normalized_text,
    review_block_from_entry,
    structure_consistency_blockers,
    substance_blockers,
)

IE = "IEC141289"


# ── fixture helpers（自建，不依賴 repo/DB 資料）──────────────────────────────


def _eligible_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """一筆「全部資格都滿足」的草稿＋entry（合併後帶 ie_review）。"""
    norm = normalize("雙手抓握主機板放至治具")
    sha = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    draft: dict[str, Any] = {
        "id": f"d001_{sha[:8]}",
        "source_text": norm,
        "review_status": "pending_ie",
        "approved_by": None,
        "plan_origin": "rule_based_v1_preannotation",
        "ie_modified": None,
        "split": None,
        "split_groups": ["module:m1"],
        "split_component": "module:m1",
        "source_provenance": [
            {"table": "motion_modules", "id": "mm-1", "raw_text": norm}
        ],
        "preannotation_caveat": [
            "take_place_pair_may_be_single_gm",
            TYPING_CHANGED_CAVEAT,
            "p_direction_single_default",
        ],
        "typing_change": {"noun_only_seq": None, "lexicon_seq": "GM"},
        "v3_structure_hint": "single_cycle",
        "v3_structure_evidence": {
            "note": "test",
            "sources": [
                {
                    "table": "motion_modules",
                    "id": "mm-1",
                    "detail": "name_zh (category=action)",
                    "cycles": 1,
                    "v3_migrated": True,
                    "basis": "test",
                }
            ],
        },
        "plan": {
            "normalized_text": norm,
            "actions": [{"action_id": "a1", "action_type": "move_place", "sequence_order": 1}],
        },
        "expected_cycles": [
            {"action_id": "a1", "complete": True, "seq": "GM", "total_tmu": 16.0}
        ],
        "expected": {"action_count": 1, "routing_status": "review"},
    }
    entry: dict[str, Any] = {
        "source_text": norm,
        "norm_sha256": sha,
        "v3_structure_hint_at_review": "single_cycle",
        "segmentation_confirmed_by": IE,
        "segmentation_confirmed_date": "2026-08-16",
        "segmentation_source": "v3_structure_confirmed",
        "ie_modified": False,
        "typing_confirmed_by": IE,
        "typing_confirmed_date": "2026-08-17",
        "typing_change_at_review": {"noun_only_seq": None, "lexicon_seq": "GM"},
        "p_direction_confirmed_by": IE,
        "p_direction_confirmed_date": "2026-08-17",
        "p_direction_caveat_at_review": "p_direction_single_default",
    }
    applied, stale = merge_review_state([draft], {sha[:8]: entry})
    assert applied == [draft["id"]] and stale == [], "前提：合併必須成功"
    return draft, entry


# ── 1. 資格檢查（promotion_blockers 唯一出處） ───────────────────────────────


def test_eligible_draft_passes():
    draft, entry = _eligible_pair()
    assert promotion_blockers(draft, entry) == [], "合格案例必須通過（守門不是恆紅）"


def test_missing_entry_blocks():
    draft, _entry = _eligible_pair()
    blockers = promotion_blockers(draft, None)
    assert any("無對應 entry" in b for b in blockers)


def test_already_promoted_entry_blocks():
    """冪等：同一句不得二次轉正。"""
    draft, entry = _eligible_pair()
    entry = {**entry, "promoted_to": "g99_dup", "promoted_date": "2026-08-17"}
    blockers = promotion_blockers(draft, entry)
    assert any("promoted_to" in b for b in blockers)


def test_unconfirmed_typing_flag_blocks():
    """mutation 證據：判型旗標沒有 IE 確認 → 擋（資格檢查拆掉本測試必紅）。"""
    draft, entry = _eligible_pair()
    del draft["ie_review"]["typing_confirmed_by"]
    del draft["ie_review"]["typing_confirmed_date"]
    blockers = promotion_blockers(draft, entry)
    assert any("判型修正未經 IE 確認" in b for b in blockers)


def test_unconfirmed_p_direction_flag_blocks():
    draft, entry = _eligible_pair()
    del draft["ie_review"]["p_direction_confirmed_by"]
    del draft["ie_review"]["p_direction_confirmed_date"]
    blockers = promotion_blockers(draft, entry)
    assert any("P 方向數未經 IE 確認" in b for b in blockers)


def test_zero_tmu_without_ruling_blocks():
    """TMU=0.0 無裁決 → 擋（空殼守門 `> 0` 改回 `is not None` 本測試必紅）；
    有裁決（expected_incomplete_reason 路徑）→ 過。"""
    draft, entry = _eligible_pair()
    draft["expected_cycles"][0]["total_tmu"] = 0.0
    draft["preannotation_caveat"].append(ZERO_TMU_CAVEAT)
    blockers = promotion_blockers(draft, entry)
    assert any("TMU=0.0 未經 IE 裁決" in b for b in blockers)
    assert any("expected_incomplete_reason" in b for b in blockers)

    # IE 裁決 distance_unstated → 重新合併 → reason 落草稿 → 通過
    entry2 = {
        **entry,
        "zero_tmu_ruling": ZERO_TMU_RULING_DISTANCE_UNSTATED,
        "zero_tmu_ruled_by": IE,
        "zero_tmu_ruled_date": "2026-08-17",
    }
    draft.pop("ie_review")
    applied, stale = merge_review_state([draft], {entry2["norm_sha256"][:8]: entry2})
    assert applied and not stale
    assert draft["expected_incomplete_reason"] == ZERO_TMU_RULING_DISTANCE_UNSTATED
    assert promotion_blockers(draft, entry2) == []


def test_substance_guard_rejects_zero_tmu_as_substance():
    """mutation 證據（隔離 substance 守門）：complete 但 TMU=0.0 且無 reason
    ——`substance_blockers` 必擋；把 `> 0` 改回 `is not None`，本測試必紅。"""
    case = {
        "expected_cycles": [
            {"action_id": "a1", "complete": True, "seq": "CM", "total_tmu": 0.0}
        ],
    }
    assert substance_blockers(case), "TMU=0.0 不是實質內容（D3-018 M1）"
    # reason 路徑放行（誠實記錄資訊不足）
    case["expected_incomplete_reason"] = ZERO_TMU_RULING_DISTANCE_UNSTATED
    assert substance_blockers(case) == []
    # TMU>0 路徑放行
    del case["expected_incomplete_reason"]
    case["expected_cycles"][0]["total_tmu"] = 3.0
    assert substance_blockers(case) == []


def test_incomplete_ruling_case_eligible_via_honest_reason():
    """D3-026（第五批）：incomplete 草稿（missing_core_m、無 TMU）本身撞
    substance 守門；IE 的 incomplete 裁決合併後（expected_incomplete_reason
    ＝逐型釘值）＝誠實轉正路徑放行。mutation：apply 的 reason 寫入拆掉 →
    本測紅（substance blocker 仍在）。"""
    draft, entry = _eligible_pair()
    # 改成 X/I 型 CM 句形狀：incomplete、無 TMU
    draft["plan"]["actions"] = [
        {"action_id": "a1", "action_type": "controlled_move", "sequence_order": 1}
    ]
    draft["expected_cycles"] = [
        {"action_id": "a1", "complete": False, "seq": "CM",
         "issues_contain": ["missing_core_m"]}
    ]
    blockers = promotion_blockers(draft, entry)
    assert any("expected_incomplete_reason" in b for b in blockers), (
        "incomplete 無 reason 必須先被空殼守門擋住（前提）"
    )

    entry2 = {
        **entry,
        "incomplete_ruling": "distance_unstated+x_seconds_required",
        "incomplete_ruled_by": IE,
        "incomplete_ruled_date": "2026-08-17",
    }
    draft.pop("ie_review")
    applied, stale = merge_review_state([draft], {entry2["norm_sha256"][:8]: entry2})
    assert applied and not stale
    assert draft["expected_incomplete_reason"] == "distance_unstated+x_seconds_required"
    assert promotion_blockers(draft, entry2) == []


def test_multi_cycle_confirmed_but_plan_not_resegmented_blocks():
    """切分確認為 multi_cycle_n 而 plan 仍 1 action（rule planner 恆單 action）
    → 原樣轉正＝把 IE 已否定的切分寫進標準答案——必擋。"""
    draft, entry = _eligible_pair()
    draft["v3_structure_hint"] = "multi_cycle_2"
    draft["v3_structure_evidence"]["sources"][0]["cycles"] = 2
    entry2 = {**entry, "v3_structure_hint_at_review": "multi_cycle_2"}
    draft.pop("ie_review")
    applied, stale = merge_review_state([draft], {entry2["norm_sha256"][:8]: entry2})
    assert applied and not stale
    blockers = promotion_blockers(draft, entry2)
    assert any("plan 未重切" in b for b in blockers)


def _batch_eligible_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """批次確認（D3-021）下全資格滿足的草稿＋entry：無切分爭點（無旗標、
    無 v3 hint）、有實質內容、S 檢通過。"""
    norm = normalize("鎖附螺絲並確認")
    sha = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    draft: dict[str, Any] = {
        "id": f"d002_{sha[:8]}",
        "source_text": norm,
        "review_status": "pending_ie",
        "approved_by": None,
        "plan_origin": "rule_based_v1_preannotation",
        "ie_modified": None,
        "split": None,
        "split_groups": ["module:m2"],
        "split_component": "module:m2",
        "source_provenance": [
            {"table": "motion_modules", "id": "mm-2", "raw_text": norm}
        ],
        "preannotation_caveat": [],
        "plan": {
            "normalized_text": norm,
            "actions": [
                {"action_id": "a1", "action_type": "controlled_move", "sequence_order": 1}
            ],
        },
        "expected_cycles": [
            {"action_id": "a1", "complete": True, "seq": "CM", "total_tmu": 21.0}
        ],
        "expected": {"action_count": 1, "routing_status": "review"},
    }
    entry: dict[str, Any] = {
        "source_text": norm,
        "norm_sha256": sha,
        "v3_structure_hint_at_review": None,
        "segmentation_confirmed_by": IE,
        "segmentation_confirmed_date": "2026-08-17",
        "segmentation_source": REVIEW_SEGMENTATION_SOURCE_BATCH,
        "ie_modified": False,
    }
    applied, stale = merge_review_state([draft], {sha[:8]: entry})
    assert applied == [draft["id"]] and stale == [], "前提：批次確認合併必須成功"
    return draft, entry


def test_batch_confirmed_eligible_draft_passes():
    """批次切分確認＋實質內容＝合格（守門不是恆紅）；轉正後 gold 檔的
    ie_review 保留批次來源（與逐筆確認可區分的軌跡）。"""
    draft, entry = _batch_eligible_pair()
    assert promotion_blockers(draft, entry) == []
    assert draft["ie_review"]["segmentation_source"] == REVIEW_SEGMENTATION_SOURCE_BATCH


def test_batch_confirmed_multi_action_plan_blocks():
    """批次確認的對象＝單 action 現狀；plan 若是多 action，「無爭點」前提
    本身有假——結構一致性擋（把批次來源在 structure_consistency_blockers
    併回 v3 hint 分支 → hint 為 None 誤放行 → 本測試紅）。"""
    draft, entry = _batch_eligible_pair()
    draft["plan"]["actions"].append(
        {"action_id": "a2", "action_type": "move_place", "sequence_order": 2}
    )
    blockers = structure_consistency_blockers(draft)
    assert blockers and "plan 未重切" in blockers[0]
    assert any("plan 未重切" in b for b in promotion_blockers(draft, entry))


def _lint_pair(
    *, dependencies: list[dict[str, Any]] | None = None, lone: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    """帶 `acquire_without_place` 旗標的合格草稿＋entry（plan 真的有未閉合的
    acquire——旗標與 plan 必須同進同出，不是把字串塞進 caveat 就算）。

    `lone=True`＝plan 只有那個 acquire（跨列持有情境：dependency 表達不了）；
    否則 a1 acquire ＋ a2 process（同 plan 內可用 tool_held_for 表達）。"""
    draft, entry = _eligible_pair()
    actions = [{"action_id": "a1", "action_type": "acquire", "sequence_order": 1}]
    if not lone:
        actions.append(
            {"action_id": "a2", "action_type": "process", "sequence_order": 2}
        )
    draft["plan"]["actions"] = actions
    draft["plan"]["dependencies"] = list(dependencies or [])
    draft["expected"]["action_count"] = len(actions)
    draft["v3_structure_hint"] = f"multi_cycle_{len(actions)}" if not lone else "single_cycle"
    entry["v3_structure_hint_at_review"] = draft["v3_structure_hint"]
    draft["preannotation_caveat"].append(ACQUIRE_LINT_CAVEAT)
    assert acquire_without_place(draft["plan"]["actions"]), "前提：旗標必須真的命中"
    return draft, entry


def _ruled_via_state(
    draft: dict[str, Any], entry: dict[str, Any], ruling: str, tmp_path: Path
) -> dict[str, Any]:
    """把裁決寫進 state 檔往返一趟（形狀驗證＋投影規則都走真程式碼，不是測試
    自己捏形狀），回傳載入後的 entry；草稿的 ie_review 同步更新。"""
    ruled = {
        **entry,
        "acquire_lint_ruling": ruling,
        "acquire_lint_ruled_by": IE,
        "acquire_lint_ruled_date": "2026-08-17",
    }
    state = {
        "schema_version": "wi-review-state-v1",
        "entries": {entry["norm_sha256"][:8]: ruled},
    }
    path = tmp_path / REVIEW_STATE_FILENAME
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    loaded = load_review_state(path)[entry["norm_sha256"][:8]]
    draft["ie_review"] = review_block_from_entry(loaded)
    return loaded


def test_unresolved_lint_flag_blocks():
    """acquire_without_place（取而無放）沒有 IE 裁決＝未解決的覆核提問，
    fail-closed（D3-028 加了裁決機制、D3-029 擴成四類，**沒答案時照舊擋**）。"""
    draft, entry = _lint_pair(lone=True)
    blockers = promotion_blockers(draft, entry)
    assert any(ACQUIRE_LINT_CAVEAT in b for b in blockers)
    assert any("未經 IE 裁決" in b for b in blockers)


@pytest.mark.parametrize("ruling", sorted(ACQUIRE_LINT_CLEARING_RULINGS))
def test_acquire_lint_clearing_rulings_resolve_flag(ruling: str, tmp_path: Path):
    """對照組（D3-029）：三類**合法歸宿**各自解除旗標、可轉正。

    D3-028 只有一個合法 token，所以「填錯類別會怎樣」測不出來；四類之後每類
    各一條——三類放行、`genuinely_missing` 照擋（下一條），少任一條都證明不了
    守門沒被拆成恆過/恆擋。`tool_held` 用跨列持有情境（plan 內表達不了
    dependency，反向驗證不適用；可表達卻沒表達的情形另測）。"""
    draft, entry = _lint_pair(lone=True)
    loaded = _ruled_via_state(draft, entry, ruling, tmp_path)
    assert promotion_blockers(draft, loaded) == []


def test_acquire_lint_genuinely_missing_still_blocks(tmp_path: Path):
    """**D3-029 的核心**：`genuinely_missing`（建模錯誤——取了之後物件消失）
    是合法的**裁決值**（state 檔收）但**不解除轉正阻擋**——它是「這筆錯了」的
    宣告，不是通過條件。

    mutation：把 `genuinely_missing` 加進 `ACQUIRE_LINT_CLEARING_RULINGS`
    （或在 acquire_lint_blockers 裡讓它落到放行路徑）→ 本測試紅。"""
    draft, entry = _lint_pair(lone=True)
    loaded = _ruled_via_state(
        draft, entry, ACQUIRE_LINT_RULING_GENUINELY_MISSING, tmp_path
    )
    assert loaded["acquire_lint_ruling"] == ACQUIRE_LINT_RULING_GENUINELY_MISSING, (
        "前提：state 檔必須收得下這個值（它是四類之一，不是壞值）"
    )
    blockers = promotion_blockers(draft, loaded)
    assert any(ACQUIRE_LINT_RULING_GENUINELY_MISSING in b for b in blockers)
    assert any("不是通過條件" in b for b in blockers)
    assert ACQUIRE_LINT_RULING_GENUINELY_MISSING not in ACQUIRE_LINT_CLEARING_RULINGS


def test_acquire_lint_unknown_and_retracted_tokens_rejected(tmp_path: Path):
    """fail-closed 兩層：state 檔擋自創/已撤回 token（IE 沒定義過的歸宿不得
    登記）；正式 gold 的 ie_review 不經 load_review_state，轉正端再擋一次。"""
    draft, entry = _lint_pair(lone=True)
    for bad_token in ("whatever_the_ie_probably_meant", ACQUIRE_LINT_RETRACTED_RULINGS[0]):
        with pytest.raises(SystemExit, match="acquire_lint_ruling"):
            _ruled_via_state(draft, entry, bad_token, tmp_path)
    # 第二層：繞過 state 檔直接寫進 gold 的 ie_review 也要擋
    draft["ie_review"] = {
        **draft["ie_review"],
        "acquire_lint_ruling": "whatever_the_ie_probably_meant",
    }
    assert any("fail-closed" in b for b in caveat_resolution_blockers(draft))


def test_acquire_lint_tool_held_auto_derived_from_dependency():
    """D3-029 要求 4：plan 已標 `tool_held_for` ⇒ 裁決自動推得 `tool_held`，
    **不必 IE 逐筆答**（g02「拿取電動起子…鎖附兩顆螺絲」即此型）。

    對照：拆掉 dependency 就回到「未經 IE 裁決」擋下——自動推導綁的是 plan
    真的表達了工具持有，不是無條件放行。"""
    dep = [{"from_action": "a1", "to_action": "a2", "type": "tool_held_for"}]
    draft, entry = _lint_pair(dependencies=dep)
    assert acquire_lint_auto_ruling(draft["plan"]) == ACQUIRE_LINT_RULING_TOOL_HELD
    assert promotion_blockers(draft, entry) == [], "plan 已表達工具持有 → 免答"

    draft["plan"]["dependencies"] = []
    assert acquire_lint_auto_ruling(draft["plan"]) is None
    assert any("未經 IE 裁決" in b for b in promotion_blockers(draft, entry))


@pytest.mark.parametrize(
    ("dep_type", "expect_blocked"),
    [
        ("tool_held_for", False),
        # same_object／uses_tool 不主張物件停在手上（放好後再作業／只是用到
        # 工具）——自動推導與反向驗證都只認 tool_held_for
        ("same_object", True),
        ("uses_tool", True),
    ],
)
def test_acquire_lint_tool_held_requires_dependency_when_expressible(
    dep_type: str, expect_blocked: bool, tmp_path: Path
):
    """`tool_held` 的反向驗證（D3-029 要求 4）：同 plan 內**可表達卻沒表達**
    `tool_held_for` ⇒ 擋。裁決宣稱工具留在手上，compile 端 `is_tool_held`
    卻不會生效，後續 action 的 G 會被當成重新抓取——裁決與 TMU 不一致。"""
    dep = [{"from_action": "a1", "to_action": "a2", "type": dep_type}]
    draft, entry = _lint_pair(dependencies=dep)
    loaded = _ruled_via_state(draft, entry, ACQUIRE_LINT_RULING_TOOL_HELD, tmp_path)
    blockers = promotion_blockers(draft, loaded)
    if expect_blocked:
        assert any("tool_held_for" in b for b in blockers)
        assert acquire_lint_tool_held_unexpressed(draft["plan"]) == ["a1"]
    else:
        assert blockers == []
        assert acquire_lint_tool_held_unexpressed(draft["plan"]) == []


def test_acquire_lint_tool_held_across_rows_not_blocked(tmp_path: Path):
    """邊界：acquire 是 plan 最後一個 action＝跨列持有（g08「右手抓握電動起子
    保持住至機箱」下一列才鎖附）——dependency 是 plan 內的，跨列表達不了，
    此時 `tool_held` 合法且不擋（擋了合法的跨列持有就無路可走）。"""
    draft, entry = _lint_pair(lone=True)
    loaded = _ruled_via_state(draft, entry, ACQUIRE_LINT_RULING_TOOL_HELD, tmp_path)
    assert acquire_lint_tool_held_unexpressed(draft["plan"]) == []
    assert promotion_blockers(draft, loaded) == []


def test_acquire_lint_ruling_tokens_are_the_four_ie_categories():
    """四類歸宿的名單釘值（IE 2026-08-17 裁決）：多一類/少一類/改名都要有人
    看見——token 是寫進 review-state 與正式 gold 的標準答案值。"""
    assert ACQUIRE_LINT_RULING_TOKENS == (
        "placed",
        "consumed_by_later_action",
        "tool_held",
        "genuinely_missing",
    )
    assert ACQUIRE_LINT_CLEARING_RULINGS == set(ACQUIRE_LINT_RULING_TOKENS[:3])


def test_unknown_caveat_blocks_fail_closed():
    draft, entry = _eligible_pair()
    draft["preannotation_caveat"].append("some_future_flag")
    blockers = promotion_blockers(draft, entry)
    assert any("some_future_flag" in b for b in blockers)


def test_unmerged_review_state_blocks():
    draft, entry = _eligible_pair()
    draft.pop("ie_review")
    blockers = promotion_blockers(draft, entry)
    assert any("無 ie_review" in b for b in blockers)


def test_provenance_mismatch_blocks():
    """S 檢：換句不換 provenance → 擋。"""
    draft, entry = _eligible_pair()
    fictional = "左手虛構一個不存在的動作句"
    draft["plan"]["normalized_text"] = fictional
    # sha 完整性會先炸——這裡直接打 S 檢函式與 blockers 的組合語意
    assert not provenance_matches_normalized_text(draft)


# ── 1b. D3-022：IE 重切（ie_modified=true）的轉正路徑 ────────────────────────


def _ie_modified_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """模擬 D3-022 重切後的合格草稿＋entry：plan 2 action（ie_edited）、
    entry 宣告 ie_modified=true＋切分裁決 multi_cycle_2（重切後結構）。"""
    draft, entry = _eligible_pair()
    entry = {
        **entry,
        "ie_modified": True,
        "segmentation_source": "ie_ruling",
        "ie_ruling": "multi_cycle_2",
        "ie_ruling_notes": "D3-022 測試：重切為 2 段誠實 span",
    }
    norm = draft["plan"]["normalized_text"]
    draft["review_status"] = "ie_edited"
    draft["notes"] = "IE 重切（測試）：涵蓋對應記於此"
    draft["plan"]["actions"] = [
        {"action_id": "a1", "action_type": "acquire", "sequence_order": 1,
         "evidence": [{"start": 0, "end": 4, "text": norm[0:4]}]},
        {"action_id": "a2", "action_type": "move_place", "sequence_order": 2,
         "evidence": [{"start": 4, "end": len(norm), "text": norm[4:]}]},
    ]
    draft["expected_cycles"] = [
        {"action_id": "a1", "complete": True, "seq": "GM", "total_tmu": 10.0},
        {"action_id": "a2", "complete": True, "seq": "GM", "total_tmu": 16.0},
    ]
    draft["expected"] = {"action_count": 2, "routing_status": "review"}
    draft["ie_review"] = review_block_from_entry(entry)
    return draft, entry


def test_ie_modified_reseg_eligible_and_payload_carries_flag():
    """D3-022：重切草稿（entry 宣告 ie_modified=true＋ie_edited＋結構一致）
    可走工具轉正；payload 的 ie_modified 以 entry 為準（true＝計入 Plan 層
    指標），IE 留在 notes 的涵蓋對應保留、轉正註記附加。"""
    draft, entry = _ie_modified_pair()
    assert promotion_blockers(draft, entry) == []
    payload = promoted_case_payload(
        draft, new_id="g98_reseg", approved_by=IE,
        approved_date="2026-08-17", split="test", ie_modified=True,
    )
    assert payload["ie_modified"] is True, "重切轉正必須保留 ie_modified=true（真 ground truth）"
    assert "IE 重切（測試）" in payload["notes"], "IE 的 notes 內容不得被轉正註記蓋掉"
    assert draft["id"] in payload["notes"], "草稿 id 仍須進 notes 供追溯"
    # 未宣告時預設 false（原樣核准路徑不變）；管線樣板 notes 直接被取代
    draft2, _ = _eligible_pair()
    draft2["notes"] = DRAFT_NOTES_BOILERPLATE
    payload2 = promoted_case_payload(
        draft2, new_id="g97_plain", approved_by=IE,
        approved_date="2026-08-17", split="test",
    )
    assert payload2["ie_modified"] is False
    assert DRAFT_NOTES_BOILERPLATE not in payload2["notes"]


def test_edited_draft_without_entry_declaration_blocks():
    """mutation 證據（D3-022）：ie_edited 草稿但 entry 未宣告 ie_modified=true
    → 擋——編輯過的 plan 以「未修改」身分轉正會被 Plan 層指標錯誤排除
    （真 ground truth 被丟掉）。"""
    draft, entry = _ie_modified_pair()
    entry2 = {**entry, "ie_modified": False}
    draft["ie_review"] = review_block_from_entry(entry2)
    blockers = promotion_blockers(draft, entry2)
    assert any("不得以未修改身分轉正" in b for b in blockers)


def test_entry_declared_modified_but_draft_not_edited_blocks():
    """反方向：entry 宣告 ie_modified=true 但草稿不是 ie_edited → 擋
    （「IE 改過」的宣告掛在管線原樣 plan 上＝說謊）。"""
    draft, entry = _eligible_pair()
    entry2 = {**entry, "ie_modified": True}
    blockers = promotion_blockers(draft, entry2)
    assert any("review_status 非 ie_edited" in b for b in blockers)


def test_resegmentation_ruling_blocks_promotion_fail_closed():
    """mutation 證據（D3-022 d016 型）：entry 帶 title_sentence_no_resegmentation
    → 即使其他資格全滿足也擋——「d016 被錯誤轉正」必紅。"""
    draft, entry = _eligible_pair()
    entry2 = {
        **entry,
        "resegmentation_ruling": RESEGMENTATION_RULING_TITLE_SENTENCE,
        "resegmentation_ruled_by": IE,
        "resegmentation_ruled_date": "2026-08-17",
    }
    draft["ie_review"] = review_block_from_entry(entry2)
    blockers = promotion_blockers(draft, entry2)
    assert any("resegmentation_ruling" in b for b in blockers), (
        "IE 裁決「不硬切、不轉正」的案例竟然可轉正——fail-closed 守門死了"
    )


# ── 2. promoted_case_payload（純轉換） ───────────────────────────────────────


def test_promoted_case_payload_transform():
    draft, _entry = _eligible_pair()
    before = copy.deepcopy(draft)
    payload = promoted_case_payload(
        draft,
        new_id="g99_test_case",
        approved_by=IE,
        approved_date="2026-08-17",
        split="test",
    )
    assert payload["id"] == "g99_test_case"
    assert payload["approved_by"] == IE
    assert payload["approved_date"] == "2026-08-17"
    assert payload["review_status"] == "approved"
    assert payload["ie_modified"] is False, "原樣核准（確認≠修改）"
    assert payload["split"] == "test"
    assert before["id"] in payload["notes"], "草稿 id 必須進 notes 供追溯"
    assert "不可外推" in payload["notes"], "challenge-oversampled 但書必須跟著檔案走"
    # 內容不動：plan／期望／覆核軌跡原樣保留
    assert payload["plan"] == before["plan"]
    assert payload["expected_cycles"] == before["expected_cycles"]
    assert payload["ie_review"] == before["ie_review"]
    assert payload["source_provenance"] == before["source_provenance"]
    assert draft == before, "promoted_case_payload 必須是純轉換（不就地改草稿）"


def test_promoted_case_payload_notes_reflect_actual_aspects():
    """D3-027（D3-026 複審 L1）：轉正 notes 尾句依**實際存在的覆核面向**生成
    ——沒有 TMU=0 裁決的案例不得宣稱「TMU=0 裁決見…」（樣板謊言）。
    mutation：樣板改回硬寫固定尾句 → 本測紅。"""
    # 無任何裁決（只有切分/判型/P 方向確認）→ 兩種裁決都不得被宣稱
    draft, _entry = _eligible_pair()
    payload = promoted_case_payload(
        draft, new_id="g96_notes_aspects", approved_by=IE,
        approved_date="2026-08-17", split="test",
    )
    assert "TMU=0 裁決" not in payload["notes"], "沒有的裁決不得寫進 notes"
    assert "incomplete 裁決" not in payload["notes"]
    for claimed in ("切分確認", "判型確認", "P 方向數確認"):
        assert claimed in payload["notes"], f"實際存在的面向 {claimed} 要被指出"
    # incomplete 裁決案例（D3-026 第五批形狀）→ 宣稱 incomplete、不宣稱 TMU=0
    draft2, _e2 = _eligible_pair()
    draft2["ie_review"]["incomplete_ruling"] = "distance_unstated"
    payload2 = promoted_case_payload(
        draft2, new_id="g95_notes_inc", approved_by=IE,
        approved_date="2026-08-17", split="test",
    )
    assert "incomplete 裁決" in payload2["notes"]
    assert "TMU=0 裁決" not in payload2["notes"]


# ── 3. repo 現況自洽（讀已 commit 檔案） ─────────────────────────────────────


def _gold_cases() -> dict[str, dict[str, Any]]:
    return {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(GOLD_DIR.glob("*.json"))
    }


def _state_entries() -> dict[str, dict[str, Any]]:
    state_path = DRAFT_DIR / REVIEW_STATE_FILENAME
    if not state_path.exists():
        pytest.skip("repo 無 review-state.json")
    return load_review_state(state_path)


def test_repo_promoted_gold_matches_state_markers():
    """雙向同進同出：非 seed 正式 gold ⟺ state entry 的 promoted_to。

    - entry 標了 promoted_to 但正式 gold 沒有該檔＝標記指向幽靈；
    - 正式 gold 有非 seed 案例但無 entry 標記＝繞過轉正工作流混入。
    promoted 標記拆掉，本測試必紅。"""
    entries = _state_entries()
    promoted = {
        e["promoted_to"]: (sha8, e)
        for sha8, e in entries.items()
        if e.get("promoted_to")
    }
    non_seed = {
        str(d["id"]): d for d in _gold_cases().values() if not is_seed_gold_case(d)
    }
    assert set(promoted) == set(non_seed), (
        f"promoted 標記與正式 gold 不一致：只在 state={sorted(set(promoted) - set(non_seed))}"
        f"；只在 gold={sorted(set(non_seed) - set(promoted))}"
    )
    assert len(promoted) == PROMOTED_GOLD_N, "轉正筆數釘值（_seed_gold_baseline）漂移"
    for gold_id, (sha8, entry) in promoted.items():
        d = non_seed[gold_id]
        norm = d["plan"]["normalized_text"]
        assert hashlib.sha256(norm.encode("utf-8")).hexdigest() == entry["norm_sha256"], (
            f"{gold_id}：正式 gold 的句子與 promoted entry 的 sha 不符"
        )
        assert d.get("approved_date") == entry["promoted_date"], (
            f"{gold_id}：approved_date 與 promoted_date 不一致"
        )
        assert (GOLD_DIR / f"{gold_id}.json").exists()


def test_promoted_marker_removal_detected():
    """mutation 證據（in-memory）：拆掉任一 promoted_to 標記 → 雙向比對必失衡。"""
    entries = _state_entries()
    promoted_ids = {e["promoted_to"] for e in entries.values() if e.get("promoted_to")}
    if not promoted_ids:
        pytest.skip("尚無轉正 entry")
    mutated = copy.deepcopy(entries)
    victim = next(
        sha8 for sha8, e in sorted(mutated.items()) if e.get("promoted_to")
    )
    removed_id = mutated[victim].pop("promoted_to")
    mutated[victim].pop("promoted_date", None)
    still_marked = {e.get("promoted_to") for e in mutated.values() if e.get("promoted_to")}
    non_seed_ids = {
        str(d["id"]) for d in _gold_cases().values() if not is_seed_gold_case(d)
    }
    assert removed_id in non_seed_ids and removed_id not in still_marked, (
        "拆掉標記後雙向比對竟然還平衡——偵測死了"
    )


def test_repo_promoted_gold_passes_promotion_invariants():
    """每筆轉正案例重驗轉正不變量——未達標草稿混進正式 gold 就在這裡紅。
    末段以 in-memory mutation 證明檢查是活的。"""
    entries = _state_entries()
    by_promoted = {
        e["promoted_to"]: e for e in entries.values() if e.get("promoted_to")
    }
    non_seed = [d for d in _gold_cases().values() if not is_seed_gold_case(d)]
    if not non_seed:
        pytest.skip("尚無轉正案例")
    for d in non_seed:
        gid = str(d["id"])
        entry = by_promoted.get(gid)
        assert entry is not None, f"{gid}：無 promoted entry（另測已擋，防連鎖誤導）"
        assert d.get("approved_by") not in (None, "", "seed")
        assert d.get("review_status") == "approved"
        # D3-022 起 ie_modified 分兩類：宣告的唯一出處＝state entry——
        # false＝原樣核准（自我指涉排除）；true＝IE 重切（計入 Plan 層指標）。
        # gold 檔與 entry 漂移＝指標分母被竄改。
        assert isinstance(d.get("ie_modified"), bool)
        assert d.get("ie_modified") == bool(entry.get("ie_modified")), (
            f"{gid}：gold 檔 ie_modified 與 state entry 宣告不一致（自我指涉防線）"
        )
        assert isinstance(d.get("plan_origin"), str) and d["plan_origin"]
        assert d.get("split") in PROMOTION_SPLITS
        assert d.get("split_component"), f"{gid}：split_component 稽核憑據不得剝除"
        assert caveat_resolution_blockers(d) == [], f"{gid}：caveat 未全解"
        assert substance_blockers(d) == [], f"{gid}：無實質內容"
        assert structure_consistency_blockers(d) == [], f"{gid}：切分結構與 plan 不一致"
        assert provenance_matches_normalized_text(d), f"{gid}：S 檢失敗"
        assert d.get("ie_review") == review_block_from_entry(entry), (
            f"{gid}：ie_review 與 promoted entry 投影不一致"
        )

    # mutation：把一筆帶判型旗標案例的確認剝掉 → caveat 檢查必紅（證明活著）
    sample = next(
        (d for d in non_seed if TYPING_CHANGED_CAVEAT in (d.get("preannotation_caveat") or [])),
        None,
    )
    if sample is not None:
        mutated = copy.deepcopy(sample)
        mutated["ie_review"].pop("typing_confirmed_by", None)
        assert caveat_resolution_blockers(mutated), "剝掉判型確認竟然還過——檢查死了"


def _reason_ruling_errors(d: dict[str, Any]) -> list[str]:
    """單筆 gold 的 reason↔IE 裁決承重檢查（D3-027；D3-026 複審 M2）。

    先前 `expected_incomplete_reason` 與 ie_review 的裁決值在 gold 檔上零驗證
    （substance 守門只看非空字串）——複合 token 改序、自創 token、issues_contain
    清空都能全綠。規則：
    - reason ⟺ 裁決（zero_tmu_ruling / incomplete_ruling）同進同出且**相等**；
    - token 跑與 state 檔同一套 canonical 驗證（單一出處，不抄第二份）；
    - incomplete 裁決必須對得到至少一筆 complete=false 且 issues_contain 非空
      的 expected cycle（裁決要承在被驗證的缺漏上）。"""
    errors: list[str] = []
    ir = d.get("ie_review") or {}
    zero = ir.get("zero_tmu_ruling")
    inc = ir.get("incomplete_ruling")
    reason = d.get("expected_incomplete_reason")
    if zero and inc:
        errors.append("zero_tmu_ruling 與 incomplete_ruling 並存（前提互斥）")
    ruling = zero or inc
    if reason is None and ruling is None:
        return errors
    if reason is None or ruling is None:
        errors.append(
            f"expected_incomplete_reason={reason!r} 與 ie_review 裁決 {ruling!r} "
            "必須同進同出（reason 的唯一來源＝IE 裁決）"
        )
        return errors
    if reason != ruling:
        errors.append(
            f"expected_incomplete_reason={reason!r} != 裁決值 {ruling!r}（reason 不承重）"
        )
    if zero is not None and zero != ZERO_TMU_RULING_DISTANCE_UNSTATED:
        errors.append(
            f"zero_tmu_ruling={zero!r} 非法"
            f"（唯一合法值 {ZERO_TMU_RULING_DISTANCE_UNSTATED!r}）"
        )
    if inc is not None:
        canonical_err = incomplete_ruling_canonical_error(inc)
        if canonical_err:
            errors.append(canonical_err)
        cycles = d.get("expected_cycles") or []
        if not any(
            c.get("complete") is False and (c.get("issues_contain") or [])
            for c in cycles
        ):
            errors.append(
                "incomplete_ruling 存在但無任何 complete=false 且 issues_contain "
                "非空的 expected cycle（g49 型：issues_contain 清空＝裁決懸空）"
            )
    return errors


def test_repo_expected_incomplete_reasons_bound_to_rulings():
    """repo 不變量（D3-027；D3-026 複審 M2）：正式 gold 的 reason 值承重。
    複審實測 g45 複合 token 改掉／g48 改 totally_made_up／g49 issues_contain
    清空——836 全綠（零測試觸及）；本測讓三種壞值都紅。"""
    non_seed = [d for d in _gold_cases().values() if not is_seed_gold_case(d)]
    if not non_seed:
        pytest.skip("尚無轉正案例")
    problems = {
        str(d["id"]): errs
        for d in non_seed
        if (errs := _reason_ruling_errors(d))
    }
    assert not problems, f"gold reason↔裁決不變量失敗：{problems}"
    # 前提自檢：檢查不是恆空轉（repo 現況本來就有兩型裁決案例）
    assert any((d.get("ie_review") or {}).get("incomplete_ruling") for d in non_seed), (
        "repo 應有 incomplete 裁決案例（D3-026 第五批）——全消失代表另有問題"
    )
    assert any((d.get("ie_review") or {}).get("zero_tmu_ruling") for d in non_seed), (
        "repo 應有 TMU=0 裁決案例（D3-019 首批）——全消失代表另有問題"
    )


def test_reason_ruling_binding_mutations_detected():
    """mutation 證據（in-memory；D3-026 複審 M2 的三種壞值）：逐一必紅。"""
    base = next(
        (
            d
            for d in sorted(_gold_cases().values(), key=lambda x: str(x.get("id")))
            if "+" in str((d.get("ie_review") or {}).get("incomplete_ruling") or "")
        ),
        None,
    )
    assert base is not None, "repo 應有複合 incomplete_ruling 案例（g45/g48 型）"
    assert _reason_ruling_errors(base) == [], "前提：原件必須通過（守門不是恆紅）"
    # (1) 複合 token 改序——canonical 順序是唯一寫法（g45 型 mutation）
    m1 = copy.deepcopy(base)
    swapped = "+".join(reversed(m1["ie_review"]["incomplete_ruling"].split("+")))
    m1["ie_review"]["incomplete_ruling"] = swapped
    m1["expected_incomplete_reason"] = swapped
    assert _reason_ruling_errors(m1), "複合 token 改序竟然還過——canonical 驗證死了"
    # (2) 自創 token（g48 型 mutation）；(2b) 只改 reason＝與裁決漂移
    m2 = copy.deepcopy(base)
    m2["ie_review"]["incomplete_ruling"] = "totally_made_up"
    m2["expected_incomplete_reason"] = "totally_made_up"
    assert _reason_ruling_errors(m2), "自創 token 竟然還過——token 驗證死了"
    m2b = copy.deepcopy(base)
    m2b["expected_incomplete_reason"] = "totally_made_up"
    assert _reason_ruling_errors(m2b), "reason 與裁決漂移竟然還過——相等檢查死了"
    # (3) issues_contain 清空（g49 型 mutation）
    m3 = copy.deepcopy(base)
    for c in m3["expected_cycles"]:
        c.pop("issues_contain", None)
    assert _reason_ruling_errors(m3), "issues_contain 清空竟然還過——裁決懸空沒被抓"


def test_repo_same_component_same_split():
    """硬規則（spec §14.2）：同 split_component 必同 split——正式 gold 全體檢。"""
    comp_split: dict[str, set[str]] = {}
    for d in _gold_cases().values():
        comp, split = d.get("split_component"), d.get("split")
        if comp and split:
            comp_split.setdefault(comp, set()).add(split)
    offenders = {c: sorted(s) for c, s in comp_split.items() if len(s) > 1}
    assert not offenders, f"同 component 跨 split（leakage）：{offenders}"


def test_promoted_sentences_no_longer_in_drafts():
    """轉正後句子離開草稿目錄（existing_gold_norms 排除）；殘留＝重複覆核。"""
    entries = _state_entries()
    promoted_sha8 = {s for s, e in entries.items() if e.get("promoted_to")}
    if not DRAFT_DIR.is_dir():
        return
    draft_sha8s = set()
    for p in sorted(DRAFT_DIR.glob("*.json")):
        if p.name == REVIEW_STATE_FILENAME:
            continue
        draft_sha8s.add(draft_sha8(json.loads(p.read_text(encoding="utf-8"))))
    dupes = promoted_sha8 & draft_sha8s
    assert not dupes, f"已轉正句子仍在草稿目錄：{sorted(dupes)}"


# ie_modified=true 的正式 gold：IE 改了什麼 → 該筆 plan 應有幾個 action，
# 以及 notes 必須留下哪個關鍵字（建模差異寫在案例上，不只寫在 worklog）。
# 兩族的預期**相反**（重切改 action 數／判型只改 action_type，數維持 1），
# 分開釘值才擋得住「判型答案被當成重切」這類錯置。
IE_MODIFIED_RESEG_EXPECTED = {          # D3-022
    "g30_pick_dummy_dimm_debag": 2,     # v3_structure_confirmed multi_cycle_2 照切
    "g31_confirm_points_press_handle": 2,   # ie_ruling multi_cycle_2（部分重切）
    "g32_pick_board_debag_place_bench": 3,  # ie_ruling multi_cycle_3（部分重切）
}
IE_MODIFIED_TYPING_EXPECTED = {         # D3-028（單 action 判型答案）
    "g55_pick_screw_x1": 1,
    "g56_place_heatsink_on_cpu": 1,
    "g57_lh_pick_screw_from_box": 1,
}


def test_repo_ie_modified_promotions_pinned():
    """釘值：ie_modified=true 的正式 gold 恰為 D3-022 重切 3 筆（g30–g32）＋
    D3-028 判型答案 3 筆（g55–g57），宣告與 state entry 一致、plan action 數
    與該族語意一致、建模依據留在案例 notes。

    mutation 證據：把任一筆的 ie_modified 改回 false（或 entry 宣告拆掉）→
    本測試與 test_planner_eval 的分母釘值（plan_metrics_n）同時紅——
    「ie_modified=true 者被錯誤排除」在兩層都會被抓到。"""
    entries = _state_entries()
    modified_gold = {
        gid: d for gid, d in (
            (str(d["id"]), d) for d in _gold_cases().values()
        ) if d.get("ie_modified") is True
    }
    expected_actions = {**IE_MODIFIED_RESEG_EXPECTED, **IE_MODIFIED_TYPING_EXPECTED}
    assert set(modified_gold) == set(expected_actions), (
        "ie_modified=true 的 gold 名單漂移（D3-022 重切 3 筆＋D3-028 判型 3 筆）"
    )
    assert len(modified_gold) == IE_MODIFIED_GOLD_N
    by_promoted = {
        e["promoted_to"]: e for e in entries.values() if e.get("promoted_to")
    }
    # 案例 notes 必須寫出「IE 改了什麼」——族別關鍵字（重切／判型答案）
    note_keyword = dict.fromkeys(IE_MODIFIED_RESEG_EXPECTED, "重切")
    note_keyword.update(dict.fromkeys(IE_MODIFIED_TYPING_EXPECTED, "判型答案"))
    for gid, d in modified_gold.items():
        entry = by_promoted.get(gid)
        assert entry is not None and entry.get("ie_modified") is True, (
            f"{gid}：state entry 未宣告 ie_modified=true（宣告的唯一出處）"
        )
        assert len(d["plan"]["actions"]) == expected_actions[gid], (
            f"{gid}：plan action 數與 IE 修改的語意不符"
        )
        assert d.get("notes") and note_keyword[gid] in d["notes"], (
            f"{gid}：建模依據／涵蓋對應必須留在案例 notes（含「{note_keyword[gid]}」）"
        )


def test_repo_d016_title_sentence_stays_draft_not_promoted():
    """D3-022 釘值（d016）：「拿取風槍清潔放置DIMM材料盒的DIMM」＝標題句
    不硬切——entry 帶 resegmentation_ruling、未轉正、句子仍在草稿目錄、
    資格檢查必擋。

    mutation 證據：把它轉正（gold 目錄出現同句）或把 fail-closed 擋拆掉 →
    本測試紅（「d016 被錯誤轉正」）。"""
    entries = _state_entries()
    entry = entries.get("d0350279")
    assert entry is not None, "d0350279 entry 遺失"
    assert entry.get("resegmentation_ruling") == RESEGMENTATION_RULING_TITLE_SENTENCE
    assert not entry.get("promoted_to"), "IE 裁決不轉正的標題句竟被標 promoted"
    # 句子不得出現在正式 gold（以 normalized_text sha8 比對，不靠檔名）
    gold_sha8s = {draft_sha8(d) for d in _gold_cases().values()}
    assert "d0350279" not in gold_sha8s, "d016 被錯誤轉正——標題句進了正式 gold"
    # 草稿仍在（多動作辨識參考），且資格檢查擋下
    draft_path = next(DRAFT_DIR.glob("*_d0350279.json"), None)
    assert draft_path is not None, "d016 草稿應留在草稿目錄當多動作辨識參考"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    blockers = promotion_blockers(draft, entry)
    assert any("resegmentation_ruling" in b for b in blockers)
