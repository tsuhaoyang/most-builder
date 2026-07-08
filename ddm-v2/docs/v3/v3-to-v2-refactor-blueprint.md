# v3 → v2 Refactor 藍圖（核心邏輯 + 功能整合設計）

> **狀態**：設計定稿中（本文件即設計，尚未改程式）。
> **前置文件**：[v2-v3-core-logic-diff-and-integration.md](v2-v3-core-logic-diff-and-integration.md)（差異盤點）。
> **裁決基準（User 2026-07-04 拍板）**：
> 1. **v3 的資料與使用邏輯經 IE 認證，為權威**——差異盤點中的 C1（M 階梯=吋(cm)）、C2（M 腳步採 v3 值）、C3（X 捨入採 v3）、C5（I/X 擴充檔位）、C6（G 選項即語意）、C8（以字典 JSON 為準）、C9（A3 只算 reach）全部依 v3 定案。
> 2. **SIMO：UX 用 v3 配對標記、引擎仍取 max**（防標錯低估工時的安全網）。
> 3. **檢索架構走 pgvector / 中文語意方向**，為未來 LLM+VLM 接入預留。
> 4. **WI Pool（MI 語句庫→搜尋→組裝工序表）是核心使用邏輯**，以相同概念優化結構後納入 v2。
>
> 遵循 skills：[[architecture-v2]]（單一引擎、規則是資料、ADR 制度）、[[ie-most-engineer]]（黃金測試鐵則）、[[database-v2]]（約束進 schema、手寫 migration）、[[engineering-standards]]。

---

## 1. 總體策略

```
v3（IE 認證的值與使用邏輯）          v2（架構與引擎骨幹）
┌─────────────────────┐            ┌─────────────────────────────┐
│ minimost_ai_dictionary │──值──────▶│ rule-set MINIMOST_FACTORY_V2 │ ← 新版本資料，引擎不分叉
│ 使用邏輯（repeat/顯示規則│──行為────▶│ most_engine 單點修改＋黃金重錨 │
│  /SIMO配對/覆寫留痕）   │            │                             │
│ WI Pool＋組裝工作流     │──概念────▶│ 組件庫 motion_modules（§5）    │
│ NL 解析＋同義詞         │──重寫────▶│ nlp/ 新套件（port-adapter）    │
└─────────────────────┘            └─────────────────────────────┘
```

**不變的鐵則**：引擎只有一套（`most_engine/`）；規則是版本化資料；cycle 快照 `rule_set_id` 可回放；每項變更先寫黃金測試再實作。v3 的程式碼本體（兩套引擎、規則式 parser 現碼）**不搬**，只搬其認證過的值、規則語意與工作流概念。

**連鎖影響（必須同步改版，否則反漂移機制會反過來擋住正確的值）**：
- `docs/core-logic/minimost-sequence-model-core-logic-spec.md` §4 全面改版（M 階梯單位、M 腳步、X 捨入、G gating、I/X 檔位、A3）
- `docs/core-logic/core-logic-validation-test-catalog.md` 黃金/反例重錨
- `scripts/core_logic/` 驗證器、`tests/unit/test_most_engine.py`
- `.claude/skills/ie-most-engineer/SKILL.md`（計算口徑段落：X ceil→half-up、M 階梯吋(cm)、G gating 移除）
- memory：`sequence-model-three-source-divergence` 標記 resolved（第四來源 v3 字典為權威）

---

## 2. ADR 清單（依 architecture-v2 制度，先立決策再動工）

> 編號自 **ADR-014** 起：012（3D 渲染）、013（Excel 匯入）已被既有決策使用。

| ADR | 標題 | 狀態建議 | 摘要 |
|---|---|---|---|
| **ADR-014** | v3 IE 認證字典為 MiniMOST 值權威 | proposed→accepted | `minimost_ai_dictionary_v1.json` 取代 1205/JS 成為值的唯一來源；黃金測試重錨；部分取代舊 OQ 裁決（Q3 ceil→half-up、M 階梯單位）；**保留**不乘 10、1 TMU=0.036s |
| **ADR-015** | NL 解析納入 scope | proposed | **supersedes ADR-010（NL→MOST 暫緩）**——IE 已在 v3 自行開發並認證用法；v2 以 `DraftParserPort` hexagonal 接入，第一版 rule-based adapter（修正 v3 五缺陷），預留 wi-parser-upgrade Stage 2/3 |
| **ADR-016** | 檢索架構：pg_trgm + pgvector 混合、EmbeddingProvider port | proposed | 見 §4；為 LLM+VLM 預留的基礎設施決策（含 Postgres image 變更），屬「引入外部依賴」必須 ADR |
| **ADR-017** | 組件庫：motion_modules 合併範本與 MI 語句概念 | proposed | 見 §5；消滅「兩套範本體系」的單一真相決策 |
| **ADR-018** | 審核工作流與角色收斂 | proposed | v3 五角色（analyst/reviewer/approver/viewer/admin）與 v2 RBAC（IE/manager/admin）+ LB 共享登入收斂成一套；狀態機 draft→submitted→reviewed→approved(=published)→retired |

---

## 3. 值層與引擎變更（Phase 1 核心）

### 3.1 新 rule-set `MINIMOST_FACTORY_V2`（資料變更）

Seed 來源直接由 `ddm-v3/minimost_ai_dictionary_v1.json` 程式化轉換（寫一支 converter script，不手抄——手抄是漂移源）。`MINIMOST_FACTORY_V1` 保留（published、供舊 cycle 回放）。

| 參數 | V2 rule-set 內容 | schema 動作 |
|---|---|---|
| A | 帶值不變；**A3（返回格）僅 reach** | 引擎規則（見 3.2），資料不變 |
| B | 0/10/32/42 不變（`b_none` 保留為顯式預設列） | 無 |
| G | 值不變；**全部 `requires_modifier=false`**（v3「選項即完整語意」）——gating 語意由資料驅動，**引擎零修改** | 無（純資料） |
| P | base/addon 值不變；addon 新增 `display_rule`（show_self / hidden / prefix_visible_term）；`a_align` 改為選項自含精度語意（`needs_precision=false`、label 含「精度<4mm」） | `rule_p_addons` 加欄 `display_rule text`、`sentence_text_zh text` |
| M 階梯 | 門檻改 **cm 正確值：≤2.5→3, ≤10→6, ≤25→10, ≤45→16, ≤75→24**；`>75→42` 檔是否保留列 OQ 問 IE（v3 動詞無此檔、v3 腳步有） | 資料值變更（欄位不變，`max_cm` 語意修正） |
| M 腳步 | **獨立於階梯**：≤25→10, ≤40→16, ≤55→24, ≤75→32, >75→42 | **新表 `rule_m_foot_bands`**；`m_foot` 動詞 pricing_kind 改 `foot` 讀新表 |
| M 旋轉/手度 | ≤12.5cm 1/2/3圈=16/32/42；≤50cm 1/2圈=24/42（>50cm 與大直徑 3 圈檔列 OQ）；手度 ≤90→6、≤180→10 | 資料變更 |
| X | 九檔（壓合/卡合&壓合/熱熔/點膠/鎖附0.216→6/鐳雕/刷PPID/刷工單/刷條形碼）；`x_none` 保留 | 資料變更（rows） |
| I | 八檔（檢查/確認 ×正常6/範圍外16；對準到點 10/24；對齊兩點 16/32）+ `i_none` | `rule_i_options` 加欄 `vision_scope text`（normal/outside，供 UI 分組） |
| 全參數 | 選項補 `sentence_text_zh`（narrative 用字與計算標籤分離，v3 字典已提供） | 各選項表加欄 `sentence_text_zh` |

### 3.2 引擎修改（單點、每項配黃金測試）

| # | 修改 | 位置 | 黃金測試影響 |
|---|---|---|---|
| E1 | A3 返回格僅算 reach（slot6 拒收 `twist_deg`/`foot_cm` → 新錯誤碼 `A_RETURN_COMPONENT`） | `calculate.py` slot6 路徑 | 新增反例 |
| E2 | X 捨入 ceil → **Decimal 除法 ROUND_HALF_UP（TMU 3 位）**，同步全引擎輸出精度口徑（TMU 3 位、秒 4 位） | `calculate.py` `_x_tmu` + 合計 | **X 10s：278 → 277.778**；黃金重錨 |
| E3 | P 附加互斥：`a_insert` ⊥ `a_snap` → 新錯誤碼 `P_ADDON_CONFLICT`；「有附加必有 base」已由現行「無 base→0」涵蓋，改為顯式 422 | `_p_tmu` | 新增反例 |
| E4 | **slot 級 `repeat_count`**（slot_inputs 新欄位，G/P/X/I 整格乘、**M 僅乘 verb 再進 max**——v3 認證規則）；驗證 ≥1 整數 | `calculate.py` 各 slot fn | 新增黃金（推×16 等） |
| E5 | SIMO：引擎維持群組 max；**儲存層把 `simo_with_row_id` 配對正規化為 `simo_group_id`**（配對→同組），前端用 v3 配對 UX | `worksheet_service.py` 轉換；引擎不動 | 不變 |
| E6 | narrative：實作 P `display_rule` 三態（插入/卡合取代 base 動詞、對準前綴、較難處理/施加壓力隱藏）與 A_move 手度「翻轉+目標物」規則 | `narrative.py` | 新增敘事黃金 |
| E7 | 人工覆寫：`slot_inputs` 每格新增選填 `manual_override {tmu, reason, by}`；覆寫時 `computed` 記 before/after 進 audit | `calculate.py` + schema | 新增測試 |
| E8 | 黃金值重標定：GM=28 不變；CM=29 輸入語意改為「推 18 吋（45cm）」；全部 89 案例逐一過帳 | `scripts/core_logic/` | 全面重錨 |

工序表層新增 `allowance_percent`（worksheet 級，`standard_seconds = normal × (1+allowance%/100)`）；與 LevelEntry `coefficient`（列級難度係數，LB 用）**語意不同、兩者並存**——寬放是「休息/疲勞政策」、係數是「動作難度」，寫進 spec 防混用（接續既有 [OQ-002 Allowance 與標準工時](../decisions/OQ-002-allowance-and-standard-time.md) 討論，請 IE 確認命名與預設值）。

---

## 4. 檢索架構（User 裁決：走 pgvector / 語意方向，為 LLM+VLM 預留）→ ADR-016

### 4.1 設計：三層檢索、一個投影表、一個 port

```
查詢 "抓螺絲放治具"
   │
   ├─ L1 確定層：同義詞/代碼精確命中（rule_option_synonyms，正規化最長匹配）→ 命中即回，零模糊
   ├─ L2 文字層：pg_trgm GIN 子字串/相似度（中文 trigram 可用，無需斷詞extension）
   └─ L3 語意層：pgvector KNN（embedding）→ 與 L2 做 RRF 融合排序
                     ▲
             EmbeddingProvider port（hexagonal）
             ├─ adapter: 本地 BGE-M3 服務（地端、離線）
             ├─ adapter: API embedding（雲端）
             └─ adapter: null（未配置時系統仍可用，只退化到 L1+L2）
```

**`search_documents` 投影表**（單一檢索面，所有可搜尋實體投影進來）：

```sql
search_documents(
  id uuid PK,
  doc_type text CHECK (doc_type IN ('motion_module','wi_row','vocab','worksheet')),
  ref_id uuid NOT NULL,          -- 回指來源列
  rule_set_id uuid NULL,         -- 值版本語境
  content_norm text NOT NULL,    -- 正規化全文（NFKC+繁簡統一，見 §6 nlp）
  embedding vector(1024) NULL,   -- pgvector；null=尚未嵌入（背景補算）
  updated_at timestamptz,
  UNIQUE(doc_type, ref_id)
)
-- 索引：GIN (content_norm gin_trgm_ops)；ivfflat/hnsw (embedding)
```

寫入路徑：service 層在來源實體 save/publish 時同步 upsert 投影（同交易）；embedding 由背景工作補算（`embedding IS NULL` 掃描），**檢索功能不因 embedding 服務不在而失效**。

### 4.2 為什麼這樣設計（取捨）

- **不選 zhparser/PGroonga**：要自編 PG extension、維運重；工廠詞彙封閉，trgm+同義詞層已覆蓋文字檢索需求，語意缺口由 pgvector 補。
- **pgvector 現在就進 schema、embedding 服務延後**：User 明確要為 LLM+VLM 預留——`vector` 欄與 port 先就位（成本＝換 `pgvector/pgvector:pg16` image + 一次 migration），模型服務何時上線不影響 schema。這正是 wi-parser-upgrade Stage 2（BGE-M3 hybrid 檢索）的落地位，未來 VLM（影片動作→工序建議）產生的文本也走同一投影表。
- **確定層永遠在最前**：工時系統的檢索首先要「對」再要「聰明」；精確命中不給語意層洗牌的機會。
- 部署影響（[[deploy]]）：docker image 換 pgvector 版、`CREATE EXTENSION pg_trgm, vector` 進 migration、embedding 服務為選配容器——寫入 ADR-016。

---

## 5. 組件庫：WI Pool 的結構優化（User：核心邏輯、以相同概念優化）→ ADR-017

### 5.1 v3 的使用邏輯（保留的心智模型）

IE 的工作流：**做好一句 MI（多個 GM/CM 序列組成）→ 存進個人/共用庫 → 下次組工序表時關鍵字搜庫 → 挑選加入 → 系統快照、可再微調，總 TMU 自動重算**。v3 用三表（MiStatement / StatementSequence / StatementItem）實現，關鍵設計是「**加入時複製快照、留來源 provenance、改快照不回寫原件**」。

> **🔍 程式碼查證補充（2026-07-05，見 [verification-code-audit.md](verification-code-audit.md) §2.1）**：v3 另有**新一代三層系統**與上述舊一代並存——L1 Action Modules（動作模組池）→ L2 WI Templates（WI 範本池）→ L3 Process Routes（製程途程），且有顯式 **apply-back**（流程實例回寫來源範本，owner 限定）。對應關係：本節的 `motion_modules`（rows 1..n）天然覆蓋 L1＋L2；L3 ≈ 既有 ProcessVersion＋worksheet；apply-back ≈「從工序表列發布組件新版本」（impl-04 §3）。兩代並存＋四處計算路徑（audit §2.2）進一步佐證本合併決策。

### 5.2 類似案例（結構的業界原型）

| 案例 | 對應概念 |
|---|---|
| 套件庫 registry（npm/PyPI）| 發布不可變版本；使用端固定版本＋vendor 複製 → 我們的「模組版本 + 快照引用」 |
| CAD block / BOM phantom assembly | 可重用子組件插入圖面時實體化複製、保留庫連結 → 「加入工序表＝實體化列」 |
| CMS 元件庫（duplicated block vs synced block）| v3 選了 duplicate（快照）而非 sync（連動）——**工時文件必須快照**，否則改庫會追溯改歷史工時 |
| v2 自己的 rule-set 快照 | 同一哲學：使用當下的版本凍結、可回放 |

v3 的直覺與這些原型一致，結構上的問題只有一個：**它和 v2 的 motion_templates 是重疊概念**（單 cycle 範本 vs 多 cycle 語句庫）。依「單一真相」原則合併成一個庫。

### 5.3 提案：`motion_modules`（統一組件庫）

```
motion_modules                      ← 庫主檔（可搜尋的「東西」）
  id, site_id NULL=全域, name_zh, category, keywords text[],
  scope CHECK IN ('personal','site','global'),   ← v3 個人庫 + v2 廠標準 統一
  owner, status CHECK IN ('draft','standard','retired'),
  current_version int
motion_module_versions              ← 不可變發布版本（registry 模式）
  id, module_id FK, version_no int, rule_set_id FK(快照),
  rows jsonb NOT NULL,              ← 有序 CycleIn[]（1 列=單 cycle 範本；n 列=MI 語句）
  narrative_zh text, total_tmu numeric, total_seconds numeric,
  published_by, published_at
  UNIQUE(module_id, version_no)
wi_rows（既有表加欄）
  + source_module_id uuid NULL      ← provenance：從哪個模組實體化
  + source_module_version int NULL
```

- **單 cycle 範本＝rows 長度 1 的 module**：現有 `motion_templates` 以 migration 轉入，舊表退役（分步：先雙寫後切換，ADR-011 加法優先）。
- **加入工序表＝實體化**：把 version 的 rows 複製成 WiRow+MostCycle（快照），寫 provenance 兩欄；之後編輯互不影響——與 v3 StatementItem 語意等價，但落在 v2 既有的 WiRow 穩定 id / LevelEntry 體系上，**Level 標註、LB 輸出、匯出合約全部免改**。
- **總 TMU 重算**：實體化後就是普通 worksheet 列，走既有 `compute_table`（含 SIMO 引擎 max）——不需要 v3 的 `_recalculate_project_totals` 平行邏輯。
- **檢索**：module 的 name/keywords/narrative 投影進 `search_documents`（§4），WI Pool 搜尋= `doc_type='motion_module'` 的混合檢索。
- v3 的 WISetProject ≈ v2 的 ProcessVersion+Worksheet（已存在），不另建表；「組裝」是前端工作流：搜庫 → 多選 → 批次實體化 → 排序（既有 seq_no）。

### 5.4 治理

`scope=personal` 免審核；升 `site/global`（=standard）走 §8 審核流。IE 在 v3 的「個人序列庫」習慣保留，又獲得 v2 的廠級標準化治理。

---

## 6. NL 解析與同義詞（→ ADR-015）

### 6.1 新套件 `src/ddm_v2/nlp/`（引擎保持純淨，解析屬建議層）

```
src/ddm_v2/nlp/
  normalization.py      ← NFKC + OpenCC 繁簡 + 空白/大小寫（v3 邏輯移植，加測試）
  ports.py              ← DraftParserPort（輸入原文 → NLDraftResult：slot 候選+信心+provenance）
  rule_based.py         ← 第一版 adapter：字典驅動最長匹配（修 v3 五缺陷，見 6.3）
  （future: retrieval.py ← Stage 2 BGE-M3 adapter，接 §4 檢索層）
api: POST /api/v2/worksheets/nl-draft   ← 回「建議」，永不直接寫工時；採用與否由 IE 在 UI 確認
```

**原則**：NL 解析輸出是**建議（draft suggestion）**，經 IE 確認後才變成 `slot_inputs`；工時的真相永遠來自引擎算 slot_inputs，AI 層錯了最多是建議差，不污染工時——這是 ADR-015 的核心邊界。

### 6.2 同義詞儲存方案（回覆 User「除了 v3 JSONB 還有什麼解法」）

| 方案 | 做法 | 優點 | 缺點 | 判定 |
|---|---|---|---|---|
| S1 v3 現況 | `synonyms_json` TEXT 掛選項列 | 最簡單 | 歧義無防線、無法稽核單筆、查詢靠載入全部 | 不採 |
| S2 **獨立表＋唯一約束** | `rule_option_synonyms(rule_set_id, parameter, option_code, synonym_raw, synonym_norm)`；`UNIQUE(rule_set_id, synonym_norm)` | **DB 層直接擋「一詞映兩選項」**；可稽核、可單筆 CRUD、匯入衝突顯式報錯；符合 database-v2「要被約束的→升表」 | 合法的一詞多義（例「對準」既是 P 修飾也是 I 選項）會被擋 | **採，為基底** |
| S3 顯式歧義建模 | 同 S2 但唯一約束放寬為 `UNIQUE(rule_set_id, parameter, synonym_norm)`（**同參數內唯一、跨參數允許**）＋`priority` 欄 | 保留跨參數合法多義（對準/卡合本來就跨 P/I），參數內仍零歧義；解析器對跨參數命中回多候選 | 稍複雜 | **採，S2 的收斂形** |
| S4 純語意無同義詞 | 不維護同義詞，選項文字直接 embedding，向量相似度匹配 | 零維護 | 非確定性、閾值難調、無法保證工時輸入正確性 | 不單獨採 |
| S5 **混合（最終形）** | S3 確定層 → 未命中才落 §4 L3 語意層 → 低信心進審核佇列（top-K 供 IE 一鍵選） | 確定性優先、語意兜底、人審收口；即 wi-parser-upgrade Stage 2/3 的落地 | 需要 §4 基建 | **目標架構** |

**結論**：Phase 1 落 **S3**（migration 新表 + 匯入器帶入 v3 `synonyms_json`，衝突報告給 IE 清洗），基建到位後升級 **S5**。同義詞表同時服務：NL 解析（最長匹配詞典）、workbench 選項搜尋、`search_documents` 的 content 擴充。

### 6.3 rule_based adapter 必修的 v3 五缺陷（重寫不照搬的原因）

1. 全 slot 改**正規化後最長匹配**（v3 只有 M 有）；2. 詞表由 S3 表生成（消滅 G_SELECT 遮蔽 bug 這類排序依賴）；3. 進 parser 前先過 `normalization.py`；4. context 抽取改角色標註式規則（不用黑名單 regex）；5. 信心分數重定義（default 必須低於 inferred，修反置 bug），低信心欄位在 UI 標示待確認。

---

## 7. 字典/規則匯入器

- `services/v2/rule_set_import_service.py`：Excel（`MiniMOST_rag.xlsx` 格式）→ **draft rule-set**（含全部子表＋同義詞）→ 驗證報告（衝突/缺漏/與現版差異 diff）→ IE 確認 → publish（凍結）。
- 一次性 converter：`scripts/import_v3_dictionary.py` 讀 `minimost_ai_dictionary_v1.json` 產 `MINIMOST_FACTORY_V2` seed——**V2 rule-set 的出生就是程式轉換而非手抄**。
- 對應 v3 的 `dictionary_import.py` + `dictionaries.py` CRUD；v2 版差異：CRUD 僅限 draft 版本（published 不可變），同義詞除外（可對 published 版本增補，因為它不影響已算工時，只影響建議層——寫進 ADR-014 邊界）。

## 8. 審核工作流與 RBAC（→ ADR-018，與 [[rbac-hard-requirement]] 合併設計）

- ProcessVersion 狀態機擴充：`draft → submitted → reviewed → approved(=published) → retired`，`changes_requested → draft` 回繞；audit log 表記錄每次遷移（who/when/from/to/comment）。
- 角色收斂提案：LB 共享登入的身份 → v2 角色映射 `IE(=analyst)、IE-lead(=reviewer)、manager(=approver)、admin、viewer`；閘道 ForwardAuth 提供身份、v2 存角色。細節在 ADR-018 展開，**不在本文件定案**（涉及 LB 端）。

---

## 9. 實施順序（每 phase 出 migration＋測試，符合 [[testing-ci-hard-rules]]）

| Phase | 內容 | Migration | 主要風險 |
|---|---|---|---|
| **P0 決策落地** | ADR-014~018、core-logic spec 改版、黃金目錄重錨（先紅後綠）、ie-most-engineer skill 更新 | — | 規格債：不先做，後面每步都會被舊防線擋 |
| **P1 值層＋引擎** | `MINIMOST_FACTORY_V2` seed（converter 產）、新表 `rule_m_foot_bands`、加欄（display_rule/vision_scope/sentence_text_zh）、引擎 E1–E8、worksheet `allowance_percent` | v2_0008, v2_0009 | CM 黃金重錨要逐案過帳 |
| **P2 檢索基建** | pgvector image、`pg_trgm`+`vector` extension、`search_documents`、EmbeddingProvider port（null adapter）、WI 檢索 API | v2_0010 | 部署 image 變更需走 [[deploy]] checklist |
| **P3 組件庫** | `motion_modules`/`motion_module_versions`、WiRow provenance 欄、motion_templates 轉移、實體化 API、前端 WI Pool 工作流 | v2_0011 | 舊範本轉移的資料遷移 |
| **P4 NL 解析** | `nlp/` 套件、`rule_option_synonyms`（S3）、nl-draft API、workbench 建議 UI | v2_0012 | 無工時風險（建議層隔離） |
| **P5 工作流** | 狀態機擴充、audit log、角色映射 | v2_0013 | 依賴 LB 認證整合時程 |

**每個 phase 的完成定義**：migration 可逆（downgrade 實測）、endpoint 測試齊、`validate-core-logic` 綠、CI_GATES 更新。

## 10. 待 IE 確認殘項（整合中追蹤，不阻塞 P0/P2）

1. M 距離動詞 `>75cm → 42` 檔存廢（v2 有、v3 動詞無、v3 腳步有）。
2. 旋轉 `>50cm` 與大直徑 3 圈檔。
3. `allowance_percent`（工序表級寬放）與 LevelEntry `coefficient`（列級難度）的命名與預設值。
4. slot `repeat_count` 上限（是否封頂，如 ≤99）。
5. 同義詞跨參數多義白名單（S3 匯入衝突報告出來後逐筆裁決）。
