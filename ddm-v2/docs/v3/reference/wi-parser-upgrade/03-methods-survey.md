# 03 · 方法調查、優劣比較與決策矩陣

> 用 [02 的積木](02-concepts-primer.md) 逐一檢視 6 大類做法。每類都標明：**它負責管線的哪一段、強在哪、弱在哪、SOTA 工具、成本/部署/確定性**。
> 最後給決策矩陣與推薦。先記住一句話：**沒有單一方法全贏；正解是分階段混合。**

---

## 3.0 先分清楚「管線的兩個子問題」

任何方法都在解這兩件事之一（或兩者）：

- **子問題 A — 抽取/拆解（Extraction）**：把自由文字拆成「帶角色的片段」（處理語序、語言、口語）。
- **子問題 B — 對應/連結（Linking）**：把片段對到封閉的 `option_code`（處理同義、錯字、跨語言詞彙）。

> 數值（距離→區間）與 sequence model 判定是**確定性規則**，不該丟給模型。把這部分先切出來，模型只處理真正需要泛化的地方。

---

## 3.1 M0 — 強化規則式 ＋ 古典模糊比對

**做什麼**：正規化（NFKC/OpenCC）→ 斷詞（jieba+userdict）→ 最長匹配 + rapidfuzz + pinyin。主要解**子問題 B 的字面層**，並修掉現況 bug。

| 優點 | 缺點 |
|------|------|
| 完全確定性、可離線、毫秒級 | 不懂語意同義（`扣上`≠`卡合` 字面） |
| 零 ML 基礎設施，立刻可上 | 跨語言能力弱（英文要另建表） |
| 可解釋性最佳，稽核友善 | 語序/口語仍靠脆弱規則 |
| 立即修掉「遮蔽 bug、繁簡、全形」 | 同義詞仍需人工維護 |

**SOTA 工具**：`opencc`、`jieba`/`pkuseg`、`rapidfuzz`、`pypinyin`、`lingua`(語言偵測)。
**定位**：**所有方案的 Phase 0 地基**，也是其他引擎失效時的**確定性 fallback**。

---

## 3.2 M1 — 稠密／混合檢索（每 slot 候選生成）

**做什麼**：把詞典每個 option 的 `sentence_text_zh`（+ 同義詞）預先 embedding；查詢片段做 hybrid（dense+BM25）檢索取 top-K。解**子問題 B 的語意層**，且**天生跨語言**。

| 優點 | 缺點 |
|------|------|
| 懂語意同義（扣上≈卡合≈snap fit） | 永遠回最近鄰 → 需門檻＋reranker |
| 多語模型直接跨中英 | 對極短專名（DIMM/PPID）dense 較弱 → 靠 sparse 補 |
| 詞典更新只需重建索引，免改碼 | 單靠檢索精度不夠，需重排 |
| 可完全地端（BGE-M3, MIT） | 需要向量索引基礎設施 |

**SOTA 工具**：**BGE-M3**（一模型同時 dense+sparse+ColBERT，100+ 語言，MIT，8192 token，官方建議 hybrid+rerank）；**Qwen3-Embedding-0.6B/4B/8B**（MTEB 多語榜 2025 第一梯隊，Apache-2.0，支援自訂維度）；multilingual-e5。向量庫：`pgvector`（你已用 Postgres，最省事）、Milvus、Qdrant。
**定位**：**Stage 2 候選生成**。

---

## 3.3 M2 — 檢索 ＋ Cross-encoder 重排

**做什麼**：在 M1 的 top-K 上加 reranker 做精排。解**子問題 B 的精確層**。

| 優點 | 缺點 |
|------|------|
| 精度顯著高於純 bi-encoder | 比 bi-encoder 慢（只排 K 個可接受） |
| 兩段式（召回→精排）是業界標準配方 | 多一個模型要部署 |
| 分數適合拿去校準 → 服務審核分流 | 仍不懂「一句多動作」的拆解（那是子問題 A） |

**SOTA 工具**：**bge-reranker-v2-m3**、**Qwen3-Reranker-0.6B/4B**、Cohere Rerank（雲端）。
**定位**：**Stage 2 精排 + 信心來源**。

---

## 3.4 M3 — 零樣本／微調 NER（GLiNER / GLiNER2）

**做什麼**：給定角色 label（hand/from_location/grasp_verb/…），抽出帶角色的 span。**直接解子問題 A**，且**語序/語言無關**。

| 優點 | 缺點 |
|------|------|
| **零樣本起步**，多語（100+），CPU 可跑，Apache-2.0 | 零樣本對「領域動詞」可能要微調才穩 |
| 語序顛倒、中英混雜都能抽 | 只抽 span，仍需 M1/M2 做 linking |
| 幾分鐘可微調，輕量好部署 | 邊界切割偶有誤差，需後處理 |
| 確定性比 LLM 高（無自由生成） | 「一句多動作」分段需額外邏輯 |

**SOTA 工具**：**GLiNER**（`gliner-community/gliner_*-v2.5`、`gliner-multi`）、**GLiNER2**（schema 驅動多任務 IE，2025）、GLinker（entity linking）。
**定位**：**Stage 1 抽取**的**地端首選**（Profile B 主力）。

---

## 3.5 M4 — LLM 結構化抽取（Constrained Decoding）

**做什麼**：用 LLM 一次完成「拆解 + 角色標註 + slot 對應 + sequence model 判定」，並用 schema/enum + constrained decoding 保證輸出合法且 `option_code` 不越界。**同時解 A+B**，泛化最強。

| 優點 | 缺點 |
|------|------|
| 對「任何奇怪句子/語言/語序/口語」泛化天花板最高 | 成本/延遲較高 |
| 一句多動作、隱含資訊推理最強 | 雲端有資料落地疑慮（NFR3） |
| constrained decoding 保證格式合法 | 「格式合法 ≠ 語意正確」，仍需校準＋審核 |
| few-shot 可快速注入領域知識 | 確定性需靠 `temp=0`＋鎖版本＋快取維持 |

**SOTA 工具**：**OpenAI Structured Outputs**（`response_format` json_schema, strict）、**Outlines**（保證合法結構，支援 vLLM/Ollama/llama.cpp/transformers，Apache-2.0）、vLLM guided decoding、xgrammar。地端模型：Qwen2.5/3-Instruct、Llama-3.x，用 vLLM 或 llama.cpp 跑。
**定位**：**Stage 1（＋部分 Stage 2）**的**精度天花板**（Profile A 主力）；或 Profile B 中**只處理殘留難句**的「重砲」。

---

## 3.6 M5 — 自訓任務模型（token classification / seq2seq）

**做什麼**：用你累積的標註資料，微調一個專用 slot-filling 或 seq2seq 模型。

| 優點 | 缺點 |
|------|------|
| 在地資料夠多時精度與延遲俱佳 | **需要大量標註資料**（冷啟動痛） |
| 完全可地端、可控 | 訓練/維運 MLOps 成本 |
| 推論便宜 | 詞典/slot 改版要重訓 |

**SOTA 工具**：HuggingFace `transformers`、微調 GLiNER（其實 M3 微調就是輕量版 M5）、small seq2seq（mT5）。
**定位**：**長期**選項；等 active learning 累積夠資料再做。**不建議一開始就走**。

---

## 3.7 決策矩陣（對需求打分，5 = 最佳）

| 準則（權重） | M0 規則+模糊 | M1 檢索 | M2 +重排 | M3 GLiNER | M4 LLM | M5 自訓 |
|---|---|---|---|---|---|---|
| 跨語言（中英）★★★ | 2 | 4 | 4 | 4 | **5** | 4 |
| 語序/口語魯棒 ★★★ | 1 | 2 | 2 | 4 | **5** | 4 |
| 同義/錯字 ★★ | 3 | 4 | **5** | 4 | **5** | 4 |
| 精度天花板 ★★★ | 2 | 3 | 4 | 4 | **5** | 4 |
| 低審核成本（可校準分數）★★★ | 2 | 3 | 4 | 4 | 4 | 4 |
| 確定性/可稽核 ★★ | **5** | 4 | 4 | 4 | 2 | 4 |
| 可地端/資料落地 ★★★ | **5** | **5** | **5** | **5** | 3* | **5** |
| 維護成本（免改碼擴充）★★ | 2 | **5** | **5** | 4 | 4 | 2 |
| 基礎設施/延遲成本 ★★ | **5** | 3 | 3 | 4 | 2 | 3 |
| 冷啟動（無需標註即可起步）★★ | **5** | 4 | 4 | 4 | **5** | 1 |

\* M4 地端（vLLM + 開源模型）可拿回落地分數，但要 GPU。

**怎麼讀**：沒有任何一行全 5。M0 在「確定性/成本/冷啟動」無敵但「語意/語序」很弱；M4 在「泛化/精度」無敵但「確定性/成本/落地」要付代價；M1–M3 在中間且**互補**。→ **結論是組合，不是單選。**

---

## 3.8 推薦：分階段混合管線（Layered Hybrid）

把它們**疊起來**，各司其職，並用**信心分流**統一收斂（完整設計見 [04](04-architecture-design.md)）：

```
M0 正規化/數值/sequence 判定（確定性地基，永遠先跑）
  → M3 或 M4 做 Stage 1 抽取（拆解 + 角色，解語序/語言）
    → M1+M2 做 Stage 2 linking（候選生成 + 重排，解同義/跨語言）
      → 校準 + 多引擎一致性 → 分流（自動採用 / 送審）
        → 修正回流（M5 的養分）
```

### 兩個落地 Profile（你二選一，或先 B 後 A）

| | **Profile A — 最高精度** | **Profile B — 最低審核成本／可地端** |
|---|---|---|
| Stage 1 抽取 | **M4 LLM**（雲端 frontier 或地端 vLLM）+ constrained decoding | **M3 GLiNER**（微調）+ 規則打底 |
| Stage 2 linking | M1+M2（BGE-M3 + reranker）做 grounding 限定候選 | M1+M2（BGE-M3 + bge-reranker，全地端） |
| 難句處理 | 本來就 LLM | 殘留低信心才呼叫 M4 LLM（少量） |
| 落地性 | 雲端有疑慮；地端需 GPU | **全程可離線** |
| 精度 | **最高** | 高（且隨 active learning 逼近 A） |
| 成本/延遲 | 較高 | **低** |
| 適合時機 | 追求極致正確、可接受雲端/ GPU | 內部部署、資料敏感、要省人力 |

> **我的建議**：先用 **Phase 0（M0）** 立刻止血並建立 gold set；接著走 **Profile B 為骨幹**（地端、便宜、可稽核），把 **M4 LLM 當「殘差重砲」** 只打 B 處理不了的難句——這樣**同時拿到 A 的精度上限與 B 的成本下限**。若公司允許雲端且追求極致，再把主解析器整個切到 Profile A。

> **內部已驗證的先例**：上述「檢索＋重排＋多閘門一致性＋人回饋動態門檻」並非紙上談兵——內部 **Romantic-Rush 評測框架**（[domain-specific-llm-eval](../../../domain-specific-llm-eval)）已實作過 contextual keyword gate、human-feedback 動態門檻與 active learning。哪些可直接借用、如何對映到本專案，見 [09-prior-art-romantic-rush-eval.md](09-prior-art-romantic-rush-eval.md)。

---

下一篇 [04-architecture-design.md](04-architecture-design.md)：把這個混合管線畫成可實作的元件、資料契約、信心模型與分流邏輯，並說明它如何接進你現有的 `nl_draft_parser.py` 與路由。
