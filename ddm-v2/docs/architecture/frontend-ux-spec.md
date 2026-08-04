# DDM v2 Frontend UX Design Spec

> **來源**：從使用者驗證過的 v3 UX 萃取，並由 ADR-021/022 收斂為 ddm-v2 的 UX 約束。
> **用途**：v2 前端 UX 規格。技術實作（框架/元件庫）可換，本文件描述的互動語意與佈局邏輯不可任意改。
> **維護**：更動本文件前必須有使用者確認；設計決策理由用 `▷ 原因` 標記。
> **決策關聯**：[ADR-021](../decisions/ADR-021-ia-restructure-v3-parity.md)、[ADR-022](../decisions/ADR-022-workbench-two-layer-correction.md)、[ADR-024](../decisions/ADR-024-master-data-vs-dictionary-boundary.md)。衝突時以較新的 accepted ADR 為準。

---

## 1. 全域殼層（AppLayout）

### 1.1 佈局結構

```
┌─────────────────────────────────────┐
│ Header (固定 50px)                   │
├──────────┬──────────────────────────┤
│ Sidebar  │  Main Content            │
│ 200px /  │  #f5f7fa 底色            │
│ 56px折疊 │  16px padding            │
└──────────┴──────────────────────────┘
```

- Sidebar 可折疊：展開 200px / 折疊 56px，切換動畫 0.2s ease
- Mobile（≤768px）：Sidebar 轉 `position: fixed`，折疊至完全隱藏（0px）
- Header 左側：系統名稱；右側：登入使用者 + 登出按鈕

### 1.2 導覽項目（固定順序）

| 項目 | 短標（折疊時） | 角色可見 |
|------|--------------|---------|
| 儀表板 | 表 | 全部 |
| MOST 工作台 | M | 全部 |
| WI 專案建立 | W | 全部 |
| Level System | L | 全部 |
| 分析案件 | 案 | 全部 |
| 字典管理 | 典 | admin 限定 |
| 使用者管理 | 人 | admin 限定 |

▷ 原因：折疊時用短字標而非 icon，確保中文使用者在小螢幕仍能識別。

### 1.3 色彩 Token（全域）

| Token | 色碼 | 用途 |
|---|---|---|
| `sidebar-bg` | `#304156` | 深藍灰 sidebar 背景 |
| `page-bg` | `#f5f7fa` | 主內容區底色 |
| `card-border` | `#e4e7ed` | 所有卡片外框 |
| `toolbar-bg` | `#fafafa` | 工具列底色 |
| `toolbar-border` | `#ebeef5` | 工具列下邊框 |
| `tmu-value` | `#1a73e8` | **TMU 數值**（藍色粗體，全站一致） |
| `meta-text` | `#909399` | 計數/次要資訊（11–12px） |
| `row-editing` | `#fdf6ec` | 編輯中的列（暖黃） |
| `row-selected` | `#eff6ff` | 已選取的列（淺藍） |
| `row-dragging` | `#e0f2fe` + `outline: 2px solid #0ea5e9` | 拖曳中 |
| `ai-inferred` | 綠色 | AI Badge：AI 推斷 |
| `ai-default` | 橘色 | AI Badge：預設值 |
| `ai-pending` | 紅色 | AI Badge：待確認 |

---

## 2. MOST 工作台（MostWorkbenchPage）

### 2.1 整體佈局：單欄垂直堆疊

```
┌─────────────────────────────────────┐  ← Section 1: 序列編輯器
│ [NlDraftInput]                      │    flex-shrink: 0
│ [模型選擇器 150px] [SequenceSummaryBar flex-1] │
│ [SequenceSlotBuilder — 水平 slot strip] │
│ [錯誤 alert，紅色，條件顯示]          │
│ [WI 語句輸入] [更新動作/新增動作按鈕] │
├─────────────────────────────────────┤  ← Section 2: 動作清單
│ [搜尋 180px] [列數] | [選取資訊/合計] │    flex: 1, min-height: 200px
│ [MiCompositionTable]                │
├─────────────────────────────────────┤  ← Section 3: WI 大綱（條件顯示）
│ WI 大綱 (N 項)                      │    max-height: 42vh，內部滾動
│ [WiOutline]                         │
└─────────────────────────────────────┘
```

**覆蓋層（overlay）：**
- `SlotModal`：對話框，點擊 slot block 觸發
- `WiItemInspector`：抽屜（drawer），點擊 WI 大綱項目觸發

▷ **單欄設計原因**：IE 分析師的操作主線是線性的（填格→算→存），三欄佈局在小螢幕會讓工具列超出視口。

▷ **42vh 上限原因**：避免 WI 大綱展開後擠壓上方動作清單，使第 8–12 列不可見。

### 2.2 Section 1 — 序列編輯器

**模型切換行為（必須保留）：**
- `GM → CM`：清空 P/A2/B2；保留 A1/B1/G/A3 及全部 context 欄位
- `CM → GM`：清空 M/X/I；保留 A1/B1/G/A3 及全部 context 欄位
- NL 草稿填入時用 `suppressModelChangeReset` flag 防止切換清空 AI 推斷的值

**按鈕狀態：**
- 新建模式：「新增動作」（綠色）
- 編輯模式：「更新動作」（橘/warning）+ 「取消編輯」

**WI 名稱規則：**
- 首條已存句子自動填入 WI 名稱
- 使用者手動改過（`wiNameTouched = true`）後，不再自動覆蓋

**計算觸發：**
- 任何 slot/context/hand/frequency 變更 → 400ms debounce → preview API（無副作用）

### 2.3 Slot Strip（SequenceSlotBuilder）

水平排列，`flex-wrap: wrap; gap: 6px`。完整欄位順序：

**General Move：** 使用手 | 從哪裡 | A1 | B1 | G | 目標物 | 元件 | A2 | B2 | P | 到哪裡 | A3
**Controlled Move：** 使用手 | 從哪裡 | A1 | B1 | G | 目標物 | 元件 | M | 到哪裡 | X | I | 哪裡 | A3

**Context Block 樣式：**
- 使用手：紫底（`#f0e6ff`，border `#c4a8e8`）；含 「顯示於MI」checkbox
- 其他 context：暖黃底（`#fdf8e8`，border `#e0d8c0`）
- 寬度：`min-width: 80px; max-width: 110px`

**AI Badge：**
- 浮於 slot block 下方（`position: absolute; bottom: -2px; transform: translateX(-50%)`）
- 三色表示 AI 信心程度（綠/橘/紅）

### 2.4 Section 2 — 動作清單（MiCompositionTable）

**12 欄結構（左→右）：**

| 欄 | 寬度 | 說明 |
|---|---|---|
| 拖曳把手 ⋮⋮ | 36px | cursor: grab |
| Checkbox | 34px | 選取供「加入 WI」 |
| # 序號 | 34px | |
| 手 | 44px | 右手/左手/雙手 |
| WI / 動作描述 | min 200px, flex | 人工句優先；2-line clamp |
| Base TMU | 58px, 右對齊 | |
| 頻率 | 100px | 內嵌 input-number（80px，右側控制） |
| Eff TMU | 70px | **藍色粗體 `#1a73e8`** |
| CT(秒) | 62px | |
| SIMO | 56px | checkbox |
| 納入 TMU | 60px | SIMO 開啟時顯示刪除線 + 灰色 |
| 操作 | 100px, 固定右側 | ✏️ 編輯 / 📋 複製 / ✕ 刪除（紅） |

**拖曳 UX 細節（必須完整實作）：**
- 拖曳中：`#e0f2fe` + `outline: 2px solid #0ea5e9` + shadow
- 放置目標上半：3px 藍色 top border
- 放置目標下半：3px 藍色 bottom border
- Handle hover：灰色填充；active：淺藍 + cursor grabbing

**高度計算：**
- 用 `ResizeObserver` 動態量測容器高度作為 `maxHeight`（fallback: 360px）
- 目的：確保動作清單永遠在視口內可滾動，不因 WI 大綱展開而被遮

### 2.5 Section 3 — WI 大綱（WiOutline）

- 條件顯示：`savedMiStatements.length > 0` 才出現
- `max-height: 42vh`，內部 `overflow-y: auto`
- 點擊項目 → WiItemInspector 抽屜

**工具列邏輯：**
- 有選取列時：顯示「已選 N 筆 · Eff TMU · CT 秒」+ WI 名稱輸入 + 「加入 WI」按鈕
- 無選取時：顯示合計列（WI 數 / 動作數 / TMU / 秒）

---

## 3. SlotModal（格位編輯對話框）

### 3.1 尺寸規則

| Slot | 寬度 | 原因 |
|---|---|---|
| A（A1/A2/A3） | **820px** | ADistanceSelector 需要左右視覺佈局 |
| 其他所有格 | **520px** | 標準 |

### 3.2 各格 UI 結構

**A 格（reach distance）：**
1. ADistanceSelector（視覺選擇器，全寬）
2. 手轉角度：下拉選單（僅 A1/A2；A3 不顯示）
3. 腳步：下拉選單（僅 A1/A2）
4. 公式說明：「計算方式：依據距離 / 手轉角度 / 腳步取最大值」或「A3 僅依據距離計算」

**B 格（body motion）：**
- 單一下拉，**選完自動確認關閉**（無 Footer 按鈕）

**G/I 格（grasp/inspect）：**
- 單一下拉 + 確認按鈕 + repeat count

**M 格（controlled move verb）：**
- 三組（verb / hand_degree / foot_step），各有 label + filterable 下拉 + TMU 顯示
- 公式說明：「取最大值 max(動作, 手轉角度, 腳步)」

**P 格（place）：**
- 基礎動作下拉
- 附加條件：tag 選擇器（`el-check-tag` 風格）
  - **最多 2 項**
  - **insert ⊥ snap 互斥**（UI 即時強制，後端重驗）
- 公式說明：「基礎 + Σ(附加條件)」

**X 格（process time）：**
- 時間類型下拉
- 條件式秒數輸入（`seconds_source === 'user_input_seconds'` 時才顯示）
- 公式說明：「秒數 ÷ 0.036 = TMU」

### 3.3 共用 UI 模式

**Repeat Count 區塊**（G/P/M/X/I 可用）：
- 虛線 top border 分隔
- `input-number` min=1
- >1 時顯示紫色 `×N` badge（`#9c27b0`）
- 說明文字：「此動作重複次數（不影響其他欄位）」

**公式說明卡片**：
- `border-left: 3px solid #409eff; background: #f9f9f9`
- 永遠顯示在 modal 內容底部

**Footer：**
- 左側：「清除此欄位」（danger/text，僅有現有選擇時顯示）
- 右側：取消 + 確認（B 格無此 footer）

---

## 4. WI Pool 面板（Block E）

### 4.1 佈局結構

```
┌─────────────────────────────────────┐
│ Block E — WI Pool              N/N  │  ← 灰色 Header
├─────────────────────────────────────┤
│ [搜尋 180px]  |  [已選N筆][加入][取消] │  ← Toolbar
├─────────────────────────────────────┤
│ ┌─ WI Card ──────────────────────┐  │
│ │ ☐ ▸ CODE | WI名稱 | N模組·TMU·s│  │  ← max-height: 40vh（RWD，不寫 px）
│ │   ├ 1. GM ▐ 句子... ▐ TMU      │  │
│ │   └ 2. CM ▐ 句子... ▐ TMU      │  │
│ └──────────────────────────────── ┘  │
└─────────────────────────────────────┘
```

**WI Card 展開/折疊：**
- 折疊：顯示 checkbox + expand arrow + code + name + stats chip + 操作按鈕
- 展開：子項縮排 36px，各子項顯示：序號 | GM/CM tag | 句子（2-line clamp）| TMU

**高度原則（RWD）：**

- 所有 Pool / 清單面板高度一律用 `vh` 單位，不寫 `px` 固定值
- WI Pool 列表區：`max-height: 40vh`；WIPoolSearch 搜尋表格：`max-height: 45vh`

**選取狀態：**
- Card border 變 `#409eff`，背景 `#ecf5ff`

**空白狀態：**
- 置中灰字「尚無 WI 模板，請先組合動作模組並儲存」

---

## 5. WI 專案建立頁（WISetBuilderPage）

### 5.1 佈局

```
┌─────────────────────────────────────┐
│ WI Set Builder / WI 專案建立        │
│ [專案選擇器 280px]  [New Project]   │  ← max-width: 1200px, 置中
├─────────────────────────────────────┤
│ Section A — 專案 Metadata 表單      │  ← 必填：名稱/site/BU/process/family/model
├─────────────────────────────────────┤
│ Section B — WI Pool 搜尋            │  ← 加入後：清選取、保留搜尋結果
├─────────────────────────────────────┤
│ Section C — 已選 WI 清單           │  ← 支援 drag-reorder + 上下箭頭
├─────────────────────────────────────┤
│ Section D — 統計摘要               │
├─────────────────────────────────────┤
│ Section E — 儲存 / 複製 / 刪除      │
└─────────────────────────────────────┘
```

### 5.2 關鍵互動規則

| 行為 | 規則 |
|---|---|
| 加入 WI | 若專案尚未儲存，先自動建立再加入 |
| 加入後 | Section B 選取清空，但搜尋結果保留（可立即選下一批） |
| 排序 | Drag-and-drop 與上下箭頭 buttons 呼叫相同 `handleReorder` |
| URL 同步 | 建立/載入/複製/刪除後 `router.replace({ query: { id } })` |

---

## 6. v2 vs v3 功能差異對照

### 6.1 對照表

| 功能 | v2 現況 | v3 現況 | 移植決策 |
|---|---|---|---|
| **全域導覽** | 水平 Tab bar（8 個 tab） | 可折疊側邊 Sidebar | **移植 v3 設計**：換成 sidebar |
| **MOST 工作台** | 基本格位表格，`quick/precise` 兩個 mode | 富互動：slot strip + SlotModal + AI badge + ResizeObserver | **移植 v3**：完整重實作 |
| **Slot 編輯** | 簡單 `<select>` inline | SlotModal（per-slot 820/520px 對話框） | **移植 v3** |
| **AI 草稿輸入（NlDraft）** | 無 | NlDraftInput（上方全寬輸入區） | **移植 v3** |
| **AI badge（推斷信心）** | 無 | 三色 badge（推斷/預設/待確認） | **移植 v3** |
| **WI 大綱** | 無 | WiOutline（42vh conditional panel） | **移植 v3** |
| **WI Pool / WI 專案** | 無 | WISetBuilderPage + WIPool 完整實作 | **移植 v3** |
| **分析案件** | 無 | CaseEditorPage / CaseListPage / CaseReportPage | **移植 v3** |
| **字典管理** | 無 | DictionariesPage + DictionaryImportPage | **移植 v3** |
| **Level System** | 有（LevelSystem.tsx） | 有（LevelSystemPage.vue） | **保留 v2**，按 v3 UX 補齊缺口 |
| **主數據（MasterData）** | 有（MasterData.tsx） | 無（融入字典管理） | **評估移除**：功能合併進 Dictionary 管理 |
| **Rule-set Viewer** | 有（RuleSetViewer.tsx） | 無 | **保留 v2**：admin 管理用，v3 只是不顯示給一般用戶 |
| **SOP 版本** | 有（SopPanel.tsx） | 無 | **評估移除**：v3 沒有此設計，先暫停開發 |
| **匯出** | 有（Export.tsx） | CaseReportPage | **保留 v2，對齊 v3 CaseReport** |
| **匯入 Excel** | 有（ImportModal 浮層） | 無（已廢棄入口） | **保留 v2**：工業用途必要 |
| **使用者管理** | 有（UsersPanel.tsx） | UsersPage | **保留 v2**，對齊 v3 UX |
| **目錄（catalog）** | 有（CatalogPanel.tsx） | 無 | **保留 v2**：Site/Product/SKU 層級管理 |

### 6.2 v2 應移除的功能

| 功能 | 理由 |
|---|---|
| `主數據 (MasterData)` tab | v3 設計將其融入字典管理；單獨的 tab 造成概念重複。等字典管理移植後移除。 |
| `SOP 版本` tab | v3 未規劃此功能；目前 v2 實作是空殼。暫停，不繼續投資。 |
| `quick/precise` 兩模式切換 | v3 只有一種編輯模式（slot strip + modal）；兩模式增加認知負擔。 |
| 水平 tab 導覽 | 換成 v3 的 sidebar；tab bar 移除。 |

### 6.3 v2 保留並強化的功能

| 功能 | 說明 |
|---|---|
| Rule-set Viewer | Admin 工具，v3 不顯示給一般用戶但 v2 需要 |
| 目錄（Catalog） | Site→Product→SKU 層級，v3 沒有但業務上必要 |
| Excel 匯入 | 工廠現場仍需 Excel 流程 |
| 匯出（Export） | 對齊 v3 CaseReport 的三頁 xlsx 格式 |

---

## 7. 移植優先順序

```
Phase 1：殼層重構
  → Sidebar 導覽（替換 tab bar）
  → AppLayout 實作

Phase 2：工作台核心
  → SequenceSlotBuilder（slot strip）
  → SlotModal（per-slot 820/520px）
  → AI badge 系統
  → MiCompositionTable（12欄 + drag）
  → NlDraftInput

Phase 3：WI 組合
  → WI 大綱（WiOutline）
  → WI Pool / WI 專案建立（WISetBuilderPage）

Phase 4：案件流程
  → CaseEditorPage / CaseListPage / CaseReportPage

Phase 5：字典管理
  → DictionariesPage（合併現有 MasterData）
```

---

## 8. 不可改動的 UX 規則（任何框架都要遵守）

1. **計算在後端**：slot 變更後 call preview API，前端不算 TMU
2. **人工句優先**：`user_edited` 句子存在時，重算不覆蓋
3. **加入 WI 後保留搜尋結果**：只清選取，不清搜尋
4. **Snapshot 不自動同步**：動作模組/WI 加入後，上游變更不影響已加入的版本
5. **AI badge 三態**：AI 推斷的值必須有視覺標示（不能靜默填入）
6. **模型切換遷移規則**：A1/B1/G/A3 + context 保留；model-exclusive 格清空
7. **SIMO 顯示**：納入 TMU 在 SIMO 開啟時必須有刪除線視覺
8. **B 格自動確認**：選完就關閉，不需要按確認鈕
9. **P 格 insert⊥snap 互斥**：UI 強制，不等後端 422
10. **TMU 值統一用藍色粗體**（`#1a73e8` 或等效品牌色）顯示
