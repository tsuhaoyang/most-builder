"""SlotLinker：依 action_type 向參數池查詢候選（附錄 A2）。

L0 motion_templates（可選 session）、L1 synonym exact、L2 pg_trgm（可選）。
L3 embedding 本階段不實作（provider 無表則跳過）。
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
from ddm_v2.services.v2.template_matching import score_keywords

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
        score, hits = score_keywords(plan.normalized_text, list(tmpl.get("keywords") or []))
        if score > 0:
            ranked.append((float(score), tmpl, hits))
    if not ranked:
        return []
    ranked.sort(key=lambda x: (-x[0], x[1].get("id") or ""))
    out: list[SlotCandidateSet] = []
    for i, (score, tmpl, _hits) in enumerate(ranked[:TOP_K], start=1):
        # score_keywords 是字元長度加總；縮放到 0.5–0.95 顯示用，非校準機率
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


class SlotLinker:
    def __init__(self, synonyms: list[dict]) -> None:
        self._lexicon = build_lexicon(synonyms)

    async def link(
        self,
        plan: WorkInstructionPlan,
        *,
        session: AsyncSession | None = None,
        rule_set_id: Any | None = None,
        templates: list[dict] | None = None,
    ) -> list[SlotCandidateSet]:
        results: list[SlotCandidateSet] = []

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

            # inspect 視線範圍未明 → NORMAL 變體＋i_range_assumed（若有 i_confirm 類命中）
            if action.action_type == "inspect":
                for sc in results:
                    if (
                        sc.action_id == action.action_id
                        and sc.parameter == "I"
                        and sc.chosen
                        and sc.review_reason is None
                    ):
                        if "inspect_kind" not in action.roles or not action.roles["inspect_kind"].text:
                            sc.needs_review = True
                            sc.review_reason = "i_range_assumed"
                        break

        return results
