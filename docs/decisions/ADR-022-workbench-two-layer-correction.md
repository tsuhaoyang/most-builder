# ADR-022：工作台兩層模型修正 — 動作/WI 分層、WI 大綱、教學型格位介面

- **狀態**：Accepted（使用者/IE 裁決於 2026-07-14）
- **決策者**：Howard（IE）＋ 審查總召
- **關聯**：修正 ADR-021 的一處核心誤讀；ADR-014（值權威）、ADR-020（SIMO）
- **本文件是修正批次 A~E 所有派工的必讀母版。**

## 背景：ADR-021 哪裡讀錯了

ADR-021 把 v2 的「MOST 工作台」定義為三層組裝工作台（來自 v3 的 `/most-workbench-v3`）。經使用者指正與程式碼查證：

1. **v3 導覽的「MOST 工作台」是單頁版 `/most-workbench`**（`AppLayout.vue:13`）；三層版**不在 v3 導覽**，是實驗性隱藏頁，非驗證過的 UX。
2. **v3 的 WI 庫 = MI statements（WI 大綱）**：`wi_set_builder.py:184-190` 註解明示 "List old MOST workbench MI Statements (WI 大綱) as the WI Pool source"。
3. v3 正確工作流：**MOST 工作台建動作（sequence）→ 勾選群組成 WI 大綱（1 筆 MI statement = 1 筆 WI）→ WI 專案建立從 WI 大綱清單選入專案 → Calculation Summary → Create Project = 一份真實 Work Instruction**。

由此產生的 v2 缺口（使用者驗收發現）：
- 動作與 WI 沒分層：動作清單列的是「模組」（1 模組可含 5 動作只顯示合計）
- WI 大綱區塊不存在；「WI 組成工作區」「製程途程工作區」兩個多餘 tab（實驗頁殘留）
- WI 專案建立的庫混入單動作模組/範本（v3 是純 WI 級 13 筆）
- 版本 rows 未存每列計算結果 → 展開子表無每列 TMU
- 多動作 WI 編輯只載 rows[0]
- **WiItemInspector 缺失**（v3：點 WI 大綱群組內 row → 右側抽屜內嵌完整 SequenceSlotBuilder，可檢視微調，後端重算寫回，「已微調」badge）
- **教學型格位介面缺失**（v3 A 格 modal：工位伸手範圍圖 SVG 俯視互動選值＋距離對照表 ≤2.5→0/≤5→1/…/>60→24 TMU＋實際距離 cm 輸入＋計算方式說明；v2 只有三個純下拉）

## 決策：目標模型

### 資料模型（重用 motion_modules，不開新表）

| 概念 | v2 實作 | 對應 v3 |
|---|---|---|
| **動作**（工作素材） | `motion_module`，`category='action'`，恰 1 row | most_sequence_items |
| **WI**（WI 大綱項） | `motion_module`，`category='wi-template'`，rows = 動作的**快照複本**（copy-on-write，微調不影響來源動作） | most_mi_statements + items |
| WI 專案 | `wi_set_projects`（不變），items 引用 category='wi-template' | wi_set_projects |

**版本 rows 必須持久化每列計算結果**（publish 時引擎已算，寫進 rows JSON：`computed: {total_tmu, total_seconds, eff_tmu, contribution_tmu}`）——展開子表、Inspector、對帳都吃這裡，前端永不自算。

### 「MOST 工作台」回歸 v3 單頁（無 tab）

由上而下：AI 快速建模列 → 摘要列 → 交錯句型（既有）→ **動作清單（列個別動作，各自 TMU，✏️📋✕）** → **WI 大綱區**（勾動作→建 WI；WI 列表可展開/改名/調序/刪除；「已微調」badge）→ 點 WI 內 row 開 **WiItemInspector 右抽屜**（內嵌 SlotBuilder，row 級編輯→後端重算→新版本）。

### 兩個多餘 tab 的去向

- 「WI 組成工作區」→ **移除**（WI 大綱取代）
- 「製程途程工作區」→ 其「WI 實體化進工時表」能力**搬入分析案件的工時表編輯情境**（WiWorkbench 工具列「從 WI 庫插入」），之後 tab 移除。apply-back（套用回模板）隨遷。

### WI 專案建立

庫只列 `category='wi-template'`；展開子表補每列 Base TMU/頻率/Eff TMU/SIMO（吃 rows.computed）。

### WI 專案 → 分析案件（2026-08-04 補充裁決）

`wi_set_projects` 是排序後的 WI 範本集合，`process_versions + most_worksheets` 才是
Level System、WI 預覽與匯出的分析案件資料來源。兩者不得靠名稱或 `site/model` 文字欄位
隱式配對；WI 專案目前沒有 `sku_id`，儲存專案也不得偷偷在任意 SKU 下建立空案件。

採以下顯式轉換契約：

1. WI 專案儲存後提供「建立分析案件」，使用者必須選擇 Product / SKU，機種/線別名稱預填
	專案 `model → process → name`，仍可修改。
2. `POST /api/v2/wi-set-projects/{project_id}/instantiate` 在單一 transaction 內建立 worksheet，
	再依 `wi_set_items.seq_no` 呼叫既有 `motion_module_service.instantiate_to_worksheet()`；每列仍由
	worksheet 的 rule-set 與 `most_engine` 重算，前端不組 rows、不計 TMU。
3. 空專案、手動條目、缺失/未發布/退役 WI 或非法 vocab UUID / SIMO 均整筆失敗並 rollback，
	不得在分析案件留下空殼或部分匯入結果。`object_vocab_id` 是敘述 metadata，不是
	`most_engine` 計算輸入；合法 WI row 可不含 object（`v2_0025` 改為 nullable），不得因此跳列，
	也不得由前端偷填第一個 object 當假預設。
4. 成功後前端 invalidate `cases` / `sku-worksheets` / `worksheet`，設定同一個 `activeWs` 並切到
	分析案件；案件詳情的 WI 預覽與 Level System 都直接讀該 worksheet rows。
5. Level System 必須依 `activeWs` 自行載入並 hydrate worksheet，不能依賴使用者曾先開過
	WiWorkbench 的記憶體副作用。

### 教學型格位介面（全域共用，工作台/Inspector/案件編輯同套）

- A 格 modal：移植 ADistanceSelector（SVG 工位伸手範圍圖，點圖選檔）＋距離對照表＋實際距離 cm 輸入＋手度/腳步
- 各格 modal 底部補計算方式說明（文案照 v3）

## 實施批次（依賴順序）

| 批次 | 內容 | 席位 |
|---|---|---|
| A | 後端：rows 計算結果持久化（publish 豐富化）＋row 級編輯/調序/刪除端點（重算發新版）＋category 規範＋搬遷資料重掛（29 動作以 category='action' 補搬；17 筆 WI 重發佈豐富化 rows） | ddm-backend → ddm-validator |
| B | 工作台單頁化：移除三 tab、動作清單改 category='action'、WI 大綱區、WiItemInspector 抽屜 | ddm-frontend |
| C | 教學型格位介面：ADistanceSelector 移植＋對照表＋計算方式說明（改 SlotBuilder 內部） | ddm-frontend |
| D | WI 專案建立：庫過濾＋展開子表計算欄 | ddm-frontend（可與 C 並行，檔案不重疊） |
| E | 案件編輯情境「從 WI 庫插入」（實體化搬家）→ 移除製程途程 tab | ddm-frontend＋ddm-backend |

## 驗收協定（沿 ADR-021，每批硬性）

typecheck/build/e2e 綠＋agent 附 Playwright 截圖＋**協調者親自 Playwright 核圖對照 v3**＋code-reviewer 過 → 才 commit。黃金錨（GM=28/CM=29）與搬遷對帳值（88/154.333/616/3739.666…）在每批後不得漂移。
