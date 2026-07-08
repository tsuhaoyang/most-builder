# 01 · 問題定義、現況診斷與需求

## 1.1 我們的輸入與輸出到底是什麼

### 輸入：自由文字 WI（不可控）
使用者在 workbench 的「AI 快速建模」框輸入一句話，例如：

- `從料架上拿DIMM放至流水線`
- `右手抓取螺絲鎖附到主板`
- `left hand pick the connector and snap-fit onto PCB`（英文）
- `放至流水線，DIMM從料架上拿`（語序顛倒）
- `用右手把對淮的元件插進去`（口語＋錯字「對淮」）

### 輸出：結構化 MOST 動作（可稽核、TMU 可重現）
解析器要產出 [NLDraftResult](../../apps/api/app/services/nl_draft_parser.py)，核心是：

```text
sequence model:  GENERAL_MOVE | CONTROLLED_MOVE
context fields:  hand_type, show_hand_in_sentence,
                 from_location, target_object, component, to_location, where_location
slot options:    每個 slot 的 option_code（封閉集合）
  ├ A1/A2/A3  距離  → reach_distance 區間（數值映射）
  ├ B1/B2     身體  → B_STAND / B_EYE_MOVE / B_BEND_OR_SIT
  ├ G         取得  → G_GRASP / G_PICK / G_SELECT / …（10 種）
  ├ P         放置  → base_action（4 種）+ modifiers（對準/插入/卡合）
  ├ M         控制移動 → M_PRESS_BUTTON / 推/拉/旋轉…
  ├ X         製程  → 壓合/熱熔/點膠/鎖附/掃碼…
  └ I         檢查  → check/confirm/align × (normal | outside 視線)
```

最終句子的組裝順序（見 [most.py `_compose_full_sentence`](../../apps/api/app/api/routes/most.py)）：

- **GENERAL_MOVE**：`使用手 + 從哪裡 + A1 + B1 + G + 目標物 + 元件 + A2 + B2 + P + 至哪裡 + A3`
- **CONTROLLED_MOVE**：`使用手 + 從哪裡 + A1 + B1 + G + 目標物 + 元件 + M + 至哪裡 + X + I + 哪裡 + A3`

> **關鍵觀察**：這不是「整句配一個答案」的分類題，而是**一句話要拆成多個 slot + 多個開放欄位**的**結構化抽取（structured extraction / semantic parsing over an ontology）**。這個本質決定了後面所有技術選型。

---

## 1.2 現況程式逐行診斷（為什麼會「很笨」）

目前 [nl_draft_parser.py](../../apps/api/app/services/nl_draft_parser.py) 是 **Stage 1 規則式**：`RuleBasedDraftParser.parse()` 依序做 hand → context(regex) → distance → B → actions → A/B defaults → warnings。它的「比對」核心是一行：

```python
for kw in keywords:
    if kw in text:        # ← 子字串包含，毫無「模糊」可言
        ...
        return            # ← 第一個命中就回傳，順序決定優先級
```

### 五個結構性弱點

| # | 弱點 | 證據（程式位置） | 後果 |
|---|------|------------------|------|
| 1 | **「先命中先贏」，非最長匹配** | `_parse_g` / `_parse_p` / `_match_x` / `_match_i` / `_parse_b` 都用 `for kw in keywords: if kw in text: return` | 短詞遮蔽長詞，順序錯就配錯 |
| 2 | **G 詞表有實際遮蔽 bug** | `G_SYNONYMS`：`(["拿取","拿","取",…],"G_SELECT")` 排在 `(["拿取小",…],"G_SELECT_SMALL")` **前面** | 「拿取小元件」永遠命中 `G_SELECT`，`G_SELECT_SMALL` 不可達 |
| 3 | **只有 M 用了最長匹配** | `_parse_m` 與 `_parse_controlled_move_context` 用 `sorted(keywords, key=len, reverse=True)`；G/P/X/I/B **沒有** | 同類 bug 散落各 slot |
| 4 | **零正規化** | 全檔無 NFKC / 繁簡轉換；詞表是繁體 | 「检查」(簡)、「２０cm」(全形)、英文輸入全部 miss |
| 5 | **context 抽取靠脆弱 regex** | `_parse_context` 用一串字元黑名單 `[^\s拿取抓放推拉插刷]` | 語序一變、用詞一換就抓錯或抓不到 |

### 其他限制
- **信心是寫死的常數**（`confidence=0.85/0.9/0.8/0.6`），不是真的「不確定性」，無法用來做有意義的審核分流。
- **完全無法跨語言**：英文 WI 直接全 miss。
- **語序敏感**：`_parse_controlled_move_context` 依賴「G verb 在 M/X 之前」的位置假設，顛倒就崩。
- **同義詞維護是手動**：每個新講法都要有人去改 `*_SYNONYMS` 或 DB `synonyms_json`。
- **信心反置（比寫死更糟）**：`source="default"`（純猜）給 `confidence=1.0`，反而**高於**真正 inferred 的 0.8–0.9 → 任何分流都會優先信任「猜的」。見 [08 §8.8](08-current-system-reference.md)。
- **parser 內硬編 TMU**：`_apply_b_defaults` 的 B1/B2 預設 `tmu=42/10` 直接寫死、未走詞典 → 詞典改值即不一致（[08 §8.9 D6](08-current-system-reference.md)）。
- **跨 slot 關鍵字碰撞**：`對準`/`對齊`/`卡合` 同時對到多個 slot（P modifier ↔ I ↔ X），同一詞依解析路徑給不同答案（[08 §8.9 D4](08-current-system-reference.md)）——這類是**語意歧義**，升級後應交給「多引擎不一致 → 送審」而非硬寫死。

> 📋 現況的完整結構（資料類別、option_code 全清單、詞典 JSON 路徑、A 區間表、DB 同義詞鉤子、11 項已確認缺陷）整理在 **[08 現況系統事實清單](08-current-system-reference.md)**，作為升級時的相容基準與單一事實來源。

> 結論：現況在「**乾淨、照預期語序、繁體、用詞剛好在表內**」的句子上堪用；一旦遇到你要的「奇怪句子」就大量失準。這正是升級的動機。

---

## 1.3 「奇怪句子」挑戰分類（測試集要涵蓋這些）

把「不論多奇怪」拆成可測的維度，之後 gold set（見 [06](06-evaluation-and-audit.md)）要每類都有樣本：

| 維度 | 範例 | 對策（預告） |
|------|------|--------------|
| **繁簡混用** | `检查后放置` | Stage 0 OpenCC 正規化 |
| **全半形/英數** | `伸手２０ＣＭ` | Stage 0 NFKC |
| **錯字／形近** | `對淮`(對準)、`鎖咐`(鎖附) | 模糊比對 rapidfuzz |
| **同音字** | `壓合` vs `押合` | pinyin 比對 |
| **中英混雜** | `right hand 拿 connector 卡合` | 多語 embedding / LLM |
| **純英文** | `pick screw, fasten to mainboard` | 多語 embedding / LLM |
| **語序顛倒** | `放到流水線，從料架拿DIMM` | Stage 1 角色標註（位置無關） |
| **口語／贅字** | `就把那個東西大概放上去` | LLM 抽取 + abstention |
| **一句多動作** | `拿A放B，再拿C鎖附` | 分段（segmentation）成多筆 |
| **同義講法不在表內** | `扣上`（=卡合 `P_SNAP_FIT`） | 語意檢索 + reranker |
| **缺資訊** | `放上去`（沒講距離/身體） | 預設值 + 標「待確認」 |
| **歧義** | `對準`（可能是 P 修飾，也可能是 I 檢查） | 多引擎不一致 → 審核 |

---

## 1.4 需求規格

### 功能需求（FR）
- **FR1**：輸入任意語言／語序的 WI，輸出合法的 MOST 結構（sequence model + slots + context）。
- **FR2**：每個 slot 附 **calibrated confidence** 與 **top-K 候選**（供一鍵修正）。
- **FR3**：能把一句多動作**分段**成多筆 action module。
- **FR4**：每個結果附 **provenance**（來源引擎、命中片段、分數、模型/prompt 版本）。
- **FR5**：低信心／引擎不一致的項目進入**審核佇列**，並在 UI 標出可疑 slot。
- **FR6**：人工修正能**回流**成同義詞 / few-shot / gold sample（active learning）。

### 非功能需求（NFR）
- **NFR1 可重現／可稽核**：相同輸入 + 相同模型/詞典版本 → 相同輸出（製造業要求）。LLM 一律 `temperature=0` 且鎖版本並快取。
- **NFR2 計算引擎權威**：解析只做「建議預填」，TMU 仍由現有計算引擎決定，不可被 AI 蓋過。
- **NFR3 資料落地**：公司內部製造資料敏感；要提供**可完全地端**的方案（Profile B）。
- **NFR4 延遲**：互動式預填，p95 目標 < 2s（地端小模型）或 < 4s（雲端 LLM）。
- **NFR5 漸進可回退**：每個 phase 可獨立開關（feature flag），出問題能退回上一個確定性層。
- **NFR6 維護成本**：新增 slot 選項時，不需要改程式（靠詞典 + 向量索引 + few-shot 設定驅動）。

---

## 1.5 成功指標（怎麼算「成功」）

詳細定義與量測腳本見 [06](06-evaluation-and-audit.md)，這裡先建立直覺：

| 指標 | 定義 | 目標 |
|------|------|------|
| **Slot accuracy** | 各 slot option_code 對的比例 | ≥ 0.95（含跨語言/亂序集） |
| **Sentence exact-match** | 整句 MOST 結構完全正確的比例 | ≥ 0.85 |
| **Slot F1（抽取）** | Stage 1 span 抽取的 precision/recall | ≥ 0.90 |
| **Coverage@Precision** | 在「自動通過 precision ≥ 0.98」前提下，能自動通過的比例 | ≥ 0.70 且持續上升 |
| **Audit rate** | 需人工審核的比例 | 越低越好；隨 active learning 下降 |
| **Time-to-audit** | 每筆審核平均耗時 | < 10 秒/筆（一鍵候選） |

> **「精度最高」與「審核成本最低」其實是同一條曲線（risk–coverage curve）上的兩個取捨點**。我們不選單點，而是**讓門檻可調**：要更準就提高自動通過門檻（coverage 降、人工多）；要更省人力就降低門檻（coverage 升、靠信心保證精度）。這條曲線怎麼畫、怎麼設門檻，是 [06](06-evaluation-and-audit.md) 的重點。

---

下一篇 [02-concepts-primer.md](02-concepts-primer.md)：把會用到的每個技術積木用白話講清楚，讓你讀後面的設計時沒有黑盒子。
