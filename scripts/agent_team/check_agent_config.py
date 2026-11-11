#!/usr/bin/env python3
"""agent／文件設定一致性檢查（commit 前跑）。

來源：line-balance_stream-weaver_v2/scripts/agent_team/check_agent_config.py（commit 2b59ddc）。
本 repo（MOST／ddm-v2）差異（與 LB 分歧點——日後要再分歧前先回報）：
  - 業務檔範圍：`src/ddm_v2/**/*.py` ＋ `src/frontend/src/**/*.{ts,tsx}`（LB 是 `src/**/*.py` ＋
    `src/static/dashboard/**/*.js`）。
  - 無 example_feature 樣板豁免。
  - 轉接層只掃 `.kiro/`、`.claude/`（MOST 沒有 .github/agents、.cursor/rules 這兩套 agent 設定）。
  - 舊路徑殘留清單（check_6）改為 MOST 從無到有的情境（本 repo 未曾把設定放 .kiro/steering 下）。

五＋三項檢查（LB 同款）：
  1. CLAUDE.md 含 @AGENTS.md。
  2. 轉接檔引用到存在的 docs/agent-team/ 檔。
  3. 三處 agent 名單一致：docs/agent-team/agents/、.claude/agents/、.kiro/agents/。
  4. AGENTS.md、checkpoint.md 引用的路徑都存在。
  5. domains.yaml 的 paths／docs 指向存在（不存在 → 警告）。
  6. 已搬走的舊路徑殘留 → error。
  7. agent 正本＋AGENTS.md 反引號引用的程式／測試路徑存在（斷鏈 → error）。
  8. 每個業務檔至少命中一個領域，或在 no_domain_allowlist → 否則 error。

退出碼：有 ERROR → 1；只有 WARN 或全綠 → 0。
用法：python3 scripts/agent_team/check_agent_config.py
"""
from __future__ import annotations

import glob as _glob
import json
import os
import re
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """git 根＝專案根（2026-11-11 起，原 most-builder/ddm-v2/ 上移為 repo 根）。
    agent 設定正本、腳本、轉接層、CLAUDE.md／AGENTS.md 都在 git 根。
    REPO＝DDM＝git 根（保留 DDM 名稱以減少改動；ddm-v2/ 前綴的舊引用仍被容忍）。"""
    for parent in [start, *start.parents]:
        if (parent / ".git").exists():
            return parent
        if (parent / "docs" / "agent-team" / "domains.yaml").is_file():
            return parent
    return start.parent


REPO = find_repo_root(Path(__file__).resolve())
DDM = REPO  # 2026-11-11 起 git 根＝專案根（原 ddm-v2/ 上移）
AGENT_TEAM = DDM / "docs" / "agent-team"
AGENTS_DIR = AGENT_TEAM / "agents"

errors: list[str] = []
warns: list[str] = []
oks: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warns.append(msg)


def ok(msg: str) -> None:
    oks.append(msg)


def canon_agents() -> set[str]:
    return {p.stem for p in AGENTS_DIR.glob("*.md")}


DOC_REF_RE = re.compile(r"(?:@|file://|#\[\[file:)?((?:ddm-v2/)?docs/agent-team/[A-Za-z0-9_./-]+)")


def _ref_exists(ref: str) -> bool:
    """轉接檔可能寫 ddm-v2-relative（docs/agent-team/…）或 root-relative（ddm-v2/docs/agent-team/…）。
    兩種都接受，只要任一解析得到存在的檔。"""
    if ref.startswith("ddm-v2/"):
        ref = ref[len("ddm-v2/"):]  # 舊 split-root 寫法視同 repo 根相對
    return (DDM / ref).exists() or (REPO / ref).exists()


def referenced_agent_team_paths(text: str) -> list[str]:
    out = []
    for m in DOC_REF_RE.findall(text):
        ref = m.rstrip(".,;。、）)】」』")
        if "<" in ref or ">" in ref:
            continue  # 佔位說明，非真實引用
        out.append(ref)
    return out


def check_1_claude_imports_agents() -> None:
    claude = REPO / "CLAUDE.md"
    if not claude.is_file():
        err("CLAUDE.md 不存在")
        return
    if "@AGENTS.md" in claude.read_text(encoding="utf-8"):
        ok("CLAUDE.md 含 @AGENTS.md")
    else:
        err("CLAUDE.md 未引入 @AGENTS.md")


def check_2_transceivers_reference_existing_canon() -> None:
    targets: list[Path] = []
    targets += list((DDM / ".claude" / "agents").glob("*.md"))
    targets += list((DDM / ".kiro" / "agents").glob("*.json"))
    targets += list((DDM / ".kiro" / "steering").glob("*.md"))
    for f in targets:
        text = f.read_text(encoding="utf-8")
        refs = referenced_agent_team_paths(text)
        if not refs:
            continue
        for ref in refs:
            if not _ref_exists(ref):
                err(f"{f.relative_to(REPO)} 引用不存在的檔案：{ref}")
        ok(f"{f.relative_to(REPO)} 的 {len(refs)} 個 docs/agent-team 引用都存在")


def check_3_agent_lists_consistent() -> None:
    canon = canon_agents()
    if not canon:
        err("docs/agent-team/agents/ 沒有任何正本 .md")
        return
    claude = {p.stem for p in (DDM / ".claude" / "agents").glob("*.md")}
    kiro = {p.stem for p in (DDM / ".kiro" / "agents").glob("*.json")}
    if claude == canon:
        ok(f".claude/agents 名單與正本一致（{len(canon)} 個）")
    else:
        err(f".claude/agents 名單與正本不一致：缺 {sorted(canon - claude)}，多 {sorted(claude - canon)}")
    if kiro == canon:
        ok(f".kiro/agents 名單與正本一致（{len(canon)} 個）")
    else:
        err(f".kiro/agents 名單與正本不一致：缺 {sorted(canon - kiro)}，多 {sorted(kiro - canon)}")


def check_4_entry_refs_exist() -> None:
    for entry in [REPO / "AGENTS.md", AGENT_TEAM / "checkpoint.md"]:
        if not entry.is_file():
            err(f"{entry.relative_to(REPO)} 不存在")
            continue
        text = entry.read_text(encoding="utf-8")
        refs = referenced_agent_team_paths(text)
        script_refs = []
        for m in re.findall(r"((?:ddm-v2/)?scripts/agent_team/[A-Za-z0-9_./-]+)", text):
            ref = m.rstrip(".,;。、）)【」』")
            if "<" in ref or ">" in ref:
                continue
            script_refs.append(ref)
        missing = [r for r in refs if not _ref_exists(r)]
        missing += [r for r in script_refs if not (REPO / r.removeprefix("ddm-v2/")).exists()]
        if missing:
            err(f"{entry.relative_to(REPO)} 引用不存在：{missing}")
        else:
            ok(f"{entry.relative_to(REPO)} 引用的 {len(refs) + len(script_refs)} 個路徑都存在")


def check_5_domains_yaml_paths() -> None:
    try:
        import yaml
    except ModuleNotFoundError:
        warn("check_5 略過：此 python 環境無 pyyaml")
        return

    reg = AGENT_TEAM / "domains.yaml"
    if not reg.is_file():
        err("docs/agent-team/domains.yaml 不存在")
        return
    data = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    for d in data.get("domains", []) or []:
        did = d.get("id", "?")
        for doc in d.get("docs", []) or []:
            if not (DDM / doc).exists():
                warn(f"domains.yaml [{did}] docs 指向不存在：{doc}")
        for p in d.get("paths", []) or []:
            if not any(c in p for c in "*?[") and not (DDM / p).exists():
                warn(f"domains.yaml [{did}] paths 指向不存在：{p}")
    ok(f"domains.yaml 檢查完成（{len(data.get('domains', []))} 領域）")


def check_6_no_stale_moved_paths() -> None:
    """已搬走的舊路徑若出現在轉接檔／steering／agent 設定 → error（擋 commit）。

    MOST 從無到有，本來就不該把 agent 設定放進 .kiro/steering 或 .claude/dev_team；
    這裡守的是「日後有人誤把正本塞回工具目錄」。
    """
    stale = [
        ".kiro/steering/domains.yaml",
        ".kiro/steering/decisions.log",
        ".kiro/steering/commit-convention.md",
        ".kiro/steering/checkpoint.md",
        ".kiro/steering/verification.md",
        ".claude/dev_team/domains.yaml",
    ]
    whitelist = {
        "docs/architecture/docs-and-agent-docs-restructure-plan.md",
        "docs/agent-team/decisions.log",
    }
    root_globs = ["AGENTS.md", "CLAUDE.md"]
    ddm_globs = [
        ".claude/agents/*.md", ".kiro/agents/*.json", ".kiro/steering/*.md",
        "docs/agent-team/agents/*.md", "docs/agent-team/checkpoint.md",
        "docs/agent-team/commit-convention.md", "docs/agent-team/verification.md",
    ]
    seen_hit = False
    scan: list[Path] = []
    for pat in root_globs:
        scan += sorted(REPO.glob(pat))
    for pat in ddm_globs:
        scan += sorted(DDM.glob(pat))
    for f in scan:
        rel = str(f.relative_to(REPO))
        if rel in whitelist:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for s in stale:
            if s in text:
                err(f"{rel} 仍含已搬走的舊路徑：{s}（應改為 docs/agent-team/ 或 scripts/agent_team/）")
                seen_hit = True
    if not seen_hit:
        ok("無已搬走的舊路徑殘留")


def check_7_canon_code_paths_exist() -> None:
    """agent 正本＋AGENTS.md 內反引號引用的程式／測試路徑必須存在（斷鏈 → error）。
    路徑皆解析於 repo 根；舊寫法的 ddm-v2/ 前綴會先剝除再解析。"""
    code_re = re.compile(r"`((?:ddm-v2/)?[A-Za-z0-9_./-]+\.(?:py|js|ts|tsx|json|csv|yaml))`")
    real_roots = ("src", "tests", "test", "scripts", "migrations", "ddm-v2")
    files = list(AGENTS_DIR.glob("*.md")) + [REPO / "AGENTS.md"]
    seen = False
    for f in files:
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        for m in sorted(set(code_re.findall(text))):
            if any(x in m for x in ("<", ">", "example")):
                continue
            if m.split("/")[0] not in real_roots:
                continue
            if not (REPO / m.removeprefix("ddm-v2/")).exists():
                err(f"{f.relative_to(REPO)} 引用不存在的程式/測試路徑：{m}")
                seen = True
    if not seen:
        ok("agent 正本與 AGENTS.md 引用的程式/測試路徑都存在")


def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    out = ["^"]
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def check_8_business_files_have_domain() -> None:
    """每個業務檔（src/ddm_v2/**/*.py ＋ src/frontend/src/**/*.{ts,tsx}，排除 __pycache__、
    產生檔 api.d.ts、測試設定 *.config.ts）至少命中一個領域 paths；否則須在 no_domain_allowlist。
    命中 0 且不在白名單 → error（比照 LB check_8）。"""
    try:
        import yaml
    except ModuleNotFoundError:
        warn("check_8 略過：此 python 環境無 pyyaml")
        return
    reg = AGENT_TEAM / "domains.yaml"
    if not reg.is_file():
        err("check_8：docs/agent-team/domains.yaml 不存在")
        return
    data = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    pats = []
    for d in data.get("domains", []) or []:
        pats += [_glob_to_regex(p) for p in d.get("paths", []) or []]
    allow = {e.get("path") for e in data.get("no_domain_allowlist", []) or []}
    files = [
        f for f in _glob.glob(str(DDM / "src/ddm_v2/**/*.py"), recursive=True)
        + _glob.glob(str(DDM / "src/frontend/src/**/*.ts"), recursive=True)
        + _glob.glob(str(DDM / "src/frontend/src/**/*.tsx"), recursive=True)
        if "__pycache__" not in f
    ]
    missing = []
    for f in files:
        rel = os.path.relpath(f, DDM)  # repo 根相對，對齊 domains.yaml 的 paths
        if rel in allow:
            continue
        if not any(p.match(rel) for p in pats):
            missing.append(rel)
    if missing:
        for m in sorted(missing):
            err(f"業務檔命中 0 領域且不在 no_domain_allowlist：{m}（補進某領域 paths，或加白名單附理由）")
    else:
        ok(f"所有業務檔（{len(files)} 檔）都命中領域或在白名單")


def check_9_transceivers_are_thin() -> None:
    """轉接層必須維持薄（Howard 2026-09-16 裁決 1）：
      - .kiro/agents/*.json：prompt 摘要 ≤10 行，且引用 docs/agent-team/agents/<name>.md。
      - .claude/agents/*.md：正文（front-matter 之後）摘要 ≤10 行，且引用 docs/agent-team/agents/<name>.md。
    超出即 warning（不擋 commit，但提醒規則本體外流）。"""
    def _refs_canon(text: str, name: str) -> bool:
        return f"docs/agent-team/agents/{name}.md" in text

    # .kiro/agents/*.json
    for f in sorted((DDM / ".kiro" / "agents").glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            warn(f"{f.relative_to(REPO)} 無法解析為 JSON")
            continue
        name = data.get("name", f.stem)
        prompt = str(data.get("prompt", ""))
        n_lines = len([ln for ln in prompt.splitlines() if ln.strip()])
        if n_lines > 10:
            warn(f"{f.relative_to(REPO)} prompt 摘要 {n_lines} 行（>10）——轉接應維持薄，規則本體移到正本")
        if not _refs_canon(prompt + " ".join(data.get("resources", [])), name):
            warn(f"{f.relative_to(REPO)} 未引用正本 docs/agent-team/agents/{name}.md——轉接必須指路")

    # .claude/agents/*.md
    for f in sorted((DDM / ".claude" / "agents").glob("*.md")):
        text = f.read_text(encoding="utf-8")
        name = f.stem
        # 去掉 front-matter（--- … ---）後算正文非空行數
        body = text
        if text.lstrip().startswith("---"):
            parts = text.split("---", 2)
            body = parts[2] if len(parts) == 3 else text
        n_lines = len([ln for ln in body.splitlines() if ln.strip()])
        if n_lines > 10:
            warn(f"{f.relative_to(REPO)} 正文 {n_lines} 行（>10）——轉接應維持薄，規則本體移到正本")
        if not _refs_canon(text, name):
            warn(f"{f.relative_to(REPO)} 未引用正本 docs/agent-team/agents/{name}.md——轉接必須指路")
    ok("轉接層薄度檢查完成（.kiro/agents JSON prompt ≤10 行、.claude/agents 正文 ≤10 行、皆指向正本）")


def main() -> int:
    check_1_claude_imports_agents()
    check_2_transceivers_reference_existing_canon()
    check_3_agent_lists_consistent()
    check_4_entry_refs_exist()
    check_5_domains_yaml_paths()
    check_6_no_stale_moved_paths()
    check_7_canon_code_paths_exist()
    check_8_business_files_have_domain()
    check_9_transceivers_are_thin()

    print("== check_agent_config ==")
    for m in oks:
        print(f"OK   {m}")
    for m in warns:
        print(f"WARN {m}")
    for m in errors:
        print(f"ERR  {m}")
    print(f"-- {len(oks)} ok, {len(warns)} warn, {len(errors)} error --")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
