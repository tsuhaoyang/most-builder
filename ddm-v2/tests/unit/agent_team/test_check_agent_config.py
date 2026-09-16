"""check_agent_config.py 單元測試（MOST split-root：git 根 + ddm-v2/ 子專案）。

以 tmp_path 造一個最小 monorepo 樹（根有 .git／CLAUDE.md／AGENTS.md；agent 設定、腳本、
轉接層、業務檔都在 ddm-v2/ 下），跑腳本 subprocess，驗證：
  - 完整正確的樹 → exit 0
  - 轉接檔引用不存在的正本 → exit 1（check_2）
  - CLAUDE.md 缺 @AGENTS.md → exit 1（check_1）
  - agent 名單不一致（.kiro 少一個）→ exit 1（check_3）
  - 舊路徑殘留 → exit 1（check_6）；搬家實作書白名單不擋
  - 正本引用不存在程式路徑 → exit 1（check_7）
  - 業務檔命中 0 領域且不在白名單 → exit 1（check_8）；在白名單 → 0
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT_REL = "ddm-v2/scripts/agent_team/check_agent_config.py"
AGENTS = ["most-code-reviewer", "most-logic-reviewer"]


def _build_repo(root: Path, *, break_link=False, drop_claude_import=False, drop_kiro_agent=False) -> None:
    (root / ".git").mkdir()
    ddm = root / "ddm-v2"
    at = ddm / "docs" / "agent-team" / "agents"
    at.mkdir(parents=True)
    for name in AGENTS:
        (at / f"{name}.md").write_text(f"# {name}\n正本內容\n", encoding="utf-8")
    (ddm / "docs" / "agent-team" / "checkpoint.md").write_text(
        "# checkpoint\n見 scripts/agent_team/domain_guard.py\n", encoding="utf-8"
    )
    (ddm / "docs" / "agent-team" / "domains.yaml").write_text(
        "domains:\n  - id: demo\n    title: demo\n    docs: []\n    paths: []\n", encoding="utf-8"
    )
    (ddm / "scripts" / "agent_team").mkdir(parents=True)
    (ddm / "scripts" / "agent_team" / "domain_guard.py").write_text("# stub\n", encoding="utf-8")
    # 把受測腳本複製進 tmp 樹（路徑常數靠 find_repo_root 自我定位，複製後行為一致）
    real = Path(__file__).resolve().parents[3] / "scripts" / "agent_team" / "check_agent_config.py"
    (ddm / "scripts" / "agent_team" / "check_agent_config.py").write_text(
        real.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # AGENTS.md（root，寫 ddm-v2/ 前綴的引用）
    (root / "AGENTS.md").write_text(
        "# AGENTS\n角色正本：`ddm-v2/docs/agent-team/agents/<name>.md`。\n"
        "關卡腳本：`ddm-v2/scripts/agent_team/domain_guard.py`。\n", encoding="utf-8"
    )
    (root / "CLAUDE.md").write_text(
        "# CLAUDE\n" + ("" if drop_claude_import else "@AGENTS.md\n"), encoding="utf-8"
    )
    # .claude/agents 轉接（ddm-v2 下，ddm-v2-relative 引用）
    ca = ddm / ".claude" / "agents"
    ca.mkdir(parents=True)
    for name in AGENTS:
        target = "docs/agent-team/agents/does-not-exist.md" if break_link else f"docs/agent-team/agents/{name}.md"
        (ca / f"{name}.md").write_text(f"---\nname: {name}\n---\n@{target}\n", encoding="utf-8")
    # .kiro/agents 轉接（JSON）
    ka = ddm / ".kiro" / "agents"
    ka.mkdir(parents=True)
    for name in (AGENTS[:-1] if drop_kiro_agent else AGENTS):
        (ka / f"{name}.json").write_text(
            json.dumps({
                "name": name, "description": "d", "tools": [],
                "prompt": f"見 docs/agent-team/agents/{name}.md",
                "resources": [f"file://docs/agent-team/agents/{name}.md"],
            }, ensure_ascii=False), encoding="utf-8"
        )
    (ddm / ".kiro" / "steering").mkdir(parents=True)


def _run(root: Path) -> subprocess.CompletedProcess:
    # 用系統 python3（check_5/check_8 需 pyyaml；本 repo 的 .venv 也有，但系統 python3 最穩）
    return subprocess.run(
        [sys.executable, str(root / SCRIPT_REL)], cwd=root, capture_output=True, text=True
    )


def _has_yaml() -> bool:
    return subprocess.run([sys.executable, "-c", "import yaml"], capture_output=True).returncode == 0


def test_clean_tree_passes(tmp_path: Path) -> None:
    _build_repo(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_broken_link_fails(tmp_path: Path) -> None:
    _build_repo(tmp_path, break_link=True)
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "does-not-exist" in r.stdout


def test_missing_claude_import_fails(tmp_path: Path) -> None:
    _build_repo(tmp_path, drop_claude_import=True)
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "@AGENTS.md" in r.stdout


def test_agent_list_mismatch_fails(tmp_path: Path) -> None:
    _build_repo(tmp_path, drop_kiro_agent=True)
    r = _run(tmp_path)
    assert r.returncode == 1
    assert ".kiro/agents" in r.stdout


def test_stale_moved_path_fails(tmp_path: Path) -> None:
    _build_repo(tmp_path)
    victim = tmp_path / "ddm-v2" / ".claude" / "agents" / f"{AGENTS[0]}.md"
    victim.write_text(
        victim.read_text(encoding="utf-8") + "\n領域知識來自 .kiro/steering/domains.yaml。\n",
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "已搬走的舊路徑" in r.stdout


def test_stale_path_in_whitelist_is_allowed(tmp_path: Path) -> None:
    _build_repo(tmp_path)
    plan = tmp_path / "ddm-v2" / "docs" / "architecture"
    plan.mkdir(parents=True)
    (plan / "docs-and-agent-docs-restructure-plan.md").write_text(
        "原 .kiro/steering/domains.yaml 搬入 docs/agent-team/。\n", encoding="utf-8"
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_canon_broken_code_path_fails(tmp_path: Path) -> None:
    _build_repo(tmp_path)
    victim = tmp_path / "ddm-v2" / "docs" / "agent-team" / "agents" / f"{AGENTS[0]}.md"
    victim.write_text(
        victim.read_text(encoding="utf-8") + "\nCheck `src/ddm_v2/does_not_exist.py`.\n",
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "不存在的程式/測試路徑" in r.stdout


def test_business_file_without_domain_fails(tmp_path: Path) -> None:
    if not _has_yaml():
        pytest.skip("python 環境無 pyyaml，check_8 無法測")
    _build_repo(tmp_path)
    (tmp_path / "ddm-v2" / "docs" / "agent-team" / "domains.yaml").write_text(
        "domains:\n  - id: demo\n    title: demo\n    docs: []\n"
        "    paths:\n      - \"src/ddm_v2/covered/**\"\n"
        "no_domain_allowlist: []\n", encoding="utf-8"
    )
    (tmp_path / "ddm-v2" / "src" / "ddm_v2" / "orphan").mkdir(parents=True)
    (tmp_path / "ddm-v2" / "src" / "ddm_v2" / "orphan" / "loose.py").write_text("x = 1\n", encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "命中 0 領域" in r.stdout
    assert "src/ddm_v2/orphan/loose.py" in r.stdout


def test_business_file_in_allowlist_passes(tmp_path: Path) -> None:
    if not _has_yaml():
        pytest.skip("python 環境無 pyyaml，check_8 無法測")
    _build_repo(tmp_path)
    (tmp_path / "ddm-v2" / "docs" / "agent-team" / "domains.yaml").write_text(
        "domains:\n  - id: demo\n    title: demo\n    docs: []\n"
        "    paths:\n      - \"src/ddm_v2/covered/**\"\n"
        "no_domain_allowlist:\n  - path: \"src/ddm_v2/orphan/loose.py\"\n    reason: 純匯出\n",
        encoding="utf-8"
    )
    (tmp_path / "ddm-v2" / "src" / "ddm_v2" / "orphan").mkdir(parents=True)
    (tmp_path / "ddm-v2" / "src" / "ddm_v2" / "orphan" / "loose.py").write_text("x = 1\n", encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
