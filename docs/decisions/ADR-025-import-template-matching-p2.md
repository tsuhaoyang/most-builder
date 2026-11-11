# ADR-025: 匯入自動建模（範本庫 /match 接上匯入流程，P2）

**狀態：** accepted（2026-07-22，User 核可信任邊界）
**日期：** 2026-07-22
**關聯：** [ADR-024](ADR-024-master-data-vs-dictionary-boundary.md)（範本庫定位）、
[ADR-023](ADR-023-dictionary-governance-unification.md)（§3.4 回放鐵則、§3.5 讀 active）、
[ADR-014](ADR-014-v3-dictionary-as-value-authority.md)（值權威）、
`docs/architecture/import-and-productivity-plan.md`（P1→P2 規劃）

## 脈絡

範本庫（`motion_templates`）是「常見動作 → 完整 MOST 七格填法」的關鍵字對照表，
P1 已建（16 筆＋CRUD＋governance）。其核心價值端點 `POST /motion-templates/match`
（以描述比對關鍵字 → 回傳現成範本）**至今無任何生產消費者**——只有測試在打。

匯入流程現況（`import_service.submit_to_worksheet`）為每一暫存列建一個 **stub CycleIn**
（空 MOST 分析），IE 之後在工序表裡逐行手動補完。一份 200 行工序表＝200 次從零建模。
範本庫存在的意義正是消滅這件事，但**沒有接上**，所以對使用者是「看得到、用不到」
（ADR-024 §3 已記為待補）。

## 決策

### 1. 匹配套用發生在 **map 預覽階段**，不是 submit 落地時

現有流程 `upload → map → submit` 不變。在 `map`（`apply_mapping` 產生預覽）階段，
對每一暫存列的描述呼叫既有的比對邏輯，把**逐行匹配建議**併入預覽回應。submit 時
只落地「被採用」的匹配。

理由：預覽是 IE 唯一能在落盤前看見結果的地方；把匹配放在這裡，IE 核對與落地是同一
個心智動作。

### 2. 信任邊界：**逐行建議 + IE 核對後才落地**（User 裁決 2026-07-22）

關鍵字比對會誤命中（「自行確認螺絲拉力」不該套「鎖附螺絲」），而工時標準等同財務
資料。故：

- 每行顯示匹配結果：命中的範本名、seq_kind、**以 active 規則重算的 TMU**、比對分數、
  命中的關鍵字。
- **預選採用**（有命中時），但 IE 可逐行**取消**或**換其他候選**。
- 未命中的行維持現有 stub 行為，明確標示「無命中，須手動建模」。
- submit 只把「採用」的行套 cycle，未採用/未命中的維持 stub。

**這是 H-1 覆核可視性原則在匯入面的延伸**：系統可以建議，但不得把猜測默默當成事實
落盤。「自動套用、事後再改」被否決，理由與 H-1 相同——誤命中的錯誤 TMU 一旦落盤，
IE 不一定會回頭發現。

### 3. TMU 以 **active 規則重算**，範本不是歷史快照

範本的 `cycle_template` 存的是**動作結構**（A 伸手幾 cm、G 用哪個碼、M 轉幾圈…），
**不存值、不存 rule_set_code**（D9 已清除寫死的 V1）。套用時：

- 解析當前 active rule-set（ADR-023 §3.5），把 `cycle_template` 當作 `CycleIn` 餵進
  **唯一計算引擎** `POST /minimost/calculate` 的同一條路徑重算 TMU。
- **取不到 active 是錯誤狀態，不是 fallback**（ADR-023 §3.5、守則 §7 第 1 條）——
  預覽該行標為錯誤，不得猜一個版本繼續算。
- 前端**不得**自行計算或顯示任何未經後端重算的 TMU（守則 §7 第 3 條）。

這正好是回放鐵則的**反面**：歷史 cycle 要用它**當初**的版本回放（不變）；範本套用要用
**現在**的 active 版本計算（因為它是新建模，不是回放）。兩者都由「該用哪一版」這個
問題的答案決定，方向相反但同源。

### 4. 匹配只比對 standard 庫（維持現有 `/match` 行為）

`match_templates` 已限 `is_active AND status='standard'`——草稿範本不參與匯入建議。
維持。

## 契約（給實作定死，兩端據此並行）

**預覽回應**：`apply_mapping`／`GET /{import_id}` 的每一暫存列，新增：

```jsonc
"match": {
  "template_id": "…",            // 命中的範本；無命中為 null
  "template_name_zh": "鎖附螺絲",
  "seq_kind": "CM",
  "score": 0.83,
  "matched_keywords": ["鎖", "螺絲"],
  "computed_tmu": 29,            // 以 active 重算；解析失敗為 null
  "computed_seconds": 1.044,
  "candidates": [ … ]            // 其餘命中的範本（供 IE 換選），同結構去掉 candidates
} | null                          // 完全無命中為 null
```

**submit 請求**：`SubmitIn` 新增每行的採用決定：

```jsonc
"row_adoptions": [ {"row_index": 0, "template_id": "…"} , … ]
```

- 只有列在 `row_adoptions` 的行套對應範本的 cycle（後端**重新**以 active 解析並計算，
  **不信任前端傳來的 TMU**——前端傳的只有 `template_id`，值一律後端算）。
- 未列入的行維持 stub。
- `row_adoptions` 引用的 `template_id` 若非 standard／不存在 → 422（不得靜默略過）。

**RBAC**：沿用匯入既有的 `analyst`。

## 後果

- 好處：範本庫從「看得到、用不到」變成真正的生產力工具；一致地走唯一計算引擎，匯入
  的 TMU 與手動建模的 TMU 同源同值。
- 代價：預覽階段多一次 per-row 比對＋計算；大批匯入時需注意 N 次 calculate 的成本
  （實作可批次解析 active 一次、重用引擎的 rule-set 載入）。
- 邊界：**誤命中由 IE 逐行否決兜底**，系統不保證比對精確；比對演算法（`_score`）本身
  不在本 ADR 範圍，維持現狀。
- 未決：範本套用後，IE 在工序表裡的後續微調是否要記錄「源自範本 X」的來源（供日後
  分析範本命中率）。P2 不做，列為後續。
