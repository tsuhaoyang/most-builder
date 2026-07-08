# v3 程式碼查證報告（docs/v3 spec 對照 ddm-v3 實際程式碼）

> **日期**：2026-07-05 ｜ **方法**：直接審 `ddm-v3/apps/api/` 程式碼與測試（**不採信 ddm-v3 的 markdown 文件**），逐條對照 docs/v3 各文件的宣稱；三路平行查證＋人工裁決衝突點。
> **總結**：核心宣稱**大多獲程式碼證實**（含最關鍵的「DB seed＝字典 JSON」）；發現 **12 項需更正/精確化**（C-1~C-12，已回寫至各文件）與 **1 項重大補充**（v3 三層組裝系統）。裁決與設計方向**全部維持不變**，部分文件描述已修正。

## 1. 逐條驗證表（宣稱 → 判定 → 證據）

### 1.1 計算引擎與資料流

| 宣稱（docs/v3 原文意旨） | 判定 | 程式碼證據（ddm-v3/apps/api/） |
|---|---|---|
| workbench 實際計算走 `calculation_v2`（Decimal） | ✅ | `routes/most.py:21-30`、`routes/most_workbench_v3.py:25-32` 均 import calculation_v2 全套；無 live route 用 `calculation.py` 計算函式 |
| A1/A2=max(reach,hand,foot)、A3 只算 reach | ✅ | `calculation_v2.py:71-78` |
| P：≤2 修飾、insert⊥snap、有修飾必有 base、空 P=0 | ✅ | `calculation_v2.py:89-95,129-141`；字典 JSON `max_selected=2, mutually_exclusive` |
| X：fixed/user seconds ÷0.036、ROUND_HALF_UP 3 位、user 秒>0 驗證 | ✅ | `calculation_v2.py:110-119,143-148` |
| repeat：G/P/X/I 整格×、M 僅 verb×再 max、A/B 不支援、≥1 整數、句子 ×N | ✅ | `calculation_v2.py:25-68,98-107,150-159,191-194` |
| SIMO：is_simo 列貢獻 0、總計只加非 SIMO | ✅ | `calculation_v2.py:262-263,286-287`；`routes/most.py:582-586` |
| `simo_with_row_id` 有配對驗證 | ❌ **僅儲存、零驗證**（欄位存在 `models/most.py:51`，無任何檢查） | → impl-02 E5 的驗證是 v2 新增，非 v3 移植 |
| **DB 字典 seed 值＝字典 JSON** | ✅ **逐值抽查全過**（G_GRASP=6、B 10/32/42、I 八檔、X 0.216→6 四項、M 距離 2.5/10/25/45/75、M foot 25/40/55/75/>75、旋轉 D12.5×3+D50×2、A reach 七檔） | `default_dictionary_seed.py:33-170` 直讀 JSON 無轉換 |
| workbench options 讀 DB（非 JSON 檔） | ✅ | `routes/most.py:230-234,1077-1135` 查 DB 四表 |
| 計算快照可稽核（含每 slot 明細） | ✅ | `routes/most.py:415-421`（slot_calculations＋row_result＋句子片段） |
| 字典 Excel 匯入產新版本＋import_warnings | ✅（is_active 切換由另端點負責，匯入預設 False） | `dictionary_import.py:53-108` |
| allowance 為 case 級功能 | ⚠️ **僅半接線**：workbench/MI 層完全沒有 allowance；只在 analysis case 層有欄位並於報表輸出標準秒 | `routes/analysis.py:38,75`、`report_export.py`；`routes/most.py` 無任何 allowance |
| 人工覆寫（manual_index_value）是 v3 功能 | ❌ **非 live 功能**：只存在 `calculation.py` dataclass 與測試，無任何 route 接受 | `routes/most*.py` schema 皆無此欄位 |

### 1.2 NL 解析與句子生成

| 宣稱 | 判定 | 證據 |
|---|---|---|
| 先命中先贏、僅 M 最長匹配 | ✅（B/G/P/X/I 均 first-hit；M `sorted(key=len, reverse=True)`） | `nl_draft_parser.py:388-405,477-536,610-680,698` |
| G 遮蔽：G_SELECT_SMALL 不可達 | ✅（機制精確化：**first-hit＋子字串命中**——「拿取小」永遠先被「拿取」吃掉，與表序無關；無測試覆蓋此案例） | `nl_draft_parser.py:141-152,477-494` |
| parser 零正規化 | ✅（且補充：`normalization.py` **已實裝** NFKC/OpenCC，接線於 `dictionary_import.py:162,201`；但 parser 與 nl-draft route 均未呼叫；default seed 的 normalized_text 直接 copy display_text 未經 normalize） | `nl_draft_parser.py:1010-1019`、`normalization.py:12-16,131-189` |
| context 黑名單 regex、語序敏感 | ✅ | `nl_draft_parser.py:342-371` |
| 信心反置（default 1.0 > inferred） | ✅（實測全表：inferred 0.75–0.9、default 1.0，賦值點 13 處） | `nl_draft_parser.py:401-953` 各賦值點 |
| DB 同義詞優先＋publish 失效快取 | ✅ | `nl_draft_parser.py:80-135,283-289`、`dictionaries.py:834,865` |
| 治具防護（負先行斷言）＋測試 | ✅ | `nl_draft_parser.py:185-194,621-631`、`test_nl_draft_parser.py:19-107` |
| 一句多動作無分段 | ✅（同句可偵測多 slot，但不拆多列） | `nl_draft_parser.py:417-466` |
| P 句子規則（插入/卡合取代、對準前綴、hidden） | ✅（hidden 以「省略不組入」實現，無顯式分支——行為正確） | `calculation_v2.py:198-230` |
| nl-draft 輸出含 needs_review | ⚠️ v3 無此欄位，用 `warnings`＋`missing_fields` 表達 | `routes/most.py:279-287`、`nl_draft_parser.py:40-57` |

### 1.3 組裝系統／工作流／匯出

| 宣稱 | 判定 | 證據 |
|---|---|---|
| WI Pool：ILIKE %kw% 搜句子/名稱（含子序列） | ✅（無分頁，直接 `.all()`） | `wi_set_builder.py:184-214` |
| 加入專案＝快照複製＋provenance | ✅（`wi_*_snapshot` 五欄＋`wi_snapshot_json`；source 刪除不影響快照） | `wi_set_builder.py:366-460` |
| 專案總計排除 SIMO | ❌ **v3 bug**：`_recalculate_project_totals` 直接加總快照、未排 SIMO——與 `calculate_analysis_total` 不一致，WI Set 總計可能高估 | `wi_set_builder.py:171-178` vs `calculation_v2.py:279-297` |
| MI Statement 快照延遲建立（backfill）＋is_modified_from_source | ✅ | `routes/most.py:919-967,784-808` |
| ActionModuleTemplate 是 dead model | ❌ **完整 live 功能**（CRUD＋clone＋reorder） | `most_workbench_v3.py:320-544` |
| 工作流五態＋changes_requested、非法遷移擋 400 | ✅（末態 v3 命名 **archived**） | `routes/analysis.py:85-91,429-434` |
| 五角色 seed＋端點 guard | ✅（admin/analyst/reviewer/approver/viewer；`require_roles` Depends） | `db/init_db.py:15-21`、`dependencies.py:34-50` |
| audit 每次遷移落一筆 | ✅ | `routes/analysis.py:448-456`、`models/audit.py:20-32` |
| 報表：openpyxl 三 sheet、含每列 slot 明細與標準秒 | ✅ | `report_export.py:1-140` |
| 前端無自算 TMU | ✅（全走後端 API） | `SlotModal.vue`、`WIPoolSearch.vue`、`api/most.ts` |
| 無 LB 整合痕跡（獨立 JWT） | ✅ | `core/security.py:1-31`、`models/user.py:41-58` |

## 2. 重大補充發現（原文件未涵蓋）

### 2.1 v3 有兩代組裝系統並存，新一代是三層

`most_workbench_v3.py`（1118 行）是完整的三層 live 系統，與舊一代（MostMiStatement＋`wi_set_builder.py` 的 WISetProject）**平行並存**：

| v3 三層 | 模型 | 端點 | 對應 v2 設計（ADR-017） |
|---|---|---|---|
| **L1 Action Modules（動作模組池）** | `ActionModuleTemplate` | CRUD＋clone＋reorder（`most_workbench_v3.py:320-544`） | `motion_modules`（rows 長度 1） |
| **L2 WI Templates（WI 範本池）** | `WITemplate`＋`WITemplateItem` | CRUD＋items＋clone＋reorder（:551-830） | `motion_modules`（rows 長度 n）——**我方合併設計天然覆蓋 L1+L2** |
| **L3 Process Routes（製程途程）** | `ProcessRoute`＋`ProcessRouteItem` | 建立即快照 WI 範本、clone、reorder（:838-1050） | `ProcessVersion`＋worksheet（既有） |

**apply-back**（`:1054-1117`）：L3 流程項目可**顯式**回寫來源 WI 範本（owner/admin 限定、整組覆寫、含 totals）——證實 v3 的同步哲學是「快照不自動同步＋顯式回寫」。v2 對應：組件版本不可變 → apply-back＝**「從工序表列發布組件新版本」**（已補進 impl-04 §3）。

**架構意涵**：兩代並存＝概念重複（MiStatement/WISetProject vs WITemplate/ProcessRoute），再加上四處計算/合計路徑（見 2.2），**強化 ADR-017 的合併決策與單一引擎原則**。

### 2.2 v3 實際有四處計算/合計邏輯（反漂移論點的實證）

1. `calculation_v2.py` — live workbench（正確、Decimal）。
2. `calculation.py` — 幾乎 orphan（僅被借用常數；含未接線的 allowance/manual override）。
3. `routes/analysis.py:213-216,274-279,333-336` — **inline 手算**（`sum(index)×freq×0.036`），第三套。
4. `wi_set_builder.py:171-178` — 快照加總（**漏排 SIMO 的 bug**），第四套。

→ v2 整合時**只允許 most_engine 一套**（含 worksheet/module 合計），此清單作為反例教材附於 ADR-014。

### 2.3 其他

- `most_workbench.py` service 是 orphan module（無 route 引用）——先前文件把它當 workbench service 的描述已更正。
- 句子組裝分工：`calculation_v2.generate_slot_sentence`（slot 片段）＋ `routes/most.py:139-211 _compose_full_sentence`（整句，含 `show_hand_in_sentence`）；`sentence_generation.py` 提供模板。

## 3. 更正清單（C-1~C-12，2026-07-05；C-13~C-17，2026-07-08）

| # | 更正 | 回寫位置 |
|---|---|---|
| C-1 | most_workbench.py 為 orphan；live 計算在 routes 層 | 本報告 §2.3；差異盤點檔案對照表 |
| C-2 | v3 有四處計算路徑（非兩套引擎） | 本報告 §2.2；ADR-014 反例 |
| C-3 | allowance 僅 analysis case 層半接線，workbench 層無 | 差異盤點 §4.2 註記 |
| C-4 | 人工覆寫非 v3 live 功能——E7 是「採納 v3 規格構想」非移植 | impl-02 E7、blueprint F7 |
| C-5 | v3 三層組裝系統＋apply-back（重大補充） | 本報告 §2.1；impl-04 §3；blueprint §5 |
| C-6 | normalization 已接線於 dictionary_import；parser/seed 未用 | impl-05 §1 註記 |
| C-7 | G 遮蔽機制＝first-hit＋子字串（非表序問題） | impl-05 §6.3 表 |
| C-8 | nl-draft 無 needs_review（warnings/missing_fields）；confidence 實測值 | impl-05 §3 註記 |
| C-9 | simo_with_row_id 僅儲存無驗證 | impl-02 E5 註記 |
| C-10 | v3 工作流末態命名 archived（v2 用 retired，對映之） | impl-06 §1 |
| C-11 | P hidden 修飾以省略實現（行為正確） | 無需改（impl-02 E6 設計相同） |
| C-12 | WI Set 專案總計漏排 SIMO 為 v3 bug（不移植） | impl-04 §2 不變量佐證 |
| **C-13** | **WILibrary endpoint 只查 MiStatement，不含 WITemplate**：`wi_set_builder.py list_wi_library()` 僅 `db.query(MostMiStatement)`；F-04 舊文描述曖昧 | F-04 §1 補充；F-03b §5 |
| **C-14** | **ProcessRoute AddWI 有 bug（每次加 WI 都 createProcessRoute）**：`ProcessWorkspace.vue L79-86` 在 for 迴圈內每次呼叫 `createProcessRoute`，產生孤兒資料；v2 改為增量 API（`POST /items`） | F-03b §4 |
| **C-15** | **WISetProjectItem.source_wi_id 實存 MiStatement.id，非 WITemplate.id**：model 注釋說「Reference back to WITemplate」，但 `AddItemsRequest` 注釋明確寫 "MostMiStatement IDs from old MOST workbench"；v3 DB 實際資料亦確認（13 筆 MiStatement ID） | F-04 §1 補充 |
| **C-16** | **IE 生產 DB 實況確認一代主導**：minimost.db 中 13 筆 MiStatement＝真實伺服器組裝工序；WITemplate 2 筆（「取dimm」「123」）、ProcessRoute 1 筆（「工作中流程」）均為測試實驗資料；三層架構 IE 尚未正式採用 | 本報告 §2.4（新增）；F-04 §1 補充 |
| **C-17** | **前端 WILibraryItem.source 為死欄位**：TypeScript `WILibraryItem` 有 `source: string`，但後端 `WILibraryItemResponse` 無此欄，從未回傳；真正的 `source` 欄位在 `ActionModuleTemplate`（manual/ai/copied）；v2 型別定義需清理 | F-03b §5 |

## 4. 對裁決與設計的影響評估

- **裁決不變**：值權威（seed=JSON 已證實）、SIMO（引擎 max）、檢索方向、組件庫合併——查證結果全部支持或強化。
- **設計微調（已回寫）**：impl-04 增「apply-back＝發布新版」API；impl-02 E7 改列「規格採納」；impl-05 明確「v3 正規化僅在匯入路徑生效，v2 須全路徑接線」。
- **2026-07-08 新增**：C-13~C-17 五項補充查證——WILibrary 範圍確認、AddWI bug 修正規格、source_wi_id 真實語意、IE DB 實況、死欄位清單；詳見 [F-03b](features/F-03b-snapshot-design-and-apply-back-spec.md)。
- **新增待確認**（併入殘項清單）：IE 是否需要 L2/L3 分層的顯式對應（v2 以「多列 module＋worksheet」覆蓋 L1+L2+L3，分層 UI 是否足夠由前端工作流驗證）。

## 5. IE 生產 DB 實況（2026-07-08 新增查證，C-16）

直接查 `ddm-v3/apps/api/minimost.db`：

| 資料表 | 筆數 | 內容性質 |
| --- | --- | --- |
| `most_mi_statements` | 13 | ✅ 真實生產資料（SQT 廠伺服器組裝工序：DIMM 安裝、主板處理等；總工時最大 TMU=616） |
| `wi_set_projects` | 1 | ✅ 真實（SQT-BU6-L10_ASSY-K860G6-K860G6；含全部 13 筆 MiStatement） |
| `wi_set_project_items` | 13 | ✅ 真實（對應 13 筆 MiStatement） |
| `wi_templates` | 2 | ⚠️ 測試（「取dimm」「123」——明顯非生產命名） |
| `process_routes` | 1 | ⚠️ 測試（「工作中流程」） |
| `action_module_templates` | 3 | ⚠️ 測試（2 manual + 1 copied；DIMM 相關實驗） |
| `analysis_cases` | 0 | — 未使用 |
| `workflow_audit_logs` | 0 | — 未使用 |

**結論**：IE 在 v3 的真實工作流程是**一代路徑**（Sequence → MiStatement → WISetProject）；三層架構（ActionModule → WITemplate → ProcessRoute）在 IE 尚未落地採用。v2 移植方向（以三層為 canonical、提供從 MiStatement 升格的路徑）是正確的，但需要評估升格 UX 的設計優先度。
