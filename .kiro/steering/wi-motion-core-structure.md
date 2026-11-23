---
inclusion: always
---

# 核心定義：WI ⊃ motion 兩層結構（MOST 工序組織的基本模型）

> **重要性（User 定調 2026-09-11）**：這是 MOST 系統的核心組織結構，**未來會很常用、影響很大**。
> 所有涉及 MOST 工序、Level System、LB 整合、匯出的 agent 都必須理解這兩層。
> 以實讀 code 確認，非推測。
>
> **2026-11-23 更新（ADR-038）**：WI 的編輯改在「每份 WI 一個工作區」進行。MOST 工作台（`workbench-v3`）
> 與它的「WI 大綱」畫面依 ADR-038 D4 移除（前端移除進行中），所以本檔不再以工作台當例子。
> 兩層結構本身不變。

## 兩層結構

MOST 的工序組織分**兩層**：

1. **motion 層（最小單位）**：一個 **motion = 一個七格 GM/CM MOST model = 一個 cycle**。
   - 每個 motion 有自己的 narrative（WI 語句/動作描述，如「右手抓握電動起子保持住至機箱」）、hand、frequency、
     SIMO 標記、七格 slot 值、由單一引擎算出的 TMU。
   - 這是 TMU 計算與工時標準的**最小粒度**。

2. **WI 層（動作群組）**：一個 **WI = 一句 WI 語句 + 底下多個 motion**。
   - 例：WI「拿取電動起子，依圖示鎖附兩顆螺絲」= 1 句語句，底下 **3 motions**（拿起子、鎖第一顆、鎖第二顆）。
   - WI 是「把多個 motion 組織成一個有意義的作業單位」的層級，供人閱讀與組織。

**一句話**：WI 是「一句話描述的作業」，motion 是「這句話底下的每一個 MOST 動作模型」。**一個 WI 通常含多個 motion。**

## Code 層對應（實讀確認）

| 概念層 | 工時表（worksheet，正本） | 工作區編輯區（ADR-038，規劃中） |
|---|---|---|
| WI 層 | 同一個 `wi_rows.wi_group`（作業名稱，ADR-035 D10；同名＝同作業的**候選**成員）的那些列 | 草稿列依 WI 語句分組顯示，可「整組確認」 |
| motion 層 | 一筆 `wi_rows` ＋ 一筆 `most_cycles`（`most_cycle.wi_row_id` unique，1:1，`worksheet.py`） | 一個草稿列（審核單位；ADR-038 D2） |

- 工時表是一份 SKU 工序版本的正式工時（`process_version` ⇔ `most_worksheet`，1:1）。**一個 WI 在工時表裡是多列**：
  每個 motion 一列，靠 `wi_group` 組回同一個 WI。
  - `wi_group` 是可為空的文字欄位，不是硬鍵：空值的列不屬於任何 WI 分組；同名只是「可能同一作業」，不要拿它當唯一識別。
- 【規劃中，ADR-038 D3】新內容（人工、單句 AI、整份上傳）先進工作區的**編輯區**，確認後按「寫入工時表」才落盤。
  一句 WI 經 AI 拆成多個 motion，所以 Excel 的一列進到工時表會變成好幾列。編輯區尚未實作，現況是直接編輯工時表。
- 舊的範本資料：`motion_module`（`category='wi-template'`，`rows[]` 是 WI 底下的 motion 快照）也體現同樣的兩層，
  但它屬於要移除畫面的範本庫，資料保留、不再有入口，也**不提供跨 SKU 重用**（ADR-038 D4）。
  **不要**再把它當成 WI 的主要落點，也不要建議「從範本庫插入」。
- `motion_templates`（動作範本，與 `motion_module` 是不同的表）**保留並繼續使用**：Excel 匯入的範本比對（ADR-025）
  與規則解析的 L0 範本提示（`nlp/linking.py`）都靠它（ADR-038 D4）。

## 對 LB 整合的關鍵含意（見 `docs/lb-integration/MOST_LB_CONTRACT.md` D1）

- **LB task = motion（most model），不是 WI。** 真正的「1:1」在 **motion 層**（一個 motion = 一個 LB task）。
- **一個 WI（一句語句）= 多個 motion = LB 的多個 task。** 這些 task 之間用 predecessors（先後）、cub/worker_cub
  （同站/同人）等表達關係。
- WI 語句進 LB 走 **(c)**：**motion 的 narrative 當 LB `action`（task 層精確描述，供 General 判定）**；
  **WI 語句用「WI 分組欄位」另帶**（讓 LB 知道這些 task 同屬一個 WI，供雙向同步對回 WI 層），
  不把同一句 WI 語句灌進多個 task 的 action（會重複、General 判定分不出）。

## 使用守則（給所有 agent）

- 談「工時計算/TMU/單一動作」→ 指 **motion 層**。
- 談「一句作業描述/作業分組/組織」→ 指 **WI 層**（含多 motion）。
- 不要把「WI」與「motion」混為一談；不要假設「一個 WI = 一個動作」（一個 WI 常含多個 motion）。
- 涉及 LB 匯出時，task 粒度一律對到 **motion**，WI 是上層分組。
- 涉及 AI 解析或審核時：審核單位是 **motion**，畫面依 **WI** 分組（ADR-038 D2）。
