#!/usr/bin/env python3
"""docs 一致性檢查（WP-D3，實作書 §2）。

來源：line-balance_stream-weaver_v2/scripts/docs_check.py（commit 81cc553）。
本 repo（MOST／ddm-v2）差異（與 LB 分歧前先回報）：
  - split-root：git 根＝most-builder/，docs 在 ddm-v2/docs、程式在 ddm-v2/。REPO＝git 根，DOCS＝REPO/ddm-v2/docs。
  - 孤兒判準改為「不在 DOC_REGISTRY.md 任何一區」（Howard 2026-09-17 裁決），非 LB 的「無其他 md 引用檔名」。
  - 領域索引一致性另比對「domain md 的程式入口 vs domains.yaml paths」。
  - 白名單：跨 repo LB 路徑、產生檔（api.d.ts）、設計期未建腳本（llm spec 三支），各註明理由。

擋 commit（error）：
  - 斷鏈：docs 引用的程式／測試／資料檔或 .md 連結不存在（歷史 R2 刪線 ~~…~~ 除外；白名單除外）。

警告（warning，不擋）：
  - 孤兒：非歷史／非入口且不在 DOC_REGISTRY.md 任何一區。
  - 缺狀態標頭：ADR／spec 沒有「## 狀態」。
  - 領域索引與 domains.yaml 不一致（檔名集合 或 程式入口 paths）。
  - graphify 圖落後 HEAD 超過門檻。

退出碼：有 error → 1；只有 warning 或全綠 → 0。
用法：python3 scripts/docs_check.py（在 ddm-v2/ 下）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """MOST split-root：git 根（含 .git）＝most-builder/；專案在 ddm-v2/。"""
    for parent in [start, *start.parents]:
        if (parent / ".git").exists():
            return parent
        if (parent / "ddm-v2" / "docs" / "agent-team" / "domains.yaml").is_file():
            return parent
    return start.parent


REPO = find_repo_root(Path(__file__).resolve())
DDM = REPO / "ddm-v2"
DOCS = DDM / "docs"

# 跨 repo LB 路徑（TASK_CSV_INPUT_CONTRACT 是 LB 端提供的輸入契約副本；v4-integration 為 v4/LB 評估）。
# 這些是 MOST 對接／評估用的外部參考，不在本 repo，非 MOST 斷鏈。
CROSS_REPO_LB_PREFIXES = ("src/optimization/", "src/shared/domain/", "src/result/", "src/versioning/", "src/static/")
# 產生檔（由工具生成，非手寫源碼；可能未生成或 gitignore）。
GENERATED_ALLOWLIST = {
    "src/shared/types/api.d.ts",  # 由 npm run gen:api 自 OpenAPI 產生
    "src/frontend/openapi.json",  # 由後端 OpenAPI 匯出（gitignore；乾淨檢出不存在）
}
# 設計期規劃、尚未建的腳本（llm spec 記錄設計意圖；worklog 已自註不存在）。
FORWARD_REF_ALLOWLIST = {
    "scripts/dev_seed_ai_bundles.py",
    "scripts/build_option_embeddings.py",
    "scripts/prune_ai_runs.py",
    # LB 端產法／原始 fixture 路徑（跨 repo，記於 MOST fixture README 的來源出處，非 MOST 檔）：
    "scripts/gen_writeback_sample.py",
    "test/backend/integration/fixtures/most_integration/writeback_sample.json",
}
GRAPH_LAG_THRESHOLD = 5  # 圖落後 HEAD 超過幾個 commit 才警告

# 三層入口／規範／缺口／盤點暫存等「本身就是入口或過程」的檔，不當孤兒。
ENTRIES = {
    "docs/DOC_REGISTRY.md", "docs/BACKLOG.md", "docs/_inventory.md",
    "docs/decisions/README.md",
}
REAL_ROOTS = ("src", "tests", "test", "scripts", "migrations")

errors: list[str] = []
warns: list[str] = []
oks: list[str] = []


def err(m: str) -> None: errors.append(m)
def warn(m: str) -> None: warns.append(m)
def ok(m: str) -> None: oks.append(m)


def _clean(p: str) -> bool:
    return not any(x in p for x in ("...", "…", "<", ">", "example", "/foo", "/bar", "XXX", "dXXX"))


def _all_docs() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


HISTORY_MARK = "歷史文件（不可作為現況依據）"


def _is_history(d: Path, txt: str | None = None) -> bool:
    if txt is None:
        txt = d.read_text(encoding="utf-8", errors="replace")
    return HISTORY_MARK in txt


CODE_RE = re.compile(r"`((?:ddm-v2/)?[A-Za-z0-9_./?=-]+\.(?:py|md|js|ts|tsx|json|csv|yaml))`")
LINK_RE = re.compile(r"\]\(([^)]+\.md)[^)]*\)")
STRIKE_RE = re.compile(r"~~.*?~~", re.S)


def _strip_history(txt: str) -> str:
    """移除 R2 刪線 ~~...~~ 內容——歷史紀錄（已刪除物），不算 live 引用。"""
    return STRIKE_RE.sub("", txt)


def _code_ref_ok(base: str) -> bool:
    if base.split("/")[0] not in REAL_ROOTS:
        return True  # 非程式路徑（如純檔名），略過
    if base.startswith(CROSS_REPO_LB_PREFIXES):
        return True
    if base in GENERATED_ALLOWLIST or base in FORWARD_REF_ALLOWLIST:
        return True
    return (DDM / base).exists() or (REPO / base).exists()


def check_broken_links() -> None:
    n = 0
    for d in _all_docs():
        raw = d.read_text(encoding="utf-8", errors="replace")
        if _is_history(d, raw):
            continue  # 歷史文件的引用不算 live 斷鏈
        # v4-integration：前瞻＋跨 repo（v4/LB）評估，程式引用多指向 LB repo，非 MOST live 斷鏈
        if "v4-integration" in d.parts:
            continue
        txt = _strip_history(raw)
        rel_d = str(d.relative_to(REPO))
        for m in sorted(set(CODE_RE.findall(txt))):
            if not _clean(m):
                continue
            base = m.split("?")[0]
            if base.split("/")[0] not in REAL_ROOTS:
                continue
            if not _code_ref_ok(base):
                err(f"斷鏈 {rel_d} → 程式/測試檔不存在：{base}")
                n += 1
        for m in sorted(set(LINK_RE.findall(txt))):
            if m.startswith("http") or not _clean(m):
                continue
            target = os.path.normpath(os.path.join(str(d.parent), m))
            # 跨 repo 連結（解析後落在本 repo 之外，如 LB 的 DOC_CONVENTION.md）不算本 repo 斷鏈
            try:
                Path(target).resolve().relative_to(REPO.resolve())
            except ValueError:
                continue
            if not os.path.exists(target):
                err(f"斷鏈 {rel_d} → .md 連結不存在：{m}")
                n += 1
    if n == 0:
        ok("無斷鏈（歷史文件與白名單除外）")


def check_orphans() -> None:
    """孤兒＝非歷史、非入口，且路徑／檔名**不在 DOC_REGISTRY.md 任何一區**（Howard 裁決）。
    ADR 經「ADR 索引層」一跳可達（DOC_REGISTRY → decisions/README.md → 各 ADR），不算孤兒。
    某目錄若被 DOC_REGISTRY 以整區收編（如 v4-integration/、llm/gold-review/），其下檔案亦視為已收。"""
    reg_txt = (DOCS / "DOC_REGISTRY.md").read_text(encoding="utf-8", errors="replace")
    # DOC_REGISTRY 以整目錄收編的區（連結指向該目錄某檔＋文字說明「N 份」）
    dir_level_covered = ("docs/v4-integration/", "docs/llm/gold-review/")
    orph = []
    for d in _all_docs():
        rel = str(d.relative_to(REPO))          # ddm-v2/docs/...
        docs_rel = str(d.relative_to(DDM))      # docs/...
        if docs_rel in ENTRIES:
            continue
        if "agent-team" in d.parts:
            continue  # dev-team infra，由 AGENTS.md/DOC_REGISTRY dev-team 區收錄
        if _is_history(d):
            continue  # 已標歷史，收於 DOC_REGISTRY 歷史區
        if docs_rel.startswith("docs/decisions/ADR-"):
            continue  # ADR 索引層：經 decisions/README.md 一跳可達
        if any(docs_rel.startswith(p) for p in dir_level_covered):
            continue  # 目錄整區收編
        in_reg = docs_rel[len("docs/"):] in reg_txt or d.name in reg_txt
        if not in_reg:
            orph.append(rel)
    for o in sorted(orph):
        warn(f"孤兒（不在 DOC_REGISTRY.md 任何一區）：{o}")
    if not orph:
        ok("無孤兒文件（皆在 DOC_REGISTRY 某一區、ADR 索引層、或已標歷史）")


def check_status_headers() -> None:
    n = 0
    for d in _all_docs():
        rel = str(d.relative_to(DDM))
        if not (rel.startswith("docs/decisions/ADR-") or rel.startswith("docs/architecture/")
                or rel.startswith("docs/core-logic/")):
            continue
        txt = d.read_text(encoding="utf-8", errors="replace")
        if _is_history(d, txt):
            continue
        if not re.search(r"^#{1,3}\s*狀態", txt, re.M) and "## Status" not in txt \
                and "**狀態" not in txt and "> **狀態" not in txt:
            warn(f"缺狀態標頭（## 狀態 / **狀態**）：{rel}")
            n += 1
    if n == 0:
        ok("ADR/spec 狀態標頭齊全（歷史除外）")


def check_domain_index_matches() -> None:
    try:
        import yaml
    except ModuleNotFoundError:
        warn("領域索引一致性略過：此 python 無 pyyaml")
        return
    reg = DOCS / "agent-team" / "domains.yaml"
    data = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    domains = data.get("domains", [])
    ids = {d["id"] for d in domains}
    idx = {p.stem for p in (DOCS / "domains").glob("*.md")}
    if ids != idx:
        warn(f"領域索引檔名與 domains.yaml id 不一致：缺索引 {sorted(ids - idx)}，多索引 {sorted(idx - ids)}")
    else:
        ok(f"領域索引檔名與 domains.yaml 一致（{len(ids)} 個）")
    # 程式入口 vs domains.yaml paths：抽 domain md 的反引號路徑，至少要與該 domain 的 paths 有交集
    mismatch = 0
    for dm in domains:
        did = dm["id"]
        md = DOCS / "domains" / f"{did}.md"
        if not md.is_file():
            continue
        md_txt = md.read_text(encoding="utf-8")
        md_paths = set(re.findall(r"`(src/[A-Za-z0-9_./*-]+)`", md_txt))
        yaml_prefixes = {p.split("*")[0].rstrip("/") for p in dm.get("paths", [])}
        if md_paths and yaml_prefixes:
            hit = any(any(mp.startswith(yp) or yp.startswith(mp.split("*")[0].rstrip("/")) for yp in yaml_prefixes)
                      for mp in md_paths)
            if not hit:
                warn(f"領域索引 {did}.md 程式入口與 domains.yaml paths 無交集（請對齊）")
                mismatch += 1
    if mismatch == 0:
        ok("領域索引程式入口與 domains.yaml paths 一致")


def check_graph_freshness() -> None:
    graph = DDM / "graphify-out" / "graph.json"
    if not graph.is_file():
        warn("graphify 圖不存在（ddm-v2/graphify-out/graph.json）；跑 `graphify . --code-only` 建圖")
        return
    built = json.loads(graph.read_text(encoding="utf-8")).get("built_at_commit")
    if not built:
        warn("graphify 圖無 built_at_commit")
        return
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    if built == head:
        ok(f"graphify 圖為最新（built_at_commit == HEAD {head[:7]}）")
        return
    lag = subprocess.run(["git", "rev-list", "--count", f"{built}..HEAD"], cwd=REPO, capture_output=True, text=True)
    try:
        n = int(lag.stdout.strip())
    except ValueError:
        n = GRAPH_LAG_THRESHOLD + 1
    if n > GRAPH_LAG_THRESHOLD:
        warn(f"graphify 圖落後 HEAD {n} 個 commit（built={built[:7]}）；跑 `graphify update .`（只重抽程式、免 LLM key；不接 --code-only，那是完整建圖的參數）")
    else:
        ok(f"graphify 圖落後 {n} commit（未超門檻 {GRAPH_LAG_THRESHOLD}）")


def main() -> int:
    check_broken_links()
    check_orphans()
    check_status_headers()
    check_domain_index_matches()
    check_graph_freshness()
    print("== docs_check ==")
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
