# impl-03：檢索基礎設施 — pg_trgm + pgvector 混合、search_documents 投影、EmbeddingProvider port

> **Phase**：P2 ｜ **ADR**：ADR-016 ｜ **User 裁決**：走 pgvector/語意方向，為 LLM+VLM 預留。
> **設計原則**：確定層永遠優先於語意層；embedding 服務缺席時系統功能完整（優雅降級）；hexagonal port-adapter。

## 1. 三層檢索模型

| 層 | 機制 | 何時命中 | 特性 |
|---|---|---|---|
| L1 確定層 | 同義詞/代碼精確匹配（`rule_option_synonyms` 正規化最長匹配，見 impl-05） | 詞完全對應 | 零模糊、可測試、命中即回 |
| L2 文字層 | `pg_trgm` GIN + ILIKE/similarity | 子字串/近似字 | 中文 trigram 免斷詞 extension |
| L3 語意層 | `pgvector` KNN（cosine） | 語意相近、跨說法 | 需 embedding；與 L2 做 RRF 融合 |

融合：`RRF(k=60)`，L2/L3 各取 top-20 融合後回 top-N；L1 命中則直接置頂且標 `match_type=exact`。

## 2. Schema（migration `v2_0011_search_infrastructure`）

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE search_documents (
  id uuid PRIMARY KEY,
  doc_type text NOT NULL CHECK (doc_type IN ('motion_module','wi_row','vocab','worksheet')),
  ref_id uuid NOT NULL,
  rule_set_id uuid NULL REFERENCES rule_sets(id),
  content_norm text NOT NULL,          -- normalization.normalize() 後全文
  embedding vector(1024) NULL,         -- NULL = 待補算
  embedding_model text NULL,           -- 模型指紋（換模型須重嵌）
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (doc_type, ref_id)
);
CREATE INDEX ix_searchdoc_trgm ON search_documents USING gin (content_norm gin_trgm_ops);
CREATE INDEX ix_searchdoc_vec  ON search_documents USING hnsw (embedding vector_cosine_ops);
```

- `downgrade()`：drop table 與索引；**extension 不 drop**（可能他表使用，註記於 migration docstring）。
- 維度 1024 = BGE-M3 dense 維度；換模型維度不同 → 新 migration（ADR-016 記載）。

## 3. EmbeddingProvider port（`most_engine` 之外，`src/ddm_v2/search/`）

```python
# src/ddm_v2/search/ports.py
class EmbeddingProvider(Protocol):
    model_id: str
    async def embed(self, texts: list[str]) -> list[list[float]] | None: ...
        # None = 服務不可用（呼叫端必須容忍，不得拋出中斷業務流）

# adapters（src/ddm_v2/search/adapters/）
# null_provider.py     → 永遠回 None（預設；未配置時）
# bge_m3_http.py       → 地端 BGE-M3 服務（EMBEDDING_URL 環境變數）
# （future）api_provider.py → 雲端 embedding API
```

選配環境變數：`EMBEDDING_PROVIDER=null|bge_m3_http`、`EMBEDDING_URL`。預設 `null`。

## 4. 投影寫入路徑（單一真相：來源表；投影可重建）

- **同交易 upsert**：`worksheet_service`/`motion_module_service`/`vocab` 的 save/publish 內，組 `content_norm`（名稱＋敘事＋關鍵字，經 `nlp.normalization`）upsert 進 `search_documents`（`embedding` 置 NULL）。
- **背景補嵌**：`scripts/backfill_embeddings.py`（可 cron）：撈 `embedding IS NULL OR embedding_model != current` 批次呼叫 provider；provider 回 None → 跳過留待下次。
- **全量重建**：`scripts/rebuild_search_index.py`——投影表可任意 truncate 重建（災難恢復與 normalize 規則升版時用）。

## 5. Search service 與 API

```
src/ddm_v2/search/service.py
  async def search(q, doc_types, rule_set_id=None, limit=10) -> list[SearchHit]
  # SearchHit: {doc_type, ref_id, score, match_type: exact|text|semantic|fused, snippet}

GET /api/v2/search?q=...&types=motion_module,wi_row&limit=10
```

- q 先過 normalization → L1（僅 vocab/option 類）→ L2 → L3（embedding 可用時）→ RRF。
- L3 查詢向量：即時呼叫 provider；不可用 → 純 L2（回應標 `semantic: false`，前端可提示）。
- RBAC：沿用既有 API guard；搜尋結果過濾呼叫者可見範圍（personal scope 只回本人）。

## 6. 部署（[[deploy]] checklist 項）

| 項 | 變更 |
|---|---|
| Postgres image | `postgres:16` → `pgvector/pgvector:pg16`（compose 兩檔同步）；既有 volume 相容（同 PG 大版本） |
| entrypoint | 不變（extension 由 migration 建） |
| 選配服務 | `embedding`（BGE-M3, TEI/infinity image）compose profile `--profile semantic`；不啟用時系統照常 |
| 上線前 | migration 可逆實測、`rebuild_search_index` 演練、無 embedding 服務的降級路徑 e2e |

## 7. 測試

1. 單元：RRF 融合、normalize→L1/L2 命中矩陣、null provider 降級。
2. 整合（真 DB）：trgm 中文子字串命中（「壓合」命中「並壓合機台」）、UNIQUE(doc_type,ref_id) upsert、投影與來源同交易一致性。
3. Endpoint：`GET /api/v2/search` 正常/空查詢/未授權/types 過濾。
4. 選配（有 embedding 服務的 CI job）：語意命中冒煙（「黏膠」→「點膠」類）。

## 8. 與未來 LLM+VLM 的接點（不在 P2 實作，僅預留）

- VLM（影片→動作草稿）產出的文本描述 → 同一 `search_documents`（新 doc_type 走 CHECK 擴充，加法 migration）。
- NL 解析 Stage 2（impl-05 目標形 S5）直接以本層做選項連結檢索。
- RAG：`content_norm` + 來源表即是語料面；不另建平行儲存。
