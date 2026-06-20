# OQ-003 — 持久化策略：Phase 1 是否直接採 PostgreSQL

**Status:** 🟡 討論中  
**提出日期:** 2026-04-17  
**Owner:** DevOps / Tech Lead  
**相關規格:** `docs/specs/system-architecture-spec.md` §7.1, §6 Phase 3

---

## 問題定義

Phase 1 是否應直接放棄 JSON store，改採 PostgreSQL？  
若未來有 line-balance 與 MVA 等其他系統，現在應該拆成 microservice，還是先維持單一服務？

---

## 為什麼重要

這個決策會直接影響：

- Phase 1 的開發範圍
- schema 設計方式
- multi-site 資料隔離設計
- audit / history 的保存方式
- 未來是否能平滑銜接其他系統

---

## 先修正現況認知

目前程式中的 JSON store **不是完全沒有保護**。  
實際上 `JsonStore` 已經做了：

- `fcntl.flock(...)` 檔案鎖
- `tempfile + os.replace(...)` 的 atomic write

可參考：

- `src/ddm_v2/repositories/store.py`

因此目前真正的問題不是「完全沒有 lock」，而是：

1. 仍然是**單檔 JSON**，查詢能力有限
2. `app.state.store` 是**單例 in-memory store**
3. 未來若有多 worker / 多 process / 多 instance，會有 stale state 與一致性風險
4. 對 multi-site / audit / versioning 的支援仍遠遠不夠

---

## 使用者本輪回答

### 2026-04-17 使用者回答

1. **決定使用 PostgreSQL**
2. 預期使用者規模約 **50 人**
3. 系統先部署在**單一伺服器**
4. 但會有**不同 site 的使用者**
5. 不同 site 會有不同 IE 規則與習慣
6. 歷史資料與操作歷程都需要被記錄
7. Phase 1 希望至少包含：
   - 正確的 MOST 計算
   - 資料庫設計與實作
   - 後台管理
8. 部署方式傾向 PostgreSQL + Docker Compose
9. 此系統是整體系統的一部分，未來還有 line-balance 與 MVA 等子系統

---

## 已討論方案

### 方案 A：先維持 JSON，後續再遷移 PostgreSQL

- 優點：
  - Phase 1 實作較快
  - 遷移工作可延後
- 缺點：
  - 現在就得處理 50 users、multi-site、history
  - 很快又要做第二次架構轉換

### 方案 B：Phase 1 直接採 PostgreSQL，但先不拆微服務

- 優點：
  - 資料模型可一次到位
  - 能較早支援 audit、versioning、multi-site
  - 避免 JSON → DB 的中間遷移成本
- 缺點：
  - Phase 1 複雜度上升
  - 需要更嚴謹的 schema 與 migration 流程

### 方案 C：Phase 1 就拆成多個 microservice

- 優點：
  - 邊界看似清楚
- 缺點：
  - 在 domain 尚未穩定前過早拆分
  - 會同時增加：
    - service boundary 設計成本
    - auth / routing / deployment 複雜度
    - 跨服務一致性問題

---

## 架構審查意見

基於目前的需求，我的明確建議是：

> **Phase 1 直接採 PostgreSQL，但不要急著拆 microservice。**

更具體地說：

- **資料層**：直接改用 PostgreSQL
- **應用層**：維持單一服務（modular monolith）
- **整合層**：為未來 line-balance / MVA 預留 API 與資料邊界

原因如下：

1. 你現在的核心挑戰不是 service 拆分，而是：
   - MiniMOST 算法正確性
   - Product / SKU / Site / Version 的資料模型
   - 後台管理
   - 歷史與發布機制
2. 在這些 domain 還沒穩定前，過早拆服務只會把不確定性放大
3. line-balance 本來就已是另一個專案，因此目前更適合用 API integration，而不是現在就把本專案拆碎

---

## 目前建議

### 建議 1：Phase 1 架構採「Modular Monolith + PostgreSQL」

也就是：

- 單一 deployable service
- 清楚的 module 邊界
- 單一 PostgreSQL 資料庫
- 後續再依成熟度拆出獨立服務

### 建議 2：資料模型要從一開始就帶 `site`

因為使用者已明確說明：

- 不同 site 有不同規則
- 不同 site 有不同習慣

所以不能把 site 當成單純顯示欄位，而應是主要資料維度之一。

### 建議 3：history 不能只做成一般 log

由於你明確要求「every history should be record」，Phase 1 的 schema 應至少考慮：

- audit log
- versioned standard document
- publish history
- 可能的 imported source trace

---

## 已回答問題

### Q1. Site 之間的資料是完全隔離，還是共用部分 master data？

**使用者回答：** 可在 backstage management platform 提供由 manager 將某 site 的資料同步到另一 site 的機制。  
**歸檔解讀：** 不是完全隔離，也不是天然全域共用；更接近「各 site 各自管理，但可透過受控同步複製」。

### Q2. Product / SKU 是全域主檔，還是 site-local 主檔？

**使用者回答：** 延續上一題。  
**歸檔解讀：** 目前較接近「各 site 擁有自己的標準版本，但後台可進行跨 site 同步」。詳細粒度請以 `OQ-001` 為主，不在本文件重複追問。  
**引用：** 見 `OQ-001-most-system-selection.md`

### Q3. 歷史紀錄要做到「一般 audit log」還是「可回溯版本快照」？

**使用者回答：** 發布後的版本要可回朔；編輯過程不需要完整回朔。  
**歸檔結論：** 至少要有 published version snapshot；草稿編輯過程不一定要 event-sourcing。

### Q4. 後台管理要管理哪些主檔？工具、設備、工時規則、site policy 是否都要版本化？

**使用者回答：** 簡單一點，先管理版本即可；設備、工具等偏資料面，不一定需要版本化。  
**歸檔結論：** 版本化優先落在「標準文件 / 發布結果」，不是所有主檔一律版本化。

### Q5. 認證登入是否將來要與其他子系統共用？

**使用者回答：** 是。另一個 line-balance 專案已設置 auth-service（OAuth2），未來可串接；現階段未接入前仍需先有本地功能。  
**歸檔結論：** Phase 1 需保留外部 auth 整合介面，但不可依賴其已存在。

## 已補充回答

### Q6. 「跨 site 同步」是單次複製、持續同步，還是發布時手動同步？

**使用者回答：** 發布時手動同步；另外後台可指定某一個版本要同步到哪一個 site。  
**歸檔結論：** 同步是顯式管理行為，不是自動持續同步。

### Q7. 被同步到另一 site 後，是否立即分叉成獨立版本，不再自動回寫來源？

**使用者回答：** 是，要分叉成獨立版本。  
**歸檔結論：** 跨 site 同步後即形成獨立版本線，不自動跟隨來源更新。

### Q8. 既然草稿編輯過程不要求完整回朔，Phase 1 是否只需記錄最後修改者、修改時間與發布快照即可？

**使用者回答：** 是的。  
**歸檔結論：** Phase 1 不需完整 event-sourcing；最後修改資訊 + published snapshot 即可。

## 已補充回答

### Q9. 被同步的單位是整份標準文件、單一 SKU 版本，還是可細到部分工序？

**使用者回答：** 是單一 SKU 版本。使用者理解為：一個產品會有多個 SKU，而每個 SKU 會有多個版本；但每個版本只會有一份資料，因此同步只能同步這一整份資料。  
**歸檔結論：** 跨 site 同步的最小單位為「單一 SKU 的單一版本」，不做部分工序粒度同步。

## 待續討論問題

### Q10. 同步到另一 site 後，是否要保留「來源 site / 來源 SKU version」追溯欄位？

**使用者回答：** 需要。  
**歸檔結論：** 跨 site 同步後的新版本必須保留來源追溯欄位，至少包含來源 site 與來源 SKU version。

---

## 目前暫定結論

> Phase 1 直接採 PostgreSQL，並以 modular monolith 為主，不建議現在就拆成多個 microservice。  
> 微服務邊界應先透過模組與 API 契約保留，待 domain 穩定後再拆。

---

## Resolution

**Decision:**  
- Phase 1 採 PostgreSQL
- Phase 1 不先拆 microservice，先做 modular monolith  
**Target database:** PostgreSQL  
**Migration trigger:** 不採「之後再遷移」，而是 Phase 1 直接上 PostgreSQL  
**Interim safety measure (atomic write):** 已存在於舊 JSON store，但 Phase 1 目標為直接退場  
**Date:** 2026-04-17  
**Decided by:** 使用者 + 架構討論（待正式確認）  
**Implementation impact:**  
- 需重新設計 persistence layer
- 需引入 migration 機制
- schema 需納入 `site`、版本、發布歷程與 audit 能力
