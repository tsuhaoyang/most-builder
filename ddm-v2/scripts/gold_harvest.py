#!/usr/bin/env python3
"""gold_harvest.py — WI gold set 擴充的預標註管線（唯讀 DB）。

目標：把 IE 的工作從「從零標 50 筆」降到「覆核 50 筆預標註」
（`docs/architecture/wi-ai-parser-system-spec.md` §19 P0 退出條件：IE 核准 ≥50 筆真實案例）。

做什麼：
1. 從 dev DB 撈全部真實 WI 描述文字（wi_rows.sub_activity、
   motion_module_versions.rows[*].sub_activity、motion_modules.name_zh、
   motion_templates.name_zh），正規化去重、標注來源與挑戰維度
   （`docs/architecture/wi-ai-parser-system-spec.md` §14.3 的 16 維度；
   規則式只判得動其中 9 個，其餘每筆標 "unknown"，缺口在報告點名）。
2. 多樣性選擇（greedy max-coverage，非取前 N 筆）。
3. 對每筆候選跑**現行 rule pipeline**（RuleBasedParser → plan → SlotLinker(no-DB)
   → compile → engine_gate → routing；TMU 唯一出處＝most_engine），把結果寫成
   **草稿 gold JSON**（wi-gold-v1 相容；`approved_by: null`、
   `review_status: "pending_ie"`）放進 `tests/gold/wi_plans_draft/`。
4. 產出 IE 覆核表（markdown，每筆一節、附具體問題）與 harvest 摘要。

草稿不是 gold：
- 評測（`scripts/wi_ai_eval.py`、`nlp/gold_eval.py`）只掃 `tests/gold/wi_plans/*.json`
  （glob 不遞迴），草稿目錄是 sibling，結構上掃不到；隔離守門在
  `tests/unit/test_gold_draft_isolation.py`。
- 本腳本**拒絕**把輸出寫進 `tests/gold/wi_plans/`（目錄名守衛）。

誠實旗標（寫在每一筆草稿上，不是只寫在文件裡）：
- 每筆草稿標 `plan_origin: "rule_based_v1_preannotation"`——草稿的 plan 就是
  rule planner 的輸出；IE 未修改即轉正（`ie_modified: false`）的案例會被
  planner 段的 Plan 層指標排除（自我指涉；見 `nlp/planner_eval.py`）。
- rule planner 結構上永遠單 action——凡命中多動作啟發式的候選，草稿標
  `preannotation_caveat: ["likely_multi_action_undercounted", ...]`。
  例外一：恰好「取＋放」兩動詞且無連接詞不算 multi_action（MiniMOST 的 GM 本來
  就是 G＋P 同 cycle），改標中性旗標 `take_place_pair_may_be_single_gm`，
  IE 裁決建單一 GM 或兩個 action——不預設低估方向。
  例外二：恰好「取/觸＋推/拉」兩動詞且無連接詞同理（CM 序列的 G 與 M 同一
  cycle：`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2，
  CM＝A B G M X I A），改標中性旗標 `take_move_pair_may_be_single_cm`。
- v3 結構回填（D3-014 裁決 3）：帶上述三種切分旗標的草稿附
  `v3_structure_hint`＋`v3_structure_evidence`——v3 遷移資料是 IE 驗證過並
  提供的生產資料，其結構（module/cycle 邊界）就是 IE 的切分裁決，據此把
  「取＋放怎麼建」從開放題改成確認題（預設依 v3 結構）。誠實邊界：hint 是
  **證據不是判決**——IE 可推翻，且絕不寫進 `expected.*`。
- 「取必有放」lint（D3-014 裁決 2）：plan 含 acquire 而其後同 plan 內無收尾
  （move_place／release_return／controlled_move）→ 標 `acquire_without_place`。
  WARN 不 BLOCK：單句 acquire 可能合法（放在下一句/下一列，如 gold g01），
  所以只在**同 plan 內**判；判定用 action_type 序列，不用文字啟發式。
- dev DB 的 `rule_option_synonyms` 若為空，slot 全部無候選，草稿標
  `empty_lexicon_no_slot_candidates`。
- complete 但 TMU=0.0（距離未述＝0cm 的引擎口徑輸出）標
  `zero_tmu_distance_unstated`（D3-018 M1）：TMU=0.0 非真值，覆核表逐筆問
  「補距離或判定句子資訊不足」；原樣轉正撞空殼守門（total_tmu > 0）。
- 「清潔→x_blow_clean」是情境條件裁決（D3-021：IE 只裁吹風情境）——lexicon
  配出此映射而句面無風槍/吹風脈絡時標 `x_clean_context_unverified`，
  不無條件套用（轉正 fail-closed）。
- 9 個可判維度的 `false` 同為啟發式輸出（quantity/tool/simo 的漏標已有實證，
  如「多顆」無數字不命中 quantity）——每筆草稿標 `heuristic_tags_unverified`
  點名這幾維，IE 覆核時 true/false 都要確認。

決定性：同一 DB 跑兩次輸出 byte-identical（SQL ORDER BY＋Python 穩定排序、
sha256 命名、輸出不含任何 timestamp）。守門在
`tests/integration/test_gold_harvest.py`。

IE 覆核狀態的存活（D3-015）：out 目錄的 `review-state.json`（IE 的檔案，
harvest 只讀不寫、`--force` 不刪）記錄切分維度的確認/裁決，重產時以
normalized_text 的 sha256 前 8 碼配對合併回草稿的 `ie_review` 區塊；文字或
v3 結構證據變了的 entry 標 stale 列入摘要，**不靜默套用**。stale 筆在覆核表
該節印 banner（**先前裁決的內容印出來**，不是只給指標——否則 IE 會被確認題
的預設值引導推翻自己先前的裁決；D3-023 複審必修 1），合併語意不變。詳見檔內
「IE 覆核狀態」節與 `docs/llm/gold-review/README.md`。

用法（於 ddm-v2/）：
  PYTHONPATH=src .venv/bin/python scripts/gold_harvest.py --out tests/gold/wi_plans_draft/
  # IE 改完草稿 plan 後，用單一引擎重算 expected_cycles/expected（不跑 planner）：
  PYTHONPATH=src .venv/bin/python scripts/gold_harvest.py --recompile tests/gold/wi_plans_draft/dXXX_*.json
  # 正式 gold（tests/gold/wi_plans/）的 expected 是鎖點：預設拒絕 recompile。
  # 引擎/規則變更需重鎖時，顯式核可並留痕（reason 會寫進檔案 notes）：
  PYTHONPATH=src .venv/bin/python scripts/gold_harvest.py \
    --recompile tests/gold/wi_plans/gXX_*.json --relock-approved --reason "..."
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ddm_v2.most_compiler.compile import allow_lists_from_rule_set, compile_plan  # noqa: E402
from ddm_v2.most_compiler.engine_gate import apply_engine_gate  # noqa: E402
from ddm_v2.most_engine.providers import build_from_seed_v2  # noqa: E402
from ddm_v2.nlp.contracts import SourceRef, WorkInstructionPlan  # noqa: E402
from ddm_v2.nlp.gold_eval import (  # noqa: E402
    DEFAULT_RULE_SET_CODE,
    case_rule_set_code,
    evaluate_gold_case,
)
from ddm_v2.nlp.lexicon import build_lexicon, match_all  # noqa: E402
from ddm_v2.nlp.linking import (  # noqa: E402
    P_DEST_MECHANISM,
    P_DEST_SURFACE,
    P_VARIANT_DEFAULT,
    P_VARIANT_SURFACE,
    SlotLinker,
    classify_p_destination,
    x_clean_context_missing,
)

# D3-024：清潔情境守門的單一出處搬進 nlp.linking——常數原名再匯出
# （tests 與既有引用不變；判定函式 x_clean_context_missing 同上方 import）
from ddm_v2.nlp.linking import X_CLEAN_CONTEXT_TERMS as X_CLEAN_CONTEXT_TERMS  # noqa: E402
from ddm_v2.nlp.linking import X_CLEAN_OPTION_CODE as X_CLEAN_OPTION_CODE  # noqa: E402
from ddm_v2.nlp.linking import X_CLEAN_SYNONYM_NORM as X_CLEAN_SYNONYM_NORM  # noqa: E402
from ddm_v2.nlp.normalization import normalize  # noqa: E402
from ddm_v2.nlp.planner_eval import (  # noqa: E402
    RULE_PLANNER_NAME,
    evaluate_planner_case,
    planner_preannotation_origin,
    rule_based_plan,
)
from ddm_v2.nlp.routing import compute_routing  # noqa: E402
from ddm_v2.nlp.rule_based import RuleBasedParser, _verb_seq, classify_seq  # noqa: E402
from ddm_v2.nlp.rule_plan_adapter import plan_from_rule_result  # noqa: E402

GOLD_SCHEMA_VERSION = "wi-gold-v1"
DEFAULT_LIMIT = 60
# 草稿 notes 的管線樣板（preannotate 寫入；promoted_case_payload 據此判斷
# 「IE 有沒有在 notes 留過內容」——樣板照抄＝無內容，轉正時以轉正註記取代；
# IE 寫過的 notes（如 D3-022 重切的涵蓋對應）轉正時保留並附加轉正註記）
DRAFT_NOTES_BOILERPLATE = (
    "預標註草稿（rule pipeline 自動產生；scripts/gold_harvest.py）。"
    "非 gold——IE 覆核核准前不得移入 tests/gold/wi_plans/。"
)
# 草稿 plan 的出處標記（planner 段評測據此排除自我指涉案例；見 nlp/planner_eval.py）
PLAN_ORIGIN_PREANNOTATION = planner_preannotation_origin(RULE_PLANNER_NAME)
PIPELINE_DESC = (
    "rule_based_v1 -> plan_from_rule_result -> SlotLinker(no-db) -> "
    "compile_plan -> engine_gate(most_engine) -> compute_routing(auto=off)"
)

# ── 挑戰維度（spec §14.3 的 16 項；detectable=False 者規則式判不動，每筆標 unknown）──
CHALLENGE_DIMS: list[tuple[str, str, bool]] = [
    # 判定＝OpenCC s2twp 會改寫原文（簡體字或大陸用語如「主板→主機板」都算——
    # 兩者都會讓 normalized_text 與原文位移，是同一類挑戰）
    ("zh_simplified_variant", "繁簡（簡體字/大陸用語）", True),
    ("fullwidth_chars", "全形字元", True),
    ("typo", "錯字", False),
    ("homophone", "同音別字", False),
    ("mixed_zh_en", "中英混合", True),
    ("english_only", "純英文", True),
    ("inverted_word_order", "語序顛倒", False),
    ("colloquial", "口語", False),
    ("multi_action", "多 action", True),
    ("quantity", "數量", True),
    ("tool_handling", "工具持有", True),
    ("simo_both_hands", "SIMO／雙手", True),
    ("missing_info", "缺資訊", False),
    ("ambiguity", "歧義", False),
    ("diagram_reference_no_image", "依圖示但無圖片", True),
    ("site_jargon_dirty_import", "不同 site 用語與匯入髒資料", False),
]
DIM_KEYS = [k for k, _, _ in CHALLENGE_DIMS]
DIM_ZH = {k: zh for k, zh, _ in CHALLENGE_DIMS}
DETECTABLE_DIMS = [k for k, _, d in CHALLENGE_DIMS if d]
UNDETECTABLE_DIMS = [k for k, _, d in CHALLENGE_DIMS if not d]

# 多動作啟發式（誠實聲明：這是 attention flag，不是 ground truth；IE 裁決）。
# multi_action = 動詞命中 >= 2（最長優先、位置不重疊、排除名詞內幽靈命中）或含
# 順序連接詞——但兩種「同 cycle 配對」除外，各發中性旗標由 IE 裁決方向：
# 1. 恰好「取＋放」兩動詞且無連接詞：MiniMOST 的 GM 序列本來就是 G＋P 同一
#    cycle → take_place_pair_may_be_single_gm。
# 2. 恰好「取/觸＋推/拉」兩動詞且無連接詞：CM 序列的 G 與 M 同一 cycle
#    （`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2，
#    CM＝A B G M X I A，與 GM 的 G+P 同一論證）→ take_move_pair_may_be_single_cm。
_ACTION_VERBS = [
    "保持住", "按動按鈕",
    "拿取", "拿起", "抓握", "接觸", "放置", "放至", "放入", "放下", "貼上", "貼附",
    "鎖附", "按壓", "下壓", "按下", "按動", "撕除", "掃描", "熱壓", "旋緊", "折合",
    "擦拭", "插入", "去除", "清潔", "確認", "整理", "對準", "掰開", "壓合",
    "推至", "拉至", "丟至", "組至", "組於", "撕開", "鎖付",
]
_CONNECTIVES = ["然後", "接著", "隨後", "並且", "之後再"]
_TOOL_NOUNS = ["電動起子", "起子", "風槍", "治具", "扳手", "夾具", "鑷子", "烙鐵", "電批"]
_DIAGRAM_MARKS = ["依圖", "如圖", "圖示", "見圖", "參圖"]
# 「取/觸」動詞面（GM 與 CM 配對共用的 grasp 面；「接觸」＝G 的接觸取得，
# 與覆核表「取放建模」「取移建模」題同一判定——take_place_pair/take_move_pair
# 是唯一出處，覆核表的題目直接呼叫同一函式）
_TAKE_VERBS = ("拿取", "拿起", "抓握", "接觸")
_PLACE_VERB_PREFIXES = ("放", "組", "丟", "插入", "貼")
# 「推/拉」控制移動動詞面（CM 的 M；take_move_pair 用）
_CTRL_MOVE_VERBS = ("推至", "拉至")
# 動詞面被名詞內動詞擊穿的排除名單：「DIMM壓合治具」的「壓合」不是動詞——
# 動詞命中**緊接**這類設備名詞（動詞＋名詞＝設備名的組合）時排除該命中。
# 名單依語料定，只收設備名：工作台/料架/料盒/垃圾桶**不收**——語料中它們常作
# 真動詞的直接受詞（「放置工作台」「放至料架」「丟至垃圾桶」），收了會反向
# 擊穿真命中。
_VERB_COMPOUND_NOUNS = ("治具", "冶具", "機台", "機臺", "夾具", "模具")

# 啟發式輸出的 false 也未經覆核（quantity 的「多顆」無數字不命中是實證漏標）；
# 這幾維的 false 特別容易被 IE 誤讀成「已確認沒有」——逐筆寫進草稿點名。
HEURISTIC_UNVERIFIED_DIMS = ["quantity", "tool_handling", "simo_both_hands"]

# ── D3-017／D3-023：判型變更標注 + P 方向數旗標 ─────────────────────────────
#
# 判型變更：rule parser 的 GM/CM 判型吃動詞字典（第三輪 D3-017 收 M/G+P；
# 第六輪 D3-023 收 X/I 為 CM 訊號；nlp/rule_based.py classify_seq；衝突矩陣
# 見該 docstring）。與「僅名詞」舊判型（＝classify_seq 傳空詞典）不同者掛
# 本旗標，覆核表標「判型已由動詞字典修正，請確認」——舊/新值存草稿
# `typing_change` 欄。
TYPING_CHANGED_CAVEAT = "typing_changed_by_verb_lexicon"
_ACTION_TYPE_TO_SEQ = {"move_place": "GM", "controlled_move": "CM"}

# P 方向數（IE 裁決 D3-017）：「放至/放置」按賓語情境擇變體——機構件→對準
# （p_place_single，方向數 IE 未指定、預設一種）；盤面→無方向（p_place_none）；
# 判不出→維持預設並交 IE。名詞分類清單的**單一出處**＝nlp/linking.py
# （生產 nl-draft、gold_eval 重放與本腳本同一套；此處只做旗標與提問）。
P_DIRECTION_CAVEATS = {
    P_DEST_MECHANISM: "p_direction_single_default",
    P_DEST_SURFACE: "p_direction_none_by_context",
    # unclassified 與防禦性 None 都落此旗標（判不出＝交 IE 裁決）
    None: "p_direction_unclassified_default_single",
}
P_DIRECTION_CAVEAT_NAMES = frozenset(P_DIRECTION_CAVEATS.values())

# D3-018 M1：TMU=0.0 不是真值——「complete」是結構完成度不是 TMU 可信度。
# 引擎口徑下距離未述＝0cm（M 階梯 0→0）且 G/B 伴隨 slot 不由 linker 掛值
# （CM 的 G、GM 的 G 等不填；X/I 自 D3-024 起面命中掛值，但不改本旗標的
# 成立條件），會產出 complete 且 TMU=0.0 的 cycle。轉正空殼
# 守門（tests/unit/test_gold_draft_isolation.py approved_case_defects）要求
# total_tmu > 0 或顯式 expected_incomplete_reason——原樣轉正會被擋。
# 旗標逐筆掛草稿＋覆核表逐筆提問，不只摘要一句話。
ZERO_TMU_CAVEAT = "zero_tmu_distance_unstated"

# D3-021：「清潔」→ x_blow_clean 是**情境條件裁決**——IE 只裁了吹風情境
# （語料 4 筆全是風槍/吹風），不是無條件映射。同義詞表本身不帶情境（DB 映射
# 是全域的），情境守門仿 p_direction 情境規則模式：句面無風槍/吹風脈絡而
# lexicon 仍配出「清潔→x_blow_clean」時掛旗標交 IE，**不無條件套用**——該
# 旗標無確認機制（IE 未裁非吹風情境），轉正 fail-closed 擋下。
# D3-024 起判定的單一出處搬到 `src/ddm_v2/nlp/linking.py`（linker 掛 X 格時
# 同一守門：掛值照掛但 needs_review）——本檔 import 共用，常數與函式名保留
# 原名再匯出（旗標／schema 5i／轉正擋的語意不變）。
X_CLEAN_CONTEXT_CAVEAT = "x_clean_context_unverified"


def has_zero_tmu_complete_cycle(expected_cycles: list[dict[str, Any]]) -> bool:
    """任一 complete 期望 cycle 的 total_tmu == 0？（D3-018 M1 單一出處：
    preannotate 的旗標、schema 守門（test_gold_draft_schema 5g）、summary
    統計共用本函式——不允許三邊條件漂移。）"""
    return any(
        ec.get("complete") and ec.get("total_tmu") == 0 for ec in expected_cycles
    )


try:
    import opencc as _opencc_mod

    _S2TWP = _opencc_mod.OpenCC("s2twp")
except Exception as exc:  # pragma: no cover — opencc 是宣告的 runtime dependency
    raise RuntimeError(f"opencc initialization failed: {exc}") from exc


def _longest_first_hits_pos(text: str, terms: list[str]) -> list[tuple[int, str]]:
    """最長優先、位置不重疊的詞面命中（與 nlp.lexicon.match_all 同精神的輕量版），
    回傳 (起始位置, 詞面)。"""
    hits: list[tuple[int, str]] = []
    covered: set[int] = set()
    for term in sorted(set(terms), key=lambda t: (len(t), t), reverse=True):
        pos = 0
        while True:
            idx = text.find(term, pos)
            if idx == -1:
                break
            span = set(range(idx, idx + len(term)))
            if not span & covered:
                hits.append((idx, term))
                covered |= span
            pos = idx + 1
    hits.sort()
    return hits


def _longest_first_hits(text: str, terms: list[str]) -> list[str]:
    return [t for _, t in _longest_first_hits_pos(text, terms)]


def _action_verb_hits(text: str) -> list[str]:
    """動詞面命中，排除名詞內幽靈命中（命中後緊接設備名詞者，如「壓合治具」的
    「壓合」）。

    take_place_pair / take_move_pair / detect_challenge_tags / 覆核表的配對題
    全部共用本函式——單一判定，不允許兩邊條件漂移。"""
    return [
        term
        for idx, term in _longest_first_hits_pos(text, _ACTION_VERBS)
        if not text[idx + len(term):].startswith(_VERB_COMPOUND_NOUNS)
    ]


def _has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


def _has_ascii_alpha(s: str) -> bool:
    return any(ch.isascii() and ch.isalpha() for ch in s)


def _quantity_present(norm: str) -> bool:
    if re.search(r"[×x]\s*\d+", norm):
        return True
    if re.search(r"\d+\s*[顆個次支條片組粒張]", norm):
        return True
    if re.search(r"[一兩二三四五六七八九十]+\s*[顆個次支條片組粒張]", norm):
        return True
    return False


def _fullwidth_kinds(raw: str) -> tuple[bool, bool]:
    """(全形英數, 全形標點/空白) 分開判定——合著算會讓「3 筆全是全形逗號」被誤讀成
    全形英數已有覆蓋。"""
    has_alnum = False
    has_punct = False
    for ch in raw:
        if "０" <= ch <= "９" or "Ａ" <= ch <= "Ｚ" or "ａ" <= ch <= "ｚ":
            has_alnum = True
        elif "！" <= ch <= "～" or ch == "　":
            has_punct = True
    return has_alnum, has_punct


def take_place_pair(norm: str) -> bool:
    """恰好「取＋放」兩動詞且無順序連接詞——GM 本來就是 G＋P 同 cycle，
    不算 multi_action；發 take_place_pair_may_be_single_gm 中性旗標由 IE 裁決。"""
    if any(c in norm for c in _CONNECTIVES):
        return False
    verb_hits = _action_verb_hits(norm)
    if len(verb_hits) != 2:
        return False
    takes = [v for v in verb_hits if v in _TAKE_VERBS]
    places = [v for v in verb_hits if v.startswith(_PLACE_VERB_PREFIXES)]
    return len(takes) == 1 and len(places) == 1


def take_move_pair(norm: str) -> bool:
    """恰好「取/觸＋推/拉」兩動詞且無順序連接詞——CM 序列的 G 與 M 本來就在
    同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：
    CM＝A B G M X I A，與 GM 的 G+P 同一論證），不算 multi_action；
    發 take_move_pair_may_be_single_cm 中性旗標由 IE 裁決。"""
    if any(c in norm for c in _CONNECTIVES):
        return False
    verb_hits = _action_verb_hits(norm)
    if len(verb_hits) != 2:
        return False
    takes = [v for v in verb_hits if v in _TAKE_VERBS]
    moves = [v for v in verb_hits if v in _CTRL_MOVE_VERBS]
    return len(takes) == 1 and len(moves) == 1


def detect_challenge_tags(raw: str, norm: str) -> dict[str, Any]:
    """16 維度標注：規則式可判的回 bool，判不動的回 "unknown"（不硬湊）。"""
    verb_hits = _action_verb_hits(norm)
    tags: dict[str, Any] = {}
    for key in DIM_KEYS:
        tags[key] = "unknown"
    fw_alnum, fw_punct = _fullwidth_kinds(raw)
    tags["zh_simplified_variant"] = _S2TWP.convert(raw) != raw
    tags["fullwidth_chars"] = fw_alnum or fw_punct
    tags["mixed_zh_en"] = _has_cjk(raw) and _has_ascii_alpha(raw)
    tags["english_only"] = _has_ascii_alpha(raw) and not _has_cjk(raw)
    tags["multi_action"] = (
        (len(verb_hits) >= 2 or any(c in norm for c in _CONNECTIVES))
        and not take_place_pair(norm)
        and not take_move_pair(norm)
    )
    tags["quantity"] = _quantity_present(norm)
    tags["tool_handling"] = bool(_longest_first_hits(norm, _TOOL_NOUNS))
    tags["simo_both_hands"] = (
        "雙手" in norm or "兩手" in norm or ("左手" in norm and "右手" in norm)
    )
    tags["diagram_reference_no_image"] = any(m in norm for m in _DIAGRAM_MARKS)
    return tags


# ── 「取必有放」lint（D3-014 裁決 2）────────────────────────────────────────

# acquire 的收尾 action 類型（消耗掉「取」的抓握者）：
# - move_place／release_return：字面上的「放」。
# - controlled_move：CM 序列**沒有 P 參數**（A B G M X I A；
#   `docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2）——推/拉到
#   定位即完成取的閉合。且裁決 1 明言 acquire＋controlled_move 兩個 action 是
#   合法建模，把它標成「取而無放」會跟裁決 1 打架。
# - composite_unknown **不算**收尾：判不出型的 action 不能拿來宣稱「有放」。
_ACQUIRE_CLOSER_TYPES = ("move_place", "release_return", "controlled_move")


def acquire_without_place(actions: list[dict]) -> bool:
    """plan 內「取而無放」lint（裁決 2：取最後一定有放）。

    判定用 plan 的 action_type 序列（依 sequence_order），**不用文字啟發式**——
    R1 的教訓：動詞面會被名詞擊穿。任何 acquire 之後（同 plan 內）沒有收尾
    action（`_ACQUIRE_CLOSER_TYPES`）即命中。

    旗標語意＝WARN 標給 IE，不是 BLOCK：只在**同 plan 內**判——單句 acquire
    可能合法（「放」在下一句/下一列的 plan 裡，正式 gold g01「拿起DIMM」即此型），
    所以問題是「這句的放在哪？被截斷了還是描述缺漏？」，不是「本句必錯」。

    preannotate（發旗標）、`_questions_for`（覆核表提問）、schema 守門測試
    共用本函式——單一判定，不允許條件漂移。"""
    ordered = sorted(actions, key=lambda a: (a.get("sequence_order") or 0))
    for i, a in enumerate(ordered):
        if a.get("action_type") != "acquire":
            continue
        if not any(b.get("action_type") in _ACQUIRE_CLOSER_TYPES for b in ordered[i + 1:]):
            return True
    return False


# ── 來源採集（唯讀）─────────────────────────────────────────────────────────


@dataclass
class SourceRecord:
    priority: int          # representative raw 的挑選優先序（小者優先）
    table: str
    row_id: str
    detail: str | None     # e.g. "rows[3].sub_activity"
    group_key: str         # leakage group（同 group 必須同 split）
    timestamp: str | None  # DB 時間戳（ISO；注意：v3 遷移資料是遷移時間，非原著作時間）
    raw: str

    def provenance(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "id": self.row_id,
            "detail": self.detail,
            "group_key": self.group_key,
            "db_timestamp": self.timestamp,
            "raw_text": self.raw,
        }


@dataclass
class Candidate:
    norm: str
    raw: str
    sources: list[SourceRecord] = field(default_factory=list)
    tags: dict[str, Any] = field(default_factory=dict)

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.norm.encode("utf-8")).hexdigest()

    @property
    def split_groups(self) -> list[str]:
        return sorted({s.group_key for s in self.sources})


# ── v3 結構回填（D3-014 裁決 3 → 裁決 1 的逐案化）───────────────────────────
#
# 來源單位的「cycle 容器」語意（2026-08-16 查證於 src/ddm_v2/models/v2 與
# scripts/migrate_v3_user_data.py）：
# - `wi_rows` 一列 ↔ 至多一個 MostCycle（most_cycles.wi_row_id UNIQUE）＝一個
#   cycle 容器；但 v3 搬遷**不寫 wi_rows**（只寫 motion_modules／versions／
#   WI Set／vocab）——此表的列不是 v3 遷移資料，不餵 hint。
# - `motion_module_versions.rows[]` 一列＝一個 cycle（rows[*].cycle 為單一
#   CycleIn）；一個 module 幾列＝IE 把這段話切成幾個 cycle。
# - `motion_modules.name_zh` 對應其發布版（current_version）的 rows 列數；
#   無發布版（current_version=0）＝結構訊號缺失。
# - `motion_templates.cycle_template`＝單一 CycleIn＝一個 cycle；本表由
#   dev_seed_templates.py 種入、v3 搬遷不寫——同樣不餵 hint。
#
# 證據力定位（裁決 3）：v3 遷移資料（keywords 帶 'v3-import' 的 module 及其
# 版本列）是 IE 驗證過並提供的生產資料——**結構（module/cycle 邊界）就是 IE
# 的切分裁決**，不只文字。誠實邊界：hint 是**證據不是判決**——覆核表預設依
# v3 結構、IE 可推翻；hint 絕不寫進 `expected.*`（守門在
# tests/unit/test_gold_draft_schema.py）。

STRUCTURE_HINT_SINGLE = "single_cycle"
STRUCTURE_HINT_AMBIGUOUS = "ambiguous"
_V3_IMPORT_KEYWORD = "v3-import"
# 帶這三種切分旗標的草稿才回填（配對題／切分題的裁決對象）；其餘草稿無切分
# 爭點，不加欄位（scope 守門在 schema 測試）
SEGMENTATION_CAVEATS = (
    "likely_multi_action_undercounted",
    "take_place_pair_may_be_single_gm",
    "take_move_pair_may_be_single_cm",
)


def structure_hint_multi(n: int) -> str:
    return f"multi_cycle_{n}"


def _module_id_from_group_key(group_key: str) -> str | None:
    prefix = "module:"
    return group_key[len(prefix):] if group_key.startswith(prefix) else None


def _structure_evidence_for_source(
    rec: SourceRecord, module_structure: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """單一來源的結構證據：{table, id, detail, cycles, v3_migrated, basis}。

    `cycles=None`＝該來源給不出 cycle 數（如 module 無發布版）；
    `v3_migrated=False` 的來源**不餵 hint**（結構語意仍成立，但不是 IE 的
    v3 裁決——wi_rows 在本 DB 是 dev seed，motion_templates 是 seed 腳本）。"""
    if rec.table == "motion_module_versions":
        module_id = _module_id_from_group_key(rec.group_key)
        info = module_structure.get(module_id or "", {})
        return {
            "table": rec.table,
            "id": rec.row_id,
            "detail": rec.detail,
            "cycles": 1,
            "v3_migrated": bool(info.get("v3_import")),
            "basis": "版本 rows[] 一列＝一個 cycle（rows[*].cycle 為單一 CycleIn）",
        }
    if rec.table == "motion_modules":
        info = module_structure.get(rec.row_id, {})
        n = info.get("n_rows")
        if n is None:
            basis = "module 無發布版（current_version=0）——結構訊號缺失"
        else:
            basis = (
                f"module 名稱句對應發布版 v{info.get('current_version')} 共 {n} 列"
                f"＝IE 把這段話切成 {n} 個 cycle"
            )
        return {
            "table": rec.table,
            "id": rec.row_id,
            "detail": rec.detail,
            "cycles": n,
            "v3_migrated": bool(info.get("v3_import")),
            "basis": basis,
        }
    if rec.table == "wi_rows":
        return {
            "table": rec.table,
            "id": rec.row_id,
            "detail": rec.detail,
            "cycles": 1,
            "v3_migrated": False,
            "basis": (
                "wi_rows 一列＝一個 cycle 容器（most_cycles.wi_row_id UNIQUE）；"
                "但 v3 搬遷不寫 wi_rows——非 v3 遷移資料，不餵 hint"
            ),
        }
    # motion_templates
    return {
        "table": rec.table,
        "id": rec.row_id,
        "detail": rec.detail,
        "cycles": 1,
        "v3_migrated": False,
        "basis": (
            "cycle_template＝單一 CycleIn＝一個 cycle；但本表為 seed 腳本種入、"
            "v3 搬遷不寫——非 v3 遷移資料，不餵 hint"
        ),
    }


def v3_structure_backfill(
    cand: Candidate, module_structure: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    """該候選的 v3 結構 hint 與證據。

    決策規則（單一出處；schema 測試對 repo 草稿重驗同一不變式）：
    - v3 來源（v3_migrated=True 且 cycles 已知）全數同 n → n==1 ⇒ single_cycle、
      n>1 ⇒ multi_cycle_n。
    - v3 來源彼此矛盾（同句出現在不同結構的多個來源）⇒ ambiguous
      （reason=conflicting_v3_structures，矛盾證據全列）。
    - 無任何 v3 結構訊號（來源全非 v3、或 module 無發布版）⇒ ambiguous
      （reason=no_v3_structure_signal）。"""
    sources = [_structure_evidence_for_source(s, module_structure) for s in cand.sources]
    v3_counts = sorted({
        e["cycles"] for e in sources if e["v3_migrated"] and e["cycles"] is not None
    })
    reason: str | None = None
    if not v3_counts:
        hint = STRUCTURE_HINT_AMBIGUOUS
        reason = "no_v3_structure_signal"
    elif len(v3_counts) > 1:
        hint = STRUCTURE_HINT_AMBIGUOUS
        reason = "conflicting_v3_structures"
    else:
        hint = STRUCTURE_HINT_SINGLE if v3_counts[0] == 1 else structure_hint_multi(v3_counts[0])
    evidence: dict[str, Any] = {
        "note": (
            "hint 是證據不是判決：來源＝IE 驗證過的 v3 生產資料的結構"
            "（module/cycle 邊界）；覆核表預設依 v3 結構、IE 可推翻；"
            "本欄位絕不寫進 expected.*"
        ),
        "sources": sources,
    }
    if reason is not None:
        evidence["reason"] = reason
    return hint, evidence


async def fetch_source_records(database_url: str) -> tuple[list[SourceRecord], dict[str, int]]:
    """撈四個來源表的原文（SELECT-only；不開 transaction 寫入路徑）。"""
    from sqlalchemy import text as sql_text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(database_url, poolclass=NullPool)
    records: list[SourceRecord] = []
    counts: dict[str, int] = {}
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    sql_text(
                        "SELECT mm.id::text AS id, mm.name_zh, mm.category, mm.created_at "
                        "FROM motion_modules mm "
                        "WHERE COALESCE(btrim(mm.name_zh), '') <> '' ORDER BY mm.id"
                    )
                )
            ).all()
            counts["motion_modules"] = len(rows)
            for r in rows:
                # wi-template 名稱＝v3 遷移的完整 WI 語句（優先當 representative）
                prio = 1 if r.category == "wi-template" else 4
                records.append(
                    SourceRecord(
                        priority=prio,
                        table="motion_modules",
                        row_id=r.id,
                        detail=f"name_zh (category={r.category})",
                        group_key=f"module:{r.id}",
                        timestamp=r.created_at.isoformat() if r.created_at else None,
                        raw=r.name_zh,
                    )
                )

            # v3 結構回填素材：module → (category, v3-import?, 發布版列數)。
            # LEFT JOIN：無發布版（current_version=0）的 module 也要進表——
            # n_rows=None＝結構訊號缺失，不是「沒這個 module」。
            struct_rows = (
                await conn.execute(
                    sql_text(
                        "SELECT mm.id::text AS id, mm.category, "
                        "       (mm.keywords @> ARRAY[:kw]::text[]) AS v3_import, "
                        "       mm.current_version, "
                        "       jsonb_array_length(v.rows) AS n_rows "
                        "FROM motion_modules mm "
                        "LEFT JOIN motion_module_versions v "
                        "  ON v.module_id = mm.id AND v.version_no = mm.current_version "
                        "ORDER BY mm.id"
                    ),
                    {"kw": _V3_IMPORT_KEYWORD},
                )
            ).all()
            _MODULE_STRUCTURE_HOLDER["rows"] = {
                r.id: {
                    "category": r.category,
                    "v3_import": bool(r.v3_import),
                    "current_version": r.current_version,
                    "n_rows": r.n_rows,
                }
                for r in struct_rows
            }

            rows = (
                await conn.execute(
                    sql_text(
                        "SELECT v.id::text AS version_id, v.module_id::text AS module_id, "
                        "       v.published_at, ord.idx - 1 AS row_index, "
                        "       ord.elem->>'sub_activity' AS txt "
                        "FROM motion_module_versions v "
                        "CROSS JOIN LATERAL jsonb_array_elements(v.rows) "
                        "     WITH ORDINALITY AS ord(elem, idx) "
                        "WHERE COALESCE(btrim(ord.elem->>'sub_activity'), '') <> '' "
                        "ORDER BY v.id, ord.idx"
                    )
                )
            ).all()
            counts["motion_module_versions.rows[]"] = len(rows)
            for r in rows:
                records.append(
                    SourceRecord(
                        priority=3,
                        table="motion_module_versions",
                        row_id=r.version_id,
                        detail=f"rows[{r.row_index}].sub_activity",
                        group_key=f"module:{r.module_id}",
                        timestamp=r.published_at.isoformat() if r.published_at else None,
                        raw=r.txt,
                    )
                )

            rows = (
                await conn.execute(
                    sql_text(
                        "SELECT w.id::text AS id, w.worksheet_id::text AS worksheet_id, "
                        "       w.sub_activity, w.created_at "
                        "FROM wi_rows w "
                        "WHERE w.sub_activity IS NOT NULL AND btrim(w.sub_activity) <> '' "
                        "ORDER BY w.id"
                    )
                )
            ).all()
            counts["wi_rows"] = len(rows)
            for r in rows:
                records.append(
                    SourceRecord(
                        priority=2,
                        table="wi_rows",
                        row_id=r.id,
                        detail="sub_activity",
                        group_key=f"worksheet:{r.worksheet_id}",
                        timestamp=r.created_at.isoformat() if r.created_at else None,
                        raw=r.sub_activity,
                    )
                )

            rows = (
                await conn.execute(
                    sql_text(
                        "SELECT t.id::text AS id, t.name_zh, t.created_at "
                        "FROM motion_templates t "
                        "WHERE COALESCE(btrim(t.name_zh), '') <> '' ORDER BY t.id"
                    )
                )
            ).all()
            counts["motion_templates"] = len(rows)
            for r in rows:
                records.append(
                    SourceRecord(
                        priority=5,
                        table="motion_templates",
                        row_id=r.id,
                        detail="name_zh",
                        group_key=f"template:{r.id}",
                        timestamp=r.created_at.isoformat() if r.created_at else None,
                        raw=r.name_zh,
                    )
                )

            # --rule-set-code 打錯字與「0 條同義詞」必須可區分：code 不存在就大聲失敗
            code = _RULE_SET_CODE_HOLDER["code"]
            known = [
                r.code
                for r in (
                    await conn.execute(sql_text("SELECT code FROM rule_sets ORDER BY code"))
                ).all()
            ]
            if code not in known:
                raise SystemExit(
                    f"--rule-set-code {code!r} 不存在於 rule_sets（現有：{known or '（無）'}）。"
                    "打錯字不能靜默退化成「詞典 0 條」。"
                )
            syn_rows = (
                await conn.execute(
                    sql_text(
                        # priority＝偏好位次（數字小者優先，0＝預設；D3-017）。
                        # 選擇順序實際由 nlp.lexicon.build_lexicon 的 tie-break 決定，
                        # 此處排序只求輸出決定性且與該語意一致。
                        "SELECT s.parameter, s.option_code, s.synonym_norm, s.priority "
                        "FROM rule_option_synonyms s "
                        "JOIN rule_sets r ON r.id = s.rule_set_id "
                        "WHERE r.code = :code "
                        "ORDER BY s.parameter, s.priority ASC, s.synonym_norm, s.option_code"
                    ),
                    {"code": code},
                )
            ).all()
            _SYNONYMS_HOLDER["rows"] = [
                {
                    "parameter": r.parameter,
                    "option_code": r.option_code,
                    "synonym_norm": r.synonym_norm,
                    "priority": r.priority,
                }
                for r in syn_rows
            ]
    finally:
        await engine.dispose()
    return records, counts


# module-level holders：讓 fetch 一次連線讀完（避免多引擎）；main() 設定
_RULE_SET_CODE_HOLDER: dict[str, str] = {"code": DEFAULT_RULE_SET_CODE}
_SYNONYMS_HOLDER: dict[str, list[dict]] = {"rows": []}
_MODULE_STRUCTURE_HOLDER: dict[str, dict[str, dict[str, Any]]] = {"rows": {}}


def existing_gold_norms(gold_dir: Path | None = None) -> set[str]:
    """正式 gold 目錄既有案例的 normalize(source_text)——已在 gold 的句子不重複進草稿。"""
    root = gold_dir or GOLD_DIR
    norms: set[str] = set()
    for p in sorted(root.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            # 吞掉＝壞檔的 gold 句子會重複進草稿、IE 重工——大聲失敗，修檔再 harvest
            raise SystemExit(f"正式 gold 檔 {p} 不是有效 JSON（{exc}）——修檔後再跑 harvest") from exc
        src = data.get("source_text") or (data.get("plan") or {}).get("source_text")
        if src:
            norms.add(normalize(str(src)))
    return norms


def build_candidates(records: list[SourceRecord]) -> list[Candidate]:
    """正規化去重（key=normalize(raw)）；representative raw 依 (priority, table, id) 決定。"""
    by_norm: dict[str, Candidate] = {}
    ordered = sorted(records, key=lambda r: (r.priority, r.table, r.row_id, r.detail or ""))
    for rec in ordered:
        norm = normalize(rec.raw)
        if not norm:
            continue
        cand = by_norm.get(norm)
        if cand is None:
            cand = Candidate(norm=norm, raw=rec.raw)
            by_norm[norm] = cand
        cand.sources.append(rec)
    out = sorted(by_norm.values(), key=lambda c: c.norm)
    for c in out:
        c.sources.sort(key=lambda r: (r.priority, r.table, r.row_id, r.detail or ""))
        c.tags = detect_challenge_tags(c.raw, c.norm)
    return out


def select_diverse(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Greedy max-coverage：每輪挑「對目前覆蓋最少的維度貢獻最大」者；決定性 tie-break。

    不是取前 N 筆——同維度重複的候選會被排到低覆蓋維度的候選之後。
    """
    coverage: dict[str, int] = {k: 0 for k in DETECTABLE_DIMS}
    remaining = list(candidates)
    selected: list[Candidate] = []
    while remaining and len(selected) < limit:
        def score(c: Candidate) -> float:
            return sum(
                1.0 / (1 + coverage[k]) for k in DETECTABLE_DIMS if c.tags.get(k) is True
            )

        best = max(remaining, key=lambda c: (score(c), c.norm))  # 同分取 norm 較大者（決定性）
        remaining.remove(best)
        selected.append(best)
        for k in DETECTABLE_DIMS:
            if best.tags.get(k) is True:
                coverage[k] += 1
    return selected


def compute_split_components(selected: list[Candidate]) -> dict[str, str]:
    """split_groups 的傳遞閉包（union-find）→ 每個 group_key 對到 component id。

    component id＝該連通分量中字典序最小的 group_key（決定性）。同 component 的
    草稿必須進同一 split——閉包由這裡算好寫進草稿，不讓 IE 手推。
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            # 決定性合併方向：小的當根
            if rb < ra:
                ra, rb = rb, ra
            parent[rb] = ra

    for cand in selected:
        keys = cand.split_groups
        for k in keys:
            parent.setdefault(k, k)
        for k in keys[1:]:
            union(keys[0], k)

    members: dict[str, list[str]] = {}
    for k in parent:
        members.setdefault(find(k), []).append(k)
    out: dict[str, str] = {}
    for group in members.values():
        canon = min(group)
        for k in group:
            out[k] = canon
    return out


# ── 預標註（現行 rule pipeline；TMU 唯一出處＝most_engine）──────────────────


def used_lexicon_entries(norm: str, synonyms: list[dict]) -> list[dict]:
    """該筆實際會用到的 lexicon 條目（planner 的混合詞典掃描 ∪ linker 的逐參數池掃描）。

    目的：核准後的 gold 檔自足（eval 重放不依賴 DB）。子集重放與全字典等價：
    match_all 的位置遮蔽只由「有命中的條目」造成，而有命中者必在子集內。
    """
    used: dict[tuple[str, str, str], dict] = {}

    def _collect(pool: list[dict]) -> None:
        lex = build_lexicon(pool)
        for _s, _e, entry in match_all(norm, lex):
            for s in pool:
                if (
                    s["parameter"] == entry.parameter
                    and s["option_code"] == entry.option_code
                    and s["synonym_norm"] == entry.norm
                ):
                    used[(s["parameter"], s["option_code"], s["synonym_norm"])] = s
                    break

    _collect(synonyms)  # RuleBasedParser 視角：全參數混合詞典
    params = sorted({s["parameter"] for s in synonyms})
    for p in params:  # SlotLinker 視角：逐參數池（無跨參數遮蔽）
        _collect([s for s in synonyms if s["parameter"] == p])

    # 同 (parameter, norm) 的變體整組帶上（v2_0038 一面多 code）：match_all 的
    # 位置覆蓋只讓偏好序第一的變體出現在命中清單，但 P 方向情境規則
    # （nlp.linking）與重放都需要完整變體組——缺了 p_place_none，gold 檔重放
    # 時規則配不出盤面變體，expected 會與 harvest 當下不一致。
    for key in list(used):
        param, _code, norm = key
        for s in synonyms:
            if s["parameter"] == param and s["synonym_norm"] == norm:
                used[(s["parameter"], s["option_code"], s["synonym_norm"])] = s

    return [
        {
            "parameter": s["parameter"],
            "option_code": s["option_code"],
            "synonym_norm": s["synonym_norm"],
            "priority": s["priority"],
        }
        for s in sorted(used.values(), key=lambda x: (x["parameter"], x["synonym_norm"], x["option_code"]))
    ]


def expected_cycle_from_draft(d: Any) -> dict[str, Any]:
    """CycleDraft → gold `expected_cycles[]` 條目（與 gold_eval._check_cycle 形狀相容）。"""
    exp: dict[str, Any] = {"action_id": d.action_id, "complete": bool(d.complete)}
    cyc = d.cycle or {}
    if d.complete:
        exp["seq"] = cyc.get("seq")
        if cyc.get("seq") == "GM":
            exp["g_code"] = (cyc.get("g2") or {}).get("g_code")
            exp["p_base_code"] = (cyc.get("p5") or {}).get("p_base_code")
        else:
            x_code = (cyc.get("x4") or {}).get("x_code")
            i_code = (cyc.get("i5") or {}).get("i_code")
            comps = (cyc.get("m3") or {}).get("m_components") or []
            if x_code is not None:
                exp["x_code"] = x_code
            if i_code is not None:
                exp["i_code"] = i_code
            if comps:
                exp["m_verb"] = comps[0].get("verb_code")
                exp["distance_cm"] = comps[0].get("distance_cm")
        exp["frequency"] = cyc.get("frequency")
        if d.engine_result is not None:
            exp["total_tmu"] = d.engine_result.get("total_tmu")
            exp["tech_line"] = d.engine_result.get("tech_line")
        else:
            # 引擎拒絕的 complete cycle：期望必須說「引擎拒絕」而不是留一個
            # 無 TMU 的 complete 期望——後者在 gold_eval 重放必回
            # 「expected engine_result」紅燈（產出即紅）。gold_eval._check_cycle
            # 對 expected_engine_rejected 驗「引擎仍拒絕」，不驗 TMU。
            exp["expected_engine_rejected"] = True
    else:
        if d.cycle is None:
            exp["cycle"] = None
        else:
            # typed 但 incomplete：帶 seq 讓 _check_cycle 不誤入 cycle=null 分支
            exp["seq"] = cyc.get("seq")
    if d.issues:
        exp["issues_contain"] = list(d.issues)
    return exp


async def run_pipeline(
    source_text: str, synonyms: list[dict], rs: Any
) -> tuple[Any, list, list, str, list[str]]:
    """現行 rule pipeline（與 wi_ai_service 關 LLM、gold_eval compile 段同路徑）。

    `rs` 由呼叫端 build 一次傳入（build_from_seed_v2 不進逐筆迴圈）。
    """
    parser = RuleBasedParser(synonyms)
    rule_result = parser.parse(source_text)
    plan, _legacy = plan_from_rule_result(rule_result, source_ref=SourceRef(kind="interactive"))
    linker = SlotLinker(synonyms)
    candidates = await linker.link(plan)
    drafts = compile_plan(
        plan,
        candidates,
        rule_set_code=_RULE_SET_CODE_HOLDER["code"],
        allow_lists=allow_lists_from_rule_set(rs),
        face_hit_params=linker.face_hit_params(plan),
    )
    drafts = apply_engine_gate(drafts, rs)
    status, reasons = compute_routing(plan, candidates, drafts, auto_enabled=False)
    return plan, candidates, drafts, status, reasons


async def preannotate(
    cand: Candidate,
    synonyms: list[dict],
    draft_id: str,
    rs: Any,
    split_component: str,
    module_structure: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    plan, _candidates, drafts, status, reasons = await run_pipeline(cand.raw, synonyms, rs)
    plan_json = plan.model_dump(mode="json")

    caveats: list[str] = []

    # D3-017 判型變更：新判型直接讀 plan（單一出處＝管線輸出，不重推一次），
    # 舊判型＝「僅名詞」classify_seq（空詞典）；不同者掛旗標＋留舊/新值。
    new_seq = _ACTION_TYPE_TO_SEQ.get(plan_json["actions"][0]["action_type"])
    old_seq = classify_seq(plan.normalized_text, cand.raw, frozenset())
    typing_change: dict[str, Any] | None = None
    if new_seq != old_seq:
        caveats.append(TYPING_CHANGED_CAVEAT)
        typing_change = {"noun_only_seq": old_seq, "lexicon_seq": new_seq}

    # D3-017 P 方向數旗標：本草稿的 cycle 實際選了方向變體才發（composite_unknown
    # 沒有 P slot，發了也沒有可覆核的值）；outcome 由單一出處
    # nlp.linking.classify_p_destination 判（生產/重放/harvest 同一套）。
    lex = build_lexicon(synonyms)
    p_chosen = {
        ((d.cycle or {}).get("p5") or {}).get("p_base_code")
        for d in drafts
        if d.cycle is not None
    }
    if p_chosen & {P_VARIANT_DEFAULT, P_VARIANT_SURFACE}:
        outcome = classify_p_destination(plan.normalized_text, lex)
        caveats.append(
            P_DIRECTION_CAVEATS.get(outcome, "p_direction_unclassified_default_single")
        )
    if cand.tags.get("multi_action") is True:
        # rule planner 結構上永遠單 action——多動作候選的切分幾乎必然低估
        caveats.append("likely_multi_action_undercounted")
    elif take_place_pair(cand.norm):
        # 取＋放配對不是 multi_action 證據（GM＝G+P 同 cycle）；中性旗標，IE 裁決方向
        caveats.append("take_place_pair_may_be_single_gm")
    elif take_move_pair(cand.norm):
        # 取/觸＋推/拉配對同理（CM＝G 與 M 同 cycle）；中性旗標，IE 裁決方向
        caveats.append("take_move_pair_may_be_single_cm")
    if acquire_without_place(plan_json["actions"]):
        # 裁決 2「取最後一定有放」：plan 有 acquire 而同 plan 內其後無收尾。
        # WARN 不 BLOCK——語意見 acquire_without_place docstring
        caveats.append("acquire_without_place")
    if not synonyms:
        caveats.append("empty_lexicon_no_slot_candidates")
    if any(d.complete and d.engine_result is None for d in drafts):
        # 期望端已寫 expected_engine_rejected（重放驗「引擎仍拒絕」，不假綠）；
        # 旗標提醒 IE：轉正前必須修 cycle 值，否則撞空殼守門（無 TMU 需顯式
        # expected_incomplete_reason）
        caveats.append("engine_rejected_cycle")
    expected_cycles_json = [expected_cycle_from_draft(d) for d in drafts]
    if has_zero_tmu_complete_cycle(expected_cycles_json):
        # D3-018 M1：complete 但 TMU=0.0（距離未述）——逐筆旗標＋覆核表逐筆
        # 提問；原樣轉正會撞空殼守門（total_tmu > 0 或顯式
        # expected_incomplete_reason）
        caveats.append(ZERO_TMU_CAVEAT)
    used_synonyms = used_lexicon_entries(plan.normalized_text, synonyms)
    if x_clean_context_missing(plan.normalized_text, used_synonyms):
        # D3-021：「清潔→x_blow_clean」是吹風情境的裁決——句面無風槍/吹風
        # 脈絡時不無條件套用，掛旗標交 IE（轉正 fail-closed 擋下）
        caveats.append(X_CLEAN_CONTEXT_CAVEAT)

    out: dict[str, Any] = {
        "id": draft_id,
        "source_text": cand.raw,
        "notes": DRAFT_NOTES_BOILERPLATE,
        "review_status": "pending_ie",
        "approved_by": None,
        # plan 出處＝rule planner 預標註；轉正時必填 ie_modified: true|false，
        # 未修改（false）的案例會被 planner 段 Plan 層指標排除（自我指涉防線）
        "plan_origin": PLAN_ORIGIN_PREANNOTATION,
        "ie_modified": None,
        "split": None,
        "split_groups": cand.split_groups,
        # 傳遞閉包算好的分組（同 component 必同 split）；IE 不用手推 leakage 群
        "split_component": split_component,
        "source_provenance": [s.provenance() for s in cand.sources],
        "challenge_tags": cand.tags,
        # 這幾維的 false 也是啟發式輸出（未覆核）——不是「已確認沒有」
        "heuristic_tags_unverified": list(HEURISTIC_UNVERIFIED_DIMS),
        "preannotation_caveat": caveats,
    }
    if typing_change is not None:
        # 與 TYPING_CHANGED_CAVEAT 同進同出（schema 守門）：舊/新判型留在草稿上，
        # 覆核表據此標「判型已由動詞字典修正，請確認」
        out["typing_change"] = typing_change
    if any(c in caveats for c in SEGMENTATION_CAVEATS):
        # D3-014 裁決 3：只對有切分爭點的草稿回填 v3 結構（hint 是證據不是判決）
        hint, evidence = v3_structure_backfill(cand, module_structure)
        out["v3_structure_hint"] = hint
        out["v3_structure_evidence"] = evidence
    out.update({
        "preannotation": {
            "pipeline": PIPELINE_DESC,
            "planner": RULE_PLANNER_NAME,
            "rule_set_code": _RULE_SET_CODE_HOLDER["code"],
            "lexicon_source": "rule_option_synonyms",
            "lexicon_size": len(synonyms),
            "routing_reasons": list(reasons),
        },
        "plan": plan_json,
        "synthetic_synonyms": used_synonyms,
        "expected_cycles": expected_cycles_json,
        "gold_schema_version": GOLD_SCHEMA_VERSION,
        "expected": {
            "action_count": len(plan.actions),
            "routing_status": status,
        },
    })
    return out


# ── IE 覆核表 ────────────────────────────────────────────────────────────────

_CORE_PARAM_ZH = {
    "acquire": "G（取得）",
    "move_place": "P（放置）",
    "controlled_move": "M（控制移動）",
    "process": "X（製程）",
    "inspect": "I（檢驗）",
}

_CAVEAT_ZH = {
    "likely_multi_action_undercounted": (
        "rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，"
        "**切分幾乎必然低估**——請務必逐動詞檢查"
    ),
    "take_place_pair_may_be_single_gm": (
        "本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 "
        "G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**"
        "（G 與 P 各取值）還是 acquire＋move_place **兩個 action**"
        "（見下方「取放建模」題；不預設方向）"
    ),
    "take_move_pair_may_be_single_cm": (
        "本句是「取/觸＋推/拉」動詞配對（無連接詞）——MiniMOST 的 CM 序列本來就是 "
        "G 與 M 同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md`"
        " §2：A B G M X I A），單 action 不必然是低估。請裁決：建成**單一 CM cycle**"
        "（G 與 M 各取值）還是 acquire＋controlled_move **兩個 action**"
        "（見下方「取移建模」題；不預設方向）"
    ),
    "acquire_without_place": (
        "本 plan 含 acquire（取）而其後**同 plan 內**沒有任何收尾 action"
        "（move_place／release_return／controlled_move）——裁決 2：「取最後一定有放」。"
        "**這句的「放」在哪？是句子被截斷了，還是描述缺漏？**"
        "邊界：本旗標只在同 plan 內判，是 WARN 不是 BLOCK——單句 acquire 可能"
        "合法（「放」在下一句/下一列，如正式 gold g01「拿起DIMM」不發明後續步驟）；"
        "判定用 action_type 序列，不用文字啟發式"
    ),
    "empty_lexicon_no_slot_candidates": (
        "dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，"
        "option code 需 IE 自填（並考慮順手登記同義詞）"
    ),
    "engine_rejected_cycle": (
        "引擎拒絕了此草稿的 cycle（complete 但引擎不收）：期望已記 "
        "`expected_engine_rejected: true`（重放驗「引擎仍拒絕」，不會假綠）。"
        "核准轉正前必須修正 cycle 值——原樣轉正沒有 TMU，會被空殼守門擋下"
        "（除非顯式寫 expected_incomplete_reason）"
    ),
    "p_direction_single_default": (
        "P 方向數（IE 情境規則 D3-017）：賓語屬**機構件類**（治具/卡槽/機箱/"
        "接頭/點位）→ 必對準，已預設 `p_place_single`。**方向數預設一種，"
        "不對請改**（p_place_multi 多種方向／p_place_none 無方向）"
    ),
    "p_direction_none_by_context": (
        "P 方向數（IE 情境規則 D3-017）：賓語屬**盤面類**（流水線/工作台/"
        "垃圾桶/料盒/材料盒/料架）→ 無方向，已套用 `p_place_none`。請確認"
    ),
    "p_direction_unclassified_default_single": (
        "P 方向數（IE 情境規則 D3-017）：賓語**不屬機構件/盤面名單**，判不出"
        "情境——暫用預設 `p_place_single`（方向數預設一種）。**請 IE 裁決**"
        "（single/multi/none）"
    ),
    ZERO_TMU_CAVEAT: (
        "此句未述距離，**TMU=0.0 非真值**（引擎口徑：距離未述＝0cm、M 階梯 "
        "0→0；G/B 伴隨 slot 未由 linker 掛值——X/I 自 D3-024 起面命中掛值）"
        "——complete 是結構完成度"
        "不是 TMU 可信度。**請補距離（改 plan/cycle 後 `--recompile` 重算）或"
        "判定句子資訊不足**（轉正時顯式寫 expected_incomplete_reason；"
        "空殼守門要求 total_tmu > 0，原樣轉正會被擋）"
    ),
    X_CLEAN_CONTEXT_CAVEAT: (
        "「清潔」情境條件（IE 裁決 D3-021）：「清潔→x_blow_clean 並吹風清潔」"
        "只裁了**吹風情境**（語料 4 筆全是風槍/吹風）——本句配出此映射但句面"
        "**無風槍/吹風脈絡**，不無條件套用。**請 IE 裁決本句的「清潔」建法**"
        "（吹風 x_blow_clean？擦拭 m_wipe？其他？）；未裁前本筆轉正 fail-closed 擋下"
    ),
}


# likely_multi 的降級版警語（D3-014：結構若顯示單一 cycle，「幾乎必然低估」
# 對該筆要降級——v3 結構是 IE 的切分裁決，不再預設切分是錯的）
_LIKELY_MULTI_DOWNGRADED_ZH = (
    "本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE "
    "當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），"
    "「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 "
    "v3 的切分本身有誤（hint 是證據不是判決，可推翻）"
)


def _seq_zh(seq: str | None) -> str:
    return {"GM": "GM（一般移動）", "CM": "CM（控制移動）"}.get(seq or "", "未定（composite_unknown）")


def _caveat_line_zh(caveat: str, draft: dict[str, Any]) -> str:
    """單筆草稿的旗標說明文字（覆核表用）。

    likely_multi_action_undercounted＋v3 結構 single_cycle ⇒ 警語降級
    （D3-014 裁決 3）；typing_changed 讀草稿 `typing_change` 欄組動態文字；
    其餘照 `_CAVEAT_ZH`。與 preannotate 的旗標共用同一欄位——不另判一次。"""
    if (
        caveat == "likely_multi_action_undercounted"
        and draft.get("v3_structure_hint") == STRUCTURE_HINT_SINGLE
    ):
        return _LIKELY_MULTI_DOWNGRADED_ZH
    if caveat == TYPING_CHANGED_CAVEAT:
        tc = draft.get("typing_change") or {}
        return (
            "**判型已由動詞字典修正，請確認**：動詞字典參與 GM/CM 判型"
            "（D3-017 收 M/G+P、D3-023 收 X/I；衝突矩陣見 nlp/rule_based.py "
            "classify_seq）——"
            f"舊判型（僅名詞觸發）＝{_seq_zh(tc.get('noun_only_seq'))}，"
            f"新判型（動詞字典參與）＝{_seq_zh(tc.get('lexicon_seq'))}。"
            "不同意新判型請在本筆「判型」題回答"
        )
    return _CAVEAT_ZH.get(caveat, caveat)


def _structure_evidence_brief(draft: dict[str, Any]) -> str:
    """v3 結構證據的一行摘要（覆核表用；完整證據在草稿 JSON）。"""
    sources = (draft.get("v3_structure_evidence") or {}).get("sources") or []
    parts = []
    for s in sources:
        cyc = "cycle 數未知（無發布版）" if s.get("cycles") is None else f"{s['cycles']} cycle"
        weight = "v3" if s.get("v3_migrated") else "非 v3，不餵 hint"
        parts.append(f"`{s['table']}/{str(s['id'])[:8]}…`（{s['detail']}；{cyc}；{weight}）")
    return "；".join(parts) or "（無來源證據）"


def _structure_hint_cycles(hint: str | None) -> int | None:
    """hint 字串 → cycle 數（single_cycle=1、multi_cycle_n=n、其他=None）。"""
    if hint == STRUCTURE_HINT_SINGLE:
        return 1
    if hint and hint.startswith("multi_cycle_"):
        return int(hint.rsplit("_", 1)[1])
    return None


def _mark_evidence(norm: str, start: int, end: int) -> str:
    return norm[:start] + "【" + norm[start:end] + "】" + norm[end:]


def _questions_for(draft: dict[str, Any]) -> list[str]:
    plan = draft["plan"]
    tags = draft["challenge_tags"]
    hint = draft.get("v3_structure_hint")
    hint_n = _structure_hint_cycles(hint)
    qs: list[str] = []
    n = len(plan["actions"])
    split_q = (
        f"切分：預測 action 數 = {n}。本句實際應拆成幾個 action？"
        "若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。"
    )
    # D3-014 裁決 3：v3 結構回填——有結構答案的預填、缺失/矛盾的維持開放題
    if hint_n == 1:
        split_q += (
            "【v3 結構】IE 當初把這句建為**單一 cycle**"
            f"（證據：{_structure_evidence_brief(draft)}），預設依此；不同意再改。"
        )
    elif hint_n is not None:
        split_q += (
            f"【v3 結構】IE 當初把這句切成 **{hint_n} 個 cycle**"
            f"（證據：{_structure_evidence_brief(draft)}），預設依此切分；不同意再改。"
        )
    elif hint == STRUCTURE_HINT_AMBIGUOUS:
        reason = (draft.get("v3_structure_evidence") or {}).get("reason", "")
        split_q += (
            f"【v3 結構】結構訊號缺失或矛盾（{reason}；"
            f"證據：{_structure_evidence_brief(draft)}）——維持開放題，請逐動詞裁決。"
        )
    qs.append(split_q)
    for a in plan["actions"]:
        if a["action_type"] == "composite_unknown":
            qs.append(
                f"判型（{a['action_id']}）：預測為 composite_unknown"
                "（動詞字典已參與判型（含 X/I）——仍未定＝動詞未登記/單一動詞不足/"
                "訊號衝突棄權，逐類統計見 harvest-summary）。"
                "實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？"
            )
        else:
            core = _CORE_PARAM_ZH.get(a["action_type"], "?")
            q = (
                f"判型（{a['action_id']}）：預測為 {a['action_type']}，對嗎？"
                f"若對，core 參數 {core} 的 option code 是什麼？（預標註無候選時請直接填）"
            )
            if TYPING_CHANGED_CAVEAT in (draft.get("preannotation_caveat") or []):
                tc = draft.get("typing_change") or {}
                q += (
                    f"【判型已由動詞字典修正：{_seq_zh(tc.get('noun_only_seq'))} → "
                    f"{_seq_zh(tc.get('lexicon_seq'))}，請確認】"
                )
            qs.append(q)
    # D3-017 P 方向數：cycle 實際選了方向變體的草稿逐筆問（旗標與提問同一出處）
    for c in draft.get("preannotation_caveat") or []:
        if c in P_DIRECTION_CAVEAT_NAMES:
            qs.append(f"P 方向數：{_CAVEAT_ZH[c]}")
    # D3-018 M1：TMU=0.0 的草稿逐筆問（旗標與提問同一出處；不只摘要一句話）
    if ZERO_TMU_CAVEAT in (draft.get("preannotation_caveat") or []):
        qs.append(f"TMU=0.0：{_CAVEAT_ZH[ZERO_TMU_CAVEAT]}。")
    # D3-021：清潔情境條件不成立的草稿逐筆問（旗標與提問同一出處）
    if X_CLEAN_CONTEXT_CAVEAT in (draft.get("preannotation_caveat") or []):
        qs.append(f"清潔情境：{_CAVEAT_ZH[X_CLEAN_CONTEXT_CAVEAT]}。")
    # 配對題與草稿旗標**共用同一判定**（take_place_pair / take_move_pair）：
    # 兩邊條件各寫一份曾經自相矛盾（掛「幾乎必然低估」的節同時出「多半建單一
    # GM cycle」的題）——單一出處，宣稱即事實。
    # D3-014 裁決 1＋3：「取+放怎麼建」逐案裁決，答案優先用 v3 結構回填——
    # 有結構答案時從開放題改成**確認題**（預設依 v3 結構，IE 可推翻）；
    # 缺失/矛盾時維持開放題並列出證據。
    norm_text = plan["normalized_text"]
    if take_place_pair(norm_text):
        if hint_n == 1:
            qs.append(
                "取放建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**"
                f"（證據：{_structure_evidence_brief(draft)}）——**預設建成單一 GM "
                "cycle（G 與 P 各取值）**；不同意再改成 acquire + move_place 兩個 "
                "action（hint 是證據不是判決，可推翻）。"
            )
        elif hint_n is not None:
            qs.append(
                f"取放建模（確認題）：v3 結構顯示 IE 當初把這句切成 **{hint_n} 個 "
                f"cycle**（證據：{_structure_evidence_brief(draft)}）——**預設依此切成 "
                f"{hint_n} 個 action/cycle**；不同意再改（hint 是證據不是判決，可推翻）。"
            )
        else:
            open_q = (
                "取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，"
                "還是 acquire + move_place **兩個 action**？（裁決 1：看動作逐案裁決，不預設方向）"
            )
            if hint == STRUCTURE_HINT_AMBIGUOUS:
                reason = (draft.get("v3_structure_evidence") or {}).get("reason", "")
                open_q += (
                    f"【v3 結構訊號缺失或矛盾（{reason}）：{_structure_evidence_brief(draft)}】"
                )
            qs.append(open_q)
    elif take_move_pair(norm_text):
        if hint_n == 1:
            qs.append(
                "取移建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**"
                f"（證據：{_structure_evidence_brief(draft)}）——**預設建成單一 CM "
                "cycle（G 與 M 各取值）**；不同意再改成 acquire + controlled_move "
                "兩個 action（hint 是證據不是判決，可推翻）。"
            )
        elif hint_n is not None:
            qs.append(
                f"取移建模（確認題）：v3 結構顯示 IE 當初把這句切成 **{hint_n} 個 "
                f"cycle**（證據：{_structure_evidence_brief(draft)}）——**預設依此切成 "
                f"{hint_n} 個 action/cycle**；不同意再改（hint 是證據不是判決，可推翻）。"
            )
        else:
            open_q = (
                "取移建模：此句是「取/觸＋推/拉」動詞配對——應建成**一個 CM cycle"
                "（G 與 M 各取值）**，還是 acquire + controlled_move **兩個 action**？"
                "（CM 序列的 G 與 M 本來就在同一 cycle：`docs/core-logic/"
                "minimost-sequence-model-core-logic-spec.md` §2；裁決 1：逐案裁決）"
            )
            if hint == STRUCTURE_HINT_AMBIGUOUS:
                reason = (draft.get("v3_structure_evidence") or {}).get("reason", "")
                open_q += (
                    f"【v3 結構訊號缺失或矛盾（{reason}）：{_structure_evidence_brief(draft)}】"
                )
            qs.append(open_q)
    # 「取必有放」提問與旗標共用同一判定（acquire_without_place）——單一出處
    if acquire_without_place(plan["actions"]):
        qs.append(
            "取而無放（裁決 2）：plan 有 acquire 而其後同 plan 內無任何收尾"
            "（move_place／release_return／controlled_move）——**這句的「放」在哪？"
            "是被截斷了還是描述缺漏？**若「放」在下一句/下一列，請在 notes 註明"
            "（單句 acquire 合法，如 g01）；若本句就該有「放」，請補 action。"
        )
    if tags.get("quantity") is True:
        qs.append("數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）")
    if tags.get("tool_handling") is True:
        qs.append("工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。")
    if tags.get("simo_both_hands") is True:
        qs.append("SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）")
    if tags.get("diagram_reference_no_image") is True:
        qs.append("依圖示：無圖片情境下，句面資訊足以決定參數嗎？不足請在 unresolved 標 missing_info。")
    qs.append(
        f"routing：預測 routing_status = {draft['expected']['routing_status']}"
        f"（理由：{'、'.join(draft['preannotation']['routing_reasons']) or '無'}）。核准後應維持這個值嗎？"
    )
    return qs


def _ie_review_lines(draft: dict[str, Any]) -> list[str]:
    """已合併覆核狀態的草稿在覆核表的狀態行（D3-015）。

    語意邊界寫死在字面上：切分維度的確認/裁決 ≠ 整筆 gold 核准。"""
    ir = draft.get("ie_review")
    if not ir:
        return []
    who = ir.get("segmentation_confirmed_by")
    date = ir.get("segmentation_confirmed_date")
    out: list[str] = []
    if ir.get("segmentation_source") == "v3_structure_confirmed":
        out.append(
            f"**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（{who}，{date}）。"
            "僅確認切分，不是整筆 gold 核准；`ie_modified: false`"
            "（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。"
        )
    elif ir.get("segmentation_source") == REVIEW_SEGMENTATION_SOURCE_BATCH:
        out.append(
            f"**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批"
            f"確認現行切分（單 action＝single_cycle；{who}，{date}）。"
            "與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`"
            "——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。"
        )
    elif ir.get("segmentation_source") == "ie_ruling":
        ruling = ir.get("ie_ruling")
        out.append(
            f"**✅ IE 裁決（切分維度）**：`{ruling}`（{who}，{date}）——"
            "裁決取代本節 v3 結構的 ambiguous/開放題。僅裁決切分，不是整筆 gold 核准。"
        )
        if ir.get("ie_ruling_notes"):
            out.append(f"  - 裁決註記：{ir['ie_ruling_notes']}")
        if ir.get("plan_pending_resegmentation"):
            out.append(
                "  - **切分裁決已下，plan 重切等第二輪（需子句對應）**：裁決的各 cycle "
                "子句不是原句的子字串，無法誠實切出對應 evidence span——不編造 span，"
                "plan 維持單 action 待第二輪以子句對應重切。"
            )
        rejected = [
            s
            for s in (draft.get("v3_structure_evidence") or {}).get("sources") or []
            if s.get("ie_ruling_rejected")
        ]
        for s in rejected:
            out.append(
                f"  - IE 裁決否定的結構（證據保留不刪）：`{s['table']}/{str(s['id'])[:8]}…`"
                f"（{s['detail']}；{s['cycles']} cycle）"
            )
    # D3-019：判型／P 方向數／TMU=0 三個面向的覆核狀態（有才顯示）
    if ir.get("typing_confirmed_by"):
        out.append(
            f"**✅ IE 覆核狀態（判型）**：動詞字典的判型修正已確認照預設"
            f"（{ir['typing_confirmed_by']}，{ir['typing_confirmed_date']}）。"
            "確認≠修改，`ie_modified` 維持 false。"
        )
    if ir.get("p_direction_confirmed_by"):
        out.append(
            f"**✅ IE 覆核狀態（P 方向數）**：方向數變體已確認照預設"
            f"（{ir['p_direction_confirmed_by']}，{ir['p_direction_confirmed_date']}）。"
        )
    if ir.get("zero_tmu_ruling"):
        out.append(
            f"**✅ IE 裁決（TMU=0.0）**：`{ir['zero_tmu_ruling']}`——句子未述距離、"
            f"判定資訊不足（{ir['zero_tmu_ruled_by']}，{ir['zero_tmu_ruled_date']}）；"
            "草稿已記 `expected_incomplete_reason`（轉正走誠實記錄路徑，不發明距離）。"
        )
    if ir.get("incomplete_ruling"):
        out.append(
            f"**✅ IE 裁決（incomplete）**：`{ir['incomplete_ruling']}`——缺漏語意"
            "已逐型釘值（距離/顆數/秒數句面未述，等佈局資料）"
            f"（{ir['incomplete_ruled_by']}，{ir['incomplete_ruled_date']}）；"
            "草稿已記 `expected_incomplete_reason`（誠實 incomplete 轉正路徑，"
            "不發明值）。"
        )
    if ir.get("resegmentation_ruling"):
        out.append(
            f"**✅ IE 裁決（重切）**：`{ir['resegmentation_ruling']}`——本句是製程"
            "標題句，各列為獨立子句非本句子字串，**不硬切、不轉正**（fail-closed）；"
            "留在草稿當多動作辨識參考"
            f"（{ir['resegmentation_ruled_by']}，{ir['resegmentation_ruled_date']}）。"
        )
        if ir.get("resegmentation_ruling_notes"):
            out.append(f"  - 裁決註記：{ir['resegmentation_ruling_notes']}")
    return out


def _stale_prior_rulings_zh(entry: dict[str, Any]) -> list[str]:
    """stale entry 的先前確認/裁決**內容**摘要（覆核表 banner 用；D3-023 複審
    必修 1）。

    內容要印出來，不是只給指標：IE 在覆核表上看不到自己先前的裁決，就會被
    確認題的預設值（如「v3 切 5 cycle，預設依此」）引導推翻自己（d004/
    d0350279 實案——IE 已裁標題句不硬切，覆核表上卻長得像全新草稿）。
    重切裁決排最前（它是先前狀態的主結論），其餘面向依 entry 欄位逐一列出。"""
    out: list[str] = []
    if entry.get("resegmentation_ruling") == RESEGMENTATION_RULING_TITLE_SENTENCE:
        out.append(
            "標題句不硬切（D3-022，`title_sentence_no_resegmentation`——"
            "不重切、不轉正，內容由成分列的獨立 gold 覆蓋）"
        )
    src = entry.get("segmentation_source")
    if src == "ie_ruling":
        out.append(f"切分裁決 `{entry.get('ie_ruling')}`")
    elif src == REVIEW_SEGMENTATION_SOURCE_BATCH:
        out.append("切分批次確認（無爭點案例，`no_contention_batch_confirmed`）")
    elif src == "v3_structure_confirmed":
        out.append(
            f"切分已確認照 v3 結構（`{entry.get('v3_structure_hint_at_review')}`）"
        )
    if entry.get("typing_confirmed_by"):
        tc = entry.get("typing_change_at_review") or {}
        out.append(
            f"判型修正已確認（{_seq_zh(tc.get('noun_only_seq'))} → "
            f"{_seq_zh(tc.get('lexicon_seq'))}）"
        )
    if entry.get("p_direction_confirmed_by"):
        out.append(f"P 方向數已確認（`{entry.get('p_direction_caveat_at_review')}`）")
    if entry.get("zero_tmu_ruling"):
        out.append(f"TMU=0 已裁 `{entry['zero_tmu_ruling']}`（句子資訊不足）")
    if entry.get("incomplete_ruling"):
        out.append(f"incomplete 已裁 `{entry['incomplete_ruling']}`（缺漏語意逐型釘值）")
    return out


def _stale_review_lines(stale: dict[str, Any]) -> list[str]:
    """stale 筆的覆核表 banner（D3-023 複審必修 1）。

    只影響覆核表顯示——**合併語意不變**（stale 照樣不套用、草稿一個欄位都
    不動，見 apply_review_state_entry）。banner 三要件：stale 原因、先前裁決
    的**內容**（_stale_prior_rulings_zh）、指回 review-state entry＋「先重新
    確認再答題」指示。

    mutation 證據：banner 拆掉 → tests/unit/test_gold_harvest_review_state.py
    ::test_stale_draft_checklist_banner_shows_prior_ruling 紅。"""
    rulings = _stale_prior_rulings_zh(stale.get("entry") or {})
    if rulings:
        content = f"**先前裁決：{'；'.join(rulings)}**"
    else:  # 防禦性：load_review_state 保證至少一個面向，正常走不到這裡
        content = "**先前覆核記錄內容未能摘要——請直接開 review-state entry 核對**"
    return [
        f"**⚠️ 本筆先前 IE 覆核狀態因 `{stale['reason']}` 未套用**"
        "（stale——確認/裁決所依據的內容已變，不靜默沿用；本節下方的預設值"
        f"**未帶入**先前狀態）；{content}，見 review-state entry"
        f"（`{stale['sha8']}`）。**本次請先重新確認先前裁決是否維持，"
        "再看下列問題。**"
    ]


def build_review_checklist(
    drafts: list[dict[str, Any]],
    review_stale: list[dict[str, Any]] | None = None,
) -> str:
    stale_by_sha8 = {s["sha8"]: s for s in (review_stale or [])}
    lines: list[str] = []
    lines.append("# IE 覆核表 — gold set 擴充預標註草稿")
    lines.append("")
    lines.append("<!-- 本檔由 scripts/gold_harvest.py 產生；重跑 harvest 會整檔重寫，IE 批註請寫在草稿 JSON 或另開檔案 -->")
    lines.append("")
    lines.append(
        "草稿位置：`tests/gold/wi_plans_draft/`。**這些不是 gold**（`approved_by: null`、"
        "`review_status: pending_ie`），評測不會撿到。核准／轉正流程見 "
        "`docs/llm/gold-review/README.md`。"
    )
    lines.append("")
    lines.append(
        "**先讀這個——預標註的系統性偏差**：現行 rule planner 對任何輸入都只會產生"
        "**1 個 action、evidence=整句**。所以「預測 action 數=1」不是模型判斷，是結構限制；"
        "帶 `likely_multi_action_undercounted` 的每一筆都請假設切分是錯的，逐動詞重切"
        "（**例外**：該筆若有 `v3_structure_hint: single_cycle`，警語降級——v3 結構顯示 "
        "IE 當初建為單一 cycle，預設依此）。"
        "帶 `take_place_pair_may_be_single_gm` 的是「取＋放」配對——GM 本來就是 G＋P 同 "
        "cycle，**不預設低估**，請用該筆的「取放建模」題裁決單一 GM 或兩個 action。"
        "帶 `take_move_pair_may_be_single_cm` 的是「取/觸＋推/拉」配對——CM 的 G 與 M "
        "同一 cycle，同樣**不預設低估**，請用該筆的「取移建模」題裁決單一 CM 或兩個 action。"
        "配對題與切分題已用 **v3 結構回填**（D3-014 裁決 3：v3 遷移資料是 IE 驗證過"
        "並提供的，結構＝IE 的切分裁決）：有結構答案的是**確認題**（預設依 v3 結構，"
        "不同意再改），缺失/矛盾的維持開放題——hint 是證據不是判決，IE 可推翻。"
        "帶 `acquire_without_place` 的是「取而無放」（裁決 2：取最後一定有放）——"
        "請回答該筆的「放」在哪（WARN 不 BLOCK；單句 acquire 可能合法）。"
        "另外：`challenge_tags` 裡 9 個可判維度的 `false` 也是啟發式輸出"
        "（`heuristic_tags_unverified` 點名的維度已有實證漏標），true/false 請一併確認。"
    )
    lines.append("")
    n_flag = sum(1 for d in drafts if d["preannotation_caveat"])
    n_reviewed = sum(1 for d in drafts if d.get("ie_review"))
    lines.append(f"共 {len(drafts)} 筆，其中 {n_flag} 筆帶 ⚠️ 旗標。")
    if n_reviewed:
        lines.append("")
        lines.append(
            f"其中 **{n_reviewed} 筆**已由 `review-state.json` 合併 IE 覆核狀態"
            "（各節「IE 覆核狀態」行）。注意：那是**切分維度**的確認/裁決，"
            "**不是整筆 gold 核准**——cycle 仍 incomplete 的照樣要覆核 option code，"
            "轉正另有流程（`docs/llm/gold-review/README.md`）。"
        )
    stale_ids = [d["id"] for d in drafts if draft_sha8(d) in stale_by_sha8]
    if stale_ids:
        lines.append("")
        lines.append(
            f"**⚠️ {len(stale_ids)} 筆**（{'、'.join(f'`{i}`' for i in stale_ids)}）的"
            "先前 IE 覆核狀態本輪 **stale 未套用**（確認/裁決所依據的內容已變，"
            "不靜默沿用）——該筆小節有 banner，**先前裁決的內容印在 banner 上**；"
            "請先重新確認裁決是否維持，再答該節問題（該節的預設值未帶入先前狀態）。"
        )
    lines.append("")
    for d in drafts:
        plan = d["plan"]
        lines.append("---")
        lines.append("")
        lines.append(f"## {d['id']}")
        lines.append("")
        lines.append(f"**原文**：{d['source_text']}")
        norm = plan["normalized_text"]
        if norm != d["source_text"]:
            lines.append(f"**正規化**：{norm}")
        srcs = "; ".join(
            f"`{s['table']}/{s['id'][:8]}…`（{s['detail']}）" for s in d["source_provenance"][:3]
        )
        more = len(d["source_provenance"]) - 3
        if more > 0:
            srcs += f"；另 {more} 個來源見草稿 JSON"
        lines.append(f"**來源**：{srcs}")
        true_dims = [DIM_ZH[k] for k in DIM_KEYS if d["challenge_tags"].get(k) is True]
        lines.append(f"**挑戰維度（規則式判定）**：{'、'.join(true_dims) or '（無命中）'}")
        if d.get("v3_structure_hint"):
            lines.append(
                f"**v3 結構**：`{d['v3_structure_hint']}`——{_structure_evidence_brief(d)}"
                "（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）"
            )
        stale_rec = stale_by_sha8.get(draft_sha8(d))
        if stale_rec is not None:
            lines.extend(_stale_review_lines(stale_rec))
        for line in _ie_review_lines(d):
            lines.append(line)
        for c in d["preannotation_caveat"]:
            lines.append(f"**⚠️ {c}**：{_caveat_line_zh(c, d)}")
        lines.append("")
        lines.append(f"**預測 action 數**：{len(plan['actions'])}")
        lines.append("**預測切分（evidence 以【】標在正規化原文上）**：")
        for a in plan["actions"]:
            if a["evidence"]:
                ev = a["evidence"][0]
                marked = _mark_evidence(norm, ev["start"], ev["end"])
            else:
                marked = "（無 evidence）"
            lines.append(f"- `{a['action_id']}` {a['action_type']}：{marked}")
        lines.append("")
        tmu_lines: list[str] = []
        for ec in d["expected_cycles"]:
            if ec.get("complete") and ec.get("total_tmu") is not None:
                tmu_lines.append(
                    f"- `{ec['action_id']}`：TMU={ec['total_tmu']}，tech line=`{ec['tech_line']}`"
                )
            else:
                why = "、".join(ec.get("issues_contain") or []) or "incomplete"
                tmu_lines.append(f"- `{ec['action_id']}`：未編譯（{why}）")
        lines.append("**預測 TMU / tech line**：")
        lines.extend(tmu_lines or ["- （無 cycle）"])
        lines.append(f"**預測 routing**：`{d['expected']['routing_status']}`")
        lines.append("")
        lines.append("**IE 請回答**：")
        for i, q in enumerate(_questions_for(d), start=1):
            lines.append(f"{i}. {q}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ── D3-017／D3-023：判型統計（僅名詞 vs 動詞字典參與）與 unknown 卡點分類 ───

# composite_unknown 卡點分類（決定性；每筆恰一類，優先序＝列出順序）：
# 1. verb_mixed_abstain     M/X/I＋P 同句（跨模型混合＝多 cycle 證據）→ 設計上棄權
# 2. noun_cm_verb_gm_abstain 名詞 CM × 動詞 GM（衝突矩陣 ※2）→ 設計上棄權
# 3. unregistered_verbs     句面有動詞面但（部分）未登記（`?` 待 IE 裁決）
# 4. single_verb_insufficient 已登記動詞只有 G 或 P 單獨（單一動詞不足以定型）
# 5. no_verb_face           句面完全無動詞面命中 → 需 IE 改 plan 或補描述
_UNKNOWN_BLOCK_ZH = {
    "verb_mixed_abstain": "動詞跨模型混合（M/X/I＋P 同句）→ 棄權（多 cycle 證據，設計如此）",
    "noun_cm_verb_gm_abstain": "名詞 CM × 動詞 GM 衝突 → 棄權（無 IE 裁決，設計如此）",
    "unregistered_verbs": "句面動詞（部分）未登記——卡 `?` 動詞，IE 裁決後可解",
    "single_verb_insufficient": "已登記動詞僅 G 或 P 單獨——單一動詞不足以定型",
    "no_verb_face": "句面無動詞面命中——需 IE 改 plan／補描述（非同義詞可解）",
}


def unknown_block_reason(
    norm: str, raw: str, synonyms: list[dict]
) -> tuple[str, list[str]]:
    """composite_unknown 草稿的卡點分類（單一出處；summary 與測試共用）。

    動詞訊號判定直接用生產端 `_verb_seq`（D3-023：X/I 收進 CM 訊號後，
    此處若自寫一份 has_m/has_p 就是平行判定路徑——兩邊必然漂移）。

    回傳 (類別, 未登記動詞面清單——僅 unregistered_verbs 類非空)。
    """
    lex = build_lexicon(synonyms)
    params_hit = frozenset(e.parameter for _, _, e in match_all(norm, lex))
    verb = _verb_seq(params_hit)
    if verb == "mixed":
        return "verb_mixed_abstain", []
    if verb == "GM" and classify_seq(norm, raw, frozenset()) == "CM":
        return "noun_cm_verb_gm_abstain", []
    registered = {s["synonym_norm"] for s in synonyms}
    unregistered = sorted({v for v in _action_verb_hits(norm) if v not in registered})
    if unregistered:
        return "unregistered_verbs", unregistered
    if "G" in params_hit or "P" in params_hit:
        return "single_verb_insufficient", []
    return "no_verb_face", []


def _round3_typing_lines(drafts: list[dict[str, Any]], synonyms: list[dict]) -> list[str]:
    """「判型」摘要節：僅名詞 vs 動詞字典參與的分佈對比＋unknown 卡點逐類。"""
    lines: list[str] = []
    lines.append("## 判型（D3-017 動詞字典參與＋D3-023 X/I 參與 GM/CM 判型）")
    lines.append("")
    lines.append(
        "判型吃動詞字典（第三輪 D3-017：M 命中＝CM 訊號、G+P 組合＝GM 訊號；"
        "第六輪 D3-023：X/I 命中同為 CM 訊號——X/I 只存在 CM 序列，與 M 同級；"
        "衝突矩陣與棄權路徑見 `src/ddm_v2/nlp/rule_based.py` classify_seq）。"
        "「舊」欄＝僅名詞觸發詞的第二輪行為（同一函式傳空詞典重算，非手抄數字）："
    )
    lines.append("")
    dist: dict[str, dict[str, int]] = {
        "GM": {"old": 0, "new": 0},
        "CM": {"old": 0, "new": 0},
        "unknown": {"old": 0, "new": 0},
    }
    changed: list[dict[str, Any]] = []
    for d in drafts:
        new_seq = _ACTION_TYPE_TO_SEQ.get(d["plan"]["actions"][0]["action_type"])
        old_seq = classify_seq(d["plan"]["normalized_text"], d["source_text"], frozenset())
        dist[new_seq or "unknown"]["new"] += 1
        dist[old_seq or "unknown"]["old"] += 1
        if new_seq != old_seq:
            changed.append(d)
    lines.append("| 判型 | 舊（僅名詞） | 新（動詞字典參與） |")
    lines.append("|---|---|---|")
    for key, zh in (("GM", "GM（move_place）"), ("CM", "CM（controlled_move）"),
                    ("unknown", "未定（composite_unknown）")):
        lines.append(f"| {zh} | {dist[key]['old']} | {dist[key]['new']} |")
    lines.append("")
    lines.append(
        f"判型變更 **{len(changed)} 筆**（草稿帶 `{TYPING_CHANGED_CAVEAT}`＋"
        "`typing_change` 舊/新值；覆核表逐筆標「判型已由動詞字典修正，請確認」）："
    )
    lines.append("")
    for d in changed:
        tc = d.get("typing_change") or {}
        lines.append(
            f"- `{d['id']}`：{_seq_zh(tc.get('noun_only_seq'))} → "
            f"{_seq_zh(tc.get('lexicon_seq'))}——「{d['source_text']}」"
        )
    lines.append("")
    # unknown 卡點逐類
    unknowns = [
        d for d in drafts
        if d["plan"]["actions"][0]["action_type"] == "composite_unknown"
    ]
    lines.append(f"### 判型仍未定的 {len(unknowns)} 筆——卡點逐類")
    lines.append("")
    by_reason: dict[str, list[tuple[dict[str, Any], list[str]]]] = {}
    for d in unknowns:
        reason, missing = unknown_block_reason(
            d["plan"]["normalized_text"], d["source_text"], synonyms
        )
        by_reason.setdefault(reason, []).append((d, missing))
    for reason in _UNKNOWN_BLOCK_ZH:
        group = by_reason.get(reason, [])
        if not group:
            continue
        lines.append(f"- **{_UNKNOWN_BLOCK_ZH[reason]}**：{len(group)} 筆")
        for d, missing in group:
            extra = f"（未登記：{'、'.join(missing)}）" if missing else ""
            lines.append(f"  - `{d['id']}`{extra}：「{d['source_text']}」")
    lines.append("")
    # P 方向數旗標統計（IE 情境規則）
    p_counts = {name: 0 for name in sorted(P_DIRECTION_CAVEAT_NAMES)}
    for d in drafts:
        for c in d["preannotation_caveat"]:
            if c in p_counts:
                p_counts[c] += 1
    lines.append(
        "### P 方向數（IE 情境規則：機構件→對準 single／盤面→無方向 none；"
        "名詞分類單一出處＝`src/ddm_v2/nlp/linking.py`）"
    )
    lines.append("")
    lines.append(
        f"- 機構件→`p_place_single`（方向數預設一種，不對請改）：{p_counts['p_direction_single_default']} 筆"
    )
    lines.append(
        f"- 盤面→`p_place_none`（已套用，請確認）：{p_counts['p_direction_none_by_context']} 筆"
    )
    lines.append(
        f"- 判不出→預設 single＋交 IE 裁決：{p_counts['p_direction_unclassified_default_single']} 筆"
    )
    lines.append("")
    return lines


def build_summary(
    counts: dict[str, int],
    all_candidates: list[Candidate],
    selected: list[Candidate],
    synonyms: list[dict],
    limit: int,
    already_gold: list[Candidate] | None = None,
    drafts: list[dict[str, Any]] | None = None,
    review_state_present: bool = False,
    review_applied: list[str] | None = None,
    review_stale: list[dict[str, Any]] | None = None,
    review_promoted: list[dict[str, Any]] | None = None,
) -> str:
    drafts = drafts or []
    review_applied = review_applied or []
    review_stale = review_stale or []
    review_promoted = review_promoted or []
    lines: list[str] = []
    lines.append("# Harvest 摘要 — gold set 擴充候選採集")
    lines.append("")
    lines.append("<!-- 本檔由 scripts/gold_harvest.py 產生（決定性輸出，不含 timestamp） -->")
    lines.append("")
    lines.append("## 來源（唯讀 DB）")
    lines.append("")
    lines.append("| 來源 | 撈得筆數 |")
    lines.append("|---|---|")
    for k in ("motion_modules", "motion_module_versions.rows[]", "wi_rows", "motion_templates"):
        lines.append(f"| {k} | {counts.get(k, 0)} |")
    lines.append("")
    lines.append(
        f"正規化去重後 unique 候選：**{len(all_candidates)}**；本次選出：**{len(selected)}**"
        f"（上限 {limit}，多樣性 greedy max-coverage，非取前 N）。"
    )
    lines.append("")
    lines.append(
        "**取樣性質**：coverage-optimized（挑戰維度過採樣），**不是**分佈代表性樣本——"
        "在本集合上量到的分數不可外推為生產分佈的表現；分佈代表性指標需另抽隨機樣本。"
    )
    if already_gold:
        excluded = "、".join(f"「{c.raw}」" for c in already_gold)
        lines.append("")
        lines.append(
            f"另有 **{len(already_gold)} 筆**與正式 gold（tests/gold/wi_plans/）既有案例同句，"
            f"已排除不重複進草稿：{excluded}。"
        )
    if len(selected) < 50:
        lines.append("")
        lines.append(
            f"**⚠️ 未達 50 筆**：實際只有 {len(selected)} 筆 unique 真實描述，缺額 "
            f"{50 - len(selected)} 筆需要 IE 提供真實工單（不得複製貼上湊數、不得生成假案例）。"
        )
    lines.append("")
    lines.append(
        f"詞典（rule_option_synonyms @ {_RULE_SET_CODE_HOLDER['code']}）：**{len(synonyms)} 條**。"
    )
    if not synonyms:
        lines.append(
            "**⚠️ 詞典為空**：預標註完全沒有 slot 候選（G/P/M/X/I 全空、cycle 全部 incomplete），"
            "每筆草稿都帶 `empty_lexicon_no_slot_candidates` 旗標；IE 覆核時需自填 option code。"
        )
    if drafts:
        with_tmu = [
            d
            for d in drafts
            if any(
                ec.get("complete") and ec.get("total_tmu") is not None
                for ec in d["expected_cycles"]
            )
        ]
        # D3-018 M1 單一出處：TMU=0.0 統計＝per-draft 旗標（ZERO_TMU_CAVEAT），
        # 不在此另判一次
        zero_tmu = [d for d in drafts if ZERO_TMU_CAVEAT in d["preannotation_caveat"]]
        lines.append("")
        lines.append(
            f"Cycle 完成度：**{len(with_tmu)}／{len(drafts)} 筆**至少一個 cycle "
            "complete 帶 TMU（TMU 唯一出處＝most_engine）；其餘 "
            f"{len(drafts) - len(with_tmu)} 筆全部 incomplete"
            "（缺 slot 候選或判型未定——逐筆原因見草稿 `expected_cycles[].issues_contain`）。"
        )
        if zero_tmu:
            lines.append("")
            lines.append(
                f"**誠實旗標**：complete 之中 **{len(zero_tmu)} 筆 TMU＝0.0**"
                f"（{'、'.join('`' + d['id'] + '`' for d in zero_tmu)}）——引擎口徑下"
                "距離未述＝0cm（M 階梯 0→0）且 G/B 伴隨 slot（如 CM 的 G、"
                "GM 的 G）未由 linker 掛值（X/I 自 D3-024 起面命中掛值）。"
                "complete≠可信 TMU：TMU=0.0 非真值——每筆已掛 "
                f"`{ZERO_TMU_CAVEAT}` 旗標，覆核表逐筆問「補距離或判定句子資訊"
                "不足」；原樣轉正會撞空殼守門（total_tmu > 0 或顯式 "
                "expected_incomplete_reason）。"
            )
    lines.append("")
    lines.append("## 挑戰維度覆蓋（spec §14.3 的 16 維度）")
    lines.append("")
    lines.append("| 維度 | 規則式可判？ | 全候選命中 | 已選命中 |")
    lines.append("|---|---|---|---|")
    gaps: list[str] = []
    for key, zh, detectable in CHALLENGE_DIMS:
        if detectable:
            uni = sum(1 for c in all_candidates if c.tags.get(key) is True)
            sel = sum(1 for c in selected if c.tags.get(key) is True)
            lines.append(f"| {zh}（`{key}`） | 可判 | {uni} | {sel} |")
            if sel == 0:
                gaps.append(f"{zh}（`{key}`）：真實資料中 0 筆命中")
        else:
            lines.append(f"| {zh}（`{key}`） | **判不動（每筆標 unknown）** | — | — |")
            gaps.append(f"{zh}（`{key}`）：規則式判不動，覆核時 IE 可順手標，或需合成案例")
    lines.append("")
    # 全形細分（P2-8）：命中若全是標點，全形「英數」仍是零覆蓋——不可合著算
    fw_uni_alnum = sum(1 for c in all_candidates if _fullwidth_kinds(c.raw)[0])
    fw_uni_punct = sum(1 for c in all_candidates if _fullwidth_kinds(c.raw)[1])
    fw_sel_alnum = sum(1 for c in selected if _fullwidth_kinds(c.raw)[0])
    fw_sel_punct = sum(1 for c in selected if _fullwidth_kinds(c.raw)[1])
    lines.append(
        f"全形字元細分——全形**英數**：全候選 {fw_uni_alnum}／已選 {fw_sel_alnum}；"
        f"全形**標點/空白**：全候選 {fw_uni_punct}／已選 {fw_sel_punct}。"
    )
    if fw_sel_alnum == 0 and fw_sel_punct > 0:
        gaps.append(
            "全形英數（`fullwidth_chars` 細分）：0 筆命中——現有 fullwidth 命中全是標點，"
            "全形英數（ＡＢＣ／０１２）視為未覆蓋"
        )
    lines.append("")
    lines.append("## 覆蓋缺口（需 IE 補寫合成案例或提供真實工單，不硬湊）")
    lines.append("")
    for g in gaps:
        lines.append(f"- {g}")
    lines.append("")
    if drafts:
        lines.append("## 預測 action type 分佈（rule planner 預標註，非 ground truth）")
        lines.append("")
        type_counts: dict[str, int] = {}
        for d in drafts:
            for a in d["plan"]["actions"]:
                type_counts[a["action_type"]] = type_counts.get(a["action_type"], 0) + 1
        lines.append("| action_type | 筆數 |")
        lines.append("|---|---|")
        for t in sorted(type_counts):
            lines.append(f"| {t} | {type_counts[t]} |")
        lines.append("")
        lines.extend(_round3_typing_lines(drafts, synonyms))
        lines.append("## Split 分組（傳遞閉包已算好；同 component 必同 split）")
        lines.append("")
        comp_drafts: dict[str, list[str]] = {}
        for d in drafts:
            comp_drafts.setdefault(d["split_component"], []).append(d["id"])
        multi = {k: v for k, v in sorted(comp_drafts.items()) if len(v) > 1}
        if multi:
            lines.append("多筆同組（分 split 時必須綁在一起，草稿的 `split_component` 已標）：")
            lines.append("")
            for comp, ids in multi.items():
                lines.append(f"- `{comp}`：{'、'.join(ids)}")
        else:
            lines.append("（無多筆同組——每筆草稿各自獨立成組）")
        lines.append(
            f"\n其餘 {len(comp_drafts) - len(multi)} 個 component 各只含 1 筆草稿。"
        )
        lines.append("")
        # D3-014 裁決 3：v3 結構回填統計（有切分爭點的草稿才回填）
        lines.append("## v3 結構回填（D3-014：v3 結構＝IE 的切分裁決；hint 是證據不是判決）")
        lines.append("")
        lines.append(
            "帶切分旗標（配對／likely_multi）的草稿逐筆對回 v3 遷移資料的結構"
            "（module/cycle 邊界）；有結構答案的配對題已改為**確認題**（預設依 v3 "
            "結構，IE 可推翻），缺失/矛盾者維持開放題："
        )
        lines.append("")
        lines.append("| 旗標 | 筆數 | single_cycle | multi_cycle_n | ambiguous |")
        lines.append("|---|---|---|---|---|")
        flag_zh = {
            "take_place_pair_may_be_single_gm": "取＋放配對（GM）",
            "take_move_pair_may_be_single_cm": "取/觸＋推/拉配對（CM）",
            "likely_multi_action_undercounted": "likely_multi",
        }
        for flag in (
            "take_place_pair_may_be_single_gm",
            "take_move_pair_may_be_single_cm",
            "likely_multi_action_undercounted",
        ):
            group = [d for d in drafts if flag in d["preannotation_caveat"]]
            n_single = sum(
                1 for d in group if d.get("v3_structure_hint") == STRUCTURE_HINT_SINGLE
            )
            n_multi = sum(
                1
                for d in group
                if str(d.get("v3_structure_hint") or "").startswith("multi_cycle_")
            )
            n_amb = sum(
                1 for d in group if d.get("v3_structure_hint") == STRUCTURE_HINT_AMBIGUOUS
            )
            lines.append(
                f"| {flag_zh[flag]} | {len(group)} | {n_single} | {n_multi} | {n_amb} |"
            )
        lines.append("")
        ambiguous = [
            d for d in drafts if d.get("v3_structure_hint") == STRUCTURE_HINT_AMBIGUOUS
        ]
        if ambiguous:
            lines.append("ambiguous 逐筆（維持開放題；矛盾/缺失證據已列在草稿與覆核表）：")
            lines.append("")
            for d in ambiguous:
                reason = (d.get("v3_structure_evidence") or {}).get("reason", "")
                lines.append(f"- `{d['id']}`（{reason}）：「{d['source_text']}」")
            lines.append("")
        downgraded = [
            d
            for d in drafts
            if "likely_multi_action_undercounted" in d["preannotation_caveat"]
            and d.get("v3_structure_hint") == STRUCTURE_HINT_SINGLE
        ]
        lines.append(
            f"likely_multi 中 **{len(downgraded)} 筆**因 v3 結構顯示單一 cycle，"
            "「幾乎必然低估」警語已對該筆**降級**（覆核表逐筆標示）。"
        )
        n_awp = sum(
            1 for d in drafts if "acquire_without_place" in d["preannotation_caveat"]
        )
        lines.append("")
        lines.append(
            f"「取必有放」lint（D3-014 裁決 2）：**{n_awp} 筆**命中 "
            "`acquire_without_place`（plan 有 acquire 而同 plan 內其後無收尾；"
            "WARN 標給 IE，非 BLOCK）。"
        )
        lines.append("")
    # D3-015：IE 覆核狀態合併結果（review-state.json；stale 不靜默套用）
    lines.append("## IE 覆核狀態合併（review-state.json；--force 重產後存活）")
    lines.append("")
    if not review_state_present:
        lines.append(
            "（out 目錄無 `review-state.json`——本輪未套用任何覆核狀態。首輪 harvest "
            "屬正常；IE 覆核後由工程端把裁決記入 state 檔，之後每輪重產自動合併。）"
        )
    else:
        lines.append(
            f"套用 **{len(review_applied)} 筆**（草稿帶 `ie_review` 區塊；"
            "配對鍵＝normalized_text sha256 前 8 碼，與流水號無關）："
            f"{'、'.join(f'`{i}`' for i in review_applied) or '（無）'}"
        )
        lines.append("")
        if review_stale:
            lines.append(
                f"**⚠️ stale {len(review_stale)} 筆——未套用**（狀態所依據的內容已變，"
                "不靜默沿用；IE 需重看後更新 state 檔）："
            )
            lines.append("")
            for s in review_stale:
                lines.append(
                    f"- `{s['sha8']}`（{s['reason']}）：「{s.get('source_text') or '（無原文記錄）'}」"
                )
        else:
            lines.append("stale：0 筆（所有覆核狀態都配對到內容未變的草稿）。")
        if review_promoted:
            lines.append("")
            lines.append(
                f"已轉正（promoted）entry：**{len(review_promoted)} 筆**——跳過合併"
                "（句子已在 tests/gold/wi_plans/，不再產草稿；entry 保留為轉正軌跡）："
            )
            lines.append("")
            for s in review_promoted:
                lines.append(
                    f"- `{s['sha8']}` → `{s['promoted_to']}`："
                    f"「{s.get('source_text') or '（無原文記錄）'}」"
                )
    lines.append("")
    dropped = [c for c in all_candidates if c not in selected]
    lines.append(f"## 未入選候選（{len(dropped)} 筆；多樣性選擇額度用罄，非品質淘汰）")
    lines.append("")
    lines.append(
        "coverage-optimized 取樣會把同維度重複的候選排到額度外——以下清單供 IE 檢視"
        "是否有應優先的真實案例（用 `--limit` 放寬或手動指定補進下一輪）："
    )
    lines.append("")
    for c in dropped:
        true_dims = [k for k in DIM_KEYS if c.tags.get(k) is True]
        lines.append(f"- 「{c.raw}」（命中：{'、'.join(true_dims) or '無'}）")
    lines.append("")
    lines.append("## 已知系統性偏差（也逐筆寫在草稿的 preannotation_caveat）")
    lines.append("")
    n_multi = sum(1 for c in selected if c.tags.get("multi_action") is True)
    n_pair = sum(1 for c in selected if take_place_pair(c.norm))
    n_cm_pair = sum(1 for c in selected if take_move_pair(c.norm))
    lines.append(
        f"- rule planner 永遠單 action：{n_multi} 筆多動作候選的預測切分幾乎必然低估"
        "（`likely_multi_action_undercounted`）。"
    )
    lines.append(
        f"- 另 {n_pair} 筆是「取＋放」配對（`take_place_pair_may_be_single_gm`）：MiniMOST 的 "
        "GM 本來就是 G＋P 同一 cycle，**不預設低估**——IE 逐筆裁決建單一 GM 或兩個 action。"
    )
    lines.append(
        f"- 另 {n_cm_pair} 筆是「取/觸＋推/拉」配對（`take_move_pair_may_be_single_cm`）："
        "CM 序列的 G 與 M 本來就在同一 cycle（`docs/core-logic/"
        "minimost-sequence-model-core-logic-spec.md` §2），**不預設低估**——"
        "IE 逐筆裁決建單一 CM 或兩個 action。"
    )
    lines.append(
        "- `challenge_tags` 的 9 個可判維度：`false` 也是啟發式輸出（`heuristic_tags_unverified`"
        " 點名的 quantity/tool_handling/simo_both_hands 已有實證漏標），覆核時 true/false 都要確認。"
    )
    lines.append(
        "- 時間戳注意：v3 遷移資料的 DB 時間是**遷移執行時間**（同一天），"
        "不是原著作時間——temporal_holdout 不能用現有 created_at 定義，"
        "提案見 docs/llm/gold-review/README.md。"
    )
    return "\n".join(lines) + "\n"


# ── 寫檔與守衛 ───────────────────────────────────────────────────────────────

GOLD_DIR = ROOT / "tests" / "gold" / "wi_plans"


def assert_out_dir_safe(out_dir: Path) -> None:
    """絕不寫進正式 gold 目錄（tests/gold/wi_plans）。"""
    resolved = out_dir.resolve()
    if resolved == GOLD_DIR.resolve() or resolved.name == "wi_plans":
        raise SystemExit(
            f"拒絕輸出到 {out_dir}：這是（或同名於）正式 gold 目錄 tests/gold/wi_plans/，"
            "草稿必須放 wi_plans_draft/ 之類的 sibling 目錄。"
        )


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# ── IE 覆核狀態（review-state.json；D3-015）─────────────────────────────────
#
# 為什麼獨立檔而不是寫在草稿上：`--force` 是「整批重產」語意——草稿檔＝管線
# 輸出，可任意重生；IE 的覆核記錄是人的裁決，生命週期不同。裁決寫在草稿上
# 會被下一輪重產（同義詞登記後必然重跑）整批洗掉。
#
# 機制：覆核狀態放 out 目錄的 `review-state.json`（**IE 的檔案，harvest 只讀
# 不寫、--force 不刪**），重產時逐筆合併回對應草稿（寫進草稿的 `ie_review`
# 區塊＋`ie_modified`）。配對鍵＝normalized_text 的 sha256 前 8 碼（草稿檔名
# 後綴同一來源），與流水號無關——第二輪選擇順序改變、編號位移，狀態照樣
# 跟著句子走。
#
# 誠實邊界（stale 不靜默套用，逐條列入 harvest 摘要）：
# - 文字變了 ⇒ sha 變 ⇒ 舊 entry 配不到任何草稿 ⇒ `no_matching_draft`。
# - v3 結構 hint 變了（DB 結構訊號改變）⇒ 當初確認/裁決所依據的證據已不同
#   ⇒ `v3_structure_hint_changed`，IE 需重看。
# - entry 記 `ie_modified: true`（IE 改過 plan 內容）⇒ 本機制只保**覆核詮釋
#   資料**，不保 plan 內容——重產必然以管線輸出蓋掉 plan 編輯，這種 entry
#   拒絕合併（`ie_modified_plan_not_preservable`）；要保 plan 編輯就不要對該
#   目錄 --force，或第二輪人工重套。
# - sha8 相符但完整 sha 不符 ⇒ 不是 stale，是 state 檔損毀/雜湊碰撞 ⇒ 大聲
#   失敗（No error bypass：IE 的裁決寧可擋下重產也不可錯掛）。
#
# D3-019 追加——entry 的「覆核面向」（aspects；至少一個）：
# - 切分（segmentation_*／ie_ruling…）：D3-015 既有欄位，語意不變。
# - 判型（typing_confirmed_by/date＋typing_change_at_review）：IE 確認動詞
#   字典的判型修正照預設。stale 基準＝typing_change_at_review 與草稿 `typing_change`
#   不同（判型在新一輪又變了 ⇒ 確認所依據的值已不同 ⇒ `typing_change_changed`）。
# - P 方向數（p_direction_confirmed_by/date＋p_direction_caveat_at_review）：
#   IE 確認方向數變體照預設。stale 基準＝草稿現行 P 方向旗標與記錄不同
#   （`p_direction_context_changed`）。
# - TMU=0 裁決（zero_tmu_ruling="distance_unstated"＋ruled_by/date）：IE 裁定
#   句子未述距離＝資訊不足——合併時草稿記 `expected_incomplete_reason`
#   （轉正走既有空殼守門的 reason 路徑，不發明距離）。stale 基準＝草稿已無
#   `zero_tmu_distance_unstated` 旗標（`zero_tmu_flag_absent`）。
# D3-026 追加——incomplete 裁決（incomplete_ruling＋ruled_by/date）：IE 逐型
#   裁定 incomplete 草稿（如 X/I 型 CM 句缺核心 M）的缺漏語意——距離/顆數/
#   秒數句面未述（token 見 INCOMPLETE_RULING_TOKENS），合併時原樣寫進草稿
#   `expected_incomplete_reason`（同一誠實記錄路徑，等佈局資料，不發明值）。
#   與 zero_tmu 面向**前提互斥**（zero＝complete 帶 0.0；incomplete＝有
#   incomplete cycle），同 entry 不得並存。stale 基準＝草稿已無 incomplete
#   cycle（`incomplete_premise_absent`——句子在新一輪轉 complete，前提消失）。
# stale 判定是 entry 級 all-or-nothing：任何一個面向的依據變了就整筆 stale
# （確認所依據的證據已不同——IE 重看，不部分沿用）。
#
# 轉正標記：entry 標 `promoted_to`（正式 gold id）＋`promoted_date` ⇒ 該句已
# 在 tests/gold/wi_plans/，harvest 合併時**跳過**（不套用也不算 stale——軌跡
# 保留不刪 entry）；正式 gold ↔ promoted 標記的同進同出守門在
# tests/unit/test_gold_promotion.py。
#
# D3-021 追加——切分來源第三值 `no_contention_batch_confirmed`（批次確認）：
# IE 對「無切分爭點」的案例（草稿無任何 SEGMENTATION_CAVEATS、無 v3 hint）
# 整批確認現行切分（rule planner 的單 action＝single_cycle）。與逐筆確認
# （v3_structure_confirmed）**必須可區分**——批次確認沒有逐筆看過 v3 結構
# 證據，證據力不同，來源值就是區分（投影進草稿 ie_review 與轉正後的 gold 檔）。
# 驗證與 stale 都綁「無爭點」前提：entry 的 hint_at_review 必須是 null（有
# hint＝有爭點，不得走批次）；合併時草稿若長出任何切分旗標（新一輪動詞字典
# 讓配對/多動作旗標出現）⇒ `segmentation_contention_appeared`，確認不沿用。

REVIEW_STATE_FILENAME = "review-state.json"
REVIEW_STATE_SCHEMA_VERSION = "wi-review-state-v1"
# 批次確認（D3-021）：無爭點案例的整批切分確認——與逐筆確認可區分（見上）
REVIEW_SEGMENTATION_SOURCE_BATCH = "no_contention_batch_confirmed"
REVIEW_SEGMENTATION_SOURCES = (
    "v3_structure_confirmed",
    "ie_ruling",
    REVIEW_SEGMENTATION_SOURCE_BATCH,
)
# TMU=0 裁決的唯一合法值（D3-019：IE 判定「句子資訊不足——距離未述」；
# 合併時原樣寫進草稿 expected_incomplete_reason）
ZERO_TMU_RULING_DISTANCE_UNSTATED = "distance_unstated"
# D3-026（第五批）：incomplete 裁決的合法 token——IE 逐型裁決：A/C/D/F 型
# `distance_unstated`（鎖附/推壓距離句面未述）；B 型另帶 `count_unstated`
# （「電動鎖附(多顆)」N 未述——IE 裁：留著等佈局的螺絲群屬性）；G 型另帶
# `x_seconds_required`（清潔秒數也未述）。複合值＝依本 tuple 順序以「+」
# 串接（可讀、決定性——如 "distance_unstated+x_seconds_required"）。
INCOMPLETE_RULING_TOKENS = ("distance_unstated", "count_unstated", "x_seconds_required")
# D3-022（d016 型）：重切裁決的唯一合法值——「本句是製程標題句、不硬切」。
# 語意：IE 確認的 multi_cycle_n 是 module（範本）結構；各列是各自獨立的完整
# 子句、非本句子字串，切不出誠實 evidence span（d026 教訓：不編造），且內容
# 已由各列的獨立 gold/草稿逐筆覆蓋——本句**不重切、不轉正**，留在草稿當
# 多動作辨識參考。轉正端 fail-closed：帶本裁決的 entry 一律擋（見
# promotion_blockers）——「d016 被錯誤轉正」必須紅。
RESEGMENTATION_RULING_TITLE_SENTENCE = "title_sentence_no_resegmentation"
_RULING_RE = re.compile(r"^(single_cycle|multi_cycle_[2-9]\d*)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA8_RE = re.compile(r"^[0-9a-f]{8}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GOLD_ID_RE = re.compile(r"^g\d{2,}_[a-z0-9_]+$")
_SEQ_VALUES = (None, "GM", "CM")
# 各覆核面向的欄位群（load_review_state 驗證「有其一必有全群」，不留半套）
_SEG_ENTRY_KEYS = (
    "segmentation_confirmed_by",
    "segmentation_confirmed_date",
    "segmentation_source",
    "ie_ruling",
    "ie_ruling_notes",
    "plan_pending_resegmentation",
    "ie_rejected_evidence",
    "ruling_history",
)
_TYPING_ENTRY_KEYS = (
    "typing_confirmed_by",
    "typing_confirmed_date",
    "typing_change_at_review",
)
_P_DIR_ENTRY_KEYS = (
    "p_direction_confirmed_by",
    "p_direction_confirmed_date",
    "p_direction_caveat_at_review",
)
_ZERO_TMU_ENTRY_KEYS = ("zero_tmu_ruling", "zero_tmu_ruled_by", "zero_tmu_ruled_date")
# D3-026：incomplete 裁決（缺漏語意逐型釘值）——與 zero_tmu 前提互斥
_INCOMPLETE_ENTRY_KEYS = (
    "incomplete_ruling",
    "incomplete_ruled_by",
    "incomplete_ruled_date",
)
# D3-022 重切裁決（d016 型「標題句不硬切」）：notes 選填、其餘同進同出
_RESEG_ENTRY_KEYS = (
    "resegmentation_ruling",
    "resegmentation_ruled_by",
    "resegmentation_ruled_date",
    "resegmentation_ruling_notes",
)
_PROMOTED_ENTRY_KEYS = ("promoted_to", "promoted_date")
# entry → 草稿 ie_review 區塊要帶的欄位（review_block_from_entry 的唯一出處；
# *_at_review 是 stale 判定基準、promoted_* 是轉正軌跡——都不投影進草稿）
_REVIEW_BLOCK_KEYS = (
    "segmentation_confirmed_by",
    "segmentation_confirmed_date",
    "segmentation_source",
    "ie_ruling",
    "ie_ruling_notes",
    "plan_pending_resegmentation",
    "typing_confirmed_by",
    "typing_confirmed_date",
    "p_direction_confirmed_by",
    "p_direction_confirmed_date",
    "zero_tmu_ruling",
    "zero_tmu_ruled_by",
    "zero_tmu_ruled_date",
    # D3-026：incomplete 裁決投影進草稿（轉正資格與 5h 守門讀 ie_review）
    "incomplete_ruling",
    "incomplete_ruled_by",
    "incomplete_ruled_date",
    # D3-022：重切裁決投影進草稿（notes 帶覆蓋對應事實）——寫在草稿上的版本
    # 會被 --force 洗掉，entry 才是唯一出處，投影讓它在重產後存活
    "resegmentation_ruling",
    "resegmentation_ruled_by",
    "resegmentation_ruled_date",
    "resegmentation_ruling_notes",
)


def draft_json_files(out_dir: Path) -> list[Path]:
    """out 目錄裡的草稿 JSON——排除 review-state.json（IE 的覆核狀態檔不是草稿，
    `--force` 不得刪它、覆蓋守衛不把它當既有草稿）。"""
    return [p for p in sorted(out_dir.glob("*.json")) if p.name != REVIEW_STATE_FILENAME]


def draft_sha8(draft: dict[str, Any]) -> str:
    """草稿的配對鍵＝normalized_text 的 sha256 前 8 碼（與檔名後綴同一來源；
    不用檔名解析——檔名可被改名，normalized_text 是內容本身）。"""
    norm = draft["plan"]["normalized_text"]
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:8]


def _fail_state(path: Path | str, msg: str) -> None:
    raise SystemExit(f"review-state 無效（{path}）：{msg}——IE 覆核狀態不可靜默丟棄，修檔後再跑")


def _require_by_date(path: Path | str, ctx: str, entry: dict, by_key: str, date_key: str) -> None:
    if not (isinstance(entry.get(by_key), str) and entry[by_key].strip()):
        _fail_state(path, f"{ctx}：{by_key} 必填（IE 工號）")
    if not (isinstance(entry.get(date_key), str) and _DATE_RE.match(entry[date_key])):
        _fail_state(path, f"{ctx}：{date_key} 必須是 YYYY-MM-DD")


def _validate_typing_aspect(path: Path | str, ctx: str, entry: dict) -> None:
    """判型確認面向（D3-019）：typing_change_at_review 是 stale 判定基準，
    形狀必須與草稿 `typing_change` 欄相同（舊/新判型且兩者不同）。"""
    _require_by_date(path, ctx, entry, "typing_confirmed_by", "typing_confirmed_date")
    tc = entry.get("typing_change_at_review")
    if not (isinstance(tc, dict) and set(tc) == {"noun_only_seq", "lexicon_seq"}):
        _fail_state(
            path,
            f"{ctx}：typing_change_at_review 必須是 {{noun_only_seq, lexicon_seq}}"
            "（確認所依據的判型值必須記錄，否則 stale 偵測不了）",
        )
    if tc["noun_only_seq"] not in _SEQ_VALUES or tc["lexicon_seq"] not in _SEQ_VALUES:
        _fail_state(path, f"{ctx}：typing_change_at_review 值必須是 GM/CM/null")
    if tc["noun_only_seq"] == tc["lexicon_seq"]:
        _fail_state(path, f"{ctx}：typing_change_at_review 舊/新判型相同——沒有變更就沒有確認題")


def _validate_p_direction_aspect(path: Path | str, ctx: str, entry: dict) -> None:
    _require_by_date(
        path, ctx, entry, "p_direction_confirmed_by", "p_direction_confirmed_date"
    )
    caveat = entry.get("p_direction_caveat_at_review")
    if caveat not in P_DIRECTION_CAVEAT_NAMES:
        _fail_state(
            path,
            f"{ctx}：p_direction_caveat_at_review 必須是 {sorted(P_DIRECTION_CAVEAT_NAMES)}"
            "（確認所依據的方向數旗標必須記錄）",
        )


def incomplete_ruling_canonical_error(ruling: Any) -> str | None:
    """incomplete 裁決 token 的 canonical 形狀檢查（**單一出處**；D3-027）：
    INCOMPLETE_RULING_TOKENS 的非空子集、無重複、依 tuple 順序以「+」串接。
    回傳 None＝合法，否則回傳錯誤描述。state 檔驗證（_validate_incomplete_aspect）
    與正式 gold 的 repo 不變量（test_gold_promotion）共用——gold 檔上的 ruling
    值先前不跑此驗證，壞值（順序亂/自創 token）落檔零測試會紅。"""
    tokens = ruling.split("+") if isinstance(ruling, str) and ruling else []
    canonical = [t for t in INCOMPLETE_RULING_TOKENS if t in set(tokens)]
    if not tokens or tokens != canonical:
        return (
            f"incomplete_ruling={ruling!r} 不合法——必須是 "
            f"{INCOMPLETE_RULING_TOKENS} 的非空子集、無重複、依該順序以「+」串接"
        )
    return None


def _validate_incomplete_aspect(path: Path | str, ctx: str, entry: dict) -> None:
    """incomplete 裁決（D3-026）：ruling＝INCOMPLETE_RULING_TOKENS 的非空子集
    依 tuple 順序以「+」串接（決定性形狀——同義複合值只有一種寫法）。"""
    err = incomplete_ruling_canonical_error(entry.get("incomplete_ruling"))
    if err:
        _fail_state(path, f"{ctx}：{err}")
    _require_by_date(path, ctx, entry, "incomplete_ruled_by", "incomplete_ruled_date")


def _validate_zero_tmu_aspect(path: Path | str, ctx: str, entry: dict) -> None:
    ruling = entry.get("zero_tmu_ruling")
    if ruling != ZERO_TMU_RULING_DISTANCE_UNSTATED:
        _fail_state(
            path,
            f"{ctx}：zero_tmu_ruling 目前唯一合法值是 "
            f"{ZERO_TMU_RULING_DISTANCE_UNSTATED!r}（IE 判定句子資訊不足；"
            "補距離請改 plan/cycle 走 --recompile，不在本欄）",
        )
    _require_by_date(path, ctx, entry, "zero_tmu_ruled_by", "zero_tmu_ruled_date")


def _validate_reseg_aspect(path: Path | str, ctx: str, entry: dict) -> None:
    """重切裁決面向（D3-022，d016 型）：只有一個合法值（fail-closed——新裁決
    型態必須先定義），且必須附著在既有的 multi_cycle 切分記錄上（single_cycle
    沒有「不硬切」可裁）。"""
    ruling = entry.get("resegmentation_ruling")
    if ruling != RESEGMENTATION_RULING_TITLE_SENTENCE:
        _fail_state(
            path,
            f"{ctx}：resegmentation_ruling 目前唯一合法值是 "
            f"{RESEGMENTATION_RULING_TITLE_SENTENCE!r}（IE 裁決標題句不硬切；"
            "其他重切結果走 plan 編輯＋ie_modified=true，不在本欄）",
        )
    _require_by_date(
        path, ctx, entry, "resegmentation_ruled_by", "resegmentation_ruled_date"
    )
    notes = entry.get("resegmentation_ruling_notes")
    if notes is not None and not (isinstance(notes, str) and notes.strip()):
        _fail_state(path, f"{ctx}：resegmentation_ruling_notes 若存在必須是非空字串")
    # 裁決前提：切分記錄存在且為 multi_cycle_n（標題句的結構證據）
    if entry.get("segmentation_source") == "ie_ruling":
        structure = entry.get("ie_ruling")
    else:
        structure = entry.get("v3_structure_hint_at_review")
    if not (isinstance(structure, str) and structure.startswith("multi_cycle_")):
        _fail_state(
            path,
            f"{ctx}：{RESEGMENTATION_RULING_TITLE_SENTENCE} 的前提是 multi_cycle "
            f"切分記錄（標題句對應多列），得到 {structure!r}",
        )


def _validate_promoted_marker(path: Path | str, ctx: str, entry: dict) -> None:
    """轉正標記：promoted_to（正式 gold id）＋promoted_date 同進同出——
    軌跡保留（entry 不刪），harvest 合併時跳過。"""
    target = entry.get("promoted_to")
    if not (isinstance(target, str) and _GOLD_ID_RE.match(target)):
        _fail_state(
            path, f"{ctx}：promoted_to 必須是正式 gold id（gNN_slug 形式）"
        )
    if not (
        isinstance(entry.get("promoted_date"), str)
        and _DATE_RE.match(entry["promoted_date"])
    ):
        _fail_state(path, f"{ctx}：promoted_date 必須是 YYYY-MM-DD")


def load_review_state(path: Path) -> dict[str, dict[str, Any]]:
    """讀取並驗證 review-state.json；檔案不存在＝空狀態（首輪合法）。

    驗證是硬的（SystemExit）：state 檔是 IE 裁決的唯一載體，格式錯誤若被吞掉，
    合併就會靜默漏套——寧可擋下 harvest。"""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail_state(path, f"不是有效 JSON：{exc}")
    if not isinstance(data, dict):
        _fail_state(path, "頂層必須是 object")
    if data.get("schema_version") != REVIEW_STATE_SCHEMA_VERSION:
        _fail_state(
            path,
            f"schema_version={data.get('schema_version')!r}，"
            f"預期 {REVIEW_STATE_SCHEMA_VERSION!r}",
        )
    entries = data.get("entries")
    if not isinstance(entries, dict) or not entries:
        _fail_state(path, "entries 必須是非空 object（sha8 → entry）")
    for sha8, entry in entries.items():
        ctx = f"entries[{sha8!r}]"
        if not _SHA8_RE.match(sha8):
            _fail_state(path, f"{ctx}：鍵必須是 8 碼小寫十六進位（草稿檔名後綴）")
        if not isinstance(entry, dict):
            _fail_state(path, f"{ctx}：必須是 object")
        full = entry.get("norm_sha256")
        if not (isinstance(full, str) and _SHA256_RE.match(full)):
            _fail_state(path, f"{ctx}：norm_sha256 必須是 64 碼 sha256")
        if full[:8] != sha8:
            _fail_state(path, f"{ctx}：norm_sha256 前 8 碼 {full[:8]} 與鍵不一致")
        if not (isinstance(entry.get("source_text"), str) and entry["source_text"].strip()):
            _fail_state(path, f"{ctx}：source_text 必填（人讀對照用）")
        if not isinstance(entry.get("ie_modified"), bool):
            _fail_state(path, f"{ctx}：ie_modified 必填 true|false")
        # 面向偵測（D3-019）：有其一欄位＝宣告該面向 ⇒ 該面向欄位群必須完整
        has_seg = any(k in entry for k in _SEG_ENTRY_KEYS)
        has_typing = any(k in entry for k in _TYPING_ENTRY_KEYS)
        has_pdir = any(k in entry for k in _P_DIR_ENTRY_KEYS)
        has_zero = any(k in entry for k in _ZERO_TMU_ENTRY_KEYS)
        has_incomplete = any(k in entry for k in _INCOMPLETE_ENTRY_KEYS)
        has_reseg = any(k in entry for k in _RESEG_ENTRY_KEYS)
        has_promoted = any(k in entry for k in _PROMOTED_ENTRY_KEYS)
        if not (has_seg or has_typing or has_pdir or has_zero or has_incomplete):
            _fail_state(
                path,
                f"{ctx}：entry 至少要有一個覆核面向"
                "（切分／判型／P 方向數／TMU=0 裁決／incomplete 裁決）"
                "——空 entry 不是覆核記錄",
            )
        if has_zero and has_incomplete:
            # 前提互斥：zero_tmu＝「complete 帶 TMU=0.0」、incomplete＝「有
            # incomplete cycle」——同一句不可能同時成立；兩面向都寫進同一個
            # expected_incomplete_reason，並存＝值互踩
            _fail_state(
                path,
                f"{ctx}：zero_tmu 與 incomplete 裁決前提互斥（complete+0.0 vs "
                "incomplete cycle），同 entry 不得並存",
            )
        if has_typing:
            _validate_typing_aspect(path, ctx, entry)
        if has_pdir:
            _validate_p_direction_aspect(path, ctx, entry)
        if has_zero:
            _validate_zero_tmu_aspect(path, ctx, entry)
        if has_incomplete:
            _validate_incomplete_aspect(path, ctx, entry)
        if has_reseg:
            if not has_seg:
                _fail_state(
                    path,
                    f"{ctx}：重切裁決必須附著在切分面向上"
                    "（沒有切分記錄就沒有「不硬切」的對象）",
                )
            _validate_reseg_aspect(path, ctx, entry)
        if has_promoted:
            _validate_promoted_marker(path, ctx, entry)
        if not has_seg:
            continue
        if not (
            isinstance(entry.get("segmentation_confirmed_by"), str)
            and entry["segmentation_confirmed_by"].strip()
        ):
            _fail_state(path, f"{ctx}：segmentation_confirmed_by 必填（IE 工號）")
        if not (
            isinstance(entry.get("segmentation_confirmed_date"), str)
            and _DATE_RE.match(entry["segmentation_confirmed_date"])
        ):
            _fail_state(path, f"{ctx}：segmentation_confirmed_date 必須是 YYYY-MM-DD")
        src = entry.get("segmentation_source")
        if src not in REVIEW_SEGMENTATION_SOURCES:
            _fail_state(
                path, f"{ctx}：segmentation_source 必須是 {REVIEW_SEGMENTATION_SOURCES}"
            )
        if "v3_structure_hint_at_review" not in entry:
            _fail_state(
                path,
                f"{ctx}：v3_structure_hint_at_review 必填（可為 null）——"
                "沒有它就無法偵測「確認所依據的結構證據已改變」",
            )
        hint_at = entry["v3_structure_hint_at_review"]
        ruling = entry.get("ie_ruling")
        if src == "v3_structure_confirmed":
            # 「照 v3 結構預設 OK」——被確認的預設必須真的存在（非 ambiguous）
            if not (isinstance(hint_at, str) and _RULING_RE.match(hint_at)):
                _fail_state(
                    path,
                    f"{ctx}：v3_structure_confirmed 但 hint_at_review={hint_at!r} "
                    "不是可確認的結構答案（single_cycle/multi_cycle_n）",
                )
            if ruling is not None:
                _fail_state(path, f"{ctx}：確認≠裁決——v3_structure_confirmed 不得帶 ie_ruling")
        elif src == REVIEW_SEGMENTATION_SOURCE_BATCH:
            # D3-021 批次確認：對象限「無切分爭點」案例——有 v3 hint＝有爭點，
            # 必須走逐筆確認/裁決；批次來源混用逐筆語意＝證據力造假
            if hint_at is not None:
                _fail_state(
                    path,
                    f"{ctx}：{REVIEW_SEGMENTATION_SOURCE_BATCH} 但 "
                    f"hint_at_review={hint_at!r}——批次確認的對象是無切分爭點的"
                    "草稿（無 v3 hint）；有結構 hint 的案例走逐筆 "
                    "v3_structure_confirmed/ie_ruling",
                )
            if ruling is not None:
                _fail_state(
                    path,
                    f"{ctx}：確認≠裁決——{REVIEW_SEGMENTATION_SOURCE_BATCH} "
                    "不得帶 ie_ruling",
                )
        else:  # ie_ruling
            if not (isinstance(ruling, str) and _RULING_RE.match(ruling)):
                _fail_state(
                    path, f"{ctx}：ie_ruling 必須是 single_cycle 或 multi_cycle_n（n≥2）"
                )
        pending = entry.get("plan_pending_resegmentation")
        if pending is not None:
            if not isinstance(pending, bool):
                _fail_state(path, f"{ctx}：plan_pending_resegmentation 必須是 bool")
            if pending and not (isinstance(ruling, str) and ruling.startswith("multi_cycle_")):
                _fail_state(
                    path,
                    f"{ctx}：plan_pending_resegmentation 只在 multi_cycle 裁決下有意義"
                    "（單 cycle 沒有「等重切」）",
                )
        rejected = entry.get("ie_rejected_evidence")
        if rejected is not None:
            if not (isinstance(rejected, list) and rejected):
                _fail_state(path, f"{ctx}：ie_rejected_evidence 若存在必須是非空 list")
            for r in rejected:
                if not (
                    isinstance(r, dict)
                    and isinstance(r.get("table"), str)
                    and isinstance(r.get("id"), str)
                ):
                    _fail_state(path, f"{ctx}：ie_rejected_evidence 條目需 {{table, id}}")
        # 更正軌跡（標準答案集的更正不能是無痕覆寫）：entry 被更正時，先前的
        # 裁決與更正理由記在 ruling_history——若存在，形狀必須完整，否則
        # 「保留軌跡」只是空殼宣稱。條目兩型（fail-closed：非此二型即擋）：
        # - 切分裁決更正（D3-015/D3-022 既有）：帶有效 `ie_ruling`（先前答案）。
        # - 面向退場（D3-024，d0350279 型）：帶 `superseded_aspects`——判型/
        #   P 方向/TMU=0 面向的依據在新一輪消失（如判型棄權讓 typing_change
        #   旗標不再存在）時，stale 重確認的過程記錄：退場面向的欄位原值全文
        #   搬進 superseded_aspects（不無痕刪除），entry 本體只留仍有依據的
        #   面向。切分面向不得走此型（切分更正走 ie_ruling 型；標題句另有
        #   resegmentation_ruling 欄）。
        history = entry.get("ruling_history")
        if history is not None:
            if not (isinstance(history, list) and history):
                _fail_state(
                    path, f"{ctx}：ruling_history 若存在必須是非空 list（更正軌跡不可是空殼）"
                )
            retire_allowed = (
                set(_TYPING_ENTRY_KEYS)
                | set(_P_DIR_ENTRY_KEYS)
                | set(_ZERO_TMU_ENTRY_KEYS)
                | set(_INCOMPLETE_ENTRY_KEYS)
            )
            for h in history:
                if not isinstance(h, dict):
                    _fail_state(path, f"{ctx}：ruling_history 條目必須是 object")
                prev_ruling = h.get("ie_ruling")
                aspects = h.get("superseded_aspects")
                if aspects is not None:
                    if prev_ruling is not None:
                        _fail_state(
                            path,
                            f"{ctx}：ruling_history 條目不得同時是切分更正（ie_ruling）"
                            "與面向退場（superseded_aspects）——兩型分開記",
                        )
                    if not (isinstance(aspects, dict) and aspects):
                        _fail_state(
                            path,
                            f"{ctx}：superseded_aspects 必須是非空 object（退場面向的原值全文）",
                        )
                    bad = sorted(set(aspects) - retire_allowed)
                    if bad:
                        _fail_state(
                            path,
                            f"{ctx}：superseded_aspects 含不可退場欄位 {bad}"
                            "（只有判型/P 方向/TMU=0/incomplete 面向可退場；"
                            "切分走 ie_ruling 型）",
                        )
                    # D3-024 複審 M1：退場記錄的**值**依面向分組跑同一批
                    # _validate_*_aspect（單一出處，不另抄）——「原值全文保留」
                    # 若保留的是 garbage（壞日期/非法 seq/半套面向），軌跡即空殼。
                    hctx = f"{ctx}.ruling_history[].superseded_aspects"
                    if any(k in aspects for k in _TYPING_ENTRY_KEYS):
                        _validate_typing_aspect(path, hctx, aspects)
                    if any(k in aspects for k in _P_DIR_ENTRY_KEYS):
                        _validate_p_direction_aspect(path, hctx, aspects)
                    if any(k in aspects for k in _ZERO_TMU_ENTRY_KEYS):
                        _validate_zero_tmu_aspect(path, hctx, aspects)
                    if any(k in aspects for k in _INCOMPLETE_ENTRY_KEYS):
                        _validate_incomplete_aspect(path, hctx, aspects)
                    # 假退場：退場鍵不得同時存在於 entry 本體——退場＝搬移
                    # 非複製（entry 同時持有完整面向＝面向根本沒退場）
                    dup = sorted(k for k in aspects if k in entry)
                    if dup:
                        _fail_state(
                            path,
                            f"{ctx}：superseded_aspects 的退場鍵 {dup} 仍存在於 "
                            "entry 本體——退場是搬移不是複製，本體必須移除退場面向",
                        )
                elif not (isinstance(prev_ruling, str) and _RULING_RE.match(prev_ruling)):
                    _fail_state(
                        path, f"{ctx}：ruling_history 條目缺有效 ie_ruling（先前答案必須保留）"
                    )
                if not (
                    isinstance(h.get("supersede_reason"), str)
                    and h["supersede_reason"].strip()
                ):
                    _fail_state(
                        path,
                        f"{ctx}：ruling_history 條目缺 supersede_reason（為何更正必須寫明）",
                    )
                if not (
                    isinstance(h.get("superseded_date"), str)
                    and _DATE_RE.match(h["superseded_date"])
                ):
                    _fail_state(
                        path, f"{ctx}：ruling_history 條目的 superseded_date 必須是 YYYY-MM-DD"
                    )
    return entries


def review_block_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """state entry → 草稿的 `ie_review` 區塊（單一出處：合併與 schema 守門測試
    共用本函式，不允許兩邊投影規則漂移）。"""
    return {k: entry[k] for k in _REVIEW_BLOCK_KEYS if entry.get(k) is not None}


def apply_review_state_entry(draft: dict[str, Any], entry: dict[str, Any]) -> str | None:
    """把單筆覆核狀態合併進草稿；回傳 None＝已套用、字串＝stale 原因（未動草稿）。

    所有前置檢查先做完才落筆——不留半套狀態。stale 是 entry 級 all-or-nothing：
    任一面向的依據變了就整筆不套（確認所依據的證據已不同，IE 重看）。"""
    norm = draft["plan"]["normalized_text"]
    full = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    if entry["norm_sha256"] != full:
        raise SystemExit(
            f"review-state 完整性失敗：entry {entry['norm_sha256'][:8]} 的 norm_sha256 "
            f"與草稿 {draft.get('id')} 的 normalized_text sha 不符——"
            "state 檔損毀或雜湊碰撞，不是 stale，人工排查後再跑"
        )
    if entry.get("ie_modified") is True:
        return "ie_modified_plan_not_preservable"
    if entry.get("v3_structure_hint_at_review") != draft.get("v3_structure_hint"):
        return "v3_structure_hint_changed"
    rejected = entry.get("ie_rejected_evidence") or []
    sources = (draft.get("v3_structure_evidence") or {}).get("sources") or []
    source_keys = {(s["table"], s["id"]) for s in sources}
    if any((r["table"], r["id"]) not in source_keys for r in rejected):
        return "rejected_evidence_missing"
    caveats = draft.get("preannotation_caveat") or []
    if entry.get("segmentation_source") == REVIEW_SEGMENTATION_SOURCE_BATCH:
        # D3-021：批次確認的前提＝該句無切分爭點。新一輪若長出任何切分旗標
        # （動詞字典擴充讓配對/多動作旗標出現），前提已不成立——批次確認
        # 不得沿用（IE 沒逐筆看過爭點），整筆 stale 交 IE 重看
        if any(c in caveats for c in SEGMENTATION_CAVEATS):
            return "segmentation_contention_appeared"
    if "typing_change_at_review" in entry:
        # 判型確認的依據＝當時的舊/新判型值；新一輪判型又變了就不得沿用確認
        if draft.get("typing_change") != entry["typing_change_at_review"]:
            return "typing_change_changed"
    if "p_direction_caveat_at_review" in entry:
        current = [c for c in caveats if c in P_DIRECTION_CAVEAT_NAMES]
        if current != [entry["p_direction_caveat_at_review"]]:
            return "p_direction_context_changed"
    if "zero_tmu_ruling" in entry:
        # 裁決前提＝該筆 complete 但 TMU=0.0；旗標消失（TMU 變真值或退回
        # incomplete）＝前提已不成立
        if ZERO_TMU_CAVEAT not in caveats:
            return "zero_tmu_flag_absent"
    if "incomplete_ruling" in entry:
        # D3-026：裁決前提＝該筆有 incomplete cycle（佈局資訊句面未述）；
        # 新一輪全部 cycle 轉 complete（不論 TMU）＝前提消失，裁決不得沿用
        if not any(
            c.get("complete") is False for c in draft.get("expected_cycles") or []
        ):
            return "incomplete_premise_absent"
    draft["ie_review"] = review_block_from_entry(entry)
    draft["ie_modified"] = False  # 確認≠修改（entry 的 ie_modified=true 已在上面拒絕）
    for r in rejected:
        for s in sources:
            if (s["table"], s["id"]) == (r["table"], r["id"]):
                # IE 裁決否定的結構：證據保留不刪，標記讓覆核表/後人看得到
                s["ie_ruling_rejected"] = True
    if entry.get("zero_tmu_ruling"):
        # D3-019：TMU=0 裁決落地＝走既有 expected_incomplete_reason 機制
        # （空殼守門的誠實記錄路徑；不發明距離）
        draft["expected_incomplete_reason"] = entry["zero_tmu_ruling"]
    if entry.get("incomplete_ruling"):
        # D3-026：incomplete 裁決落地＝同一 expected_incomplete_reason 機制
        # （與 zero_tmu 前提互斥已在 load_review_state 硬驗，不會互踩）
        draft["expected_incomplete_reason"] = entry["incomplete_ruling"]
    return None


def merge_review_state(
    drafts: list[dict[str, Any]], entries: dict[str, dict[str, Any]]
) -> tuple[list[str], list[dict[str, Any]]]:
    """整批合併：回傳（已套用草稿 id 排序清單, stale 條目清單）。決定性：
    entry 依 sha8 排序處理，輸出穩定。

    stale 條目附原 entry（`entry` 鍵）——覆核表 banner 要印**先前裁決的內容**
    （D3-023 複審必修 1），拆掉附帶＝banner 只剩指標，測試會紅。

    標 `promoted_to` 的 entry 跳過（不套用也不算 stale）：該句已在正式 gold、
    不再產草稿——entry 保留是轉正軌跡，不是待合併狀態。"""
    by_sha8: dict[str, dict[str, Any]] = {}
    for d in drafts:
        key = draft_sha8(d)
        if key in by_sha8:  # pragma: no cover — 去重後同 norm 不會出現兩筆
            raise SystemExit(f"草稿 sha8 重複：{key}（{by_sha8[key]['id']} vs {d['id']}）")
        by_sha8[key] = d
    applied: list[str] = []
    stale: list[dict[str, Any]] = []
    for sha8 in sorted(entries):
        entry = entries[sha8]
        if entry.get("promoted_to"):
            continue
        draft = by_sha8.get(sha8)
        if draft is None:
            stale.append(
                {"sha8": sha8, "reason": "no_matching_draft",
                 "source_text": entry.get("source_text"), "entry": entry}
            )
            continue
        reason = apply_review_state_entry(draft, entry)
        if reason is None:
            applied.append(draft["id"])
        else:
            stale.append(
                {"sha8": sha8, "reason": reason,
                 "source_text": entry.get("source_text"), "entry": entry}
            )
    return sorted(applied), stale


async def cmd_harvest(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    assert_out_dir_safe(out_dir)  # 守衛在任何 DB 存取之前：絕不寫進正式 gold 目錄

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL 未設定", file=sys.stderr)
        return 1

    review_dir = Path(args.review_dir)

    _RULE_SET_CODE_HOLDER["code"] = args.rule_set_code
    records, counts = await fetch_source_records(database_url)
    synonyms = _SYNONYMS_HOLDER["rows"]
    candidates = build_candidates(records)
    gold_norms = existing_gold_norms()
    already_gold = [c for c in candidates if c.norm in gold_norms]
    all_candidates = [c for c in candidates if c.norm not in gold_norms]
    selected = select_diverse(all_candidates, args.limit)

    out_dir.mkdir(parents=True, exist_ok=True)
    # review-state.json 不是草稿：不觸發覆蓋守衛、--force 不刪（IE 的覆核狀態檔）
    existing = [p.name for p in draft_json_files(out_dir)]
    if existing and not args.force:
        raise SystemExit(
            f"{out_dir} 已有 {len(existing)} 個草稿（可能含 IE 編輯），不覆蓋。"
            "確定要整批重產請加 --force。"
        )
    if args.force:
        for p in draft_json_files(out_dir):
            p.unlink()

    rs = build_from_seed_v2()  # 一次 build，逐筆共用（不進迴圈）
    component_of = compute_split_components(selected)
    drafts: list[dict[str, Any]] = []
    for i, cand in enumerate(selected, start=1):
        draft_id = f"d{i:03d}_{cand.sha[:8]}"
        drafts.append(
            await preannotate(
                cand,
                synonyms,
                draft_id,
                rs,
                split_component=component_of[cand.split_groups[0]],
                module_structure=_MODULE_STRUCTURE_HOLDER["rows"],
            )
        )

    # D3-015：合併 IE 覆核狀態（--force 重產後存活的機制）——寫檔前合併，
    # 草稿落地即帶狀態；stale 不靜默套用，列入摘要
    state_path = out_dir / REVIEW_STATE_FILENAME
    review_entries = load_review_state(state_path)
    review_applied, review_stale = merge_review_state(drafts, review_entries)
    review_promoted = [
        {
            "sha8": sha8,
            "promoted_to": e["promoted_to"],
            "source_text": e.get("source_text"),
        }
        for sha8, e in sorted(review_entries.items())
        if e.get("promoted_to")
    ]

    for d in drafts:
        (out_dir / f"{d['id']}.json").write_text(_dump(d), encoding="utf-8")

    review_dir.mkdir(parents=True, exist_ok=True)
    # stale 清單也進覆核表（該筆印先前裁決 banner）——不只摘要一句話
    (review_dir / "review-checklist.md").write_text(
        build_review_checklist(drafts, review_stale=review_stale), encoding="utf-8"
    )
    summary = build_summary(
        counts,
        all_candidates,
        selected,
        synonyms,
        args.limit,
        already_gold=already_gold,
        drafts=drafts,
        review_state_present=bool(review_entries),
        review_applied=review_applied,
        review_stale=review_stale,
        review_promoted=review_promoted,
    )
    (review_dir / "harvest-summary.md").write_text(summary, encoding="utf-8")

    print(f"草稿 → {out_dir}（{len(drafts)} 筆）")
    print(f"覆核表 → {review_dir / 'review-checklist.md'}")
    print(f"摘要 → {review_dir / 'harvest-summary.md'}")
    print()
    print(summary)
    return 0


def is_formal_gold_path(path: Path) -> bool:
    """檔案是否落在正式 gold 目錄（tests/gold/wi_plans/ 或任何同名 wi_plans 目錄）。"""
    resolved = path.resolve()
    return resolved.parent == GOLD_DIR.resolve() or resolved.parent.name == "wi_plans"


def assert_recompile_targets_safe(paths: list[str], *, relock_approved: bool) -> None:
    """--recompile 對正式 gold 的守衛（No error bypass）。

    已核准 gold 的 expected_* 是鎖點——「引擎改壞 → gold 紅 → recompile → 綠」
    不准零摩擦。落在 wi_plans/ 的路徑預設拒絕；顯式 --relock-approved --reason
    才放行（reason 會寫進檔案 notes 留痕）。整批先驗再動手：不留半改狀態。
    """
    if relock_approved:
        return
    blocked = [p for p in paths if is_formal_gold_path(Path(p))]
    if blocked:
        raise SystemExit(
            "拒絕 recompile 正式 gold（expected_* 是鎖點，改寫等同繞過紅燈）：\n  "
            + "\n  ".join(blocked)
            + '\n引擎/規則變更需重鎖時，顯式加 --relock-approved --reason "原因"'
            "（reason 會寫進檔案 notes），並在 commit 訊息記錄。"
        )


async def cmd_recompile(
    paths: list[str], *, relock_approved: bool = False, reason: str | None = None
) -> int:
    """IE 改完 plan 後：以檔內 plan+synthetic_synonyms 重算 expected_cycles/expected。

    不跑 planner（plan 是 IE 的裁決）；TMU 唯一出處仍為 most_engine。
    rule_set_code 讀檔內值（與 gold_eval.case_rule_set_code 同一出處）。
    """
    if relock_approved and not (reason or "").strip():
        raise SystemExit('--relock-approved 必須帶 --reason "原因"（會寫進檔案 notes 留痕）')
    assert_recompile_targets_safe(paths, relock_approved=relock_approved)

    rc = 0
    rs = build_from_seed_v2()  # 一次 build，逐檔共用
    for p in paths:
        path = Path(p)
        data = json.loads(path.read_text(encoding="utf-8"))
        plan = WorkInstructionPlan.model_validate(data["plan"])
        synonyms = data.get("synthetic_synonyms") or []
        linker = SlotLinker(synonyms)
        candidates = await linker.link(plan)
        drafts = compile_plan(
            plan,
            candidates,
            rule_set_code=case_rule_set_code(data),
            allow_lists=allow_lists_from_rule_set(rs),
            face_hit_params=linker.face_hit_params(plan),
        )
        drafts = apply_engine_gate(drafts, rs)
        status, reasons = compute_routing(plan, candidates, drafts, auto_enabled=False)
        data["expected_cycles"] = [expected_cycle_from_draft(d) for d in drafts]
        data["expected"] = {"action_count": len(plan.actions), "routing_status": status}
        if isinstance(data.get("preannotation"), dict):
            data["preannotation"]["routing_reasons"] = list(reasons)
        caveats = data.get("preannotation_caveat")
        if isinstance(caveats, list):
            # acquire_without_place 是 plan 的函數（裁決 2）：IE 改完 plan 重算時
            # 同步——補了「放」旗標就摘掉、改出「取而無放」就掛上；不動其他旗標
            has_lint = acquire_without_place(data["plan"]["actions"])
            if has_lint and "acquire_without_place" not in caveats:
                caveats.append("acquire_without_place")
            elif not has_lint and "acquire_without_place" in caveats:
                caveats.remove("acquire_without_place")
        if relock_approved and is_formal_gold_path(path):
            prev = data.get("notes") or ""
            data["notes"] = (prev + "\n" if prev else "") + f"relock_approved: {reason}"
        path.write_text(_dump(data), encoding="utf-8")
        print(f"recompiled {path.name}: actions={len(plan.actions)} routing={status}")
    return rc


# ── 轉正（草稿 → 正式 gold；docs/llm/gold-review/README.md「核准→轉正」工作流）──
#
# 資格（D3-019 首批轉正；**全部滿足才轉**，promotion_blockers 是唯一出處，
# repo 守門在 tests/unit/test_gold_promotion.py）：
# 1. 切分已確認（review-state entry 的切分面向；41 筆內）。
# 2. 確認/裁決的結構與 plan 一致——multi_cycle_n 確認但 plan 未重切（rule
#    planner 恆 1 action）不得原樣轉正。
# 3. 判型/P 方向數/TMU=0 等旗標全部有對應確認或裁決（未確認旗標＝未解決的
#    覆核提問）；acquire_without_place／engine_rejected_cycle 未解決＝擋。
# 4. 實質內容：至少一個 complete 帶 total_tmu > 0 的 cycle，或顯式
#    expected_incomplete_reason（D3-018 M1 空殼守門的兩條合法路徑）。
# 5. S 檢：plan.normalized_text 與至少一筆 source_provenance.raw_text 正規化後
#    一致（真實案例守門）。
# 6. D3-022 追加：IE 重切（plan 編輯）走同一工作流——entry 的 ie_modified
#    宣告與草稿的 ie_edited 狀態必須一致（兩方向都擋，見 promotion_blockers），
#    payload 的 ie_modified 以 entry 為準（true＝計入 Plan 層指標）；帶
#    resegmentation_ruling（標題句不硬切）的 entry 一律擋轉正。
# 落筆語意：整批先驗再動手（一筆不合格＝一筆都不寫）；compile 段預檢全綠才
# 落筆（任何一筆紅＝該筆期望值有問題，撤回該筆，不准為過而改期望）；轉正後
# review-state entry 標 promoted_to/promoted_date（軌跡保留不刪）。

PROMOTION_SPLITS = ("train", "calibration", "test", "temporal_holdout")
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def provenance_matches_normalized_text(data: dict[str, Any]) -> bool:
    """S 檢（R5）：plan.normalized_text 與至少一筆 source_provenance.raw_text
    正規化後一致（同一支 normalize——harvest 的去重鍵就是 normalize(raw)）。
    schema 守門測試與 promotion_blockers 共用本函式。"""
    norm_text = (data.get("plan") or {}).get("normalized_text")
    return any(
        normalize(str(s.get("raw_text") or "")) == norm_text
        for s in data.get("source_provenance") or []
    )


def substance_blockers(data: dict[str, Any]) -> list[str]:
    """空殼守門（D3-018 M1 同語意）：complete 帶 TMU>0，或顯式
    expected_incomplete_reason——TMU=0.0 非真值，不算實質內容。"""
    cycles = data.get("expected_cycles") or []
    has_substance = any(
        c.get("complete") is True and (c.get("total_tmu") or 0) > 0 for c in cycles
    )
    reason = data.get("expected_incomplete_reason")
    if not has_substance and not (isinstance(reason, str) and reason.strip()):
        return [
            "無任何 complete=true 帶 total_tmu > 0 的 cycle，也無顯式 "
            "expected_incomplete_reason（TMU=0.0 非真值；資訊不足要誠實寫出來）"
        ]
    return []


def caveat_resolution_blockers(data: dict[str, Any]) -> list[str]:
    """逐旗標檢查「未解決的 caveat 提問」：每個 preannotation_caveat 都要有
    對應的 IE 確認/裁決（檔內 ie_review／expected_incomplete_reason），否則擋。
    未知旗標 fail-closed——新旗標必須先定義解法才可轉正。"""
    ir = data.get("ie_review") or {}
    blockers: list[str] = []
    for c in data.get("preannotation_caveat") or []:
        if c in SEGMENTATION_CAVEATS:
            if not ir.get("segmentation_confirmed_by"):
                blockers.append(f"{c}：切分未確認（無 IE 確認/裁決）")
        elif c == TYPING_CHANGED_CAVEAT:
            if not ir.get("typing_confirmed_by"):
                blockers.append(f"{c}：判型修正未經 IE 確認")
        elif c in P_DIRECTION_CAVEAT_NAMES:
            if not ir.get("p_direction_confirmed_by"):
                blockers.append(f"{c}：P 方向數未經 IE 確認")
        elif c == ZERO_TMU_CAVEAT:
            reason = data.get("expected_incomplete_reason")
            if not (
                ir.get("zero_tmu_ruling")
                and isinstance(reason, str)
                and reason.strip()
            ):
                blockers.append(
                    f"{c}：TMU=0.0 未經 IE 裁決（需 zero_tmu_ruling＋"
                    "expected_incomplete_reason）"
                )
        elif c == X_CLEAN_CONTEXT_CAVEAT:
            # D3-021：IE 只裁了吹風情境的「清潔」——非吹風情境尚無裁決，
            # 無確認機制可解此旗標（fail-closed；下輪 IE 裁了再開機制）
            blockers.append(
                f"{c}：「清潔」非吹風情境（句面無風槍/吹風）——IE 只裁了吹風"
                "情境（D3-021），本句建法未裁，不得套 x_blow_clean 轉正"
            )
        else:
            blockers.append(f"{c}：未解決的覆核旗標（無對應確認機制，fail-closed）")
    return blockers


def structure_consistency_blockers(data: dict[str, Any]) -> list[str]:
    """確認/裁決的切分結構 ⇄ plan 一致性：single_cycle → plan 恰 1 action；
    multi_cycle_n → plan 恰 n action。rule planner 恆 1 action——multi_cycle
    確認下原樣轉正＝把 IE 已否定的切分寫進標準答案。"""
    ir = data.get("ie_review") or {}
    if not ir.get("segmentation_confirmed_by"):
        return []  # 切分未確認由 promotion_blockers 另擋
    if ir.get("segmentation_source") == "ie_ruling":
        confirmed = ir.get("ie_ruling")
    elif ir.get("segmentation_source") == REVIEW_SEGMENTATION_SOURCE_BATCH:
        # D3-021 批次確認：確認對象＝無爭點案例的現行切分（rule planner 單
        # action）＝single_cycle；plan 若不是 1 action，「無爭點」前提本身有假
        confirmed = STRUCTURE_HINT_SINGLE
    else:
        confirmed = data.get("v3_structure_hint")
    n = _structure_hint_cycles(confirmed)
    if n is None:
        return [f"確認的切分結構 {confirmed!r} 無法對應 cycle 數"]
    actions = len((data.get("plan") or {}).get("actions") or [])
    if actions != n:
        return [
            f"切分確認為 {confirmed}（{n} cycle）但 plan 有 {actions} 個 action——"
            "plan 未重切，不得原樣轉正"
        ]
    return []


def promotion_blockers(
    draft: dict[str, Any], entry: dict[str, Any] | None
) -> list[str]:
    """單筆草稿的轉正資格檢查（唯一出處；空 list＝合格）。"""
    blockers: list[str] = []
    if entry is None:
        blockers.append("review-state 無對應 entry（切分未確認——不在 IE 覆核集合內）")
    elif entry.get("promoted_to"):
        blockers.append(f"entry 已標 promoted_to={entry['promoted_to']}（不可重複轉正）")
    ir = draft.get("ie_review")
    if not ir:
        blockers.append("草稿無 ie_review（覆核狀態未合併或 stale——先跑 harvest 合併）")
    else:
        if not ir.get("segmentation_confirmed_by"):
            blockers.append("切分維度未確認（ie_review 無 segmentation_confirmed_by）")
        if entry is not None and ir != review_block_from_entry(entry):
            blockers.append("ie_review 與 state entry 投影不一致（草稿過時，重跑 harvest）")
    if draft.get("ie_modified") is True:
        blockers.append(
            "草稿 ie_modified=true——該欄是轉正時的宣告（來源＝state entry 的 "
            "ie_modified），草稿階段預填 true 會騙過自我指涉排除"
        )
    # D3-022：IE 重切（plan 編輯）的轉正路徑——編輯狀態與 entry 的 ie_modified
    # 宣告必須一致，兩個方向都擋：
    # - entry 宣告改過但草稿沒走 ie_edited 工作流＝宣告掛在管線原樣 plan 上（說謊）；
    # - 草稿被編輯過（ie_edited）但 entry 未宣告＝把 IE 的重切以「未修改」身分
    #   轉正，該筆會被 Plan 層指標錯誤排除（真 ground truth 被丟掉）。
    entry_modified = bool(entry.get("ie_modified")) if entry else False
    edited = draft.get("review_status") == "ie_edited"
    if entry_modified and not edited:
        blockers.append(
            "entry 宣告 ie_modified=true 但草稿 review_status 非 ie_edited——"
            "plan 編輯必須依工作流標記（docs/llm/gold-review/README.md）"
        )
    if edited and not entry_modified:
        blockers.append(
            "草稿 review_status=ie_edited（IE 改過 plan）但 entry 未宣告 "
            "ie_modified=true——編輯過的 plan 不得以未修改身分轉正"
        )
    if entry is not None and entry.get("resegmentation_ruling"):
        # D3-022（d016 型）：IE 裁決「標題句不硬切、不轉正」——fail-closed，
        # 內容由各列的獨立 gold 覆蓋，本句留在草稿當多動作辨識參考
        blockers.append(
            f"entry 帶 resegmentation_ruling={entry['resegmentation_ruling']}"
            "（IE 裁決本句不重切、不轉正；內容由成分列的獨立 gold 覆蓋）"
        )
    blockers += structure_consistency_blockers(draft)
    blockers += caveat_resolution_blockers(draft)
    blockers += substance_blockers(draft)
    if not provenance_matches_normalized_text(draft):
        blockers.append("S 檢失敗：normalized_text 與所有 source_provenance.raw_text 不一致")
    return blockers


def promoted_case_payload(
    draft: dict[str, Any],
    *,
    new_id: str,
    approved_by: str,
    approved_date: str,
    split: str,
    ie_modified: bool = False,
) -> dict[str, Any]:
    """草稿 → 正式 gold 檔內容（純轉換，不落盤）：改身分欄位、保留全部
    覆核軌跡（ie_review／caveat／provenance／草稿 id 進 notes 供追溯）。

    `ie_modified` 的來源＝state entry 的宣告（cmd_promote 傳入）：false＝原樣
    核准（確認≠修改，planner 段自我指涉排除）；true＝IE 改過 plan 內容
    （D3-022 重切型）——真實 ground truth，**計入** Plan 層指標。
    IE 在草稿 notes 留過的內容（如重切的 v3 列涵蓋對應）保留，轉正註記附加；
    管線樣板 notes（DRAFT_NOTES_BOILERPLATE）視為無內容，直接取代。"""
    data = json.loads(json.dumps(draft))  # deep copy
    old_id = data.get("id")
    data["id"] = new_id
    data["approved_by"] = approved_by
    data["approved_date"] = approved_date
    data["review_status"] = "approved"
    data["ie_modified"] = bool(ie_modified)
    data["split"] = split
    # 尾句依**實際存在的覆核面向**生成（D3-027；D3-026 複審 L1）：舊樣板把
    # 「TMU=0 裁決」硬寫進每筆 notes，沒有該裁決的案例＝notes 說謊（讀者去
    # ie_review 找不到的東西不該被宣稱存在）。
    ir = data.get("ie_review") or {}
    aspects = [
        label
        for key, label in (
            ("segmentation_confirmed_by", "切分確認"),
            ("typing_confirmed_by", "判型確認"),
            ("p_direction_confirmed_by", "P 方向數確認"),
            ("zero_tmu_ruling", "TMU=0 裁決"),
            ("incomplete_ruling", "incomplete 裁決"),
        )
        if ir.get(key)
    ]
    promo_note = (
        f"自草稿 {old_id} 轉正（IE 覆核核准；docs/llm/gold-review/README.md 工作流）。"
        "取樣為 challenge-oversampled（coverage-optimized），本案分數不可外推為"
        f"母體表現。{'、'.join(aspects) or '覆核軌跡'}見 ie_review 與 "
        "tests/gold/wi_plans_draft/review-state.json。"
    )
    prev_notes = (data.get("notes") or "").strip()
    if prev_notes and prev_notes != DRAFT_NOTES_BOILERPLATE:
        data["notes"] = prev_notes + "\n" + promo_note
    else:
        data["notes"] = promo_note
    return data


async def cmd_promote(
    paths: list[str],
    *,
    approved_by: str,
    approved_date: str,
    split: str,
    slugs: list[str],
) -> int:
    """草稿轉正（整批先驗再動手；一筆不合格＝一筆都不寫）。"""
    if split not in PROMOTION_SPLITS:
        raise SystemExit(f"--split 必須是 {PROMOTION_SPLITS}")
    if not _DATE_RE.match(approved_date or ""):
        raise SystemExit("--approved-date 必須是 YYYY-MM-DD")
    if not (approved_by or "").strip() or approved_by == "seed":
        raise SystemExit("--approved-by 必須是 IE 工號（seed 是 fixture 慣例，不是核准人）")
    if len(slugs) != len(paths):
        raise SystemExit(f"--slugs 數量（{len(slugs)}）必須與 --promote 檔數（{len(paths)}）一致")
    for slug in slugs:
        if not _SLUG_RE.match(slug):
            raise SystemExit(f"slug {slug!r} 不合法（^[a-z0-9_]+$）")
    if len(set(slugs)) != len(slugs):
        raise SystemExit("slug 重複")

    drafts: list[tuple[Path, dict[str, Any]]] = []
    for p in paths:
        path = Path(p)
        if is_formal_gold_path(path):
            raise SystemExit(f"{path} 已在正式 gold 目錄——轉正的輸入是草稿")
        drafts.append((path, json.loads(path.read_text(encoding="utf-8"))))
    draft_dirs = {path.parent.resolve() for path, _ in drafts}
    if len(draft_dirs) != 1:
        raise SystemExit("一次只轉正同一個草稿目錄（review-state 的歸屬要唯一）")
    state_path = draft_dirs.pop() / REVIEW_STATE_FILENAME
    state_raw = json.loads(state_path.read_text(encoding="utf-8"))
    entries = load_review_state(state_path)

    # 1) 資格：整批先驗（promotion_blockers 唯一出處）
    problems: list[str] = []
    for path, data in drafts:
        blockers = promotion_blockers(data, entries.get(draft_sha8(data)))
        if blockers:
            problems.append(f"{path.name}：\n  - " + "\n  - ".join(blockers))
    if problems:
        raise SystemExit("轉正資格不符（整批拒絕，一筆都不寫）：\n" + "\n".join(problems))

    # 2) split 防 leakage：既有正式 gold 同 split_component 不得跨 split
    gold_component_split: dict[str, str] = {}
    for gp in sorted(GOLD_DIR.glob("*.json")):
        gd = json.loads(gp.read_text(encoding="utf-8"))
        if gd.get("split_component") and gd.get("split"):
            gold_component_split[gd["split_component"]] = gd["split"]
    for path, data in drafts:
        comp = data.get("split_component")
        prev = gold_component_split.get(comp or "")
        if prev is not None and prev != split:
            raise SystemExit(
                f"{path.name}：split_component {comp} 已有正式 gold 在 split={prev}，"
                "同 component 不得跨 split（防 leakage）"
            )

    # 3) 編號與 payload；compile／planner 段預檢全綠才落筆
    serials = [
        int(m.group(1))
        for m in (re.match(r"^g(\d+)_", p.name) for p in GOLD_DIR.glob("*.json"))
        if m
    ]
    next_no = max(serials, default=0) + 1
    payloads: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for (path, data), slug in zip(drafts, slugs):
        new_id = f"g{next_no:02d}_{slug}"
        next_no += 1
        target = GOLD_DIR / f"{new_id}.json"
        if target.exists():
            raise SystemExit(f"{target} 已存在——不覆蓋已核准 gold")
        entry = entries[draft_sha8(data)]  # 資格已驗（entry 必存在）
        payload = promoted_case_payload(
            data,
            new_id=new_id,
            approved_by=approved_by,
            approved_date=approved_date,
            split=split,
            # ie_modified 宣告的唯一出處＝state entry（IE 裁決載體）：
            # true＝IE 重切過 plan（D3-022）→ 計入 Plan 層指標
            ie_modified=bool(entry.get("ie_modified")),
        )
        compile_res = await evaluate_gold_case(payload)
        if not compile_res.ok:
            problems.append(f"{path.name} → {new_id}：compile 段紅（{compile_res.errors}）")
        planner_res = await evaluate_planner_case(payload, rule_based_plan)
        if not planner_res.ok:
            problems.append(f"{path.name} → {new_id}：gold 標註缺損（{planner_res.errors}）")
        payloads.append((path, data, payload))
    if problems:
        raise SystemExit(
            "轉正預檢紅燈（該筆期望值有問題——撤回該筆，不准為過而改期望）：\n"
            + "\n".join(problems)
        )

    # 4) 落筆：寫正式 gold → 標 promoted → 刪草稿檔（entry 保留＝軌跡）
    for path, data, payload in payloads:
        (GOLD_DIR / f"{payload['id']}.json").write_text(_dump(payload), encoding="utf-8")
        entry = state_raw["entries"][draft_sha8(data)]
        entry["promoted_to"] = payload["id"]
        entry["promoted_date"] = approved_date
        path.unlink()
        print(f"promoted {path.name} → {payload['id']}.json（split={split}）")
    state_path.write_text(_dump(state_raw), encoding="utf-8")
    print(f"review-state 已標 promoted_to（{len(payloads)} 筆；entry 保留不刪）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Gold set 擴充：候選採集＋預標註草稿（唯讀 DB）")
    parser.add_argument("--out", default=str(ROOT / "tests" / "gold" / "wi_plans_draft"))
    parser.add_argument("--review-dir", default=str(ROOT / "docs" / "llm" / "gold-review"))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--rule-set-code", default=DEFAULT_RULE_SET_CODE)
    parser.add_argument("--force", action="store_true", help="覆蓋既有草稿（會先刪除 out 目錄的 *.json）")
    parser.add_argument(
        "--recompile",
        nargs="+",
        metavar="DRAFT_JSON",
        help="IE 改完 plan 後重算 expected_cycles/expected（不跑 planner、不碰 DB）",
    )
    parser.add_argument(
        "--relock-approved",
        action="store_true",
        help="允許 --recompile 改寫正式 gold（tests/gold/wi_plans/）；必須搭配 --reason",
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="--relock-approved 的重鎖原因（會寫進被改檔案的 notes 留痕）",
    )
    parser.add_argument(
        "--promote",
        nargs="+",
        metavar="DRAFT_JSON",
        help="IE 核准後轉正：草稿 → tests/gold/wi_plans/（資格檢查＋compile 預檢"
        "全綠才落筆；review-state entry 標 promoted_to）",
    )
    parser.add_argument("--approved-by", default=None, help="--promote 的核准 IE 工號")
    parser.add_argument(
        "--approved-date", default=None, help="--promote 的核准日期（YYYY-MM-DD）"
    )
    parser.add_argument(
        "--split",
        default=None,
        choices=PROMOTION_SPLITS,
        help="--promote 的 split 分配（同 split_component 必同 split）",
    )
    parser.add_argument(
        "--slugs",
        default=None,
        help="--promote 的語意 slug 清單（逗號分隔，數量與檔數一致；gNN_<slug>）",
    )
    args = parser.parse_args()
    if args.relock_approved and not args.recompile:
        parser.error("--relock-approved 只在 --recompile 模式有意義")
    if args.promote:
        if args.recompile:
            parser.error("--promote 與 --recompile 不可同時使用")
        if not (args.approved_by and args.approved_date and args.split and args.slugs):
            parser.error("--promote 需要 --approved-by、--approved-date、--split、--slugs")
        return asyncio.run(
            cmd_promote(
                args.promote,
                approved_by=args.approved_by,
                approved_date=args.approved_date,
                split=args.split,
                slugs=[s.strip() for s in args.slugs.split(",") if s.strip()],
            )
        )
    if args.recompile:
        return asyncio.run(
            cmd_recompile(
                args.recompile, relock_approved=args.relock_approved, reason=args.reason
            )
        )
    return asyncio.run(cmd_harvest(args))


if __name__ == "__main__":
    raise SystemExit(main())
