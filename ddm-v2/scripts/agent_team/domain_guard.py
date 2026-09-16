#!/usr/bin/env python3
"""MOST（ddm-v2）領域守衛（advisory）。

來源：line-balance_stream-weaver_v2/scripts/agent_team/domain_guard.py（commit 2b59ddc）。
本 repo 差異（與 LB 分歧前先回報）：render() 的收尾指向 `most-doc-sync`（LB 為 `lb-doc-sync`）。
其餘（repo root 探測、glob→regex、map／posttooluse／userprompt 三模式）與 LB 逐行相同。

把「改到哪個檔案 / 在討論什麼」對應回 docs/agent-team/domains.yaml 的領域，
並把該領域的權威文件與硬約束注入回模型的 context。

三種用法：

    domain_guard.py posttooluse   < hook JSON   # 存檔（PostFileSave）之後
    domain_guard.py userprompt    < hook JSON   # 使用者送出訊息時
    domain_guard.py map <path>...               # CLI：給 checkpoint 品質關卡用

只提醒，不阻擋——真正的關卡在 checkpoint 品質關卡。任何錯誤都靜默退出 0。
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "docs" / "agent-team" / "domains.yaml").is_file():
            return parent
        if (parent / ".git").exists():
            return parent
    return start.parent


REPO = find_repo_root(Path(__file__).resolve())
REGISTRY = REPO / "docs" / "agent-team" / "domains.yaml"

STATE_DIR = Path(tempfile.gettempdir()) / "most-domain-guard"


def load_domains() -> list[dict]:
    import yaml

    with REGISTRY.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("domains", []) or []


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    out = ["^"]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def rel_path(raw: str) -> str:
    try:
        return str(Path(raw).resolve().relative_to(REPO))
    except (ValueError, OSError):
        return raw.lstrip("./")


def domains_for_paths(paths: list[str], domains: list[dict]) -> list[dict]:
    rels = [rel_path(p) for p in paths if p]
    hits = []
    for domain in domains:
        patterns = [glob_to_regex(g) for g in domain.get("paths", [])]
        if any(rx.match(r) for rx in patterns for r in rels):
            hits.append(domain)
    return hits


def domains_for_text(text: str, domains: list[dict]) -> list[dict]:
    low = text.lower()
    hits = []
    for domain in domains:
        for kw in domain.get("keywords", []):
            k = kw.lower()
            if k.isascii():
                if re.search(rf"(?<![a-z0-9_]){re.escape(k)}(?![a-z0-9_])", low):
                    hits.append(domain)
                    break
            elif k in low:
                hits.append(domain)
                break
    return hits


def already_warned(session: str, domain_ids: list[str]) -> list[str]:
    if not session:
        return domain_ids
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state = STATE_DIR / f"{re.sub(r'[^A-Za-z0-9_-]', '_', session)}.txt"
        seen = set(state.read_text(encoding="utf-8").split()) if state.exists() else set()
        fresh = [d for d in domain_ids if d not in seen]
        if fresh:
            with state.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(fresh) + "\n")
        return fresh
    except OSError:
        return domain_ids


def render(hits: list[dict], trigger: str) -> str:
    lines = [
        f"[dev-team 領域守衛] {trigger}命中以下領域。這是提醒，不是阻擋。",
        "",
    ]
    for d in hits:
        lines.append(f"### {d['id']} — {d.get('title', '')}")
        docs = d.get("docs", [])
        if docs:
            lines.append("權威文件：" + "、".join(docs))
        for inv in d.get("invariants", []):
            lines.append(f"  - {inv}")
        if d.get("review_note"):
            lines.append(f"  註：{d['review_note'].strip()}")
        lines.append("")
    lines.append(
        "若這次改動或討論會**改變**上述任一條規則的語意，先問使用者要不要更新邏輯；"
        "獲得同意後由 most-doc-sync 更新對應文件。commit 前跑 checkpoint 品質關卡"
        "（docs/agent-team/checkpoint.md）。"
    )
    return "\n".join(lines)


def emit(event: str, context: str) -> None:
    print(context)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "map":
        domains = load_domains()
        hits = domains_for_paths(sys.argv[2:], domains)
        for d in hits:
            print(f"{d['id']}\t{d.get('title', '')}\t{','.join(d.get('docs', []))}")
        return 0

    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    domains = load_domains()
    session = str(payload.get("session_id", ""))

    if mode == "posttooluse":
        tool_input = payload.get("tool_input") or {}
        tool_response = payload.get("tool_response") or {}
        candidates = [
            payload.get("file_path"),
            payload.get("filePath"),
            payload.get("path"),
            tool_input.get("file_path"),
            tool_input.get("path"),
            tool_response.get("filePath"),
        ]
        hits = domains_for_paths([c for c in candidates if c], domains)
        trigger = "檔案改動"
        event = "PostToolUse"
    elif mode == "userprompt":
        text = str(
            payload.get("prompt")
            or payload.get("userInput")
            or payload.get("message")
            or ""
        )
        hits = domains_for_text(text, domains)
        trigger = "討論內容"
        event = "UserPromptSubmit"
    else:
        return 0

    if not hits:
        return 0

    fresh_ids = already_warned(session, [d["id"] for d in hits])
    fresh = [d for d in hits if d["id"] in fresh_ids]
    if not fresh:
        return 0

    emit(event, render(fresh, trigger))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # 守衛壞掉不得擋住工作
        if os.environ.get("MOST_DOMAIN_GUARD_DEBUG"):
            raise
        sys.exit(0)
