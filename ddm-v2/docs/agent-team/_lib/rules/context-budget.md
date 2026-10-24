---
類別: "SPEC（CORE）"
狀態: "權威"
層級: "L1（方法論，專案中立）"
適用: "所有採用 dev-workflow 的專案"
---

# Context 預算與清理 (Context Budget)

## 0. 核心原則

> **可清理點 = 狀態已完全落盤的點。**

只能在「resume 需要的東西全在檔案裡」的地方清 context。
如果某個決定目前只存在於對話裡，清掉就是銷毀工作。

這條原則反過來講就是階段關卡的定義：

> **一個 gate 如果沒有產出 durable artifact，它就不是真的 gate。**

所以「哪裡可以機械清」和「哪裡該有 artifact」是同一張表。
agent 必須 **resume from durable state, not memory**——
狀態檔存在的唯一理由就是讓 context 變成可丟棄的東西。

---

## 1. 機械清理時機

| 時機 | 動作 | 清之前必須已落盤 |
|---|---|---|
| **gate 通過後** | `/clear` | 該階段 artifact 已寫入 + 交棒檔已更新 |
| **一張票結案後** | `/clear`（**必清**） | 完成紀錄 + 證據 + SPEC 狀態翻 `已落地` + 決策紀錄追加 |
| **每個 task commit 後** | `/clear`（可選，視票大小） | commit 存在 + task 完成紀錄 |
| **委派前** | 不清，把工作丟出去 | — |
| **被迫 `/compact` 時** | 清完補記「為什麼剛才不能落盤」 | 這是**流程缺口信號**，見 §5 |
| **設計探索中** | 邊討論邊寫進 DESIGN 草稿 | 否則只剩 compact 一條路 |

「一張票結案後必清」配合 `stage-table.md` §5 的 WIP = 1：
**一張票一個 session。** 平行票的 context 是相乘的，
而且你會開始搞混哪個結論屬於哪張票。

---

## 2. 交棒檔：讓 `/clear` 變免費的那個 artifact

沒有這個，§1 整張表都不能用。每張票一份，十幾行。
**檔案位置與類別宣告的正本是 `doc-taxonomy.md` §1.5「票庫結構」**
（票庫路徑屬 L2，所以下面那行是範例，不是規定）：

```yaml
# 類別: TICKET（交棒檔）
# <票庫>/TICKET-012/state.yaml
id: TICKET-012
state: active                                 # ← 票級狀態（control-flow.md §1.1）
stage: implement                              # ← 階段（stage-table.md §1）
depth: L1                                     # ← 只有 human 可以改（control-flow.md §1.4）
assignee: implementer(python)
upstream: [REQ-007, DESIGN-011, ACC-004]

next_action: "實作 TASK-045"
read_first:                                   # ← 下一棒的 context 預算
  - docs/dev_docs/KPI_CALCULATION_CORE_SPEC.md#3
  - acc/ACC-004.md
  - src/kpi/calculator.py

open_questions: []                            # 空 = 可以安全往下走
log:
  - "2026-10-02 design PASS，reviewer(design) 無發現"
  - "2026-10-02 ACC-004 由 human 核可，綁 DESIGN-011 hash a1b2…"
```

### 2.-1 兩個可選的頂層區塊：`tasks:` 與 `deviations:`（DW-7）

範例是最小形狀。交棒檔另有兩個頂層區塊，依票而定：

**`tasks:`** —— 承載該票的 TASK（**欄位形狀的正本在 `doc-taxonomy.md` §1.5「TASK 檔的形狀與位置」**，本節不重述）。
每個 TASK 一個 list item，有 `id` / `summary` / `assignee` / `depends_on` / `status`（三值 `todo`／`agent_done`／`done`）/
`commit`（下一筆回填）/ `covers` / `read_first`。TASK 屬 TICKET 類，不新增第十類。

**`deviations:`** —— 流程阻擋／宣告偏離的單一可定址承載，取代散落四處（manifest、`state.yaml` 註解、ACC 第一節、
adopters 表）。每項四欄：

```yaml
deviations:
  - what: "<偏離/阻擋了哪條規則> 的一句話"
    why:  "<原因>"
    ref:  "<指回的依據：票號 / ADR / 條文 anchor>"
    since: "<YYYY-MM-DD>"
```

與 `README.md`「`local_deviations` 是這個設計的核心」同形——不防止偏離，而讓偏離成為被記錄的、可定址的決定。
與票級 `blocked`（`control-flow.md` §1.1、C21）是**兩件事**：`blocked` 是票躺著、下一步由外部；`deviations:` 是票仍正常
推進但宣告了某規則的偏離。一張票可以同時 `state: active` 且有 `deviations:` 條目。本區塊與「宣告偏離」正本的對齊義務
歸 `DW-19`（兩票誰先定案由後定案一方對齊，`deviations:` 四欄刻意保持最小以降對齊成本）。

### 2.0 `state` 與 `stage` 是兩個欄位，不是一個

v0.3.1 之前這裡只有 `status: implement`——那是**階段**，被當成狀態用。
兩者回答不同的問題：

| 欄位 | 回答 |
|---|---|
| `stage` | 現在在做哪一種工作 |
| `state` | 現在**卡在誰身上**，以及這張票能不能被放下 |

一個欄位塞兩個語意的後果：票卡在 human 關卡時，`status` 只能寫
它**進入關卡前**的那個階段，於是「在等人」這件事無處可寫
——而那正是離場檢查（§4）最需要知道的事。

狀態詞彙與轉移規則：`control-flow.md` §1（正本，本節不重述）。

### 2.1 `read_first` 是關鍵欄位

它把「下一個 session 該讀什麼」寫死，所以新 session 不必靠猜、
不必重讀整個領域、也不必由你口述一遍背景。

而這一欄其實是 task sizing 規則的另一面：

> 如果一個 task 需要讀完整份 Specification 和 Design 才能被理解，
> **它就太大了。**

推論：**「task 切小」不只是工程衛生，它直接就是 context 控制手段。**
如果某個 task 的 `read_first` 列不出來、或列出來有八個檔案，
那不是 context 問題，是 task 切太大。上限 4 個檔案。

### 2.2 `open_questions` 非空時不准清

那代表有東西還懸在你腦袋裡，沒有落盤。

**增刪在 log 留痕（DW-7）。** 條目**解決後移除**時，在同一筆 log 點名移除哪一條（用條首文字）與依據；
**新增**條目時 log 註來源（哪張票／哪個角色移交）。引用一條 open_question 用**條首文字**，不用行號或序號
（行號會隨增刪漂）。穩定標識（供他檔定址）暫不強制，與 `deviations:` 的標識問題一起待 `DW-19` 對齊後定。
**結案前** `open_questions` 須清空、或每條註明去向（移交他票／已解決）——本處「非空不准清」是既有約束，不新增檢查。

### 2.3 交棒檔的自我檢驗

> **交棒檔如果比它省下的 context 還長，它就是淨虧損。**

上限十幾行。不要長成大 YAML。

---

## 3. 不要先花掉：四條規則

清理只是回收。下面四條是源頭控制。

### 3.1 「讀很多、結論很短」的工作一律委派

這是可委派任務的特徵。subagent 的 tool output 不進主 context，
只有 final report 進來。

但還有同樣重要的另一半：**回報格式必須有固定章節與長度上限。**
如果 subagent 回報沒有上限，你只是把問題搬了個位置。

### 3.2 每個角色要有「必讀 / 不讀」清單

> **清單本體在 `roles/<角色>.md`**（v0.3.1 起）。
> 本節只留原則——per-role 的資料跟著角色定義走，一個概念一個權威（R3）。
> 原本列在這裡的那張表已移出，未刪除語意，只換了住處。

**這同時是 context 控制和職責分離。**
一個角色讀了它不該讀的東西，就會做它不該做的決定——

- verifier 讀了實作，就會開始**體諒**實作，而不是驗它
- implementer 讀了需求理由，就會開始自己調整需求範圍

這跟「生產者 ≠ 審查者」是同一條原則，只是從輸入端講。

如果 implementer 非得讀 REQ 才知道要做什麼，
那是 **DESIGN 不完整**，不是 context 不夠。

### 3.3 超過 ~200 行的權威檔必須有分段取用入口

如果 agent 每次都要整份讀進來才找到一個領域，那是每 session 的固定稅。

**所以領域對照腳本（給定檔案路徑 → 回傳命中的領域）本身就是 context 最佳化**，
價值遠超過「提醒」這個表面功能。知識圖譜查詢同理——
它回答問題，而不是讓你讀檔。

規則：**任何超過約 200 行的權威檔，必須配一個分段取用入口**
（腳本、index、或穩定章節錨點）。否則它會被整份讀，每次都讀。

### 3.4 常駐檔只放指路，不放規則本體

`CLAUDE.md` / `AGENTS.md` / `MEMORY.md` 每個 session 都載入，是固定成本。

> **常駐入口檔 ≤ 60 行。規則本體一律在 `docs/`，由指路連結帶到。**

`MEMORY.md` 同理：一行一條，內容在各自檔案裡。

---

## 4. 離場檢查（清之前三問）

```
1. 我剛才做的決定，有寫在檔案裡嗎？
2. 下一棒要讀什麼，有寫進交棒檔的 read_first 嗎？
3. 有沒有「我知道但沒寫下來」的東西？     ← 最危險的一項
```

第 3 題對應文件更新流程最後一步的「決策紀錄追加」紀律。
那條規則本來是為了文件可追蹤，但它同時是 context 安全網——
**append 完才准清。**

---

## 5. `/compact` 的定位：它是缺口信號，不是工具

`/compact` 要付一次全 context 讀取，而且摘要有損。
它該被當成**診斷訊號**：

> 被迫 compact = 「剛才那段工作沒有落盤處」

compact 之後要問一句：**這段工作缺哪個 artifact？**
答案通常就是這套流程該補的一欄。

反過來也要誠實：**過度清理有實際代價。**
重讀檔案也要錢，而且「我們上次為什麼否決了方案 B」如果不在檔案裡，
清掉就永久消失。所以是**只在 gate 清**，不是「覺得長了就清」。

> 「我老是弄丟 context」的解法不是更頻繁地壓縮，是**更多落盤點**。

---

## 6. 明確不做（避免過度設計）

- ❌ **不要寫 hook 自動偵測 context 長度然後自動清。**
  清理點很少，而且清掉的是你的工作，該由你決定。
- ❌ **交棒檔不要長成大 YAML。** 見 §2.3。
  `read_first` 超過 4 個檔案是 task 太大的信號，不是欄位該加長。
- ❌ **不要為 context 管理開獨立階段。**
  它是每個 gate 的附帶動作，不是流程節點。

---

## 7. 與階段主表的接點

`stage-table.md` 每個階段的**離開條件最後一項固定是**：

> 交棒檔已更新，可清。

---

## 8. 相關文件

- `rules/stage-table.md` — 階段邊界即清理點
- `rules/control-flow.md` — 票級狀態與「可否清」的對應表（§1.1）
- `rules/doc-taxonomy.md` — 各角色讀取清單對應的文件類別
- `roles/` — **各角色的必讀／不該讀清單本體**（§3.2）
