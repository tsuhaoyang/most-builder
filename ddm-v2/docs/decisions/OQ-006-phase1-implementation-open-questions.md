# OQ-006 — Phase 1 實作未決問題

**Status:** 🟢 已定案  
**提出日期:** 2026-04-17  
**Owner:** Tech Lead / IE Lead  
**相關規格：**

- `docs/specs/phase-1-implementation-spec.md`
- `docs/specs/phase-1a-core-foundation-spec.md`
- `docs/specs/phase-1b-collaboration-and-governance-spec.md`

---

## 目的

本文件專門記錄「從決策文件推進到實作規格之後，才浮現出的細節問題」。

這些問題與 `OQ-001` ~ `OQ-005` 不同：

- 前者偏業務與方向決策
- 本文件偏實作落地時的具體細節

---

## 已知上下文

目前已確認：

- Phase 1 先做 MiniMOST
- 架構採 PostgreSQL + modular monolith
- 資料粒度為 `Product / SKU / Site / Version`
- published version 不可直接修改
- 鎖定粒度為 `SKU version`
- time source 建立後不可修改
- 前台採簡化 sequence 元件
- 後台管理 sequence 模板與 custom element

---

## 問題與答案

### Q1. Phase 1 是否納入 MiniMOST 的完整進階特性？

目前 MiniMOST 核心已確認，但仍有 3 項細節尚未最後定案：

1. `B parameter` 是否在 Phase 1 完整支援
2. `ENW (Effective Net Weight)` 是否納入
3. `P10 / P16 / P24` 是否納入

**為什麼重要：**

- 若不納入，Phase 1 範圍較可控
- 若納入，可提升與 MiniMOST 原典的一致性

**使用者決策：** 採暫定建議。  
**定案內容：**

- `B parameter`：Phase 1a 納入
- `ENW`：Phase 1a 保留欄位，可選配
- `P10 / P16 / P24`：Phase 1a 納入

**歸檔結論：** Phase 1a 不只做 MiniMOST 最小骨架，而要做到足以支撐較完整 MiniMOST 場景的程度。

---

### Q2. TTL 到期後，是否仍需管理員強制解除鎖？

目前已確認：

- TTL 到期會自動解鎖
- 鎖定單位為 `SKU version`
- 到期後保留已儲存資料，丟棄未儲存變更

尚未定案的是：

- 是否仍需提供 manager / admin 手動強制解除鎖，作為例外處理

**為什麼重要：**

- 若 TTL 設太長，實務上可能仍卡住使用者
- 若沒有強制解除能力，現場處理效率可能不足

**使用者決策：** 採暫定建議。  
**定案內容：**

- 保留 TTL 自動解鎖
- 另外提供 manager / admin 強制解除鎖，作為例外處理

**歸檔結論：** Phase 1b 必須同時具備自動解鎖與手動 override。

---

### Q3. 私人模板是否需要治理規則？

目前已確認：

- 後台可建立共用模板
- 資深 IE 可建立私人模板

尚未定案的是：

- 私人模板是否需要有效期限
- 是否限制只能擁有者使用
- 是否允許轉交給其他人

**為什麼重要：**

- 若完全不管，可能快速累積大量過期或重複模板
- 若一開始治理太重，又會降低 Phase 1 可交付性

**使用者決策：** 採暫定建議。  
**定案內容：**

- Phase 1 先不做私人模板期限
- Phase 1 先不做模板轉交機制
- 私人模板先以擁有者私有為主

**歸檔結論：** 私人模板治理在 Phase 1 採輕量策略，避免過早增加流程複雜度。

---

### Q4. `allowance_percent` 的預設套用策略

目前已確認：

- `allowance_percent` 欄位存在
- `standard_time_seconds` 需保存
- `time_source` 為 SKU level

尚未最後定案的是：

- Phase 1 預設到底先採：
  - by SKU
  - by 工序
  - 或兩者皆可但以 SKU 為主

**使用者決策：** 採暫定建議。  
**定案內容：**

- Phase 1 預設先以 **SKU level** 為主
- 不在 Phase 1 一開始就做完整多層繼承樹

**歸檔結論：** allowance 的主配置粒度為 SKU version / SKU-level，較細的工序級控制可延後。

---

## 原先建議優先順序

| 優先級 | 問題 | 建議 |
|--------|------|------|
| 高 | Q1 MiniMOST 完整度 | 先定，因為會直接影響 Phase 1a 演算法範圍 |
| 中 | Q2 TTL 管理員強制解鎖 | 在 Phase 1b 開工前定掉 |
| 中 | Q4 allowance 預設策略 | 在 API / schema 最終定義前定掉 |
| 低 | Q3 私人模板治理 | 可延後到 Phase 1b 後段再定 |

---

## 已採納建議

本次使用者已確認採用以下建議：

1. Phase 1a：
   - `B parameter`：納入
   - `ENW`：保留欄位，可選配
   - `P10 / P16 / P24`：納入
2. Phase 1b：
   - 提供 admin 強制解鎖
   - allowance 預設先以 SKU level 為主
   - 私人模板先不做期限與轉交機制

---

## Resolution

**Decision:**  
- Phase 1a 納入 `B parameter`
- Phase 1a 保留 `ENW` 欄位並作為可選配能力
- Phase 1a 納入 `P10 / P16 / P24`
- Phase 1b 提供 admin / manager 強制解除鎖
- Phase 1 私人模板先不做期限與轉交治理
- Phase 1 allowance 預設以 SKU level 為主  
**Date:** 2026-04-17  
**Decided by:** 使用者（採架構暫定建議）  
**Implementation impact:**  
- 影響 Phase 1a MiniMOST 實作邊界
- 影響 Phase 1b lock / template / allowance 設計
