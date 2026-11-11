# 文件與 agent 設定重整實作書（MOST／ddm-v2 端）

> **給誰**：執行本重整的 agent（任何工具）。
> **狀態**：Design Accepted（2026-09-16，Howard 裁決六項——同 LB 端，見 §0.2）。**已逐階段落地（分支 `chore/agent-docs-shared`）：**
> - **階段一**（agent 團隊正本＋腳本＋轉接＋CLAUDE/AGENTS）：`aed28d2`、`356f5d0`、`2e46e72`、`9ba4986`；裁決落地 `be5e5a4`。
> - **WP-D1**（graphify 重建＋盤點）：`0817d9b`（`_inventory.md` 暫存，WP-D3 已刪）。
> - **WP-D2**（11 領域索引＋DOC_REGISTRY 三層入口＋三裁決＋歷史檔頭＋斷鏈訂正）：`2741657`、`5498648`。
> - **WP-D3**（`docs_check.py`＋checkpoint 加步驟＋most-doc-sync 要求＋文件規範節＋刪 `_inventory.md`）：本次。
> **對照**：LB 端同名實作書 `line-balance_stream-weaver_v2/docs/architecture/docs-and-agent-docs-restructure-plan.md`（commit `2b59ddc`），已完整落地並驗收（階段一＋二：`e942faa`…`fcc757c`）。本檔只寫 **MOST 的差異與現況**，共通設計不重抄（DOC_CONVENTION R3）。
> **分支**：`chore/agent-docs-shared`，自 `feature/lb-projection` 末端（`c9062eb`）分岔——因為重整的素材（ADR-035 全部文件、lb-integration/）都在該分支上。**不 push、不合入**。
> **不改任何產品程式**。

---

## 0. 現況與裁決

### 0.1 MOST 與 LB 的關鍵差異（2026-09-16 實際盤點）

| 項目 | LB | **MOST（本 repo）** |
|---|---|---|
| repo 邊界 | repo 根＝專案根 | repo 根＝`most-builder/`，**專案在 `ddm-v2/`**；同層還有 `ddm-legacy/`、`ddm-v3/`、`minimost_level/` |
| agent 定義 | `.kiro/agents/` 8 個（正本） | **`.kiro/agents/` 與 `.claude/agents/` 都是空的**——MOST **完全沒有** reviewer／doc-sync agent |
| 品質關卡 | `checkpoint.md` ＋ hooks ＋ `domains.yaml`（19 領域） | **完全沒有**：無 checkpoint、無 hook、無 `domains.yaml`、無 `decisions.log` |
| steering | 10 份 | 5 份（`development-workflow` 95 行、`most-domain-knowledge` 105、`project-conventions` 76、`wi-motion-core-structure` 52、`graphify` 5） |
| 入口檔 | 無（階段二新建 `docs/README.md`） | 有 `docs/DOC_REGISTRY.md`（42 條連結／89 份文件 → **約 47 份不在索引**） |
| 工具設定 | 四套（.kiro／.claude／.github／.cursor） | 兩套（.kiro／.claude）＋ repo 根 `CLAUDE.md`（146 行，已追蹤） |
| graphify | 階段二新建，與 HEAD 同步 | `graphify-out/` 存在但為 **2026-09-02** 建（8527 節點），**落後整個 ADR-035**（投影層 11 檔、作業版 UI、B1／B7 全部不在圖裡） |
| commit 慣例 | `[Phase N][Scope] type(scope): …` ＋ `-Signed-off-by` | 實際慣例為 `implements ADR-NNN: WPn …` 與 `docs: …`（**未成文**，散在 agent brief 裡） |

**結論**：MOST 的階段一不是「統一四套」，而是**把 LB 驗證過的那套建起來（從無到有）**，並以 LB 的正本為範本。

### 0.2 沿用 LB 的六項裁決（Howard 2026-09-16）

1. 分類法唯一＝`domains.yaml` 的領域（MOST 需新建，草案 §1 C）。
2. 目錄最小改動＋索引層（MOST 擴充既有 `DOC_REGISTRY.md`，**不另建 README**）。
3. 歷史文件原地不動、標註「不可作為現況依據」、agent 預設不讀。
4. 檢查腳本：斷鏈擋 commit；孤兒、重複權威先警告。
5. graphify 先重建，之後由 checkpoint 維護。
6. 共用內容進版控；`.kiro/`、`.claude/` 只留薄轉接。

---

## 1. 階段一：建立 agent 團隊正本

### A 位置（MOST 專屬決定）

| 檔 | 位置 | 理由 |
|---|---|---|
| `AGENTS.md` | **`most-builder/AGENTS.md`**（repo 根，與 `CLAUDE.md` 同層） | 工具是在 repo 根被載入的 |
| 正本 `agent-team/` | **`ddm-v2/docs/agent-team/`** | MOST 的文件都在 `ddm-v2/docs/`；`AGENTS.md` 指過去 |
| 腳本 | `ddm-v2/scripts/agent_team/{domain_guard.py,check_agent_config.py}`、`ddm-v2/scripts/docs_check.py` | 與 LB 同形；自 LB 複製後改路徑常數，檔頭註明來源 commit |
| 轉接層 | `ddm-v2/.kiro/`（steering＋agents JSON）、`ddm-v2/.claude/agents/`、`most-builder/CLAUDE.md` | 維持 gitignore |

### B agent 清單（新建，比照 LB 但只取需要的）

| agent | 用途 |
|---|---|
| `most-code-reviewer` | 機械面：typed contracts、Fail-Fast、加法演進（ADR-011）、i18n 對稱（ADR-032）、錯誤信封（ADR-034）、測試覆蓋 |
| `most-logic-reviewer` | **參數化 `domain_id`**，領域知識來自 `domains.yaml` |
| `most-doc-sync` | 使用者核可後才改權威文件；先跑 `docs_check.py` 再語意複核 |

LB 的 architecture／backend／frontend／testing／validator 五個**不建**（MOST 由主對話＋執行 agent 直接做，沒有這層分工需求）。

### C `domains.yaml` 草案（領域鍵，細節由執行者依實際程式補 paths／anchors／invariants）

| 領域 | 程式範圍（起點） | 權威文件（起點） |
|---|---|---|
| `most-engine` | `src/ddm_v2/most_engine/**` | `docs/core-logic/*`、ADR-014／028 |
| `rule-set` | rule-set 服務與版本、回放 | ADR-023（MOST）、ADR-025 |
| `level-system` | `most_engine/level.py`、`services/v2/level_validation_service.py` | `docs/core-logic/level-system-core-logic-spec.md` |
| `wi-workbench` | `services/v2/worksheet_service.py`、SIMO 配對、clone | data-model 規格、ADR-020 |
| `motion-module` | `services/v2/motion_module_service.py` | 對應 ADR |
| `nlp-compiler` | `most_compiler/**`、`nlp/**` | ADR-033、compiler spec |
| `lb-projection` | `lb_projection/**`、`services/v2/export_service.py`、匯出路由 | **`docs/lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md`**、ADR-035 |
| `job-ux` | `src/frontend/src/features/level-system/**` | 作業版實作書 |
| `i18n` | `shared/i18n/**`、`errors/registry.py` | ADR-032、ADR-034 |
| `excel-import` | `services/v2/import_service.py`、`schemas/v2/import_excel.py` | ADR-013 |
| `auth-rbac` | 權限相依點 | ADR-019 |

**驗收**：每個業務檔（`src/ddm_v2/**/*.py`、`src/frontend/src/**/*.ts(x)`）至少命中一個領域；例外進 `no_domain_allowlist` 並逐條寫理由；`check_agent_config.py` 對漏網檔 error（LB check_8 同款）。

### D `checkpoint.md`／`commit-convention.md`（MOST 專屬內容）

- `checkpoint.md`：比照 LB 但 agent 名改 `most-*`；測試指令用 MOST 實際的（`PYTHONPATH=src pytest tests/unit`、`tests/integration`、`python3 scripts/core_logic/run_all.py`、前端 `npm run typecheck && npm run build`、Playwright via `preview_server`）。
- `commit-convention.md`：**把現行未成文慣例寫下來**——`implements ADR-NNN: <WP> <一句話>`（實作）、`docs: …`（純文件）、body 逐檔列變更；並記錄「`.kiro/`、`.claude/` 永不 commit」。
- `decisions.log`：新建，格式同 LB（tab 分隔：日期／domain_id／檔與節／摘要／分支），**只由主 context 追加**。

### E 工具語法

Claude 的 `@AGENTS.md` 已在 LB 實測可用；Kiro steering 用 `#[[file:…]]`、agent JSON 用「摘要 ≤10 行＋指路＋`resources: file://…`」。MOST 只有這兩套，不需再測 Copilot／Cursor。

### F `CLAUDE.md`（repo 根，146 行）改薄轉接

保留 Claude 專屬段落（`.claude/` 位置、skills、hook 指向），其餘規則指向 `AGENTS.md`。**改之前先逐條查證**是否與現況相符（LB 的 `CLAUDE.md` 曾有六處過時敘述）；發現過時就在本輪一併校正，並把「查到的過時清單」附在回報裡。

---

## 2. 階段二：文件重整（LB 的 WP-D1／D2／D3，MOST 差異）

- **WP-D1 盤點**：先 `graphify .` 重建（現有圖已落後 ADR-035 全部工作）。除四類問題（斷鏈／孤兒／重複權威／歷史）外，MOST 另需處理：
  - `docs/DOC_REGISTRY.md` 未收錄的約 47 份 → 逐份判定「收進索引／標歷史／確實該刪」。
  - ~~空目錄 `docs/sample_excel/`、`docs/html_con/` → 判定去留。~~ **訂正（2026-09-17，WP-D1 實測）**：兩者**非空目錄**（原敘述只數 `.md`，漏數其他副檔名）——`docs/sample_excel/` 有 3 個 `.xlsx`（MOST 邏輯原始 Excel，來源素材）；`docs/html_con/` 有 2 個 `.html`（`v2-workbench.html`、`v2-wi-preview.html`，封存原型）。裁決：**保留，標「素材／封存原型」**，非去留空目錄問題。
  - `docs/v3/`、`docs/llm/`、`docs/v4-integration/`、`docs/roadmap/` → 分類為「歷史／前瞻計畫／現行」，前瞻計畫在索引標「未排程，實作前需回到本文件補 spec」。
- **WP-D2**：`docs/domains/<id>.md` 11 份（七段格式同 LB，「吃哪些欄位／狀態」要實際查程式）；`DOC_REGISTRY.md` 升為三層入口（改什麼功能 → 領域索引 → 權威規格），保留既有權威順序段落。
- **WP-D3**：`docs_check.py`（自 LB 複製改路徑）、`checkpoint.md` 加兩步、`most-doc-sync` 正本要求先跑腳本、`DOC_CONVENTION` 對應段落（MOST 若無此檔則在 `DOC_REGISTRY.md` 補一節「文件規範」並指向 LB 版本的三條硬規則精神——**不得複製全文**）。

---

## 3. 禁止事項

1. 不動產品程式。
2. 不 push、不合入。
3. 不做 docs 大搬遷；歷史文件不刪（標註即可）。
4. 規則不得重複——`AGENTS.md` 薄、內容留 `docs/`。
5. 子 agent 不得寫 `.kiro/`；`decisions.log` 只由主 context 追加。
6. 盤點與裁決分離：重複權威取捨、未收錄文件的去留、空目錄處置，一律交 Howard。
7. 腳本自 LB 複製時，**檔頭註明來源 repo 與 commit**；日後兩邊若要分歧，先回報。
