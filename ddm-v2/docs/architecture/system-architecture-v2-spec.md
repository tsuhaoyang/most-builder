# 目標系統架構規格 v2（定點重建 / Target Architecture）

**文件類型：** 系統架構規格（取代舊版系統架構規格；舊版已隨 legacy 一併移除）
**版本：** 0.1 — 草案（架構分岔已定，第二層決策見 §12）
**建立日期：** 2026-06-17
**作者：** 架構師（20y SWE + IE 視角）
**前提：** 核心邏輯已確認並以 89 個測試護住（見 [sequence](../core-logic/minimost-sequence-model-core-logic-spec.md) / [level](../core-logic/level-system-core-logic-spec.md) / [test-catalog](../core-logic/core-logic-validation-test-catalog.md)）。本文件談「如何把核心邏輯做成可信的系統」。

---

## 1. 已鎖定的架構決策（2026-06-17，User）

| # | 決策 | 選定 |
|---|------|------|
| D1 | 建置策略 | **定點重建**：保留基礎設施（FastAPI/PostgreSQL/Docker/Alembic/RBAC）與「對的」minimost rule-set 表；移除教科書 ×10 引擎；以確認的核心邏輯重建 WI Workbench 與 Level System |
| D2 | v1 範圍 | 核心（WI Workbench + Level System + 詞彙庫 + Rule-set 管理）**＋ SOP 版本與簽核 ＋ 跨系統數據對齊 ＋ RBAC 多角色/多廠區**；**移除 simulation/line-balance**（LB 為獨立 project） |
| D3 | 核心邏輯權威 | **規則表＝版本化資料（DB）＋ 後端唯一計算引擎**；前端取權威值經 API；WI 快照所用 rule-set 版本 |
| D4 | 前端 | **React + TypeScript SPA**，以 `wi-workbench.html` 為 UX 藍本 |

> 這四項共同消滅現況最大病灶：**三套互相矛盾的核心定義**（教科書 / 工廠 Excel / 程式），與 **兩個並存的計算引擎**（`most_calculation_service` ×10 vs `minimost_service`）。

---

## 2. 架構總覽

```
┌─────────────────────────────────────────────────────────────┐
│  React + TypeScript SPA（UX 藍本：wi-workbench）              │
│   ├─ WI Workbench：工時表編制（sequence model 填格）          │
│   ├─ Level System：main/sub/cub/nb 標註 + 即時驗證           │
│   ├─ 主數據/詞彙庫管理、Rule-set 管理（IE）                   │
│   └─ SOP 版本/簽核、廠區/使用者（RBAC）                       │
└───────────────┬─────────────────────────────────────────────┘
                │ REST/JSON（OpenAPI → 型別安全 client）
┌───────────────▼─────────────────────────────────────────────┐
│  FastAPI 後端（hexagonal：routes → services → repositories） │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ ★ 唯一核心引擎 most_engine/（由 validator 升級而來）   │  │
│   │   - sequence calc（讀 rule-set 資料，非硬編）          │  │
│   │   - level validator（R1–R9）                          │  │
│   │   - LB 輸出合約 builder                                │  │
│   └──────────────────────────────────────────────────────┘  │
│   services：wi / level / rule_set / vocab / sop / auth / code │
│   repositories：SQLAlchemy async                              │
└───────────────┬─────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────┐
│  PostgreSQL（Alembic）                                        │
│   rule_set（版本化 MOST 表）· wi/worksheet/cycle（快照版本）  │
│   level_entry（深度階層）· work_vocab · sop_version           │
│   public_entity_code/BOM · users/sites/roles                 │
└──────────────────────────────────────────────────────────────┘
                │ 輸出合約（JSON：nodes/precedence/cub/number）
                ▼
        Line Balance（你的獨立 project；本系統不含其演算法）
```

---

## 3. 核心引擎：單一權威來源設計（D3 的落實，本架構心臟）

問題根因＝核心邏輯有三套且會漂移。對策分三層：

### 3.1 規則為「資料」，不是「程式碼」
所有可調的 MOST 表（A 伸手/手度/腳步帶、B、G、P base/addon、M 階梯/旋轉、X、I、`system_tmu_multiplier`、各種限制）存為 **版本化 rule-set 資料**（已存在 `minimost_*` 表，沿用並補齊）。
- IE 在「Rule-set 管理」頁編輯 → 產生**新版本**（`draft → published → retired`）。
- 規則改動＝資料改動 + 新版本，**不改程式、不重部署**。

### 3.2 演算法只實作一次（後端）
唯一計算引擎 `most_engine/`（由 [minimost_sequence_validator.py](../../scripts/core_logic/minimost_sequence_validator.py) 升級：把硬編常數換成「讀 rule-set 資料」）。
- 端點：`POST /api/v2/minimost/calculate`（cycle + rule_set_version → 每格 TMU + 合計 + tech_line）。
- `POST /api/v2/level/validate`（rows → R1–R9 issues）。
- `POST /api/v2/level/build-output`（→ LB 合約 JSON）。

### 3.3 快照與回放
每筆 WI cycle 持久化時記錄 **`rule_set_version_id`**；之後重算用當時版本 → **數值可回放、可稽核**。

### 3.4 漂移防線（CI）
核心邏輯驗證（[scripts/core_logic/](../../scripts/core_logic/)）的黃金/反例測試，CI 上對「引擎」跑（不再只是獨立 validator）。黃金值（GM28/CM29、教學 7 範例、image5 反例）是規格的一部分，任何引擎或 rule-set 改動都必須維持綠燈。

> **前端即時性 vs 單一引擎**：見 §12 Q-A（建議：前端以 debounce 呼叫 calculate API 取權威值；若 UX 需更即時，再開「以同一組黃金向量鎖定的 TS 鏡像引擎」，CI 對 TS 與 Python 同跑黃金集）。

---

## 4. 資料模型（目標，重點表）

> 沿用既有 `minimost_*`、`work_vocab_items`、`users/sites`、`public_entity_codes`；**重建** level 模型；**移除** simulation 表。

| 領域 | 表（沿用 ✅ / 重建 🔁 / 新增 ➕ / 移除 ❌） | 重點 |
|------|------|------|
| Rule-set | ✅ `minimost_rule_sets` 及 A/B/G/P/M/X/I 子表 | 版本化；補齊 B（1205 值 0/10/32/42）、A 三分量帶 |
| WI 工時表 | 🔁 `worksheets` / `wi_rows`（方法步）/ `cycles`（GM/CM 七格 + params_snapshot + **rule_set_version_id**） | 一列一方法步；Freq、SIMO group |
| Level System | 🔁 `level_entries`：content、second(=raw×coef)、number/number_count、ascription、level（支援 `~`/`/`）、countersignature、order；連 `wi_row_id` | 對齊教學檔案深度模型（R1–R9）；巢狀>2 待 C2 |
| 詞彙庫 | ✅ `work_vocab_items`（object/target/destination/hand…） | 敘事主數據 |
| SOP | ✅/🔁 `sop_versions` + 狀態流轉/簽核 | 與 worksheet 綁定版本快照 |
| 跨系統 | ✅ `public_entity_codes` / `code_prefix_registry` / BOM | external_code 對齊 |
| RBAC | ✅ `users` / `sites` / roles（IE/manager/admin） | 多廠區 |
| 計算引擎 | ❌ 移除 `most_calculation_service`（×10）、`GENERAL_MOVE/CONTROLLED_MOVE` schema、`simulation_*` | |

---

## 5. API 介面（目標骨幹）

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/v2/minimost/calculate` | POST | ★唯一計算：cycle(GM/CM) + rule_set → slot TMU/合計 |
| `/api/v2/minimost/rule-sets` | GET/POST/PUT | rule-set 版本 CRUD（IE） |
| `/api/v2/worksheets/{id}` | GET/PUT | WI 工時表存讀（含 cycles 快照） |
| `/api/v2/level/{worksheet_id}` | GET/PUT | Level 標註存讀（自 WI 同步） |
| `/api/v2/level/validate` | POST | R1–R9 驗證 → issues |
| `/api/v2/level/build-output` | POST | → LB 合約 JSON |
| `/api/v2/most/work-vocab/*` | CRUD | 詞彙庫 |
| `/api/v2/sop/versions/*` | CRUD | SOP 版本/狀態 |
| `/api/v2/masterdata/export\|import`、`/code-prefix-registry` | — | 跨系統數據對齊 |
| `/api/v2/auth/*`、`/users*`、`/sites*` | — | RBAC/廠區 |

---

## 6. 前端架構（React + TS）

- UX 現況＝[v2-workbench.html](../html_con/v2-workbench.html)（多分頁 SPA：WI 編制 / Level System / 主數據 / Rule-set / SOP / 匯出）。
- 型別安全：openapi-typescript 由後端 OpenAPI 產生 client。
- 結構：`features/wi-workbench`、`features/level-system`、`features/rule-set`、`features/vocab`、`features/sop`、`shared/api`、`shared/most-types`。
- 計算：呼叫 `/minimost/calculate` 取權威 TMU（debounce）；句子敘事在前端組裝（規則來自 API 的 rule-set 資料）。

---

## 7. 既有資產 處置清單（Salvage Plan）

| 既有 | 處置 | 理由 |
|------|------|------|
| FastAPI/PG/Docker/Alembic | **保留** | 基礎設施健全 |
| `models/minimost.py` + seed | **保留並補齊** | 方向正確（工廠表）；補 B 1205 值、A 三分量 |
| `scripts/core_logic/*` validators | **升級為引擎 + 留作 CI 測試** | 已是規格的可執行版 |
| RBAC（users/sites/roles 三角色） | **保留簡化** | D2 保留多廠區 |
| `sop_*`、`public_entity_codes`、`work_vocab_items` | **保留** | D2 範圍內 |
| `most_calculation_service.py`（×10） | **移除** | 教科書錯誤口徑 |
| `GENERAL_MOVE/CONTROLLED_MOVE` schema | **移除** | 改 GM/CM |
| `level_service.py` + `level_system_entries` | **重建** | 舊扁平模型 → 教學檔案深度模型 |
| `simulation_service.py` + 表 | **移除** | LB 獨立 project |
| legacy 靜態 UI（validation_shell 等） | **移除** | 改 React SPA |

---

## 8. 對 Line Balance 的輸出合約（系統邊界）

LB 為獨立 project。本系統輸出（`/level/build-output`）：
```json
{
  "nodes": [{"content","second","ascription","level","countersignature","order","number","number_count"}],
  "precedence_edges": [{"from","to"}],
  "cub_groups": {"cub1": ["B","C"]},
  "number_constraints": {"nb1": {"limit": 1, "members": ["G","H"]}}
}
```
規則（需求清單）：MOST 語句更動時 Level 不清空（區分上傳/暫存）；必出 LB + 限制線；標出超限列。

### 8.1 匯出 tab（Tab⑥）需求（User 2026-06-18）

1. **先預覽 WI**：以 **1128 式 Excel 呈現**（SUB/Key Parts/HAND/METHOD/SEQUENCE A B G…/Freq/SIMO/TMU）。
2. 使用者選輸出：
   - **(a) Excel**：WI 1128 式 .xlsx。
   - **(b) LB 系統格式**：
     - **① .csv**：先把資料轉成 LB 可用的 CSV。
     - **② 呼叫 LB API**：先做**接口（adapter）**，LB 的 **request model 由 User 後續提供**再對映填入。
3. LB 為獨立 project；本系統只負責**產出/送出**，不含 LB 演算法。

---

## 9. 分階段建置計畫（建議）

| 階段 | 內容 | 出場標準 |
|------|------|----------|
| **P0 引擎化** | validator → `most_engine`（讀 rule-set 資料）；補齊 rule-set（B/A 三分量）；CI 接黃金集 | 89 測試對引擎全綠 |
| **P1 核心 API+DB** | calculate / rule-set / worksheet / level（含重建 level schema） | API 對黃金集回正確值 |
| **P2 WI Workbench SPA** | React 重建 ① WI 編制 + ③ Level，串 API | 能完成一份 WI + Level 並驗證 |
| **P3 周邊** | 詞彙庫管理、SOP 版本/簽核、RBAC/廠區、跨系統數據對齊 | D2 範圍齊備 |
| **P4 輸出與收尾** | LB 輸出合約、匯入匯出、移除舊引擎/UI/simulation | 舊資產清理完成 |

---

## 10. 非功能需求（重點）

- **可稽核**：cycle 快照 rule-set 版本；SOP 版本化；審計記錄沿用。
- **部署**：on-prem 內網（截圖為 `10.134.60.16`）；Docker 單機/小規模並發。
- **可測**：核心引擎 100% 由黃金/反例集鎖定；API 層 functional test。

---

## 11. 風險

| 風險 | 對策 |
|------|------|
| 前端優化計算與後端漂移 | 後端唯一權威；若加 TS 鏡像則同跑黃金集（§12 Q-A） |
| rule-set 改動破壞既有 WI 數值 | cycle 快照版本 + 回放；rule-set 改版需重驗黃金集 |
| Level 深度巢狀>2 未定 | 先支援扁平 + 單層巢狀，巢狀>2 待 IE（C2） |
| 既有資料遷移 | 舊 level/most 數據是否保留→§12 Q-D |

---

## 12. 第二層待決問題（Open Questions）

| # | 問題 | 決議（2026-06-17） |
|---|------|------|
| **Q-A** | 前端 TMU 即時性 | ✅ **純後端 debounce 計算**（單一引擎、零漂移）；UX 不夠再考慮 TS 鏡像 |
| **Q-B** | 部署/租戶 | 建議單庫多廠區（site 隔離）、on-prem；待確認（低風險） |
| **Q-C** | Rule-set 治理 | ✅ **IE 編 draft、manager+ publish；WI 凍結在當時 rule-set 版本（可回放）** |
| **Q-D** | 既有資料 | ✅ **全新起算——現有資料可刪（皆測試階段）**；v2 以全新 migration 起新 schema |
| **Q-E** | SOP 簽核範圍 | ✅ **輕量版本快照（draft/published）起步**，日後再長多狀態簽核 |
| **Q-F** | Level 巢狀>2（C2）＋ 機台/人力分攤（C1）＋ B 選用規則（C4） | ⏳ 待 IE（level §14 清單） |

---

*§1 四大架構決策 ＋ §12 第二層（Q-A/C/D/E）皆已定，僅 Q-B（低風險）與 Q-F（待 IE）未鎖。下一步：進入 **P0 引擎化**。*
