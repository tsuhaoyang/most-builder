# ADR-023：字典管理統一 — active 旗標、選項級編輯、與 ADR-014 的調和

- **狀態**：Accepted（使用者/IE 指示於 2026-07-20；協調者裁決）
- **決策者**：Howard（IE）＋ 審查總召
- **關聯**：**ADR-014（值權威）— 本 ADR 為其執行細則，不推翻其原則**；ADR-021（IA）、ADR-022（兩層工作台）、`docs/v3/v2-authoritative-model-guide.md` §5
- **本文件是 P2 所有派工的必讀母版。**

## 1. 背景與三個推翻性發現

使用者指出：v3 的字典管理是**單一入口的兩層結構**（版本清單 → 點進版本編輯該版所有字典設定），而 v2 拆成不相干的「字典管理」（詞彙庫）與「Rule-set」（唯讀參數表）兩個 tab。經 Playwright 實操 v3 ＋ 程式碼深度對照，三項與原假設不符：

**發現 1｜v2 後端已有版本生命週期，缺的是 active 旗標、選項粒度與前端。**
`api/routes/v2/rule_set.py` 已有 `list`/`full`/`clone-draft`/`put-full`/`publish`，服務層 `rule_set_service.py:92-146` 含 draft-only 凍結與 audit log。`RuleSetViewer.tsx:74` 寫「編輯/版本化為後續功能」是**前端文案落後於後端事實**。

**發現 2｜v3 的 archive 是無效程式碼，不得照抄。**
`dictionaries.py:410-422` 檢查 `is_active` 後只 `db.commit()`，**無任何欄位變更**——`DictionaryVersion` 根本沒有 status/archived 欄，只有 `is_active`。v3 UI 的「封存」按鈕點下去除了跳成功訊息什麼都不做。**v2 的 `status IN ('draft','published','retired')` 語意嚴格優於 v3，retired 就是 archive，已存在。**

**發現 3｜v3 有 work_vocab_items 的對應物（LexicalOption），但 v2 的設計較佳，不向 v3 靠攏。**
v3 `lexical_options` 綁 `dictionary_version_id` CASCADE（換字典版本＝物件清單重建）；v2 `work_vocab_items` 是全域主數據，帶 `source_system IN ('local','mes','erp','plm','imported')` 供 PLM/MES/ERP 介接。**保留 v2 設計**，但它不該叫「字典」。

## 2. 結構性約束：為什麼不能照抄 v3 的 CRUD

| | v3 | v2 |
|---|---|---|
| 選項模型 | **單一泛型表** `parameter_options`，7 參數共用（`option_code/display_text_zh/tmu_value/...`） | **11 張專用子表**，因參數語意不同構 |
| A | 同一張表的選項 | `rule_a_bands`＝**區間帶**（component/max_value/index_value），無「選項代碼」概念 |
| P | 同上 | `rule_p_bases` ＋ `rule_p_addons`（兩張，addon ≤2） |
| M | 同上 | **五張**：verbs / ladder_bands / foot_bands / rotation_bands / hand_bands |

**結論：v3 的「七個參數分頁」是 UI 概念，v2 照抄；但 v3 的「一套 `PUT /options/{id}` 打天下」在 v2 不可能成立。** v2 的選項級 CRUD 必須是每參數一組端點（P/M 需分頁內次級 tab）。A 因帶界必須連續無洞，採整組替換而非單筆增刪。

## 3. 決策

### 3.1 命名（UI 層改名，資料層不動）

| 現況 | 改為 | 理由 |
|---|---|---|
| tab「Rule-set」 | **「MOST 字典」** | 這才是 v3 心智模型的「字典」 |
| tab「字典管理」（詞彙庫＋範本） | 詞彙庫 → **「主數據」**；範本庫歸屬待 ADR-021 後續裁決 | 「字典」之名必須讓給 rule-set |
| 表 `rule_sets` / API `/api/v2/rule-sets` | **保持不變** | 改名成本高、風險大；「rule set」在工程層準確。**UI 稱字典、資料層稱 rule-set，兩者同物**（本 ADR 明記） |

### 3.2 版本生命週期（v2 保持四態，比 v3 精確）

`status ∈ {draft, published, retired}` × `is_active ∈ {true,false}`：

- **clone-draft**：`new_code` 改選填，缺省自動生成 `{code}_DRAFT_{YYYYMMDDHHMM}`（須查重附序號，code 有 UNIQUE）
- **publish**：`draft → published`，**新增發布前驗證**＝`load_rule_set_from_db(code).validate_complete()`（引擎自己的完整性契約，比 v3「數一數有沒有選項」精確，且保證 activate 後不會 runtime 才炸）
- **activate**（v2 全新）：前置 `status='published'` ＋ `validate_complete()` ＋ 寫 audit log；實作為同交易「先全體 deactivate → 再單一 activate」，**並加 partial unique index** `CREATE UNIQUE INDEX ... ON rule_sets ((true)) WHERE is_active`（比 v3 多一道 DB 防線，併發雙 activate 會撞 unique 而非靜默雙 active）
- **retire**（＝v3 的 archive，但真的會生效）：`status='retired'`，前置 `is_active=false`

### 3.3 與 ADR-014 的調和（本 ADR 的核心）

ADR-014 約束的是**「認證版本的值」**，不是「禁止一切線上編輯」。其否決選項 B 的理由是「破壞既有 cycle 快照回放；違反 published 凍結原則」——**否決的是改 published 版本**。而 v2 的 `replace_children` 已強制 `status != 'draft'` → 409，凍結機制已存在且正確。

**四條規則（全部可機械驗證）**：

**規則 1 — 三層可變性矩陣**

| 資料 | draft | published(非 active) | published+active | retired |
|---|---|---|---|---|
| 子表選項值（TMU/帶界/code） | ✅ | ❌409 | ❌409 | ❌409 |
| 標籤/句子文字 | ✅ | ❌409 | ❌409 | ❌409 |
| **同義詞** | ✅ | **✅** | **✅** | ❌ |
| 版本 metadata（name/notes） | ✅ | ✅ | ✅ | ✅ |
| `is_active` | ❌（須先 publish） | ✅ activate | ✅（他人 activate 時隱含 deactivate） | ❌ |
| `status` | →published | →retired（須先 deactivate） | ❌ | 終態 |

同義詞那格是 ADR-014 白紙黑字授權：「published rule-set 唯一可後補資料＝同義詞（僅影響建議層不影響工時）」。

**規則 2 — clone-on-write（照抄 v3 最好的設計）**
使用者在 published/active 版按編輯 → 確認對話框「是否建立草稿版本後編輯？」→ 自動 clone → 切到 draft 續編。**使用者從不撞 409**，凍結規則透過 UI 流程自然滿足。

**規則 3 — 認證血緣 `provenance`（v2 新增，v3 無）**
`rule_sets.provenance ∈ {certified_import, manual, cloned}`：
- `certified_import`＝由 `import_v3_dictionary.py` → seed → `dev_seed_v2.py` 產生（V1/V2 屬此）
- **`provenance='certified_import'` 的版本，任何選項級寫入或 `PUT /full` 一律 409，即使 status='draft'。**

這讓 ADR-014 的「認證版本禁手改」從文件約定變成 **DB 可驗證的規則**。IE 要改認證值只有一條路：改 JSON → 重跑腳本 → 新版本。

**規則 4 — activate 雙重把關**：`status='published'` ＋ `validate_complete()` ＋ audit log。這是替代 IE 認證的最低治理門檻。

### 3.4 回放安全（不可違反的鐵則）

三處 FK 皆 `RESTRICT`（`most_cycles.rule_set_id`、`motion_module_versions.rule_set_id`、`most_worksheets.default_rule_set_id`）→ DB 層已擋死「刪掉被引用的 rule_set」。`load_rule_set_from_db(session, code)` **只依 code 查表，不看 status 也不看 is_active** → retired 版本仍可載入計算，回放能力天然保留。

**明文禁令（必須寫進 CI_GATES）**：
1. **`load_rule_set_from_db` 永遠不得依 status/is_active 過濾。回放路徑不看治理狀態。**
2. 治理狀態只在「選擇」時生效（`GET /rule-sets?selectable=true` 只回 published+active 供 UI 下拉），不在「載入」時生效
3. 新增整合測試：建立引用 retired 版本的 cycle → retire → 重算 → TMU 不變
4. worksheet 的 `default_rule_set_id` 是**建立時凍結的快照**，retire 不回溯改寫；但工作台須顯示警示徽章「本工序表使用已下架規則版本 X」

### 3.5 修正既存 bug：V1/V2 分裂的機械成因

`schemas/v2/most.py:12` 的 `DEFAULT_RULE_SET = "MINIMOST_FACTORY_V2"`，但 `catalog_service.py:127` 新建 worksheet 寫死 **V1**、`worksheet_service.py:58` 空 rows 存檔 fallback **V1** → **同一 worksheet 的 default 是 V1、rows schema default 是 V2**。前端同樣不一致（`config.ts` V2、`wi-workbench/api.ts:20` 預設 V1、`RuleSetViewer.tsx:58` 初始 V1）。

**規格**：新增 `get_active_rule_set()/get_active_rule_set_code()`；上述所有寫死處改讀 active；**移除 `schemas/v2/most.py` 的 `DEFAULT_RULE_SET`**（Pydantic 層無 session，不該持有值權威）；前端刪 `ACTIVE_RULE_SET` 常數改用 `GET /api/v2/rule-sets/active` ＋ `useActiveRuleSet()` hook。

Migration 資料遷移：`is_active=true WHERE code='MINIMOST_FACTORY_V2'`；`provenance='certified_import' WHERE code IN (V1,V2)`；**V1 保持 published + inactive**（回放版本，永遠可載入但不再被選中）。

### 3.6 匯出/匯入

- **匯出**：`GET /rule-sets/{code}/export` 回 `load_full()` 形狀 ＋ `{schema_version, exported_at, exported_by}`。**與 `PUT /full` 對稱**，形成 export→離線編輯→import 閉環。**不得**輸出成 `minimost_ai_dictionary_v1.json` 格式——那份 JSON 是**輸入**（方向：JSON → seed → DB），反向產生會製造第二個值權威來源。
- **匯入**：`POST /rule-sets/import` 只吃 export 形狀、**只建 `status=draft, provenance=manual`**。
- **CLI 匯入路徑不得 HTTP 化**：`scripts/import_v3_dictionary.py` 走 git 有三個 v3 沒有的性質——(a) 生成的 seed 進版控、值變更有 diff 可 review；(b) 過 CI Gate 3 黃金測試才能 merge；(c) 未知 option_code 硬中止（`_die()`）確保無靜默降級。做成上傳按鈕＝把值權威交給 runtime。

### 3.7 不移植的 v3 功能

| v3 功能 | 裁決 |
|---|---|
| `archive` 端點 | 無效程式碼（發現 2），v2 用 retire |
| `sequence_models` / `parameter_slots` 表 | v2 序列與格位硬編碼於引擎，是**刻意差異**（引擎權威），不搬 |
| `suggest-code` | P3 或不做。v3 的 `_ZH_TO_CODE` 對 v2 無用（v2 用 `g_grasp` 小寫短碼）；若要做可反轉 `import_v3_dictionary.py` 既有對照表 |
| 泛型 `PUT /options/{id}` | 結構不同構（§2），改每參數端點 |
| `lexical_options` 綁版本 | v2 主數據設計較佳（發現 3） |

## 4. 實施批次（依賴鏈：D1 → D2 → {D3,D4} → D5；D6 獨立）

| 批次 | 內容 | Migration |
|---|---|---|
| **D1** | 後端：`is_active`＋`provenance`＋partial unique index；`activate`/`retire`/`GET active`；publish 加 `validate_complete()`；clone-draft 自動命名；**兩處寫死 V1 改讀 active**；replay isolation 整合測試 | **有**（v2_0020） |
| **D2** | 後端：選項級 CRUD（每參數端點＋P/M 次級 section；A 整組替換）＋`assert_editable` 統一 gate（certified_import/非 draft → 409）；11 張子表加 `is_active` | **有**（v2_0021） |
| **D3** | 後端：export/import draft | 無 |
| **D4** | 前端：統一兩層字典 UI（L1 版本清單＋L2 七參數分頁＋選項 dialog）；clone-on-write；刪 `ACTIVE_RULE_SET` 改 hook | 無 |
| **D5** | 前端：詞彙庫改歸「主數據」；範本庫歸屬待 ADR-021 裁決 | 無 |
| **D6** | 文件/CI：本 ADR、ADR-014 加「後續」段、CI_GATES Gate 5 擴充＋新增「恆有且僅有一個 is_active」 | 無 |

**未涵蓋（獨立小批次）**：`catalog_service.py:125` 的 `version_no = COUNT+1` 併發撞 unique（與字典治理正交，見 guide §5-4）。

## 5. 驗收協定（沿 ADR-021/022）

每批：typecheck/build/e2e 綠 ＋ agent 附 Playwright 截圖 ＋ **協調者親自核圖對照 v3** ＋ code-reviewer 過 → 才 commit。**黃金錨 GM=28/CM=29 與 V1 回放在每批後不得漂移**；D1/D2 需 ddm-validator 席位驗證。
