# impl-05：NL 解析與同義詞 — nlp/ 套件、DraftParserPort、rule_option_synonyms

> **Phase**：P4 ｜ **ADR**：ADR-015（supersedes ADR-010）｜ **設計輸入**：[reference/wi-parser-upgrade/](../reference/wi-parser-upgrade/)（v3 的 01–09）。
> **核心邊界**：NL 解析輸出是**建議**，經 IE 在 UI 確認才寫入 `slot_inputs`；工時真相永遠來自引擎。AI 層失效＝建議變差，**不可能**污染工時。
> **不照搬 v3 現碼**：v3 `nl_draft_parser.py` 有五項已知結構缺陷（其 `01-problem-and-requirements.md` §1.2 自承），本實作為重寫。

## 1. 套件結構（引擎外、hexagonal）

```
src/ddm_v2/nlp/
  __init__.py
  normalization.py     # NFKC → OpenCC(s2twp) → 空白收斂/英文小寫；純函數；offset map 保留原文對應
                       # 查證 C-6：v3 已實裝同等服務但只接線於 dictionary_import（parser/nl-draft route/seed 均未用，
                       # 且 seed 的 normalized_text 直接 copy 原文）——v2 必須全路徑接線：parser 入口、同義詞寫入、search 投影。
  ports.py             # DraftParserPort Protocol ＋ 輸出 dataclasses
  rule_based.py        # 第一版 adapter：字典驅動最長匹配
  lexicon.py           # 由 rule_option_synonyms + rule-set 選項 label 建匹配詞典（含快取/失效）
  # future: retrieval.py（Stage 2：impl-03 語意層連結，S5 目標形）
```

依賴方向：`nlp` → `models/schemas`（讀）；`most_engine` **不得** import `nlp`（單向）。新依賴：`opencc-python-reimplemented`（runtime deps 必須入 pyproject——[[testing-ci-hard-rules]]）。

## 2. 同義詞表（migration `v2_0013_synonyms`；S3 方案）

```sql
CREATE TABLE rule_option_synonyms (
  id uuid PRIMARY KEY,
  rule_set_id uuid NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
  parameter text NOT NULL CHECK (parameter IN ('A','B','G','P','M','X','I','vocab')),
  option_code text NOT NULL,            -- 對應各 rule_* 子表 code（vocab 時為 work_vocab_items.external_code）
  synonym_raw text NOT NULL,            -- IE 輸入原文
  synonym_norm text NOT NULL,           -- normalization 後（匹配鍵）
  priority int NOT NULL DEFAULT 0,      -- 跨參數同詞時的排序提示
  created_by text NOT NULL, created_at timestamptz NOT NULL,
  UNIQUE (rule_set_id, parameter, synonym_norm)   -- ★ 同參數內零歧義（DB 層防線）
);
```

- **同參數內唯一**：一個詞在同一參數只能指向一個選項（歧義是誤判主因，DB 直接擋）。
- **跨參數允許**（如「對準」合法存在於 P 與 I）：parser 對跨參數命中回多候選由 IE 選。
- 寫入時 service 驗 `option_code` 存在於對應子表（應用層 FK；子表異構無法用真 FK）。
- **published rule-set 可增補同義詞**（唯一的 published 後可變資料——它只影響建議層不影響工時，邊界寫入 ADR-014）。
- 初始資料：converter 延伸讀 v3 字典/`nl_draft_parser.py` 詞表 → 產生 seed；`UNIQUE` 衝突輸出**衝突報告**由 IE 逐筆裁決（殘項 #5），不得自動擇一。

## 3. Port 合約

```python
# ports.py
@dataclass(frozen=True)
class SlotCandidate:
    option_code: str
    score: float                # 0..1 校準信心
    source: str                 # "exact" | "longest_match" | "retrieval" | "default"
@dataclass(frozen=True)
class SlotSuggestion:
    slot_index: int             # 0..6
    field: str                  # 例 "g_code" / "p_base_code" / "reach_cm"
    chosen: SlotCandidate | None
    top_k: list[SlotCandidate]  # 含 chosen；跨參數歧義時 ≥2
    needs_review: bool
@dataclass(frozen=True)
class NLDraftResult:
    raw_text: str; normalized_text: str
    suggested_seq: str | None   # "GM" | "CM" | None
    context: dict               # hand / object / from / to（vocab 候選）
    slots: list[SlotSuggestion]
    overall_confidence: float
    provenance: dict            # parser 版本、詞典版本、耗時

class DraftParserPort(Protocol):
    def parse(self, text: str, rule_set_code: str) -> NLDraftResult: ...
```

> 查證 C-8：v3 的 nl-draft 輸出**無** `needs_review` 欄位（以 `warnings`＋`missing_fields` 表達）；本合約的 `needs_review` 是 v2 新設計。前端相容不是考量（v2 前端本來就是新接），但移植 v3 測試案例時注意欄位對映。

## 4. rule_based adapter — v3 五缺陷的對應修正

> 五缺陷已於 2026-07-05 對程式碼逐條證實（[verification-code-audit.md](../verification-code-audit.md) §1.2），含 confidence 實測值（inferred 0.75–0.9、default 1.0，13 個賦值點）。

| v3 缺陷（程式碼證實） | 本實作 |
|---|---|
| 先命中先贏（僅 M 最長匹配；`nl_draft_parser.py:388-698`） | **全參數統一最長匹配**：lexicon 依 `len(synonym_norm)` 降冪建 Aho-Corasick/排序詞表 |
| G 詞表遮蔽（查證 C-7 精確化：**first-hit＋子字串命中**使「拿取小」永遠先被「拿取」吃掉，與表序無關；v3 無測試覆蓋） | 詞典由 DB 生成＋最長匹配，匹配順序不再影響結果；遮蔽案例以測試鎖死 |
| 零正規化 | 進 parser 前必過 `normalization.normalize()`；簡體/全形有測試 |
| context 黑名單 regex 脆弱 | 角色標註式規則：先抽「從/到/在/放到」等介詞框架與距離數值，剩餘 span 依位置標 object/from/to；抽不出→留空＋needs_review，不硬猜 |
| 信心反置（default=1.0 > inferred） | 固定序：exact 0.95 / longest_match 0.8 / retrieval（future）0.6 / **default 0.3**；`needs_review = chosen is None or score<0.7 or 跨參數多候選` |

判型規則（GM/CM）：沿用 v3 認證的 X 機台觸發詞（「並壓合機台/進行壓合/執行壓合」→CM；「壓合治具/壓合站/壓合位置」名詞→GM）——v3 `test_nl_draft_parser.py` 的治具防護測試**全數移植**為本實作驗收案例。

## 5. API 與 UI 合約

```
POST /api/v2/worksheets/nl-draft   body: {text, rule_set_code}
→ NLDraftResult（JSON）
```

- 唯讀、無副作用；不建列不寫 cycle。前端把建議填入 workbench 表單，`needs_review` 欄位高亮＋top_k 下拉；IE 按「採用」才進既有 save 流程（引擎重新驗算——建議值不繞過引擎驗證）。
- 同義詞維護 API：`GET/POST/DELETE /api/v2/rule-sets/{code}/synonyms`（409 = UNIQUE 衝突，回應含既有映射供 IE 判斷）。

## 6. 測試

1. normalization：NFKC/繁簡/全形數字/混排各案例。
2. lexicon：最長匹配矩陣（「拿取(選取-小)」>「拿取」）、DB 同義詞優先於 label、快取失效。
3. parser 黃金：v3 治具防護案例全套 + 每參數命中/未命中/歧義（跨參數「對準」回雙候選）各一。
4. 信心：default < inferred 的排序不變量測試。
5. Endpoint：nl-draft 正常/空文本/未知 rule_set/未授權；synonyms CRUD 含 409。

## 7. 升級路線（不在 P4 實作）

S5 目標形：L1 未命中 → impl-03 L3 語意檢索連結選項 → 低信心進審核佇列。屆時只新增 `retrieval.py` adapter 與 port 內 `source="retrieval"`，合約不變。
