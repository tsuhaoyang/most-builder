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
from _seed_gold_baseline import PROMOTED_GOLD_N  # noqa: E402
from gold_harvest import (  # noqa: E402
    PROMOTION_SPLITS,
    REVIEW_STATE_FILENAME,
    TYPING_CHANGED_CAVEAT,
    ZERO_TMU_CAVEAT,
    ZERO_TMU_RULING_DISTANCE_UNSTATED,
    caveat_resolution_blockers,
    draft_sha8,
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


def test_unresolved_lint_flag_blocks():
    """acquire_without_place（取而無放）是未解決的覆核提問——fail-closed。"""
    draft, entry = _eligible_pair()
    draft["preannotation_caveat"].append("acquire_without_place")
    blockers = promotion_blockers(draft, entry)
    assert any("acquire_without_place" in b for b in blockers)


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
        assert d.get("ie_modified") is False, (
            f"{gid}：本批全部原樣核准——ie_modified 必為 false（自我指涉防線）"
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
