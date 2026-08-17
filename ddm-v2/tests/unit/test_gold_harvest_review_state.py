"""gold_harvest 的 IE 覆核狀態保留機制（D3-015；不需 DB）。

守什麼：`--force` 整批重產草稿時，IE 的覆核記錄（review-state.json）必須存活
且**不得錯掛**——第二輪（同義詞登記後）一定會重跑 harvest，覆核狀態被洗掉或
被靜默套到內容已變的草稿上都是事故。

機制不變式：

1. 配對鍵＝normalized_text 的 sha256 前 8 碼（與流水號無關）——編號位移
   （d026→d031）狀態照樣跟著句子走。
2. stale 不靜默套用：文字變（sha 變 → 配不到）、v3 結構 hint 變（確認/裁決
   所依據的證據已不同）、entry 記 ie_modified=true（plan 內容本機制保不了）
   → 全部回報 stale、草稿一個欄位都不動。
3. sha8 相符但完整 sha 不符＝state 損毀/碰撞 → SystemExit（不是 stale）。
4. state 檔驗證是硬的（SystemExit）：格式錯誤被吞掉＝IE 裁決靜默漏套。
5. review-state.json 不是草稿：`draft_json_files` 排除它（--force 不刪、
   覆蓋守衛不計入）。
6. repo 現況自洽：41 筆 entry 全部配對到現有草稿且非 stale。首輪
   （IE 2026-08-16 親答）：39 確認＋d045 單 cycle 裁決＋d026 三 cycle 裁決；
   **第二輪更正**（2026-08-16 釐清並獲 User 確認）：d026 這句本身＝1 列——
   首輪「3 列」是對整個 wi-template 三步驟製程的回答（提問誤述範本結構為
   句子切分）。更正軌跡保留在該 entry 的 `ruling_history`（先前答案全文＋
   為何更正）——標準答案集的更正不能是無痕覆寫。
7. `ruling_history`（更正軌跡）若存在必須形狀完整（先前 ie_ruling＋
   supersede_reason＋superseded_date）——「保留軌跡」不可是空殼宣稱。

mutation 證據（CI_GATES 規則 7）：
- 把 `merge_review_state` 的 sha 配對改成流水號配對 → `test_renumbered_draft_still_matched` 紅。
- 把 `apply_review_state_entry` 的 hint 比對拆掉 → `test_stale_when_hint_changed` 紅。
- 把 stale 改成靜默套用 → `test_stale_entry_leaves_draft_untouched` 紅。
- 把 `draft_json_files` 的排除拆掉 → `test_review_state_file_is_not_a_draft` 紅。
- 把 `load_review_state` 的 ruling_history 驗證拆掉 →
  `test_load_review_state_rejects_bad_ruling_history` 紅。
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRAFT_DIR = ROOT / "tests" / "gold" / "wi_plans_draft"

sys.path.insert(0, str(ROOT / "scripts"))
from gold_harvest import (  # noqa: E402
    REVIEW_STATE_FILENAME,
    REVIEW_STATE_SCHEMA_VERSION,
    apply_review_state_entry,
    draft_json_files,
    draft_sha8,
    load_review_state,
    merge_review_state,
    review_block_from_entry,
)

# ── fixture helpers（自建，不依賴 repo/DB 資料）──────────────────────────────


def _sha(norm: str) -> str:
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _draft(norm: str, idx: int = 1, hint: str | None = "single_cycle") -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": f"d{idx:03d}_{_sha(norm)[:8]}",
        "source_text": norm,
        "review_status": "pending_ie",
        "approved_by": None,
        "ie_modified": None,
        "plan": {"normalized_text": norm, "actions": []},
        "preannotation_caveat": ["take_place_pair_may_be_single_gm"],
        "expected": {"action_count": 1, "routing_status": "review"},
    }
    if hint is not None:
        d["v3_structure_hint"] = hint
        d["v3_structure_evidence"] = {
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
        }
    return d


def _entry(norm: str, hint: str | None = "single_cycle", **over: Any) -> dict[str, Any]:
    e: dict[str, Any] = {
        "source_text": norm,
        "norm_sha256": _sha(norm),
        "v3_structure_hint_at_review": hint,
        "segmentation_confirmed_by": "IEC141289",
        "segmentation_confirmed_date": "2026-08-16",
        "segmentation_source": "v3_structure_confirmed",
        "ie_modified": False,
    }
    e.update(over)
    return e


def _state(entries: dict[str, dict]) -> dict[str, Any]:
    return {"schema_version": REVIEW_STATE_SCHEMA_VERSION, "entries": entries}


def _write_state(path: Path, entries: dict[str, dict]) -> Path:
    path.write_text(json.dumps(_state(entries), ensure_ascii=False), encoding="utf-8")
    return path


# ── 1. 配對與合併 ────────────────────────────────────────────────────────────


def test_confirmation_applied_to_matching_draft():
    d = _draft("雙手抓握主機板放至治具")
    entry = _entry("雙手抓握主機板放至治具")
    applied, stale = merge_review_state([d], {_sha(d["plan"]["normalized_text"])[:8]: entry})
    assert applied == [d["id"]] and stale == []
    assert d["ie_review"] == review_block_from_entry(entry)
    assert d["ie_review"]["segmentation_source"] == "v3_structure_confirmed"
    assert "ie_ruling" not in d["ie_review"], "確認題不帶裁決欄位"
    assert d["ie_modified"] is False, "確認≠修改——ie_modified 落 false"


def test_renumbered_draft_still_matched():
    """編號位移（第二輪選擇順序改變）不影響配對——鍵是 sha 不是流水號。"""
    norm = "拿取排線並對準接頭"
    d = _draft(norm, idx=57)  # 上一輪是 d045，本輪變 d057
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: _entry(norm)})
    assert applied == [d["id"]] and stale == []
    assert d["ie_review"]["segmentation_confirmed_by"] == "IEC141289"


def test_ruling_with_pending_resegmentation_and_rejected_evidence():
    """multi_cycle 裁決＋plan 待重切＋否定結構標記（證據保留不刪）。

    首輪 d026 曾是此型（第二輪已更正為 single_cycle）；機制本身仍是合法形狀，
    測試保留驗機制。"""
    norm = "雙手抓握主機板組至機箱"
    d = _draft(norm, hint="ambiguous")
    entry = _entry(
        norm,
        hint="ambiguous",
        segmentation_source="ie_ruling",
        ie_ruling="multi_cycle_3",
        ie_ruling_notes="3 列 wi-template 是對的",
        plan_pending_resegmentation=True,
        ie_rejected_evidence=[{"table": "motion_modules", "id": "mm-1"}],
    )
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: entry})
    assert applied == [d["id"]] and stale == []
    assert d["ie_review"]["ie_ruling"] == "multi_cycle_3"
    assert d["ie_review"]["plan_pending_resegmentation"] is True
    src = d["v3_structure_evidence"]["sources"][0]
    assert src["ie_ruling_rejected"] is True, "否定的結構要標記"
    assert src["cycles"] == 1, "證據本體保留不刪"


# ── 2. stale：不靜默套用 ─────────────────────────────────────────────────────


def test_stale_when_text_changed_sha_mismatch():
    """文字變了 ⇒ sha 變 ⇒ 舊 entry 配不到任何草稿 ⇒ no_matching_draft。"""
    old_norm, new_norm = "拿取排線並對準接頭", "拿取排線並對準接頭孔位"
    d = _draft(new_norm)
    applied, stale = merge_review_state([d], {_sha(old_norm)[:8]: _entry(old_norm)})
    assert applied == []
    assert [s["reason"] for s in stale] == ["no_matching_draft"]
    assert stale[0]["source_text"] == old_norm, "報告要帶原文供 IE 對照"
    assert "ie_review" not in d


def test_stale_when_hint_changed():
    """v3 結構 hint 變了（第二輪 DB 結構訊號不同）⇒ 確認所依據的證據已變，
    不得沿用——IE 需重看。"""
    norm = "雙手抓握主機板放至治具"
    d = _draft(norm, hint="multi_cycle_2")  # 當初確認時是 single_cycle
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: _entry(norm, hint="single_cycle")})
    assert applied == []
    assert [s["reason"] for s in stale] == ["v3_structure_hint_changed"]
    assert "ie_review" not in d


def test_stale_when_entry_has_plan_edits():
    """entry 記 ie_modified=true：本機制只保覆核詮釋資料，plan 內容重產必被
    管線輸出蓋掉——拒絕合併（否則「IE 改過」的宣告掛在管線原樣 plan 上＝說謊）。"""
    norm = "雙手抓握主機板放至治具"
    d = _draft(norm)
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: _entry(norm, ie_modified=True)})
    assert applied == []
    assert [s["reason"] for s in stale] == ["ie_modified_plan_not_preservable"]
    assert d.get("ie_modified") is None, "stale 不得動草稿欄位"


def test_stale_when_rejected_evidence_missing():
    norm = "雙手抓握主機板組至機箱"
    d = _draft(norm, hint="ambiguous")
    entry = _entry(
        norm,
        hint="ambiguous",
        segmentation_source="ie_ruling",
        ie_ruling="multi_cycle_3",
        ie_rejected_evidence=[{"table": "motion_modules", "id": "not-there"}],
    )
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: entry})
    assert [s["reason"] for s in stale] == ["rejected_evidence_missing"]
    assert "ie_review" not in d


def test_stale_entry_leaves_draft_untouched():
    """stale 的前置檢查在任何落筆之前——草稿必須 deep-equal 原樣（不留半套狀態）。"""
    norm = "雙手抓握主機板組至機箱"
    d = _draft(norm, hint="ambiguous")
    before = copy.deepcopy(d)
    entry = _entry(
        norm,
        hint="ambiguous",
        segmentation_source="ie_ruling",
        ie_ruling="multi_cycle_3",
        plan_pending_resegmentation=True,
        ie_rejected_evidence=[{"table": "motion_modules", "id": "not-there"}],
    )
    assert apply_review_state_entry(d, entry) == "rejected_evidence_missing"
    assert d == before


def test_full_sha_mismatch_is_integrity_failure_not_stale():
    """sha8 相符但完整 sha 不符＝state 損毀/碰撞——大聲失敗，不是 stale。"""
    norm = "雙手抓握主機板放至治具"
    d = _draft(norm)
    entry = _entry(norm)
    entry["norm_sha256"] = _sha(norm)[:8] + "0" * 56  # 前 8 碼相同、其餘偽造
    with pytest.raises(SystemExit, match="完整性失敗"):
        apply_review_state_entry(d, entry)


# ── 2b. D3-019 面向（判型/P 方向/TMU=0）：套用、stale、promoted 跳過 ─────────


def _typed_draft(norm: str, **over: Any) -> dict[str, Any]:
    """帶判型/P 方向/TMU=0 旗標素材的草稿（自建）。"""
    d = _draft(norm, hint=None)
    d["preannotation_caveat"] = ["typing_changed_by_verb_lexicon"]
    d["typing_change"] = {"noun_only_seq": None, "lexicon_seq": "CM"}
    d.update(over)
    return d


def _aspect_entry(norm: str, **over: Any) -> dict[str, Any]:
    """僅帶 D3-019 面向（無切分面向）的 entry——d042 型（不在首輪 41 筆內）。"""
    e: dict[str, Any] = {
        "source_text": norm,
        "norm_sha256": _sha(norm),
        "ie_modified": False,
        "typing_confirmed_by": "IEC141289",
        "typing_confirmed_date": "2026-08-17",
        "typing_change_at_review": {"noun_only_seq": None, "lexicon_seq": "CM"},
    }
    e.update(over)
    return e


def test_typing_only_entry_applies_without_segmentation_aspect():
    """d042 型：entry 只有判型面向（切分不在 41 筆內，不冒填）→ 照樣合併。"""
    norm = "按壓功能測試治具面板"
    d = _typed_draft(norm)
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: _aspect_entry(norm)})
    assert applied == [d["id"]] and stale == []
    assert d["ie_review"]["typing_confirmed_by"] == "IEC141289"
    assert "segmentation_source" not in d["ie_review"]
    assert d["ie_modified"] is False


def test_stale_when_typing_change_changed():
    """mutation 證據：新一輪判型與確認當時不同 → 整筆 stale（拆掉比對必紅）。"""
    norm = "按壓功能測試治具面板"
    d = _typed_draft(norm)
    d["typing_change"] = {"noun_only_seq": None, "lexicon_seq": "GM"}  # 判型又變了
    before = copy.deepcopy(d)
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: _aspect_entry(norm)})
    assert applied == []
    assert [s["reason"] for s in stale] == ["typing_change_changed"]
    assert d == before, "stale 不得動草稿"


def test_stale_when_p_direction_context_changed():
    norm = "左手抓握治具放至定位"
    d = _typed_draft(norm)
    d["preannotation_caveat"] = ["p_direction_none_by_context"]  # 情境分類變了
    del d["typing_change"]
    entry = _aspect_entry(norm)
    for k in ("typing_confirmed_by", "typing_confirmed_date", "typing_change_at_review"):
        del entry[k]
    entry.update(
        p_direction_confirmed_by="IEC141289",
        p_direction_confirmed_date="2026-08-17",
        p_direction_caveat_at_review="p_direction_single_default",
    )
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: entry})
    assert applied == []
    assert [s["reason"] for s in stale] == ["p_direction_context_changed"]


def test_zero_tmu_ruling_applies_reason_and_stale_when_flag_absent():
    """TMU=0 裁決：套用時草稿記 expected_incomplete_reason（值原樣）；
    旗標消失（裁決前提不成立）→ stale。"""
    norm = "左手抓握包裝袋去除表面"
    entry = _aspect_entry(norm)
    for k in ("typing_confirmed_by", "typing_confirmed_date", "typing_change_at_review"):
        del entry[k]
    entry.update(
        zero_tmu_ruling="distance_unstated",
        zero_tmu_ruled_by="IEC141289",
        zero_tmu_ruled_date="2026-08-17",
    )
    d = _typed_draft(norm)
    d["preannotation_caveat"] = ["zero_tmu_distance_unstated"]
    del d["typing_change"]
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: entry})
    assert applied == [d["id"]] and stale == []
    assert d["expected_incomplete_reason"] == "distance_unstated"
    assert d["ie_review"]["zero_tmu_ruling"] == "distance_unstated"

    # 旗標消失（例如距離補上、TMU 變真值）→ 裁決前提不成立 → stale
    d2 = _typed_draft(norm)
    d2["preannotation_caveat"] = []
    del d2["typing_change"]
    applied, stale = merge_review_state([d2], {_sha(norm)[:8]: entry})
    assert applied == []
    assert [s["reason"] for s in stale] == ["zero_tmu_flag_absent"]
    assert "expected_incomplete_reason" not in d2


def test_promoted_entry_skipped_not_stale():
    """轉正 entry：合併跳過（不套用、不算 stale）——即使 sha 配不到草稿也不進
    stale 名單（句子已在正式 gold，本來就不該有草稿）。"""
    norm = "雙手抓握主機板放至治具"
    entry = _entry(norm, promoted_to="g06_board_to_press_fixture", promoted_date="2026-08-17")
    applied, stale = merge_review_state([], {_sha(norm)[:8]: entry})
    assert applied == [] and stale == []

    # 就算草稿存在（理論上不會——gold 重複守門另擋），也不套用
    d = _draft(norm)
    applied, stale = merge_review_state([d], {_sha(norm)[:8]: entry})
    assert applied == [] and stale == []
    assert "ie_review" not in d


# ── 3. state 檔驗證（硬紅，不靜默）──────────────────────────────────────────


def test_load_review_state_missing_file_is_empty(tmp_path: Path):
    assert load_review_state(tmp_path / REVIEW_STATE_FILENAME) == {}


def test_load_review_state_roundtrip(tmp_path: Path):
    norm = "雙手抓握主機板放至治具"
    p = _write_state(tmp_path / REVIEW_STATE_FILENAME, {_sha(norm)[:8]: _entry(norm)})
    entries = load_review_state(p)
    assert list(entries) == [_sha(norm)[:8]]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda s: s.__setitem__("schema_version", "wi-review-state-v0"), "schema_version"),
        (lambda s: s.__setitem__("entries", {}), "entries"),
        (
            lambda s: next(iter(s["entries"].values())).__setitem__(
                "segmentation_confirmed_date", "16/08/2026"
            ),
            "YYYY-MM-DD",
        ),
        (
            lambda s: next(iter(s["entries"].values())).__setitem__(
                "segmentation_source", "gut_feeling"
            ),
            "segmentation_source",
        ),
        (
            lambda s: next(iter(s["entries"].values())).__setitem__(
                "v3_structure_hint_at_review", "ambiguous"
            ),
            "不是可確認的結構答案",
        ),
        (
            lambda s: next(iter(s["entries"].values())).__setitem__("ie_ruling", "single_cycle"),
            "確認≠裁決",
        ),
        (
            lambda s: next(iter(s["entries"].values())).pop("norm_sha256"),
            "norm_sha256",
        ),
    ],
)
def test_load_review_state_rejects_bad_shapes(tmp_path: Path, mutate, match: str):
    norm = "雙手抓握主機板放至治具"
    state = _state({_sha(norm)[:8]: _entry(norm)})
    mutate(state)
    p = tmp_path / REVIEW_STATE_FILENAME
    p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit, match=match):
        load_review_state(p)


def test_load_review_state_accepts_valid_ruling_history(tmp_path: Path):
    """更正軌跡（d026 型第二輪更正）：形狀完整的 ruling_history 可載入。"""
    norm = "雙手抓握主機板組至機箱"
    entry = _entry(
        norm,
        hint="ambiguous",
        segmentation_source="ie_ruling",
        ie_ruling="single_cycle",
        ruling_history=[
            {
                "ie_ruling": "multi_cycle_3",
                "ruled_date": "2026-08-16",
                "superseded_date": "2026-08-16",
                "supersede_reason": "提問誤述範本結構為句子切分，釐清後更正",
            }
        ],
    )
    p = _write_state(tmp_path / REVIEW_STATE_FILENAME, {_sha(norm)[:8]: entry})
    entries = load_review_state(p)
    assert entries[_sha(norm)[:8]]["ruling_history"][0]["ie_ruling"] == "multi_cycle_3"


@pytest.mark.parametrize(
    ("history", "match"),
    [
        ([], "非空 list"),  # 空殼軌跡
        (["not-a-dict"], "object"),
        (
            [{"superseded_date": "2026-08-16", "supersede_reason": "x"}],
            "ie_ruling",
        ),  # 先前答案沒保留
        (
            [{"ie_ruling": "multi_cycle_3", "superseded_date": "2026-08-16"}],
            "supersede_reason",
        ),  # 為何更正沒寫
        (
            [
                {
                    "ie_ruling": "multi_cycle_3",
                    "supersede_reason": "x",
                    "superseded_date": "16/08/2026",
                }
            ],
            "YYYY-MM-DD",
        ),
    ],
)
def test_load_review_state_rejects_bad_ruling_history(tmp_path: Path, history, match: str):
    """更正軌跡驗證是硬的：軌跡缺件＝「保留軌跡」只是空殼宣稱——擋下。"""
    norm = "雙手抓握主機板組至機箱"
    entry = _entry(
        norm,
        hint="ambiguous",
        segmentation_source="ie_ruling",
        ie_ruling="single_cycle",
        ruling_history=history,
    )
    p = _write_state(tmp_path / REVIEW_STATE_FILENAME, {_sha(norm)[:8]: entry})
    with pytest.raises(SystemExit, match=match):
        load_review_state(p)


@pytest.mark.parametrize(
    ("over", "match"),
    [
        # 判型面向：欄位群不完整/形狀錯
        ({"typing_confirmed_by": "IEC141289"}, "typing_confirmed_date"),
        (
            {
                "typing_confirmed_by": "IEC141289",
                "typing_confirmed_date": "2026-08-17",
                "typing_change_at_review": {"noun_only_seq": None},
            },
            "typing_change_at_review",
        ),
        (
            {
                "typing_confirmed_by": "IEC141289",
                "typing_confirmed_date": "2026-08-17",
                "typing_change_at_review": {"noun_only_seq": "GM", "lexicon_seq": "GM"},
            },
            "舊/新判型相同",
        ),
        # P 方向面向：caveat 名不在名單
        (
            {
                "p_direction_confirmed_by": "IEC141289",
                "p_direction_confirmed_date": "2026-08-17",
                "p_direction_caveat_at_review": "not_a_flag",
            },
            "p_direction_caveat_at_review",
        ),
        # TMU=0 面向：裁決值不合法
        (
            {
                "zero_tmu_ruling": "just_zero_is_fine",
                "zero_tmu_ruled_by": "IEC141289",
                "zero_tmu_ruled_date": "2026-08-17",
            },
            "distance_unstated",
        ),
        # promoted 標記：形狀錯／缺日期
        ({"promoted_to": "not-a-gold-id", "promoted_date": "2026-08-17"}, "promoted_to"),
        ({"promoted_to": "g06_board_to_press_fixture"}, "promoted_date"),
    ],
)
def test_load_review_state_rejects_bad_aspect_shapes(tmp_path: Path, over, match: str):
    """D3-019 面向欄位驗證是硬的：半套面向/非法值＝IE 裁決可能靜默漏套——擋下。"""
    norm = "雙手抓握主機板放至治具"
    entry = _entry(norm, **over)
    p = _write_state(tmp_path / REVIEW_STATE_FILENAME, {_sha(norm)[:8]: entry})
    with pytest.raises(SystemExit, match=match):
        load_review_state(p)


def test_load_review_state_rejects_entry_without_any_aspect(tmp_path: Path):
    """空 entry（無任何覆核面向）不是覆核記錄——擋下。"""
    norm = "雙手抓握主機板放至治具"
    entry = {
        "source_text": norm,
        "norm_sha256": _sha(norm),
        "ie_modified": False,
    }
    p = _write_state(tmp_path / REVIEW_STATE_FILENAME, {_sha(norm)[:8]: entry})
    with pytest.raises(SystemExit, match="至少要有一個覆核面向"):
        load_review_state(p)


def test_load_review_state_ruling_requires_valid_ruling(tmp_path: Path):
    norm = "雙手抓握主機板組至機箱"
    entry = _entry(norm, hint="ambiguous", segmentation_source="ie_ruling")  # 缺 ie_ruling
    p = _write_state(tmp_path / REVIEW_STATE_FILENAME, {_sha(norm)[:8]: entry})
    with pytest.raises(SystemExit, match="ie_ruling"):
        load_review_state(p)

    entry = _entry(
        norm,
        hint="ambiguous",
        segmentation_source="ie_ruling",
        ie_ruling="single_cycle",
        plan_pending_resegmentation=True,  # 單 cycle 沒有「等重切」
    )
    p = _write_state(tmp_path / REVIEW_STATE_FILENAME, {_sha(norm)[:8]: entry})
    with pytest.raises(SystemExit, match="plan_pending_resegmentation"):
        load_review_state(p)


# ── 4. review-state.json 不是草稿 ────────────────────────────────────────────


def test_review_state_file_is_not_a_draft(tmp_path: Path):
    """draft_json_files 排除 state 檔——`--force` 的刪除迴圈與覆蓋守衛都吃這個
    清單，排除拆掉＝IE 覆核狀態被 --force 刪光。"""
    (tmp_path / "d001_aaaaaaaa.json").write_text("{}", encoding="utf-8")
    _write_state(tmp_path / REVIEW_STATE_FILENAME, {"a" * 8: _entry("x")})
    names = [p.name for p in draft_json_files(tmp_path)]
    assert names == ["d001_aaaaaaaa.json"]


# ── 5. repo 現況自洽（首輪覆核結果；讀已 commit 檔案）───────────────────────


def _repo_drafts() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in draft_json_files(DRAFT_DIR)
    ]


def test_repo_review_state_all_entries_fresh_and_applied():
    """active（未轉正）entry 全部配對到現有草稿且非 stale；草稿上的 ie_review
    與重放合併結果一致（決定性）。

    D3-019 起 entry 分兩類：標 `promoted_to` 的（已轉正 tests/gold/wi_plans/，
    句子不再產草稿——合併跳過、不算 stale、軌跡保留）與 active 的（必須全數
    套用）。promoted ↔ 正式 gold 的同進同出守門在 test_gold_promotion.py。"""
    state_path = DRAFT_DIR / REVIEW_STATE_FILENAME
    if not state_path.exists():
        pytest.skip("repo 無 review-state.json（草稿可能已全數轉正）")
    entries = load_review_state(state_path)
    active = {k: v for k, v in entries.items() if not v.get("promoted_to")}
    drafts = _repo_drafts()
    if not drafts:
        pytest.skip("wi_plans_draft 目前沒有草稿")

    # 重放合併：在剝掉 ie_review 的 deep copy 上重跑，結果必須與 repo 檔一致
    stripped = []
    for d in drafts:
        c = copy.deepcopy(d)
        c.pop("ie_review", None)
        c.pop("expected_incomplete_reason", None)  # TMU=0 裁決的合併產物（D3-019）
        c["ie_modified"] = None
        for s in (c.get("v3_structure_evidence") or {}).get("sources") or []:
            s.pop("ie_ruling_rejected", None)
        stripped.append(c)
    applied, stale = merge_review_state(stripped, entries)
    assert stale == [], f"repo state 有 stale entry（IE 需重看）：{stale}"
    assert len(applied) == len(active), (
        "active entry 沒有全數套用（promoted 以外的 entry 必須逐筆配對到草稿）"
    )
    by_id_repo = {d["id"]: d for d in drafts}
    for c in stripped:
        assert c == by_id_repo[c["id"]], f"{c['id']}：重放合併與 repo 檔不一致"


def test_repo_ie_rulings_present_after_round2_correction():
    """IE 覆核結果落地檢查。首輪（2026-08-16 親答）：d045=single_cycle、39 筆
    確認照 v3 結構預設、d026=multi_cycle_3。**第二輪更正**（2026-08-16 釐清並
    獲 User 確認）：d026 這句本身＝1 列——首輪「3 列」是對整個 wi-template
    三步驟製程的回答（提問誤述範本結構為句子切分）。更正不是無痕覆寫：
    先前裁決全文＋為何更正保留在 state entry 的 `ruling_history`。"""
    state_path = DRAFT_DIR / REVIEW_STATE_FILENAME
    if not state_path.exists():
        pytest.skip("repo 無 review-state.json（草稿可能已全數轉正）")
    drafts = {d["id"]: d for d in _repo_drafts()}
    d026 = next((d for i, d in drafts.items() if i.startswith("d026_")), None)
    d045 = next((d for i, d in drafts.items() if i.startswith("d045_")), None)
    if d026 is None or d045 is None:
        pytest.skip("d026/d045 已不在草稿目錄（可能已轉正或重編號）")

    ir26 = d026["ie_review"]
    assert ir26["ie_ruling"] == "single_cycle", "第二輪更正：這句本身＝1 列"
    assert "plan_pending_resegmentation" not in ir26, (
        "single_cycle 下沒有「等重切」——首輪的 pending 旗標必須隨更正清除"
    )
    assert len(d026["plan"]["actions"]) == 1
    rejected = [
        s
        for s in d026["v3_structure_evidence"]["sources"]
        if s.get("ie_ruling_rejected")
    ]
    assert [(s["table"], s["cycles"]) for s in rejected] == [("motion_modules", 3)], (
        "更正後被否定的是「wi-template 名稱句對應 3 列＝本句切 3 個 cycle」的推論"
        "（範本名稱是製程標題，不是本句的切分）；證據保留不刪。"
        "首輪對單列 action module 的否定已隨更正撤回。"
    )
    # 更正軌跡：state entry 必須保留首輪答案與更正理由（無痕覆寫＝標準答案集事故）
    entries = load_review_state(state_path)
    entry26 = entries[draft_sha8(d026)]
    history = entry26.get("ruling_history")
    assert history, "d026 被更正過——ruling_history 必須存在（不無痕覆寫）"
    assert [h["ie_ruling"] for h in history] == ["multi_cycle_3"], "先前答案必須保留"
    assert "誤述" in history[0]["supersede_reason"], "為何更正必須寫明（提問誤述範本結構）"

    ir45 = d045["ie_review"]
    assert ir45["ie_ruling"] == "single_cycle"
    assert "plan_pending_resegmentation" not in ir45
    assert len(d045["plan"]["actions"]) == 1

    confirmed = [
        d for d in drafts.values()
        if (d.get("ie_review") or {}).get("segmentation_source") == "v3_structure_confirmed"
    ]
    # 首輪 39 筆確認；D3-019 首批轉正把其中 21 筆（全部 v3_structure_confirmed）
    # 搬進 tests/gold/wi_plans/ → 草稿目錄剩 18 筆帶確認。促成守恆的另一半
    # （promoted entry ↔ 正式 gold 檔）在 test_gold_promotion.py。
    state_entries = load_review_state(DRAFT_DIR / REVIEW_STATE_FILENAME)
    promoted_confirmed = sum(
        1
        for e in state_entries.values()
        if e.get("promoted_to")
        and e.get("segmentation_source") == "v3_structure_confirmed"
    )
    assert len(confirmed) + promoted_confirmed == 39, (
        f"切分確認守恆破了：草稿 {len(confirmed)} ＋ 已轉正 {promoted_confirmed} ≠ 39"
    )
    assert len(confirmed) == 18
    for d in confirmed:
        assert d["v3_structure_hint"] != "ambiguous"
        assert d["ie_modified"] is False


def test_repo_drafts_sha8_matches_filename_suffix():
    """draft_sha8（配對鍵）與檔名後綴同源——兩邊漂移＝配對機制沉默失效。"""
    files = draft_json_files(DRAFT_DIR)
    if not files:
        pytest.skip("wi_plans_draft 目前沒有草稿")
    for p in files:
        d = json.loads(p.read_text(encoding="utf-8"))
        assert p.stem.rsplit("_", 1)[1] == draft_sha8(d), p.name
