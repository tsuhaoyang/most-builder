# ADR-023：字典管理統一 — active 旗標、選項級編輯、與 ADR-014 的調和

- **狀態**：Accepted（使用者/IE 指示於 2026-07-20；協調者裁決）
- **決策者**：Howard（IE）＋ 審查總召
- **關聯**：**ADR-014（值權威）— 本 ADR 為其執行細則，不推翻其原則**；ADR-021（IA）、ADR-022（兩層工作台）、[v2 權威模型守則](../architecture/v2-authoritative-model-guide.md) §5
- **本文件是 P2 所有派工的必讀母版。**

## 1. 背景與三個推翻性發現

使用者指出：v3 的字典管理是**單一入口的兩層結構**（版本清單 → 點進版本編輯該版所有字典設定），而 v2 拆成不相干的「字典管理」（詞彙庫）與「Rule-set」（唯讀參數表）兩個 tab。經 Playwright 實操 v3 ＋ 程式碼深度對照，三項與原假設不符：

**發現 1｜v2 後端已有版本生命週期，缺的是 active 旗標、選項粒度與前端。**
`api/routes/v2/rule_set.py` 已有 `list`/`full`/`clone-draft`/`put-full`/`publish`，服務層 `rule_set_service.py:92-146` 含 draft-only 凍結與 audit log。`RuleSetViewer.tsx:74` 寫「編輯/版本化為後續功能」是**前端文案落後於後端事實**。

**發現 2｜v3 的 archive 是無效程式碼，不得照抄。**
`dictionaries.py:410-422` 檢查 `is_active` 後只 `db.commit()`，**無任何欄位變更**——`DictionaryVersion` 根本沒有 status/archived 欄，只有 `is_active`。v3 UI 的「封存」按鈕點下去除了跳成功訊息什麼都不做。**v2 的 `status IN ('draft','published','retired')` 語意嚴格優於 v3，retired 就是 archive，已存在。**

**發現 3｜v3 有 work_vocab_items 的對應物（LexicalOption），但 v2 的設計較佳，不向 v3 靠攏。**
v3 `lexical_options` 綁 `dictionary_version_id` CASCADE（換字典版本＝物件清單重建）；v2 `work_vocab_items` 是全域主數據，帶 `source_system IN ('local','mes','erp','plm','imported')` 供 PLM/MES/ERP 介接。**保留 v2 設計**，但它不該叫「字典」。

## 2. 結構性約束：為什麼不能照抄 v3 的 CRUD

| | v3 | v2 |
|---|---|---|
| 選項模型 | **單一泛型表** `parameter_options`，7 參數共用（`option_code/display_text_zh/tmu_value/...`） | **12 張專用子表**，因參數語意不同構 |
| A | 同一張表的選項 | `rule_a_bands`＝**區間帶**（component/max_value/index_value），無「選項代碼」概念 |
| P | 同上 | `rule_p_bases` ＋ `rule_p_addons`（兩張，addon ≤2） |
| M | 同上 | **五張**：verbs / ladder_bands / foot_bands / rotation_bands / hand_bands |

**結論：v3 的「七個參數分頁」是 UI 概念，v2 照抄；但 v3 的「一套 `PUT /options/{id}` 打天下」在 v2 不可能成立。** v2 的選項級 CRUD 必須是每參數一組端點（P/M 需分頁內次級 tab）。

**帶型（band）vs 選項型（option）的分界（2026-07-21 修正：原文只提 A，實作時發現 M 的四張子表同屬帶型）**：
- **帶型**＝`rule_a_bands`（reach/twist/foot）＋ `rule_m_ladder_bands` / `m_foot_bands` / `m_rotation_bands` / `m_hand_bands`。**無 `code` 欄，無法以 `options/{option_code}` 定址**；且帶界必須整體遞增無重疊，逐筆編輯會產生非法中間態 → **一律整組替換**（`PUT /params/{A|M}/bands`），驗證：遞增／無重疊／open-ended 僅末位；rotation 依 `revolutions` **分組**各自成序。
- **選項型**＝b / g / p_bases / p_addons / m_verbs / x / i → 選項級 CRUD。
- **帶界驗證不得只掛在 `PUT /bands`**：`PUT /full`（`replace_children`）必須套用同一組驗證，否則整組替換的立論被姊妹端點架空（D2 code-review HIGH-2；rotation 是唯一不經 `_sort_bands` 排序的帶族，錯序會靜默算出錯誤 TMU）。
- **A 帶的靜默夾取風險**：`rule_set_data.py:63` 對 A 帶超界輸入 `return bands[-1][1]`（**唯一會靜默夾取的一族**；ladder/hand 回 range 錯誤）。故物理無上界的 `A.reach`/`A.foot` 末帶應為 open-ended；`A.twist`（180° 物理有界）可為有限值。

## 3. 決策

### 3.1 命名（UI 層改名，資料層不動）

| 現況 | 改為 | 理由 |
|---|---|---|
| tab「Rule-set」 | **「MOST 字典」** | 這才是 v3 心智模型的「字典」 |
| tab「字典管理」（詞彙庫＋範本） | 詞彙庫 → **「主數據」**；範本庫歸屬待 ADR-021 後續裁決 | 「字典」之名必須讓給 rule-set |
| 表 `rule_sets` / API `/api/v2/rule-sets` | **保持不變** | 改名成本高、風險大；「rule set」在工程層準確。**UI 稱字典、資料層稱 rule-set，兩者同物**（本 ADR 明記） |

### 3.2 版本生命週期（v2 保持四態，比 v3 精確）

`status ∈ {draft, published, retired}` × `is_active ∈ {true,false}`：

- **clone-draft**：`new_code` 改選填，缺省自動生成 `{code}_DRAFT_{YYYYMMDDHHMM}`（須查重附序號，code 有 UNIQUE）
- **publish**：`draft → published`，**新增發布前驗證**＝`load_rule_set_from_db(code).validate_complete()`（引擎自己的完整性契約，比 v3「數一數有沒有選項」精確，且保證 activate 後不會 runtime 才炸）
- **activate**（v2 全新）：前置 `status='published'` ＋ `validate_complete()` ＋ 寫 audit log；實作為同交易「先全體 deactivate → 再單一 activate」，**並加 partial unique index** `CREATE UNIQUE INDEX ... ON rule_sets ((true)) WHERE is_active`（比 v3 多一道 DB 防線，併發雙 activate 會撞 unique 而非靜默雙 active）
- **retire**（＝v3 的 archive，但真的會生效）：`status='retired'`，前置 `is_active=false`

### 3.3 與 ADR-014 的調和（本 ADR 的核心）

ADR-014 約束的是**「認證版本的值」**，不是「禁止一切線上編輯」。其否決選項 B 的理由是「破壞既有 cycle 快照回放；違反 published 凍結原則」——**否決的是改 published 版本**。而 v2 的 `replace_children` 已強制 `status != 'draft'` → 409，凍結機制已存在且正確。

**四條規則（全部可機械驗證）**：

**規則 1 — 三層可變性矩陣**

| 資料 | draft | published(非 active) | published+active | retired |
|---|---|---|---|---|
| 子表選項值（TMU/帶界/code） | ✅ | ❌409 | ❌409 | ❌409 |
| 標籤/句子文字（`_zh`） | ✅ | ❌409 | ❌409 | ❌409 |
| **`_en` 標籤／句子文字**（`label_en`／`sentence_text_en`） | ✅ | **✅** | **✅** | ❌ |
| **同義詞** | ✅ | **✅** | **✅** | ❌ |
| 版本 metadata（name/notes） | ✅ | ✅ | ✅ | ✅ |
| `is_active` | ❌（須先 publish） | ✅ activate | ✅（他人 activate 時隱含 deactivate） | ❌ |
| `status` | →published | →retired（須先 deactivate） | ❌ | 終態 |

同義詞那格是 ADR-014 白紙黑字授權：「published rule-set 唯一可後補資料＝同義詞（僅影響建議層不影響工時）」。

**`_en` 那格是 [ADR-032](ADR-032-bilingual-ui-and-data-label-layer.md) D4 修訂本規則新增的一列**（2026-08-18）：
`label_en`／`sentence_text_en` 在 draft、published(非 active)、published+active 皆可後補寫入，僅
`retired` 終態不可寫——**論證見 ADR-032 D4，不在此重複**（摘要：`_en` 的性質比同義詞更弱，
在 ADR-032 I3 的約束下純顯示、連建議層都不影響，既然更弱的同義詞被允許後補，更強的沒有理由被凍結）。
`_zh` 標籤／句子文字仍維持原本的 draft-only（❌409），未被本次修訂觸及。

**規則 1 補節 — 同義詞的鍵與偏好序（v2_0038 / D3-017；2026-08-16 補記）**

- **UNIQUE 新定義**：`UNIQUE(rule_set_id, parameter, synonym_norm, option_code)`（migration
  v2_0038，取代原 `UNIQUE(rule_set_id, parameter, synonym_norm)`）。放寬動機＝D3-017 的 IE
  情境裁決：「放至/放置」一個詞面需掛兩個變體 code（`p_place_single`／`p_place_none`），
  舊鍵下第二個變體登不進去、`priority` 欄形同虛設。
- **priority 語意**：偏好位次——**數字小者優先，0＝預設**。parser 端 tie-break
  （`nlp/lexicon.py` build_lexicon：同 norm 以 (priority, option_code) 升冪）與
  `list_synonyms` 排序同一語意；同 priority 時以 option_code 字母序收尾保證決定性。
- **H1 的殘留風險與本次補救（D3-018）**：放寬後「同面兩個 code 撞同一 priority」DB 不再
  擋——parser 會按 option_code 字母序**靜默擇一且不標 review**（審查實測：g_grasp／g_touch
  同掛「握住」priority 0 → 永遠選 g_grasp、g_touch 不進 top_k、TMU 錯且無旗標）。補救＝
  service 層 `create_synonym` 擋「同 (rule_set, parameter, synonym_norm) 已存在**其他**
  option_code 且 priority 相同」→ 409 `SYNONYM_PRIORITY_COLLISION`（一面多 code 必須以
  不同 priority 顯式宣告偏好序；手滑撞面被擋、刻意變體放行）。**已知邊界**：service 層
  守門無 DB 約束背書（並發雙寫可穿透）；同面變體整組注入 top_k 的通則化（目前僅 P 方向
  變體有情境規則處理，其他面第二變體不進 top_k）記後續票（worklog D3-018）。
- **P 方向名詞清單暫住程式碼的理由與畢業條件**：機構件／盤面分類清單（`nlp/linking.py`）
  是 IE 情境裁決的單一出處，暫以程式碼常數承載——語料 60 筆、成員穩定、逐項附證據，且
  單一出處供生產 nl-draft／gold_eval 重放／harvest 三方共用。**畢業條件**：清單成為 IE
  常態維護對象（新增站別／料件需 IE 自行增修）時，遷進 rule-set 子表走本 ADR 治理
  （值版本化＋clone-on-write）。

**規則 1 補節二 — 同義詞登記的合法來源（D3-028；2026-08-17 IE 指示後補立）**

> **同義詞登記的合法來源只有二：(a) 該詞出現在對應選項自己的標籤/句面文字裡
> （正規化後子串比對），或 (b) 有明確的 IE 裁決紀錄。工程端不得以相似性自行判定。**

**為什麼要立這條**：D3-028 覆核時工程端提了兩條候選同義詞——「下壓≈按壓 →
`m_press`」「按下≈按動按鈕 → `m_btn`」。IE 反問：「動詞應該要按照 most 字典庫
去查吧？」這一問點破了一個治理漏洞：**同義詞決定 option code，option code 決定
TMU**。規則 1 允許 published/active 版後補同義詞，理由是「僅影響建議層不影響
工時」——那句話只在「詞是從字典本身衍生的」前提下成立。一旦工程端可以憑語意
相似度自己造映射，工時映射就變成工程判斷，ADR-014 的值權威（改值只能改 JSON →
重跑腳本 → 新版本）被從側門繞過，而且**沒有任何機制會發現**。

**22 條現況的分類（2026-08-17 逐條查證，`MINIMOST_FACTORY_V2`）**：

| 類別 | 條數 | 說明 |
|---|---|---|
| (a) 標籤衍生 | **21** | 詞與該 option 的 `label_zh`／`sentence_text_zh` 有子串關係 |
| (b) IE 裁決 | **1** | 「插入」→ `p_asm_single`（D3-021：照放置邏輯、多費力＝base+addon） |

(a) 的子串關係**雙向**都算，因為兩種寫法都真實存在：

- 詞 ⊆ 標籤：`拿取` ⊆ `拿取(選取)`、`確認` ⊆ `並確認(正常視線範圍)`、
  `清潔` ⊆ `並吹風清潔`、`鎖附` ⊆ `並鎖附固定(鎖附順序如圖所示)`；
- 標籤 ⊆ 詞：`放` ⊆ `放至`/`放置`、`組` ⊆ `組至`/`組於`、`推` ⊆ `推至`、
  `拉` ⊆ `拉至`、`丟` ⊆ `丟至`——**字典的句面用單字動詞，工單寫的是帶方向
  補語的複合詞**。只驗單向會誤殺 10 條既有登記。

唯一例外「插入」與 `p_asm_single`（標籤`組(一種方向)`／句面`組`）**兩個方向都
不成立**，靠 (b) 的 IE 裁決成立——這正是 allowlist 要存在的理由。

**為什麼字典本身給不了 alias**：v3 認證字典
`docs/v3/reference/minimost_ai_dictionary_v1.json` 的欄位已逐一查證，
**沒有 alias/synonym 欄位**可匯入；`import_v3_dictionary.py` 因此也產不出同義詞。
(a) 只能靠選項自己的標籤/句面文字，這是現況的天花板，不是實作偷懶。

**這條規則守的是 provenance，不是語意正確性**（誠實邊界，必須寫明）：
同一參數下**多個 code 共用同一詞素**時，本規則**判斷不出選了哪個 code**——
而那正是決定 TMU 的那一步。實例：P 的 `p_place_none`（標籤`放(無方向)`／句面
`放`）、`p_place_single`（`放(一種方向)`／`放`）、`p_asm_single`（`組(一種方向)`／
`組`）——「放至」對前兩個 code 都通過 (a)（現況也真的兩條都登記了，靠
priority 0／1 表達 IE 的情境裁決 D3-017），但「放至該算單方向還是無方向」這條
規則一句話都說不出口，兩者的 P 值不同、TMU 就不同。

它擋掉的只有一件事：「字典裡完全沒有這個詞素」的相似性判斷。**選哪個 code**
由 IE 覆核、priority 偏好序與黃金測試承擔。要收緊就得等字典本身長出 alias 欄位
（見上），不是把這個測試調嚴。

**機械守門（不新增 DB 欄位、無 migration）**：
`tests/integration/test_synonym_registration_governance.py` 對 DB 現存**每一條**
`rule_option_synonyms` 斷言 (a) 或 (b) 成立；(b) 的例外走 repo 側 allowlist
（鍵＝`(parameter, synonym_norm, option_code)`，值＝裁決引用如「D3-021」；比照
`SEED_GOLD_IDS` 白名單模式——例外要進版控、被 review、可 grep），並附
「allowlist 不得有已撤銷登記的殘留條目」「每條都要指得出輪次」兩條衛生檢查。
mutation：塞相似性判斷的假同義詞（純函式與**真寫進 DB** 兩版）→ 紅；
allowlist 清空 → 「插入」那條紅；`label_derived` 恆真 → 紅。
`parameter='A'`／`vocab` 無可定址選項標籤 → fail-closed 判為未授權
（`create_synonym` 對 A 刻意跳過 option_code FK 驗證，這條路徑寫得進 DB）。

**機械守門的範圍聲明（D3-030 M2；別把它讀成全覆蓋）**：守門判定的是**測試
執行當下 DB 裡現存的每一條**同義詞，而 CI／新環境裡那批資料的來源就是版控的
種子腳本 `scripts/dev_seed_synonyms.py`（22 條，逐條標註 IE 裁決輪次）——
換句話說，**實際被機械檢查的是版控詞典**。它**不涵蓋**執行期 IE 走
`POST /api/v2/rule-sets/{code}/synonyms` 的即時登記：那條路徑寫進去的條目在
下一次守門測試跑到那個環境之前，沒有任何機械檢查會看它一眼（生產環境根本
不跑測試）。**準則要不要下沉到 `create_synonym` API 本身**（登記時就以標籤
衍生／allowlist 判定，違反回 409）＝已記票、本輪不做：值域判定要能引用 IE
裁決紀錄，而裁決紀錄目前住在 repo（allowlist），API 端取用需要另一套載體。

**未登記的處理（D3-028 實例）**：「下壓」「按下」**不登記**，兩筆草稿
（`0e83128f`「下壓 CPU 拉桿鎖定」、`00104439`「按下電源測試按鈕」）留在
`tests/gold/wi_plans_draft/`，卡點記為「動詞不在字典標籤內、無 IE 裁決」。
解鎖路徑二選一：IE 裁決（→ allowlist ＋ 登記）或字典本身新增該詞面
（→ 改 JSON、重跑 converter、新版本，走 ADR-014 既有路徑）。

**規則 2 — clone-on-write（照抄 v3 最好的設計）**
使用者在 published/active 版按編輯 → 確認對話框「是否建立草稿版本後編輯？」→ 自動 clone → 切到 draft 續編。**使用者從不撞 409**，凍結規則透過 UI 流程自然滿足。

**規則 3 — 認證血緣 `provenance`（v2 新增，v3 無）**
`rule_sets.provenance ∈ {certified_import, manual, cloned}`：
- `certified_import`＝由 `import_v3_dictionary.py` → seed → `dev_seed_v2.py` 產生（V1/V2 屬此）
- **`provenance='certified_import'` 的版本，任何選項級寫入或 `PUT /full` 一律 409，即使 status='draft'。**
  - **唯一例外＝`_en` 標籤／句面**（規則 1 那一列，ADR-032 D4）：走**另一條並列的 gate**
    `rule_set_service.assert_en_editable()`（只擋 `retired`，不看 `provenance`），
    端點 `PATCH /rule-sets/{code}/params/{param}/options/{option_code}/en`，
    欄位白名單只有 `label_en`／`sentence_text_en`。**規則 3 本身沒有被放寬**：
    `assert_editable()` 一個字沒改，值與 `_zh` 對認證版本仍然一律 409
    （對照測試：`tests/integration/test_i18n_review_mutations.py::
    test_ordinary_option_patch_on_certified_rule_set_is_still_409`）。

這讓 ADR-014 的「認證版本禁手改」從文件約定變成 **DB 可驗證的規則**。IE 要改認證值只有一條路：改 JSON → 重跑腳本 → 新版本。

**規則 4 — activate 雙重把關**：`status='published'` ＋ `validate_complete()` ＋ audit log。這是替代 IE 認證的最低治理門檻。

### 3.4 回放安全（不可違反的鐵則）

三處 FK 皆 `RESTRICT`（`most_cycles.rule_set_id`、`motion_module_versions.rule_set_id`、`most_worksheets.default_rule_set_id`）→ DB 層已擋死「刪掉被引用的 rule_set」。`load_rule_set_from_db(session, code)` **只依 code 查表，不看 status 也不看 is_active** → retired 版本仍可載入計算，回放能力天然保留。

**明文禁令（必須寫進 CI_GATES）**：
1. **`load_rule_set_from_db` 永遠不得依 status/is_active 過濾。回放路徑不看治理狀態。**
2. 治理狀態只在「選擇」時生效（`GET /rule-sets?selectable=true` 只回 published+active 供 UI 下拉），不在「載入」時生效
3. 新增整合測試：建立引用 retired 版本的 cycle → retire → 重算 → TMU 不變
4. worksheet 的 `default_rule_set_id` 是**建立時凍結的快照**，retire 不回溯改寫；但工作台須顯示警示徽章「本工序表使用已下架規則版本 X」

### 3.5 修正既存 bug：V1/V2 分裂的機械成因

`schemas/v2/most.py:12` 的 `DEFAULT_RULE_SET = "MINIMOST_FACTORY_V2"`，但 `catalog_service.py:127` 新建 worksheet 寫死 **V1**、`worksheet_service.py:58` 空 rows 存檔 fallback **V1** → **同一 worksheet 的 default 是 V1、rows schema default 是 V2**。前端同樣不一致（`config.ts` V2、`wi-workbench/api.ts:20` 預設 V1、`RuleSetViewer.tsx:58` 初始 V1）。

**第三個路徑（2026-07-20 補：原規格漏列，由 D1 code-review 發現）**：`services/v2/import_service.py:170-175` 用 `select(RuleSet).order_by(created_at.desc()).limit(1)` 當 fallback——不是寫死字串，但同樣繞過 active，且**本 ADR 讓它更危險**：clone-draft 支援自動命名後，「最新建立的 rule_set」極可能是未發布的 draft clone，會讓匯入的 rows 用未過 `validate_complete()` 的規則集計算。**一併改讀 active。**

**規格**：新增 `get_active_rule_set()/get_active_rule_set_code()`；上述所有寫死處**與隱式預設處**改讀 active；**移除 `schemas/v2/most.py` 的 `DEFAULT_RULE_SET`**（Pydantic 層無 session，不該持有值權威）；前端刪 `ACTIVE_RULE_SET` 常數改用 `GET /api/v2/rule-sets/active` ＋ `useActiveRuleSet()` hook。

**部署面行為變更（須寫進 release note）**：全新部署且 `DDM_SEED_DEMO=false` 時，庫內零 rule_sets → `POST /skus/{id}/worksheets` 會 500（`NoActiveRuleSet`），而非如舊版靜默寫入 `default_rule_set_id=NULL`。這是「不得靜默寫 NULL」的預期結果。

Migration 資料遷移：`is_active=true WHERE code='MINIMOST_FACTORY_V2'`；`provenance='certified_import' WHERE code IN (V1,V2)`；**V1 保持 published + inactive**（回放版本，永遠可載入但不再被選中）。

### 3.6 匯出/匯入

- **匯出**：`GET /rule-sets/{code}/export` 回 `load_full()` 形狀 ＋ `{schema_version, exported_at, exported_by}`。**與 `PUT /full` 對稱**，形成 export→離線編輯→import 閉環。**不得**輸出成 `minimost_ai_dictionary_v1.json` 格式——那份 JSON 是**輸入**（方向：JSON → seed → DB），反向產生會製造第二個值權威來源。
- **匯入**：`POST /rule-sets/import` 只吃 export 形狀、**只建 `status=draft, provenance=manual`**。
- **CLI 匯入路徑不得 HTTP 化**：`scripts/import_v3_dictionary.py` 走 git 有三個 v3 沒有的性質——(a) 生成的 seed 進版控、值變更有 diff 可 review；(b) 過 CI Gate 3 黃金測試才能 merge；(c) 未知 option_code 硬中止（`_die()`）確保無靜默降級。做成上傳按鈕＝把值權威交給 runtime。

### 3.7 不移植的 v3 功能

| v3 功能 | 裁決 |
|---|---|
| `archive` 端點 | 無效程式碼（發現 2），v2 用 retire |
| `sequence_models` / `parameter_slots` 表 | v2 序列與格位硬編碼於引擎，是**刻意差異**（引擎權威），不搬 |
| `suggest-code` | P3 或不做。v3 的 `_ZH_TO_CODE` 對 v2 無用（v2 用 `g_grasp` 小寫短碼）；若要做可反轉 `import_v3_dictionary.py` 既有對照表 |
| 泛型 `PUT /options/{id}` | 結構不同構（§2），改每參數端點 |
| `lexical_options` 綁版本 | v2 主數據設計較佳（發現 3） |

## 4. 實施批次（依賴鏈：D1 → D2 → {D3,D4} → D5；D6 獨立）

| 批次 | 內容 | Migration |
|---|---|---|
| **D1** | 後端：`is_active`＋`provenance`＋partial unique index；`activate`/`retire`/`GET active`；publish 加 `validate_complete()`；clone-draft 自動命名；**兩處寫死 V1 改讀 active**；replay isolation 整合測試 | **有**（v2_0020） |
| **D2** | 後端：選項級 CRUD（每參數端點＋P/M 次級 section；A 與 M 帶型整組替換）＋`assert_editable` 統一 gate（certified_import/非 draft → 409）；12 張子表加 `is_active` | **有**（v2_0021） |
| **D3** | 後端：export/import draft | 無 |
| **D4** | 前端：統一兩層字典 UI（L1 版本清單＋L2 七參數分頁＋選項 dialog）；clone-on-write；刪 `ACTIVE_RULE_SET` 改 hook | 無 |
| **D5** | 前端：詞彙庫改歸「主數據」；範本庫歸屬待 ADR-021 裁決 | 無 |
| **D6** | 文件/CI：本 ADR、ADR-014 加「後續」段、CI_GATES Gate 5 擴充＋新增「恆有且僅有一個 is_active」 | 無 |

**未涵蓋（獨立小批次）**：`catalog_service.py:125` 的 `version_no = COUNT+1` 併發撞 unique（與字典治理正交，見 guide §5-4）。

## 5. 驗收協定（沿 ADR-021/022）

每批：typecheck/build/e2e 綠 ＋ agent 附 Playwright 截圖 ＋ **協調者親自核圖對照 v3** ＋ code-reviewer 過 → 才 commit。**黃金錨 GM=28/CM=29 與 V1 回放在每批後不得漂移**；D1/D2 需 ddm-validator 席位驗證。
