# ADR-016: 檢索架構 — pg_trgm + pgvector 混合、EmbeddingProvider port

**狀態：** proposed
**日期：** 2026-07-04
**關聯：** [../v3/impl/impl-03-search-infrastructure.md](../v3/impl/impl-03-search-infrastructure.md)、ADR-015、ADR-017、[[deploy]]

## 脈絡

v3 的 WI Pool 關鍵字查詢為純 `ILIKE '%kw%'`（無索引、中文無斷詞）。User 裁決檢索要走 pgvector/語意方向，為未來 LLM+VLM 接入預留架構。引入 DB extension 與選配外部服務屬「引入外部依賴」，須 ADR。

## 決策

三層檢索：L1 同義詞精確匹配 → L2 `pg_trgm` 文字層 → L3 `pgvector` 語意層（RRF 融合）；所有可搜尋實體投影進單一 `search_documents` 表；embedding 經 `EmbeddingProvider` port（null / BGE-M3 地端 / API 三 adapter），**服務缺席時降級至 L1+L2，功能完整**。

## 考慮過的選項

- **A. 維持純 ILIKE** — 無索引、無語意、與 User 的 LLM+VLM 前瞻方向不符；否決。
- **B. 中文全文檢索 extension（zhparser/PGroonga）** — 斷詞最好，但需自建 PG image、維運重；工廠詞彙封閉，trgm＋同義詞層已覆蓋文字需求；否決。
- **C. 外部搜尋引擎（Elasticsearch/Meilisearch）** — 新增有狀態服務、與單一真相原則衝突（雙儲存）；否決。
- **D. trgm＋pgvector in-Postgres 混合（選定）** — schema 與 port 先就位、模型服務後到；投影表可任意重建（來源表是真相）；一套基建同時服務 WI 檢索、NL Stage 2、未來 RAG/VLM 文本。

## 後果

- 好處：LLM+VLM 接點就緒（新 doc_type 加法擴充）；確定層優先保「先對再聰明」。
- 代價：Postgres image 換 `pgvector/pgvector:pg16`（compose 兩檔、上線 checklist）；hnsw 索引維護成本；換 embedding 模型須重嵌（`embedding_model` 指紋管理）。
- 邊界：投影 upsert 與來源寫入同交易；embedding 補算為背景任務，任何失敗不阻斷業務流。
