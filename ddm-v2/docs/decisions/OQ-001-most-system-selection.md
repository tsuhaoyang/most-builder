# OQ-001 — MOST 系統範圍：MiniMOST、BasicMOST、MaxiMOST

**Status:** 🟡 討論中  
**提出日期:** 2026-04-17  
**Owner:** IE Lead  
**相關規格:** `docs/specs/system-architecture-spec.md` §3.2  
**核心算法參考:** `docs/specs/MOST-core-algorithm-spec.md` §3, §10

---

## 問題定義

此系統在 Phase 1 應採用哪一種 MOST 系統？  
未來若擴充到其他 MOST 系統，應該以什麼粒度建模？

---

## 為什麼重要

MiniMOST、BasicMOST、MaxiMOST 使用的是**不同的資料卡與索引值規則**。  
若用錯系統，則：

- TMU 計算會失真
- index value 驗證規則會錯
- 舊資料匯入後無法正確解釋
- 後續跨廠區、跨產品比較將失去一致性

目前程式中只有 `seq_type = GENERAL / CONTROLLED`，這只是序列模型形狀，不等於 MOST 系統本身，因此仍缺乏系統層級的語義。

---

## 背景

| 項目 | MiniMOST | BasicMOST | MaxiMOST |
|------|----------|-----------|----------|
| 適用週期 | < 1 分鐘 | 2–30 分鐘 | > 30 分鐘 |
| 詳細程度 | 最高 | 中等 | 最粗 |
| 典型場景 | 短循環、高重複裝配 | 一般製造 / 零售 / 配送 | 維修、重裝配、長工序 |
| Phase 1 需求 | 已確認優先採用 | 暫不實作 | 未來可能需要 |

使用者補充的業務背景如下：

- 這套系統的核心用途，是讓 IE 為**每個產品、每個 SKU** 建立一份公定組裝步驟文件
- 但不同廠區會因工具、設備、人力條件不同而需要不同選項
- 因此業務粒度不能只停在 project，還要考慮 `product / SKU / site`

---

## 已討論方案

### 方案 A：Phase 1 僅實作 MiniMOST

- 先只支援 MiniMOST 計算與驗證
- 架構上保留未來擴充 MaxiMOST 的能力
- 優點：
  - 範圍可控，適合先把核心算法做正確
  - 與既有 legacy MiniMOST 背景一致
  - 可優先支援短循環裝配場景
- 缺點：
  - 未來若要支援 MaxiMOST，資料模型與 UI 必須預先留好擴充點

### 方案 B：Phase 1 同時支援多 MOST 系統

- 一開始就導入 `most_system`
- 每個分析依所選系統套用不同資料卡
- 優點：
  - 模型一次到位
- 缺點：
  - 範圍過大
  - 目前需求尚未清楚到可直接一次做完
  - 會延後 Phase 1 核心交付

---

## 本輪討論紀錄

### 2026-04-17 使用者回答

1. **Phase 1 先實作 MiniMOST，但必須保留未來擴充能力**
2. 此系統不是單純 by project，而是更接近：
   - 產品（Product）
   - SKU
   - 廠區（Site）
3. 不同廠區會有不同的：
   - 工具
   - 設備
   - 人力條件
   - 可設置選項

### 2026-04-17 架構審查意見

目前最合理的方向是：

- **Phase 1 演算法層只實作 MiniMOST**
- 但資料模型與服務邊界必須預留：
  - `site`
  - `product`
  - `sku`
  - 未來 `most_system`

也就是說，**Phase 1 不需要真的把 MaxiMOST 算法做出來，但不能把資料模型寫死成永遠只有 MiniMOST。**

---

## 目前建議

### 建議 1：Phase 1 不導入 step-level `most_system`

在 Phase 1 僅支援 MiniMOST 的前提下，不建議一開始就把 `most_system` 放到每個 step。  
否則 UI、驗證與匯入流程會先被過度複雜化。

### 建議 2：以 `產品 + SKU + 廠區` 作為標準文件的核心辨識維度

較合理的概念應接近：

- Product：產品族 / 型號
- SKU：具體規格
- Site：廠區
- Version：標準文件版本

### 建議 3：未來的 MaxiMOST 應以「策略式擴充」接入

即：

- `MiniMOSTEngine`
- `MaxiMOSTEngine`

未來再由 service layer 或 configuration 決定使用哪種 engine，而不是在 Phase 1 先把所有邏輯混在一起。

---

## 已回答問題

### Q1. 同一個 SKU 在不同 site，是同一份標準的 site override，還是各 site 各自有獨立標準版本？

**使用者回答：** 各 site 各自有獨立標準版本。  
**歸檔結論：** `site` 不是單純 override 條件，而是標準文件的核心維度之一。

### Q2. Site 差異只影響工具 / 設備 / 人力選項，還是會影響步驟本身？

**使用者回答：** 會影響，因此資料模型必須保有足夠彈性；即使有些 site 恰好相同，也不能把系統設計寫死成永遠相同。  
**歸檔結論：** 步驟本身不得假設為全 site 共用。

### Q3. 若未來導入 MaxiMOST，判定規則是依 cycle time、依工序類型，還是由 IE 手動指定？

**使用者回答：** 由 IE 手動指定。  
**歸檔結論：** 未來若支援多 MOST 系統，切換權限與指定入口應由 IE 控制，而不是完全自動推斷。

### Q4. 舊資料若不是 MiniMOST 格式，Phase 1 要拒收、轉換，還是只當參考附件保留？

**使用者回答：** 可保留；若沒有 MOST 格式，則需要 parser，將特定文字對照 MOST 系統後轉為 MOST 格式。  
**歸檔結論：** 舊資料匯入不以拒收為唯一策略，而是傾向「保留 + 轉換」。

## 已補充回答

### Q5. parser 的輸入格式範圍是什麼？文字敘述、Excel、舊 SOP、工時表，還是特定模板？

**使用者回答：** 目前預期有兩種：

1. 舊 SOP（使用者理解為目前專案 MOST 系統輸出的格式）
2. Excel，且皆應有特定模板

**歸檔結論：** Phase 1 parser 不應以任意自由格式為目標，而應聚焦於「舊 SOP 輸出格式 + 特定模板 Excel」。

### Q6. parser 轉出的結果是直接成為正式 MOST step，還是先成為待 IE 確認的草稿？

**使用者回答：** 需由 IE 確認，因此結果應可編輯；若可編輯實作成本太高，也可先報錯要求使用者修正，但必須保留原始檔案。  
**歸檔結論：** 匯入結果原則上應先進入可確認流程，不宜直接視為正式標準；若 Phase 1 無法支援完整可編輯導入，至少要保留原始檔與錯誤回饋。

## 已補充回答

### Q7. IE 手動指定 MaxiMOST 時，是否需要保留原因欄位，避免後續審核無法理解？

**補充說明：** 這題的意思是：未來如果某個產品 / SKU 原本大多數都用 MiniMOST，但 IE 對某一份標準文件改選 MaxiMOST，系統是否要要求填一個原因，例如：

- 長工序維修作業
- 非短循環裝配
- 特殊設備保養流程

這樣之後審核者或接手的人才知道為什麼不是用 MiniMOST。

**使用者回答：** 是，要填寫原因。  
**歸檔結論：** 若未來支援多 MOST 系統，IE 在切換 MiniMOST / MaxiMOST 時，必須填寫切換原因欄位。

## 待續討論問題

### Q8. 原因欄位是否只允許自由文字，還是要提供常見原因下拉選單 + 備註？

**使用者回答：** 下拉選單 + 備註。  
**歸檔結論：** 若未來支援多 MOST 系統切換，原因欄位應採「常見原因下拉 + 備註」模式，而非純自由文字。
---

## 目前暫定結論

> Phase 1 採 **MiniMOST-only**，但整體資料模型與服務設計必須保留未來擴充至 MaxiMOST 的能力。  
> 標準文件的業務粒度應至少涵蓋 `Product / SKU / Site / Version`，不能只停留在 project 層級。

---

## Resolution

**Decision:** Phase 1 採 MiniMOST，保留未來擴充 MaxiMOST 的架構空間  
**Date:** 2026-04-17  
**Decided by:** 使用者（待正式確認）  
**Implementation impact:**  
- Phase 1 只實作 MiniMOST 資料卡與驗證規則
- schema / service / persistence 需預留 `product`、`sku`、`site`、`version`
- 暫不導入多 MOST engine 的完整切換機制，但需保留擴充點
