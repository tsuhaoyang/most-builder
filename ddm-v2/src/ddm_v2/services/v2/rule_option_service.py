"""選項級 CRUD 服務（ADR-023 D2）。

兩種形狀（ADR-023 §2）：
- **選項型**（B / G / P.base / P.addon / M.verb / X / I）：有 `code` → 單筆 CRUD ＋ duplicate。
  刪除一律**硬刪**：只有 draft 可寫（`assert_editable`），而 draft 未被任何 cycle 引用
  （回放引用的是 published 版本的 rule_set_id），所以不需要 v3 的 soft-delete 分支。
- **帶型**（A / M.ladder / M.foot / M.rotation / M.hand）：無 code，帶界須整體遞增無重疊
  → 只提供**整組替換**。逐筆增刪會產生非法中間態，故不提供。

所有寫入前一律過 `rule_set_service.assert_editable`（certified_import / 非 draft → 409）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2 import rule_set_tables as rt
from ddm_v2.schemas.v2.rule_set_options import (
    BandInvalid,
    OptionSpec,
    resolve,
    validate_bands,
)
from ddm_v2.services.v2.rule_set_service import RuleSetNotFound, assert_editable

__all__ = [
    "BandInvalid",
    "OptionConstraintViolation",
    "OptionExists",
    "OptionNotFound",
    "create_option",
    "delete_option",
    "duplicate_option",
    "list_options",
    "replace_bands",
    "resolve",
    "update_option",
]


class OptionNotFound(Exception):
    pass


class OptionExists(Exception):
    pass


class OptionConstraintViolation(ValueError):
    """跨列語意約束（非單列 schema 可判定者），例如 P addon 的 max_select 必須全表一致。"""


class BandsNotSupported(ValueError):
    """對帶型區塊呼叫單筆 CRUD（或反之）。"""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _serialize(spec: OptionSpec, row: Any) -> dict[str, Any]:
    """以 schema 的欄位集為準序列化（欄位名＝ORM column 名，單一真實來源）。"""
    out: dict[str, Any] = {"id": str(row.id)}
    for field in spec.schema.model_fields:
        out[field] = _jsonable(getattr(row, field))
    return out


def validate_payload(spec: OptionSpec, payload: dict[str, Any], *, base: Any = None) -> dict[str, Any]:
    """以 (param, section) 解析出的 schema 驗證 payload。

    PATCH 用 `base`（現有 ORM 列）先鋪底再覆蓋 → 部分更新也能過**完整**驗證，
    不必另寫一套 all-optional schema（兩套 schema 必然漂移）。
    ValidationError 由呼叫端轉 422。
    """
    merged: dict[str, Any] = {}
    if base is not None:
        merged = {f: _jsonable(getattr(base, f)) for f in spec.schema.model_fields}
    merged.update(payload)
    return spec.schema.model_validate(merged).model_dump()


async def _rows(session: AsyncSession, spec: OptionSpec, rs_id: uuid.UUID) -> list[Any]:
    stmt: Any = select(spec.model).where(spec.model.rule_set_id == rs_id)
    if spec.filter_field is not None:
        stmt = stmt.where(getattr(spec.model, spec.filter_field) == spec.filter_value)
    return list((await session.execute(stmt.order_by(spec.model.sort_order))).scalars().all())


async def _get_rule_set_id(session: AsyncSession, code: str) -> uuid.UUID:
    from ddm_v2.models.v2.rule_set import RuleSet

    rs_id = (await session.execute(select(RuleSet.id).where(RuleSet.code == code))).scalar_one_or_none()
    if rs_id is None:
        raise RuleSetNotFound(code)
    return rs_id


async def _find(session: AsyncSession, spec: OptionSpec, rs_id: uuid.UUID, option_code: str) -> Any:
    row = (
        await session.execute(
            select(spec.model).where(
                spec.model.rule_set_id == rs_id, spec.model.code == option_code
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise OptionNotFound(option_code)
    return row


def _require_options(spec: OptionSpec) -> None:
    if spec.kind != "options":
        raise BandsNotSupported(
            f"{spec.param}.{spec.section} 是區間帶，無「選項代碼」概念；"
            f"請用 PUT /params/{spec.param}/bands 整組替換（ADR-023 §2）"
        )


def _require_bands(spec: OptionSpec) -> None:
    if spec.kind != "bands":
        raise BandsNotSupported(
            f"{spec.param}.{spec.section} 是選項表，請用 /params/{spec.param}/options 單筆 CRUD"
        )


# ── 讀 ────────────────────────────────────────────────────────────
async def list_options(
    session: AsyncSession, code: str, param: str, section: str | None, *, active_only: bool = False
) -> dict[str, Any]:
    """讀取一個 (param, section) 的所有列。

    ⚠️ 預設**不**過濾 is_active——編輯畫面必須看得到已停用的選項才能重新啟用。
    `active_only=true` 供下拉選單類消費端使用。
    """
    spec = resolve(param, section)
    rs_id = await _get_rule_set_id(session, code)
    rows = await _rows(session, spec, rs_id)
    if active_only:
        rows = [r for r in rows if r.is_active]
    return {
        "rule_set_code": code,
        "param": spec.param,
        "section": spec.section,
        "kind": spec.kind,
        "items": [_serialize(spec, r) for r in rows],
    }


# ── 選項型寫入 ─────────────────────────────────────────────────────
async def _check_cross_row(session: AsyncSession, spec: OptionSpec, rs_id: uuid.UUID, data: dict[str, Any], *, exclude_id: uuid.UUID | None = None) -> None:
    """跨列語意約束。

    目前僅 P.addon：引擎的 `p_addon_max = min(max_select for all addons)`（providers.py），
    因此 max_select 是**全表一個值**的語意；若容許逐列不同，改一列會靜默壓低整體上限。
    """
    if spec.model is not rt.RulePAddon:
        return
    others = [r for r in await _rows(session, spec, rs_id) if r.id != exclude_id]
    if not others:
        return
    existing = {r.max_select for r in others}
    if data["max_select"] not in existing or len(existing) > 1:
        raise OptionConstraintViolation(
            f"P addon 的 max_select 必須全表一致（引擎取 min 當 p_addon_max）："
            f"現有 {sorted(existing)}，收到 {data['max_select']}"
        )


async def create_option(
    session: AsyncSession, code: str, param: str, section: str | None, payload: dict[str, Any]
) -> dict[str, Any]:
    spec = resolve(param, section)
    _require_options(spec)
    await assert_editable(session, code)
    rs_id = await _get_rule_set_id(session, code)
    data = validate_payload(spec, payload)
    existing = (
        await session.execute(
            select(spec.model.id).where(spec.model.rule_set_id == rs_id, spec.model.code == data["code"])
        )
    ).first()
    if existing is not None:
        raise OptionExists(data["code"])
    await _check_cross_row(session, spec, rs_id, data)
    row = spec.model(id=uuid.uuid4(), rule_set_id=rs_id, **data)
    session.add(row)
    await session.flush()
    return _serialize(spec, row)


async def update_option(
    session: AsyncSession, code: str, param: str, section: str | None, option_code: str, payload: dict[str, Any]
) -> dict[str, Any]:
    spec = resolve(param, section)
    _require_options(spec)
    await assert_editable(session, code)
    rs_id = await _get_rule_set_id(session, code)
    row = await _find(session, spec, rs_id, option_code)
    data = validate_payload(spec, payload, base=row)
    if data["code"] != option_code:
        clash = (
            await session.execute(
                select(spec.model.id).where(spec.model.rule_set_id == rs_id, spec.model.code == data["code"])
            )
        ).first()
        if clash is not None:
            raise OptionExists(data["code"])
    await _check_cross_row(session, spec, rs_id, data, exclude_id=row.id)
    for field, value in data.items():
        setattr(row, field, value)
    await session.flush()
    return _serialize(spec, row)


async def delete_option(
    session: AsyncSession, code: str, param: str, section: str | None, option_code: str
) -> dict[str, Any]:
    """硬刪（見模組 docstring：draft 無人引用，不需 soft-delete）。"""
    spec = resolve(param, section)
    _require_options(spec)
    await assert_editable(session, code)
    rs_id = await _get_rule_set_id(session, code)
    row = await _find(session, spec, rs_id, option_code)
    await session.execute(delete(spec.model).where(spec.model.id == row.id))
    await session.flush()
    return {"deleted": option_code, "param": spec.param, "section": spec.section}


async def _next_copy_code(session: AsyncSession, spec: OptionSpec, rs_id: uuid.UUID, src_code: str) -> str:
    """`{code}_copy` → `{code}_copy_2` → …（連續 duplicate 不得撞 UNIQUE(rule_set_id, code)）。"""
    taken = {
        c for (c,) in (
            await session.execute(select(spec.model.code).where(spec.model.rule_set_id == rs_id))
        ).all()
    }
    base = f"{src_code}_copy"
    if base not in taken:
        return base
    for n in range(2, 1000):
        candidate = f"{base}_{n}"
        if candidate not in taken:
            return candidate
    raise OptionExists(base)


async def duplicate_option(
    session: AsyncSession, code: str, param: str, section: str | None, option_code: str
) -> dict[str, Any]:
    spec = resolve(param, section)
    _require_options(spec)
    await assert_editable(session, code)
    rs_id = await _get_rule_set_id(session, code)
    src = await _find(session, spec, rs_id, option_code)
    new_code = await _next_copy_code(session, spec, rs_id, option_code)
    data = {f: getattr(src, f) for f in spec.schema.model_fields}
    data["code"] = new_code
    data["sort_order"] = max((r.sort_order for r in await _rows(session, spec, rs_id)), default=-1) + 1
    row = spec.model(id=uuid.uuid4(), rule_set_id=rs_id, **data)
    session.add(row)
    await session.flush()
    return _serialize(spec, row)


async def replace_bands(
    session: AsyncSession, code: str, param: str, section: str | None, items: list[dict[str, Any]]
) -> dict[str, Any]:
    """整組替換一個帶型區塊（A 依 component、M 依 section）。"""
    spec = resolve(param, section)
    _require_bands(spec)
    await assert_editable(session, code)
    rs_id = await _get_rule_set_id(session, code)

    data = [validate_payload(spec, item) for item in items]
    validate_bands(spec, data)

    stmt: Any = delete(spec.model).where(spec.model.rule_set_id == rs_id)
    if spec.filter_field is not None:
        stmt = stmt.where(getattr(spec.model, spec.filter_field) == spec.filter_value)
    await session.execute(stmt)
    await session.flush()

    for i, item in enumerate(data):
        extra = {spec.filter_field: spec.filter_value} if spec.filter_field else {}
        session.add(spec.model(id=uuid.uuid4(), rule_set_id=rs_id, **{**item, "sort_order": i}, **extra))
    await session.flush()
    return await list_options(session, code, param, section)
