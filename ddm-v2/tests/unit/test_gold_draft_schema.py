"""草稿 gold（tests/gold/wi_plans_draft/）schema 與自洽守門。

守什麼：

1. 結構層：每個草稿過 wi-gold-v1 頂層形狀＋wi-plan-v1 plan schema
   （`load_gold_cases_checked` 零 load error）。
2. 標註層：evidence offset 走 `planner_eval` 既有的 `0 <= start < end <= len`
   守衛與 slice==text 檢查（g05 那類越界 bug 不准進草稿）。
3. 草稿身分：`approved_by: null`、`review_status` ∈ {pending_ie, ie_edited}、
   `split: null`、`plan_origin` 標明 plan 出處（rule planner 預標註）、
   `ie_modified` 於轉正前不得為 true——**草稿不是 gold**，身分欄位錯了就可能被誤轉正。
   pending_ie 另要求與 rule planner 重放**整份 plan 相等**（byte-level dict 比對，
   不是只查 action 數——改 `action_type`、換句子而不改狀態都要紅）。
4. 挑戰維度：`challenge_tags` 至少包含 spec §14.3 的 16 維度
   （`docs/architecture/wi-ai-parser-system-spec.md`；spec 語意是「至少涵蓋」，
   IE 可加自訂維度），16 維的值只能是 bool 或 "unknown"（判不動就標 unknown，不硬湊）。
5. 誠實旗標：multi_action 候選必帶 `likely_multi_action_undercounted`；
   「取＋放」配對（`take_place_pair_may_be_single_gm`）與「取/觸＋推/拉」配對
   （`take_move_pair_may_be_single_cm`）各與 multi_action 互斥——GM＝G+P 同
   cycle、CM＝G+M 同 cycle，配對不是低估證據，不得反向推 IE 過度切分。
   `heuristic_tags_unverified` 必須點名 false 也未覆核的維度。
   `engine_rejected_cycle` 旗標與 `expected_cycles[].expected_engine_rejected`
   期望必須同進同出（旗標無期望＝話沒說完；期望無旗標＝IE 看不到警示）。
6. 重放自洽：compile 段（plan → link/compile/engine）與 planner 段
   （source_text → rule planner）都能重放且與檔內期望一致——保證核准後
   移入正式 gold 時不會立刻紅。
7. 來源一致（R5）：`plan.normalized_text` 必須與**至少一筆**
   `source_provenance[].raw_text` 正規化後一致——spec §19 要的是「50 筆**真實**
   案例」，把 `source_text` 換成虛構句再重生 plan/recompile 不會動 provenance，
   守門就靠這一條（mutation：`test_provenance_mutation_detected`）。

mutation 證據（CI_GATES 規則 7）：把任一 pending_ie 草稿的 `action_type` 改掉
（狀態不動）、evidence.end 改越界、review_status 改掉、刪 preannotation_caveat、
ie_modified 改 true、換 `source_text` 不動 provenance → 對應斷言紅；改回 → 綠。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ddm_v2.nlp.gold_eval import evaluate_gold_case

# harvest 用的正規化函式（ddm_v2.nlp.normalization.normalize）——R5 的來源一致
# 守門必須用同一支，不另抄一份
from ddm_v2.nlp.normalization import normalize
from ddm_v2.nlp.planner_eval import (
    evaluate_planner_case,
    load_gold_cases_checked,
    rule_based_plan,
)

ROOT = Path(__file__).resolve().parents[2]
DRAFT_DIR = ROOT / "tests" / "gold" / "wi_plans_draft"

# 挑戰維度定義的唯一出處是 harvest 腳本（tests 與 scripts 共用，不複製清單）
sys.path.insert(0, str(ROOT / "scripts"))
from gold_harvest import (  # noqa: E402
    DIM_KEYS,
    HEURISTIC_UNVERIFIED_DIMS,
    PLAN_ORIGIN_PREANNOTATION,
)


def provenance_matches_normalized_text(data: dict) -> bool:
    """R5：plan.normalized_text 是否與至少一筆 source_provenance.raw_text
    正規化後一致（同一支 normalize——harvest 的去重鍵就是 normalize(raw)）。"""
    norm_text = (data.get("plan") or {}).get("normalized_text")
    return any(
        normalize(str(s.get("raw_text") or "")) == norm_text
        for s in data.get("source_provenance") or []
    )


def _draft_files() -> list[Path]:
    if not DRAFT_DIR.is_dir():
        return []
    return sorted(DRAFT_DIR.glob("*.json"))


def _draft_ids() -> list[str]:
    return [p.name for p in _draft_files()]


@pytest.fixture(scope="module")
def drafts() -> list[tuple[Path, dict]]:
    files = _draft_files()
    if not files:
        pytest.skip("wi_plans_draft 目前沒有草稿（可能全數已轉正）")
    cases, load_errors = load_gold_cases_checked(DRAFT_DIR)
    assert not load_errors, f"草稿結構層無效：{[e.to_dict() for e in load_errors]}"
    assert len(cases) == len(files)
    return cases


def test_draft_dir_is_sibling_not_inside_gold():
    """草稿目錄必須是 wi_plans 的 sibling——放進 gold 目錄底下都算擺錯位置。"""
    gold_dir = ROOT / "tests" / "gold" / "wi_plans"
    assert DRAFT_DIR.parent == gold_dir.parent
    assert not DRAFT_DIR.resolve().is_relative_to(gold_dir.resolve())


@pytest.mark.parametrize("fname", _draft_ids() or ["<empty>"])
async def test_draft_case(fname: str, drafts: list[tuple[Path, dict]]):
    data = next(d for p, d in drafts if p.name == fname)

    # 3. 草稿身分：pending_ie＝管線原樣；ie_edited＝IE 改過但尚未轉正
    assert data.get("gold_schema_version") == "wi-gold-v1"
    assert data.get("approved_by") is None, "草稿不得有 approved_by——有值代表該轉正而非留在 draft"
    assert data.get("review_status") in {"pending_ie", "ie_edited"}
    assert data.get("split") is None, "split 於核准時才填"
    assert isinstance(data.get("split_groups"), list) and data["split_groups"]
    comp = data.get("split_component")
    assert isinstance(comp, str) and comp, "split_component（傳遞閉包分組）必須由 harvest 算好"
    # plan 出處與 ie_modified：自我指涉排除（planner_eval）靠這兩欄；
    # 草稿階段 ie_modified 不得為 true（true 是轉正時 IE 的宣告，不是預填值）
    assert data.get("plan_origin") == PLAN_ORIGIN_PREANNOTATION, (
        "草稿的 plan 就是 rule planner 的輸出——plan_origin 不得缺漏或竄改，"
        "否則轉正後會混進 Plan 層指標（自我指涉假象）"
    )
    assert data.get("ie_modified") is not True, (
        "ie_modified=true 是轉正時的宣告；草稿階段預填 true 會讓未修改的預標註"
        "騙過自我指涉排除"
    )
    prov = data.get("source_provenance")
    assert isinstance(prov, list) and prov, "每筆草稿必須標注來源（表/id）"
    for s in prov:
        assert s.get("table") and s.get("id")
    # 7. 來源一致（R5）：換掉 source_text／重生 plan／--recompile 都不會動
    # provenance——虛構句混進「真實案例」集合就在這裡紅
    assert provenance_matches_normalized_text(data), (
        f"{fname} 的 plan.normalized_text 與所有 source_provenance[].raw_text "
        "正規化後皆不一致——source_text 疑似被換成非來源原文（spec §19 要求真實案例）"
    )

    # 4. 挑戰維度：至少包含 16 維度（spec 語意）；16 維的值 bool 或 "unknown"
    tags = data.get("challenge_tags")
    assert isinstance(tags, dict)
    assert set(tags) >= set(DIM_KEYS), (
        f"challenge_tags 缺 spec §14.3 維度：{set(DIM_KEYS) - set(tags)}"
    )
    for k in DIM_KEYS:
        v = tags[k]
        assert v is True or v is False or v == "unknown", f"{k}={v!r} 不是 bool/unknown"

    # 5. 誠實旗標
    caveats = data.get("preannotation_caveat")
    assert isinstance(caveats, list)
    if tags.get("multi_action") is True:
        assert "likely_multi_action_undercounted" in caveats, (
            "多動作候選必須逐筆標 likely_multi_action_undercounted（系統性偏差不准只寫在文件裡）"
        )
    if "take_place_pair_may_be_single_gm" in caveats:
        # 取放配對不是 multi_action（GM＝G+P 同 cycle）；兩旗標互斥，
        # 否則 caveat 又把 IE 推回「必然低估」的錯誤方向
        assert tags.get("multi_action") is not True, (
            "take_place_pair 與 multi_action 互斥：配對不是切分低估的證據"
        )
        assert "likely_multi_action_undercounted" not in caveats
    if "take_move_pair_may_be_single_cm" in caveats:
        # 取/觸＋推/拉配對同理（CM＝G+M 同 cycle）；與 multi_action／GM 配對互斥
        assert tags.get("multi_action") is not True, (
            "take_move_pair 與 multi_action 互斥：配對不是切分低估的證據"
        )
        assert "likely_multi_action_undercounted" not in caveats
        assert "take_place_pair_may_be_single_gm" not in caveats
    # engine_rejected_cycle 旗標 ↔ expected_engine_rejected 期望同進同出
    has_rejected_exp = any(
        ec.get("expected_engine_rejected") for ec in data.get("expected_cycles") or []
    )
    assert has_rejected_exp == ("engine_rejected_cycle" in caveats), (
        f"{fname}：engine_rejected_cycle 旗標與 expected_engine_rejected 期望必須"
        "同進同出（旗標無期望＝話沒說完；期望無旗標＝IE 看不到警示）"
    )
    unverified = data.get("heuristic_tags_unverified")
    assert isinstance(unverified, list) and set(unverified) == set(HEURISTIC_UNVERIFIED_DIMS), (
        "heuristic_tags_unverified 必須點名 false 也未覆核的維度（quantity/tool/simo 有實證漏標）"
    )

    # 2+6. planner 段重放：offset 守衛（gold_* 具名錯誤＝標註缺損）永遠檢查；
    # 「與 rule planner 重放整份 plan 相等」只對 pending_ie（原樣草稿）要求——
    # IE 改過的草稿（ie_edited）本來就會偏離 rule planner，那是修正不是缺陷。
    p = await evaluate_planner_case(data, rule_based_plan)
    assert p.ok, f"{fname} 標註缺損：{p.errors}"
    if data["review_status"] == "pending_ie":
        # P0-2：整份 plan 相等比對——只查 action 數擋不住改 action_type/換整句
        replay = await rule_based_plan(data)
        assert replay.model_dump(mode="json") == data["plan"], (
            f"{fname} 與 rule planner 重放不一致：pending_ie 草稿必須是管線原樣"
            "（整份 plan 相等，不是只有 action 數）；IE 動手改的第一步是把 "
            "review_status 改成 'ie_edited'（見 docs/llm/gold-review/README.md）"
        )

    # 6. compile 段重放：plan → link/compile/engine 與 expected_cycles/expected 一致。
    # ie_edited 也必須過——IE 改了 plan 卻忘了跑 --recompile 時，這裡會紅。
    c = await evaluate_gold_case(data)
    assert c.ok, f"{fname} compile 段重放失敗（改了 plan 後忘了 --recompile？）：{c.errors}"


def test_provenance_mutation_detected(drafts: list[tuple[Path, dict]]):
    """R5 mutation 證據：把 source_text 換成虛構句並依 pipeline 重生 plan
    （normalized_text 跟著變）、不動 provenance → 來源一致守門必紅。"""
    _path, original = drafts[0]
    data = json.loads(json.dumps(original))  # deep copy
    assert provenance_matches_normalized_text(data), "前提：repo 草稿本身必須綠"

    fictional = "左手虛構一個不存在的動作句"
    data["source_text"] = fictional
    data["plan"]["source_text"] = fictional
    data["plan"]["normalized_text"] = normalize(fictional)  # 重生 plan 後的必然結果
    assert not provenance_matches_normalized_text(data), (
        "換 source_text 不動 provenance 竟然過關——R5 守門死了"
    )


def test_drafts_do_not_duplicate_formal_gold(drafts: list[tuple[Path, dict]]):
    """同一句話不得同時存在於草稿與正式 gold（重複覆核＝浪費 IE、轉正＝撞名）。"""
    from ddm_v2.nlp.normalization import normalize

    gold_dir = ROOT / "tests" / "gold" / "wi_plans"
    gold_norms = set()
    for p in sorted(gold_dir.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        src = d.get("source_text") or (d.get("plan") or {}).get("source_text")
        if src:
            gold_norms.add(normalize(str(src)))
    dupes = [
        p.name
        for p, d in drafts
        if normalize(str(d.get("source_text") or "")) in gold_norms
    ]
    assert not dupes, f"草稿與正式 gold 同句：{dupes}"
