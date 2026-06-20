# OQ-004 — 多使用者併發、工作區與發布模型

**Status:** 🟡 討論中  
**提出日期:** 2026-04-17  
**Owner:** DevOps / Tech Lead  
**相關規格:** `docs/specs/system-architecture-spec.md` §7.4  
**依賴:** OQ-003（PostgreSQL 與整體架構策略）

---

## 問題定義

多使用者情境下，系統要如何避免互相覆寫？  
不同 site 的產品標準、使用者工作區、與後台管理資料之間應如何隔離？

---

## 為什麼重要

目前真正的核心問題，不只是技術上的 locking，而是**資料的所有權與發布模式**：

- 使用者是共編同一份標準，還是各自有私人 workspace？
- 已發布的標準能否直接修改？
- 不同 site 對同一個 product / SKU 的標準是共用還是各自獨立？

如果這些規則沒有先定，單純談 optimistic locking 或 pessimistic locking 都不夠。

---

## 使用者本輪回答

### 2026-04-17 使用者回答

1. 此問題非常重要，系統會有不少使用者
2. 使用情境分成兩層：
   - **user stage**：計算、展示、檔案匯出等使用者操作
   - **backstage management**：manager / senior user 管理資料
3. 一般使用者應有自己的空間，不應互相影響
4. 但後台管理的資料會影響 user stage
5. 以 site 作為管理邏輯的一部分是合理的
6. 使用者補充範例：
   - A 廠區已發布 `001` 產品
   - A 廠區使用者只能基於該產品進行更改
   - B 廠區若沒有 `001` 產品，則需用新增

---

## 架構審查意見

這段回答非常重要，因為它顯示：

> **你真正想要的不是多人同時共編同一份文件，而是「私人工作區 + 版本發布 + site 隔離」模型。**

這會大幅改變系統設計方向。

較合理的模型不是：

- 大家同時修改同一份 live document

而是：

- 使用者在自己的 workspace 工作
- 後台管理者維護可發布的標準版本
- 已發布的標準應被視為穩定快照

---

## 建議的資料/流程模型

### 1. Published Standard（已發布標準）

- 維度：`site + product + sku + version`
- 為正式對外使用的標準
- 應視為不可直接 in-place 修改

### 2. User Workspace（使用者工作區）

- 每位使用者擁有自己的 workspace / 草稿
- 可基於某個 published standard 建立工作副本
- 工作副本之間互不干擾

### 3. Backstage Draft（後台草稿）

- 由 manager / senior user 維護共享資料與標準草稿
- 草稿經審核後發布成新版本
- 發布後才影響後續 user stage

---

## 對你提供案例的解讀

### 案例：A 廠區已發布 001 產品

這裡我建議不要理解成「A 廠區 user 只能直接修改已發布文件」。  
更安全的做法應是：

- A site 已有 `001`
- A site user 可基於已發布版本建立**新草稿 / 新版本**
- 不直接改寫已發布版本

### 案例：B 廠區沒有 001 產品

這裡仍有兩種可能，需要後續定義：

1. **完全新增**
2. **從其他 site 或 global template 複製再調整**

第二種通常比較實用，但必須明確記錄來源關係。

---

## 已討論方案

### 方案 A：所有人共編同一份 site 文件

- 優點：
  - 概念簡單
- 缺點：
  - 高衝突
  - 難 audit
  - 容易破壞已發布標準

### 方案 B：私人 workspace + 發布版本（推薦）

- 使用者各自工作
- 後台維護共享資料與發布機制
- 已發布內容不直接改寫
- 優點：
  - 大幅降低衝突
  - 更符合標準文件治理
  - 易於做 audit 與 version history

### 方案 C：site 完全隔離，各自維護所有資料

- 優點：
  - 邏輯清楚
- 缺點：
  - 容易重複建置
  - 難共享通用知識與標準

---

## 鎖定與一致性策略建議

若採用「私人 workspace + 發布版本」模型，我建議：

### 對 user workspace

- 以使用者私人資料為主
- 不需要重型共享鎖
- 只需一般 version / save 保護即可

### 對 backstage shared draft / master data

- 採 **optimistic locking**
- 共享草稿或共享主檔被修改時，使用版本號避免覆寫

### 對 published standard

- 發布後視為 immutable snapshot
- 若要變更，建立新版本，而不是直接修改舊版本

---

## 已回答問題

### Q1. A site 與 B site 是否允許共享同一個 global product / SKU template？

**使用者回答：** 已於資料庫文件回應。  
**歸檔引用：** 以 `OQ-003-database-migration.md` 為主，不在本文件重複追問。

### Q2. workspace 是否有草稿 / 提交 / 審核 / 發布流程？

**使用者回答：** 是，需要這功能。  
**歸檔結論：** workspace 不是單純暫存，而是需要具備正式流程狀態。

### Q3. 是否需要顯示某標準目前被哪位 manager 編輯中？

**使用者回答：** 需要。  
**歸檔結論：** 後台共享編輯需具備 presence / lock hint / editing indicator。

### Q4. 後台管理會管理哪些共享資料？工具、設備、site policy、allowance、custom element 是否都在其中？

**使用者回答：** 已在其他文件回答。  
**歸檔引用：**
- 版本與主檔範圍：見 `OQ-003-database-migration.md`
- allowance：見 `OQ-002-allowance-and-standard-time.md`
- custom element：見 `OQ-005-custom-tool-elements.md`

## 已補充回答

### Q5. 「更改當前版本」是指可直接改 published version，還是可直接改當前 draft version？

**使用者回答：** 當前版本；若修改 published version，則等同於要建立新版本。  
**歸檔結論：** 此前衝突已收斂。可直接修改的是當前工作版本 / 草稿版本；published version 若要變更，必須建立新版本。

### Q6. 若允許直接修改當前版本，line-balance 或其他下游系統如何知道引用的是修改前還是修改後資料？

**使用者回答：** 要有版本 tag。  
**歸檔結論：** 下游系統不得直接追 live draft，應透過版本 tag 綁定來源版本。

### Q7. presence 只是顯示「誰正在編輯」，還是要阻止其他 manager 同時進入相同編輯頁？

**使用者回答：** 要阻止，並顯示誰在編輯，讓使用者知道要聯絡誰。  
**歸檔結論：** 後台共享編輯採「阻止衝突 + 顯示佔用者」模式，而非單純提示。

## 已補充回答

### Q8. 鎖定粒度是「整份標準文件」還是「某個版本草稿」？

**使用者回答：** 鎖 by SKU version。  

**補充說明：**

- **整份標準文件鎖定**：只要有人在編 `SKU-001`，這份文件所有版本相關編輯都被鎖住
- **某個版本草稿鎖定**：只鎖住正在編輯的那個版本草稿，例如 `SKU-001 v3 draft`，不影響其他版本

**歸檔結論：** 鎖定粒度採 `SKU version`，也就是以單一 SKU 的單一版本資料作為鎖定單位。

### Q9. 若編輯者中斷離線，鎖怎麼釋放？是否需要 TTL 或管理員強制解除？

**使用者回答：** 需要 TTL；假設在編輯模式下 1 天內沒有更新，則退出編輯並恢復成修改前。  
**使用者決策：** 採用架構建議。  
**歸檔結論：** 需要自動逾時解鎖；TTL 目前暫定為 1 天未更新即退出編輯。TTL 到期時：

- 解除鎖
- 保留已儲存的草稿內容
- 只丟棄未儲存的變更

不自動回滾整份已儲存的草稿版本。

## 待續討論問題

- [ ] TTL 到期後，是否仍需管理員手動強制解除鎖的功能，作為例外處理？

---

## 目前暫定結論

> 本系統較適合採用「私人 workspace + 後台草稿 + 已發布版本」模型，而不是多人共編同一份 live 文件。  
> site 應是核心維度之一。  
> 已發布版本不可直接修改；若需變更，必須建立新版本。  
> 可直接修改的是當前工作版本 / 草稿版本，且需保留修改者資訊與版本標記。

---

## Resolution

**Decision:**  
- user stage 與 backstage management 分離
- 使用者應有自己的 workspace
- 已確認需要 presence / 編輯中提示
- published version 不可直接修改；修改需建立新版本
- 當前工作版本可編輯，且需保留修改紀錄  
**Locking strategy:** 對 shared draft / master data 採 optimistic locking，並對共享編輯頁提供阻止式佔用提示；鎖定粒度為 `SKU version`；published data 以版本 tag 供下游引用  
**Interim safety (filelock):** 舊 JSON store 已存在，但 Phase 1 目標將轉向 PostgreSQL  
**Date:** 2026-04-17  
**Decided by:** 使用者 + 架構討論（待正式確認）  
**Implementation impact:**  
- 需設計 workspace、draft、published version 三層資料模型
- 需釐清 site 與 product / SKU 的關係
- 需為共享後台資料導入 version control / optimistic locking
- 需實作 TTL 自動解鎖，且 TTL 到期不回滾已儲存資料
