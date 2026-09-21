# AGENTS.md — MOST / DDM v2（most-builder monorepo）

工業工程 MiniMOST 工時量測平台：FastAPI 後端（`/api/v2`）＋ React 前端 ＋ PostgreSQL。
**專案在 `ddm-v2/`**（monorepo 根＝`most-builder/`，同層另有 `ddm-legacy/`、`ddm-v3/`、`minimost_level/`）。

> **本檔是薄入口（指路，不重寫規則）**。規則本體在 `ddm-v2/docs/`；此處只給一句話與連結，
> 避免同一條規則出現在兩處（DOC_CONVENTION R3 精神）。任何工具（Claude、Kiro）都以本檔與其指向的
> `ddm-v2/docs/agent-team/` 正本為單一事實來源。**幾乎所有指令都要先 `cd ddm-v2`。**

## 品質關卡（不可跳過）

- 每完成一個功能段落或準備 commit 前，必須跑品質關卡：**`ddm-v2/docs/agent-team/checkpoint.md`**。
- 主對話不得自行做 code review 或資安檢查——委派對應 reviewer（見 checkpoint）。
- 動到 agent 設定時，commit 前跑 `python3 scripts/agent_team/check_agent_config.py`（在 `ddm-v2/` 下）。
- 重大架構決策必須有 ADR 紀錄（`ddm-v2/docs/decisions/`）。

## agent 團隊（正本在 ddm-v2/docs/agent-team/agents/）

- `most-code-reviewer` — 機械面：typed contracts、Fail-Fast、加法演進（ADR-011）、i18n 對稱（ADR-032）、
  錯誤信封（ADR-034）、測試覆蓋。
- `most-logic-reviewer` — 參數化 `domain_id`，領域知識來自 `ddm-v2/docs/agent-team/domains.yaml`。
- `most-doc-sync` — 使用者核可後才改權威文件；先跑腳本再語意複核。
- 領域登記表：`ddm-v2/docs/agent-team/domains.yaml`（功能領域 → 路徑、graphify 錨點、權威文件、硬約束）。
- commit 慣例：`ddm-v2/docs/agent-team/commit-convention.md`。驗證規範：`ddm-v2/docs/agent-team/verification.md`。
- 決策追蹤：`ddm-v2/docs/agent-team/decisions.log`（只由主 context 追加）。

## 核心不變量（細節見對應正本／ADR，不在此重述）

- **單一權威引擎**：`ddm-v2/src/ddm_v2/most_engine/` 是所有 TMU 計算與 level 驗證的唯一來源；前端不自算
  （值一律來自 `POST /api/v2/minimost/calculate`）。動到引擎／rule-set／level → 必過
  `PYTHONPATH=src python scripts/core_logic/run_all.py`（黃金 GM=28／CM=29）。
- **unit 與 integration 分開跑**（同名 `test_search.py`，一起跑 basename 衝突）。
- **`.kiro/`、`.claude/` 永不 commit**（gitignore）；正本在 `docs/agent-team/`、腳本在 `scripts/agent_team/`。
- **LB 回寫（ADR-036）v1 直連無認證，只可內網／本機**：`lb-writeback/fetch` 直連 LB base URL、不經 gateway；掛 Traefik 前不得對外開放（ADR-036 §4／禁止事項）。

## 架構地圖與常用指令

- 專案總覽、目錄地圖、部署／測試／lint 指令：見 `ddm-v2/README.md` 與 `ddm-v2/docs/DOC_REGISTRY.md`（文件索引）。
  此處不重列，以免漂移。
- CI 關卡完整清單：`ddm-v2/docs/CI_GATES.md`（唯一權威）。

## graphify（知識圖譜）

- `ddm-v2/graphify-out/` 已於 WP-D1 重建並與 HEAD 同步（9323 節點）。回答 codebase 問題先 `graphify query "<問題>"`，
  改完程式 `graphify update .`；維護時機見 checkpoint。
- **日常＝`graphify update .`（只重抽程式、免 key、不接 `--code-only`）；重建整張圖才用 `graphify . --code-only`**（本機無 LLM key）：文件／paper／image 的**語意抽取需 LLM key**
  （GEMINI／ANTHROPIC／OPENAI 等）；code-only 走本地 AST、免 key，足夠日常程式圖維護。docs 的盤點與索引改由
  `DOC_REGISTRY.md` 三層入口＋領域索引處理，不依賴圖的語意層。

## 歷史文件

- `ddm-v2/docs/v3/`、`docs/html_con/`、`docs/architecture/legacy-inventory-and-engine-audit.md`、各 `*-worklog.md`、
  `roadmap/phase5-*` 等為歷史／存檔，檔頭已標「歷史文件」，**不可作為現況依據，agent 預設不讀**
  （分類見 `ddm-v2/docs/DOC_REGISTRY.md` 的〈歷史〉〈過程紀錄〉〈前瞻計畫〉區）。

## 跨專案整合

- 本專案與 LB（`/home/howard/workspace/line-balance_stream-weaver_v2`，Stream Weaver）強關聯：
  MOST 匯出 → LB 匯入（MOST 是工時標準來源，LB 是消費方做產線平衡）、auth 整合、部署拓撲。
- 共享契約以文件為單一來源（`ddm-v2/docs/lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md`）——找不到對應文件時先問，不要兩邊各寫一份。
