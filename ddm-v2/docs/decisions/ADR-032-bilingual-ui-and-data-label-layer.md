# ADR-032：雙語（中／英）支援 — UI 外殼與資料標籤層

- **狀態**：**accepted**（2026-08-18，User 核可）
- **日期**：2026-08-18
- **決策者**：Howard（IE，2026-08-18 裁決範圍與權威模式）＋ 架構師（論證與資料模型提案）
- **關聯**：
  - [ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（加法演進——本 ADR 全部變更皆為加法）
  - [ADR-014](ADR-014-v3-dictionary-as-value-authority.md)（值權威；同義詞＝published 唯一可後補資料的先例）
  - [ADR-021](ADR-021-ia-restructure-v3-parity.md)（UI 母版＝v3——**本 ADR 是刻意的加法偏離，見 D3.3**）
  - [ADR-023](ADR-023-dictionary-governance-unification.md)（字典治理——**本 ADR 修訂其規則 1 矩陣，見 D4**）
  - [ADR-024](ADR-024-master-data-vs-dictionary-boundary.md)（主數據 vs 字典權責——待審清單的角色歸屬依此）
  - [ADR-026](ADR-026-wi-ai-parser-pipeline-boundary.md)（AI parser 邊界——第三層英文 NLP **不在本輪**）
  - 被本 ADR 取代的草稿：[`docs/roadmap/phase5-i18n-full-bilingual-spec.md`](../roadmap/phase5-i18n-full-bilingual-spec.md)（2026-06-21，從未實作）

---

## 1. 脈絡

### 1.1 roadmap 草案的認知落差：不是「補完一半」，是從零開始

草案〈現況（已有的一半基礎）〉宣稱資料標籤層「已有欄」＝已有基礎。**逐表實測（2026-08-18，
`ddm_v2_most`）證明欄位存在但值全空**——欄位不是基礎，值才是：

| 表 | 欄 | 列數（V1 ＋ V2） | 非空 |
|---|---|---|---|
| `rule_b_options` | `label_en` | 4 ＋ 4 | **0** |
| `rule_g_actions` | `label_en` | 11 ＋ 11 | **0** |
| `rule_p_bases` | `label_en` | 7 ＋ 7 | **0** |
| `rule_p_addons` | `label_en` | 5 ＋ 5 | **0** |
| `rule_m_verbs` | `label_en` | 15 ＋ 16 | **0** |
| `rule_x_options` | `label_en` | 4 ＋ 11 | **0** |
| `rule_i_options` | `label_en` | 4 ＋ 9 | **0** |
| `work_vocab_items` | `name_en` | 59 | **0** |
| `sites` / `products` / `skus` | `name_en` | 1 / 1 / 1 | **0** |
| `motion_templates` | `name_en` | 16 | **16**（見 1.2c） |

合計 **113 列選項**（active 的 `MINIMOST_FACTORY_V2` 佔 **63** 列），`label_en` 一律 NULL。
> 派工簡報所述「五張表 95 條」少算了 `rule_b_options` 與 `rule_p_addons` 兩張表；本 ADR 以 **7 張表** 為準。

前端：`package.json` 無 `react-i18next`／`i18next`／任何 i18n 框架；`.tsx` 內含中文的字串字面值
約 **553 處**、含中文的檔案 **62 個**。`AppLayout` 標頭目前只有標題、匯入按鈕與使用者資訊，**無語言切換位**。

**結論：這是從零開始的功能，不是補完。** 草案的「一半基礎」說法會讓排程低估，本 ADR 更正之。

### 1.2 草案沒看見的三個事實（各自改變設計）

**(a) `sentence_text_en` 不存在。** 敘事引擎 `most_engine/narrative.py` 取的是
`sentence_text_zh`（NULL 才回退 `label_zh`）。7 張表都只有 `sentence_text_zh`，**沒有 `_en` 對應欄**。
草案第 2 項說「用 rule-set `label_en` ＋ vocab `name_en` 組英文敘事」——資料模型不支援：
`label_zh` 與 `sentence_text_zh` 是**兩個不同語意的欄**（標籤要能在下拉選單中辨義，句面要能入句），
實測可證：`p_asm_multi` 標籤＝「組(多種方向)」、句面＝「組」；`i_align1` 標籤＝「並對準(正常視線範圍到點)」、句面＝「並對準」。
英文必須同樣兩欄。

**(b) 中文標籤裡內建了句子的連接詞。** 實測 active 版：`rule_x_options` 11 條中 **7 條**、
`rule_i_options` 9 條中 **8 條** 的 `label_zh` 以「**並**」開頭（並點膠／並鐳雕／並對準…）。
也就是說**中文樣板把連接詞的責任外包給了資料**。逐字機器翻譯會產出 "and apply glue"，
英文樣板再補一個 "and" 就變成 "…, and and apply glue"。這不是翻譯品質問題，是**欄位語意在兩種語言下不同**——
直接證明 D7 的「英文樣板系統與中文樣板系統平行存在，不是翻譯管道」不是風格選擇，是被資料形狀逼出來的。

**(c) `motion_templates.name_en` 16 筆已有值，但出處不明。** 值來自 `scripts/dev_seed_templates.py`
的開發者手寫欄（take／place／open/remove／scan/check…），**不是 IE 認證、不是翻譯流程產出**。
若不處理，這 16 筆會被誤當成「已翻譯且可信」而永遠不進待審清單。D5 的來源標記值域因此必須有
`legacy_seed` 這一格——**已有值 ≠ 已覆核**。

**另補一項事實**：v3 的 IE 認證字典（`docs/v3/reference/minimost_ai_dictionary_v1.json`）與 v3 SQLite
（24 表）**完全沒有任何 `_en`／`locale`／`language` 欄位**。所以**英文沒有既有權威可援引**，
也無法從 v3 收割；ADR-014 的值權威只覆蓋中文。這是 D2 成立的前提事實。

### 1.3 與 ADR-023 規則 1 的正面衝突（本 ADR 必須解決的核心）

ADR-023 §3.3 規則 1 的三層可變性矩陣有一列是「**標籤／句子文字**」，其可變性為：
draft ✅、published(非 active) ❌409、published+active ❌409、retired ❌409。

`label_en` 與（將新增的）`sentence_text_en` **在字面上正屬於這一列**。而 User 裁決是
「機器翻譯先全部灌值」——要灌的目標正是 `MINIMOST_FACTORY_V2`（published ＋ active）。
兩者直接相撞：照現行規則，灌英文得先 clone-on-write 出草稿、改值、publish、activate，
**為了一批不可能改變 TMU 的顯示字串，發一個新的認證版本**；而且「之後有空再修」的每一次修正
都要再發一版。這條路與 User 的裁決 2 不相容，必須明文處理（D4），不能靠實作時默默繞過。

### 1.4 為什麼現在決

三個理由：(a) `label_en` 已經是 API 契約的一部分（`/rule-sets/{code}/options` 與 `/full` 都回傳它，
`features/dictionary/paramSchema.ts` 甚至已有「英文標籤」編輯欄），現況是**一個對外承諾但永遠是 null 的欄位**；
(b) 一旦有第二個語系或有人開始手填，儲存位置與治理歸屬就會被實作既成事實決定；
(c) 敘事英文化牽動 7 張表的加法 migration 與 clone 路徑，愈晚做，要回填的歷史列愈多。

---

## 2. 決策

### D1 範圍＝第一層（UI 外殼）＋ 第二層（業務資料標籤，含引擎敘事英文化）；第三層明確不做

（User 裁決 2026-08-18 第 1 條）

| 層 | 內容 | 本輪 |
|---|---|---|
| **L1 UI 外殼** | React 元件內的固定字串（選單、按鈕、表頭、提示） | ✅ Phase A |
| **L2 業務資料標籤** | 7 張選項表 `label_en`／`sentence_text_en`、`work_vocab_items.name_en`、`motion_templates.name_en`、引擎敘事英文版 | ✅ Phase B／C |
| **L3 AI 工單解析器英文 NLP** | 英文語料、英文 lexicon、平行英文 gold set、英文 parser 評測 | ❌ **不做**（D9） |

**L2 包含敘事**，因為敘事是引擎輸出的一部分，若只翻標籤而 METHOD 欄仍是中文，
英文使用者拿到的是半成品；而敘事所需的 `sentence_text_en` 與標籤同源同表，一起做邊際成本最低。

### D2 翻譯權威＝機器翻譯先全灌、人工後修（fill-then-fix），不走「草稿等核准才上線」

（User 裁決 2026-08-18 第 2 條）

**User 立場意譯**：先讓英文介面能用；逐條等 IE 核准會讓這件事永遠停在 0%。

**架構師論證（為什麼這在本專案是安全的，以及讓它安全的三個前提）**：
本專案對「未經人工驗證的資料」的既有慣例是 fail-closed（WI parser gold set：草稿不進正式集、
`review-state.json` 只由 IE 寫、harvest 只讀不寫）。本決策看似違背它，實則不同——因為
**翻譯錯誤與解析錯誤的爆炸半徑不同**：解析結果會**變成 TMU**，翻譯結果**只被人看**。
但這個區別只在下列三個前提成立時為真，故一併裁定為不變式（§3）：

1. `_en` 不得進入任何決定 TMU 的路徑（引擎、lexicon、同義詞、範本比對）——I3。
2. 同一參數內不得有兩個選項共用同一個正規化英文字串——I5（否則英文介面下 IE 會選錯格，
   翻譯錯誤就**真的變成 TMU 錯誤**）。
3. 每一條機器翻譯值都帶可查詢的來源標記與過期偵測——D5（否則「之後再修」無從指派、無從驗收）。

**取捨誠實記錄**：代價是英文介面在覆核完成前會顯示未經 IE 確認的字串。這是 User 明示接受的。
本 ADR 不加「機器翻譯」浮水印給一般使用者（User 裁決 5 明確要求標記僅工程／IE 端可見），
改以**成本更低、不打擾人的補償措施**：選項下拉在英文語系下**同時顯示語言中立的 option code**
（`grasp (g_grasp)`）。code 已存在、跨語言恆定，且對中文介面零影響。

### D3 語言來源＝使用者個人設定；API 回應保持語言中立

（User 裁決 2026-08-18 第 3 條）

**D3.1 `app_users.locale`（加法 migration）**

- `locale text NULL`，`CHECK (locale IN ('zh-TW','en'))`。
- **NULL 的語意是「未設定」→ 回退系統預設（目前 `zh-TW`）**，不是「無語言」。
  用 NULL 而非 `NOT NULL DEFAULT 'zh-TW'`，是為了讓日後改系統預設能自動套用到未表態的使用者。
- **語系碼與欄位後綴的對照固定為**：`zh-TW` → `*_zh` 欄；`en` → `*_en` 欄。
  明文記載以免有人日後引入 `zh-CN`／`zh_Hant` 等第三種寫法。
- `/api/v2/me` 回應加 `locale`；新增 `PATCH /api/v2/me/locale`（本人可改自己的，
  無需 admin——這是個人偏好，不是授權）。

**D3.2 未登入／gateway 模式的預設語言：問題其實不存在，但要寫清楚**

實測 `auth/deps.py::current_user`：**沒有匿名路徑**。取不到身分一律 401；取得身分而 DB 無此人時
JIT 建立（`roles=[]`）。所以每一個 API 呼叫背後都有一個 `app_users` 列，JIT 建立者 `locale=NULL` → `zh-TW`。
真正的「無使用者」只有前端在 `/me` 回來之前的第一次繪製——該期間讀 `localStorage` 的上次語系，
沒有就用 `zh-TW`；`/me` 到達後以伺服器值為準並回寫 localStorage（伺服器是權威，localStorage 只是首屏快取）。

**D3.3 API 回應語言中立，語言選擇發生在呈現層（架構師提案，本 ADR 的關鍵取捨）**

**不做** `Accept-Language` 內容協商、**不**讓 `label` 欄位的語意隨使用者而變。理由：

- `/rule-sets/{code}/options` 目前同時回 `label`（中）與 `label_en`，**現況就是雙欄並存**。
  把 `label` 改成「隨使用者語言變」是**型別不變、語意悄悄改變**的破壞性變更，
  正是 ADR-011 §政策 1 要避免的那種漂移；且所有既有前端消費點都會靜默改變行為。
- 語言中立的回應可被快取、可被 e2e 穩定斷言、不需要 `Vary: Accept-Language`。
- 唯一真正需要伺服器端選語言的產物是**伺服器生成的文件**（匯出、未來的 PDF）——那類端點日後應以
  **顯式請求參數** `?lang=` 取語言，**不隱含讀使用者屬性**（同一份匯出檔給誰看，不必然等於誰按的按鈕）。

  > **先例（沿用）**：`02-Memory/Third-Party-Field-Format-Reconnaissance.md`——「後端儲存決策與前端消費策略
  > 必須在同一個時間點定案，否則前端會補上一個看似合理、實則與後端衝突的中間轉換」。
  > 本節即是在定 `_en` 儲存決策的同一刻，把消費策略一併定死：**前端依 locale 挑欄，不做任何合併或猜測**。

**D3.4 語言切換 UI 的位置**：`AppLayout` 標頭右側，使用者資訊左邊（與 `匯入 Excel` 同列）。
理由：全域偏好屬全域外殼，不屬任一分頁；且該處是唯一在所有 7 個分頁都存在的容器。

### D4 `_en` 在 published／active 版可後補 —— 本 ADR 修訂 ADR-023 規則 1 矩陣

**裁定**：在 ADR-023 §3.3 規則 1 的三層可變性矩陣**新增一列**：

| 資料 | draft | published(非 active) | published+active | retired |
|---|---|---|---|---|
| **`_en` 標籤／句面（`label_en`／`sentence_text_en`）** | ✅ | **✅** | **✅** | ❌ |

原有的「標籤／句子文字」列**收窄為「`_zh` 標籤／句子文字」**，維持 ❌409 不變。

**論證**：ADR-014 授權「published 唯一可後補的資料＝同義詞」，理由逐字是
「僅影響建議層不影響工時」。`_en` 的性質**比同義詞更弱**——同義詞至少會影響 parser 選哪個 option code
（ADR-023 規則 1 補節二正是為此立的守門），而 `_en` 在 I3 的約束下**連建議層都不影響，純顯示**。
既然更弱的資料被允許後補，更強的沒有理由被凍結。`retired` 為終態，維持不可寫（與同義詞同）。

**為什麼寫在 ADR-032 而不是補一節到 ADR-023**（自問自答，因為兩者都說得通）：

- 本決策的作用域**大於字典**：同一套來源標記與待審清單同時治理 `work_vocab_items`／`motion_templates`
  （ADR-024 歸類為**主數據**，不在 ADR-023 管轄範圍）與前端 catalog。
  把政策拆成「字典的部分在 ADR-023、主數據的部分在 ADR-032」會製造兩份會漂移的真相——
  這正是 ADR-024 事後剖析裡「改變欄位語意卻只改一半」造成 16 筆隱形模組的同一種病。
- 因此：**政策整份留在 ADR-032**，但 **ADR-023 §3.3 規則 1 必須加一行交叉引用**指向此處。
  這是本 ADR 被核可時的必辦事項（§10 第 1 項），不是可選的收尾。

**RBAC**：`_en` 的編輯權＝`analyst`（IE）以上。依據 ADR-024 §5.4 對同義詞的同一套推理
（只影響建議／顯示層 → 不需 approver），且與 rule-set 選項寫入現行的 `require_role("analyst")` 一致。
`_en` 的寫入**不觸發 clone-on-write 攔截**（與同義詞相同的繞道），否則規則 1 的新列形同虛設。

**D4 實作補記（2026-08-20，D6 mutation 輪次一併落地）**：D4 自 2026-08-18 裁定後
**一直沒有實作**——`rule_set_service.assert_editable()` 對 `provenance='certified_import'`
一律 409，而 active 的 V2 正是 `certified_import`，所以矩陣新列所授權的那 63 列
rule-option 英文，實際上一個字都改不動。本輪補上：

- **新增一條與 `assert_editable` 並列的 gate**：`rule_set_service.assert_en_editable()`
  ——404（不存在）→ 409（`retired`）→ 放行，**刻意不看 `provenance`、也不要求 `status='draft'`**。
  **不是**在 `assert_editable` 上開 `allow_en=True` 旁路：那條路一旦有人忘了關，
  `label_zh` 與 `base_tmu` 會跟著解凍，正是 D4 要避免的形狀。
- **唯一的寫入端點**：`PATCH /api/v2/rule-sets/{code}/params/{param}/options/{option_code}/en`
  → `rule_option_service.update_option_en_text()`。欄位白名單
  `EN_WRITABLE_FIELDS = {label_en, sentence_text_en}`（schema 層另有 `extra="forbid"`，
  兩道），白名單外一律 422；`retired` 409；RBAC `analyst`；走 `workflow_audit_log`
  （`action='option_en_update'`，記前後值）。
- **I5 的唯一性檢查下沉到這條路徑**：先前 I5 只在灌值腳本裡守（灌值當下避免碰撞），
  線上編輯一開，`g_grasp`(6 TMU)／`g_touch`(3 TMU) 被改成同一個英文字面就沒人擋了。
  現在同 (rule_set, 參數表) 內 `label_en` 正規化後重複 → 409 `EN_LABEL_NOT_UNIQUE`。
  **2026-08-20 checkpoint 更正**：上面這段先前只在 `update_option_en_text` 一條路成立，
  讀起來卻像洞補上了——`label_en` 也是 `_OptionIn` 的可寫欄位，`create_option`／
  `update_option` 走 `validate_payload` 完全沒有唯一性檢查，任何 draft 上仍改得出兩個
  相同的英文標籤。三條路徑現已共用同一支 `_assert_en_label_unique`（上線前實測既有
  63 筆 `label_en` 零衝突，接上不會讓既有編輯操作開始 409）。**`duplicate_option`
  刻意不接**：它整列複製（含 `label_en`），接上等於複製功能對任何已有英文標籤的選項
  一律 409；複製出來的列本來就是待改的半成品（`code` 也只是 `{code}_copy`）。
  這是下面「已知邊界」的第 3 條。
  句面（`sentence_text_en`）不受此限——句面本來就允許重複（多條「刻意不入句」同為空字串），
  唯一性是下拉選單辨義的要求，不是句子的要求。

### D5 翻譯來源標記＝獨立側表 `i18n_review_state`（文字仍留在原欄）

（User 同意架構師提案，2026-08-18 裁決第 5 條）

**形狀**：一張表，只存「關於譯文的事實」，**不存譯文本身**。

```
i18n_review_state
  id              uuid pk
  entity_type     text  not null  CHECK IN ('rule_option','vocab_item','motion_template')
  scope_key       text  not null  -- 見下方「鍵的選擇」
  field           text  not null  CHECK IN ('label','sentence','name')
  locale          text  not null  CHECK IN ('en')          -- 加法擴充：日後新語系加值
  source          text  not null  CHECK IN ('machine','human','legacy_seed','untranslated')
                                  -- 'untranslated'＝v2_0043 新增：側表列只為記指派而
                                  --   存在、尚無譯文（理由見 D6 後半的補記）
  source_sha256   text  not null  -- 翻譯當下「中文來源字串」正規化後的 sha256
  translated_by   text            -- machine：服務／模型識別字串；human：員工號
  translated_at   timestamptz not null
  reviewed_by     text            -- source='human' 時必填（CHECK）
  reviewed_at     timestamptz
  target_sha256   text            -- v2_0043：覆核當下「英文譯文」正規化後的 sha256
  assigned_to     text            -- v2_0043：指派給誰（員工號）；NULL＝未指派
  assigned_at     timestamptz
  note            text
  UNIQUE (entity_type, scope_key, field, locale)
```

**為什麼是側表而不是在每張表加欄**：9 張表 × 每個可譯欄 4 個中繼欄，會產生 30＋ 個欄位，
且每加一個語系就再乘一次。側表讓「待審清單」是**一次查詢**而不是九個 UNION，
且新增可譯實體只是多一個 `entity_type` 值（加法）。

**為什麼譯文不搬進側表**：`label_en` 已是既有 API 契約（`/options`、`/full`、`paramSchema.ts` 編輯欄）
且 `load_full`／`_insert_children` 已攜帶它——搬家等於改契約＋資料遷移，換來的只是「更整齊」。
**文字一個真相（原欄）、覆核狀態一個真相（側表）**，兩者不重複。
> 這與 gold set 的既有形狀同構：`tests/gold/wi_plans_draft/review-state.json` 是**與被覆核物分離**的
> 狀態檔，`gold_harvest.py` 只讀不寫。本表是它的 DB 版。

**鍵的選擇（`scope_key`）——這一格是設計的重點，不是細節**：

- `rule_option` → `'{parameter}:{option_code}'`（例：`g:g_grasp`）。**刻意不含 `rule_set_id`。**
  理由：`replace_children` 在每次存草稿時**刪除並重建子表列**，主鍵會換；用列 id 當鍵，
  覆核狀態會在每次編輯後變孤兒。更根本的是，**英文譯文的正確性不隨 TMU 版本而變**——
  「抓握＝grasp」不會因為 clone 出 V3 就需要重審。以版本無關的業務鍵為主鍵，覆核成果才會累積。
- `vocab_item` / `motion_template` → 該列 id 的字串（這兩者是主數據，無 clone 行為，id 穩定）。
- 代價：若某個 option_code 在新版本改了中文標籤，`source_sha256` 不符 → 自動變「過期」重回待審。
  這正是要的行為。

**過期偵測（`source_sha256`）**：直接沿用 gold review 的 `norm_sha256` 手法——
中文來源變了，譯文就是**過期**，重回待審清單並標 `stale`，**但不自動失效、不靜默沿用**。
`ruling_history` 那種完整軌跡不複製（翻譯的更正史價值遠低於 IE 裁決的更正史）；
覆蓋寫入由既有 `workflow_audit_log` 承接即可。

**預設值與既有資料的初始狀態**：

| 情形 | 側表 | 意義 |
|---|---|---|
| `_en IS NULL` | **無列** | 從未翻譯 |
| Phase B 機器灌值 | `source='machine'` | 可用、未覆核 |
| IE 改過並確認 | `source='human'` ＋ `reviewed_by/at` | 已覆核 |
| `motion_templates` 既有 16 筆 | `source='legacy_seed'` | **有值但出處不明，等同未覆核**（1.2c） |

### D6 待審清單：查詢定義、角色、來源集合

**清單 = 下列三種列的聯集**（單一查詢）：

```
(1) 目標欄位 IS NULL                                   → never_translated
(2) 有側表列且 source IN ('machine','legacy_seed')     → unreviewed
(3) 有側表列且 source_sha256 <> sha256(現行中文來源)   → stale
```

**(2)／(3) 重疊時的優先序（Phase B 實作補記，2026-08-18；把已成立的裁決記清楚，不是重寫
決策）**：一列可能同時符合 (2)（`source ∈ {machine, legacy_seed}`）與 (3)（sha 不符）——
例如機器翻完之後，中文標籤又被改了，但這條翻譯從未被人覆核過。這種情況一律歸
**`unreviewed`，(2) 先於 (3)**：`stale` 的語意是「**曾經**被 IE 覆核（`source='human'`），
之後中文來源才變」——D6 上文「重回待審清單」的「重回」二字已經暗示它曾經離開過待審清單
（＝曾經被覆核）；`machine`／`legacy_seed` 從未離開過待審清單，談不上「重回」。對使用者
更有意義的訊息也是「這條還沒人看過」，不是「這條過期了」（過期暗示曾經有人確認過）。

**「有譯文但查無側表列」也歸 `unreviewed`，不是 `stale`（2026-08-20 checkpoint 修正）**：
上面那條優先序只講了 (2)（`source` 值域）與 (3)（sha 不符）的重疊，漏了第三種情形——
一列**根本沒有側表列**，但 `_en` 欄位有字。這一支先前落進 `stale`（`review_sha256` 為
`None` 必然不等於任何 sha256），而 `stale` 的語意是「曾經被覆核，之後內容變了」：一列
沒有覆核基準，不可能過期，報 `stale` 傳達的訊息與事實相反。這不是理論邊角——
`POST /api/v2/vocab` 帶 `name_en` 建新詞彙時完全不寫側表列（**每一筆新詞彙一出生就是
`stale`**），D4 的 `_en` 線上編輯閘也只寫欄位、不碰側表。而且它讓「指派不改變 status」
這句本 ADR 與程式碼三處明文的承諾**不成立**：`assign_review()` 就地補一筆 `legacy_seed`
側表列，status 就從 `stale` 變成 `unreviewed`。`_classify` 現在顯式先回 `unreviewed`；
兩者同屬待審，`n/126` 的分子分母不變。

**`source_changed` 欄位（同一次實作補記）**：因為上面的優先序，`status='unreviewed'`
本身分不出「剛翻好、中文沒變過」與「翻過，但中文後來又改了、它還沒被人看過」——兩者對覆核者
的意義不同，但單看 `status` 看不出差異。API 回應（`I18nPendingItemOut`）與服務層
（`TranslatableRow`）因此都加了一個獨立的布林欄位 `source_changed`（`review_sha256` 是否
不等於現行中文來源的 sha256），把這個區別顯式標出來，而不是讓它悄悄消失在 `unreviewed`
這一個值裡。不引入第四個 status 值——`status` 的三態聯集維持 D6 定義的形狀不變，
`source_changed` 是它的一個獨立正交維度。`review_sha256 is None`（從未翻譯過、
連側表列都沒有）時 `source_changed` 一律 `False`——沒有基準可比較，不能算「變了」
（L3，2026-08-18 第二輪複審修正：這個子情況先前只在程式碼與 docstring 裡寫清楚，
本節文字沒有涵蓋，此處補上，行為本身沒有變）。

**寫入端不比對內容，覆核正確性完全依賴上面的讀取端過期偵測（Phase B 實作補記，
2026-08-18 第四輪簡化定案）**：`upsert_review_state`（`i18n_service.py`）只做一個
寫入前檢查——`scope_key` 指涉的 entity 是否存在（查無則 fail-closed 拒絕）；
`source_text` 如實記錄呼叫端這次覆核當下看到的中文，**不**與任何版本的「現行
文字」逐字比對。「同一個 scope_key 被 active 版與所有 draft 版共用，draft 改過
的中文會不會污染 active 的顯示狀態」這個問題，完全交給上面 D5 原始設計的讀取端
sha256 過期偵測（`source_sha256 <> sha256(現行中文來源)` → `stale`）處理——它
本來就是拿 `review_sha256` 去比對**每一個候選列自己的**現行中文，不會因為寫入端
如實記錄了另一個版本的文字就把這一列誤標「已覆核」。Phase B 開發過程中一度在
寫入端另外加過第二層逐字比對防線（連同一個 `rule_set_id` 局部放行參數，允許
呼叫端聲明「這個 code 只存在於某個非 active 版本」以繞過比對），但那道防線是
同一個問題的第二個、版本無關、精度更低的答案，且是連續兩輪複審每一個阻擋級
問題的唯一來源——第三輪複審後判定拆除，不再保留，避免下一個人誤以為系統有
兩層防護（正確性保護只有一層：讀取端）。

**這道防線的範圍限定（第四輪複審 M1）**：`source_sha256` 只追蹤**來源中文**的
變化，不追蹤**目標英文**（`label_en` 等）。若同一個 `scope_key` 在不同版本
分別被編輯了各自的英文譯文（例如只在 draft 改 `label_en`、中文一個字沒動），
active 版的英文即使從未被覆核，也不會被標為 `stale`——因為讀取端比的是中文
sha 而非英文本身。D4 允許逐欄編輯譯文，這條路徑理論可達；Phase B 只有唯讀
端點、灌值只在 `_en IS NULL` 時填、clone 會複製 `_en`，需要人為分版編輯才
會踩到，故本輪不視為阻擋，留待開放覆核 mutation 端點時一併設計
（候選方案：side table 增加 `target_sha256`，或限制覆核只能對 active 版
的候選列進行）。

**定案（2026-08-20，User 裁決；migration v2_0043）：採 `target_sha256`。**
側表新增 `target_sha256 text NULL`，語意與 `source_sha256` 對稱——記「**覆核當下的
英文譯文**」正規化後的 sha256（同一支 `norm_sha256`）。讀取端的 `stale` 判定因此擴充為
「**中文來源變了 或 英文譯文在覆核後被改過**」：兩者都是「曾經被覆核、之後內容變了」，
所以歸同一個 `stale`；區分兩者的是一個與 `source_changed` 正交的新布林欄位
`target_changed`（照 S6 的先例，**不引入第四個 status 值**，D6 的三態形狀不變）。
`target_sha256 IS NULL`（既有列全部如此，純加法）→ 沒有基準可比較 → `target_changed`
一律 `false`，比照 L3 對 `review_sha256 is None` 的處理——所以這個欄位上線當下不會讓
任何一列憑空變成 `stale`。**不採候選方案二（限制覆核只能對 active 版進行）**：D4 明文
允許 IE 在 draft 新增 active 沒有的選項，方案二會讓那些列永遠無法覆核——把一個
「精度不足」的問題換成一個「整類資料不可覆核」的問題。

**來源集合限定為：active rule-set ＋ 現存 draft ＋ 全部主數據。**
`published(非 active)` 與 `retired` 版本是凍結的歷史，不需要翻譯，也不該灌大家的待辦清單。
這同時把 rule-set 側的工作量從 113 列收斂為 **63 列**（active V2）。

**分母修正：63 → 126（2026-08-20，覆核 mutation 輪次；這是缺陷修正，不是範圍擴張）**。
上面那個「63」算的是 **option code 數**，但一個 option 有**兩個**可譯欄位——
`label`（下拉標籤）與 `sentence`（敘事句面），D5 的側表 `field` 值域本來就同時收這兩個，
Phase C 也真的把 63 筆 `field='sentence'` 的覆核狀態寫進了側表。**問題是它們永遠不會
出現在待審清單裡**：`i18n_service._candidates_sql()` 對 `rule_option` 硬寫
`'label' AS field`，句面那 63 筆寫得進側表、卻查不出來。後果是**風險排序完全顛倒**——
英文使用者在 METHOD 欄實際讀到的整句敘事（句面）覆核追蹤是 0% 且不可達，
風險低得多的下拉標籤反而 100% 可見。清單一旦要能操作（可指派、可標記完成），這個缺口
就必須補，否則「覆核率 100%」會是一個只涵蓋一半資料的數字。故 `_candidates_sql()`
自本輪起 7 張選項表各出兩列候選，**`summary()` 的 rule_option 分母由 63 變成 126**
（實測 `{'total': 126, 'reviewed': 0, 'pending': 126}`；含主數據的全體分母由 138 變成 201）。
下文「驗收定義」與 D10 Phase B 原本寫的「`n/63`」一併更新為「`n/126`」。

句面候選的**來源中文**取 `COALESCE(NULLIF(sentence_text_zh,''), label_zh)`——必須與引擎的
回退鏈逐字一致（`narrative._sent()` ＝ `sentence or label`，灌值腳本算 `source_sha256`
時用的也是同一條鏈）。取裸 `sentence_text_zh` 的話，句面留空的那幾條（`m_hand`／`m_foot`／
`b_none`…）會拿一個引擎根本沒讀的字串去算 sha256，整批句面永遠顯示過期。

**誰看得到**：`analyst`（IE）以上（與 D4 的編輯權一致）。`viewer` 不顯示入口。
依據 ADR-024 的權責分界：清單同時涵蓋**字典**（admin 入口「MOST 字典」）與**主數據**
（analyst 入口「主數據管理」）兩類物件，取兩者權限的**下界** analyst，
再由既有的 `assert_editable`／角色守門決定每一列能不能寫——不另造一套權限模型。

**呈現介面：P6 定案（Phase B 前端實作補記，2026-08-18）**——「主數據管理」頁新增第三分頁
（詞彙庫、動作模組範本之後），不另立側欄項。理由不變：側欄總數是 ADR-021／024 反覆爭取的
稀缺資源，為一個過渡性工作清單再加一項不划算；清單同時涵蓋字典（admin 入口）與主數據
（analyst 入口）兩類物件，但「放哪邊都有一半是別人家的東西」這個顧慮，敗給了側欄名額更稀缺
這個事實。上文與下表（P6）「本 ADR 不定案／實作時對照 v3 與使用習慣再定」的說法至此已過期，
以本段為準。

**Phase B 分兩半交付，本輪只完成前半**（同一次補記）：`I18nReviewTab.tsx` ＋ GET
`/api/v2/i18n/review/summary`／`/pending` 兩支端點，做到「待審清單可見、可依 entity_type／
status／關鍵字篩選、覆核進度數字（`n/total`）可見」——**唯讀**，沒有標記完成的 mutation
端點，前端也刻意不做「標記已覆核」按鈕與逐列編輯英文譯文的入口（後者是既有 `label_en`
編輯欄／D4 的事）。下文「驗收定義」寫的「每條可指派、可標記完成」在本輪**尚未達成**——
mutation 端點與「標記已覆核」UI 留給下一輪。**不要把 Phase B 標記為已完成**：這一輪只是
前端唯讀半部落地，不是 D6 驗收定義的全部。

**後半的後端已落地（2026-08-20；UI 仍未做，Phase B 仍不得標記完成）**：

| 端點 | 角色 | 語意 |
|---|---|---|
| `POST /api/v2/i18n/review/mark-reviewed` | analyst+ | `source='human'` ＋ `reviewed_by`／`reviewed_at` ＋ `target_sha256`；可選帶 `target_en`，在**同一個交易**內先經 D4 的 `_en` 寫入閘改譯文、再寫側表 |
| `POST /api/v2/i18n/review/assign` | analyst+ | `assigned_to`／`assigned_at`（v2_0043 新增欄）；`null` ＝取消指派 |
| `PATCH /api/v2/rule-sets/{code}/params/{param}/options/{option_code}/en` | analyst+ | D4 的 `_en` 專用寫入閘（見 D4 實作補記） |

三個刻意的設計選擇，每一個都對應本 ADR 的一句話：

1. **沒有批次核准端點**（I5／R1）：`g_grasp`(6 TMU)／`g_touch`(3 TMU) 這種「英文看起來
   一樣」的誤譯只有逐條人看才擋得住，一次核准 126 列會把覆核變成橡皮圖章——而「每條
   譯文都有人負責」正是 D2 賴以成立的第三個前提。要開這條路得先回答「怎麼避免橡皮
   圖章」，那是新的裁決，不是實作細節。
2. **沒有譯文的列不得被標成已覆核**（422 `I18N_REVIEW_TARGET_MISSING`）：否則覆核率
   會上升而英文介面還是空的。要覆核就在同一個請求帶 `target_en`。
   `field='sentence'` 的空字串是例外——那是 D7.6 的「刻意不入句」，是有意義的值——
   **但這個例外有前提：該列的中文句面本身必須是空的**（2026-08-20 checkpoint 修正）。
   先前這個例外無條件放行，等於一張橡皮圖章：中文句面「抓握」的 `g_grasp` 也吃得下
   `target_en=""`，回 200、`sentence_text_en` 被清成空、離開待審清單；`sentence_text_en`
   為 NULL、連側表列都沒有的列同樣吃得下——**完全沒有英文，卻算已覆核**。63 條句面用
   63 個空字串請求就能把 `n/126` 推到 126/126 而英文全空，正是 R2 寫明的「本 ADR 最可能
   的失敗模式」。判準改成看中文句面（`sentence_text_zh IS NULL OR = ''`，現況 active 版
   7 條：`b_none`／`a_hard`／`a_press`／`m_hand`／`m_foot`／`x_none`／`i_none`），
   與 D7.6 的定義同一個判準。純空白（`"   "`）一律不是「刻意不入句」：它在入口就被
   strip 成空字串，再套用上面的前提。
3. **`_en` 自由文字在入口 strip 並設長度上限**（同一次修正）：`label_en`／`name_en`
   ≤ 200 字元（對齊 `import_service` 對 vocab 名稱的既有處理）、`sentence_text_en`
   ≤ 500——這條路徑碰得到**生產字典的 active 認證版**而任何 analyst 都走得到，實測
   未設限時 200,001 字元寫得進去。strip 的理由有兩個：`narrative_en._sent()` 的回退鏈
   是 `sentence_en or label_en`，`"   "` 是 truthy → 不會回退，會把一段空白當動詞組進
   英文敘事句（引擎側不動，擋入口就夠）；以及覆核路徑先前是裸 `setattr`，同一個字串
   經覆核路徑存成 `'   Padded   '`、經 `PATCH /api/v2/vocab/{id}` 存成 `'Padded'`，
   而 `schemas/v2/vocab.py` 檔頭明講「字串一律 strip，在入口擋掉」。
4. **主數據的譯文改動也留前後值**（同一次修正）：`rule_option` 有 `option_en_update`
   記 `changed_fields: {before, after}`，`vocab_item`／`motion_template`（約 75 條）
   先前只留得下「某人覆核過這條」，還原不了英文被改成什麼。`i18n_review_mark` 的
   payload 現在帶同樣形狀的 `changed_fields`。
3. **端點不收 client 端宣告的中文／英文原文**：`source_sha256`／`target_sha256` 一律由
   伺服器從候選查詢（與待審清單**同一份 SQL**）取現行值計算。兩邊只要有一處對來源
   欄位的解讀不同，覆核完的列會立刻被讀取端判成 `stale`。

指派欄位為此在側表新增，並且 `source` 值域加了 `'untranslated'`（v2_0043）——
`never_translated` 的列本來就沒有側表列，而那正是最需要有人認領的一批；舊值域三個值
（machine／human／legacy_seed）**每一個都是在描述「譯文從哪來」**，對一條還沒有譯文的列
填其中任何一個都是謊。讀取端把 `'untranslated'` 與 machine／legacy_seed 同列為
`unreviewed`，所以**指派不會改變一列的 `status`**（指派記的是「誰在處理」，不是「處理到哪」）。

**已知邊界（2026-08-20 checkpoint 記票，本輪刻意不處理）**：

1. **I5 與側表 upsert 沒有 DB 約束背書，並發可穿透**：唯一性是「先查再寫」的應用層
   檢查，兩個同時進來的請求可以雙雙通過檢查再雙雙寫入；側表的 upsert 同理（讀-改-寫，
   沒有 `ON CONFLICT`）。現況是**單一 IE 逐條覆核**的工作型態，衝突視窗小到不值得為它
   加 unique index／`ON CONFLICT`（那會牽動灌值腳本與 `_en` 閘兩條既有路徑）。
   要處理就一起處理，不是在覆核端點單點補。
2. **`_en` 專用端點寫得進 V1（published 非 active），覆核端點碰不到 V1**：前者的 gate
   是 `assert_en_editable`（只擋 retired），後者的候選集合是「active ＋ 現存 draft」
   （D6 明文）。兩條路徑對「哪些版本可寫」的定義不一致——不是安全問題（V1 的英文標籤
   本來就允許後補），但**同一件事兩個答案**，日後要收斂成一個。
3. **`duplicate_option` 不受 I5 約束**：整列複製會複製 `label_en`，複製當下就產生一組
   重複的英文標籤（見上方 D4 補記）。要修得先決定複製時 `label_en` 的處理（跟 `code`
   一樣加尾綴？清空？），那是新的裁決，不是實作細節。

**驗收定義（重要，否則「之後再修」是空話）**：Phase B 的完成判準**不是**「翻譯都有了」，
而是「**覆核進度是可見且可下降的數字**」——字典／主數據頁標頭顯示 `英文覆核 n/126`
（原文寫 `n/63`，2026-08-20 隨句面進入清單一併更新，理由見上方「分母修正」），
點進去是待審清單，每條可指派、可標記完成。本 ADR **不設期限**（期限屬 User 的排程權）。

### D7 敘事英文化：平行樣板系統，不是翻譯管道

**D7.1 現況**：`most_engine/narrative.py`（105 行，純函數）以中文語序硬拼字串：
`HAND_NAMES` → 從/到介詞 → G 句面 → `×N` → 「物件」→ 伸手 N 公分 → …「最後收束返回。」

**D7.2 新增欄位（皆為加法 migration）**：

- 7 張選項表新增 `sentence_text_en text NULL`（1.2a）。
  **實作陷阱**：`rule_set_service.load_full()`／`_insert_children()`／`schemas/v2/rule_set_options.py`
  三處都要同步加欄，**否則 clone-draft 與 `PUT /full` 會靜默丟掉英文句面**（現行 `label_en`
  三處都有，是可照抄的正確樣本）。
- `most_cycles.narrative_en text NULL`（與既有 `narrative_zh` 對稱，同為**可重生快取**）。
- **`motion_module_versions` 不加 `narrative_en`**。該表是**不可變版本快照**（ADR-024 §1「業務產出」
  自有版本鏈）；為舊快照回填等於改寫不可變列，不回填則永遠是 NULL。
  改為**讀取時以該版本 pin 的 `rule_set_id` 即時產生**，不落盤。

**D7.3 英文樣板與中文樣板的關係**：**共用資料輸入（同一份 cycle ＋ labels ＋ vocab），
各自獨立的組句規則**。不是「中文句子丟去翻譯」，也不是「同一套樣板換字串表」。三個實證理由：

1. **連接詞的歸屬不同**（1.2b 實測）：中文把「並」寫進資料（X 7/11、I 8/9），英文樣板必須自己出
   "and"，且 `sentence_text_en` 必須是**不含連接詞的乾淨動詞片語**。同一份資料在兩套樣板裡職責不同。
2. **`display_rule` 的值域內建中文語序假設**：`p_addons.display_rule='prefix_visible_term'`
   ——「**前綴**可見詞」（中文：「以『**對準**組』放置」）。英文的對應可見詞多半落在**動詞之後**
   （"place, aligned to the mark"）。同一個欄位值在英文樣板要被解讀成別的位置，
   所以英文樣板必須有自己的 `display_rule` 解讀，不能共用分支。
3. **句型骨架不同**（見下）。

**D7.4 語序差異具體例（自現行中文樣板反推）**：

| # | 中文（現行 `build_narrative` 產出） | 英文應有的語序 | 差在哪 |
|---|---|---|---|
| 1 | 右手**從料架**抓握「假DIMM」，伸手約20公分。 | RH: grasp the dummy DIMM **from the rack**, reaching ~20 cm. | 中文來源片語**前置於動詞**，英文**後置於受詞**。欄位替換不可能得到正確結果，必須重排 |
| 2 | 隨後移動約15公分，**翻轉「假DIMM」**，到流水線，以「保持住」放置。 | Then move ~15 cm to the line, **turning the part over**, and hold it in place. | 中文「翻轉」是**並列子句**插在移動與目的地之間；英文用**分詞片語**且目的地緊跟動詞。GM 的三個修飾語（距離／手度／目的地）在兩種語言的**相對順序不同** |
| 3 | ，**並點膠**，**並對準** | , **while dispensing glue**, **aligned to the point** | 中文的連接詞在**資料**裡（label 開頭的「並」）；英文的連接詞在**樣板**裡，資料只給乾淨片語。且 X（同時進行的程序）與 I（視覺對準）在英文應取**不同連接方式**（while ／ 過去分詞），中文則一律「並」 |
| 4 | 右手…（主謂結構） | RH: grasp…（**祈使句**，以手別作前綴） | 英文工業 METHOD 慣例是祈使動詞開頭。沿用中文主謂會得到 "The right hand grasps…" 這種沒有工廠會用的句子 |

**D7.5 生成與回填**：新存檔的 cycle 同時產 `narrative_zh` 與 `narrative_en`；
既有列由一次性回填腳本補。**回填腳本不得重算 TMU**——必須以每個 cycle 自己 pin 的
`rule_set_id` 載標籤（見 I4），否則就是拿現行 active 字典把歷史案件靜默重算一遍。

**D7.6 敘事排除規則：M 的伴隨維度不入句（2026-08-19 補入，User 裁決）**

M 格 `pricing_kind` ∈ {`hand`,`foot`}（`m_hand`／`m_foot`）的分量**兩語都不入句**。

- **依據**：IE 認證字典的 `parameters.M.controls` 是三個平行控制群，`hand_degree`／`foot_step`
  的選項**全部沒有句面**（字典自己的範例 `{verb:"理(<=4(10))", hand_degree:"<=180"}` →
  `mi_text: "理"`，句子只寫動詞）。它們是計價維度，不是動作動詞。
- **落點在敘事層、判準是 `pricing_kind`**，不是靠資料留空句面。三個理由：
  1. 直接編碼字典語意，對未來新增的同類計價方式自動生效；
  2. 不需要動任何 rule-set 資料（`certified_import` 凍結，改值要走 JSON→converter→新版本）；
  3. **留空句面達不到這個效果**——`_sent()` 的回退鏈（中文：句面→標籤；英文：句面→標籤→
     中文句面→中文標籤）一被走到就會把「手度」／"Hand turn" 漏進句子。
- 實作：`providers.build_label_map()` 把 `pricing_kind` 帶進 labels，中英兩套樣板各自的
  `_m_verb_entry()` 取第一顆非伴隨維度的分量；整格沒有動詞 → M 子句整段不出現
  （英文退回 "work at {to}"，與中文保留「在『to』一側」對稱）。共用的只有
  `rule_set_data.M_COMPANION_KINDS` 這個定義（R3 要求兩邊同步，D8 的雙語不變式守著）。
- **I1 不受影響**：排除的是字串。伴隨維度照常參與 `max()`——`m_push`45cm(16) ＋ 手度180(10)
  仍是 M16。
- **與引擎加嚴的關係**：ADR-028 A8（`M_COMPANION_WITHOUT_VERB`）同批落地，禁止「只有伴隨維度」
  的新輸入。但本規則**仍必須涵蓋那種形狀**：歷史 `most_cycles.slot_inputs` 裡就有這種列
  （依 ADR-023 §3.4 不改資料，實測 2 筆），任何**重新產生**敘事的路徑（存檔重算、
  motion module 版本讀取、日後的回填腳本）碰到它時，M 子句必須整段消失。
- **生效範圍（重要，別誤讀成「歷史列會自動修好」）**：worksheet 的
  `most_cycles.narrative_zh`／`narrative_en` 是**寫入時產生並落盤的快照**
  （`services/v2/worksheet_service.py` 存檔路徑產生、讀取路徑直接回欄位，不重算），
  所以本規則**只對之後寫入的 cycle 生效**。上述 2 筆既有列的錯誤敘事**不會自動消失**——
  它們現在也重存不了（A8 會擋 422），`scripts/backfill_narrative_en.py` 又只補
  `narrative_en IS NULL`。要清掉必須另寫一支**以各 cycle 自己 pin 的 `rule_set_id`
  重算敘事、不動 TMU**的腳本（follow-up，不在本輪）。
  **例外**：`motion_module_versions` 沒有 `narrative_en` 欄位（見 D7.2），其英文敘事是
  **讀取時即時產生**的，所以版本快照那條路徑一上線就自動套用本規則。

> **`sentence_text_*` 為 NULL vs 空字串：兩份文件語意衝突，此處留紀錄（不在本輪統一）。**
> `models/v2/rule_set_tables.py:63` 的欄位註解寫「`sentence_text_zh`：NULL 回退 `label_zh`」；
> `scripts/dev_seed_i18n_labels.py` 的句面表註解寫「空字串＝**刻意不入句**」並列出 7 條
> （`b_none`／`a_hard`／`a_press`／`m_hand`／`m_foot`／`x_none`／`i_none`）。實際資料裡
> `m_hand`／`m_foot` 是 `sentence_text_zh` **NULL** ＋ `sentence_text_en` **空字串**——兩種寫法各佔一半。
> 現況：**「不入句」從來不是由句面留空達成的**，7 條各有顯式機制（`a_hard`／`a_press` ＝
> `display_rule='hidden'`；`x_none`／`i_none` ＝樣板哨兵判斷；`b_none` 不入句；`m_hand`／`m_foot`
> ＝本節的 `pricing_kind`），而句面留空只是「這條沒有句面素材」的事實陳述，回退鏈照走。
> 兩份註解因此都只對了一半。要統一的話有兩條路（**本 ADR 不選**）：把「不入句」升為顯式欄位
> （例如 `sentence_text_*` 之外加 `narrative_visibility`），或明訂「空字串＝不入句、NULL＝回退」
> 並讓 `_sent()` 分辨兩者。在裁決前，**不要把任何新的「不入句」需求寄託在句面留空上**——
> 它不會生效，而且不會有測試變紅。

### D8 防止中英樣板漂移：語意不變式的雙語參數化測試（架構師獨立提案）

**問題**：兩套樣板 ＝ 兩份維護面積。未來 IE 改一條敘事規則（例如 E6 又加一個 `display_rule` 值），
很可能只改中文那套，英文靜默落後，而且**沒有任何測試會紅**。

**提案**：既有 `tests/unit/test_narrative.py`（E6 三態、A_move 手度翻轉、`×N`）
**參數化為 `locale ∈ {zh, en}`**，斷言的**不是字面字串**，而是**語意不變式**：

- `display_rule='hidden'` 的 addon 的可見詞**不出現**在任一語言的輸出中；
- `prefix_visible_term` 的可見詞**出現且僅出現一次**；
- `repeat_count=N` 在兩語輸出各出現一次重複標記；
- 物件名／來源／目的地在兩語輸出中皆出現。

任何只改一邊的變更，另一邊會缺一項不變式而紅。這是**結構性斷言**，不會因為英文用詞調整而假紅
（呼應 vault `02-Memory/Always-True-Assertion-Detector-Self-Disable.md` 的相反面：
斷言必須綁在會壞的性質上，不是綁在會變的字面上）。

### D9 範圍邊界：明確**不做**的三項，各附觸發條件

**(1) L3 — AI WI parser 英文化（獨立待辦）**
不動 `src/ddm_v2/nlp/`：不建英文 lexicon、不建平行英文 gold set、不做英文 parser 評測。
理由：中文 parser 的 gold set 才剛完成 P0 覆核（cycle 完成度誠實紀錄仍在爬升），
在單語都未收斂時開第二語言，等於把一個未證明的管線複製成兩個。
> **觸發條件（三者任一成立才啟動）**：(a) 有工廠實際以英文撰寫 WI 原始文件並要求匯入；
> (b) 中文 parser 的 gold 指標達到 ADR-026／worklog 定義的 L3 出場標準且穩定；
> (c) `_en` 覆核率達 100%（英文 lexicon 的素材就是覆核過的 `_en`——沒有它，英文 parser 沒有可信詞面來源）。

**(2) 匯出文件雙語（roadmap 草案第 4 項）— 本輪不做**
理由：匯出（Excel／CSV／LB 契約）的欄位語言涉及**外部消費方**（LB 匯入、客戶文件），
改它是跨系統契約變更，需與 LineBalance 協調（unified-arch），不是本 ADR 的單邊決定。
且 D7 的 `narrative_en` 一旦存在，匯出只是多一個 `?lang=` 參數的取欄問題（D3.3 已預留規則）。
> **觸發條件**：出現實際的英文文件收件人（客戶／海外廠／稽核），或 LB 端提出雙語欄位需求。

**(3) 錯誤訊息／API i18n（roadmap 草案第 5 項）— 本輪不做**
現況 domain 例外訊息中英混雜（例：「需要 analyst 以上角色」「rule-set 不存在：{code}」）。
理由：錯誤訊息 i18n 需要先把**訊息目錄化**（每個例外一個 code），那是獨立的錯誤契約重構，
規模與風險都不亞於本 ADR 全部三個 Phase；且錯誤訊息的主要讀者是 IE 與工程端（現況中文可讀）。
> **觸發條件**：(a) 有英文語系的一般使用者回報看不懂錯誤；或 (b) 需要對外開放 API 給第三方
> （屆時錯誤 code 化本來就是必要條件，i18n 順帶完成）。

**(4) 度量單位不在本輪**：`cm`／`TMU`／秒維持原樣，不做 inch 轉換。單位轉換會動到引擎輸入，
與「語言只影響字串」的不變式（I1）直接衝突，必須是獨立決策。

### D10 分階段（每階段可獨立驗收）

| 階段 | 內容 | 完成判準 |
|---|---|---|
| **A** | 前端 i18n 框架導入 ＋ UI 外殼字串外部化 ＋ 標頭語言切換 ＋ `app_users.locale` ＋ `/me` 帶 locale ＋ `PATCH /me/locale` | 切到 en 後，**外殼**（側欄 7 項＋admin 2 項、標頭、按鈕、表頭）無中文殘留；切回 zh 與 v3 截圖對照一致；e2e 全綠 |
| **B** | 7 張選項表 ＋ 詞彙 ＋ 範本的 `label_en`／`name_en` 機器灌值 ＋ `i18n_review_state` ＋ 待審清單 ＋ 覆核 UI | active 版 63 列選項（＝**126 個可譯欄位**：label ＋ sentence）與 59 筆詞彙**皆有英文且皆有來源標記**；待審清單顯示 `n/126` 且可指派；`legacy_seed` 16 筆正確落在未覆核側；**英文標籤唯一性檢查（I5）零衝突** |
| **C** | `sentence_text_en`（7 表＋clone 路徑三處）＋ 英文樣板系統 ＋ `most_cycles.narrative_en` ＋ 回填腳本 ＋ 雙語參數化敘事測試 | D7.4 的四個語序案例在英文輸出中成立；`run_all.py` 黃金值 **GM=28／CM=29** 不變；回填腳本對 TMU 零改動（前後 diff 為空） |

**A 可獨立上線**（外殼英文＋資料仍中文，是可用的中間態）。**B 依賴 A**（沒有語系切換，灌了也看不到）。
**C 依賴 B**（沒有 `sentence_text_en` 的素材，英文敘事只能回退中文）。

---

## 3. 架構不變式（違反即否決）

**I1 — `most_engine/` 的 TMU 計算零改動。** 語言只影響字串。
可機械檢查：Phase A/B 對 `most_engine/` 的 diff 應只有 `narrative.py`（Phase C），
且 `scripts/core_logic/run_all.py` 黃金值（GM=28／CM=29）在三個 Phase 後皆不變。

**I2 — 中文輸出不得因英文化而改變。** 既有 `narrative_zh` 的產出、既有 `label_zh` 的顯示、
既有 e2e 的中文斷言，全部維持位元級不變。英文是**加上去的第二條路徑**，不是把既有路徑一般化後的分支
（ADR-011 加法演進）。

> **適用範圍（2026-08-19 User 裁決，補說明，不改上段語意）**：I2 守的是**實際資料**的輸出。
> 「入口驗證已擋掉、且 DB 零存量」的不可能輸入（例如純空白的詞彙名）不在保護範圍內——
> 對這類輸入做防呆硬化（`narrative.py` 與 `narrative_en.py` 的 vocab `.strip()`，R3 要求兩邊同步）
> 雖然字面上改變了中文輸出，但對任何實際存在的資料位元級不變，不視為違反 I2。
> 判準：改動後 `tests/unit/test_narrative.py` 的 `test_zh_*` 逐字斷言必須**全數不變且全綠**；
> 有任何一條需要改測試去迎合程式，就是真的踩到 I2，必須退回重議。

> **例外：修正錯誤敘事（2026-08-19 User 裁決）**。I2 守的是「**中文不得因英文化而改變**」——
> 它禁的是英文化造成的副作用，不是禁止修正一句本來就寫錯的中文。D7.6 的敘事排除規則
> （M 的 `pricing_kind` ∈ {hand,foot} 不入句）**同時改變中文與英文輸出**，且改的是**實際資料
> 的形狀**（實測 2 筆 `most_cycles.slot_inputs` 是這種形狀，舊敘事產出「以手度實施移動」
> 而該格是 0 TMU、英文對應 "Then Hand turn at the bench"）。這屬於**刻意的錯誤修正**，
> 不是英文化的副作用：
> 它由字典語意驅動，就算沒有英文化也該修，只是英文側同一個缺陷讓它被發現。
> 判準（與上一段的空白防呆不同，因為這裡**確實**要改中文輸出）：
> 1. 變更必須**兩語同時**（R3），且只影響 M 的伴隨維度子句，其餘子句位元級不變；
> 2. `test_zh_*` 六條逐字斷言仍須**全數不變且全綠**（它們驗的是 P/X/I 與 twist，不碰此路徑）；
> 3. TMU 不得改變（I1）——伴隨維度照常參與 `max()`。
> 三條有任何一條不成立，就不是「修正錯誤敘事」而是真的踩到 I2，退回重議。實測：
> `test_zh_*` 6 passed、一條未改；黃金值 167 項全綠。
>
> **落地範圍**：worksheet 的 `narrative_zh`／`narrative_en` 是**存檔時**產生的快照
> （讀取路徑直接回欄位、不重算），所以本例外實際改到的是**之後寫入**的 cycle；
> 上述 2 筆既有列的舊敘事仍原樣躺在 DB，要清掉得靠獨立的重算腳本（D7.6，follow-up）。
> 這一點反而讓 I2 的風險更小：既有中文輸出連「刻意修正」的那部分都沒有被就地改寫。

**I3 — `_en` 不得進入任何決定 TMU 的路徑。**
禁止：`_en` 被登記為同義詞、被寫入 `motion_templates.keywords`、被 `nlp/lexicon.py` 建索引、
被 `template_matching.score_keywords` 消費。
> 這條有既有的近因：`features/dictionaries/api.ts:117` 的範本搜尋**已經在比對 `name_en`**
> （前端純顯示過濾，無害），而 `motion_templates.keywords` **已經含英文關鍵字**且**會決定套用哪個範本、
> 進而決定 TMU**。兩者只隔一個「順手把 name_en 也加進 keywords」的提交。
> 更根本的依據是 ADR-023 規則 1 補節二：**同義詞登記的合法來源只有「標籤衍生」與「IE 裁決」兩種，
> 工程端不得以相似性自行判定**——機器翻譯的英文字串屬於第三種來源，明文禁止。
> 可機械檢查：CI 守衛擋 `nlp/`、`template_matching.py`、`synonym_service.py` 讀取任何 `_en` 欄位。

> **近失（2026-08-19）：守衛漏放了一次真實違規，因此擴大兩個維度。**
> 實作 ADR-028 A8 時，有人做 DRY 清理，把 `services/v2/wi_ai_service.py::_option_labels()`
> ——一份**刻意重複的純中文** label map——換成 `most_engine/providers.py` 的共用 label-map
> builder。那條路徑是 `wi_ai_service` → `most_compiler/engine_gate.py` → `compute_cycle`，
> **決定 TMU**；共用 builder 會把 `label_en`／`sentence_text_en` 帶進 labels dict。
> 改動當下 unit 1159 ＋ integration 533 ＋ 黃金 174 **全綠**，本守衛也全綠，由人工複審擋下。
> 失效原因有兩個，缺一不可：
> 1. **覆蓋面**——`_guarded_py_files()` 當時只掃 `nlp/`＋2 個檔，`most_compiler/` 與
>    `wi_ai_service.py` 都不在內。
> 2. **穿透性**——就算掃了也抓不到：違規的字面是那支 builder 的**函式名**，
>    `label_en` 三個字在 `providers.py` 裡，不在被掃的檔案裡。**純欄位名 grep 看不穿函式邊界。**
>
> 處置（已落地於 `tests/unit/test_i18n_en_field_isolation.py`）：掃描範圍加入
> `most_compiler/` 與 `wi_ai_service.py`；新增**載體符號**維度 `FORBIDDEN_EN_CARRIERS`
> ——「本身會把 `_en` 具體化進回傳值的 helper」，守衛對象呼叫它即違規；並加後設測試回頭
> 驗證每個載體的定義確實仍含 `_en` 欄位（避免清單腐爛成沒有根據的魔法字串）。
> 擴大後以還原前的版本實測：`test_i3_no_en_carrier_calls_in_tmu_determining_paths`
> **1 failed**，錯誤訊息精確指出 `(wi_ai_service.py, build_label_map)`；還原後 6 passed。
> `_option_labels()` 上也補了錨點註解說明「這份重複是刻意的」——先前它一個字的說明都沒有，
> 這正是它會被 DRY 掉的機械成因。
>
> 一般化的教訓（值得套用到其他 grep 型守衛）：**零容忍的字面 grep 只能守「符號出現在被掃檔案裡」
> 的違規**。當一個 helper 把受管制的東西封裝起來，違規就會從被掃的檔案裡消失，
> 而守衛依然全綠——每個 grep 型守衛都該一併問「有沒有一支函式可以代我讀它？」

**I4 — 敘事回填不得重算 TMU。** 回填 `narrative_en` 必須以每個 cycle 自己的 `rule_set_id`
載入標籤（`most_cycles.rule_set_id` 是回放的唯一依據）。以現行 active 字典重算歷史 cycle，
是 CLAUDE.md〈No error bypass〉等級的靜默資料汙染。

**I5 — 同一參數內，英文標籤正規化後必須唯一。**
實測風險是量化的：`g_grasp`（抓握，**base_tmu=6**）與 `g_touch`（接觸，**base_tmu=3**）
若被翻成無法區分的英文，英文介面下 IE 選錯格＝**TMU 差一倍**。
`g_pat`（輕拍）／`g_tap`（輕按）同為 3 TMU、`m_tearopen`（撕開）／`m_teartape`（撕除）
是幾乎必然碰撞的一組。灌值腳本必須以 `(rule_set_id, 參數表)` 為範圍做唯一性檢查，
**有衝突就中止並列出衝突對，不得自動加後綴矇混**。

**I6 — 語系碼與欄位後綴的對照唯一**（D3.1）：`zh-TW`↔`_zh`、`en`↔`_en`。
不得出現第三種寫法，也不得在程式碼裡各自維護一份對照。

---

## 4. 考慮過的選項

### 4.1 語言來源（User 已選 A）

| 選項 | 取捨 | 判定 |
|---|---|---|
| **A. 使用者個人設定（`app_users.locale`）** | 跨裝置一致、可由本人隨時切換、行為決定性高（截圖／e2e／客服可重現）。代價：多一個欄位、多一個端點、新使用者需自己切一次 | ✅ **User 裁決採用** |
| B. 站別／廠區固定 | 「這個廠說英文」聽起來合理，且無需個人設定。**否決理由**：語言是**人**的屬性不是**地點**的屬性——同一廠內台籍 IE 與外籍 IE 並存是常態；而且 v2 的 `plant_code` 來自 gateway 注入的身分，使用者無法自行更正，一旦判錯就**完全無法自救**。此外 `site_ids` 是複數（一人可跨廠），「站別語言」在多站使用者身上無定義 | ❌ |
| C. 瀏覽器 `Accept-Language` 自動偵測 | 零設定、首次體驗好。**否決理由**：(a) 破壞決定性——同一使用者換台電腦／換瀏覽器就換語言，Playwright 截圖與 e2e 斷言變成環境相依（現有 11 個 spec 以中文文字定位）；(b) 工廠共用電腦的瀏覽器語系與使用者無關；(c) 客服情境「我的畫面變英文了」無從查起。**可保留為單一用途**：未來若要為從未表態的新使用者做首次預設，可讀一次 `Accept-Language` 寫入 `locale`——**但那是寫入偏好，不是每次請求都協商**，且本輪不做 | ❌（本輪） |

### 4.2 翻譯權威（User 已選 A）

| 選項 | 取捨 | 判定 |
|---|---|---|
| **A. 機器翻譯先全灌，人工後修** | 英文介面立刻可用；覆核可增量、可指派。代價：上線期間顯示未覆核字串（風險 R1，以 I5＋code 併顯緩解） | ✅ **User 裁決採用** |
| B. 先出草稿，IE 逐條核准才上線（fail-closed，比照 gold set） | 治理上最乾淨，與既有 gold-review 慣例完全一致。**否決理由（User 立場）**：63 列選項＋59 筆詞彙＝122 條逐條核准，在 IE 手上會排在所有交付之後，實際結果是英文永遠 0%，功能等於沒做。**架構師補充**：gold set 的 fail-closed 有硬理由（草稿會變成 TMU 的標準答案），翻譯沒有——在 I3 成立的前提下，錯的譯文只讓人看得困惑，不讓數字變錯。爆炸半徑不同，治理強度不必相同 | ❌ |

### 4.3 譯文的儲存位置（架構師評估，User 未指定）

| 選項 | 取捨 | 判定 |
|---|---|---|
| **A. 沿用既有 `_en` 欄 ＋ 獨立覆核側表** | 零資料遷移、零 API 契約變更（`label_en` 已在 `/options`、`/full`、`paramSchema.ts`）；覆核狀態與被覆核物分離（同 gold review-state 形狀）。代價：新增語系要加欄（`label_ja`…），第三語系時需重新評估 | ✅ **採用** |
| B. 譯文也搬進通用翻譯表（`i18n_translations`，含 text） | 對 N 語系最乾淨，加語系＝加列。**否決理由**：要遷移既有欄、改 7 張表的 `load_full`／`_insert_children`／schema 與前端消費點，而換來的好處只在「有第三語系」時才兌現——目前沒有任何第三語系的需求證據。**這是為假想需求付現金** | ❌（列為 R5 的重評路徑） |
| C. 每張表各自加來源標記欄（`label_en_source`、`label_en_reviewed_by`…） | 無多型鍵、有 FK 完整性。**否決理由**：9 張表 × 4 欄 = 30＋ 欄，且待審清單要九路 UNION；每加一個可譯欄再乘一次 | ❌ |

### 4.4 英文敘事的產生路徑（架構師評估）

| 選項 | 取捨 | 判定 |
|---|---|---|
| **A. 平行英文樣板系統**（共用輸入、各自組句） | 語序正確、可測；代價是兩套樣板要同步維護（以 D8 緩解） | ✅ **採用**（User 裁決 4 同向） |
| B. 中文敘事整句丟機器翻譯 | 最省事。**否決理由**：整句 MT 會把 TMU 相關名詞翻得不一致（同一個 `g_grasp` 在不同句子裡可能翻成不同字），失去「同一個 key 一個譯文」的單一真相；且每次顯示都要外呼翻譯服務或再存一份快取。**User 裁決 4 已明確否決** | ❌ |
| C. 同一套樣板，語序差異用條件分支處理 | 只有一份程式。**否決理由**：1.2b／D7.3 的三項證據顯示差異不在字串而在**結構**（連接詞歸屬、`display_rule` 位置語意、句型骨架），條件分支會讓 `narrative.py` 每個 slot 都長出 `if locale ==`，中文路徑的可讀性與可審性一起賠掉，且違反 I2（中文輸出不得被英文化改動的風險大增） | ❌ |

---

## 5. 後果

**正面**

- 英文使用者可用完整介面（外殼＋標籤＋敘事），不需要看中文猜。
- `label_en` 從「API 契約裡永遠是 null 的欄位」變成有值、有出處、有覆核狀態的資料。
- ADR-023 規則 1 的矩陣補上一列，`_en` 的可變性從「靠實作默契」變成明文規則。
- 覆核工作變成可查詢、可指派、可驗收的清單，而不是「有空再說」。

**代價 / 注意**

- **維護面積 +1 套敘事樣板**（以 D8 的雙語參數化測試緩解，但不消除）。
- **e2e 與截圖驗收受影響**：現有 11 個 spec 以中文文字定位（`toHaveText(/主數據管理/)` 等）。
  Phase A 後**必須固定測試使用者的 locale 為 `zh-TW`**，否則預設值一改，整批 e2e 紅。
  同理，ADR-021 要求的「Playwright 截圖對照 v3」**一律以 zh 語系截圖**——
  v3 完全沒有英文（實測 24 表零 `_en`／`locale` 欄），英文畫面沒有母版可對照。
- **ADR-021 的加法偏離**：語言切換是 v3 沒有的 UI 元素。本 ADR 判定 ADR-021 的權威範圍是
  **資訊架構（IA）與畫面結構**，不是「禁止任何 v3 沒有的全域控制項」；切換器不新增側欄項、
  不改變任一分頁的結構，故不觸及 ADR-021 的核心約束。**但這一點必須由 User 確認**（P8）。
- **前端 553 處字串字面值的外部化是機械但量大的工作**，且期間容易出現「一半 key 一半硬編」的
  中間態。Phase A 應以「側欄／標頭／共用元件」為第一批，逐分頁推進，並在 CI 加一條
  「新增的 `.tsx` 不得含中文字面值」的守衛，防止外部化速度輸給新功能寫入速度。

---

## 6. 待定參數（本 ADR **不**擅自填值）

| # | 參數 | 為什麼不能猜 |
|---|---|---|
| **P1** | **英文的實際讀者是誰**（外籍作業員／海外廠 IE／客戶文件收件人／稽核） | 這決定三層的價值順序。若真正的驅動是**客戶文件**，那本輪排除的「匯出雙語」才是最高價值，而 Phase A 的 UI 外殼是最低價值——順序會整個顛倒。**User 的裁決給了範圍，但沒有給讀者**；本 ADR 依裁決執行，同時誠實記下：**若 P1 的答案是「客戶文件」，D9(2) 的觸發條件應立即成立，本 ADR 的階段順序需重排** |
| **P2** | **機器翻譯服務／模型的選擇** | 供應商（雲端翻譯 API／自架模型／既有 LLM 管線）牽涉資料外流政策（工序名稱與物料名是廠內資訊）、成本、可重現性（同一輸入是否恆得同一輸出，關係到能否用腳本重跑驗證）。**不擅自決定**。灌值腳本應設計為「翻譯後端可替換」的介面，並把服務識別字串寫進 `translated_by`，讓日後可追「這批是哪個模型翻的」 |
| **P3** | **是否提供 MOST 標準術語表（termbase）給翻譯服務** | MOST 是國際標準，A/B/G/P/M/X/I 與 Gain Control／Placement／Action Distance 等在英文有**既定術語**。若不給術語表，MT 會自創譯法（例：`m_screw` 的 `label_zh` 是「滑出螺絲」，逐字翻會得到 "slide out screw" 這種業界看不懂的東西）。建議做，但術語表內容須由 IE 提供／確認——**工程端不得自行認定 MOST 標準術語**（同 ADR-023 補節二的精神） |
| **P4** | **`work_vocab_items` 的英文是否該由 MES/ERP/PLM 同步而非翻譯** | 詞彙庫是主數據且 `source_system` 已含 `mes/erp/plm`（ADR-024）。廠內物料在 ERP 裡**很可能已有官方英文品名**——若有，翻譯它是製造第二個真相。灌值前必須確認：這 59 筆的英文，是翻譯的產物還是同步的產物 |
| **P5** | **`sites`／`products`／`skus` 的 `name_en` 是否納入** | 這三張表也有空的 `name_en`（各 1 筆）。它們是組織階層主數據，英文名可能有官方定名（法人名稱、產品行銷名），不該由 MT 決定。本 ADR 的 Phase B **暫不納入**，待 P4／P5 一併確認 |
| **P6** | ~~待審清單的呈現位置~~ **已定案（Phase B 前端實作補記，2026-08-18）**：「主數據管理」頁第三分頁，見 D6 | 側欄項數是 ADR-021／024 反覆爭取的稀缺資源，這點勝過「清單同時涵蓋字典與主數據兩類物件、放哪邊都有一半是別人家的東西」的顧慮 |
| **P7** | **第三語系是否在可見的未來出現** | 直接決定 4.3 選項 A 是否要在某個時點轉為 B。若答案是「會」，`sentence_text_en` 這批加欄就是在挖未來的坑（每語系 ×7 欄）。目前無證據，故按 A 走並列入 R5 |
| **P8** | **語言切換器是否算違反 ADR-021 的 v3 母版原則** | 本 ADR 判定不違反（§5），但 ADR-021 的權威是 User 的使用者驗證，不是架構師的推理。**核可本 ADR 時請一併確認這一點** |

---

## 7. 風險

**R1 — 機器翻譯對 MOST 近義術語的誤譯（最高風險，已量化）**
`g_grasp`（抓握，6 TMU）與 `g_touch`（接觸，3 TMU）是不同 TMU 的兩個選項；
`g_grab`（抓取）／`g_grasp`（抓握）／`g_regrasp`（重新抓握）三者中文靠一個字辨義；
`g_pat`（輕拍）／`g_tap`（輕按）與 `m_tearopen`（撕開）／`m_teartape`（撕除）是必然碰撞組。
英文介面下若兩個選項看起來一樣，IE 選錯格，**翻譯錯誤就變成工時錯誤**。
**緩解**：I5 的唯一性檢查（機械、灌值時阻斷）＋ D2 的 option code 併顯（`grasp (g_grasp)`）
＋ P3 的術語表。**殘留風險**：唯一性檢查只擋「字面相同」，擋不住「字面不同但同樣難以辨義」
（"grab" vs "grasp"）——這只能靠 IE 覆核，也正是待審清單存在的理由。

**R2 — 「之後有空再修」永遠不會發生**
這是本 ADR 最可能的失敗模式：MT 灌完、清單建好、`n/126` 停在 126，兩年後沒人記得那個數字的意思。
**緩解**：Phase B 的完成判準寫的是「數字可見且可下降」而非「翻譯存在」；清單預設過濾為
「active 版 ＋ 主數據」把工作量壓在 122 條以內（不是 113＋59 全量）。
**殘留風險**：本 ADR 不設期限（期限屬 User 的排程權）。若六個月後覆核率仍為 0%，
應視為**這個功能的英文讀者其實不存在**（P1 沒有答案），屆時該檢討的是要不要繼續維護英文，
而不是再加一個提醒機制。

**R3 — 兩套敘事樣板漂移**
未來 IE 改一條敘事規則（新增 `display_rule` 值、改 GM 修飾語順序），只改中文那套。
**緩解**：D8 的雙語參數化語意不變式測試。
**殘留風險**：不變式只覆蓋「已知會壞的性質」；全新的規則類型（例如新增一個 slot）
會在兩邊都沒有斷言。**建議在 `narrative.py` 與英文樣板檔頭互相標註「改這裡必須改那裡」**，
並在 CI 加一條低成本守衛：兩個樣板模組的檔案 mtime／diff 若只有一邊變動，PR 需顯式說明理由。

**R4 — 外部化的中間態**
Phase A 期間必然有一段「一半 key、一半硬編」。若新功能持續以硬編中文寫入，外部化永遠追不完。
**緩解**：Phase A 完成後立即加 CI 守衛（新增 `.tsx` 不得含中文字面值），把守衛與外部化同批交付，
不要留到「之後補」。

**R5 — 第三語系出現時，`_en` 欄的設計會變成負債**
每個語系 ×（7 表 label ＋ 7 表 sentence ＋ vocab ＋ template）＝ 16 個加欄。
**緩解**：`i18n_review_state` 的 `locale` 欄已是值域可加法擴充的形狀，**覆核治理不需重做**；
真正要遷的只有文字欄。**觸發重評（§8）**：第三語系一被提出，立即重新評估 4.3 選項 B。

**R6 — `_en` 從顯示層滲進判斷層**
I3 禁止，但禁令的執行力取決於守衛是否真的存在。現況已有兩個鄰接面
（`motion_templates.keywords` 決定 TMU、`dictionaries/api.ts:117` 已在比對 `name_en`），
距離「順手把 name_en 加進 keywords」只有一個提交。
**緩解**：I3 的 CI 守衛必須與 Phase B **同批交付**，不得延後——一旦滲入，
它會以「範本比對更準了」的面貌出現，沒有人會覺得那是 bug。

---

## 8. 重新評估的訊號（proposed 必填）

1. **P1 的答案是「客戶文件／海外收件人」** → D9(2) 的觸發條件即時成立，階段順序需重排（匯出優先於 UI 外殼）。
2. **第三語系被提出** → 重評 4.3（A → B 的資料模型遷移）與 R5。
3. **Phase B 上線六個月後覆核率仍為 0%** → 視為英文讀者不存在的證據，檢討是否停止維護 `_en`
   （而不是加提醒機制）。
4. **I5 的唯一性檢查在灌值時大量衝突（> 10% 選項）** → 表示 MT 對本領域的辨義能力不足，
   應退回「先術語表、後 MT」甚至退回 4.2 選項 B（逐條 IE 核准）——D2 的成立前提被證偽。
5. **IE 開始要求「英文也要能反查 option」** → 那是英文進入建議層的訊號，I3 必須先被正式推翻
   （需新 ADR，且要回答 ADR-023 補節二的「合法來源」問題），不得默默放行。
6. **`sentence_text_en` 加欄後發現 clone／`PUT /full` 靜默丟值** → 說明 D7.2 的三處同步沒做全，
   應立即補測（同一個 option 經 clone 後 `sentence_text_en` 必須逐字相等）。

---

## 9. 不由本 ADR 決定

1. 機器翻譯服務／模型的選型（P2）與其資料外流政策。
2. 待審清單的具體介面（P6）與視覺設計。
3. MOST 標準英文術語表的內容（P3）——屬 IE 權威，同 ADR-014 的值權威邏輯。
4. `work_vocab_items`／`sites`／`products`／`skus` 的英文是否來自 ERP 同步（P4／P5）。
5. 匯出雙語的欄位形狀（雙欄並列 vs 依 `?lang=` 切換）——涉及 LB 契約，歸 unified-arch。
6. 覆核工作的期限與人力分配。

---

## 10. 核可後的必辦事項（不是可選的收尾）

1. **ADR-023 §3.3 規則 1 矩陣加一行交叉引用**指向本 ADR 的 D4（`_en` 可後補；`_zh` 維持凍結）。
   不做這件事，ADR-023 與實作會立刻不一致——這正是 ADR-024 事後剖析裡「只改一半」的病。
2. **`docs/roadmap/phase5-i18n-full-bilingual-spec.md` 標記為被本 ADR 取代**
   （其〈現況（已有的一半基礎）〉一節與事實不符，見 §1.1；保留檔案供追溯，但不得再被當作實作依據）。
3. `docs/decisions/README.md` 與 `docs/DOC_REGISTRY.md` 的狀態同步（本次已隨 ADR 一併提交為 proposed）。
