"""gold_harvest.py 整合守門（需 DB；唯讀）。

守什麼：

1. **決定性**：同一 DB 連跑兩次，草稿 JSON 與覆核表/摘要 byte-identical
   （排序穩定、輸出無 timestamp）——草稿要能 diff、IE 重看不被雜訊淹沒。
2. 產出可載入：兩段 eval 的 loader 對草稿零 load error。
3. `--force` 守衛：out 目錄已有草稿時拒絕覆蓋（IE 編輯不被清掉）。
4. D3-014：帶切分旗標的草稿 ⇔ 回填 `v3_structure_hint`＋證據（scope 雙向）；
   `acquire_without_place` 旗標與 plan 的 action_type 序列判定同進同出。

測試自足（CI_GATES 規則 7）：不斷言任何來源筆數／候選數——CI DB 的 seed 與本機
不同（CI 沒跑 dev_seed_30rows / migrate_v3_user_data，候選可能是 0 筆）。
但**決定性斷言要有素材才算數**：兩次輸出都是空集合時 byte 比較是 vacuous，
skip 而非假綠。harvest 子行程只跑 SELECT，不寫 DB；輸出全部進 tmp_path，不碰 repo。

mutation 證據：把 gold_harvest.py 的 `sorted(by_norm.values(), ...)` 拿掉排序、
或在輸出 dict 塞 `datetime.now()`，決定性測試必紅。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ddm_v2.nlp.planner_eval import load_gold_cases_checked

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gold_harvest.py"

sys.path.insert(0, str(ROOT / "scripts"))
from gold_harvest import (  # noqa: E402
    REVIEW_STATE_FILENAME,
    REVIEW_STATE_SCHEMA_VERSION,
    SEGMENTATION_CAVEATS,
    acquire_without_place,
)


def _run_harvest(out_dir: Path, review_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL 未設定，略過整合測試")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out_dir),
            "--review-dir",
            str(review_dir),
            *extra,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _snapshot(dir_: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(dir_.glob("*")) if p.is_file()}


def test_harvest_deterministic_and_loadable(tmp_path: Path):
    run1_out, run1_rev = tmp_path / "r1" / "drafts", tmp_path / "r1" / "review"
    run2_out, run2_rev = tmp_path / "r2" / "drafts", tmp_path / "r2" / "review"

    p1 = _run_harvest(run1_out, run1_rev)
    assert p1.returncode == 0, p1.stdout + p1.stderr
    p2 = _run_harvest(run2_out, run2_rev)
    assert p2.returncode == 0, p2.stdout + p2.stderr

    s1, s2 = _snapshot(run1_out), _snapshot(run2_out)
    if not s1 and not s2:
        # 空對空的 byte 比較是 vacuous——不能拿它宣稱「決定性已驗證」
        pytest.skip("此 DB 來源 0 筆、無草稿輸出；決定性需至少一筆才算數")
    assert s1.keys() == s2.keys(), "兩次輸出檔名集合不同——排序/命名不穩定"
    diff = [name for name in s1 if s1[name] != s2[name]]
    assert not diff, f"兩次輸出 byte 不一致：{diff}"

    r1, r2 = _snapshot(run1_rev), _snapshot(run2_rev)
    assert r1.keys() == r2.keys()
    assert [n for n in r1 if r1[n] != r2[n]] == [], "覆核表/摘要不決定性"

    # 產出可載入（零 load error）；草稿身分正確
    cases, errors = load_gold_cases_checked(run1_out)
    assert not errors, [e.to_dict() for e in errors]
    assert len(cases) == len(s1)
    for _p, data in cases:
        assert data["approved_by"] is None
        assert data["review_status"] == "pending_ie"
        # D3-014：帶切分旗標 ⇔ 回填 v3 結構 hint＋證據（scope 守門同 schema 測試，
        # 這裡驗的是「新鮮 harvest 的輸出」而非 repo 既有草稿）
        caveats = data["preannotation_caveat"]
        has_seg = any(c in SEGMENTATION_CAVEATS for c in caveats)
        assert (data.get("v3_structure_hint") is not None) == has_seg
        if has_seg:
            assert (data.get("v3_structure_evidence") or {}).get("sources"), (
                f"{data['id']}：hint 無證據——hint 是證據不是判決，證據必須落在草稿上"
            )
        # D3-014 裁決 2：lint 與旗標同進同出（單一判定函式）
        assert ("acquire_without_place" in caveats) == acquire_without_place(
            data["plan"]["actions"]
        )

    # stdout 的摘要段也應一致（前三行印的是 tmp 路徑，不在比對範圍）
    marker = "# Harvest 摘要"
    assert marker in p1.stdout and marker in p2.stdout
    assert p1.stdout[p1.stdout.index(marker):] == p2.stdout[p2.stdout.index(marker):]


def test_review_state_survives_force_and_stale_not_applied(tmp_path: Path):
    """D3-015 關鍵演練：IE 覆核狀態在 --force 整批重產後存活；stale 不靜默套用。

    劇本：首輪 harvest → 依產出草稿寫 review-state.json（1 筆有效確認＋1 筆
    sha 配不到＋1 筆 hint 不符）→ --force 重產 → 有效確認合併回草稿、
    兩筆 stale 列入摘要且不套用、state 檔本身不被刪；再 --force 一次 →
    輸出 byte-identical（合併不破壞決定性）。

    mutation 證據：把 cmd_harvest 的 merge_review_state 呼叫拆掉 → ie_review
    斷言紅；把 --force 刪檔迴圈改回 glob("*.json") → state 檔消失斷言紅。
    """
    import hashlib
    import json

    out_dir, rev_dir = tmp_path / "drafts", tmp_path / "review"
    p1 = _run_harvest(out_dir, rev_dir)
    assert p1.returncode == 0, p1.stdout + p1.stderr
    draft_paths = sorted(p for p in out_dir.glob("*.json") if p.name != REVIEW_STATE_FILENAME)
    if not draft_paths:
        pytest.skip("此 DB 無候選（CI 最小 seed）；覆核狀態演練需至少一筆草稿")

    def _entry(draft: dict, **over: object) -> dict:
        norm = draft["plan"]["normalized_text"]
        e = {
            "source_text": draft["source_text"],
            "norm_sha256": hashlib.sha256(norm.encode("utf-8")).hexdigest(),
            "v3_structure_hint_at_review": draft.get("v3_structure_hint"),
            "segmentation_confirmed_by": "IEC141289",
            "segmentation_confirmed_date": "2026-08-16",
            "segmentation_source": "ie_ruling",
            "ie_ruling": "single_cycle",
            "ie_modified": False,
        }
        e.update(over)
        return e

    drafts = [json.loads(p.read_text(encoding="utf-8")) for p in draft_paths]
    target = drafts[0]
    target_sha8 = hashlib.sha256(
        target["plan"]["normalized_text"].encode("utf-8")
    ).hexdigest()[:8]
    entries = {
        # 有效：sha 與 hint 都對得上 → 必須合併
        target_sha8: _entry(target),
        # stale 1：sha 配不到任何草稿（文字已變/句子已不在本輪）
        "deadbeef": _entry(target, norm_sha256="deadbeef" + "0" * 56,
                           source_text="已改寫的舊句子"),
    }
    if len(drafts) > 1:
        other = drafts[1]
        other_sha8 = hashlib.sha256(
            other["plan"]["normalized_text"].encode("utf-8")
        ).hexdigest()[:8]
        # stale 2：hint 與當初覆核時不同（結構證據已變）→ 不得沿用
        entries[other_sha8] = _entry(
            other, v3_structure_hint_at_review="multi_cycle_9"
        )
    state_path = out_dir / REVIEW_STATE_FILENAME
    state_path.write_text(
        json.dumps(
            {"schema_version": REVIEW_STATE_SCHEMA_VERSION, "entries": entries},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    p2 = _run_harvest(out_dir, rev_dir, "--force")
    assert p2.returncode == 0, p2.stdout + p2.stderr
    assert state_path.exists(), "--force 不得刪 review-state.json（IE 的檔案）"

    merged = json.loads((out_dir / f"{target['id']}.json").read_text(encoding="utf-8"))
    ir = merged.get("ie_review")
    assert ir and ir["segmentation_confirmed_by"] == "IEC141289", "覆核狀態沒在重產後存活"
    assert ir["ie_ruling"] == "single_cycle"
    assert merged["ie_modified"] is False

    summary = (rev_dir / "harvest-summary.md").read_text(encoding="utf-8")
    assert "deadbeef" in summary and "no_matching_draft" in summary, "stale 必須列入報告"
    if len(drafts) > 1:
        other_merged = json.loads(
            (out_dir / f"{drafts[1]['id']}.json").read_text(encoding="utf-8")
        )
        assert "ie_review" not in other_merged, "hint 不符的 stale 狀態被靜默套用了"
        assert "v3_structure_hint_changed" in summary

    # 決定性：帶 state 再 --force 一次 → 草稿與報告 byte-identical
    before = _snapshot(out_dir)
    p3 = _run_harvest(out_dir, rev_dir, "--force")
    assert p3.returncode == 0, p3.stdout + p3.stderr
    assert _snapshot(out_dir) == before, "合併覆核狀態破壞了決定性"


def test_harvest_refuses_overwrite_without_force(tmp_path: Path):
    out_dir, rev_dir = tmp_path / "drafts", tmp_path / "review"
    p1 = _run_harvest(out_dir, rev_dir)
    assert p1.returncode == 0, p1.stdout + p1.stderr
    before = _snapshot(out_dir)
    if not before:
        pytest.skip("此 DB 無候選（CI 最小 seed）；覆蓋守衛需至少一筆草稿才可驗")

    # 模擬 IE 已編輯：再跑一次（無 --force）必須拒絕且不動任何檔案
    p2 = _run_harvest(out_dir, rev_dir)
    assert p2.returncode != 0
    assert _snapshot(out_dir) == before, "無 --force 竟然動了既有草稿"

    # --force 明示重產 → 成功
    p3 = _run_harvest(out_dir, rev_dir, "--force")
    assert p3.returncode == 0, p3.stdout + p3.stderr
    assert _snapshot(out_dir).keys() == before.keys()
