"""SlotLinker：依 action_type 向參數池查詢候選（附錄 A2）。

L0 motion_templates（可選 session）、L1 synonym exact、L2 pg_trgm（可選）。
L3 embedding 本階段不實作（provider 無表則跳過）。

D3-024（IE 裁決落地）：CM 系 action（controlled_move/process/inspect）的
X/I 面命中掛進對應格（`_CM_SEQ_ACTION_TYPES`／`_CM_EXTRA_SPECS` 節）；
「清潔→x_blow_clean」情境守門的判定單一出處也在本模組
（`x_clean_context_missing`——harvest 旗標與掛值守門共用）。

D3-024 複審（H1/H2）：X 掛值先查 option 的 input_mode——seconds 模式且無
秒數來源的候選**不落 chosen**（cycle X 格維持空＝X0），掛 `x_seconds_required`
旗標、候選仍留 top_k（`_apply_x_input_mode_rule`）；I 格的「視線範圍未明→
取 NORMAL」假設守門解綁 action_type——任何 I 格 chosen 且該 action 無
inspect_kind role 都掛 `i_range_assumed`（`_apply_i_range_rule`）。

D3-026（E 型窄豁免的判準輸入）：`SlotLinker.face_hit_params` 回報每個 action
的 lexicon 面命中參數集合——compile 端的「純 I 句」完整性窄豁免（面集合恰為
{I}）需要它，因為 slot 候選看不到未被查詢的參數面（controlled_move 不掛 G
spec，G 面命中在候選層不可見）。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.nlp.contracts import (
    OptionCandidate,
    PlannedAction,
    SlotCandidateSet,
    WorkInstructionPlan,
)
from ddm_v2.nlp.lexicon import LexEntry, build_lexicon, match_all
from ddm_v2.services.v2.template_matching import score_template

logger = logging.getLogger(__name__)

TRGM_THRESHOLD = 0.35
TOP_K = 5

# action_type → [(parameter, field, query_role_keys)]
_LINK_SPEC: dict[str, list[tuple[str, str, tuple[str, ...]]]] = {
    "acquire": [("G", "g2.g_code", ("object", "tool"))],
    "move_place": [("P", "p5.p_base_code", ("destination", "object", "tool"))],
    "controlled_move": [("M", "m3.verb_code", ("object", "tool", "process_kind"))],
    "process": [("X", "x4.x_code", ("process_kind", "object", "tool"))],
    "inspect": [("I", "i5.i_code", ("inspect_kind", "object"))],
    "release_return": [("P", "p5.p_base_code", ("object", "destination", "tool"))],
}

# ── D3-024：CM 系 action 的 X/I 面命中掛進對應格 ────────────────────────────
#
# CM 序列＝A B G M X I A（`docs/core-logic/minimost-sequence-model-core-logic-
# spec.md` §2）——同一 CM cycle 本來就同時容納 M、X、I 三格；compile 端
# （most_compiler/compile.py）也一直讀全部三格。先前 linker 只掛各 action_type
# 的 core 格（controlled_move→M、process→X、inspect→I），導致 IE 已登記的
# X/I 動詞面（確認→i_confirm、鎖附→x_screw_fix、清潔→x_blow_clean，D3-021）
# 在 controlled_move 句上閒置。本節與 G/M/P 同模式補掛：**面命中才掛**
# （lexicon 對 query 有命中才追加 spec——與 B 的條件式追加同構；無命中不加
# no_candidate 噪音）。GM 系 action（acquire/move_place/release_return）不掛
# ——GM 序列沒有 X/I 格。
#
# 完整性語意：completeness 判準仍是 CORE_PARAM_BY_ACTION 的 core 格
# （controlled_move 缺 M 仍 missing_core_m）。「X 承載做工時 M 可為零」
# D3-026 IE 已裁＝**不成立**（全面放寬被否決——鎖附/清潔型的移動真實存在，
# 走 expected_incomplete_reason 誠實 incomplete）；唯一例外＝E 型窄豁免
# （純 I 句，面集合恰 {I}），在 compile 端（most_compiler/compile.py）。
_CM_SEQ_ACTION_TYPES = frozenset({"controlled_move", "process", "inspect"})
_CM_EXTRA_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("X", "x4.x_code", ("process_kind", "object", "tool")),
    ("I", "i5.i_code", ("inspect_kind", "object")),
)

# ── 「清潔」情境守門（IE 裁決 D3-021；D3-024 起 linker 掛值也適用）──────────
#
# 「清潔→x_blow_clean」是**情境條件裁決**：IE 只裁了吹風情境（語料全是
# 風槍/吹風），同義詞表本身是全域映射、不帶情境。判定的**單一出處在這裡**
# （scripts/gold_harvest.py 的旗標、test_gold_draft_schema 5i 守門、linker
# 掛值全部 import 本模組——不允許第二份判定）。掛值語意（D3-024）：旗標
# 情境下**掛值照掛但 needs_review**（review_reason=x_clean_context_unverified）
# ——值不硬套成定案，交 IE；轉正端 fail-closed 不變（gold_harvest
# caveat_resolution_blockers）。
X_CLEAN_SYNONYM_NORM = "清潔"
X_CLEAN_OPTION_CODE = "x_blow_clean"
X_CLEAN_CONTEXT_TERMS = ("風槍", "吹風")
X_CLEAN_REVIEW_REASON = "x_clean_context_unverified"


def x_clean_context_missing(norm: str, used_synonyms: list[dict[str, Any]]) -> bool:
    """「清潔→x_blow_clean」命中但句面無吹風脈絡？（D3-021 單一出處：
    harvest 的旗標、schema 守門與 linker 掛值守門共用本函式。）

    判定對象＝實際配出的 lexicon 條目（harvest 端＝used_lexicon_entries 輸出；
    linker 端＝該 X 格 query 的 match_all 命中）——只有 lexicon 真的配出這條
    映射才有「情境是否成立」的問題；脈絡詞查 normalized_text（整句，lexicon
    配對的同一文本）。"""
    hit = any(
        s.get("parameter") == "X"
        and s.get("synonym_norm") == X_CLEAN_SYNONYM_NORM
        and s.get("option_code") == X_CLEAN_OPTION_CODE
        for s in used_synonyms
    )
    return hit and not any(t in norm for t in X_CLEAN_CONTEXT_TERMS)


def _apply_x_clean_context_rule(
    plan_norm: str,
    query: str,
    lexicon: list[LexEntry],
    chosen: OptionCandidate | None,
    needs_review: bool,
    review_reason: str | None,
) -> tuple[bool, str | None]:
    """X 格掛值的清潔情境守門：chosen 是 x_blow_clean 且經「清潔」面配出、
    句面（整句）無風槍/吹風脈絡 → 掛值照掛、標 needs_review（不硬套 IE 未裁
    的情境，也不丟掉候選——丟掉＝linker 越權裁決建法）。"""
    if chosen is None or chosen.option_code != X_CLEAN_OPTION_CODE:
        return needs_review, review_reason
    x_pool = [e for e in lexicon if e.parameter == "X"]
    used = [
        {"parameter": e.parameter, "option_code": e.option_code, "synonym_norm": e.norm}
        for _start, _end, e in match_all(query, x_pool)
    ]
    if x_clean_context_missing(plan_norm, used):
        return True, review_reason or X_CLEAN_REVIEW_REASON
    return needs_review, review_reason


# ── X input_mode 守門（D3-024 複審 H1）─────────────────────────────────────
#
# X option 分三種 input_mode（rule_x_options.mode）：zero（X0）、fixed
# （fixed_seconds 有值＝真 TMU 可算，如 x_screw_fix）、seconds（製程時間由
# IE 現場量測輸入）。seconds 模式的候選若無秒數來源就落 chosen，compile 會
# 產出 x_seconds=0 的 complete cycle → 引擎硬拒 X_SECONDS_REQUIRED →
# routing=invalid——合法草稿（如「按壓把手並清潔卡槽」，M 核心格可填）被
# 整筆判死。修法＝**不落 chosen**（cycle X 格維持空＝X0，與掛值前行為相同）、
# 候選仍留 top_k、掛 `x_seconds_required` 旗標——資訊保留、需求浮上、不硬拒；
# 秒數模式的製程時間本來就要 IE 量測給值，不落 chosen 是誠實而非丟資訊。
#
# mode 來源：session＋rule_set_id 可用（生產路徑）→ 讀該 rule set 的
# rule_x_options（runtime 值權威＝DB）；否則（unit／gold_eval 重放）→ seed
# 權威 build_from_seed_v2（這些路徑的 engine gate 用的就是同一份 seed 資料）。
X_SECONDS_REVIEW_REASON = "x_seconds_required"
# 秒數來源判準＝compile 讀 x_seconds 的同一形狀（most_compiler/compile.py：
# process_kind role 帶秒值）——linker 不另創秒數語意（compile 端是唯一消費者）
_X_SECONDS_UNITS = frozenset({"s", "sec", "秒"})
_SEED_X_INPUT_MODES: dict[str, str] | None = None


def _seed_x_input_modes() -> dict[str, str]:
    global _SEED_X_INPUT_MODES
    if _SEED_X_INPUT_MODES is None:
        from ddm_v2.most_engine.providers import build_from_seed_v2

        _SEED_X_INPUT_MODES = {
            code: mode for code, (mode, _fsec) in build_from_seed_v2().x_options.items()
        }
    return _SEED_X_INPUT_MODES


async def _load_x_input_modes(
    *, session: AsyncSession | None, rule_set_id: Any | None
) -> dict[str, str]:
    """X option code → input_mode。DB 路徑不吞錯（rule_x_options 是必在表，
    查詢失敗＝環境壞了，讓例外浮上——與 trgm 的 extension 可缺不同）。"""
    if session is not None and rule_set_id is not None:
        from ddm_v2.models.v2.rule_set_tables import RuleXOption

        rows = (
            await session.execute(
                select(RuleXOption.code, RuleXOption.mode).where(
                    RuleXOption.rule_set_id == rule_set_id
                )
            )
        ).all()
        return {str(code): str(mode) for code, mode in rows}
    return _seed_x_input_modes()


def _x_seconds_source_present(action: PlannedAction) -> bool:
    pk = action.roles.get("process_kind")
    return bool(pk is not None and pk.unit in _X_SECONDS_UNITS and pk.value is not None)


def _apply_x_input_mode_rule(
    action: PlannedAction,
    chosen: OptionCandidate | None,
    x_modes: dict[str, str],
    needs_review: bool,
    review_reason: str | None,
) -> tuple[OptionCandidate | None, bool, str | None]:
    """X 掛值的 input_mode 守門（H1）：seconds 模式且無秒數來源 → 不落
    chosen（X0）＋`x_seconds_required`；fixed/zero（真值可算）與「seconds
    但句面帶秒數」（compile 會填 x_seconds）照掛。不在 mode 表的 code 原樣
    通過——compiler allow-list 是未知 code 的守門，不在此重複。"""
    if chosen is None:
        return chosen, needs_review, review_reason
    if x_modes.get(chosen.option_code) != "seconds":
        return chosen, needs_review, review_reason
    if _x_seconds_source_present(action):
        return chosen, needs_review, review_reason
    return None, True, review_reason or X_SECONDS_REVIEW_REASON


def _apply_i_range_rule(
    action: PlannedAction,
    chosen: OptionCandidate | None,
    needs_review: bool,
    review_reason: str | None,
) -> tuple[bool, str | None]:
    """I 格掛值的視線範圍守門（D3-024 複審 H2）：「視線範圍未明→取 NORMAL
    變體」是假設（i_confirm 6 TMU vs i_confirm_out 16 TMU），原先只綁
    action_type=="inspect"——D3-024 起 controlled_move/process 也掛 I 格，
    同一假設繞過守門。解綁：任何 I 格 chosen 且該 action 無 inspect_kind
    role → `i_range_assumed`（與 P 方向／X 清潔守門同層擺放）。"""
    if chosen is None:
        return needs_review, review_reason
    role = action.roles.get("inspect_kind")
    if role is not None and role.text:
        return needs_review, review_reason
    return True, review_reason or "i_range_assumed"


_B_BODY_HINTS = ("蹲", "彎", "起身", "彎腰", "蹲下", "站起")
_P_ADDON_HINTS = (("插入", "a_insert"), ("卡合", "a_snap"), ("卡入", "a_snap"), ("對準", "a_align"))

# ── P 方向數情境規則（IE 裁決 D3-017，2026-08-16 User 親答）────────────────
#
# 「放至/放置」的方向數按賓語情境定：放入**機構件**（要定位）→ 必對準
# （p_place_single；方向數 IE 未指定，預設一種）；放上**盤面類**（盤子/
# conveyor 家族）→ 無方向（p_place_none）。詞面本身在字典裡掛兩個變體
# （v2_0038 一面多 code），本規則負責依賓語擇一；判不出 → 維持預設
# p_place_single 並標 needs_review 交 IE。
#
# 名詞分類清單＝**單一出處**（harvest 的旗標、gold_eval 的重放、生產 nl-draft
# 全部 import 這裡；不允許第二份清單）。成員從 60 筆語料實證定，逐項附證據：
#
# 機構件類（要定位；IE 例示：治具/卡槽/機箱「這類要定位的」）：
# - 治具：d002「放至DIMM壓合治具」、d012「放置於DIMM壓合治具」——主板入治具需對位
# - 冶具：治具的語料常見錯字變體（與 harvest _VERB_COMPOUND_NOUNS 同列）
# - 卡槽：IE 明示例；語料「組於DIMM卡槽」「插入至DIMM卡槽」（面未登記，先備）
# - 機箱：IE 明示例；語料 d026「組至機箱」（面未登記，先備）
# - 接頭：語料 d045「對準接頭」——排線入接頭需對位（IE 情境規則的「定位」家族）
# - 點位：語料 d014/d034「放至對應的點位」——治具把手回到定位點
#
# 盤面類（無方向；IE 例示：盤子/conveyor 類「含流水線/工作台/垃圾桶」）：
# - 流水線：IE 明示；語料 d010/d039「保持住至流水線」
# - 工作台：IE 明示；語料 d015/d024「放至…工作台」
# - 垃圾桶：IE 明示；語料 d052「丟至垃圾桶」
# - 料盒／材料盒：任務清單明列；語料「從DIMM材料盒拿取」（放上料盒＝盤面家族）
# - 料架：語料 d043「包裝袋放至料架」——放上架面無定位需求，歸盤面家族
#   （若 IE 認定特定料架有插槽定位，覆核表逐筆可改——每筆都帶方向數旗標）
#
# 不在兩清單者＝判不出（不硬猜）。賓語擷取＝詞面命中位置之後、至第一個
# 標點為止的子句（跨子句撿名詞會誤配——「放至定位,再從料架取料」不得配到料架）。
P_DIRECTION_FACES = frozenset({"放至", "放置"})
P_VARIANT_DEFAULT = "p_place_single"   # 對準情境（方向數預設一種，IE 未指定數）
P_VARIANT_SURFACE = "p_place_none"     # 盤面情境（無方向）
_P_DEST_MECHANISM_NOUNS = ("治具", "冶具", "卡槽", "機箱", "接頭", "點位")
# 工作臺＝OpenCC s2twp 會把「工作台」正規化成「工作臺」（同機台→機臺）；
# 分類跑在 normalized text 上，兩形都收（raw 路徑防禦）
_P_DEST_SURFACE_NOUNS = ("流水線", "工作台", "工作臺", "垃圾桶", "材料盒", "料盒", "料架")
_P_DEST_CLAUSE_BREAKS = ",，、;；。.!！?？"

# classify_p_destination 的回傳值
P_DEST_MECHANISM = "mechanism"
P_DEST_SURFACE = "surface"
P_DEST_UNCLASSIFIED = "unclassified"


def _dest_class_of_tail(tail: str) -> str | None:
    """子句尾巴的賓語分類：取**最早出現**的類別名詞（同位置長詞優先——
    「材料盒」不得被「料盒」搶先，雖同類仍以長詞為準）。"""
    best: tuple[int, int, str] | None = None  # (pos, -len, class)
    for nouns, klass in (
        (_P_DEST_MECHANISM_NOUNS, P_DEST_MECHANISM),
        (_P_DEST_SURFACE_NOUNS, P_DEST_SURFACE),
    ):
        for noun in nouns:
            pos = tail.find(noun)
            if pos == -1:
                continue
            cand = (pos, -len(noun), klass)
            if best is None or cand[:2] < best[:2]:
                best = cand
    return best[2] if best else None


def classify_p_destination(query: str, lexicon: list[LexEntry]) -> str | None:
    """P 方向數情境規則的判定（單一出處；linking／harvest 共用）。

    Returns:
        None＝query 無「放至/放置」方向變體面命中（規則不適用）；
        "mechanism"｜"surface"＝IE 情境規則有解；
        "unclassified"＝有面命中但賓語判不出（或多處命中互相矛盾）。
    """
    p_pool = [e for e in lexicon if e.parameter == "P"]
    face_hits = [
        (start, end)
        for start, end, entry in match_all(query, p_pool)
        if entry.norm in P_DIRECTION_FACES
    ]
    if not face_hits:
        return None
    classes: set[str] = set()
    for _start, end in face_hits:
        tail = query[end:]
        for i, ch in enumerate(tail):
            if ch in _P_DEST_CLAUSE_BREAKS:
                tail = tail[:i]
                break
        klass = _dest_class_of_tail(tail)
        classes.add(klass or P_DEST_UNCLASSIFIED)
    if len(classes) == 1 and P_DEST_UNCLASSIFIED not in classes:
        return classes.pop()
    return P_DEST_UNCLASSIFIED


def _apply_p_direction_rule(
    query: str,
    lexicon: list[LexEntry],
    chosen: OptionCandidate | None,
    top_k: list[OptionCandidate],
    needs_review: bool,
    review_reason: str | None,
) -> tuple[OptionCandidate | None, list[OptionCandidate], bool, str | None]:
    """P 候選的方向數後處理：依情境規則擇變體，並把另一變體補進 top_k。

    只在 chosen 是方向變體組成員（p_place_single/p_place_none）且 query 有
    「放至/放置」面命中時作用；其他 P 候選（p_hold/p_toss…）原樣通過。
    盤面情境把 chosen 換成 p_place_none；判不出維持預設並標 needs_review
    （IE 裁決）。機構件情境維持預設**不加旗標**（生產端 needs_review 通常為
    False；auto 由 DDM_WI_AI_AUTO_ENABLED=False 保護）；方向數的逐筆確認
    （「方向數預設一種，不對請改」）在 harvest 覆核表的 p_direction_* 旗標，
    不在生產旗標。
    """
    variant_group = {P_VARIANT_DEFAULT, P_VARIANT_SURFACE}
    if chosen is None or chosen.option_code not in variant_group:
        return chosen, top_k, needs_review, review_reason
    outcome = classify_p_destination(query, lexicon)
    if outcome is None:
        return chosen, top_k, needs_review, review_reason
    preferred = P_VARIANT_SURFACE if outcome == P_DEST_SURFACE else P_VARIANT_DEFAULT
    alternate = P_VARIANT_DEFAULT if preferred == P_VARIANT_SURFACE else P_VARIANT_SURFACE
    new_chosen = chosen.model_copy(update={"option_code": preferred, "rank": 1})
    rest = [c for c in top_k if c.option_code not in variant_group]
    new_top = [new_chosen, new_chosen.model_copy(update={"option_code": alternate, "rank": 2})]
    for i, c in enumerate(rest, start=len(new_top) + 1):
        new_top.append(c.model_copy(update={"rank": i}))
    if outcome == P_DEST_UNCLASSIFIED:
        return new_chosen, new_top[:TOP_K], True, review_reason or "p_direction_unclassified"
    return new_chosen, new_top[:TOP_K], needs_review, review_reason


def _query_text(action: PlannedAction, role_keys: tuple[str, ...], plan: WorkInstructionPlan) -> str:
    parts: list[str] = []
    for key in role_keys:
        role = action.roles.get(key)
        if role and role.text:
            parts.append(role.text)
    for ev in action.evidence:
        if ev.text:
            parts.append(ev.text)
    if not parts and plan.normalized_text:
        parts.append(plan.normalized_text)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return " ".join(out)


def _match_pool(
    query: str,
    lexicon: list[LexEntry],
    *,
    parameter: str,
) -> list[OptionCandidate]:
    pool = [e for e in lexicon if e.parameter == parameter]
    if not query or not pool:
        return []
    hits = match_all(query, pool)
    # 同 option 取最高分（exact=0.95）；依首次出現順序
    by_code: dict[str, OptionCandidate] = {}
    for _, _, entry in hits:
        src: str = "synonym_exact" if entry.source == "exact" else "synonym_longest"
        cand = OptionCandidate(
            parameter=parameter,
            option_code=entry.option_code,
            score=entry.score,
            source=src,  # type: ignore[arg-type]
            rank=0,
        )
        prev = by_code.get(entry.option_code)
        if prev is None or cand.score > prev.score:
            by_code[entry.option_code] = cand
    ranked = sorted(by_code.values(), key=lambda c: (-c.score, c.option_code))
    out: list[OptionCandidate] = []
    for i, c in enumerate(ranked[:TOP_K], start=1):
        out.append(c.model_copy(update={"rank": i}))
    return out


async def _trgm_candidates(
    session: AsyncSession,
    *,
    rule_set_id: Any,
    parameter: str,
    query: str,
) -> list[OptionCandidate]:
    if not query.strip():
        return []
    sql = text(
        """
        SELECT option_code,
               GREATEST(
                 similarity(synonym_norm, :q),
                 similarity(COALESCE(synonym_raw, ''), :q)
               ) AS score
        FROM rule_option_synonyms
        WHERE rule_set_id = :rs
          AND parameter = :param
          AND synonym_norm % :q
        ORDER BY score DESC, priority ASC, option_code ASC
        LIMIT :lim
        """
    )
    try:
        rows = (
            await session.execute(
                sql,
                {"q": query, "rs": rule_set_id, "param": parameter, "lim": TOP_K},
            )
        ).all()
    except Exception as exc:  # pragma: no cover — extension/path may be unavailable
        logger.debug("trgm linking skipped: %s", exc)
        return []
    out: list[OptionCandidate] = []
    for i, row in enumerate(rows, start=1):
        score = float(row.score or 0)
        if score < TRGM_THRESHOLD:
            continue
        out.append(
            OptionCandidate(
                parameter=parameter,
                option_code=row.option_code,
                score=score,
                source="trgm",
                rank=i,
            )
        )
    return out[:TOP_K]


def _merge_l1_l2(
    l1: list[OptionCandidate],
    l2: list[OptionCandidate],
) -> tuple[OptionCandidate | None, list[OptionCandidate], str | None]:
    """合併；L1 exact 與 L2 top-1 不同 → engines_disagree。"""
    by_code: dict[str, OptionCandidate] = {}
    for c in l1 + l2:
        prev = by_code.get(c.option_code)
        if prev is None or c.score > prev.score:
            by_code[c.option_code] = c
    top = sorted(by_code.values(), key=lambda c: (-c.score, c.option_code))[:TOP_K]
    for i, c in enumerate(top, start=1):
        top[i - 1] = c.model_copy(update={"rank": i})

    reason: str | None = None
    chosen: OptionCandidate | None = top[0] if top else None
    if not chosen:
        return None, [], "no_candidate"

    l1_top = l1[0].option_code if l1 else None
    l2_top = l2[0].option_code if l2 else None
    if l1_top and l2_top and l1_top != l2_top:
        reason = "engines_disagree"
        # prefer L1 exact when diverge
        chosen = next((c for c in top if c.option_code == l1_top), chosen)

    return chosen, top, reason


async def _load_active_templates(session: AsyncSession) -> list[dict]:
    from ddm_v2.models.v2.motion_template import MotionTemplate

    rows = (
        await session.execute(
            select(MotionTemplate).where(MotionTemplate.is_active.is_(True)).limit(200)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "keywords": list(r.keywords or []),
            "cycle_template": r.cycle_template,
            "name_zh": r.name_zh,
            "seq_kind": r.seq_kind,
        }
        for r in rows
    ]


def _template_hints(plan: WorkInstructionPlan, templates: list[dict]) -> list[SlotCandidateSet]:
    """L0：cycle-level template 候選（needs_review；不拆 slot、不繞過 IE）。"""
    ranked: list[tuple[float, dict, list[str]]] = []
    for tmpl in templates:
        score, hits = score_template(plan.normalized_text, tmpl)
        if score > 0:
            ranked.append((float(score), tmpl, hits))
    if not ranked:
        return []
    ranked.sort(key=lambda x: (-x[0], x[1].get("id") or ""))
    out: list[SlotCandidateSet] = []
    for i, (score, tmpl, _hits) in enumerate(ranked[:TOP_K], start=1):
        # score_template 是字元長度加總；縮放到 0.5–0.95 顯示用，非校準機率
        norm_score = min(0.95, 0.5 + score / 40.0)
        cand = OptionCandidate(
            parameter="TEMPLATE",
            option_code=str(tmpl["id"]),
            score=norm_score,
            source="template",
            rank=i,
        )
        out.append(
            SlotCandidateSet(
                action_id="__plan__",
                parameter="TEMPLATE",
                field="cycle_template",
                chosen=cand if i == 1 else None,
                top_k=[cand],
                needs_review=True,
                review_reason="template_hint",
            )
        )
    # 合併 top_k 到第一筆
    if len(out) > 1:
        first = out[0]
        merged_top = [s.top_k[0] for s in out if s.top_k]
        for j, c in enumerate(merged_top, start=1):
            merged_top[j - 1] = c.model_copy(update={"rank": j})
        out = [
            first.model_copy(
                update={
                    "chosen": merged_top[0],
                    "top_k": merged_top,
                }
            )
        ]
    return out


# face_hit_params 只認 slot 參數面（G/P/M/X/I 為現行同義詞面；A/B 先備）——
# 未來若 lexicon 出現非 slot 條目（vocab 名詞面），不得進面命中集合：
# E 型豁免的判準是「無其他 *slot* 面命中」（名詞面不是移動/做工證據）。
_SLOT_FACE_PARAMS = frozenset({"A", "B", "G", "P", "M", "X", "I"})


class SlotLinker:
    def __init__(self, synonyms: list[dict]) -> None:
        self._lexicon = build_lexicon(synonyms)

    def face_hit_params(self, plan: WorkInstructionPlan) -> dict[str, frozenset[str]]:
        """每個 action 的 lexicon 面命中參數集合（D3-026 E 型豁免的判準輸入）。

        掃描文本＝該 action 的 evidence（無則 fallback 整句 normalized_text——
        與各參數 spec 的 `_query_text` 同一 fallback 形狀，不另創文本來源）；
        詞典＝完整混合詞典（同 `used_lexicon_entries` 的 planner 視角：跨參數
        位置遮蔽一致，「面命中集合」語意與判型證據同源）。composite_unknown
        不掃（無 slot 可豁免）。回傳值只供完整性判定參考——候選/掛值仍以
        `link()` 的逐參數池為準。
        """
        out: dict[str, frozenset[str]] = {}
        for action in plan.actions:
            if action.action_type == "composite_unknown":
                continue
            q = _query_text(action, (), plan)
            out[action.action_id] = frozenset(
                e.parameter
                for _s, _e, e in match_all(q, self._lexicon)
                if e.parameter in _SLOT_FACE_PARAMS
            )
        return out

    async def link(
        self,
        plan: WorkInstructionPlan,
        *,
        session: AsyncSession | None = None,
        rule_set_id: Any | None = None,
        templates: list[dict] | None = None,
    ) -> list[SlotCandidateSet]:
        results: list[SlotCandidateSet] = []
        # X input_mode 表（H1）：整次 link 載一次（首個 X 格才載，無 X 不查）
        x_modes: dict[str, str] | None = None

        # L0 motion_templates
        tmpl_list = templates
        if tmpl_list is None and session is not None:
            try:
                tmpl_list = await _load_active_templates(session)
            except Exception as exc:  # pragma: no cover
                logger.debug("template load skipped: %s", exc)
                tmpl_list = []
        if tmpl_list:
            results.extend(_template_hints(plan, tmpl_list))

        for action in plan.actions:
            if action.action_type == "composite_unknown":
                continue
            specs = list(_LINK_SPEC.get(action.action_type, []))
            # B：僅身體動作詞才查
            blob = _query_text(action, ("object", "tool", "destination"), plan)
            if any(h in blob for h in _B_BODY_HINTS):
                specs.append(("B", "b1.b_code", ("object", "tool")))
            # X/I：CM 系 action 面命中才掛（D3-024；GM 序列無 X/I 格不掛）
            if action.action_type in _CM_SEQ_ACTION_TYPES:
                present = {p for p, _f, _r in specs}
                for extra in _CM_EXTRA_SPECS:
                    param, _field, extra_roles = extra
                    if param in present:
                        continue  # core 格已在 _LINK_SPEC（process→X、inspect→I）
                    if _match_pool(
                        _query_text(action, extra_roles, plan),
                        self._lexicon,
                        parameter=param,
                    ):
                        specs.append(extra)

            for parameter, field, role_keys in specs:
                q = _query_text(action, role_keys, plan)
                l1 = _match_pool(q, self._lexicon, parameter=parameter)
                l2: list[OptionCandidate] = []
                if session is not None and rule_set_id is not None and not l1:
                    # L1 已命中時不強制 L2；L1 空才補 trgm（降低 disagree 噪音）
                    l2 = await _trgm_candidates(
                        session,
                        rule_set_id=rule_set_id,
                        parameter=parameter,
                        query=q,
                    )
                elif session is not None and rule_set_id is not None and l1:
                    # 仍跑 L2 供 disagree 偵測（spec）
                    l2 = await _trgm_candidates(
                        session,
                        rule_set_id=rule_set_id,
                        parameter=parameter,
                        query=q,
                    )
                chosen, top_k, reason = _merge_l1_l2(l1, l2)
                needs = chosen is None or reason is not None
                if chosen is None:
                    reason = reason or "no_candidate"
                    needs = True
                if parameter == "P":
                    # IE 方向數情境規則（D3-017）：放至/放置的變體依賓語擇一
                    chosen, top_k, needs, reason = _apply_p_direction_rule(
                        q, self._lexicon, chosen, top_k, needs, reason
                    )
                if parameter == "X":
                    # input_mode 守門（H1）先於清潔守門：先定「掛不掛」，
                    # 情境旗標只對真的掛上的值有意義（chosen 空則 no-op）
                    if x_modes is None:
                        x_modes = await _load_x_input_modes(
                            session=session, rule_set_id=rule_set_id
                        )
                    chosen, needs, reason = _apply_x_input_mode_rule(
                        action, chosen, x_modes, needs, reason
                    )
                    # 清潔情境守門（D3-021/D3-024）：非吹風脈絡的 x_blow_clean
                    # 掛值照掛但 needs_review（不硬套 IE 未裁情境）
                    needs, reason = _apply_x_clean_context_rule(
                        plan.normalized_text, q, self._lexicon, chosen, needs, reason
                    )
                if parameter == "I":
                    # 視線範圍守門（H2）：I 掛值＝NORMAL 假設，不分 action_type
                    needs, reason = _apply_i_range_rule(action, chosen, needs, reason)
                results.append(
                    SlotCandidateSet(
                        action_id=action.action_id,
                        parameter=parameter,
                        field=field,
                        chosen=chosen,
                        top_k=top_k,
                        needs_review=needs,
                        review_reason=reason,
                    )
                )

            # P addon 關鍵詞（move_place）
            if action.action_type == "move_place":
                q = _query_text(action, ("destination", "object"), plan)
                for hint, code in _P_ADDON_HINTS:
                    if hint in q:
                        results.append(
                            SlotCandidateSet(
                                action_id=action.action_id,
                                parameter="P_ADDON",
                                field="p5.p_addon_codes",
                                chosen=OptionCandidate(
                                    parameter="P_ADDON",
                                    option_code=code,
                                    score=0.9,
                                    source="synonym_exact",
                                    rank=1,
                                ),
                                top_k=[
                                    OptionCandidate(
                                        parameter="P_ADDON",
                                        option_code=code,
                                        score=0.9,
                                        source="synonym_exact",
                                        rank=1,
                                    )
                                ],
                                needs_review=False,
                                review_reason=None,
                            )
                        )
                        break

        return results
