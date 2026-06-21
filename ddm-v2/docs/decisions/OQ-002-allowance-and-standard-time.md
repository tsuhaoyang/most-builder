# OQ-002 — Allowance、Normal Time 與 Standard Time

**Status:** 🟡 討論中  
**提出日期:** 2026-04-17  
**Owner:** IE Lead  
**相關規格:** `docs/specs/system-architecture-spec.md` §3.3  
**核心算法參考:** `docs/specs/MOST-core-algorithm-spec.md` §9

---

## 問題定義

1. 系統是否要計算 allowance？
2. API 是否要同時輸出 Normal Time 與 Standard Time？
3. 舊資料匯入時，歷史標準工時應如何保存與解釋？

---

## 為什麼重要

這個議題若不先定清楚，後面會出現語義混亂：

- IE 輸入的 MOST 計算結果到底是 Normal Time 還是 Standard Time？
- 舊資料匯入帶進來的 `standard time` 是否可直接當作 MOST 計算結果？
- 報表、SOP、模擬輸出到底應該顯示哪種時間？

---

## 先釐清兩種時間的差別

### Normal Time

由 MOST 依據標準序列與 index value 直接算出的時間。  
它代表：

- 100% performance level
- 不含 allowance
- 是 MOST 核心算法的直接結果

公式：

```text
Normal Time = Σ(每個 method step 的 TMU) × 0.036 秒
```

### Standard Time

在 Normal Time 上再加入 allowance 後的時間。  
它通常用於：

- 生產規劃
- 排線 / 排人
- 目標設定
- 工時標準管理

公式：

```text
Standard Time = Normal Time × (1 + Allowance%)
```

簡單理解：

- **Normal Time**：MOST 算法原始值
- **Standard Time**：現場管理實際採用的工時值

---

## 使用者補充的業務情境

使用者提出 Phase 1 至少要支援兩種情境：

### 情境 A：新產品排工序（偏模擬 / from scratch）

- IE 從零開始輸入 MOST 資料
- 一步一步建立 method step
- 系統應能產出可追溯的 MiniMOST normal time

### 情境 B：既有產品調整 / 舊資料匯入

- 可能已有歷史資料
- 舊資料可能帶有既有的 standard time
- 匯入後需要將舊資料拆解為可管理的 MOST 結構

這代表系統不能只處理「純新建」，還要處理「歷史資料轉換與對照」。

---

## 已討論方案

### 方案 A：只輸出 Normal Time

- 優點：
  - 最純粹，完全符合 MOST 核心算法語義
  - Phase 1 複雜度最低
- 缺點：
  - 舊資料中的 standard time 無處安放
  - 現場管理者可能看不懂或無法直接採用

### 方案 B：同時輸出 Normal Time 與 Standard Time

- 若 allowance 已定義，則系統同時計算 standard time
- 若 allowance 尚未定義，standard time 可為空值或僅保留匯入值
- 優點：
  - 與現場溝通較容易
  - 兼容新建與舊資料匯入
- 缺點：
  - allowance 規則若未定，容易產生混用

### 方案 C：先把 Standard Time 視為參考欄位，不先自動推導

- Phase 1 只保證 MiniMOST normal time 正確
- 若舊資料匯入已有 historical standard time，先作為參考值保存
- 等 allowance 政策定案後再決定是否由系統自動計算
- 優點：
  - 風險最低
  - 可避免把不明來源的 standard time 假裝成 MOST 算出來的結果

---

## 本輪討論紀錄

### 2026-04-17 使用者回答

1. 會有兩種主要使用情境：
   - 新產品排工序（模擬）
   - 既有產品調整（可能有歷史資料）
2. 資料來源可能為：
   - 從零建置
   - 舊資料匯入
3. 舊資料匯入時，可能會帶有既有量測出的 standard time
4. 使用者目前尚不完全理解 Normal Time / Standard Time 的差異
5. 未來 line-balance 會是另一個微服務，不一定由本系統直接執行模擬

### 2026-04-17 架構審查意見

這裡最重要的風險是：

> **歷史標準工時（historical standard time）不能直接等同於 MiniMOST 算出來的 normal time。**

因為舊資料中的 standard time 可能：

- 已含 allowance
- 使用不同量測方法
- 不是依 MiniMOST 建模得出
- 來自人工量測或其他舊系統

若不區分欄位，未來會嚴重污染核心數據語義。

---

## 目前建議

### 建議 1：Phase 1 先把 `normal_time` 作為唯一可信的算法輸出

也就是：

- MiniMOST engine 計算出的結果 = `normal_time`
- 這個欄位必須保持嚴格、可追溯、不可混淆

### 建議 2：舊資料匯入時，保留 `reference_standard_time`

也就是舊資料中帶入的工時，不要直接覆蓋算法輸出，而應該以獨立欄位存在，例如：

- `reference_standard_time_seconds`
- `reference_time_source`
- `reference_time_note`

### 建議 3：暫不在 Phase 1 強制導入 allowance 計算

在 allowance 尚未被 IE 正式定義前，不建議系統自動從 normal time 推導 standard time。  
否則容易出現「系統算出的 standard time」與「工廠既有標準工時」不一致的情況。

---

## 已回答問題

### Q1. 工廠目前是否已有正式 allowance 百分比？

**使用者回答：** 若 allowance 可理解為類似 buffer，則希望由 backstage management platform 設置，不要寫死。  
**歸檔結論：** Phase 1 不應把 allowance 規則硬編碼；應保留可配置空間。

### Q2. allowance 是依 site、依產品、依工序，還是全廠統一？

**使用者回答：** 都要能支援，系統需足夠彈性，讓 IE 可依工序、site、產品或全廠統一調整。  
**歸檔結論：** allowance 規則未來需支援多層級覆寫，不宜只做單一全域值。

### Q3. 匯入舊資料時，是否要求 IE 必須補齊 MOST step 拆解，還是允許只有參考工時？

**使用者回答：** 已於 `OQ-001` 回答，方向是「保留 + 轉換」，非直接拒收。  
**引用：** 見 `OQ-001-most-system-selection.md`

### Q4. 未來傳給 line-balance service 的時間欄位，要使用 `normal_time`、`reference_standard_time`，還是後續正式推導出的 `standard_time`？

**使用者回答：** 希望 line-balance 使用 IE 真實填入 MOST 系統後得到的時間，因為 MOST 應代表產品工序的詳細動作拆解與時間。  
**歸檔解讀：** 使用者目前更傾向由「正式 MOST 結構化結果」作為下游輸入，而不是直接用歷史匯入參考值。

## 仍需說明的問題

### Q5. 匯入的歷史 `standard time` 是否有來源標記？是否可知道其 allowance 是否已包含？

**狀態：** 使用者表示暫時不理解問題，需要舉例。  

**舉例說明：**

假設匯入一筆舊資料：

- 產品：`SKU-001`
- 步驟：`鎖 4 顆螺絲`
- 時間：`35 秒`

這 35 秒可能有三種完全不同的意思：

1. **Normal Time**：純 MOST / 量測原始值，不含 allowance
2. **Standard Time**：已含 allowance，例如 30 秒 normal time + 15% allowance = 34.5 秒
3. **Observed Time / Legacy Time**：舊系統或人工量測時間，未必符合 MOST

若不記錄來源，未來系統就無法知道這 35 秒到底能不能和 MiniMOST 算出的時間直接比較。

## 待續討論問題

### Q6. 匯入歷史時間時，是否必須要求填寫 `time_source`？例如：`legacy_standard_time`、`observed_time`、`imported_normal_time`

**使用者回答：** 希望記錄 `normal_time` 並計入 allowance，之後由使用者自行決定是否輸出含 allowance 的資料。  
**架構解讀：** 使用者更偏好把「計算基底」與「輸出選擇」分開處理，而不是在匯入時就把時間來源切得非常細。  
**審查提醒：** 這個回答仍未完全取代 `time_source` 的需求。因為即使系統內部記錄 normal time，匯入進來的舊資料若不是 normal time，仍然需要知道來源。故此題**部分已答，但未完全關閉**。

### Q7. 若 historical time 的來源不明，是否只允許當參考欄位，不得進入正式比較或下游服務？

**使用者回答：** 好。  
**歸檔結論：** 來源不明的 historical time 僅作參考，不得直接進入正式比較或下游服務。

### Q8. allowance 規則若支援多層級覆寫，優先順序應為何？例如：工序 > SKU > site > 全廠

**使用者回答：** 較傾向讓使用者選擇「by 工序」或「by SKU」即可。若選 by 工序，則每一工序各自填 allowance；若選 by SKU，則該 SKU 全部參考同一 allowance。  
**歸檔結論：** 使用者目前偏好 Phase 1 只支援較簡單的 allowance 策略，不需要一開始就做全層級繼承樹。

## 已補充回答

### Q9. 匯入舊資料時，若來源不是 normal time，系統如何判斷或要求使用者標示它是 `reference_standard_time` 還是其他類型？

**使用者回答：** 由使用者勾選，且粒度是 **SKU level**。也就是說，整份資料要嘛屬於 `reference`，要嘛屬於 `normal`；若要細到每個工序，則應改用系統重新建立資料。  
**歸檔結論：** Phase 1 不做 step-level time source 標註；time source 由使用者在 SKU / 整份版本層級勾選。

### Q10. 「記錄 normal_time 並計入 allowance」在資料模型上是指存兩個欄位，還是只存 normal_time、輸出時動態套用？

**使用者回答：** 存兩個欄位；若 allowance 有值，就代表有 allowance。  
**歸檔結論：** 資料模型需顯式保存：

- `normal_time`
- `standard_time`
- allowance 相關欄位

而不是僅在輸出時臨時計算。

### Q11. allowance 有值時，是否還要另外保存 `allowance_percent`？

**使用者回答：** allowance 的值本身就應該是 percent。  
**歸檔結論：** 資料模型中的 allowance 欄位應直接以百分比語義保存，例如 `allowance_percent`，避免再額外定義語意重複的欄位。

## 已補充回答

### Q12. SKU level 的 time source 勾選，是否允許後續被改寫？若允許，是否需保留變更紀錄？

**使用者回答：** 不可改。對 user 來說，若勾錯就刪除後重新上傳，再重新勾選正確的 time source。  
**歸檔結論：** Phase 1 的 SKU-level time source 一旦建立即不可改寫；若設定錯誤，應透過刪除重建處理，而非事後修改語義欄位。

---

## 目前暫定結論

> Phase 1 先明確區分 `normal_time` 與 `reference_standard_time`。  
> `normal_time` 來自 MiniMOST 算法，`reference_standard_time` 來自舊資料匯入或歷史工時。  
> allowance 與系統自動推導 `standard_time` 的規則，暫不視為已定案。

---

## Resolution

**Decision:**  
- Phase 1 以 MiniMOST `normal_time` 為核心算法輸出
- 匯入的歷史標準工時需獨立保存，不得直接覆蓋算法輸出  
**Allowance % agreed:** 尚未定案  
**Scope (global / per-project / per-operation):** 尚未定案  
**Date:** 2026-04-17  
**Decided by:** 使用者 + 架構討論（待正式確認）  
**Implementation impact:**  
- schema 需區分 `normal_time` 與 `reference_standard_time`
- 匯入流程需保留來源與註解
- Phase 1 可先不自動計算 `standard_time`
- SKU-level 的 time source 需設為建立後不可修改
