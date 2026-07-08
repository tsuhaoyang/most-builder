# 00：v3 系統方式分析（萃取方法論）＋ 不合理設計討論清單

> **目的**：v3 由非工程人員（IE）開發——這是它的價值（領域邏輯直接來自使用者）也是它的風險（工程紀律缺失）。本文件定義「**萃取邏輯、不搬程式**」的方法，並把所有不適合直接移植的設計列成 DISC 清單供裁決。
> **證據底稿**：[reference/](reference/) 三份（全部自程式碼直接萃取，未採信 v3 markdown）。

## 1. v3 的三層邏輯——萃取原則

### 1.1 使用邏輯（usage logic）＝ IE 的工作心智，**最高保真移植**

v3 最有價值的部分。從前端操作流萃取（reference/frontend-usage-flows.md）：

| IE 心智 | v3 體現 | 萃取結論 |
|---|---|---|
| 「動作是積木」 | 逐 slot 選項→即時看 TMU/句子→存成可重用單元 | 保真：編輯迴圈（選→算→看句→存）是規格 |
| 「由小組大、逐層重用」 | 模組(L1)→WI(L2)→流程(L3)，跨層「傳送至」 | 保真：三層心智為 canonical（見 DISC-01） |
| 「拿舊的改，不從頭做」 | 到處都有 clone/duplicate/搜尋庫 | 保真：clone 與庫搜尋是一級功能 |
| 「改實例不能動到範本；要更新範本是顯式動作」 | 快照複製＋apply-back | 保真：快照哲學＋顯式回寫（v2＝發新版） |
| 「AI 只是預填，我來確認」 | nl-draft badge（推斷/預設/待確認）＋覆蓋或補空模式 | 保真：建議層永遠可見來源與信心 |
| 「口語句子是交付物」 | 系統句＋人工改句雙欄、句子即 WI 名稱預設 | 保真：句子可重生亦可人工潤飾 |

### 1.2 功能邏輯（feature logic）＝ 行為規則，**保真但補工程紀律**

從 API 行為萃取（reference/api-inventory-*.md）。規則本身（計算、驗證、狀態機、快照時機）照抄為規格；缺的錯誤邊界、權限、原子性在 v2 規格中補齊並標注「v2 補強」。

### 1.3 資料關聯邏輯（data-relation logic）＝ 概念關聯，**保留關聯、重整載體**

v3 的概念關聯圖（值得保留）：

```
DictionaryVersion 1─* SequenceModel 1─* ParameterSlot 1─* ParameterOption
                  1─* LexicalOption
（一切分析物綁 dictionary_version_id；計算結果存快照 JSON 可稽核）

SequenceItem（原子）→ MiStatement（組合＋子快照 items）        ← 一代
ActionModule（原子）→ WITemplate（組合）→ ProcessRoute（快照組合）← 二代
MiStatement →（快照）WISetProject                              ← 一代收集器
AnalysisCase 1─* AnalysisStep 1─* StepSlot（＋工作流＋audit＋報表）← 獨立平行系統
```

載體問題（兩代並存、四處合計、Float 型別、String UUID）不移植——v2 以 rule-set／motion_modules／worksheet 承載同樣的關聯（對映表見各 CL/F 文件「v2 落地」段）。

## 2. 不合理設計討論清單（DISC）——務必逐條裁決

> 標記：🔴 不移植（v2 已有更強機制或屬 bug）｜🟡 待 User/IE 裁決｜🟢 v2 補強後採納

| # | 發現（證據） | 問題 | 建議 |
|---|---|---|---|
| **DISC-01** ✅ **已定案（2026-07-05，User）** | **兩代組裝系統並存**：一代（Sequence→MiStatement→WISetProject）與二代三層（Module→WITemplate→ProcessRoute）功能重疊、前端兩個工作台都活著（詳解見 §2.1） | 同概念兩套資料與 UI，使用者心智分裂 | **裁決：以二代三層為 canonical 使用邏輯**（F-03）；一代的 MI 語句/WI Set 為其前身、功能併入（F-02/F-04 標注收斂），v2 不建一代資料層 |
| **DISC-02** 🔴 | **後端信任前端傳入的 TMU**：calculate-row 與 sequences 的 selections 內含 `tmu_value` 由前端夾帶；AnalysisStep 的 `index_value` 更是純前端數字，後端不對照字典（api-inventory-dictionary-workflow §步驟） | **工時可被任意竄改**——標準工時系統的致命傷 | v2 鐵則：API 只收 **option code＋物理量**（cm/秒/次數），TMU 一律由引擎讀 rule-set 算。所有 F 文件的 API 合約已按此改寫 |
| **DISC-03** 🔴 | **四處計算/合計路徑**：calculation_v2（正確）、calculation.py（半棄置）、analysis.py inline 手算、wi_set_builder 快照加總（**漏排 SIMO 的 bug**） | 漂移已實際發生（WI Set 總計高估） | v2 單一引擎（most_engine）；此清單為 ADR-014 反例教材 |
| **DISC-04** 🔴 | **審核工作流掛錯聚合**：工作流/audit/報表只掛在 AnalysisCase（inline 手算的舊系統）；workbench 的序列/WI/流程**完全沒有**審核與報表 | IE 真正的產出（WI/流程）反而無治理 | v2：工作流掛 ProcessVersion（涵蓋 worksheet 與其列），報表從 worksheet 出（impl-06/F-07 已按此設計） |
| **DISC-05** 🟢 | **active 字典可直接改值**：PUT options 無唯讀防護、synonyms 改了不失效快取（僅 publish 會）（api-inventory-dictionary-workflow §PUT options） | 已發布值可靜默漂移；快取不一致 | v2：published 不可變（唯同義詞可補）＋寫入點失效快取（impl-01/07 既定） |
| **DISC-06** 🟢 | **值邏輯洩漏到前端**：模型切換自動預填 B_EYE_MOVE/P_PLACE_NO_DIRECTION 是前端寫死（frontend-usage-flows §C1） | 預設值是領域資料卻不在字典 | v2：預設/推斷規則進 rule-set 資料（is_default／建議規則），後端 options 提供，前端只渲染 |
| **DISC-07** 🟢 | **雙份組句**：前端 sentencePreview 與後端 _compose_full_sentence 並存 | 句子漂移風險 | v2：預覽也用後端句（calculate 回應已含句子，debounce 已存在，成本可接受） |
| **DISC-08** 🔴 | **case_no 以筆數產號**（`CASE-{count+1:05d}`） | 併發撞號（unique 爆） | v2：DB sequence 或 ULID |
| **DISC-09** 🟢 | **apply-back 破壞性覆寫**範本、無歷史 | 範本被覆蓋即失去舊版 | v2：組件版本不可變→apply-back＝發新版（impl-04 已定） |
| **DISC-10** 🟢 | **無分頁**（wi-library、sequences… `.all()`）；ILIKE 無索引 | 資料量大即劣化 | v2：一律分頁＋檢索走 ADR-016 基建 |
| **DISC-11** 🟢 | **型別紀律**：TMU 用 Float、id 用 String(36)、時間戳無 tz 一致性、`archive` endpoint 是空殼 | 精度/約束缺失 | v2：Numeric/UUID/timestamptz/CHECK（database-v2 慣例） |
| **DISC-12** 🟡 | **擁有權模型**：幾乎所有 workbench 資源都是「個人的」（created_by scoped），無廠級/全域治理；wi-library 搜尋範圍與 ownership 邊界不明 | 標準化資料需要治理層 | v2：scope=personal/site/global＋promote 審核（ADR-017）。**個人→標準的升級門檻需 IE 定義** |
| **DISC-13** 🟡 | **LevelSystemPage 名不符實**：只是 WI Set 唯讀檢視器，v3 沒有 Level System | 命名誤導 | v2 的 Level System（R1–R9）才是真的；三層的 L1/L2/L3 與 Level System 的 main/sub/cub **是不同概念**，文件用詞須嚴格區分（本庫一律稱「三層組裝」） |
| **DISC-14** 🟢 | **匯入 index 解析靠 regex `\(\d+\)`** 抓括號數字 | 格式稍變即靜默錯值 | v2：匯入器逐值對照驗證＋衝突報告（impl-01 §3 既定） |
| **DISC-15** 🟡 | **repeat_count 無上限**（前端僅 >5 提示） | 誤輸入 999 直接進工時 | v2 暫定 ≤99（impl-02 殘項 #4），**上限值需 IE 拍板** |

**🟡 兩項（DISC-12/15）仍開放**；DISC-01 已定案（見 §2.1）；其餘已由既有 ADR/裁決覆蓋，各 F 文件按建議欄撰寫。

### 2.1 DISC-01 詳解與裁決（✅ 2026-07-05：以二代三層為 canonical）

**「一代」「二代」都是 ddm-v3 內部的東西，與 ddm-v2 無關**——IE 在開發 v3 過程中先後做了兩套功能重疊的組裝系統，且兩套至今並存：

| | 一代（v3 較早） | 二代（v3 較晚、較完整） |
|---|---|---|
| 後端 | `routes/most.py`＋`wi_set_builder.py` | `most_workbench_v3.py`（1118 行） |
| 前端 | `/most-workbench`、`/wi-set-builder` | `/most-workbench-v3`（三分頁） |
| 一條動作 | MostSequenceItem | ActionModuleTemplate（L1） |
| 一句 WI | MostMiStatement（＋子快照 items） | WITemplate（L2，＋items） |
| 工序排列 | WISetProject（＋items） | ProcessRoute（L3，＋items） |
| 獨有能力 | — | 跨層「傳送至」、apply-back 回寫範本 |
| 已知缺陷 | WI Set 合計漏排 SIMO（bug，DISC-03） | — |

兩套做同一件事（動作→WI→工序），資料表、UI、合計邏輯各一份——非工程迭代「做了新版沒收舊版」的典型痕跡。

**裁決內容**：
1. v2 的使用邏輯以**二代三層**為準（F-03 canonical）；一代能做的二代全部涵蓋，F-02/F-04 僅保留行為規格（快照機制、搜庫收集心智）供 F-03 與 impl-04 引用，**v2 不建一代的資料層**。
2. 資料載體不受影響（兩代對映同一套）：L1/L2 → `motion_modules`（rows 1..n），L3 → ProcessVersion＋worksheet；apply-back → 發布模組新版本。
3. 若 v3 的一代資料（MiStatement/WISetProject）未來需遷移，路徑＝轉成 motion_modules ＋ worksheet 實體化列（屆時另立遷移計畫，不在本階段範圍）。

## 3. 可執行文件的撰寫規約（本資料夾所有文件遵守）

1. **兩分類**：`core-logic/`（CL-xx，計算與資料真理——實作前必讀）與 `features/`（F-xx，功能規格——可獨立分派給 AI 實作）。
2. **可執行性標準**：每份 F 文件含 目的與使用者故事／資料模型／行為規則／API 合約／驗證與錯誤／驗收條件（Given-When-Then）／v2 落地註記。一個 AI 只讀該 F 文件＋其引用的 CL 文件即可實作，不需回讀 v3 程式碼。
3. **v3 行為 vs v2 目標分離**：正文寫「應然」（已按裁決與 DISC 修正）；v3 原始行為若不同，以「（v3 實況：…）」註記——**絕不把 bug 寫成規格**。
4. 值一律引用 [impl-01](../impl/impl-01-rule-set-factory-v2.md) 的 V2 值表，不重複抄寫。
5. 引擎歸引擎：F 文件不得內嵌計算公式，一律引用 CL-01/CL-04。
