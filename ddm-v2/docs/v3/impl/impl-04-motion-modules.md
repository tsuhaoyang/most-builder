# impl-04：組件庫 motion_modules — WI Pool 的 v2 落地

> **Phase**：P3 ｜ **ADR**：ADR-017 ｜ **概念來源**：v3 WI Pool（MI 語句庫→搜尋→組裝工序表；registry「不可變版本＋使用端快照」模式）。
> **單一真相**：合併既有 `motion_templates`（單 cycle）與 v3 MI 語句（多 cycle）為一個庫；工序表列實體化後即普通 WiRow，工時/Level/LB/匯出全走既有機制。

## 1. Schema（migration `v2_0012_motion_modules`）

```sql
CREATE TABLE motion_modules (
  id uuid PRIMARY KEY,
  site_id uuid NULL REFERENCES sites(id),        -- NULL = 全域
  name_zh text NOT NULL,
  category text NULL,
  keywords text[] NOT NULL DEFAULT '{}',
  scope text NOT NULL CHECK (scope IN ('personal','site','global')),
  owner text NULL,                               -- 員工編號；personal 必填（CHECK）
  status text NOT NULL CHECK (status IN ('draft','standard','retired')) DEFAULT 'draft',
  current_version int NOT NULL DEFAULT 0,        -- 0 = 尚無發布版
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
  CONSTRAINT ck_personal_owner CHECK (scope != 'personal' OR owner IS NOT NULL)
);

CREATE TABLE motion_module_versions (
  id uuid PRIMARY KEY,
  module_id uuid NOT NULL REFERENCES motion_modules(id) ON DELETE CASCADE,
  version_no int NOT NULL,
  rule_set_id uuid NOT NULL REFERENCES rule_sets(id),   -- 快照：發布當下規則版
  rows jsonb NOT NULL,            -- 有序陣列：[{sub_activity, hand, frequency, simo_pair_index?, vocab_refs{...}, cycle: CycleIn}]
  narrative_zh text NULL,         -- 發布時由引擎生成（可重生快取）
  total_tmu numeric NOT NULL, total_seconds numeric NOT NULL,   -- 引擎算（可重生快取）
  published_by text NOT NULL, published_at timestamptz NOT NULL,
  UNIQUE (module_id, version_no)
);

ALTER TABLE wi_rows
  ADD COLUMN source_module_id uuid NULL REFERENCES motion_modules(id) ON DELETE SET NULL,
  ADD COLUMN source_module_version int NULL;   -- provenance；兩欄同 NULL 或同非 NULL（CHECK）
```

- `rows` 是 JSONB（整存整取、不查詢內部——符合 [[database-v2]] 儲存策略）；可檢索文字投影進 `search_documents`（impl-03）。
- 版本列**不可變**：發布後禁 UPDATE（service 層擋 + 無 update endpoint）；修改＝發新版 `current_version+1`。

## 2. 不變量（引擎級保證）

1. **發布即驗證**：publish 時每列 `cycle` 過 `compute_cycle`（用指定 rule_set）——算不過不能發布；`total_tmu/narrative` 由引擎產，**不接受呼叫端提供**。
2. **實體化＝複製、合計走引擎**：查證 C-12 佐證此不變量——v3 的 `wi_set_builder._recalculate_project_totals` 因平行實作合計而**漏排 SIMO**（bug）；v2 實體化後即普通列、合計唯一走 `compute_table`，此類 bug 結構上不可能發生。加入工序表時把 version.rows 展開為 WiRow＋MostCycle（cycle 的 `rule_set_id` 用 **worksheet 當前 rule-set** 重算，不是模組發布版——工序表口徑一致優先；重算結果與模組值不同時回應附 `tmu_drift` 警示欄）。
3. **改快照不回寫**：實體化後的列與模組無同步關係；provenance 僅供追溯與「模組已更新」提示。
4. **SIMO 配對**：rows 內 `simo_pair_index` 指向陣列內另一列；實體化時經 impl-02 E5 正規化成 `simo_group_id`。

## 3. API

| Method | Path | 說明 |
|---|---|---|
| GET | `/api/v2/motion-modules?q=&scope=&category=` | 列表＋檢索（q 走 impl-03 search，`doc_type=motion_module`） |
| POST | `/api/v2/motion-modules` | 建 module（draft, personal 預設） |
| GET | `/api/v2/motion-modules/{id}` | 含 current version 內容 |
| PUT | `/api/v2/motion-modules/{id}` | 改 metadata / draft 草稿內容 |
| POST | `/api/v2/motion-modules/{id}/publish` | 發布新版（引擎驗證＋計值＋投影檢索） |
| POST | `/api/v2/motion-modules/{id}/promote` | personal → site/global（=standard；P5 前限 manager 角色，後續接 ADR-018 審核流） |
| POST | `/api/v2/worksheets/{wid}/rows/from-module` | **實體化**：`{module_id, version_no?}`（預設 current）→ 批次建列，回傳新列＋`tmu_drift` |
| POST | `/api/v2/motion-modules/{id}/versions/from-rows` | **回寫發新版**（對應 v3 apply-back，查證 C-5）：以選定 worksheet 列內容發布 `current_version+1`；owner/approver 限定；版本不可變原則不破壞 |
| GET | `/api/v2/motion-modules/{id}/versions` | 版本歷史 |

錯誤邊界：publish 空 rows→422；實體化 retired module→409；version_no 不存在→404；scope 越權→403。

## 4. motion_templates 轉移（一次性資料 migration，`v2_0011` 內）

1. 每筆 `motion_templates` → `motion_modules`（scope：site_id NULL→global、有值→site；status draft→draft、standard→standard）＋ `motion_module_versions` v1（rows=[單列]，rule_set 用 template 建立時預設版，total 由引擎於 migration 後首次 seed 腳本補算——migration 本身不 import 引擎，值先置 0 並由 `scripts/backfill_module_totals.py` 補，避免 migration 依賴應用程式碼）。
2. 舊表**保留唯讀一個 phase**（雙軌禁止寫入：既有範本 API 轉 410 Gone 指向新 API），下一個 migration（P5 後）drop——分步退役符合 ADR-011。
3. `downgrade()`：刪新表兩張＋wi_rows 兩欄；舊表因未動故可逆。

## 5. 前端工作流（[[frontend-workbench]] 範疇，此處僅定合約）

Workbench 新「組件庫」面板：搜尋（關鍵字→`/api/v2/search`）→ 預覽（narrative＋TMU）→ 多選 → 批次實體化 → 列出現於工序表（含 drift 警示）。「存為組件」：選取工序表 1..n 列 → POST module（rows 由所選列的 slot_inputs 反投影）。

## 6. 測試

1. 單元：publish 驗證（壞 cycle 擋）、不可變版本（update 擋）、實體化展開含 SIMO 正規化、drift 計算。
2. 整合：轉移 migration 前後筆數/值對帳、410 舊 API、可逆實測。
3. Endpoint：全 API 正常＋錯誤邊界各一；RBAC（personal 隔離、promote 權限）。
4. e2e（Playwright）：搜→選→實體化→總 TMU 正確。
