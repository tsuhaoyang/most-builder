"""評測隔離守門：eval 絕不撿到 tests/gold/wi_plans_draft/ 的草稿。

隔離機制＝目錄範疇（`load_gold_cases` 只 glob `<gold_dir>/*.json`，不遞迴；
draft 目錄是 sibling）。「沒看過它紅過的守門不算守門」——所以本檔不只斷言
「現在沒撿到」，還用自建 tmp 樹做 mutation：**把一筆草稿塞進 wi_plans/ →
筆數必須動**，證明隔離不是因為 loader 壞掉恆空。

另守三條：

- 正式 gold 目錄不得混入 pending 草稿（tripwire：有人真把草稿複製進
  `tests/gold/wi_plans/`，這裡立刻紅——mutation 證據見 CI_GATES 規則 7 流程，
  複製 `wi_plans_draft/d001_*.json` 進 `wi_plans/` 本測試必紅）。
- 「IE 核准」要有實質門檻（P1-3；D3-018 M1 收緊）：非 seed 的正式 gold 不得是
  空殼——必須至少一個 `complete=true` 帶 `total_tmu > 0` 的 cycle（**0.0 不是
  實質內容**：距離未述的引擎口徑輸出，TMU=0.0 非真值），**或**顯式
  `expected_incomplete_reason`（誠實記錄資訊不足也可以，但要寫出來）；且必填
  `plan_origin` 與 `ie_modified`（bool）——自我指涉排除（planner_eval）靠這兩欄。
  mutation 證據：`test_empty_shell_approved_case_is_rejected` 用自建空殼證明
  守門是活的。
- seed 豁免釘白名單（R6）：`approved_by: "seed"` 只對 `SEED_GOLD_IDS`（gold_eval
  的三個已知 A5 fixture）有效——「seed」曾是任人填的字串，把 60 筆草稿標 seed
  並刪 plan_origin 就能同時穿透空殼守門與自我指涉排除（實測假指標 0.9841）。
  mutation 證據：`test_fourth_seed_file_trips_whitelist` 用第 4 筆自建 seed 證明
  tripwire 是活的。
- `scripts/gold_harvest.py` 拒絕把輸出寫進正式 gold 目錄（目錄名守衛）。

測試自足（CI_GATES 規則 7）：tmp 樹的案例全部自建，不依賴環境既存資料；
對真實 repo 的斷言只讀 repo 內已 commit 的檔案。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from ddm_v2.nlp.gold_eval import (
    SEED_GOLD_IDS,
    default_gold_dir,
    is_seed_gold_case,
    load_gold_cases,
)
from ddm_v2.nlp.planner_eval import load_gold_cases_checked

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "tests" / "gold" / "wi_plans"
DRAFT_DIR = ROOT / "tests" / "gold" / "wi_plans_draft"

sys.path.insert(0, str(ROOT / "scripts"))
from gold_harvest import assert_out_dir_safe  # noqa: E402


def _minimal_case(case_id: str, text: str) -> dict:
    """自建最小可載入案例（不依賴 repo/DB 資料）。"""
    return {
        "id": case_id,
        "source_text": text,
        "gold_schema_version": "wi-gold-v1",
        "approved_by": "seed",
        "plan": {
            "schema_version": "wi-plan-v1",
            "source_text": text,
            "normalized_text": text,
            "language": "zh",
            "source_ref": {"kind": "interactive"},
            "actions": [
                {
                    "action_id": "a1",
                    "action_type": "composite_unknown",
                    "sequence_order": 1,
                    "roles": {},
                    "evidence": [{"start": 0, "end": len(text), "text": text}],
                    "notes": None,
                }
            ],
            "dependencies": [],
            "unresolved": ["composite_unknown"],
        },
        "synthetic_synonyms": [],
        "expected_cycles": [],
    }


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_loader_scopes_to_gold_dir_and_mutation_moves_count(tmp_path: Path):
    """隔離＝目錄範疇；mutation：草稿檔進 wi_plans → 筆數 1→2（證明偵測是活的）。"""
    gold = tmp_path / "gold" / "wi_plans"
    draft = tmp_path / "gold" / "wi_plans_draft"
    _write(gold / "g01_case.json", _minimal_case("g01_case", "取物"))
    draft_case = _minimal_case("d001_case", "放物")
    draft_case.update(approved_by=None, review_status="pending_ie", split=None)
    _write(draft / "d001_case.json", draft_case)

    loaded = load_gold_cases(gold)
    assert [d["id"] for _p, d in loaded] == ["g01_case"], "draft sibling 目錄不得被掃到"

    # mutation：塞進 wi_plans → 必須被撿到（筆數/名單都動）
    shutil.copy(draft / "d001_case.json", gold / "d001_case.json")
    polluted = load_gold_cases(gold)
    assert len(polluted) == 2
    assert {d["id"] for _p, d in polluted} == {"g01_case", "d001_case"}

    # checked loader 同樣範疇（wi_ai_eval.py 用的是這個入口）
    cases, errors = load_gold_cases_checked(gold)
    assert not errors
    assert len(cases) == 2


def test_real_repo_eval_scope_excludes_draft_dir():
    """真實 repo：預設 gold 目錄＝tests/gold/wi_plans；掃描結果不含 draft 目錄檔案。"""
    assert default_gold_dir().resolve() == GOLD_DIR.resolve()

    loaded_paths = [p.resolve() for p, _d in load_gold_cases()]
    assert loaded_paths, "正式 gold 目錄不得為空"
    for p in loaded_paths:
        assert p.parent == GOLD_DIR.resolve()
        assert "wi_plans_draft" not in p.parts

    if DRAFT_DIR.is_dir():
        draft_names = {p.name for p in DRAFT_DIR.glob("*.json")}
        loaded_names = {p.name for p in loaded_paths}
        assert not (draft_names & loaded_names)


def test_formal_gold_dir_has_no_pending_drafts():
    """tripwire：正式 gold 目錄混入未核准草稿（approved_by=null 或 review_status
    非 approved）→ 立刻紅。既有 seed gold 無 review_status 欄位＝合法。"""
    offenders = []
    for p in sorted(GOLD_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        not_approved = d.get("approved_by") in (None, "")
        bad_status = d.get("review_status") not in (None, "approved")
        if not_approved or bad_status:
            offenders.append(p.name)
    assert not offenders, (
        f"正式 gold 目錄混入未核准草稿：{offenders}——草稿必須留在 wi_plans_draft/，"
        "轉正流程見 docs/llm/gold-review/README.md"
    )


def approved_case_defects(data: dict) -> list[str]:
    """「IE 核准」的實質門檻（P1-3）：非 seed 的正式 gold 不得是空殼。

    空殼＝roles 空、cycle 全 incomplete、無 TMU——填個名字就計入 50 筆等於
    P0 退出條件可以用零工作量達成。要求：至少一個 complete=true 帶
    **total_tmu > 0** 的 cycle（D3-018 M1：0.0 不是實質內容——距離未述＝0cm
    的引擎口徑輸出會產生 complete 且 TMU=0.0 的 cycle，原樣轉正＝把非真值
    寫進標準答案），或顯式 expected_incomplete_reason（誠實記錄資訊不足也
    可以，但要寫出來）。另必填 plan_origin 與 ie_modified（bool）——planner
    段的自我指涉排除靠這兩欄，缺欄＝未修改的預標註可能混進 Plan 層指標。

    seed 豁免只認 `SEED_GOLD_IDS` 白名單（R6）：只比對字串 "seed" 的話，
    任何案例都能自標 seed 同時穿透本守門與自我指涉排除。
    """
    if is_seed_gold_case(data):
        return []  # 白名單內的 seed 是 A5 fixture 慣例（D3-006），不套轉正欄位要求
    defects: list[str] = []
    if data.get("approved_by") == "seed":
        defects.append(
            f"approved_by=seed 但 id {data.get('id')!r} 不在 seed 白名單 "
            f"{sorted(SEED_GOLD_IDS)}——seed 不是萬用豁免字串，"
            "以下轉正要求照套"
        )
    origin = data.get("plan_origin")
    if not (isinstance(origin, str) and origin):
        defects.append(
            "缺 plan_origin（轉正必填；預標註轉正=rule_based_v1_preannotation、"
            "IE 手寫=ie_manual）"
        )
    if not isinstance(data.get("ie_modified"), bool):
        defects.append("缺 ie_modified（轉正必填 true|false——自我指涉排除靠這欄）")
    cycles = data.get("expected_cycles") or []
    # D3-018 M1：> 0 而非 is not None——TMU=0.0 是「距離未述」的引擎口徑輸出，
    # 不是實質內容；資訊不足的正路是顯式 expected_incomplete_reason
    has_substance = any(
        c.get("complete") is True and (c.get("total_tmu") or 0) > 0 for c in cycles
    )
    reason = data.get("expected_incomplete_reason")
    if not has_substance and not (isinstance(reason, str) and reason.strip()):
        defects.append(
            "空殼核准：無任何 complete=true 帶 total_tmu > 0 的 cycle（TMU=0.0 "
            "非真值，不算實質內容），也沒有 expected_incomplete_reason——"
            "資訊不足可以誠實記錄，但要寫出來"
        )
    return defects


def test_formal_gold_approved_cases_have_substance():
    """tripwire：正式 gold 目錄裡的非 seed 核准案例必須過實質門檻。"""
    offenders = {}
    for p in sorted(GOLD_DIR.glob("*.json")):
        defects = approved_case_defects(json.loads(p.read_text(encoding="utf-8")))
        if defects:
            offenders[p.name] = defects
    assert not offenders, f"空殼/缺欄核准案例：{offenders}"


def test_empty_shell_approved_case_is_rejected():
    """mutation 證據：空殼核准案例（roles 空、cycle 全 incomplete、無 TMU）必須被拒。"""
    shell = _minimal_case("g99_shell", "組裝")
    shell.update(approved_by="IEC999999", review_status="approved", split="test")
    shell["expected_cycles"] = [{"action_id": "a1", "complete": False, "cycle": None}]
    defects = approved_case_defects(shell)
    assert any("空殼核准" in d for d in defects)
    assert any("plan_origin" in d for d in defects)
    assert any("ie_modified" in d for d in defects)

    # 修好三缺（實質 cycle 路徑）→ 綠：證明守門不是恆紅
    shell.update(plan_origin="rule_based_v1_preannotation", ie_modified=True)
    shell["expected_cycles"] = [
        {"action_id": "a1", "complete": True, "seq": "GM", "total_tmu": 28.0}
    ]
    assert approved_case_defects(shell) == []

    # D3-018 M1 mutation：complete 但 TMU=0.0（距離未述的引擎口徑輸出）不是
    # 實質內容——守門若改回 `total_tmu is not None`，這裡必紅
    shell["expected_cycles"] = [
        {"action_id": "a1", "complete": True, "seq": "CM", "total_tmu": 0.0}
    ]
    defects = approved_case_defects(shell)
    assert any("空殼核准" in d for d in defects), (
        "TMU=0.0 穿透空殼守門：0.0 不是實質內容，必須補距離或顯式 "
        "expected_incomplete_reason"
    )

    # 帶 expected_incomplete_reason 的照樣放行（誠實記錄資訊不足仍合法）
    shell["expected_incomplete_reason"] = "此句未述距離，TMU=0.0 非真值——IE 判定資訊不足"
    assert approved_case_defects(shell) == []
    del shell["expected_incomplete_reason"]

    # 或誠實記錄資訊不足（expected_incomplete_reason 路徑）→ 也綠
    shell["expected_cycles"] = [{"action_id": "a1", "complete": False, "cycle": None}]
    shell["expected_incomplete_reason"] = "原文缺放置目標，IE 判定資訊不足以定 P 參數"
    assert approved_case_defects(shell) == []

    # 白名單內的 seed fixture 不套轉正欄位要求（D3-006 慣例）
    seed = _minimal_case("g01_acquire_dimm", "取物")
    assert approved_case_defects(seed) == []


def test_fourth_seed_file_trips_whitelist():
    """mutation 證據（R6）：第 4 筆檔案自標 approved_by=seed → tripwire 紅。

    攻擊面：seed 豁免若只比對字串，「把 60 筆草稿標 seed＋刪 plan_origin」可
    同時穿透空殼守門（P1-3）與自我指涉排除（P0-1），實測重現 0.9841 假指標。
    """
    fake = _minimal_case("g99_not_a_seed", "組裝")
    assert fake["approved_by"] == "seed"
    defects = approved_case_defects(fake)
    assert any("不在 seed 白名單" in d for d in defects)
    # 非白名單 seed 不豁免轉正要求：空殼與缺欄一併被點名
    assert any("plan_origin" in d for d in defects)
    assert any("ie_modified" in d for d in defects)
    assert any("空殼核准" in d for d in defects)

    # 白名單三筆現況全部存在且合法（名單與 repo 檔案不漂移）
    repo_ids = set()
    for p in sorted(GOLD_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("approved_by") == "seed":
            assert is_seed_gold_case(d), f"{p.name} 標 seed 但不在白名單"
            repo_ids.add(str(d.get("id")))
    assert repo_ids <= SEED_GOLD_IDS


def test_harvest_refuses_to_write_into_formal_gold(tmp_path: Path):
    """gold_harvest 的輸出目錄守衛：正式 gold 目錄與任何同名 wi_plans 目錄都拒絕。"""
    with pytest.raises(SystemExit):
        assert_out_dir_safe(GOLD_DIR)
    with pytest.raises(SystemExit):
        assert_out_dir_safe(tmp_path / "somewhere" / "wi_plans")
    # 正常草稿目錄不擋
    assert_out_dir_safe(tmp_path / "wi_plans_draft")
    assert_out_dir_safe(DRAFT_DIR)
