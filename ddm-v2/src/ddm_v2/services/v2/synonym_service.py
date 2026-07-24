"""同義詞 CRUD 服務（impl-05）。

IE 可為每個 rule-set 的各參數選項登記自然語言同義詞，
供 NL draft parser 最長匹配。
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.synonym import RuleOptionSynonym
from ddm_v2.nlp.normalization import normalize

# Fix-C1: 各 parameter 對應的子表與欄位名（應用層 FK 驗證）
#
# PARAM_RS_TABLE_MAP: rule_set-scoped 參數（表含 rule_set_id 欄）
#   B/G/P/M/X/I 各有獨立 option code 子表，查詢帶 rule_set_id 條件。
#
# A：使用 band-based lookup（rule_a_bands.component/max_value/index_value），
#   無離散 option code 子表，option_code FK 驗證跳過（A0/A3/A6/A10/A18 由引擎查帶）。
#
# vocab：work_vocab_items 不是 rule_set 範疇（無 rule_set_id 欄），
#   獨立以 external_code 查詢，不帶 rule_set_id 條件。
PARAM_RS_TABLE_MAP: dict[str, tuple[str, str]] = {
    "B": ("rule_b_options", "code"),
    "G": ("rule_g_actions", "code"),
    "P": ("rule_p_bases", "code"),
    "M": ("rule_m_verbs", "code"),
    "X": ("rule_x_options", "code"),
    "I": ("rule_i_options", "code"),
}


class RuleSetNotFound(Exception):
    pass


class RuleSetRetired(Exception):
    """ADR-024 §5：retired 是終態，不可再增刪同義詞。

    ⚠️ 這**不是** assert_editable。同義詞是 ADR-014 明定的例外——draft/published
    皆可增刪（值變更才需 clone），唯獨 retired（終態）擋住。故此處**只**檢查
    status == 'retired'，絕不併入 published/certified_import。
    """

    def __init__(self, rule_set_code: str) -> None:
        super().__init__(f"rule_set_retired: {rule_set_code}")
        self.rule_set_code = rule_set_code


def _assert_not_retired(rs: RuleSet) -> None:
    if rs.status == "retired":
        raise RuleSetRetired(rs.code)


class SynonymConflict(Exception):
    """UNIQUE(rule_set_id, parameter, synonym_norm) 衝突。"""

    def __init__(self, existing: dict[str, Any]) -> None:
        super().__init__("synonym_conflict")
        self.existing = existing


class SynonymNotFound(Exception):
    pass


class OptionCodeNotFound(Exception):
    """option_code 在指定 parameter 子表中不存在（應用層 FK 保護）。"""

    def __init__(self, parameter: str, option_code: str) -> None:
        super().__init__(f"option_code_not_found: {parameter}={option_code}")
        self.parameter = parameter
        self.option_code = option_code


def _to_dict(s: RuleOptionSynonym) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "rule_set_id": str(s.rule_set_id),
        "parameter": s.parameter,
        "option_code": s.option_code,
        "synonym_raw": s.synonym_raw,
        "synonym_norm": s.synonym_norm,
        "priority": s.priority,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _get_rule_set(session: AsyncSession, rule_set_code: str) -> RuleSet:
    rs = (
        await session.execute(
            select(RuleSet).where(RuleSet.code == rule_set_code)
        )
    ).scalar_one_or_none()
    if rs is None:
        raise RuleSetNotFound(rule_set_code)
    return rs


async def list_synonyms(
    session: AsyncSession, rule_set_code: str
) -> list[dict[str, Any]]:
    """列出指定 rule-set 的所有同義詞，依 parameter + priority 排序。"""
    rs = await _get_rule_set(session, rule_set_code)
    rows = (
        await session.execute(
            select(RuleOptionSynonym)
            .where(RuleOptionSynonym.rule_set_id == rs.id)
            .order_by(
                RuleOptionSynonym.parameter,
                RuleOptionSynonym.priority.desc(),
                RuleOptionSynonym.synonym_norm,
            )
        )
    ).scalars().all()
    return [_to_dict(r) for r in rows]


async def create_synonym(
    session: AsyncSession,
    rule_set_code: str,
    data: dict[str, Any],
    created_by: str,
) -> dict[str, Any]:
    """新增同義詞；UNIQUE 衝突時 raise SynonymConflict（含既有映射）。

    data keys: parameter, option_code, synonym_raw, priority(optional)
    """
    rs = await _get_rule_set(session, rule_set_code)
    # ADR-024 §5：retired 終態不可增刪同義詞。只擋 retired，不擋 published（ADR-014 特例）。
    _assert_not_retired(rs)

    # Fix-H1: 在 try 之前擷取所有純 Python 值，避免 rollback 後 ORM 屬性過期（MissingGreenlet）
    rs_id_val = rs.id
    param_val = data["parameter"]
    option_code_val = data["option_code"]
    synonym_raw_val = data["synonym_raw"]
    synonym_norm_val = normalize(synonym_raw_val)
    priority_val = data.get("priority", 0)

    # Fix-L2: synonym_norm 正規化後不得為空
    if not synonym_norm_val:
        raise ValueError("synonym_raw 正規化後為空，請輸入有效字詞。")

    # Fix-C1: option_code 應用層 FK 驗證
    #   - vocab: work_vocab_items 無 rule_set_id 欄，獨立查詢
    #   - B/G/P/M/X/I: rule_set-scoped 子表，帶 rule_set_id 條件
    #   - A: 無離散 code 子表（band-based），跳過驗證
    if param_val == "vocab":
        row = await session.execute(
            text("SELECT 1 FROM work_vocab_items WHERE external_code = :code LIMIT 1"),
            {"code": option_code_val},
        )
        if row.first() is None:
            raise OptionCodeNotFound(param_val, option_code_val)
    elif param_val in PARAM_RS_TABLE_MAP:
        tbl, col = PARAM_RS_TABLE_MAP[param_val]
        row = await session.execute(
            text(f"SELECT 1 FROM {tbl} WHERE rule_set_id = :rs_id AND {col} = :code LIMIT 1"),
            {"rs_id": rs_id_val, "code": option_code_val},
        )
        if row.first() is None:
            raise OptionCodeNotFound(param_val, option_code_val)
    # A: band-based, no option code table — validation skipped by design

    obj = RuleOptionSynonym(
        id=uuid.uuid4(),
        rule_set_id=rs_id_val,
        parameter=param_val,
        option_code=option_code_val,
        synonym_raw=synonym_raw_val,
        synonym_norm=synonym_norm_val,
        priority=priority_val,
        created_by=created_by,
    )
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        # Fix-H1: rollback 後只用純值查詢，不碰已過期的 ORM 屬性
        existing = (
            await session.execute(
                select(RuleOptionSynonym).where(
                    RuleOptionSynonym.rule_set_id == rs_id_val,
                    RuleOptionSynonym.parameter == param_val,
                    RuleOptionSynonym.synonym_norm == synonym_norm_val,
                )
            )
        ).scalar_one_or_none()
        raise SynonymConflict(existing=_to_dict(existing) if existing else {})

    await session.commit()
    return _to_dict(obj)


async def delete_synonym(
    session: AsyncSession,
    synonym_id: str,
    rule_set_code: str,
) -> None:
    """刪除同義詞；不存在或不屬於指定 rule-set 時 raise SynonymNotFound。"""
    rs = await _get_rule_set(session, rule_set_code)
    # ADR-024 §5：retired 終態不可增刪同義詞。只擋 retired，不擋 published（ADR-014 特例）。
    _assert_not_retired(rs)
    try:
        sid = uuid.UUID(synonym_id)
    except ValueError:
        raise SynonymNotFound(synonym_id)

    obj = (
        await session.execute(
            select(RuleOptionSynonym).where(
                RuleOptionSynonym.id == sid,
                RuleOptionSynonym.rule_set_id == rs.id,
            )
        )
    ).scalar_one_or_none()
    if obj is None:
        raise SynonymNotFound(synonym_id)

    await session.delete(obj)
    await session.commit()
