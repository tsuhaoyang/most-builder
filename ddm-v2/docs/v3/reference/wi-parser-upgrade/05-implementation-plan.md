# 05 · 分階段實作計畫（施工單）

> 給實作者（含下一個 agent）的逐步施工單。**每個 Phase 可獨立上線、可量測、可回退**。
> 鐵則：**未達該 Phase 驗收門檻（對 gold set 跑分），不得進入下一個 Phase。** 量測方法見 [06](06-evaluation-and-audit.md)。

## 專案座標與通用指令

```bash
# 後端（Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic v2）
cd apps/api && python3 -m alembic upgrade head && PYTHONPATH=. python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
cd apps/api && PYTHONPATH=. pytest                     # 後端測試（tests/ 已有 conftest.py）
# 前端（Vue 3 + Vite + Element Plus）
cd apps/web && npx vitest run                          # 前端測試
cd apps/web && npx vite build                          # 前端建置
# 全端
npm run dev
```

> **先確認 DB 種類**（看 [db/session.py](../../apps/api/app/db/session.py)）：
> Postgres → 用 **pgvector**；SQLite/其它 → 用本地 **FAISS / numpy 暴力索引**（候選池小，暴力完全夠）。此判斷影響 Phase 1。

---

## Phase 0 · 古典強化（M0）— 立即止血 ＋ 建立量測

**目標**：修掉現有 bug、加正規化與模糊比對；**建立 gold set 與評測腳本**（之後每個 Phase 的守門員）。零 ML 基礎設施。

**新增依賴**：`opencc-python-reimplemented`、`jieba`、`rapidfuzz`、`pypinyin`、`lingua-language-detector`

**步驟**
1. **建立評測骨架（先做！）**
   - `apps/api/tests/nl_gold/gold.jsonl`：先放 30–50 句（涵蓋 [01 §1.3](01-problem-and-requirements.md) 每個挑戰維度，至少繁簡/全形/錯字/亂序/中英各數句）。格式見 [06 §6.2](06-evaluation-and-audit.md)。
   - `apps/api/scripts/eval_nl_parser.py`：讀 gold、跑 parser、輸出 per-slot accuracy / sentence exact-match（見 [06 §6.4](06-evaluation-and-audit.md)）。
   - **先對「現況 parser」跑一次當 baseline 數字**，寫進 [README 狀態看板](README.md)。
2. **正規化** `app/services/nl_parser/normalize.py`：NFKC + OpenCC(s2t) + 英文小寫 + 空白，回傳 `text` 與 `offset_map`。在 `RuleBasedDraftParser.parse()` 入口先呼叫。
3. **最長匹配 + 評分**：把 `_parse_g/_parse_p/_match_x/_match_i/_parse_b` 的「first-win」改成「**收集所有命中 → 依(匹配長度→DB優先→列表序)排序取最佳**」。抽成共用 `match_slot(text, synonyms)`。（現況只有 `_parse_m` 有最長匹配，其餘皆無——見 [08 §8.9 D1/D2](08-current-system-reference.md)。）
4. **修遮蔽 bug**：驗證 `拿取小元件 → G_SELECT_SMALL`（不再被 `G_SELECT` 吃掉）。把 `G_SYNONYMS` 等表的長詞排前，或靠步驟 3 的最長匹配自動解決。
5. **模糊 fallback**：精確/最長匹配 miss 時 → `rapidfuzz`(token 級, bigram) + `pypinyin`(同音) 比對同義詞表；命中標 `badge="AI 近似比對，請確認"`、降信心；低於門檻→不猜。
6. **jieba userdict**：開機時用詞典 `display_text_zh + synonyms_json` 建 userdict，比對前先斷詞。
7. **修信心語意（為 Phase 3 鋪路）**：把 `source="default"` 的 `confidence` 從 1.0 改成**低值**並維持「待確認」徽章，解除現況的信心反置（[08 §8.8](08-current-system-reference.md)）。此步不改 TMU、不改判定，只改 confidence 數值語意。
8. **預設值改走詞典**：`_apply_b_defaults` 的 B1/B2 硬編 `tmu=42/10` 改為 `_lookup_b_option` 查詢，避免與詞典不一致（[08 §8.9 D6](08-current-system-reference.md)）。

**驗收**：gold set per-slot accuracy **不低於 baseline**；`拿取小`、`检查`(簡)、`２０cm`(全形)、`對淮`(錯字) 四類測試**由紅轉綠**；預設值 confidence 不再高於 inferred。
**回退**：純程式改動，`git revert` 即可。

---

## Phase 1 · 檢索 grounding（M1）— 候選生成

**目標**：把 MiniMOST 詞典向量化，提供「每 slot top-K 候選」，為 Stage 2 linking 打底。**先不換抽取引擎**，先讓「片段→option_code」變語意化。

**新增依賴**：`FlagEmbedding`（BGE-M3）或 `sentence-transformers`；Postgres 則加 `pgvector` + alembic migration，否則 `faiss-cpu`。

**步驟**
1. `app/services/nl_parser/base.py`(介面 `DraftEngine`)、`types.py`(契約，見 [04 §4.3](04-architecture-design.md))。
2. `index.py`：對每個 active 詞典版本，將各 slot option 的 `sentence_text_zh+display_text_zh+synonyms` 編碼成 BGE-M3 dense(+sparse)，**按 slot 分庫**儲存；記錄 `dictionary_version_id`。（JSON 路徑與「P 分 base/modifier 兩池、M 在 `controls.verb`」見 [08 §8.5](08-current-system-reference.md)。）
3. `engines/retrieval.py` `RetrievalLinker.link(span, slot) -> list[SlotCandidate]`：hybrid 檢索取 top-K。
4. `scripts/reindex_nl.py` 指令；在 dictionary publish 流程（[dictionaries.py 既有 `invalidate_synonym_cache` 處](../../apps/api/app/api/routes/dictionaries.py)）旁觸發 reindex。
5. 暫時把 RetrievalLinker 接在 Phase 0 比對之後當「第二意見」，記錄但先不改判定。

**驗收**：對 gold set 的每個動作 span，**正解 option_code 落在 top-5 的比例 recall@5 ≥ 0.95**（逐 slot）。
**回退**：feature flag `NL_USE_RETRIEVAL=false` 直接停用，回到 Phase 0。

---

## Phase 2 · Stage 1 抽取（M3 GLiNER 或 M4 LLM）— 解語序/語言

**目標**：用抽取引擎把句子拆成「帶角色 span」，取代脆弱的 regex context 抽取，並支援亂序/中英/一句多動作。

**新增依賴**：Profile B → `gliner`；Profile A → `openai`（雲端）或 `outlines`+`vllm`（地端）。

**步驟（Profile B 優先）**
1. `engines/gliner.py` `GLiNEREngine`：用 [04 §4.5](04-architecture-design.md) 的 label set 抽 span → `list[Span]`（含 raw offset）。
2. `segment.py`：以 grasp/move/place/process 動詞為錨點，把一句多動作切成多筆。
3. `orchestrator.py`：Stage0 → Stage1(引擎) → Stage2(數值/sequence 判定 + RetrievalLinker) → 暫用簡單規則組裝；輸出 `NLDraftResultV2`。
4. `engines/llm.py`（可後做或 Profile A 主用）：constrained decoding（Outlines/OpenAI Structured Outputs），enum=合法 option_code，few-shot 帶亂序/中英範例，`temp=0`+鎖版本+快取。
5. RuleEngine 仍跑，作為**投票者**（供 Stage 3 一致性比較）。

**驗收**：在**跨語言＋亂序專屬測試集**上，Stage 1 角色 span 的 **slot F1 ≥ 0.90**；「一句多動作」能正確切成多筆。
**回退**：`NL_STAGE1_ENGINE=rule` 切回規則抽取。

---

## Phase 3 · Reranker ＋ 信心校準 ＋ 審核分流 — 核心價值

**目標**：把 Stage 2 收斂到高精度，並產出**可信的信心**驅動分流；落實「自動採用 / 送審 / 棄權」與 provenance、審核佇列。**這是同時實現「最準」與「最省審核」的 Phase。**

**新增依賴**：reranker（`FlagEmbedding` 的 bge-reranker-v2-m3 或 `sentence-transformers` CrossEncoder）、`scikit-learn`（isotonic 校準）。

**步驟**
1. `engines/retrieval.py` 加 reranker 精排 top-K。
2. `confidence.py`：
   - `calibrate()`：在 gold set 的 calibration split 上 fit isotonic（原始分→機率）。
   - `slot_confidence()`：融合 校準機率 + margin + 多引擎一致性（[04 §4.7.1](04-architecture-design.md)）。
3. `routing.py`：依 `TAU_AUTO/TAU_ABSTAIN` 分流；關鍵 slot(G/P/M/X/I) 任一 review/abstain → 整筆 `needs_review`。
4. **Provenance + 佇列**：alembic 新增 `nl_draft_log`（存 [04 §4.8](04-architecture-design.md) 結構 + 修正欄）；route 寫入。
5. **路由相容**：`to_legacy()` 轉舊格式；[`/nl-draft`](../../apps/api/app/api/routes/most.py) 新增 `top_k / needs_review / provenance` 欄位（**舊前端不壞**）。
6. **前端增強** [NlDraftInput.vue](../../apps/web/src/pages/most-workbench/NlDraftInput.vue)：`needs_review` 的 slot 顯示 top-K chip 一鍵替換 + highlight 來源片段（用 offset map）。
7. **門檻設定化**：`TAU_AUTO/TAU_ABSTAIN` 進 config，並寫入 provenance。

**驗收**：在「自動採用」段 **precision ≥ 0.98**，且 **coverage ≥ 0.70**（risk–coverage 曲線見 [06 §6.5](06-evaluation-and-audit.md)）；每筆審核 time-to-audit < 10s（一鍵候選）。
**回退**：`NL_USE_RERANKER=false` 退 dense-only；分流門檻設 0 → 全自動（等同關閉審核）。

---

## Phase 4 · Active Learning 回流 ＋ 審核 UI 強化 — 讓審核率隨時間下降

**目標**：把人工修正變養分，逐步降低審核率，並逼近 Profile A 精度。

**步驟**
1. 審核修正 → 寫 `nl_draft_log.correction`；批次工具把 (片段→option_code) **回灌 DB `synonyms_json`** 並觸發 reindex。
2. 難句+正解 → 累積 **few-shot 範例庫**（給 LLM）與 **gold set 擴充**。
3. 排程：累積足量標註後**微調 GLiNER / reranker**（幾分鐘級），版本號進 provenance。
4. 儀表板：審核率、coverage@precision、各 slot 錯誤熱點（見 [06 §6.6](06-evaluation-and-audit.md)）。
5. （可選）Profile A 上線：把 Stage 1 主引擎切 LLM，B 當 fallback。

**驗收**：連續數個資料週期，**audit rate 單調下降**；修正能一鍵回灌且下次同類句自動正確。
**回退**：回流是純資料新增；可凍結 few-shot/索引版本。

---

## 依賴與 feature flag 總表

| Phase | 套件 | flag（config） |
|-------|------|----------------|
| 0 | opencc, jieba, rapidfuzz, pypinyin, lingua | `NL_NORMALIZE`, `NL_FUZZY` |
| 1 | FlagEmbedding/sentence-transformers, pgvector/faiss | `NL_USE_RETRIEVAL` |
| 2 | gliner（B）/ openai/outlines+vllm（A） | `NL_STAGE1_ENGINE=rule\|gliner\|llm` |
| 3 | reranker, scikit-learn | `NL_USE_RERANKER`, `TAU_AUTO`, `TAU_ABSTAIN` |
| 4 | （訓練）transformers | `NL_PROFILE=A\|B` |

> **每個 flag 預設 off**，逐 Phase 開啟；任何 Phase 出事都能單獨關掉退回上一層（NFR5）。

---

下一篇 [06-evaluation-and-audit.md](06-evaluation-and-audit.md)：gold set 怎麼建、指標怎麼算、校準與門檻怎麼設、審核 UI 與 active learning 的細節。
