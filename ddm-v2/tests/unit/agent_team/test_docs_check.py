"""docs_check.py 單元測試（MOST split-root：git 根 + ddm-v2/ 子專案）。

以 tmp_path 造最小 monorepo 樹，跑腳本 subprocess，驗證：
  - 乾淨樹（引用都存在）→ exit 0
  - 故意斷鏈（doc 引用不存在的程式檔）→ exit 1
  - R2 刪線 ~~...~~ 內的引用不算斷鏈 → exit 0
  - 白名單（產生檔 api.d.ts、設計期腳本、跨 repo LB 路徑）不算斷鏈 → exit 0
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT_REL = "ddm-v2/scripts/docs_check.py"


def _build(root: Path, doc_body: str) -> None:
    (root / ".git").mkdir()
    ddm = root / "ddm-v2"
    (ddm / "docs" / "agent-team").mkdir(parents=True)
    (ddm / "docs" / "domains").mkdir(parents=True)
    # domains.yaml + 對應 domain md（一致，避免無關 warning）
    (ddm / "docs" / "agent-team" / "domains.yaml").write_text(
        'domains:\n  - id: demo\n    title: demo\n    paths:\n      - "src/ddm_v2/demo/**"\n', encoding="utf-8"
    )
    (ddm / "docs" / "domains" / "demo.md").write_text(
        "# 領域索引：demo\n程式入口 `src/ddm_v2/demo/x.py`\n", encoding="utf-8"
    )
    # 一個真實存在的程式檔（供乾淨引用）
    (ddm / "src" / "ddm_v2" / "demo").mkdir(parents=True)
    (ddm / "src" / "ddm_v2" / "demo" / "x.py").write_text("x = 1\n", encoding="utf-8")
    # DOC_REGISTRY 收錄本測試 doc（避免孤兒 warning 混淆；孤兒是 warning 不影響 exit）
    (ddm / "docs" / "DOC_REGISTRY.md").write_text(
        "# 索引\n- [t](t.md)\n", encoding="utf-8"
    )
    (ddm / "docs" / "t.md").write_text(doc_body, encoding="utf-8")
    # 複製受測腳本進 tmp 樹（find_repo_root 自我定位）
    real = Path(__file__).resolve().parents[3] / "scripts" / "docs_check.py"
    (ddm / "scripts").mkdir(parents=True)
    (ddm / "scripts" / "docs_check.py").write_text(real.read_text(encoding="utf-8"), encoding="utf-8")


def _run(root: Path) -> subprocess.CompletedProcess:
    # git rev-parse HEAD 需要至少一個 commit；graphify 圖不存在只會是 warning，不影響本測試斷言
    subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], capture_output=True)
    return subprocess.run([sys.executable, str(root / SCRIPT_REL)], cwd=root, capture_output=True, text=True)


def test_clean_tree_passes(tmp_path: Path) -> None:
    _build(tmp_path, "# T\n狀態：現行\n見 `src/ddm_v2/demo/x.py`。\n")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_broken_link_fails(tmp_path: Path) -> None:
    _build(tmp_path, "# T\n見 `src/ddm_v2/demo/does_not_exist.py`。\n")
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "斷鏈" in r.stdout
    assert "does_not_exist.py" in r.stdout


def test_strikethrough_not_broken(tmp_path: Path) -> None:
    # R2 刪線內的引用是歷史紀錄，不算斷鏈
    _build(tmp_path, "# T\n~~舊測試 `src/ddm_v2/demo/removed.py`~~（訂正：已移除）。\n見 `src/ddm_v2/demo/x.py`。\n")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_whitelist_not_broken(tmp_path: Path) -> None:
    # 產生檔 + 設計期腳本 + 跨 repo LB 路徑，皆不算斷鏈
    _build(
        tmp_path,
        "# T\n"
        "產生檔 `src/shared/types/api.d.ts`；設計期 `scripts/prune_ai_runs.py`；"
        "跨 repo `src/optimization/algorithms/engine.py`。\n",
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
