"""Rule-based DraftParser adapter — 字典驅動最長匹配。

修正 v3 五項已知缺陷（impl-05 §4）：
1. 全參數統一最長匹配（v3 僅 M 有最長匹配）
2. G 詞表遮蔽問題由長詞優先 lexicon 解決
3. 全路徑過 normalization.normalize()
4. context 以介詞框架抽取，抽不出留空而非硬猜
5. 信心排序：exact=0.95 > longest_match=0.8 > default=0.3（v3 default=1.0 反置）

D3-017（IE 核可）：GM/CM 判型從「只認名詞觸發詞」擴成「動詞字典命中參與判型」
——M 動詞命中是 CM 訊號、G+P 動詞組合是 GM 訊號；衝突矩陣與棄權路徑見
`classify_seq`。判型與 slot 填充共用**同一次** lexicon 掃描（同一份傳入的
synonyms，無平行查詢路徑）。VERSION 維持 rule_based_v1：此名是 planner 路徑
身分（plan_origin／自我指涉排除的配對鍵），不是行為雜湊；行為變更由
worklog D3-017 與本 docstring 留痕。

D3-023（IE 核可開票）：X/I 動詞面命中參與判型——X 與 I **只存在於 CM 序列**
（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：
CM＝A B G M X I A；GM＝A B G A B P A 無 X/I），面命中是結構性 CM 證據，
與 M 同級。衝突象限沿 D3-017 原則逐格重推（見 `classify_seq`）；空詞典行為
不變（X/I 面未登記＝訊號恆無＝舊行為）。
"""
from __future__ import annotations

import re
import time

from .lexicon import LexEntry, build_lexicon, match_all
from .normalization import normalize
from .ports import NLDraftResult, SlotCandidate, SlotSuggestion

# GM/CM 判型關鍵字（v3 治具案例認證）——名詞/片語訊號源
# CM：在「機台」上執行的動作（並壓合機台、進行壓合、執行壓合）
# GM：操作「治具/工具」的一般手工動作
_CM_TRIGGERS = frozenset({"並壓合機台", "並壓合機臺", "進行壓合", "執行壓合", "機台", "機臺"})
_GM_NOUNS = frozenset({"治具", "壓合站", "壓合位置", "壓合夾具", "壓合治具"})


def _noun_seq(norm: str, raw: str) -> str | None:
    """名詞觸發詞判型（v3 認證行為原樣保留）。

    同時檢查 norm（NFKC+OpenCC 後）與原文（防 OpenCC 轉換改變觸發詞）；
    CM 觸發詞優先於 GM 名詞（v3 治具防護：治具+機台→CM）。
    """
    for kw in _CM_TRIGGERS:
        if kw in norm or kw in raw:
            return "CM"
    for kw in _GM_NOUNS:
        if kw in norm or kw in raw:
            return "GM"
    return None


# CM 專屬序列參數（spec §2：CM＝A B G M X I A；GM＝A B G A B P A 無 M/X/I）。
# 三者面命中都是結構性 CM 證據——同一 CM cycle 本來就同時容納 M、X、I，
# 彼此同向不衝突（D3-017 收 M；D3-023 IE 核可開票收 X/I）。
_CM_CORE_PARAMS = frozenset({"M", "X", "I"})


def _verb_seq(params_hit: frozenset[str]) -> str | None:
    """動詞字典訊號（D3-017 判型吃字典＋D3-023 X/I 參與，皆 IE 核可）。

    輸入＝lexicon 命中的 parameter 集合（與 slot 填充**同一次** match_all 的
    結果——判型不另開查詢路徑）。訊號定義：

    - "CM"：M/X/I 任一命中且無 P——三者都是 CM 專屬序列參數
      （CM＝A B G M X I A，`docs/core-logic/minimost-sequence-model-core-logic-spec.md`
      §2；GM 序列無 M/X/I 格）。G 可伴隨（CM 自己有 G 格：「接觸＋推/拉」＝
      IE 已裁的單一 CM；「抓握風槍＋吹風清潔」同構——工具取得與工具製程
      本來就在同一 CM cycle，正式 gold g13 即此型）。M/X/I 彼此同向：
      「鎖附＋確認」（X＋I）仍是單一 CM 訊號，不是混合。
    - "GM"：G 與 P 同時命中且無 M/X/I——IE 核可的 GM 訊號（GM＝G＋P 同 cycle）。
    - "mixed"：M/X/I 與 P 同時命中——跨模型混合（M/X/I 只存在 CM、P 只存在
      GM，不可能同 cycle）＝「≥2 個 cycle」的證據（「鎖附後放至」型與 M+P 的
      「去除＋放置」型同構），單 action 判型必棄權。
    - None：G 單獨或 P 單獨或無命中——單一動詞不足以定序列模型
      （G 兩型皆有；P 單獨可能是多動作句的殘片），寧可不給訊號、
      交回名詞判（不硬判）。
    """
    has_cm_core = bool(_CM_CORE_PARAMS & params_hit)
    has_p = "P" in params_hit
    has_g = "G" in params_hit
    if has_cm_core and has_p:
        return "mixed"
    if has_cm_core:
        return "CM"
    if has_g and has_p:
        return "GM"
    return None


def classify_seq(norm: str, raw: str, params_hit: frozenset[str]) -> str | None:
    """GM/CM 判型：名詞觸發詞 × 動詞字典訊號的衝突矩陣（D3-017＋D3-023）。

    動詞欄的 CM 訊號自 D3-023 起含三個來源：M、X、I（皆 CM 專屬序列參數，
    見 `_verb_seq`）；矩陣本身不因訊號來源分欄——同一格的裁決理由對三者
    成立（逐來源論證見下）。

    ::

        noun\\verb │ None │  GM  │  CM  │ mixed
        ──────────┼──────┼──────┼──────┼──────
           None   │ None │  GM  │  CM  │ None
           GM     │  GM  │  GM  │ CM※1 │ None
           CM     │  CM  │None※2│  CM  │ None

    衝突優先序與理由：

    - ※1 名詞 GM × 動詞 CM → **CM**（動詞勝）：
      （M 來源，D3-017 IE 已裁）「接觸＋推/拉」是單一 CM（d019「接觸治具
      拉至定位」型——名詞觸發誤判 GM、動詞 m_pull 才對）。
      （X/I 來源，D3-023 沿同一論證）「鎖附治具」＝對治具做工具製程——
      治具/夾具名詞只是「操作對象」證據，不排除對它做工具製程或檢驗；
      X/I 與 M 一樣是「序列參數」證據（只存在 CM，直接對應序列模型）。
      佐證：IE 登記「鎖附→x_screw_fix」的裁決情境即電動起子工具製程
      （D3-021 答案②），工具製程讀法是 IE 認可的主讀法。
      **佐證的情境限縮（誠實記錄）**：D3-021 答②原文是**條件式裁決**——
      「鎖附→X」限電動起子情境，**手動鎖附遇到再議**；本矩陣讓「鎖附」在
      **所有情境**給 CM 訊號，語料 9 筆判型解鎖中 4 筆句面無電動起子脈絡
      （「鎖附螺絲」型），落在「再議」區、超出裁決字面。現況兩道擋（判型
      不外溢成錯值）：①判型變更旗（typing_changed_by_verb_lexicon）未經
      IE 確認即擋轉正；②X 面不由 linker 掛值（per-action linking 只掛
      core M——判型解鎖≠x_screw_fix 落 cycle）。「手動鎖附是否同判 CM」
      已列下輪快答（docs/llm/gold-review/README.md）。
      **這不是全域「動詞壓名詞」**，見 ※2。
    - ※2 名詞 CM × 動詞 GM → **None**（棄權）：無 IE 裁決。機台語境的
      G+P（「放至機台…」）很可能是「上料（GM）＋機台製程（CM/X）」兩個
      action——硬判任一型都有一半機率錯，維持 composite_unknown 交 IE。
      （行為變更點：舊行為此象限由名詞判 CM；動詞證據出現後誠實降級。）
    - mixed（M/X/I＋P 同句）→ **None**（棄權，蓋過名詞）：跨模型混合＝
      多 cycle 證據——M 型如「拿取主板,去除包裝袋,將主板放置工作台」
      （M 去除＋P 放置）、X/I 型如「鎖附後放至」（X 鎖附＋P 放至），
      單 action 判成任何一型都是把多動作硬塞一格。**注意 X/I＋G 不是混合**
      ——G 在兩序列都有、CM 自有 G 格（「抓握風槍＋清潔」＝單一 CM，g13）。
    - 動詞無訊號 → 名詞判（既有 v3 認證行為原樣保留，含空詞典路徑：
      X/I 面未登記時行為＝舊版）。

    邊界假設（誠實記錄）：動詞命中取自 lexicon 對 norm 的最長匹配，未做
    「名詞內幽靈命中」排除（scripts/gold_harvest.py `_VERB_COMPOUND_NOUNS`
    是語料統計端的啟發式，判型這裡沒有）。曝險不是未來式——**已登記的
    「清潔」「確認」本身就是常見名詞前綴**（清潔布/清潔劑/確認單），判型
    會被名詞內命中擊穿：「拿取清潔布放至工作台」命中 G＋X＋P → mixed
    棄權（D3-023 複審實測 5 句同型）。現況風險落點：現行語料 0 筆命中；
    實測的「取＋名詞前綴＋放」型落點是**棄權進 IE 佇列**（fail-closed，
    不產出錯型錯值——但這是句型的僥倖，不是機制保證：無 P 動詞的變形句
    仍可能被擊穿成 typed CM）。
    **登記新動詞面（如「壓合」——會內嵌於設備名）或語料換血時須複驗本
    假設**（D3-018 M3 記票：幽靈命中排除是「壓合」登記動作的前置條件）。
    """
    verb = _verb_seq(params_hit)
    if verb == "mixed":
        return None
    noun = _noun_seq(norm, raw)
    if verb is None:
        return noun
    if noun is None or noun == verb:
        return verb
    if noun == "GM" and verb == "CM":
        return "CM"
    # noun == "CM" and verb == "GM"
    return None


# 距離數值 regex（context 抽取用）
_DIST_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:cm|公分|mm|毫米|吋|英寸|inch)")

# GM 序列 slot 定義（param, field_name, slot_index）
# 第二/三個 A 視為 GM 序列中的重複 A slot
_SLOT_PARAMS = [
    ("A", "a_code",       0),
    ("B", "b_code",       1),
    ("G", "g_code",       2),
    ("A", "a_code2",      3),
    ("B", "b_code2",      4),
    ("P", "p_base_code",  5),
    ("A", "a_code3",      6),
]


class RuleBasedParser:
    """字典驅動最長匹配 NL draft parser（第一版 adapter）。"""

    VERSION = "rule_based_v1"

    def __init__(self, synonyms: list[dict]) -> None:
        self._lexicon = build_lexicon(synonyms)

    def parse(self, text: str, rule_set_code: str = "") -> NLDraftResult:
        t0 = time.perf_counter()
        norm = normalize(text)

        # ── 最長匹配（slot 填充與判型共用同一次掃描；不另開查詢路徑）──────
        matches = match_all(norm, self._lexicon)

        # ── GM/CM 判型（名詞觸發詞 × 動詞字典訊號；衝突矩陣見 classify_seq）──
        params_hit = frozenset(entry.parameter for _, _, entry in matches)
        seq = classify_seq(norm, text, params_hit)

        # ── context 抽取 ─────────────────────────────────────────────────
        context: dict = {"hand": None, "object": None, "from": None, "to": None}
        dist_m = _DIST_RE.search(norm)
        if dist_m:
            context["reach_cm"] = float(dist_m.group(1))

        # 按 parameter 分組，保持匹配出現順序
        by_param: dict[str, list[LexEntry]] = {}
        for _, _, entry in matches:
            by_param.setdefault(entry.parameter, []).append(entry)

        # ── 組成 SlotSuggestion ──────────────────────────────────────────
        # 每個 slot 依 parameter 消耗一個候選（同 parameter 的第 N 個 slot 取第 N 個命中）
        slots: list[SlotSuggestion] = []
        seen_param_idx: dict[str, int] = {}

        for param, field_name, idx in _SLOT_PARAMS:
            candidates_raw = by_param.get(param, [])
            used = seen_param_idx.get(param, 0)

            if used < len(candidates_raw):
                entry = candidates_raw[used]
                seen_param_idx[param] = used + 1
                chosen = SlotCandidate(
                    option_code=entry.option_code,
                    score=entry.score,
                    source=entry.source,
                )
                top_k = [chosen]
            else:
                chosen = None
                top_k = []
                seen_param_idx[param] = used + 1

            needs_review = chosen is None or chosen.score < 0.7
            # TODO(P5): cross-param ambiguity (top_k≥2) requires multi-assignment match_all — deferred to Stage 2

            slots.append(
                SlotSuggestion(
                    slot_index=idx,
                    field=field_name,
                    chosen=chosen,
                    top_k=top_k,
                    needs_review=needs_review,
                )
            )

        filled = sum(1 for s in slots if s.chosen is not None)
        overall_conf = filled / len(slots) if slots else 0.0

        return NLDraftResult(
            raw_text=text,
            normalized_text=norm,
            suggested_seq=seq,
            context=context,
            slots=slots,
            overall_confidence=overall_conf,
            provenance={
                "parser": self.VERSION,
                "rule_set_code": rule_set_code,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
