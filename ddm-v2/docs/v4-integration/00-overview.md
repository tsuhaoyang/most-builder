# v4 → v2 整合審查：總覽

> **狀態**：**評估中／未排程／不得作為實作依據**（2026-09-21 進版控時標定）。審查本身已完成（2026-09-04，
> 五份子文件 01–05 皆已產出），但「要不要整合、怎麼整合」尚未裁決、也未排程；本目錄的內容是評估素材，
> 不是現行架構或已核可的計畫。要動手前需另行決策（ADR）與排程。
> **性質**：唯讀審查。本輪只讀 v4 原始碼與產出審查文件，不修改 v4，也不改 v2 程式碼。
> **目的**：把 v4（另一位 IE 從早期系統延伸、獨自開發的 minimost 系統）的功能，
> 以 v2（ddm-v2 現行系統，架構健全）的正確軟體架構收編整合。整合實作為後續另議。

## 名詞基準（本審查一律採用）

- **v2** = `ddm-v2/` 現行系統（本 repo）。技術棧：FastAPI + SQLAlchemy 2.0 async + PostgreSQL +
  React 19 + TypeScript。MOST engine 為單一權威、有黃金值鎖定（GM=28／CM=29）。
  （版號上 ddm-v2 實為第三版，但溝通一律以「v2」指這套現行系統。）
- **v4** = `~/workspace/most-builder/minimost_level/minimost/`。另一位 IE 延伸早期系統獨自開發。
  技術棧：FastAPI + SQLAlchemy **1.4** + SQLite(dev)/PostgreSQL(prod) + **Vue 3** + TypeScript + Element Plus。
  IE 熟領域、不熟軟體架構——故 v4 可能有領域價值但架構未必嚴謹。

## 審查方法（重要，貫穿所有子文件）

1. **查程式，不只信文件**。v4 的 `docs/` 由 IE 撰寫，實測與 code 有明顯落差
   （例：`docs/most-workbench.md` 只描述 MOST 工作台，但 code 另有 ESOP／LineBalance／
   LineLayout／Level System 的完整實作）。每個結論都必須回到 v4 實際 source 驗證，
   並在子文件標注「證據來源：檔案:行號」。
2. **MOST sequence 限制是重中之重**（見 `02-most-sequence-comparison.md`）。v2 的 TMU 計算是
   單一權威且有黃金值鎖定，整合不得污染其正確性。v4 有 `calculation.py` 與 `calculation_v2.py`
   兩套計算、且有 migration `58a3d1cca6f1_cm_rename_a2_to_a3_return_slot`（CM slot A2→A3 重命名），
   必須逐格對照 slot 組成、aggregation_rule、SIMO、A_return、TMU 公式是否與 v2 一致。
3. **從大功能對照到細節**：先功能矩陣，再逐領域深入。

## v4 實際程式碼結構（實測，非文件宣稱）

後端 `apps/api/app/`：
- `models/`：`most.py`(25KB)、`esop.py`(8.5KB)、`analysis.py`、`dictionary.py`、`audit.py`、`user.py`
- `services/`：`calculation.py` + `calculation_v2.py`（兩套）、`most_workbench.py`、`nl_draft_parser.py`(43KB)、
  `line_balance.py`(19KB)、`esop_generator.py`(19KB)、`esop_export.py`(16KB)、`dictionary_import.py`、
  `normalization.py`、`sentence_generation.py`、`default_dictionary_seed.py`、`report_export.py`、`storage.py`
- `api/routes/`：`most.py`(44KB)、`most_workbench_v3.py`(45KB)、`esop.py`(35KB)、`dictionaries.py`(32KB)、
  `level_system.py`(25KB)、`wi_set_builder.py`(18KB)、`line_layout.py`(17KB)、`line_balance.py`(10KB)、
  `analysis.py`(18KB)、`reports.py`、`users.py`、`auth.py`
- `alembic/versions/`：18 個 migration（含 `58a3d1cca6f1_cm_rename_a2_to_a3_return_slot`、
  `f1a2b3c4d5e7_add_level_system_tables`、`b8c9d0e1f2a3_add_esop_tables`、
  `e5f6a7b8c9d0_add_line_balance_layout_scenarios` 等）
- `tests/`：15 個測試檔（`test_most_workbench.py` 25KB、`test_level_system.py` 25KB、
  `test_line_balance.py` 37KB、`test_esop.py` 41KB、`test_calculation.py`、`test_nl_draft_parser.py` 等）

前端 `apps/web/`：Vue 3 + Element Plus（待深入）。

## 子文件索引

| 文件 | 範圍 | 狀態 |
|---|---|---|
| `00-overview.md` | 本文件：基準、方法、v4 結構 | ✅ 完成 |
| `01-feature-matrix.md` | 大功能對照矩陣（v4 有／v2 有／差異／整合影響） | ✅ 完成 |
| `02-most-sequence-comparison.md` | **MOST sequence 限制逐格對照**（重點） | ✅ 完成 |
| `03-data-model-and-dictionary.md` | 資料模型 + AI 字典差異 | ✅ 完成 |
| `04-api-comparison.md` | API 對照 | ✅ 完成 |
| `05-integration-assessment.md` | 整合建議、風險、順序（synthesis） | ✅ 完成（Line Balance 定位已依使用者裁決修正，見下） |
| `06-line-balance-kpi-logic.md` | v4 Line Balance／KPI **計算邏輯整理**（僅供參考，不整合進 v2） | ✅ 完成 |
| `07-level-system-ux-gap.md` | v4↔v2 Level System **UX 差距對照**（拖/拉/選/呈現 + 資料關聯） | ✅ 完成 |
| `08-implementation-spec.md` | **整合實作規格**（per-功能域，指導後續 agent） | ✅ 完成（草案 v1） |

## 範圍裁決：Line Balance／KPI 不整合進 v2（使用者裁決 2026-09-04）

**使用者已有另一套專門做 Line Balance 的系統。** 因此 v4 的 Line Balance 求解器與 KPI／
efficiency／balance-rate 計算，**不列為整合進 v2 的功能標的**——只需把其**重要邏輯與計算方式
整理成參考文件**（`06-line-balance-kpi-logic.md`），供該外部 LB 系統對照，不在 v2 重建求解器。

- 受影響範圍（實測）：v4 的 LB／KPI 邏輯集中在 `services/line_balance.py`（KPI/efficiency/
  balance_rate/takt/bottleneck 44 處）與 `routes/line_balance.py`（16 處）。
- 對本審查其他結論的影響：`01`／`05` 原將「Line Balance 求解器」列為 P1／Phase 2 高優先整合標的，
  **此定位已推翻**——降級為「邏輯參考、不整合」。**Line Layout／E-SOP 仍為整合標的**，但其對 LB 的
  依賴改為「依賴使用者的外部 LB 系統產出」而非「v2 內建 LB」（見 `05` 修正）。
- 不變的部分：Level System、E-SOP、Line Layout、Case 審批流、MOST sequence 對照與治理不變式
  （I1 TMU 單一權威、I2 黃金值）等結論不受此裁決影響。

## 初步觀察（假設，待各子文件以 code 證據確認或推翻）

- v4 是**功能範圍更廣**的獨立系統：ESOP builder、Line Balance/Layout 完整實作可能是 v2 尚無或僅有雛形的。
- v4 與 v2 **技術棧不相容**（SQLAlchemy 1.4 vs 2.0 async；Vue vs React）→ 整合是「功能與邏輯移植」，
  不是「code 直接搬」。
- v4 內部自身有版本演進（`calculation_v2.py`、`most_workbench_v3.py`、CM slot 重命名 migration）→
  對照時要以 v4 的**現行有效**實作為準，不是被取代的舊版。
- v4 與 v2 共享血緣：都有 ddm_v2 SQL dump、相同的 `minimost_ai_dictionary_v1`。需釐清分歧點。
