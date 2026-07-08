# F-03b：快照設計與 Apply-Back 規格（可執行功能規格補件）

> **隸屬**：F-03（三層組裝）的架構設計補件 ｜ **日期**：2026-07-08
> **起因**：v3 程式碼查證（verification-code-audit.md §2.1）確認了快照設計的實際實作；本文件將「Snapshot vs Live Reference」決策明文化，並定義 apply-back 在 v2 的強化規格。
> **效力**：本文件是 F-03 §2.4（apply-back）的實作層設計依據；任何 v2 實作必須符合本文件的驗收條件。

---

## 1. 架構決策：快照（Snapshot）而非活連結（Live Reference）

### 1.1 兩種方案對比

**Live Reference（FK 活連結）**

```
WITemplate id:2  ←──FK──  ProcessRouteItem (Process A)
                 ←──FK──  ProcessRouteItem (Process B)
```

行為：WITemplate id:2 內容一改 → Process A 和 Process B 同時被動到，使用者完全不知情。

**Snapshot（建立時複製內容）**

```
WITemplate id:2  ──建立時複製──→  ProcessRouteItem (snapshot @ t1)  ← Process A 永遠不變
WITemplate id:2  ──建立時複製──→  ProcessRouteItem (snapshot @ t2)  ← Process B 永遠不變
```

行為：WITemplate id:2 日後修改 → 現有 Process A、B 完全不受影響；新建的流程才拿到新版。

### 1.2 裁決：v3 採快照，v2 沿用並強化

**v3 的實作**（`models/most.py` 程式碼證據）：

```python
class ProcessRouteItem(Base):
    source_wi_template_id = Column(String(36), nullable=True)
    # ↑ 不是 ForeignKey！是 provenance 字串（記錄「當初從哪來的」，不是活連結）

class WISetProjectItem(Base):
    source_wi_id = Column(String(36), nullable=True)
    # ↑ 同上。雖然注釋說「WITemplate」，實際儲存的是 MiStatement.id（一代收集器）

class MostMiStatementItem(Base):
    source_sequence_id = Column(String(36), nullable=True)
    # ↑ 注釋："Provenance only — NOT a live link"
```

所有跨實體引用均為 **nullable 字串**，**無任何真實 SQLAlchemy ForeignKey**。  
這是刻意設計：IE 明確要「改實例不動範本」，以快照為基礎。

**v2 沿用快照設計**，以 `motion_modules` 的深拷貝列（L1/L2）與 `worksheet` 的實體化列（L3）承載同一語意；`provenance_module_id` 欄記錄出處，不建 FK 約束。

---

## 2. Provenance 欄位規格（v2）

每層快照建立時，必須記錄來源 ID，用於追溯與「來源已更新」提示。

| v2 資料表 | Provenance 欄位 | 記錄來源 | 是否 FK 約束 |
|---|---|---|---|
| `motion_module_items`（L2 子快照） | `source_module_id` | L1 ActionModule 的 `motion_modules.id` | ❌ nullable，軟參考 |
| `worksheet_rows`（L3 實體化） | `source_module_id` | L1/L2 `motion_modules.id` | ❌ nullable，軟參考 |

**來源刪除處理**：若 provenance ID 找不到對應資源，不刪快照——僅在 UI 顯示「來源已失聯」badge；既有流程完整保留。

---

## 3. Apply-Back 流程規格（v2 強化版）

### 3.1 v3 的行為（不移植）

```
ProcessRouteItem（已微調）→ 點「套用回 WI 模板」→ WITemplate 被破壞性覆寫
```

缺陷：無版本歷史、無影響範圍提示、無權限守衛（驗證碼審計 C-9 已確認 DISC-09 裁決不移植）。

### 3.2 v2 的 Apply-Back 流程

Apply-Back 在 v2 語意＝「**從流程實例發布組件新版本**」，不是覆寫：

```
Step 1: 使用者在 L3 流程中微調某 WI 實例
Step 2: 點「套用為新版本」
Step 3: 系統顯示影響範圍確認對話框（見 §3.3）
Step 4: 確認後，來源 motion_module 的 current_version + 1（舊版本仍可讀）
Step 5: 流程項的 provenance_module_id 更新指向新版本
Step 6: 其他引用同一模組的流程項顯示「來源有新版本可用」badge
```

### 3.3 影響範圍確認對話框（必要）

觸發條件：使用者點擊「套用為新版本」。  
顯示內容：

```
「此動作模組（[模組名稱]）目前已被引用於：
  - 流程 A（版本 2026-06-01）
  - 流程 B（版本 2026-07-03）
  共 N 個流程

套用後：
  ✓ 現有流程繼續使用快照，不受影響
  ✓ 模組版本升為 v{n+1}（舊版本保留可查）
  ✓ 上述流程會顯示「有新版本可用」提示

確認發布新版本？」
```

**行為約束**：
- 對話框非選配——無論引用數為零或一百，都必須顯示
- 使用者可選「另存為全新模組」，不影響原模組的任何版本
- 若引用數為 0，文字改為「此模組目前未被其他流程引用」

### 3.4 版本不可變原則（繼承自 DISC-09 裁決）

- 每個 `motion_module` 版本一旦 publish，`rows`/`slots`/`totals` 不可修改
- Apply-back 只能產生新版本（`current_version + 1`），不能修改現有版本
- 舊版本永遠可讀（`GET /api/v2/motion-modules/{id}/versions`）

---

## 4. ProcessRoute AddWI API 規格（v3 bug 修正）

### 4.1 v3 的 bug

```javascript
// ProcessWorkspace.vue L79-86 — 每加一個 WI 就重建整個 ProcessRoute
for (const wiId of wiIds) {
    const allIds = [...existingIds, wiId]
    const res = await mostApi.createProcessRoute({ wi_template_ids: allIds })  // ← 每次 CREATE 新的
    route = res.data
}
```

問題：加 3 個 WI 會建出 3 個 ProcessRoute 資料列，只有最後一個有效；前兩個是孤兒資料。

### 4.2 v2 的修正設計

使用增量 API，不重建：

```
POST /api/v2/process-routes/{id}/items
Body: { "module_ids": ["id1", "id2", "id3"] }
Response: 更新後的 ProcessRoute（含所有既有 + 新增 items）
```

後端實作：在現有 ProcessRoute 上 `INSERT` 新 `ProcessRouteItem` 列，**不觸動既有列**。  
若 `process_route_id` 不存在→ 404；若模組已退役→ 409。

---

## 5. 前端 WILibraryItem.source 死欄位（v2 清理）

### 5.1 問題發現

v3 TypeScript 型別定義：

```typescript
export interface WILibraryItem {
    id: string
    source: string    // ← 這個欄位
    wi_code: string | null
    // ...
}
```

v3 後端 `WILibraryItemResponse`（`wi_set_builder.py`）：

```python
class WILibraryItemResponse(BaseModel):
    id: str
    wi_code: str | None = None
    wi_name: str
    # source 欄位根本不在這裡！
```

後端從未回傳 `source`，前端 `WILibraryItem.source` 是死欄位（永遠為 undefined）。

### 5.2 `source` 欄位的真實位置

```python
class ActionModuleTemplate(Base):
    source = Column(String(20), nullable=False, default="manual")
    # 值：'manual'（手動建立）、'ai'（NL Draft 建立）、'copied'（clone）
```

`source` 屬於 **ActionModuleTemplate**，記錄「這個模組是怎麼被建立的」，與 WILibraryItem 無關。

**v2 清理要求**：v2 的 API 型別定義不得包含 `WILibraryItem.source`；ActionModule 的 `source` 欄位正常實作，含義不變。

---

## 6. 驗收條件

| 條件 | 可驗證標準 |
|---|---|
| 快照不自動同步 | Given L3 流程建立後，修改來源 L2 WI 範本。When 查看該流程。Then 流程項內容不變，顯示「來源有新版本可用」badge。 |
| Apply-back 影響範圍提示 | Given 某 L1 模組被 3 個流程引用。When IE 點「套用為新版本」。Then 對話框列出這 3 個流程，並說明現有流程不受影響。 |
| Apply-back 版本不可變 | Given apply-back 成功。Then 模組舊版本 `GET /versions` 仍可讀，新版本 `current_version + 1`。 |
| 非 owner 無法 apply-back | Given 非模組 owner 且非 admin 的使用者。When 嘗試 apply-back。Then 403。 |
| ProcessRoute 增量加入 | Given 已有 3 筆 items 的 ProcessRoute。When POST /items 加入 2 個新 WI。Then 原 3 筆不變，新增 2 筆，共 5 筆；DB 無孤兒 ProcessRoute。 |
| 來源失聯不刪快照 | Given 流程項的 provenance 來源 module 已刪除。When 查看流程。Then 流程項完整顯示，標示「來源已失聯」，不報錯。 |
| WILibraryItem 無 source 欄 | Given API `GET /wi-library` 回應。Then response body 無 `source` 欄位；前端型別定義同步不含此欄。 |
