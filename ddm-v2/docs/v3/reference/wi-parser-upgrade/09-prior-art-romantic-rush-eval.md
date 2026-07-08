# 09 · 借鏡內部既有系統：Romantic-Rush 評測框架（domain-specific-llm-eval）＋ 簡報重點整理

> **這篇是「跨章節的參考整合」**，把公司內部既有、且已驗證的 LLM 評測框架
> **Romantic-Rush**（程式在 [`domain-specific-llm-eval/`](../../../domain-specific-llm-eval)、簡報為 [`llm-rag-eval.pdf`](../../llm-rag-eval.pdf)）的方法，
> **對映**到本專案 WI→MOST 的三件難事：**(A) 片段→option_code 的語意連結**、**(B) 信心分流與審核**、**(C) gold set 與跨語言測試集**。
>
> **為什麼值得整合**：你要做的「**把不確定的匹配挑出來給人快速 audit、並讓系統越用越準**」，Romantic-Rush **已經實作過一整套**（contextual keyword gate、human-feedback 動態門檻、active learning、跨中英測試集生成）。我們**直接沿用它的設計與可重用程式**，少走很多彎路。
>
> 讀法：先看 §9.1 的對照總表抓全貌，再依你正在做的 Phase 跳到對應小節。本篇被 [03](03-methods-survey.md)、[04](04-architecture-design.md)、[06](06-evaluation-and-audit.md) 交叉引用；現況程式的事實基準見 [08-current-system-reference.md](08-current-system-reference.md)。

---

## 9.1 對照總表：它的方法 → 我們的哪一段

| Romantic-Rush 的元件 | 它原本在做什麼 | 對映到 WI→MOST 的位置 | 採用價值 |
|----------------------|----------------|------------------------|----------|
| **Contextual Keyword Gate**（[contextual_keyword_gate.py](../../../domain-specific-llm-eval/contextual_keyword_gate.py)、簡報 p25–26、p49–54） | 把答案做語意分段 → sentence-transformer 編碼 → 與「關鍵字」算 cosine → 加權門檻判過/不過 | **Stage 2 實體連結**（[04 §4.6](04-architecture-design.md)）：span → option 語意比對的**現成範式** | 直接複用「分段→嵌入→相似度→門檻」骨架；mandatory/optional 加權 ≈ 我們的 slot 必填/選填 |
| **Dynamic Metrics Gates System**（簡報 p14、p34） | Keyword Gate + RAGAS Metric Gate + G-Eval + Human Feedback **互相對齊（align）** | **Stage 3 多引擎一致性**（[04 §4.7](04-architecture-design.md)）：rule/gliner/llm 多閘門對齊 | 「多閘門對齊 = 不確定訊號」的成熟先例 |
| **Human Feedback Integration（EMA）**（[dynamic_ragas_gate_*.py](../../../domain-specific-llm-eval/dynamic_ragas_gate_with_human_feedback.py)、簡報 p27–30） | 用人工回饋以**指數移動平均**微調門檻 | **信心校準＋門檻**（[06 §6.5](06-evaluation-and-audit.md)）：門檻不是寫死，隨回饋演進 | 把我們「TAU_AUTO 可設定」升級成「**會自我調整**」 |
| **Threshold Sensitivity Smoothing**（簡報 p28） | 門檻歷史的**滾動中位數**避免抖動 | 門檻治理：避免單筆回饋讓門檻劇烈跳動 | 穩定性保險 |
| **Active Learning for HF Collection**（簡報 p29、p32） | **信心門檻 bound + 不確定區間 + 多元抽樣**決定「哪些要人看」 | **審核分流取樣**（[06 §6.6–6.7](06-evaluation-and-audit.md)）：挑出「最該被 audit」的 | 正中你「人力成本最低」訴求 |
| **Adaptive Window by Variance**（簡報 p30） | 回饋變異大→放大觀察視窗，穩定→縮小 | 校準/門檻更新的取樣窗 | 回饋雜訊自適應 |
| **Dynamic Uncertainty + Diverse Sampling（IQR）**（簡報 p32–33） | 用**四分位距**動態界定不確定區間，並抽樣部分高信心樣本防偏 | 審核佇列取樣策略 | 防止「只審低分」造成的盲區 |
| **Synthetic Testsets from Knowledge Graphs**（簡報 p36–45、[eval-pipeline](../../../domain-specific-llm-eval/eval-pipeline)） | 文件→KG→personas→scenarios→queries 自動生成測試集 | **gold set 規模化**（[06 §6.2](06-evaluation-and-audit.md)）：自動擴增奇怪句測試集 | 解 gold set 冷啟動與規模 |
| **Combining English with Chinese testsets**（簡報 p46） | 同一測試集**混合中英**關鍵字 | **跨語言測試集**（[06 §6.2 challenge=mixed_lang/english](06-evaluation-and-audit.md)） | 直接對應你「中英混雜」需求 |
| **RAGAS 四指標**（簡報 p22–24） | faithfulness / answer_relevancy / context_precision / context_recall | **評測指標借形不照搬**（§9.5） | 提供「檢索 vs 生成」分層量測的思路 |
| **Why Not Just LLM-as-a-Judge**（簡報 p65–66） | 純 LLM 評審缺**可量化指標**與**可除錯性** | 佐證我們**不靠單一 LLM**、要確定性閘門 | 設計理念背書 |
| **Multi-Agent Dynamic Routing**（簡報 p88） | `>0.9 全自動 / 0.7–0.9 人審 / <0.7 轉專家`——「**漸進式自動化，而非懸崖**」 | **Stage 3 分流分級**（[04 §4.7.2](04-architecture-design.md)） | 我們分流門檻分級的直接範本 |
| **Orthogonal / Multi-layer Validation**（簡報 p93–94） | 多代理各驗不同面向、序列驗證閘 | **多引擎一致性 + 關鍵 slot 守門** | 「不一致就送審」的理論支撐 |

> **一句話**：Romantic-Rush 的核心 IP 是「**Gate（閘門）＋ Human Feedback（人回饋）＋ Active Learning（主動學習）＋ 動態門檻**」這條迴路。本專案 [04](04-architecture-design.md) §4.5–4.7 與 [06](06-evaluation-and-audit.md) §6.5–6.7 的設計，**就是把這條迴路套用在 WI→MOST 的 slot 連結上**。

---

## 9.2 把 Contextual Keyword Gate 變成我們的 Stage 2 連結器

Romantic-Rush 的 [contextual_keyword_gate.py](../../../domain-specific-llm-eval/contextual_keyword_gate.py) 流程（簡報 p25–26）：

```text
answer ──spaCy 分段──> segments ──SentenceTransformer──> 向量
keywords ──同編碼──> 向量
score(keyword) = max_over_segments cosine(keyword, segment)
total = mean(mandatory)·w_m + mean(optional)·w_o ；過門檻則 pass
```

**對映到我們**：把「answer 的 segments」換成 **Stage 1 抽到的角色 span**，把「keywords」換成 **某 slot 的候選 option 文字（`sentence_text_zh + synonyms`）**，就得到一個**極簡的 slot 連結器**——這正是 [04 §4.6 候選生成](04-architecture-design.md) 的最小可行版（Phase 1 還沒接 BGE-M3 前就能先跑）。

**差異與升級點（務必照做）**：

| Romantic-Rush 原作 | 我們的 WI→MOST 調整 | 原因 |
|--------------------|--------------------|------|
| `all-MiniLM-L6-v2`（英文） | **BGE-M3 / multilingual-e5**（多語） | 必須跨中英（[02.4](02-concepts-primer.md)） |
| spaCy `en_core_web_sm` 分段 | 中文用 **jieba + 角色 span**（[02.2](02-concepts-primer.md)） | 英文分段器不適用中文 |
| 只回 pass/fail 分數 | 回 **top-K 候選 + 分數**（給審核一鍵選） | 服務 [06 §6.6 一鍵審核](06-evaluation-and-audit.md) |
| mandatory/optional 權重 | 映成 **關鍵 slot（G/P/M/X/I）/ 次要 slot（A/B）** 的嚴/寬門檻 | 對齊 [04 §4.7.2 分流](04-architecture-design.md) |
| 純 bi-encoder | **加 reranker 精排**（[04 §4.6.3](04-architecture-design.md)） | bi-encoder 永遠回最近鄰，需精排（[02.6](02-concepts-primer.md)） |

**可直接借用的骨架（改多語 + 回 top-K）**：

```python
# services/nl_parser/linking/keyword_gate.py — 借鏡 contextual_keyword_gate.py，改為多語 + top-K
from sentence_transformers import SentenceTransformer, util

_MODEL = SentenceTransformer("BAAI/bge-m3")  # ← 多語；原作是 all-MiniLM-L6-v2（英文）

def link_span_to_options(span_text: str, option_texts: dict[str, str], top_k: int = 5):
    """span → 該 slot 的候選 option_code top-K（含相似度）。"""
    codes = list(option_texts)
    opt_emb = _MODEL.encode(list(option_texts.values()), convert_to_tensor=True, normalize_embeddings=True)
    q_emb = _MODEL.encode(span_text, convert_to_tensor=True, normalize_embeddings=True)
    sims = util.cos_sim(q_emb, opt_emb)[0]          # 對齊原作的 cosine 比對
    ranked = sorted(zip(codes, sims.tolist()), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]                            # ← 回 top-K，給審核一鍵選（原作只回單一分數）
```

> 之後 Phase 1 換成 BGE-M3 hybrid（dense+sparse）+ pgvector，Phase 3 加 reranker，就是 [04 §4.6](04-architecture-design.md) 的完整版。這支「keyword_gate」可保留為**無向量服務時的離線備援**（呼應 [04 §4.11 失效回退](04-architecture-design.md)）。

---

## 9.3 把 Human-Feedback 動態門檻變成我們的「會自我調整的審核門檻」

[06 §6.5](06-evaluation-and-audit.md) 把 `TAU_AUTO` 定成「可設定的旋鈕」。Romantic-Rush 的 [dynamic_ragas_gate_with_human_feedback.py](../../../domain-specific-llm-eval/dynamic_ragas_gate_with_human_feedback.py) 更進一步——**門檻會隨人工回饋自我調整**（簡報 p27–32），這對「長期把人力壓低」極有價值。它的四個機制：

1. **指數移動平均（EMA）更新門檻**：`new = α·signal + (1-α)·old`（`alpha=0.1`），新回饋慢慢牽動門檻，不暴衝。
2. **自適應視窗（adaptive window）**：回饋**變異高**→放大觀察視窗（看更多筆才動），**穩定**→縮小（反應更快）。對應 `calculate_adaptive_window_size(variance, …)`。
3. **滾動中位數平滑（rolling median）**：對門檻歷史取中位數，避免單一異常回饋造成門檻抖動（簡報 p28）。
4. **不確定區間 + 多元抽樣決定誰要送審**：`needs_human_feedback_dynamic()` 用 **IQR（四分位距）** 動態界定「不確定帶」`[certainty_low, certainty_high]`，落在帶內的送審；**另外以小機率抽樣高信心樣本**（`diverse_sample_rate=0.2`）防止盲區（簡報 p32–33）。

**對映到我們**（[06 §6.5/§6.7](06-evaluation-and-audit.md) 的升級版）：

```python
# services/nl_parser/confidence.py — 借鏡 dynamic_ragas_gate_with_human_feedback.py
class AdaptiveThreshold:
    def __init__(self, tau=0.92, alpha=0.1, lo_bound=0.45, hi_bound=0.97):
        self.tau, self.alpha = tau, alpha
        self.lo_bound, self.hi_bound = lo_bound, hi_bound
        self.feedback, self.history = [], [tau]

    def needs_review(self, p_cal: float, recent_scores: list[float]) -> bool:
        # IQR 動態界定不確定帶（對齊原作 dynamic_uncertainty_adjustment）
        import numpy as np
        q1, q3 = np.percentile(recent_scores or [0.5], [25, 75])
        lo = max(self.lo_bound, q1 - 0.1); hi = min(self.hi_bound, q3 + 0.1)
        in_uncertain = lo <= p_cal <= hi
        confident_sample = p_cal > hi and np.random.random() < 0.2  # 多元抽樣防盲區
        return in_uncertain or confident_sample or (p_cal < self.tau)

    def update(self, human_pass: int):
        # EMA + 自適應視窗 + 滾動中位數（對齊原作 p28–30）
        import numpy as np
        self.feedback.append(human_pass)
        var = np.var(self.feedback[-10:]) if len(self.feedback) > 1 else 0
        win = 3 if var < 0.2 else min(10, int(3 + (var/0.2)*7))
        signal = float(np.mean(self.feedback[-win:]))
        self.tau = self.alpha*signal + (1-self.alpha)*self.tau     # EMA
        self.history.append(self.tau)
        self.tau = float(np.median(self.history[-win:]))           # 滾動中位數平滑
```

> **採用建議**：Phase 3 先用 **固定門檻**（[06 §6.5](06-evaluation-and-audit.md) 從 risk–coverage 曲線手選）上線、簡單可稽核；Phase 4 再切到上面的 **AdaptiveThreshold**，把人工修正自動牽動門檻——這正是 [05 Phase 4](05-implementation-plan.md) 「審核率隨時間下降」的引擎。**製造業稽核注意**：門檻自我調整必須**記錄每次變更（值、觸發回饋、時間）進 provenance**，否則違反 [NFR1 可重現](01-problem-and-requirements.md)。建議「門檻快照隨 dictionary_version 凍結」，重跑歷史時用當時門檻。

---

## 9.4 用「合成測試集」規模化我們的 gold set（解冷啟動）

[06 §6.2](06-evaluation-and-audit.md) 的 gold set 起步靠人工標 30–50 句，規模是瓶頸。Romantic-Rush 的 [eval-pipeline](../../../domain-specific-llm-eval/eval-pipeline) 提供 **從知識圖譜自動生成測試集** 的成熟管線（簡報 p36–45），可借來**自動擴增奇怪句**：

- **流程**（簡報 p39–44）：文件 → 切塊成階層節點 → 抽取器建關係 → 知識圖譜 → personas × scenarios → 生成 queries。
- **對我們的用法**：把 **MiniMOST 詞典 + 既有 WI 樣本**當「文件」，用 query synthesizer 產生**各種語序/語言/口語變體**的 WI 句，再由人**只驗答案**（比從零標註省力）。
- **跨語言（簡報 p46）**：直接生成「中英混合」測試句，餵 [06](06-evaluation-and-audit.md) 的 `mixed_lang` / `english` challenge 維度。
- **scenarios/personas（簡報 p45、p55–63）**：用「不同作業員講法」當 persona，自然產出口語、贅字、簡寫變體 → 正中你「不論多奇怪的句子」。

> **務必守的紀律**：合成句**可大量生成**，但 gold 答案要**人工抽驗**（至少高信心抽樣 + 全部低信心）。合成資料是**擴大覆蓋**，不是**取代人工標準答案**——否則會把模型的偏誤當成真理（簡報 p65 「Why Not Just LLM-as-a-Judge」正是此理）。建議：合成句進 `dev` 切分擴覆蓋，`test` 切分維持**人工標註**保權威（呼應 [06 §6.2 切分](06-evaluation-and-audit.md)）。

---

## 9.5 RAGAS 指標：借「分層量測」的形，不照搬

Romantic-Rush 大量用 **RAGAS**（簡報 p22–24）：

- **檢索品質**：context_precision（檢回的相關比例）、context_recall（該檢回的有沒有檢回）。
- **生成品質**：faithfulness（答案是否忠於 context）、answer_relevancy（答案是否切題）。

**我們不是 RAG 問答，但可借「分層」思路**對映到 WI→MOST：

| RAGAS 概念 | 我們的等價量測（已在 [06 §6.3](06-evaluation-and-audit.md)） |
|------------|------------------------------------------------------------|
| context_recall | **recall@K**：正解 option 是否落在候選 top-K（檢索召回） |
| context_precision | reranker 精排後**正解排第 1 的比例**（連結精度） |
| faithfulness | **provenance 一致性**：每個 slot 的判定是否有命中片段支撐（不憑空捏） |
| answer_relevancy | **sentence exact-match**：組出的 MOST 句是否真對應原文語意 |

> 重點：**指標要服務「自動通過 vs 送審」的決策**，所以我們的主指標仍是 [06 §6.3](06-evaluation-and-audit.md) 的 **auto-precision / coverage / audit-rate**；RAGAS 式分層只是幫你**定位失敗在「召回」還是「精排」**，便於除錯（呼應簡報 p66「Why Not LLM-as-a-Judge：Debug」）。

---

## 9.6 分流分級：直接採用簡報的「漸進式自動化」

簡報 p88 的 Multi-Agent Dynamic Routing 給了現成的分級門檻，與 [04 §4.7.2](04-architecture-design.md) 對齊：

| 信心 `p_cal` | Romantic-Rush 動作 | 我們的對應動作 |
|--------------|--------------------|----------------|
| `> 0.9` | 全自動回應 | **自動採用**（且多引擎一致） |
| `0.7 – 0.9` | Agent 回應 + 人審選項 | **送審**：top-K 一鍵選（[06 §6.6](06-evaluation-and-audit.md)） |
| `< 0.7` | 轉專家 / 人工 | **標 missing + 安全預設 + 送審**（fail loud） |

> 「**a gradient of automation rather than a cliff**」就是我們要的：不是「全自動 or 全人工」，而是**按信心分級**。把這三條當 `TAU_AUTO=0.9`、`TAU_ABSTAIN=0.7` 的起手值，再用 [06 §6.5](06-evaluation-and-audit.md) 的 risk–coverage 曲線校到你詞典的實況。

---

## 9.7 落地建議：哪些現在就抄、哪些列入待辦

| 借鏡項目 | 何時導入 | 對應 Phase | 風險/注意 |
|----------|----------|-----------|-----------|
| Contextual keyword gate 骨架（改多語+top-K，§9.2） | 立刻可當 Phase 1 前的最小連結器/離線備援 | [05 Phase 1](05-implementation-plan.md) | 別用英文模型；中文要先斷詞 |
| 分流三分級門檻（§9.6） | Phase 3 起手值 | [05 Phase 3](05-implementation-plan.md) | 之後用曲線校準 |
| 固定門檻 → 先上線 | Phase 3 | [05 Phase 3](05-implementation-plan.md) | 簡單、可稽核 |
| AdaptiveThreshold（EMA+IQR+視窗，§9.3） | Phase 4 | [05 Phase 4](05-implementation-plan.md) | **門檻變更要進 provenance**，否則破壞可重現性 |
| 合成測試集（KG→queries，§9.4） | gold set 擴增階段 | [06 §6.2](06-evaluation-and-audit.md) | `test` 切分仍須人工標註 |
| RAGAS 式分層除錯（§9.5） | 任何 Phase 除錯時 | [06 §6.3](06-evaluation-and-audit.md) | 不取代 auto-precision/coverage 主指標 |
| 多元抽樣（高信心抽查，§9.3） | Phase 4 | [06 §6.7](06-evaluation-and-audit.md) | 防「只審低分」盲區 |

---

## 9.8 兩個專案的邊界（不要過度耦合）

- Romantic-Rush 是**評測/守門框架**（評 LLM 答得好不好）；我們是**結構化抽取系統**（把 WI 轉 MOST）。**借的是「閘門 + 人回饋 + 主動學習 + 動態門檻」這套方法論與部分程式骨架，不是整包搬進來。**
- **不要**把 RAGAS 的 faithfulness/answer_relevancy 當成我們的上線判準（那是 RAG 問答指標）；我們的判準是 option_code 對不對（[06 §6.3](06-evaluation-and-audit.md)）。
- **不要**引入它的服務層（services/、compose、KG API）除非你真的要那套微服務；WI→MOST 只需把上述**方法與程式片段**併入 `services/nl_parser/`。

---

## 9.9 一句話總結

> 你想要的「**把不太確定的匹配挑出來、讓人一鍵 audit、而且越用越準**」，Romantic-Rush 已用
> **contextual gate（語意比對）＋ human-feedback 動態門檻（EMA/IQR/自適應視窗）＋ active learning ＋ 合成跨語言測試集**
> 驗證過一輪。本專案的 [04 §4.5–4.7](04-architecture-design.md) 與 [06 §6.5–6.7](06-evaluation-and-audit.md) 就是把這套迴路**移植到 slot 連結上**；本篇提供對照表與可重用程式，讓你（與下一個 agent）少踩坑、直接站在已驗證的肩膀上。

---

延伸：回到 [03 方法調查](03-methods-survey.md) 看這些方法在決策矩陣的位置，或到 [06](06-evaluation-and-audit.md) 看評測與門檻的完整操作。下一個 agent 的工作協定見 [07-agent-handoff.md](07-agent-handoff.md)。
