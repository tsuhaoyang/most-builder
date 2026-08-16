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
- 9 個可判維度的 `false` 同為啟發式輸出（quantity/tool/simo 的漏標已有實證，
  如「多顆」無數字不命中 quantity）——每筆草稿標 `heuristic_tags_unverified`
  點名這幾維，IE 覆核時 true/false 都要確認。

決定性：同一 DB 跑兩次輸出 byte-identical（SQL ORDER BY＋Python 穩定排序、
sha256 命名、輸出不含任何 timestamp）。守門在
`tests/integration/test_gold_harvest.py`。

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
from ddm_v2.nlp.gold_eval import DEFAULT_RULE_SET_CODE, case_rule_set_code  # noqa: E402
from ddm_v2.nlp.lexicon import build_lexicon, match_all  # noqa: E402
from ddm_v2.nlp.linking import SlotLinker  # noqa: E402
from ddm_v2.nlp.normalization import normalize  # noqa: E402
from ddm_v2.nlp.planner_eval import RULE_PLANNER_NAME, planner_preannotation_origin  # noqa: E402
from ddm_v2.nlp.routing import compute_routing  # noqa: E402
from ddm_v2.nlp.rule_based import RuleBasedParser  # noqa: E402
from ddm_v2.nlp.rule_plan_adapter import plan_from_rule_result  # noqa: E402

GOLD_SCHEMA_VERSION = "wi-gold-v1"
DEFAULT_LIMIT = 60
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
    import re

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
                        "SELECT s.parameter, s.option_code, s.synonym_norm, s.priority "
                        "FROM rule_option_synonyms s "
                        "JOIN rule_sets r ON r.id = s.rule_set_id "
                        "WHERE r.code = :code "
                        "ORDER BY s.parameter, s.priority DESC, s.synonym_norm, s.option_code"
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

    out: dict[str, Any] = {
        "id": draft_id,
        "source_text": cand.raw,
        "notes": (
            "預標註草稿（rule pipeline 自動產生；scripts/gold_harvest.py）。"
            "非 gold——IE 覆核核准前不得移入 tests/gold/wi_plans/。"
        ),
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
        "synthetic_synonyms": used_lexicon_entries(plan.normalized_text, synonyms),
        "expected_cycles": [expected_cycle_from_draft(d) for d in drafts],
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
}


# likely_multi 的降級版警語（D3-014：結構若顯示單一 cycle，「幾乎必然低估」
# 對該筆要降級——v3 結構是 IE 的切分裁決，不再預設切分是錯的）
_LIKELY_MULTI_DOWNGRADED_ZH = (
    "本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE "
    "當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），"
    "「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 "
    "v3 的切分本身有誤（hint 是證據不是判決，可推翻）"
)


def _caveat_line_zh(caveat: str, draft: dict[str, Any]) -> str:
    """單筆草稿的旗標說明文字（覆核表用）。

    likely_multi_action_undercounted＋v3 結構 single_cycle ⇒ 警語降級
    （D3-014 裁決 3）；其餘照 `_CAVEAT_ZH`。與 preannotate 的旗標共用同一
    hint 欄位——不另判一次。"""
    if (
        caveat == "likely_multi_action_undercounted"
        and draft.get("v3_structure_hint") == STRUCTURE_HINT_SINGLE
    ):
        return _LIKELY_MULTI_DOWNGRADED_ZH
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
                f"判型（{a['action_id']}）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。"
                "實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？"
            )
        else:
            core = _CORE_PARAM_ZH.get(a["action_type"], "?")
            qs.append(
                f"判型（{a['action_id']}）：預測為 {a['action_type']}，對嗎？"
                f"若對，core 參數 {core} 的 option code 是什麼？（預標註無候選時請直接填）"
            )
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


def build_review_checklist(drafts: list[dict[str, Any]]) -> str:
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
    lines.append(f"共 {len(drafts)} 筆，其中 {n_flag} 筆帶 ⚠️ 旗標。")
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


def build_summary(
    counts: dict[str, int],
    all_candidates: list[Candidate],
    selected: list[Candidate],
    synonyms: list[dict],
    limit: int,
    already_gold: list[Candidate] | None = None,
    drafts: list[dict[str, Any]] | None = None,
) -> str:
    drafts = drafts or []
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
    existing = sorted(p.name for p in out_dir.glob("*.json"))
    if existing and not args.force:
        raise SystemExit(
            f"{out_dir} 已有 {len(existing)} 個草稿（可能含 IE 編輯），不覆蓋。"
            "確定要整批重產請加 --force。"
        )
    if args.force:
        for p in out_dir.glob("*.json"):
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

    for d in drafts:
        (out_dir / f"{d['id']}.json").write_text(_dump(d), encoding="utf-8")

    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "review-checklist.md").write_text(
        build_review_checklist(drafts), encoding="utf-8"
    )
    summary = build_summary(
        counts,
        all_candidates,
        selected,
        synonyms,
        args.limit,
        already_gold=already_gold,
        drafts=drafts,
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
    args = parser.parse_args()
    if args.relock_approved and not args.recompile:
        parser.error("--relock-approved 只在 --recompile 模式有意義")
    if args.recompile:
        return asyncio.run(
            cmd_recompile(
                args.recompile, relock_approved=args.relock_approved, reason=args.reason
            )
        )
    return asyncio.run(cmd_harvest(args))


if __name__ == "__main__":
    raise SystemExit(main())
