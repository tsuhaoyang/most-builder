# ADR-024: 主數據與字典的分界（「字典管理」更名為「主數據管理」）

**狀態：** accepted（2026-07-22，User 核可）
**日期：** 2026-07-22
**關聯：** [ADR-014](ADR-014-v3-dictionary-as-value-authority.md)（值權威）、
[ADR-021](ADR-021-ia-restructure-v3-parity.md)（IA，**本 ADR 修訂其側欄命名**）、
[ADR-022](ADR-022-workbench-two-layer-correction.md)（兩層工作台，**本 ADR 補其遺漏的資料遷移**）、
[ADR-023](ADR-023-dictionary-governance-unification.md)（字典治理）

## 脈絡

v2 側欄同時存在兩個都叫「字典」的入口，使用者指出這是 v3 沒有的混亂：

| v2 現況 | 內容 |
|---|---|
| 「字典管理」（analyst+） | 詞彙庫（`work_vocab_items`）＋ 範本庫（`motion_templates`） |
| 「MOST 字典」（admin） | rule-set 版本與規則值（ADR-023 D4 建立的兩層 UI） |

原始訴求是「v3 把字典管理與 rule-set 放在一起，v2 卻分開」。**但實地查證 v3 後，
結論與訴求的字面不同**——照抄 v3 會毀掉 v2 刻意建立的能力。

### v3 的實際結構（唯讀查證，2026-07-22）

v3 **所有東西都掛在字典版本底下**（四張表皆有 `dictionary_version_id` FK）：

```
dictionary_versions
├── sequence_models / parameter_slots / parameter_options   規則值
├── lexical_options                                          詞彙
├── most_sequence_items                                      動作
├── most_mi_statements                                       WI 語句
├── action_module_templates                                  動作模組池
└── wi_templates → wi_template_items                         WI 範本
```

這就是 v3 的「字典管理」是單一入口的原因：**字典版本是所有東西的容器**。

### v2 已經在三處刻意偏離 v3，且都有理由

| 概念 | v3 | v2 | v2 偏離的理由 |
|---|---|---|---|
| 詞彙 | `lexical_options` 掛在字典版本下，版本刪除即 CASCADE | `work_vocab_items` 獨立表，另有 `site_id`／`external_code`／`source_system`(local/mes/erp/plm) | v2 要從 **MES/ERP/PLM 同步**廠內物料與工具；那是廠內現況，不該隨一份工時字典的版本被刪 |
| 動作模組 | `action_module_templates` 掛在字典版本下 | `motion_modules` 有**自己的版本鏈**（`motion_module_versions`），每版凍結當時的 `rule_set_id` | 與 ADR-023 §3.4 回放鐵則同一套邏輯：字典換版，舊模組仍可回放原值。ADR-022 已評為「正確設計，保留」 |
| 關鍵字比對範本 | **無對應概念** | `motion_templates`（`keywords` ＋ `cycle_template` ＋ `seq_kind`） | 為「匯入 Excel 工序表 → 自動建模」而設計（P2）；v3 沒有此需求 |

## 決策

### 1. 分界原則：版本的依據是「是否影響工時計算」

- **會影響計算結果 → 必須可回放 → 有版本**
- **是廠內現況（物料/工具/廠區）→ 跟著現實走 → 無版本**

依此，v2 有**三類**物件，不是兩類：

| 類別 | 內容 | 版本語意 | 歸屬入口 |
|---|---|---|---|
| **字典**（規則值） | `rule_sets` ＋ 12 張子表 | 單一 active，clone-on-write，回放鐵則 | 「MOST 字典」（admin） |
| **主數據** | 詞彙庫 `work_vocab_items`、範本庫 `motion_templates` | **無版本**，跟隨現實；可從外部系統同步 | 「主數據管理」（analyst+） |
| **業務產出** | `motion_modules`（動作／WI 範本）、`process_versions`（案件） | **自有版本鏈**，快照所用的 rule-set id | 「MOST 工作台」／「分析案件」 |

**動作模組既不是主數據也不是字典**，不得搬入「主數據管理」。

### 2. 「字典管理」更名為「主數據管理」

「字典」一詞在 v2 僅指 **MOST 規則值**。詞彙庫與範本庫是主數據。

**本 ADR 修訂 ADR-021 側欄表**（該表第 6、8 項）：

| # | ADR-021 原文 | 修訂為 |
|---|---|---|
| 6 | 字典管理 ｜ 詞彙庫＋範本 ｜ `features/dictionaries/` | **主數據管理** ｜ 詞彙庫＋範本庫 ｜ `features/dictionaries/` |
| 8 | Rule-set（admin）｜ rule-set **檢視** ｜ `features/rule-set/` | **MOST 字典**（admin）｜ rule-set 版本與規則值**完整治理**（ADR-023）｜ `features/dictionary/` |

> 第 8 項在 ADR-023 D4 落地時即已改名並替換模組（`features/rule-set/` 已刪），
> 但當時**未修訂 ADR-021**，造成 ADR 與程式碼不一致。本 ADR 一併補上。

側欄總數不變（一般 7 項＋admin 2 項）。

#### 與 checklist L-03 的關係（名字還給正確的繼承者）

v2 曾有一個叫「主數據」的 tab（`features/master-data/MasterData.tsx`，標題「主數據 / 詞彙庫」），
於 `34679f7` 退役——**退役原因正是它的詞彙 CRUD 被本頁（當時叫「字典管理」）吸收**。
`features/master-data/` 現只剩 `api.ts` 供工作台複用，無頁面、無路由。

checklist L-03 的守衛測試原本以「側欄不含『主數據』字樣」當代理，本 ADR 更名後該代理失效。
**L-03 的語意應重述為「舊 `MasterData` 元件未以獨立入口復活」，而非「『主數據』是禁用詞」。**
測試已改為斷言原始意圖且更強：主數據入口 `toHaveCount(1)` 且 `toHaveText(/主數據管理/)`
——舊 tab 復活會讓 count 變 2（保住原意圖），更名被還原會讓 text 不符（新增覆蓋）。

### 3. 範本庫保留，但需補完兩件事

範本庫是「常見動作 → 完整 MOST 七格填法」的關鍵字對照表。例：

```
鎖附螺絲  keywords=[screw, lock, tighten, fasten, 鎖, 螺絲]  seq_kind=CM
          A 伸手18cm → G 抓握 → M m_screw 轉1圈 → I 檢查 → X 無
```

用意：匯入工序表時，「鎖附 M3 螺絲 ×4」這行可經關鍵字命中，直接套出算好 TMU 的
MOST row，IE 只需核對微調，不必 200 行從零建模。

**保留（User 裁決，2026-07-22）**，但目前是半成品，需補：

1. **`/motion-templates/match` 無生產消費者**——端點與資料都在，但沒接到匯入流程。
   P2 要把它接上，否則範本庫對使用者只是一份看得到、用不到的清單。
2. **16 筆範本的 `cycle_template` 內寫死 `"rule_set_code": "MINIMOST_FACTORY_V1"`**
   ——V1 是 legacy 版本。ADR-023 D1 已清除程式碼中所有寫死的 rule-set code，但
   **資料內部的這一份沒被清到**。接上匯入後會用 V1 值算出靜默錯誤的 TMU。
   應移除該欄位、於套用時解析 active（ADR-023 §3.5）。

### 4. `motion_modules.category` 的語意收斂

`category` 目前是**無 CHECK 約束**的 text 欄（`scope`／`status` 都有 CHECK，僅它沒有），
且歷史上承載過**兩種語意**：

- ADR-022 的兩層判別值：`action` ／ `wi-template`
- 領域分類：取放／組裝／鎖附／搬運／貼附／拆解／操作／檢測

**裁定：`category` 只作為 ADR-022 的兩層判別值**，不得再承載領域分類。
須加 CHECK 約束擋住第三種值（含 NULL——NULL 的模組同樣兩層皆不屬，會重演隱形問題）。

## 事後剖析：16 筆隱形模組（2026-07-22 已清理）

`migrations/versions_v2/v2_0012_motion_templates_seed.py`（impl-04）把範本庫 16 筆
轉為 `motion_modules` ＋ `motion_module_versions`，**`category` 原封抄自 `motion_templates`
（中文領域分類），`total_tmu/total_seconds` 留 0 作 placeholder**。

其後 **ADR-022 把 `category` 的語意改為兩層判別值，但未遷移既有資料**。於是這 16 筆
落在舊語意裡：工作台濾 `action`、WI 庫濾 `wi-template`，**兩邊都不列出** → 完全隱形。

清理前逐筆查核：來源（範本庫同名列）全部仍在、`total_tmu` 全為 0、無任何 `wi_rows`
引用。已備份為 JSON 後刪除，`motion_modules` 現只剩 `action`(29) 與 `wi-template`(15)。

**教訓：改變一個欄位的語意時，必須同時遷移既有資料，否則舊語意的列會變成無人看得見
的孤兒。** ADR-022 當時只改了讀取端的過濾條件，沒有處理已存在的列。

## 5. 詞彙庫 vs 同義詞的分界（D5 補定，原「未決」）

原列為未決，本節定案。查證 `synonym_service.create_synonym` 後發現兩者關係比「各屬一邊」
更精確——同義詞是一個**別名層**，它可以指向規則選項，**也可以指向詞彙庫項**
（`parameter='vocab'` → 驗 `work_vocab_items.external_code`）。所以分界不是「切成兩半」，
是「實體 vs 對實體的稱呼」：

| | 詞彙庫 `work_vocab_items` | 同義詞 `rule_option_synonyms` |
|---|---|---|
| 是什麼 | **廠裡有哪些東西**（物件/工具/元件…），獨立實體 | **某個東西/選項還能怎麼被稱呼**，別名，不獨立存在 |
| 指向 | —（它本身就是被指的） | 規則選項（b/g/p/m/x/i）**或**詞彙庫項（`vocab`） |
| 歸屬 | 主數據（無版本，可 MES/ERP 同步） | 字典（掛 `rule_set_id`，隨版本走） |
| 影響 | 建模素材 | **只影響建議/搜尋層，不影響工時**（ADR-014） |
| 可變性 | 隨現實增刪 | **published 版本唯一可後補的資料**（ADR-014）；draft/published 可增刪，**retired 不可**（終態） |

**關鍵推論**：

1. **同義詞 CRUD 屬 MOST 字典頁**（掛在 rule-set 選項下，在 `features/dictionary/OptionEditor`
   內），不屬主數據頁——即使某條同義詞指向的是詞彙庫項，那條「別名」仍是隨字典版本演進的
   建議層知識（例：「機台」是 `x_none` 的別名，是這一版字典的認定）。
2. **同義詞 CRUD 不觸發 clone-on-write**：改 TMU 值要 clone（ADR-023），但同義詞是 ADR-014
   明定的例外——可直接後補到 published/certified 版本。前端對同義詞的寫入**必須繞過**
   OptionEditor 的 clone 攔截，否則會出現「要加個別名卻被要求先建草稿」的錯誤行為。
3. **retired 版本不可增刪同義詞**（終態）。ADR-014 只說 published 可後補，retired 是終態的
   直接推論。後端 `create_synonym`/`delete_synonym` 目前**未擋 retired**，D5 補上。
4. RBAC：同義詞只影響建議層不影響工時，故 `analyst` 可改（維持現況），不需 approver。

## 後果

- 好處：「字典」一詞在 v2 只有一個意思；三類物件的版本語意各有明確依據，不再靠慣例。
- 代價：`features/dictionaries/` 的模組名與路由 id 仍是 `dictionaries`（僅改顯示名稱與
  導覽語意）。若日後要連模組名一起改，屬獨立重構，不在本 ADR 範圍。
- 邊界：本 ADR **不**把詞彙庫併入字典版本（即不照抄 v3）。若日後 MES/ERP 同步這條線
  確定不走，該決定需要新的 ADR 推翻本條，而非默默改回。
