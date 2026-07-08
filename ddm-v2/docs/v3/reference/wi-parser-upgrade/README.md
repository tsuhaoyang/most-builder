# WI → MOST 語意解析升級：完整教材、設計與實作計畫

> **這是一套「教材 + 設計 + 實作藍圖」**，目的是把目前 [apps/api/app/services/nl_draft_parser.py](../../apps/api/app/services/nl_draft_parser.py) 的「規則式子字串比對」升級成一個
> **能處理任何奇怪 WI 句子（中英混雜、語序顛倒、錯字、口語）並穩定產出精確 MOST 句子** 的現代化管線，
> 同時把**人工審核成本壓到最低**（只挑出「不確定」的部分讓人快速 audit）。

---

## 0. 這份文件是給誰看的

| 讀者 | 怎麼用 |
|------|--------|
| **你（專案負責人）** | 從頭到尾照「學習路徑」一篇篇讀，建立對這個優化題目的深度理解。每篇都有「為什麼」而不只是「怎麼做」。 |
| **下一個接手的 LLM agent** | 先讀 [07-agent-handoff.md](07-agent-handoff.md)（工作協定 + 長時間運行規則 + Definition of Done），再依 [05-implementation-plan.md](05-implementation-plan.md) 一個 phase 一個 phase 實作，邊做邊更新本檔的「狀態看板」。 |

---

## 1. 我們要解的問題（一句話）

> 輸入：一句**自由文字**的作業描述（WI, Work Instruction），語言／語序／用詞都不可控。
> 輸出：一個**結構化、可稽核、TMU 可重現**的 MiniMOST 動作序列（sequence model + 各 slot 的 option_code + context 欄位）。
> 約束：**精確度最高**，且**人工審核成本最低**（高信心自動通過、低信心一鍵修正）。

完整問題定義見 [01-problem-and-requirements.md](01-problem-and-requirements.md)。

---

## 2. 學習路徑（建議閱讀順序）

| # | 檔案 | 你會學到 | 類型 |
|---|------|----------|------|
| 1 | [01-problem-and-requirements.md](01-problem-and-requirements.md) | 現況程式逐行診斷、需求、約束、成功指標 | 分析 |
| 2 | [02-concepts-primer.md](02-concepts-primer.md) | 正規化、斷詞、模糊比對、embedding、retrieval、reranker、NER、constrained decoding、calibration——每個積木的白話原理 | 教材 |
| 3 | [03-methods-survey.md](03-methods-survey.md) | 6 大類做法的優劣比較 + 2025–2026 SOTA + 決策矩陣 | 教材＋決策 |
| 4 | [04-architecture-design.md](04-architecture-design.md) | 推薦架構：三階段 grounded extraction + 信心分流 + 審核佇列 | 設計 |
| 5 | [05-implementation-plan.md](05-implementation-plan.md) | Phase 0→4 逐步實作、檔案清單、驗收條件 | 實作 |
| 6 | [06-evaluation-and-audit.md](06-evaluation-and-audit.md) | gold set、指標、信心校準、審核 UX、active learning | 實作＋運維 |
| 7 | [07-agent-handoff.md](07-agent-handoff.md) | 給下一個 agent 的工作協定、長時間運行、checkpoint、DoD | 協定 |
| 8 | [08-current-system-reference.md](08-current-system-reference.md) | 現況 parser 的單一事實來源（資料結構、行為、已知缺陷），升級的相容基準 | 參考 |
| 9 | [09-prior-art-romantic-rush-eval.md](09-prior-art-romantic-rush-eval.md) | **借鏡內部既有評測框架 Romantic-Rush（[domain-specific-llm-eval](../../../domain-specific-llm-eval)）＋簡報重點**：contextual gate（語意比對）、human-feedback 動態門檻（EMA/IQR/自適應視窗）、active learning、合成跨語言測試集——附對照表與可重用程式 | 參考整合 |

> **附錄 [09](09-prior-art-romantic-rush-eval.md) 怎麼讀**：它是跨章節的「站在巨人肩膀上」整合篇——讀 [03](03-methods-survey.md)（選型）、[04 §4.5–4.7](04-architecture-design.md)（信心/分流）、[06 §6.5–6.7](06-evaluation-and-audit.md)（校準/審核/主動學習）時搭配看，會看到這些設計**早被內部既有系統驗證過**，並有可直接借用的程式骨架。

---

## 3. TL;DR — 我的最終推薦

**不要押單一技術，採用「分階段的混合管線（hybrid pipeline）」，並用「信心分流（confidence-gated routing）」同時達成高精確度與低審核成本。**

核心架構（細節見 [04](04-architecture-design.md)）：

```
原文
 └─[Stage 0] 正規化 + 語言偵測（繁簡/全半形/大小寫統一，保留 offset）
     └─[Stage 1] 提及偵測 & 角色標註（語序/語言無關）  ← LLM結構化輸出 或 GLiNER
         └─[Stage 2] 對應到 MiniMOST 詞典（entity linking）← 混合檢索(BM25+BGE-M3)→reranker
             └─[Stage 3] 組裝 + 驗證 + 信心計算 + 分流
                 ├─ 高信心 → 自動採用
                 └─ 低信心/引擎不一致 → 進審核佇列（標出可疑 slot + top-K 候選一鍵選）
```

**兩個可選 profile**（你二選一或先後採用）：

- **Profile A｜最高精確度**：以 LLM（雲端 frontier 或強力地端模型）+ constrained decoding 為主解析器，檢索做 grounding，reranker 收斂，人工只審低信心。精度天花板最高，成本/延遲/部署較重。
- **Profile B｜最低審核成本／可地端**：以 **GLiNER（微調）+ BGE-M3 混合檢索 + reranker** 為主，規則打底，LLM 只處理殘留難句。確定性高、便宜、可離線、審核體驗最佳。

**無論選哪個，都先做 [Phase 0 快速勝利](05-implementation-plan.md)**：正規化 + 最長匹配 + 模糊比對（rapidfuzz/pinyin）。零 ML 基礎設施、立刻修掉現有 bug、馬上有回歸測試可量測。

> **能同時「最準」又「最省審核」的關鍵不是某個模型，而是三件事**：
> (1) **abstention 機制**（不確定就不猜，標記待審）；
> (2) **ensemble 不一致 = 不確定訊號**（多引擎一致才自動通過）；
> (3) **一鍵審核 UI**（只看被標記的 slot，top-K 候選預先載好）。

> **這三件事不是憑空設計**——內部既有的 **Romantic-Rush 評測框架**（[domain-specific-llm-eval](../../../domain-specific-llm-eval)）已用 contextual keyword gate、human-feedback 動態門檻、active learning、合成跨語言測試集**實作驗證過一輪**。我們把那套迴路移植到 WI→MOST 的 slot 連結上，對照與可重用程式見 [09](09-prior-art-romantic-rush-eval.md)。

---

## 4. 狀態看板（下一個 agent 請持續更新）

> 規則：每完成一個 phase，把狀態從 `⬜` 改成 `✅`，並在「備註」填入 commit / 量測結果（gold set 分數）。
> 任何 phase 未達驗收門檻就**不要**進下一個 phase。

| Phase | 內容 | 狀態 | 驗收門檻（見 05/06） | 備註 |
|-------|------|------|----------------------|------|
| 0 | 正規化 + 最長匹配 + 模糊比對 + 回歸測試骨架 | ⬜ | gold set slot accuracy 不退步，且修掉已知遮蔽 bug | |
| 1 | 詞典向量化 + 混合檢索 grounding（候選生成） | ⬜ | 各 slot recall@5 ≥ 0.95 | |
| 2 | Stage 1 抽取（GLiNER 或 LLM 結構化輸出） | ⬜ | 跨語言/亂序測試集 slot F1 ≥ 0.90 | |
| 3 | Reranker + 信心校準 + 審核分流 | ⬜ | 在 auto-accept 段 precision ≥ 0.98，coverage ≥ 0.7 | |
| 4 | Active learning 回流 + 審核 UI 強化 | ⬜ | 審核率隨資料累積下降；修正一鍵回灌 | |

---

## 5. 名詞速查（Glossary）

| 詞 | 白話解釋 |
|----|----------|
| **WI** | Work Instruction，作業指導／作業描述（本系統的自由文字輸入）。 |
| **MOST / MiniMOST** | 一種工時量測法；把動作拆成參數 slot（A 距離、B 身體、G 取得、P 放置、M 控制移動、X 製程、I 檢查），各對應 TMU。 |
| **slot / option_code** | 每個參數位（如 G）有一組**封閉**的選項（如 `G_GRASP`）。解析的核心就是把文字對到正確 option_code。 |
| **sequence model** | `GENERAL_MOVE` 或 `CONTROLLED_MOVE`，決定 slot 的排列骨架。 |
| **TMU** | Time Measurement Unit，最終工時單位；由詞典決定，**計算引擎才是權威**，AI 只做建議預填。 |
| **normalization** | 把不同寫法統一（繁簡、全半形、大小寫、空白）。 |
| **tokenization / 斷詞** | 把中文句子切成詞，讓比對在「詞」而非「字串包含」層級進行。 |
| **fuzzy matching** | 容錯比對（錯字、形近、同音），如 rapidfuzz、pinyin。 |
| **embedding / 向量** | 把文字映射成向量，語意相近的距離相近（如 BGE-M3、Qwen3-Embedding）。 |
| **dense / sparse / hybrid retrieval** | 稠密向量檢索 / 詞彙（類 BM25）檢索 / 兩者混合。 |
| **reranker (cross-encoder)** | 對候選做更精準的二次排序（query 與候選一起進模型）。 |
| **entity linking / canonicalization** | 把文字片段對應到本體（ontology, 即 MiniMOST 詞典）中的標準項。 |
| **NER / span labeling** | 命名實體辨識 / 把句子的片段標上角色（如 from_location、grasp_verb）。 |
| **GLiNER** | 輕量、可零樣本的多語 NER 模型，CPU 可跑、可微調。 |
| **constrained decoding / structured output** | 強制 LLM 只能輸出符合 schema（含 enum 限定 option_code）的結果，如 Outlines、OpenAI Structured Outputs。 |
| **calibration / 校準** | 把模型分數轉成可信的機率，用來設審核門檻。 |
| **abstention / selective prediction** | 「不確定就棄權」，交給人工，以換取自動通過部分的高精確度。 |
| **active learning** | 用人工修正回流，持續讓系統變準（補同義詞、補 few-shot、再微調）。 |
| **HITL** | Human-in-the-loop，人在迴路（審核）。 |

---

## 6. 重要設計原則（貫穿所有文件）

1. **計算引擎維持權威、AI 只做建議**：任何升級都不改 TMU 計算的確定性與可重現性（製造業稽核要求）。
2. **每個 slot 都要有 provenance**：來源引擎、候選、分數、模型/prompt 版本都要記錄，才能 audit 與回溯。
3. **fail loud, not silent**：寧可標「待確認」，也不要自信地猜錯（錯誤工時比缺漏更危險）。
4. **每個 phase 可獨立上線、可量測、可回退**：用 gold set 當守門員，沒過不准進下一步。
5. **先確定性、再機率性**：能用規則/數值精確解的（如距離→區間）就不要丟給模型。

---

接下來請讀 [01-problem-and-requirements.md](01-problem-and-requirements.md)。
