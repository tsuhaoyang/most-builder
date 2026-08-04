# 前端資料流設計規格（Frontend Data Flow：DTO / State）

**文件類型：** 前端資料流 / 狀態設計規格
**版本：** 0.1 — 草案
**建立日期：** 2026-06-17
**前提：** 後端 cycle DTO 契約已鎖並有 OpenAPI（[schemas/v2/most.py](../../src/ddm_v2/api/routes/v2/calculate.py)、`POST /api/v2/minimost/calculate`）。
**關聯：** [system-architecture-v2-spec.md](./system-architecture-v2-spec.md)（D3 後端唯一權威 / D4 React+TS）、[data-model-and-storage-spec.md](./data-model-and-storage-spec.md)、[minimost-sequence-model-core-logic-spec.md](../core-logic/minimost-sequence-model-core-logic-spec.md)
**範圍：** 定義前端「資料怎麼流、狀態怎麼放」；**不**寫 React 元件實作。UX 權威＝[frontend-ux-spec.md](frontend-ux-spec.md)＋ADR-021/022；`html_con/` 僅為封存原型。

---

## 1. 原則

| # | 原則 | 來由 |
|---|------|------|
| F1 | **後端唯一權威；前端不自算 TMU** | D3。前端送 cycle → API 回權威 TMU/breakdown |
| F2 | **型別由 OpenAPI 生成**（openapi-typescript） | 不手寫 DTO，杜絕前後端型別漂移 |
| F3 | **server state 與 client(編輯中) state 分離** | server state 用 TanStack Query；編輯中表單用本地 store |
| F4 | **穩定 id 從前端就生成** | wi_row.id 用 client uuid v4，存檔前即穩定 → level 標註不丟 |
| F5 | **slot_inputs 以 code 參照** | 與 rule-set 版本綁定；顯示文字另由 rule-set options 提供 |

---

## 2. 契約面（前端消費的 API/型別）

```
OpenAPI（後端 /openapi.json）
   └─ openapi-typescript → src/shared/api/types.ts（自動生成，勿手改）
```

已有端點：
| 端點 | 用途 |
|------|------|
| `POST /api/v2/minimost/calculate` | cycle DTO → `{seq,total_tmu,total_seconds,tech_line,breakdown[]}` |
| `POST /api/v2/level/validate` | level rows → `{valid,issues[]}` |
| `POST /api/v2/level/build-output` | → LB 合約 |

**⚠️ #3 揭露的後端缺口（P1 必補，見 §9）：**
- **`GET /api/v2/rule-sets/{code}/options`** — 前端**沒有它就無法 render 下拉**（需要 G/P/M/X/I/B 的 code+label 與 A/M 帶的顯示文字）。calculate 只算數、不給選項清單。
- **敘事（METHOD 句）** — 需 WI 列的 vocab（物/從/到/手）＋ cycle slots，屬「WI 列層級」，calculate（純 cycle）不含。需 row 層級 narrative 端點/欄位。

---

## 3. 前端狀態樹（client state model）

```
WorkbenchState
├─ meta: { worksheetId, processVersionId, status, ruleSetCode }   ← server 載入
├─ ruleSetOptions: RuleSetOptions                                  ← server（§2 缺口端點）快取
├─ vocab: { object[], from[], to[], tool[], hand[] }              ← server 快取（MasterDataProvider）
├─ rows: WiRowState[]                                              ← 編輯中（本地），對應 server wi_rows
│    └─ WiRowState
│         ├─ id: uuid               ← 前端生成、穩定（F4）
│         ├─ seqNo, subActivity, keyParts, hand
│         ├─ vocab: { objectId, fromId, toId, toolId }
│         ├─ frequency, simoGroupId, provenance
│         ├─ cycle: CycleDraft       ← slot 輸入（= CycleIn 形狀）
│         ├─ calc: { totalTmu, totalSeconds, techLine, breakdown[], status: 'idle|calculating|stale|error', errorCode? }
│         └─ narrativeZh?            ← server 回（不前端組，F1 精神延伸）
└─ level: LevelEntryState[]          ← 由 rows 同步派生，FK keyed by wiRowId（§7）
```

- **CycleDraft ≡ CycleIn**（seq + a0/b1/g2 + (a3|m3)/(b4|x4)/(p5|i5) + a6）。前端表單直接編輯這個物件，送 calculate。

---

## 4. 資料流：編輯一條 cycle（核心迴圈）

```
使用者改 slot（下拉/距離）
   → 更新本地 CycleDraft
   → calc.status = 'stale'
   → debounce 300ms
   → POST /minimost/calculate (CycleDraft)
        ├─ 200 → 存 breakdown/total，calc.status='idle'，逐格顯示 TMU
        └─ 422 {code} → calc.status='error'，把 code 對到該 slot 的 inline 提示（§8）
```

- **F1**：畫面顯示的 TMU 一律來自 API 回應；本地不算。
- debounce 期間顯示上一筆值 +「計算中」微標（stale）。
- 下拉式填寫，變更頻率低 → debounce 300ms 體感即時、零漂移（架構 Q-A）。

## 5. GM↔CM 切換

```
切 seq：
  保留 a0/b1/g2/a6
  reset slot3/4/5 → 新模型的空 slot（GM: a3/b4/p5 ；CM: m3/x4/i5）
  清掉另一模型的欄位（避免送出殘留；雖然後端轉換器只取相關 slot，但持久化要乾淨）
  立即重算
```

## 6. 動態表單（由 rule-set options 驅動）

| slot | UI | 資料來源 |
|------|----|---------|
| A（伸手/手度/腳步） | 3 個下拉，各選帶（顯示「≤20 公分」等） | ruleSetOptions.aBands[component] |
| B | 單選下拉（預設 b_none） | ruleSetOptions.b |
| G | 動作下拉 + 條件式「修飾」下拉（requires_modifier 時才出現） | ruleSetOptions.g |
| P（GM） | base 下拉 + 附加多選(≤2) + 條件式「精度」勾（選對準才出現） | ruleSetOptions.pBases/pAddons |
| M（CM） | 可重複「分量列」：動詞下拉 + 依 pricing_kind 顯示距離/角度/圈數 | ruleSetOptions.mVerbs/... |
| X（CM） | 選項下拉 + seconds 模式才顯示秒數輸入 | ruleSetOptions.x |
| I（CM） | 單選下拉 | ruleSetOptions.i |

- 「單選後其餘反灰、可改選」＝純視覺層次，不鎖點擊（操作規格做法 B）。
- 敘事主數據（物/從/到/手）下拉 ← vocab（§3），嵌在 slot 流程裡（取得段前、放置/移動前）。

## 7. Level 同步（不清空既有標註）

```
自工時表同步（rows 變動時）：
  for each wiRow:
     若 level[wiRowId] 不存在 → 新增（raw_seconds=cycle.totalSeconds, coefficient=1, 其餘空）
     若已存在 → 只更新 description/ct（保留 main/sub/cub/nb/level 標註）   ← 需求6「不清空」
  for level entry 其 wiRowId 已不在 rows → 標記 orphan（提示移除，不自動刪）
驗證：POST /level/validate → issues 對應到列高亮（R1–R9）
```

- 關鍵：level 以 **wiRowId（穩定）** 為鍵 → 改 MOST 內容不丟邏輯標註（F4）。
- `second = raw_seconds × coefficient` 在後端 GENERATED；前端只顯示。難度係數只在此乘一次（E6）。

## 8. 錯誤處理（code → UI）

API 422 `{code,message}` → 對映到具體欄位 inline 提示：

| code | 對應 UI |
|------|---------|
| `A_NEGATIVE` | 該 A 分量紅框 |
| `G_UNKNOWN`/`B_UNKNOWN`/… | 該 slot「選項失效，請重選」 |
| `P_TOO_MANY_ADDONS`/`P_DUP_ADDON` | P 附加區提示 |
| `SLOT_CROSS_MODEL` | 不應發生（前端切換已清欄）→ 視為 bug 上報 |
| Level `R3_ORPHAN`/`R2_REDEFINE`/`R6_NB_VS_CUB`/… | 對應列/欄高亮 + §catalog 說明 |

## 9. 暫存 / 發布 / 另存新檔（對映 API，data-model §2.9）

| 動作 | 前端行為 | 端點（P1 補） |
|------|---------|--------------|
| 暫存 (autosave) | debounce 存 draft worksheet（rows+cycles+level） | `PUT /worksheets/{id}` |
| 發布 | 狀態→published（manager+），凍結唯讀 | `POST /worksheets/{id}/publish` |
| 另存新檔 | clone 整個聚合成新 draft（前端導向新 version） | `POST /worksheets/{id}/clone` |

## 10. 技術選型（建議）

- **server state**：TanStack Query（worksheet/rule-set/vocab 載入、save mutation、calculate）。
- **編輯中 state**：輕量 store（Zustand）或 useReducer；CycleDraft/level 為受控狀態。
- **型別**：openapi-typescript 生成；calculate/validate 的 request/response 全程型別安全。
- **debounce**：calculate 以 row 為單位 debounce（300ms）。

---

## 11. 待補（含 #3 揭露的後端缺口）

| # | 項目 | 屬 |
|---|------|----|
| FE-1 | **`GET /rule-sets/{code}/options`**（下拉用 code+label+帶顯示） | P1 後端（阻擋前端 render） |
| FE-2 | **敘事生成**（row 層級：vocab+cycle+labels → 句）後端唯一產 | P1/P2 後端 |
| FE-3 | worksheet/level 持久化端點（PUT/publish/clone） | P1 後端 |
| FE-4 | B 選用指引（C4）、SIMO 群組指派 UX（C5） | 待 IE（level §14） |
| FE-5 | vocab 取得端點（MasterDataProvider）對映 | P1/P3 |

---

*本規格定義前端資料流與狀態；待 FE-1～FE-3 後端端點補齊後，即可進入 P2 React SPA 實作。*
