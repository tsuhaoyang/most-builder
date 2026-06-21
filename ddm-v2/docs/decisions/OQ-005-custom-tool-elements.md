# OQ-005 — 非標準 MOST 元件與自定義工具元素

**Status:** 🟡 討論中  
**提出日期:** 2026-04-17  
**Owner:** IE Lead / Domain Expert  
**相關規格:** `docs/specs/system-architecture-spec.md` §3.1  
**核心算法參考:** `docs/specs/MOST-core-algorithm-spec.md` §5.3

---

## 問題定義

工廠是否存在超出標準 MOST data card 的操作？  
如果有，應如何建模、治理與版本化？

---

## 為什麼重要

標準 MOST data card 雖然涵蓋多數常見動作，但實際工廠常會有：

- 特定設備操作
- 特定站點習慣
- ESD / 視覺檢查 / 掃碼等特殊流程

若系統沒有一個正式機制管理這些例外，最後就會退化成：

- 任意固定 TMU
- 無法追溯來源
- 不知道是否符合 MOST 原則

---

## 現況

目前系統中已有固定 TMU 的近似處理，例如：

```python
FIXED_ACTION_TMU = {
    "fasten": 6,
    "scan": 6,
    "press": 3,
}
```

這代表系統其實已經有「非完整 data card 推導」的行為，但尚未建立正式治理模型。

---

## 可能的非標準元素

以下是目前推測較可能出現的類型，後續需由 IE 與 domain expert 實際確認：

1. ESD 安全處理流程
2. 扭力確認 / torque verify 類動作
3. Barcode / QR scan
4. 顯微鏡 / 視覺檢查
5. 點膠、上膠、固化等待

---

## 使用者本輪補充

### 2026-04-17 使用者回答

使用者目前的方向是：

- 需要有一個 **backstage management platform**
- 讓 manager / senior user 可以管理這類情境
- 後台可以依 MOST sequence model 與定義來建立資料

這個方向是合理的，但目前回答的仍是：

- **誰來管理**

而還沒有明確回答：

- **要管理哪些 custom element**
- **如何建模**
- **哪些是 site-specific**
- **哪些是全域標準**

---

## 已討論方案

### 方案 A：固定 TMU library

- 用 action name → fixed TMU
- 優點：
  - 快速
  - 實作簡單
- 缺點：
  - 很容易偏離 MOST 原則
  - 不利於方法改善分析

### 方案 B：以標準 MOST sequence 組出 custom element

- 每個 custom element 仍可被拆回標準 sequence model
- 優點：
  - 最符合 MOST 方法論
  - 可追溯、可審查
- 缺點：
  - 後台建模較複雜

### 方案 C：Hybrid

- 手動動作仍要求以 MOST sequence 建模
- 純 process-controlled time 才允許固定值或參考值
- 這是目前最平衡的方向

---

## 架構審查意見

我同意應由 backstage management 來治理這些元素，但必須再補三個規則，否則後台只會變成「可任意輸入 TMU 的地方」：

### 規則 1：標準元素與自定義元素必須分開標示

至少要區分：

- `standard_element`
- `custom_element`
- `site_specific_element`

### 規則 2：每個 custom element 必須有來源與推導說明

至少要保存：

- 建立人
- 所屬 site
- 適用範圍
- 推導方式
- 是否經過 IE 審核

### 規則 3：custom element 必須版本化

否則一旦被修改，既有標準文件就失去可追溯性。

---

## 已有相關回答（跨文件）

### Q1. custom element 是否涉及 site 差異？

**使用者回答：** 已在其他文件回答。  
**歸檔引用：** site 差異與 product / SKU / site 粒度以 `OQ-001`、`OQ-003` 為主，不在本文件重複追問。

## 需先補充理解的問題

### Q2. 目前最確定存在的 custom element 有哪些？請列出實際工廠案例

**使用者回應：** 不太理解題意，希望先舉例。  

**補充說明：** 這裡問的不是抽象概念，而是工廠裡那些「標準 MOST data card 沒有直接定義、但你們實際會做」的動作。例如：

- 掃條碼後等待蜂鳴確認
- 用扭力起子鎖附後還要看扭力顯示
- 顯微鏡下檢查焊點
- 點膠後等待固化
- ESD 特殊操作

若這些動作存在，就可能需要 custom element。

### Q3. 是否允許 manager 直接輸入固定 TMU，還是必須提供 sequence-based 推導？

**使用者回應：** 不理解兩者差異，希望先舉例。  

**補充說明：**

- **固定 TMU**：例如直接定義「掃碼 = 6 TMU」
- **sequence-based 推導**：例如把掃碼拆成  
  `拿起掃描器 -> 對準條碼 -> 掃描 -> 確認結果`  
  再用 MOST sequence 算出總 TMU

差別在於：

- 固定 TMU 較快，但較難審核來源
- sequence-based 較符合 MOST 原則，也較容易追溯與調整

### Q4. custom element 是否需要審核與發布流程？

**使用者回應：** 目前不太理解什麼是 custom element。  
**歸檔說明：** 在尚未建立共同定義前，此題暫不要求使用者回答結論。

### Q5. custom element 被更新後，是否影響既有已發布標準，還是只影響新版本？

**使用者回應：** 目前不太理解什麼是 custom element。  
**歸檔說明：** 此題依賴 Q2 / Q3 先建立共同理解，暫不重複追問。

## 已補充回答

### Q6. 請先確認工廠是否存在列舉的特殊動作

**使用者回答：** 是，會有。  
**歸檔結論：** custom element / 特殊動作不是假設性需求，而是實際存在的需求。

### Q7. 若存在，哪些動作你認為不能只靠標準 MiniMOST step 表達？

**使用者回答：** 這部分不由系統決定，屬於 IE 專業。系統的角色是讓 IE 能快速建立他們要的工序資料；在 MOST 領域內系統都要能做到，例外由 IE 判定與處理。  
**歸檔結論：** 是否屬於例外情況的判斷權在 IE，不由系統硬編碼。

### Q8. 對這些特殊動作，你比較傾向「固定 TMU」還是「拆成 sequence」？

**使用者回答：** 在 MOST 系統中一律用 MOST 方式。  
**歸檔結論：** custom element 的建模方向已明確偏向 sequence-based，而非固定 TMU。

### Q9. 使用者介面與後台管理在這個議題上的差別

**使用者補充：** 使用者介面要讓使用者易於使用；後台管理則越詳細越好。  
**歸檔結論：** 前台與後台需要不同抽象層級：

- 前台：簡化輸入、快速建立工序
- 後台：詳細管理 sequence、定義、治理規則

## 已補充回答

### Q10. 後台是否允許 IE 建立「可重用的 sequence 模板」，供前台快速選用？

**使用者回答：** 是的，需要。  
**歸檔結論：** 後台應支援 IE 建立可重用的 sequence 模板，供前台快速建立工序資料。

### Q11. 前台是否需要把複雜 sequence 隱藏成較簡化的操作元件？

**使用者回答：** 採架構建議。  

**架構建議：**

前台建議採「**雙層抽象**」：

1. **簡化模式（預設給一般 IE 使用）**
   - 以動作卡 / 表單引導方式輸入
   - 例如：拿取、移動、放置、掃碼、鎖附、檢查
   - 系統自動帶出對應 sequence 模板與常用參數

2. **進階模式（給資深 IE / 後台使用）**
   - 可直接查看與編修完整 MOST sequence
   - 可調整參數、模板定義與規則

這樣可兼顧：

- 前台易用性
- 後台完整治理能力
- 不讓一般使用者一開始就面對過度複雜的 sequence 細節

**歸檔結論：** 前台應隱藏複雜 sequence，改以較簡化操作元件與模板驅動方式呈現；後台則保留完整 sequence 細節。

### Q12. 前台的簡化操作元件，是否要先以「General Move / Controlled Move 常見情境」為主，而不是一開始開放所有高自由度 sequence？

**使用者回答：** 採架構建議。  
**歸檔結論：** Phase 1 前台先以 `General Move / Controlled Move` 的常見情境為主，不一開始開放所有高自由度 sequence。

### Q13. 模板是只允許後台建立，還是資深 IE 也可在前台另存為模板？

**使用者回答：** 採架構建議。  
**歸檔結論：** Phase 1 採以下策略：

- 後台可建立共用模板
- 資深 IE 可在前台另存私人模板
- 若要成為共用模板，需透過後台或審核流程納管

## 待續討論問題

- [ ] 私人模板是否需要期限、擁有者限制或轉交機制？

---

## 目前暫定結論

> custom element 的治理應放在 backstage management 中，但目前尚未定義清楚其實際清單、建模方式與版本規則。  
> 在未釐清前，不應把「可在後台管理」誤認為「已完成決策」。

---

## Resolution

**Decision:** 已確認需要由 backstage management 治理，且在 MOST 系統內一律以 MOST 方式建模  
**Custom elements identified:** 已確認實際存在，但實例清單尚待後續補充  
**Modeling approach chosen:** sequence-based  
**Date:** 2026-04-17  
**Decided by:** 使用者 + 架構討論（待正式確認）  
**Implementation impact:**  
- 後台需支援 custom element 管理與 sequence 模板管理
- 需設計 element 分類、審核、版本與適用範圍
- 前台需提供簡化輸入元件，後台保留完整細節
- 前台 Phase 1 先聚焦 `General Move / Controlled Move` 常見情境
- 模板需區分「共用模板」與「私人模板」
- 後續需要補一輪工廠實際案例盤點
