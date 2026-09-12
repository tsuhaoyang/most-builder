---
inclusion: always
---

# 核心定義：WI ⊃ motion 兩層結構（MOST 工序組織的基本模型）

> **重要性（User 定調 2026-09-11）**：這是 MOST 系統的核心組織結構，**未來會很常用、影響很大**。
> 所有涉及 MOST 工序、Level System、LB 整合、匯出的 agent 都必須理解這兩層。
> 以實讀 code + Workbench UI 截圖確認，非推測。

## 兩層結構

MOST 的工序組織分**兩層**（Workbench「WI outline」截圖可見：「13 WIs · 29 motions」）：

1. **motion 層（最小單位）**：一個 **motion = 一個七格 GM/CM MOST model = 一個 cycle**。
   - 每個 motion 有自己的 narrative（WI 語句/動作描述，如「右手抓握電動起子保持住至機箱」）、hand、frequency、
     SIMO 標記、七格 slot 值、由單一引擎算出的 TMU。
   - 這是 TMU 計算與工時標準的**最小粒度**。

2. **WI 層（動作群組）**：一個 **WI = 一句 WI 語句 + 底下多個 motion**。
   - 例：WI「拿取電動起子，依圖示鎖附兩顆螺絲」= 1 句語句，底下 **3 motions**（拿起子、鎖第一顆、鎖第二顆）。
   - WI 是「把多個 motion 組織成一個有意義的作業單位」的層級，供人閱讀與組織。

**一句話**：WI 是「一句話描述的作業」，motion 是「這句話底下的每一個 MOST 動作模型」。**一個 WI 通常含多個 motion。**

## Code 層對應（實讀確認）

| 概念層 | UI | 資料落點（v2） |
|---|---|---|
| WI 層 | Workbench「WI outline」的一列 | `motion_module`（`category='wi-template'`）；一個 module 一句名稱/語句。`schemas/v2/motion_module.py:79`：「'wi-template'：WI 大綱項（rows = 動作快照複本；對應 v3 MI statements）」 |
| motion 層 | WI 展開的子列、及上方「動作清單」（All 29） | 該 module 的 `rows[]`（每 row 一個動作/cycle，含 narrative/hand/frequency/simo/computed）；`WiOutline.tsx:2-6` |

- worksheet 情境（`wi_rows` + `most_cycles`，1:1）是**另一條線**（實際案件的工時表）；WI outline 的 `category='wi-template'`
  motion_module 是**動作/WI 範本組織**。兩者都體現「一句 WI ⊃ 多個 motion」的組織意圖，但落在不同表。
- v2 現況 `most_cycle.wi_row_id` 為 **unique（1:1）**（`worksheet.py:153`）——即在 worksheet 情境，一個 wi_row 一個 cycle；
  「一個 WI 多 motion」的多層組織體現在 motion_module 的 `rows[]` 與 WI outline 的 groupby。

## 對 LB 整合的關鍵含意（見 `docs/lb-integration/MOST_LB_CONTRACT.md` D1）

- **LB task = motion（most model），不是 WI。** 真正的「1:1」在 **motion 層**（一個 motion = 一個 LB task）。
- **一個 WI（一句語句）= 多個 motion = LB 的多個 task。** 這些 task 之間用 predecessors（先後）、cub/worker_cub
  （同站/同人）等表達關係。
- WI 語句進 LB 走 **(c)**：**motion 的 narrative 當 LB `action`（task 層精確描述，供 General 判定）**；
  **WI 語句用「WI 分組欄位」另帶**（讓 LB 知道這些 task 同屬一個 WI，供雙向同步對回 WI 層），
  不把同一句 WI 語句灌進多個 task 的 action（會重複、General 判定分不出）。

## 使用守則（給所有 agent）

- 談「工時計算/TMU/單一動作」→ 指 **motion 層**。
- 談「一句作業描述/WI 大綱/組織」→ 指 **WI 層**（含多 motion）。
- 不要把「WI」與「motion」混為一談；不要假設「一個 WI = 一個動作」（一個 WI 常含多個 motion）。
- 涉及 LB 匯出時，task 粒度一律對到 **motion**，WI 是上層分組。
