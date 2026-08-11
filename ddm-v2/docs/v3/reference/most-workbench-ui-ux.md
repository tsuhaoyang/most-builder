# MOST 工作台 UI/UX 套用指南

> 目標：讓其他專案重現同一套視覺語言、互動模式與參數模型。  
> 實作基準：Sidebar「MOST 工作台」→ `/most-workbench` → `MostWorkbenchPage.vue`（UX v2.1）。  
> 相關原始碼：`apps/web/src/pages/MostWorkbenchPage.vue`、`apps/web/src/pages/most-workbench/*`、`apps/web/src/types/most.ts`。

---

## 1. 頁面總覽

單欄垂直堆疊，三個白底區塊（section）＋兩個浮層（modal / drawer）：

```
┌─────────────────────────────────────────────────────────┐
│ Editor Section（動作編輯器）                              │
│  NlDraftInput → Toolbar+SummaryBar → SlotBuilder → CTA   │
├─────────────────────────────────────────────────────────┤
│ Action List Section（已儲存動作列）                       │
│  Search / Total / Join-WI toolbar → MiCompositionTable  │
├─────────────────────────────────────────────────────────┤
│ WI Outline Section（WI 大綱，有資料才顯示）                │
│  WiOutline（可展開子動作，右側開啟 Inspector Drawer）     │
└─────────────────────────────────────────────────────────┘
  SlotModal（點 slot 開啟）
  WiItemInspector（點 WI 子項開啟）
```

### 1.1 頁面骨架樣式

| Token | 值 | 用途 |
|-------|-----|------|
| 頁面高度 | `calc(100vh - 82px)` | 扣掉 App header + 主區 padding |
| Section 背景 | `#fff` | 卡片面 |
| Section 邊框 | `1px solid #e4e7ed` | Element Plus 灰邊 |
| Section 圓角 | `8px` | 統一圓角 |
| Section 間距 | `gap: 10px` | 垂直節奏 |
| 主區背景（layout） | `#f5f7fa` | AppLayout `.app-main` |
| 強調色（TMU 數字） | `#1a73e8` | 合計 / 已選統計 |
| 互動主色 | `#409eff` | Element Plus primary |

---

## 2. 區塊 A — 動作編輯器（Editor）

### 2.1 結構順序

1. **NlDraftInput**：自然語言草稿 → 解析後回填 slot / context（可選）
2. **Toolbar**：模型下拉（`GENERAL_MOVE` / `CONTROLLED_MOVE`）+ `SequenceSummaryBar`
3. **SequenceSlotBuilder**：水平可換行的 slot/context 串列
4. **錯誤提示**：`el-alert`（計算失敗）
5. **Footer**：可覆寫的 WI 語句 +「新增動作 / 更新動作 / 清空」

槽位／context 變動後以 **400ms debounce** 呼叫 `POST /most/calculate-row`（勿每個 keystroke 打滿）。

### 2.2 SequenceSummaryBar（結果條）

- 背景：`linear-gradient(135deg, #f8fbff 0%, #f0f7ff 100%)`
- 邊框：`1px solid #d4e5f7`，圓角 `8px`
- 顯示欄位（由左到右）：

| 欄 | 來源 |
|----|------|
| 動作類型 | `GENERAL_MOVE`→一般移動 / `CONTROLLED_MOVE`→控制移動 |
| 使用手 | left/right/both → 左/右/雙手 |
| 基礎 TMU | `preview.base_tmu` |
| 頻率 | `preview.frequency`（預設 1） |
| 有效 TMU | `preview.effective_tmu`（高亮） |
| CT (秒) | `preview.effective_seconds`（≈ TMU × 0.036） |
| SIMO | 是/否 |
| 納入總時間 | `total_contribution_tmu`（SIMO 時可能為 0） |
| MI 語句 | 前端即時組句 `sentencePreview` |

### 2.3 SequenceSlotBuilder — 流水線排版

`display: flex; flex-wrap: wrap; gap: 6px`。

兩類區塊交錯：

#### Context block（語境欄，無 TMU）

| Key | 標籤 | UI | 背景 |
|-----|------|-----|------|
| hand | 使用手 | select（右/左/雙）+ checkbox「顯示於MI」 | `#f0e6ff` / border `#c4a8e8` |
| from | 從哪裡 | text input → `from_location` | `#fdf8e8` / border `#e0d8c0` |
| target | 目標物 | text → `target_object` | 同上 |
| component | 元件 | text → `component` | 同上 |
| to | 到哪裡 | text → `to_location` | 同上 |
| where | 哪裡 | text → `where_location`（僅控制移動） | 同上 |

尺寸：`min-width: 80px; max-width: 110px`；標籤字級 `10px`、置中。

#### Slot block（參數，有 TMU）

依動作類型插入的順序：

**一般移動 GENERAL_MOVE**

```
使用手 | 從哪裡 | A1 | B1 | G | 目標物 | 元件 | A2 | B2 | P | 到哪裡 | A3
```

**控制移動 CONTROLLED_MOVE**

```
使用手 | 從哪裡 | A1 | B1 | G | 目標物 | 元件 | M | 到哪裡 | X | I | 哪裡 | A3
```

---

## 3. SlotBlock 視覺規範（可直接移植的 color map）

每個 slot 是小卡片：頂部色帶標題（parameter_code + slot_key）、中間摘要 + TMU、右上角清除鈕（hover 才顯示）。

```css
/* 行為 */
.slot-block {
  min-width: 72px; max-width: 120px;
  border: 2px solid var(--slot-border);
  border-radius: 6px;
  background: var(--slot-bg);
  cursor: pointer;
}
.slot-block--empty { border-style: dashed; }
.slot-block--filled { border-style: solid; }
.slot-block:hover:not(.slot-block--disabled) {
  box-shadow: 0 2px 8px rgba(0,0,0,.15);
  transform: translateY(-1px);
}
```

### 3.1 參數色票

| parameter_code | bg | border | text | 語意 |
|----------------|----|--------|------|------|
| **A** | `#e8f4fd` | `#4a9fd5` | `#2c6b9e` | 伸手距離系 |
| **B** | `#f0f0f0` | `#999` | `#555` | 身體/眼部動作 |
| **G** | `#e8fbe8` | `#4aaf4a` | `#2d7a2d` | 抓取 |
| **P** | `#fff3e0` | `#f5a623` | `#b87314` | 放置 |
| **M** | `#f3e5f5` | `#9c27b0` | `#6a1b7a` | 控制移動動詞 |
| **X** | `#fce4ec` | `#e53935` | `#b71c1c` | 製程時間 |
| **I** | `#e0f2f1` | `#009688` | `#00695c` | 校正 |

### 3.2 NL / AI badge（疊在 slot 下方）

| 關鍵字 | class | 樣式 |
|--------|-------|------|
| 含「推斷」 | `badge-inferred` | 綠底 `#e1f3d8` / `#67c23a` |
| 含「預設」 | `badge-default` | 橘底 `#fdf6ec` / `#e6a23c` |
| 含「待確認」 | `badge-pending` | 紅底 `#fef0f0` / `#f56c6c` |

字級約 `9px`，絕對定位在 slot 下方中央。

---

## 4. SlotModal — 點擊 Slot 後的參數編輯

`el-dialog`：一般 `520px`；A 參數因視覺距離選擇器改 `820px`。標題：`{slot_key} — {display_name_zh}`。

### 4.1 各參數控制策略

| Code | 互動 | selections 結構重點 | TMU 規則（前端摘要） |
|------|------|---------------------|----------------------|
| **A** | 伸手距離視覺（`ADistanceSelector`）+ 手轉角度 + 腳步（A3 無後兩者） | `reach_distance` / `hand_degree` / `foot_step` | `max(三者 tmu)` |
| **B** | 單選 dropdown，選完**自動確認**關閉 | `option` | `tmu_value`（不可重複） |
| **G / I** | 單選 +「動作次數」後按確認 | `option` + 可選 `repeat_count` | `tmu × repeat` |
| **P** | 基礎動作 + 最多 2 個 modifiers；`P_INSERT`↔`P_SNAP_FIT` 互斥 | `base_action` + `modifiers[]` | `(base + Σ mods) × repeat` |
| **M** | 動詞 + 手轉/腳步 +「動詞次數」 | `verb` (+ optional hand/foot) | `max(verb×r, hand, foot)` |
| **X** | 製程選項；可有 `fixed_seconds` | `x_option` | 秒→TMU≈`sec/0.036`，再 × repeat |

可重複參數（G/P/M/X/I）在區塊摘要顯示 `推×16` 這類 `×N` 標記。

### 4.2 確認/清除

- 「確認」→ 寫回 `slotSelections[slot_key]` → 觸發 `calculatePreview`
- 「清除」→ 刪除該 slot 選擇
- 空 slot 以虛線邊框呈現，點擊再開 modal

---

## 5. 參數與資料模型（移植必須對齊）

### 5.1 ContextFields（無 TMU，只組句）

```ts
interface ContextFields {
  from_location: string
  target_object: string
  component: string
  to_location: string
  where_location: string  // Controlled only
}
```

### 5.2 SlotSelectionInput（送給後端計算）

```ts
interface SlotSelectionInput {
  slot_key: string          // A1, B1, G, A2, ...
  parameter_code: string    // A, B, G, P, M, X, I
  selections: Record<string, unknown>
}
```

### 5.3 CalculateRowRequest / Response

| 請求欄位 | 說明 |
|----------|------|
| `action_type` | `GENERAL_MOVE` / `CONTROLLED_MOVE` |
| `hand_type` | `left` / `right` / `both` |
| `slot_selections` | 見上 |
| `frequency` | ≥1 |
| `is_simo` | SIMO 標記 |
| `context_fields` | 可選 |
| `show_hand_in_sentence` | 是否把「左/右手」寫入語句 |

| 回應欄位 | 說明 |
|----------|------|
| `base_tmu` | Σ slot TMU |
| `effective_tmu` | × frequency |
| `effective_seconds` | × 0.036 |
| `total_contribution_tmu/seconds` | SIMO 規則下對合計的貢獻 |
| `slot_details[]` | 各 slot 的 `tmu` + `sentence` 片段 |
| `system_generated_sentence_zh` | 系統組句 |

常數：**1 TMU = 0.036 秒**。

### 5.4 模型切換遷移規則（UX 邏輯）

切換 `GENERAL_MOVE` ↔ `CONTROLLED_MOVE` 時：

- **保留**：A1 / B1 / G / A3 與大部分 context
- **刪除**：對方獨有 slots（GM: A2/B2/P；CM: M/X/I）
- 切到 GM：清 `where_location`；B2 預設「眼部動作」；若有 `to_location` 可推斷 P=放；A2 標「待確認」

---

## 6. 區塊 B — 動作列表（MiCompositionTable）

### 6.1 Toolbar

- 左：搜尋語句 +「共 N 筆」
- 右（無選取）：全表合計 TMU / 秒
- 右（有選取）：`已選 n 筆 · TMU/s` + WI 名稱（選填）+ **「加入 WI」** 主按鈕

### 6.2 表格互動

| 能力 | 行為 |
|------|------|
| 勾選 | 多選 → 組成 WI |
| 拖放排序 | 左側 handle；dragging / drop-target 高亮 |
| SIMO 開關 | 列級；影響合計貢獻 |
| 頻率編輯 | 列級 number |
| 編輯 | 回填編輯器（更新模式，按鈕變「更新動作」） |
| 再做一份 / 重工 | `rework`：以該列為底複製到編輯器 |
| 刪除 | 確認後刪序列 |

表格需要**獨立內部捲動**（`max-height` 綁住 wrapper），避免底下 WI 大綱展開把列表擠不見。

建議列態樣式（移植時保留辨識度）：編輯中列偏暖 `#fdf6ec`；已勾選 `#eff6ff`；拖放目標強調約 `#0ea5e9`。

### 6.3 選取合計

前端本地：`Σ selected.total_contribution_tmu`，秒 = TMU × 0.036。  
「加入 WI」→ `POST /most/mi-statements`（傳入勾選的 sequence ids + 名稱）。若使用者未改過 WI 名稱，可依句首自動建議。

列操作補充：**複製／重工（rework）** = 載入編輯器但不設 `editingRowId`（走新增）；**更新動作**在現況實作常採「存新列＋刪舊列」以重算，同時盡量保留 frequency / SIMO。

---

## 7. 區塊 C — WI 大綱（WiOutline）

- 有 MI statement 才顯示；面板 `max-height: 42vh`，內容內部捲動
- 每個 WI 可展開子動作（`MiStatementItem`，copy-on-write 快照）
- 子動作點擊 → **WiItemInspector**（`el-drawer`，建議 `size="480px"`、右側開）可改 slot／頻率／SIMO／語句，不回寫來源序列
- 支援：子項刪除、子項排序、WI 重新命名、WI 刪除、WI 排序

設計要點：**WI 擁有子項快照**，微調不會污染「動作列表」的來源列，也不會跨 WI 互相污染。

---

## 8. CTA 按鈕樣式語意

| 按鈕 | Element type | 時機 |
|------|--------------|------|
| 新增動作 | `success` | 編輯器無 `editingRowId` |
| 更新動作 | `warning` | 正在編輯既有列 |
| 清空 / 取消編輯 | default | 重置編輯器 |
| 加入 WI | `primary` | 有勾選動作列 |

權限：`canEdit = admin || analyst`；其餘角色唯讀（disabled）。

---

## 9. 建議元件拆分（移植時照此邊界）

| 元件 | 職責 |
|------|------|
| `MostWorkbenchPage` | 狀態、載入、計算/儲存 orchestration |
| `NlDraftInput` | NL → draft apply |
| `SequenceSummaryBar` | 唯讀結果條 |
| `SequenceSlotBuilder` | 交錯 context + slots 排版 |
| `SlotBlock` | 色塊與摘要 |
| `SlotModal` + `ADistanceSelector` | 參數細節編輯 |
| `MiCompositionTable` | 動作列 CRUD / 選擇 / SIMO / 拖放 |
| `WiOutline` | WI 樹狀大綱 |
| `WiItemInspector` | Drawer 編輯子動作 |

---

## 10. 關鍵 API（工作台本頁）

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/most/dictionary/workbench-options` | 模型與 slots/options |
| POST | `/api/most/calculate-row` | 即時預覽計算 |
| POST/GET/PATCH/DELETE | `/api/most/sequences` | 動作列 |
| POST/GET/PATCH/DELETE | `/api/most/mi-statements` | WI（MI 語句） |
| PUT/DELETE | `/api/most/mi-statements/:id/items/...` | WI 子項編輯/刪除/排序 |
| POST | `/api/most/nl-draft` | 自然語言草稿 |

完整型別見 `apps/web/src/types/most.ts`，客戶端見 `apps/web/src/api/most.ts`。

---

## 11. 附註：Workbench V3（非側欄預設）

路由 `/most-workbench-v3` 另有三子 tab（動作子模組 → WI Pool → 作業流程），並支援跨 tab「送入」pending 狀態。  
側欄「MOST 工作台」目前綁的是本文描述的 **v2.1 單欄工作台**；若要套用「層級化模板」請另開 V3 文件，不要與本頁混用同一套 layout。

---

## 12. 移植檢查清單

- [ ] Slot 色票與空/滿（dashed/solid）狀態
- [ ] GM / CM 兩種流水線順序與 context 交錯
- [ ] A 參數 `max()`、P 參數 modifier 互斥、G/P/M/X/I 可 `repeat_count`
- [ ] 預覽條欄位順序與 CT=TMU×0.036
- [ ] 動作列多選 → 加入 WI；WI 子項 copy-on-write
- [ ] 編輯器「新增 / 更新」雙模式視覺差異（success / warning）
- [ ] Section 白底 + `#e4e7ed` + `8px` 與主區 `#f5f7fa`
