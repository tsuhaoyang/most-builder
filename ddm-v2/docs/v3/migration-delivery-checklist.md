# v3 → v2 移植交付驗收清單

> **文件性質**：本清單為 v3（使用者親自設計開發）核心功能移植至 v2 的正式驗收依據。  
> **效力**：任何移植工項未達本清單驗收標準，不得視為完成交付。  
> **維護人**：產品負責人（使用者）簽核；技術更動需重新確認受影響的驗收條件。  
> **來源**：[UX-design-spec.md](analysis/UX-design-spec.md)、[F-01~F-08](analysis/features/)、[CL-01~CL-04](analysis/core-logic/)、v3 Vue 原始碼。

---

## 文件使用說明

| 欄位 | 說明 |
|---|---|
| `[ ]` | 未完成 |
| `[x]` | 已完成並通過驗收 |
| `[~]` | 部分完成／待補 |
| **驗收標準** | 全部條件符合，方可勾選完成 |
| **拒絕條件** | 任一成立即退回，不得勾選 |
| 來源 | 規格文件引用，有疑義以來源為準 |

---

## A｜全域殼層與導覽

### A-01 可折疊 Sidebar 導覽

- **來源**：UX-design-spec §1
- **交付物**：全站左側 Sidebar 元件，替換現有水平 Tab bar

**驗收標準：**
1. 展開寬度 200px，折疊寬度 56px，切換動畫 ≤ 0.3s
2. 折疊時導覽項目顯示短標字（不得消失或變成圖示）：表/M/W/L/案/典/人
3. Mobile（≤768px）：Sidebar 轉 `position: fixed`，折疊後完全隱藏（0px），不佔主內容空間
4. 切換後狀態持久化（頁面重整不重置）

**拒絕條件：**
- × 折疊時 Sidebar 完全消失，沒有 56px 收合狀態
- × 展開/折疊無動畫（突然跳動）
- × Mobile 下 Sidebar 壓縮主內容區域

---

### A-02 角色可見導覽項目

- **來源**：UX-design-spec §1.2；F-08 §1
- **交付物**：Sidebar 依登入角色動態顯示項目

**驗收標準：**
1. `viewer/analyst/reviewer/approver` 角色可見：儀表板、MOST 工作台、WI 專案建立、Level System、分析案件（共 5 項）
2. `admin` 額外可見：字典管理、使用者管理（共 7 項）
3. 導覽項目的可見性由後端 `/api/v2/me` 的 `roles` 決定，前端不硬編碼

**拒絕條件：**
- × 非 admin 可看到字典管理或使用者管理入口
- × 角色判斷在前端寫死，不依 API 回傳

---

### A-03 全域視覺 Token

- **來源**：UX-design-spec §1.3
- **交付物**：CSS 變數或 Tailwind token 設定檔

**驗收標準：**
1. TMU 數值全站統一使用藍色粗體（`#1a73e8` 或等效品牌色，需有 token 命名）
2. 編輯中的列：暖黃底色（`#fdf6ec` 或等效）
3. 已選取的列：淺藍底色（`#eff6ff` 或等效）
4. Sidebar 底色：深藍灰（`#304156` 或等效）
5. 頁面底色：`#f5f7fa` 或等效淺灰
6. 所有 token 定義在單一設定檔，不得在元件內散落 hard-coded 色碼

**拒絕條件：**
- × 各頁 TMU 顏色不一致
- × 找不到 token 集中定義

---

## B｜MOST 工作台

### B-01 單欄三區佈局

- **來源**：UX-design-spec §2.1；F-01 §1
- **交付物**：MostWorkbenchPage 佈局

**驗收標準：**
1. 頁面為**垂直單欄**，三個區塊由上至下：序列編輯器（flex-shrink: 0）→ 動作清單（flex: 1）→ WI 大綱（conditional）
2. 頁面高度鎖定 `calc(100vh - [header高度])`，主體 overflow-y: auto
3. WI 大綱區塊最大高度 42vh，超過時內部滾動，不撐高頁面
4. SlotModal 和 WiItemInspector 以 overlay 形式呈現（不改變三區佈局）

**拒絕條件：**
- × 改成三欄並排佈局
- × WI 大綱展開後壓縮動作清單，使動作清單第 8 列以後不可見

---

### B-02 NL 草稿輸入（NlDraftInput）

- **來源**：F-05；UX-design-spec §2.2
- **交付物**：工作台 Section 1 頂部全寬 NL 輸入區

**驗收標準：**
1. 輸入框位於序列編輯器頂部，寬度 100%
2. 提交後顯示 AI 建議：模型建議 + 整體信心 + 各格建議（option + 信心 + badge）
3. 編輯區已有內容時，必須詢問「覆蓋全部」或「只填空白」，不得靜默覆蓋
4. AI badge 三態顯示正確：明確（綠）、推斷（橘/黃）、待確認（紅）
5. 任何 NL 建議套用後，不直接寫入資料庫，仍須使用者走完 F-01 試算 → 儲存流程
6. Given「雙手抓握主板放到DIMM壓合治具」→ 建議 GM 且 G 有抓握建議
7. Given「推壓合治具內主板並壓合機台10秒」→ 建議 CM 且 X 含秒數 10

**拒絕條件：**
- × NL 建議直接寫入 DB（未經使用者確認）
- × badge 信心順序反置（default 信心 ≥ inferred）
- × 覆蓋已有內容前未詢問

---

### B-03 Slot Strip（水平格位列）

- **來源**：UX-design-spec §2.3；F-01 §1
- **交付物**：SequenceSlotBuilder 元件

**驗收標準：**
1. GM 完整欄位順序：使用手 | 從哪裡 | A1 | B1 | G | 目標物 | 元件 | A2 | B2 | P | 到哪裡 | A3
2. CM 完整欄位順序：使用手 | 從哪裡 | A1 | B1 | G | 目標物 | 元件 | M | 到哪裡 | X | I | 哪裡 | A3
3. 「使用手」context block 顯示紫底（與其他 context 塊有視覺區別）；「使用手」含「顯示於MI」checkbox
4. 其他 context block 顯示暖黃底
5. 有 AI 建議時，slot block 下方顯示 badge（三色），無建議時無 badge
6. 點擊任一 slot block → 開啟對應 SlotModal
7. 任何 context 欄位變更 → 400ms debounce 後自動 call preview API

**拒絕條件：**
- × GM 與 CM 欄位順序與規格不符
- × AI badge 靜默填入值（未顯示 badge 標示）
- × context 變更後不觸發 preview

---

### B-04 模型切換遷移規則

- **來源**：UX-design-spec §2.2；F-01 §1 行為規則 3
- **交付物**：模型選擇器切換邏輯

**驗收標準：**
1. GM → CM：清空 P/A2/B2，保留 A1/B1/G/A3 及全部 context 欄位
2. CM → GM：清空 M/X/I，保留 A1/B1/G/A3 及全部 context 欄位
3. NL 草稿填入時使用 suppressModelChangeReset 機制，AI prefill 的模型切換不觸發清空
4. 切換後立即觸發 preview 重算

**拒絕條件：**
- × 模型切換清空所有格（包含 A1/B1/G/A3）
- × AI 草稿建議切換模型時觸發清空，導致 AI 填入的值被清除

---

### B-05 SlotModal — A 格（reach distance）

- **來源**：UX-design-spec §3；F-01 §1
- **交付物**：A 格對話框

**驗收標準：**
1. Modal 寬度 820px（A 格專屬；其他格 520px）
2. 包含：ADistanceSelector（視覺距離選擇器）+ 手轉角度（A1/A2 才顯示，A3 不顯示）+ 腳步（同規則）
3. 公式說明顯示：A1/A2 = 「取最大值 max(距離, 手轉角度, 腳步)」；A3 = 「僅依距離計算」
4. 有現有選擇時，Footer 左側顯示「清除此欄位」（danger 樣式）
5. 公式說明卡片永遠顯示在 modal 內容區（有 left-border 視覺強調）

**拒絕條件：**
- × A 格 modal 寬度與其他格相同（失去 ADistanceSelector 空間）
- × A3 顯示了手轉角度或腳步欄位

---

### B-06 SlotModal — B 格（body motion）

- **來源**：UX-design-spec §3.2；F-01
- **交付物**：B 格對話框

**驗收標準：**
1. 只有一個下拉選單
2. 使用者選擇後**自動確認並關閉**，不顯示確認/取消按鈕
3. 選擇後立即觸發 preview 重算

**拒絕條件：**
- × B 格需要按確認鈕才能關閉

---

### B-07 SlotModal — P 格（place）

- **來源**：UX-design-spec §3.2；F-01 §1；CL-01
- **交付物**：P 格對話框

**驗收標準：**
1. 包含「基礎動作」下拉 + 「附加條件」tag 選擇器
2. 附加條件最多可選 2 項（UI 即時強制，第 3 項不可點擊或自動取消最舊的）
3. `insert`（插入）與 `snap`（卡合）互斥：選一個後另一個變為不可選
4. 公式說明：「基礎 + Σ(附加條件)」顯示於 modal 內
5. 後端仍重驗 ≤2 和互斥規則（422 回應）

**拒絕條件：**
- × 可同時選超過 2 個附加條件
- × insert 與 snap 可同時選取

---

### B-08 SlotModal — M 格（controlled move）

- **來源**：UX-design-spec §3.2；F-01
- **交付物**：M 格對話框

**驗收標準：**
1. 三組控制欄：動作動詞（verb）、手轉角度（hand_degree）、腳步（foot_step）
2. 每組各有 label + 可搜尋下拉 + 該格 TMU 顯示
3. 公式說明：「計算方式：取最大值 max(動作, 手轉角度, 腳步)」

**拒絕條件：**
- × 三組顯示為單一下拉

---

### B-09 SlotModal — X 格（process time）

- **來源**：UX-design-spec §3.2；CL-01
- **交付物**：X 格對話框

**驗收標準：**
1. 時間類型下拉選單
2. 當 `seconds_source === 'user_input_seconds'` 時，顯示秒數輸入框（其他選項時隱藏）
3. 公式說明：「秒數 ÷ 0.036 = TMU」
4. 儲存時秒數 > 0 驗證；後端 422 含明確欄位名稱

**拒絕條件：**
- × 不管時間類型，秒數輸入框永遠顯示
- × X 格選壓合機台未填秒數時，儲存不報錯

---

### B-10 Repeat Count（重複次數）

- **來源**：UX-design-spec §3.3；CL-01 §repeat
- **交付物**：各格 SlotModal 內的 repeat count 區塊

**驗收標準：**
1. G/P/M/X/I 格的 SlotModal 顯示 repeat count 輸入（min=1）
2. A/B 格**不顯示** repeat count
3. repeat > 1 時，slot block 上顯示紫色 `×N` badge（`#9c27b0` 或等效）
4. repeat count 與列級 frequency 獨立：兩者可並存，各自影響不同層級的計算
5. 說明文字：「此動作重複次數（不影響其他欄位）」

**拒絕條件：**
- × B 格或 A 格出現 repeat count
- × repeat count 影響到其他欄位的值

---

### B-11 按鈕狀態與 WI 名稱規則

- **來源**：UX-design-spec §2.2
- **交付物**：工作台 Footer 區域

**驗收標準：**
1. 新建模式顯示「新增動作」（綠色）
2. 編輯現有列時顯示「更新動作」（橘色/warning）+ 「取消編輯」
3. 第一條已儲存句子自動填入 WI 名稱欄位
4. 使用者手動修改 WI 名稱後（`wiNameTouched = true`），不再自動覆蓋
5. 「清空」按鈕重置所有格位至預設值

**拒絕條件：**
- × 新建與編輯模式按鈕標籤相同
- × 使用者已手動輸入 WI 名稱，存入新動作後被自動覆蓋

---

### B-12 句子雙欄與人工句保護

- **來源**：F-01 §1 行為規則 4；CL-02；UX-design-spec §8 規則 2
- **交付物**：動作描述欄位與重算邏輯

**驗收標準：**
1. 每列顯示系統句（後端組）與人工句（使用者輸入）雙欄
2. `user_edited` 句存在時，重算後系統句更新，**人工句不被覆蓋**
3. 人工句欄位為可編輯輸入框，系統句欄為唯讀（或折疊顯示）
4. 匯出報表使用人工句（若有），否則用系統句

**拒絕條件：**
- × 重算後人工句被系統句蓋掉
- × 前端自行組句（句子必須來自後端 API 回應）

---

## C｜動作清單（MiCompositionTable）

### C-01 12 欄表格結構

- **來源**：UX-design-spec §2.4
- **交付物**：MiCompositionTable 元件

**驗收標準：**
1. 欄位順序正確（左至右）：拖曳把手 | 勾選 | 序號 | 手 | 動作描述 | Base TMU | 頻率 | Eff TMU | CT(秒) | SIMO | 納入 TMU | 操作
2. Eff TMU 欄使用藍色粗體（token: `tmu-value`）
3. 頻率欄為 inline 數字輸入（不需打開 modal 才能改）
4. 操作欄固定於右側，包含：✏️ 編輯 / 📋 複製 / ✕ 刪除（刪除為紅色/danger）
5. 動作描述欄最小寬度 200px，多餘文字截斷（2-line clamp）

**拒絕條件：**
- × Eff TMU 不是藍色
- × 頻率需開啟 modal 才能修改

---

### C-02 SIMO 顯示規則

- **來源**：CL-04 §2；UX-design-spec §8 規則 7
- **交付物**：SIMO 相關欄位視覺呈現

**驗收標準：**
1. SIMO 開啟的列，「納入 TMU」欄顯示刪除線 + 灰色（表示被 group-max 覆蓋）
2. Given 兩列配對 SIMO（TMU 29 與 28）：合計取 29，交換標記方向後合計不變
3. 合計列顯示正確（SIMO 組只計最大值，非 SIMO 列累加）

**拒絕條件：**
- × SIMO 開啟時，兩列 TMU 都被計入合計（應取 max 而非 sum）
- × 納入 TMU 欄沒有刪除線視覺提示

---

### C-03 拖曳排序 UX

- **來源**：UX-design-spec §2.4
- **交付物**：列拖曳功能

**驗收標準：**
1. 拖曳把手（⋮⋮）cursor 為 grab；拖曳中為 grabbing
2. 拖曳中的列：淺藍底色（`#e0f2fe`）+ 2px 藍色 outline + 陰影
3. 放置目標上半：3px 藍色 top border（表示插入目標上方）
4. 放置目標下半：3px 藍色 bottom border（表示插入目標下方）
5. 完成拖曳後立即更新列順序，不需重新整理頁面
6. 拖曳樂觀更新：本地先更新，再送後端；失敗時顯示 error toast

**拒絕條件：**
- × 拖曳中無視覺反饋（游標、背景色、邊框）
- × 放置後頁面重整才看到新順序

---

### C-04 ResizeObserver 高度計算

- **來源**：UX-design-spec §2.4
- **交付物**：表格高度動態計算

**驗收標準：**
1. 動作清單表格高度由 `ResizeObserver` 動態計算（fallback: 360px）
2. 視窗縮放後，表格高度自動調整，不需重整頁面
3. WI 大綱展開後，動作清單仍可看到至少前 8 列（不被擠出視口）

**拒絕條件：**
- × 表格高度寫死像素值
- × WI 大綱展開後，動作清單被完全擠出視口

---

## D｜WI 大綱（WiOutline）

### D-01 條件顯示與高度限制

- **來源**：UX-design-spec §2.5；F-01
- **交付物**：WiOutline 面板

**驗收標準：**
1. 沒有任何已儲存的 WI 時，WI 大綱區塊**完全不渲染**（不顯示空白卡片）
2. 有 WI 時顯示，最大高度 42vh，超過時內部獨立滾動
3. 標題列顯示 WI 項目數量
4. 點擊 WI 項目 → WiItemInspector 抽屜（drawer）從右側滑入

**拒絕條件：**
- × 無 WI 時仍顯示空白大綱區塊（佔用頁面空間）
- × WI 大綱撐高整個頁面（而非內部滾動）

---

### D-02 工具列選取資訊

- **來源**：UX-design-spec §2.5
- **交付物**：動作清單工具列切換邏輯

**驗收標準：**
1. 無選取列：工具列右側顯示合計資訊（WI 數 / 動作數 / TMU / 秒）
2. 有選取列：工具列右側切換為「已選 N 筆 · Eff TMU · CT 秒」+ WI 名稱輸入框 + 「加入 WI」按鈕
3. 取消所有選取後，工具列切回合計資訊

**拒絕條件：**
- × 有選取時仍顯示全部合計（而非選取資訊）

---

## E｜WI Pool 與 WI 專案

### E-01 WI Pool 面板（Block E）

- **來源**：UX-design-spec §4；F-03；F-04
- **交付物**：WIPool 元件

**驗收標準：**
1. 卡片式佈局：灰色 Header（標題 + 計數）→ Toolbar（搜尋 + 選取操作）→ 卡片清單（max-height: 300px，可滾動）
2. WI 卡片可展開/折疊：折疊顯示 checkbox + 箭頭 + code + name + stats chip（N模組·TMU·秒）
3. 展開後：子項縮排 36px，各項顯示 GM/CM tag + 句子（2-line clamp）+ TMU
4. 選取狀態：卡片邊框變藍（`#409eff`），背景 `#ecf5ff`
5. 無 WI 時顯示提示文字「尚無 WI 模板，請先組合動作模組並儲存」
6. 搜尋框可即時過濾（含 WI name、句子內容）

**拒絕條件：**
- × WI Pool 清單無展開/折疊功能
- × 選取視覺反饋不存在

---

### E-02 WI 專案建立頁面（WISetBuilderPage）

- **來源**：UX-design-spec §5；F-04
- **交付物**：WISetBuilderPage 頁面

**驗收標準：**
1. 頁面 max-width: 1200px，水平置中
2. 頁面頂部：「WI Set Builder / WI 專案建立」標題 + 專案選擇器（載入現有專案）+ 「New Project」按鈕
3. Section A（ProjectMetadataForm）必填欄位：專案名稱、site、BU、process、family、model
4. Section B（WIPoolSearch）：選取 WI 後點「加入專案」→ 選取清空，**搜尋結果保留**
5. Section C（SelectedWISetTable）：支援 drag-and-drop 排序與上下箭頭排序（兩者結果一致）
6. Section D（摘要統計）：顯示 WI 數 / 動作數 / 總 TMU / 總秒數
7. Section E（操作按鈕）：儲存/建立（情境按鈕）、複製（儲存後才啟用）、刪除（儲存後才啟用）

**拒絕條件：**
- × 加入 WI 後搜尋結果也被清空
- × 「複製」或「刪除」在未儲存的專案上可點擊

---

### E-03 WI 加入規則

- **來源**：UX-design-spec §5.2；F-03 快照不變量
- **交付物**：加入 WI 的後端邏輯

**驗收標準：**
1. 加入 WI 時，若專案尚未建立，**先自動建立專案**再執行加入
2. 加入後的 WI 為**快照副本**：原始 WI 後續修改，不影響已加入專案的內容
3. WI 快照保留 `source_wi_id` 供溯源（UI 可顯示「來源已更新」提示，但不自動同步）

**拒絕條件：**
- × 原始 WI 修改後，已加入專案的 WI 自動更新
- × 加入時若專案未儲存，拋出錯誤而非自動建立

---

### E-04 Tab 1 — 動作模組工作區（ActionModuleWorkspace）

- **來源**：F-03 §2.1；F-03b §1；ActionModuleWorkspace.vue
- **交付物**：L1 動作模組建立器 + ActionModulePool 元件

**驗收標準：**

1. 頁面包含兩個並存區塊：**Builder**（填 slot 建立單一動作）+ **ActionModulePool**（已儲存的模組清單）
2. Builder 區：選序列模型（GM/CM）→ 填 context 欄位 + slots → 即時 preview TMU 與口語句 → 點「新增到 Pool」→ 儲存為 L1 ActionModule
3. NL Draft（自動填空）**只在此 Tab 出現**，Tab 2 / Tab 3 不得有 NL Draft 輸入框
4. ActionModulePool 支援：搜尋（依口語句）、多選、clone、edit（載入 Builder 重新編輯）、delete、拖拉排序、單條 SIMO toggle、frequency 調整
5. Pool 中每筆顯示：GM/CM tag + 使用手 + 口語句 + TMU + SIMO/frequency 狀態
6. `source` 欄位：手動建立→`manual`；NL Draft 建立→`ai`；clone→`copied`（後端儲存，前端可選顯示）
7. edit 已儲存模組：Builder 帶入原有 slot 選項，修改後點「更新模組」

**拒絕條件：**

- × Tab 2 或 Tab 3 出現 NL Draft 輸入框
- × 點「新增到 Pool」後 Builder 不清空（沿用舊值，使用者不知道是否已儲存）
- × Pool 清單無搜尋功能

---

### E-05 Tab 2 — WI 組成工作區（WIPoolWorkspace）

- **來源**：F-03 §2.2；WIPoolWorkspace.vue；WIComposer.vue
- **交付物**：L2 WI 組成器 + WI Pool 元件 + 緊湊模組選取器

**驗收標準：**

1. 頁面包含三個並存區塊：**緊湊模組選取器**（Compact Picker）+ **WI 組成器**（WIComposer）+ **WI Pool**（已儲存 WI 清單）
2. **緊湊模組選取器**：顯示 Tab 1 的 ActionModulePool 全部內容（緊湊列表，含搜尋框），可多選後點「加入組成器」；此 Picker 是為了減少使用者來回切 Tab，不是另一份資料
3. **WI 組成器**：接收「從 Tab 1 傳送過來的模組」或從 Picker 手選的模組 → 顯示順序可拖拉 → 填 WI 名稱/描述 → 點「儲存為 WI」→ 建立 WITemplate（子項快照）
4. 儲存 WI 時，每個 ActionModule 的內容**複製為子快照**：此後修改 ActionModule 不影響已建立的 WI
5. **WI Pool**：顯示所有已儲存 WITemplate；支援搜尋（WI 名稱）、clone、delete、多選後「傳送至 Tab 3」
6. WI Pool 每筆顯示：WI 名稱 + 模組數量 + 總 TMU + 總秒數；可展開看子模組列表

**拒絕條件：**

- × Tab 2 緊湊模組選取器與 Tab 1 的 ActionModulePool 資料不同步（各自獨立）
- × 儲存 WI 後修改來源模組，WI 子項內容自動跟著變
- × WI 組成器無法接收從 Tab 1 「傳送至 Tab 2」的模組

---

### E-06 Tab 3 — 製程途程工作區（ProcessWorkspace）

- **來源**：F-03 §2.3；F-03b §4；ProcessWorkspace.vue
- **交付物**：L3 ProcessRoute 編輯器 + WI 選取器

**驗收標準：**

1. 頁面包含兩個並存區塊：**WI 選取器**（Compact WI Picker）+ **製程大綱**（ProcessOutline）
2. **WI 選取器**：顯示 Tab 2 WI Pool 全部內容（含搜尋框），可多選後點「加入流程」
3. 加入流程使用**增量 API**（`POST /process-routes/{id}/items`）：現有 ProcessRoute 上增加 items，不重建整個 ProcessRoute（修正 v3 的 for-loop create bug——J-07）
4. **製程大綱**：顯示 WI 實例列表（每筆為加入時的 WI 快照）；支援拖拉排序、複製、刪除、inspector 查看子模組
5. 製程項可局部微調（inspector 改某一子模組的 slot）；改完可點「套用為新版本」（觸發 J-06 影響範圍確認對話框）
6. 顯示製程統計：WI 數量 + 總 TMU + 總秒數

**拒絕條件：**

- × 加入 N 個 WI 在 DB 建出 N 個 ProcessRoute（v3 bug 重現）
- × 微調後點「套用為新版本」未顯示影響範圍確認對話框（違反 J-06）
- × WI 選取器與 Tab 2 WI Pool 資料不同步

---

### E-07 跨 Tab 傳送機制（send-to-next）

- **來源**：F-03 §2.5；MostWorkbenchV3Page.vue（`handleSendToWI`、`handleSendToProcess`）
- **交付物**：跨 Tab 資料傳遞邏輯

**驗收標準：**

1. Tab 1 ActionModulePool 多選後點「傳送至 WI 工作區」→ **自動切換至 Tab 2**，WI 組成器帶入選取的模組（`pendingModules`）
2. Tab 2 WI Pool 多選後點「傳送至製程」→ **自動切換至 Tab 3**，WI 選取器或製程大綱直接接收（`pendingWiIds`）
3. 傳送後，來源 Tab 的選取狀態清除（不殘留）
4. 傳送是**單向**的（Tab 1→2→3）；不存在從 Tab 3 傳回 Tab 2 或 Tab 1 的自動機制
5. apply-back（Tab 3 → 來源模組）是**顯式**操作（含確認對話框），不是自動傳回

**拒絕條件：**

- × 傳送後 Tab 不自動切換，使用者需手動切換
- × 傳送後來源 Tab 選取狀態殘留
- × Tab 3 修改 WI 實例後自動回寫 Tab 2 WI Pool（應為顯式 apply-back）

---

## F｜Level System

### F-01 R1–R9 填入規則

- **來源**：`docs/core-logic/level-system-core-logic-spec.md`；F-01 §5
- **交付物**：LevelSystem 頁面 + 後端 level.py 驗證

**驗收標準：**
1. R1–R9 填入規則完整實作：main/sub/cub/nb 四層關係正確
2. 後端拒絕非法填入（422 含錯誤碼）
3. Given 黃金輸入（CL-01 §5 GM 案例），level 計算結果與文件一致
4. Level System 是 workbench 的**輸出層**：必須先有 WI 列才能填 Level

**拒絕條件：**
- × R1–R9 任一規則未實作（允許非法組合）
- × Level System 與工作台計算結果不一致

---

### F-02 Level 對 LB 的輸出合約

- **來源**：`docs/core-logic/level-system-core-logic-spec.md`；MOST→LB 整合
- **交付物**：LevelEntry 資料結構的 API 輸出

**驗收標準：**
1. LevelEntry 含：`main/sub/cub/nb` 欄位 + `row_id` + `group_id`
2. 匯出或 API 輸出的 LevelEntry 結構不得單邊修改（變更須同時更新 LB 端）
3. LB 消費 MOST 輸出的格式有對應的 schema validation 測試

**拒絕條件：**
- × LevelEntry 欄位任意增減，未通知 LB 端

---

## G｜分析案件（CaseEditorPage）

### G-01 案件清單與狀態篩選

- **來源**：F-07 §2
- **交付物**：CaseListPage

**驗收標準：**
1. 清單支援按狀態篩選：草稿 / 已送審 / 已審核 / 退回修改 / 已核准 / 已封存
2. 每筆案件顯示：案件名稱、狀態徽章、建立者、最後更新時間
3. 依角色顯示可操作按鈕（非本人且非 admin 不顯示「編輯」）

**拒絕條件：**
- × 所有使用者的清單相同（未依角色過濾可操作項目）

---

### G-02 審核狀態機

- **來源**：F-07 §1
- **交付物**：狀態機 API（submit/review/request-changes/approve/retire）

**驗收標準：**
1. 狀態轉換路徑正確：`draft → submitted → reviewed → approved → retired`；`reviewed → changes_requested → draft`
2. 非法跳關（如 draft 直接 approve）→ 409 `WORKFLOW_TRANSITION_INVALID`
3. 每次轉換記錄 audit log：who / from_state / to_state / comment / timestamp
4. 角色限制：submit=analyst；review/request-changes=reviewer；approve=approver；retire=admin
5. `WORKFLOW_MODE=simple` 時：只有 draft/approved 兩態，既有 publish 流程回歸測試全綠
6. 已 approved 的案件：內容凍結（PUT 回 409）；可 clone 新 draft

**拒絕條件：**
- × 任何角色可執行不屬於自己的狀態轉換
- × 跳關未報 409（如 draft → approve）
- × simple 模式下現有功能回歸測試失敗

---

### G-03 報表匯出（xlsx 三 sheet）

- **來源**：F-07 §3
- **交付物**：`GET /api/v2/worksheets/{id}/export.xlsx`

**驗收標準：**
1. Sheet 1（案件資訊）：含編號/產品/機種/站別/作業/廠區/線別/值版本/寬放率/狀態/時間戳 + 步驟總數/總 TMU（2 位）/總正常秒（3 位）/總標準秒（3 位）
2. Sheet 2（動作明細）：含步驟/說明（優先人工句）/序列模型/頻率/插槽明細（tech_line 展開格式：`A1(A)=6 | B1(B)=0 | …`）/步驟 TMU/正常秒（4 位）/標準秒（4 位）；SIMO 列有標示
3. Sheet 3（簽核歷程）：含時間/動作/從狀態/至狀態/執行者/備註
4. 標準秒 = 正常秒 × (1 + 寬放%)；與 CL-04 計算結果一致
5. SIMO 合計與 CL-04 §2 規格一致（group-max，不是 sum）

**拒絕條件：**
- × 少於三個 sheet
- × SIMO 列的合計用 sum 而非 max
- × 標準秒公式錯誤

---

## H｜字典管理

### H-01 字典管理頁面

- **來源**：F-06
- **交付物**：DictionariesPage

**驗收標準：**
1. 可檢視現有字典版本清單：版本號/狀態（draft/published）/建立時間
2. 可發布 / clone / 退役字典版本
3. 每個字典版本可瀏覽：模型 → slot → 選項 樹狀結構
4. 工作台使用的選項來自「已發布」的字典版本（不使用 draft 版本）

**拒絕條件：**
- × 工作台載入 draft 版字典
- × 發布/退役操作無角色限制（應為 admin 限定）

---

### H-02 字典匯入

- **來源**：F-06 §匯入；ADR-014
- **交付物**：DictionaryImportPage + `scripts/import_v3_dictionary.py`

**驗收標準：**
1. 可從 `minimost_ai_dictionary_v1.json` 匯入產生 `MINIMOST_FACTORY_V2` seed
2. `src/ddm_v2/seed/v2/rule_set_seed_v2.py` 為**生成檔**，不得手動編輯
3. 匯入後跑 golden test（GM=28, CM=29）必須通過
4. 匯入失敗時回滾，不留下半套資料

**拒絕條件：**
- × 手動編輯 rule_set_seed_v2.py 而不透過匯入腳本
- × 匯入後 golden test 失敗但仍視為成功

---

## I｜RBAC 與使用者管理

### I-01 五角色與權限矩陣

- **來源**：F-08；UX-design-spec §1.2
- **交付物**：後端 `require_roles()` + 前端 route guard

**驗收標準：**
1. 五個角色：`admin / analyst / reviewer / approver / viewer`
2. 後端 `require_roles()` 為唯一權限權威；前端 route guard 僅為 UX 友善
3. 角色對應操作：

| 操作 | 最低角色 |
|---|---|
| 讀取所有內容 | viewer |
| 建立/編輯自己的內容 | analyst |
| 送審 | analyst |
| 審核/退回 | reviewer |
| 核准/發布 | approver |
| 退役/刪除/管理使用者 | admin |

4. 角色變更後**立即生效**（不需重新登入）
5. 停用使用者（`is_active=false`）的 API 請求立即拒絕（無 grace period）

**拒絕條件：**
- × 前端可繞過後端權限（刪除前端 guard 後可執行禁止操作）
- × 角色變更後需重新登入才生效

---

### I-02 所有權範圍（Ownership Scope）

- **來源**：F-08 §ownership
- **交付物**：資源 owner 欄位 + 服務層 ownership check

**驗收標準：**
1. 每個資源（WI/案件/動作模組）攜帶 `owner` 欄位（employee_no）
2. analyst 只能修改 `owner === me` 的個人資源（admin 例外）
3. 嘗試修改他人資源 → 403 `FORBIDDEN`

**拒絕條件：**
- × analyst 可修改他人建立的 WI

---

### I-03 使用者管理頁面

- **來源**：F-08 §users
- **交付物**：UsersPanel / UsersPage

**驗收標準：**
1. 列出所有使用者：employee_no、姓名、角色、狀態
2. admin 可新增/停用/修改角色
3. 搜尋/過濾功能（按角色或狀態）
4. 停用後使用者在下次 API 請求即被拒絕

**拒絕條件：**
- × 非 admin 角色可訪問使用者管理頁面

---

## J｜核心邏輯（後端不可移除）

### J-01 GM/CM 黃金值

- **來源**：CL-01；`docs/core-logic/core-logic-validation-test-catalog.md`
- **交付物**：`most_engine/calculate.py` + golden test

**驗收標準：**
1. **GM 黃金值**：A6 B0 G6 A10 B0 P6 A0 → **TMU = 28**
2. **CM 黃金值**：A10 B0 G3 M16 X0 I0 A0 @ 45cm push → **TMU = 29**
3. 任何改動 `most_engine/` 或 rule-set seed 後，`scripts/core_logic/run_all.py` 必須全綠
4. `MINIMOST_FACTORY_V1` snapshot tests 不得改變（V1 replay isolation）

**拒絕條件：**
- × GM 不等於 28 或 CM 不等於 29
- × 修改引擎後未跑 golden test

---

### J-02 計算在後端、前端不計算

- **來源**：F-01 行為規則 1；CLAUDE.md 不變量；UX-design-spec §8 規則 1
- **交付物**：全端架構守則

**驗收標準：**
1. 所有 TMU 計算透過 `POST /api/v2/minimost/calculate`
2. 前端原始碼 grep 不到任何 TMU 計算公式（0.036 換算除外的展示用）
3. Preview API 是**無副作用的試算**：不寫入資料庫

**拒絕條件：**
- × 前端 JavaScript/TypeScript 內有任何 TMU 加總或 slot index_value 引用

---

### J-03 SIMO 合計規則

- **來源**：CL-04 §2
- **交付物**：`most_engine/calculate.py` 的 SIMO group-max 邏輯

**驗收標準：**
1. `total_tmu = Σ(非SIMO列 effective_tmu) + Σ(每 simo_group 的 max(effective_tmu))`
2. Given 兩列 SIMO（29 與 28）→ 合計 29；交換標記方向合計不變
3. Given 非 SIMO 三列 28/29/6 → 合計 63，normal = 2.268s
4. 刪除 SIMO 群組其中一列後，合計立即重算

**拒絕條件：**
- × SIMO 配對列都被計入合計（兩列都加不取 max）

---

### J-04 Snapshot 不自動同步原則

- **來源**：F-03 §snapshot；F-03b §1；UX-design-spec §8 規則 4
- **交付物**：三層組裝邏輯（動作模組 → WI 範本 → 途程）

**驗收標準：**
1. 動作模組加入 WI 範本後：修改動作模組，WI 範本內容**不自動更新**
2. WI 範本加入途程後：修改 WI 範本，途程內容**不自動更新**
3. UI 可選擇性顯示「來源已更新」provenance badge（非強制，但不得靜默同步）
4. 所有跨實體引用均為軟參考（nullable string），不建 DB-level FK 約束
5. 來源資源被刪除後：快照完整保留，UI 顯示「來源已失聯」badge，不報錯

**拒絕條件：**
- × 上游修改自動傳播到下游快照
- × 來源刪除導致快照資料消失或 API 錯誤

---

### J-05 標準秒計算鏈

- **來源**：CL-04 §3
- **交付物**：時間鏈計算與匯出

**驗收標準：**
1. `normal_seconds = total_tmu × 0.036`（4 位精度）
2. `standard_seconds = normal_seconds × (1 + allowance_percent / 100)`
3. allowance 掛在 worksheet（案件）層級，不在列層級
4. API 同時回傳 normal 與 standard；對 LB 輸出給 normal（寬放為 MOST 端政策）

**拒絕條件：**
- × standard_seconds 計算公式錯誤（如 allowance 加在 TMU 而非 seconds）

---

### J-06 Apply-Back 影響範圍確認（v2 強化，DISC-09）

- **來源**：F-03b §3；DISC-09（v3 破壞性覆寫不移植）
- **交付物**：apply-back（途程實例→發布模組新版本）API 與對話框

**驗收標準：**

1. 使用者點擊「套用為新版本」時，系統**必須**先顯示影響範圍確認對話框
2. 對話框列出：引用同一模組的流程清單（含流程名稱）+ 數量；若為 0 則說明「此模組目前未被其他流程引用」
3. 對話框說明：現有流程繼續使用快照（不受影響），新版本僅供未來引用
4. apply-back 成功後：`motion_modules.current_version` +1，舊版本仍可透過 `GET /versions` 查詢
5. 提供「另存為全新模組」選項，不影響原模組任何版本
6. 非模組 owner 且非 admin：回傳 403

**拒絕條件：**

- × apply-back 未顯示對話框即直接覆寫
- × apply-back 覆寫舊版本而非建立新版本
- × 完成後舊版本不可讀

---

### J-07 ProcessRoute 增量加入 WI（v3 bug 修正）

- **來源**：F-03b §4；C-14（v3 bug：每次加 WI 重建整個 ProcessRoute）
- **交付物**：`POST /api/v2/process-routes/{id}/items` 增量 API

**驗收標準：**

1. API 設計為增量新增：對現有 ProcessRoute 加入新 WI，不重建整個 ProcessRoute
2. Given 已有 3 筆 items 的 ProcessRoute，When POST /items 加入 2 個新 WI，Then 原 3 筆不變，新增 2 筆，共 5 筆
3. DB 中不存在孤兒 ProcessRoute（加入過程中建立後被拋棄的孤兒）
4. ProcessRoute 不存在→404；WI 模組已退役→409

**拒絕條件：**

- × 加入 N 個 WI 產生 N 個 ProcessRoute（v3 bug 重現）
- × 加入新 WI 後既有 items 的順序或內容被改動

---

## K｜MOST → LB 整合契約

### K-01 輸出合約結構

- **來源**：CLAUDE.md（流向修正）；Level System 規格
- **交付物**：MOST 匯出給 LB 的資料格式

**驗收標準：**
1. 輸出方向：**MOST 是來源、LB 是消費方**（不可反向）
2. 輸出包含：`LevelEntry[]`（含 main/sub/cub/nb + row_id + group_id）+ `normal_seconds`（不含 standard/allowance）
3. 有 API/schema validation 測試覆蓋輸出格式
4. 任何輸出欄位變更，需同時通知 LB 端（unified-arch 協調）

**拒絕條件：**
- × MOST 消費 LB 輸出（流向反轉）
- × 輸出結構單邊修改，LB 端未同步更新

---

## L｜移除確認清單（v2 功能退役）

### L-01 水平 Tab Bar → Sidebar

- [ ] 水平 Tab bar 元件已從 `App.tsx` 移除
- [ ] 所有原 Tab 的功能已在 Sidebar 導覽中對應
- **驗收**：`App.tsx` grep 不到 `TABS` 陣列或 tab 切換邏輯

---

### L-02 quick/precise 雙模式

- [ ] `mode: 'quick' | 'precise'` 狀態已從 workbench 移除
- [ ] 相關 UI 切換元件已刪除
- **驗收**：`WiWorkbench.tsx` grep 不到 `quick` / `precise` mode

---

### L-03 主數據（MasterData）Tab 退役

- [ ] `MasterData.tsx` Tab 入口已關閉或移除
- [ ] 主數據功能已合併至字典管理（DictionariesPage）
- **驗收**：nav 不再顯示獨立的「主數據」Tab

---

### L-04 SOP 版本 Tab 退役

- [ ] `SopPanel.tsx` Tab 入口已關閉
- [ ] 確認無任何 v3 功能依賴 SOP 版本
- **驗收**：nav 不再顯示「SOP 版本」Tab；相關後端 route 可保留供日後評估

---

### L-05 WILibraryItem.source 死欄位清理（C-17）

- [ ] v2 TypeScript 型別定義中，`WILibraryItem` 不含 `source` 欄位
- [ ] `GET /api/v2/wi-library` response schema 不含 `source` 欄位
- [ ] `ActionModuleTemplate.source`（值：`manual`/`ai`/`copied`）正常實作，不受影響
- **驗收**：`grep -r "WILibraryItem" src/frontend/src` 找不到 `.source` 存取；OpenAPI schema 無此欄

---

## 簽核欄

| 項目 | 簽核人 | 日期 | 備註 |
|---|---|---|---|
| **A 全域殼層**（A-01~A-03） | | | |
| **B MOST 工作台**（B-01~B-12） | | | |
| **C 動作清單**（C-01~C-04） | | | |
| **D WI 大綱**（D-01~D-02） | | | |
| **E WI Pool 與專案**（E-01~E-03） | | | |
| **F Level System**（F-01~F-02） | | | |
| **G 分析案件**（G-01~G-03） | | | |
| **H 字典管理**（H-01~H-02） | | | |
| **I RBAC 與使用者**（I-01~I-03） | | | |
| **J 核心邏輯**（J-01~J-05） | | | |
| **K LB 整合契約**（K-01） | | | |
| **L 功能退役**（L-01~L-04） | | | |

---

> **版本**：v1.0 — 2026-07-08  
> **下次審閱**：每次重大功能移植完成後更新 `[x]` 狀態；驗收標準修改需重新簽核受影響欄位。
