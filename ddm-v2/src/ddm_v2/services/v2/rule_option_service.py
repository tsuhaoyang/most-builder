"""選項級 CRUD 服務（ADR-023 D2）。

兩種形狀（ADR-023 §2）：
- **選項型**（B / G / P.base / P.addon / M.verb / X / I）：有 `code` → 單筆 CRUD ＋ duplicate。
  刪除一律**硬刪**：只有 draft 可寫（`assert_editable`），而 draft 未被任何 cycle 引用
  （回放引用的是 published 版本的 rule_set_id），所以不需要 v3 的 soft-delete 分支。
- **帶型**（A / M.ladder / M.foot / M.rotation / M.hand）：無 code，帶界須整體遞增無重疊
  → 只提供**整組替換**。逐筆增刪會產生非法中間態，故不提供。

所有寫入前一律過 `rule_set_service.assert_editable`（certified_import / 非 draft → 409）
——**唯一的例外是 `update_option_en_text`**（ADR-032 D4 的 `_en` 專用寫入閘，
走 `assert_en_editable`，只有 retired 才 409）。那條路徑只碰 `label_en`／
`sentence_text_en` 兩欄，見該函式檔頭。
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2 import rule_set_tables as rt
from ddm_v2.nlp.normalization import normalize
from ddm_v2.schemas.v2.rule_set_options import (
    BandInvalid,
    OptionSpec,
    resolve,
    validate_bands,
)
from ddm_v2.services.v2.audit_service import log_audit
from ddm_v2.services.v2.rule_set_service import (
    RuleSetNotFound,
    assert_editable,
    assert_en_editable,
)

__all__ = [
    "EN_WRITABLE_FIELDS",
    "BandInvalid",
    "EnFieldNotWritable",
    "EnLabelNotUnique",
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
    "update_option_en_text",
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


async def _log_option_change(
    session: AsyncSession,
    rs: Any,
    spec: OptionSpec,
    action: str,
    actor: str | None,
    **payload: Any,
) -> None:
    """選項/帶級寫入的稽核（ADR-023 D7 / H-1）。

    為什麼非有不可：`log_audit` 原本只掛在 import/publish/activate/delete/unretire/retire
    ——全是**狀態遷移**，一個都不是「改值」。真正把 G 動作 `base_tmu` 6 改成 3 的那一刻
    完全無紀錄，事後 log 上只有按 publish 的 approver 員編，分不出「改值的人」與
    「覆核的人」，兩人覆核形同盲簽。

    payload 一律帶 `param`/`section`/`option_code` ＋ **前後值**（帶型是整組前後快照），
    因為只記「某人動過 G 參數」還原不了被改成什麼。
    """
    await log_audit(
        session,
        entity_type="rule_set",
        entity_id=rs.id,
        action=action,
        from_status=rs.status,
        to_status=rs.status,
        actor=actor or "unknown",
        payload={"code": rs.code, "param": spec.param, "section": spec.section, **payload},
    )
    await session.flush()


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
    session: AsyncSession, code: str, param: str, section: str | None, payload: dict[str, Any],
    actor: str | None = None,
) -> dict[str, Any]:
    spec = resolve(param, section)
    _require_options(spec)
    rs = await assert_editable(session, code)
    rs_id = rs.id
    data = validate_payload(spec, payload)
    existing = (
        await session.execute(
            select(spec.model.id).where(spec.model.rule_set_id == rs_id, spec.model.code == data["code"])
        )
    ).first()
    if existing is not None:
        raise OptionExists(data["code"])
    await _check_cross_row(session, spec, rs_id, data)
    row_id = uuid.uuid4()
    if data.get("label_en") is not None:
        await _assert_en_label_unique(session, spec, rs_id, row_id, data["label_en"])
    row = spec.model(id=row_id, rule_set_id=rs_id, **data)
    session.add(row)
    await session.flush()
    after = _serialize(spec, row)
    await _log_option_change(
        session, rs, spec, "option_create", actor,
        option_code=data["code"], before=None, after=after,
    )
    return after


async def update_option(
    session: AsyncSession, code: str, param: str, section: str | None, option_code: str,
    payload: dict[str, Any], actor: str | None = None,
) -> dict[str, Any]:
    spec = resolve(param, section)
    _require_options(spec)
    rs = await assert_editable(session, code)
    rs_id = rs.id
    row = await _find(session, spec, rs_id, option_code)
    before = _serialize(spec, row)  # 稽核前值：必須在 setattr 之前取
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
    # I5 也守一般編輯路徑（2026-08-20 cr 覆審）——見 `_assert_en_label_unique` 檔頭。
    # **以 `payload` 判斷、不用 `data`**：`validate_payload` 會拿現有列鋪底，`data` 一定
    # 有 `label_en` 這個鍵；只有「這次真的要寫 `label_en`」才檢查，否則改一個 `sort_order`
    # 會因為別人造成的既有衝突而被擋。
    if payload.get("label_en") is not None:
        await _assert_en_label_unique(session, spec, rs_id, row.id, data["label_en"])
    for field, value in data.items():
        setattr(row, field, value)
    await session.flush()
    after = _serialize(spec, row)
    await _log_option_change(
        session, rs, spec, "option_update", actor,
        option_code=option_code, before=before, after=after,
        changed_fields={
            f: {"before": before.get(f), "after": after.get(f)}
            for f in sorted(set(before) | set(after))
            if before.get(f) != after.get(f)
        },
    )
    return after


# ── `_en` 專用寫入路徑（ADR-032 D4）────────────────────────────────
#
# 這是**唯一**能把英文標籤／句面寫進 `certified_import` ＋ published ＋ active 版本
# 的入口，也就是 ADR-023 §3.3 規則 1 那條新列的實作。它與上面所有寫入的差別只有
# 一個：gate 換成 `assert_en_editable`（僅 retired 409）。代價是它繞過了
# `assert_editable`，所以**欄位範圍必須是機械的、不是慣例的**——白名單寫在這裡，
# 任何未來想「順便也讓這條路徑改一下 sort_order」的改動都會撞到 `EnFieldNotWritable`。
EN_WRITABLE_FIELDS = frozenset({"label_en", "sentence_text_en"})


class EnFieldNotWritable(ValueError):
    """試圖經 `_en` 寫入閘寫入白名單以外的欄位（ADR-032 D4／I3）。

    這不是「防呆」，是這條閘存在的前提：它是唯一繞過 `assert_editable` 的路徑，
    一旦能寫到 `label_zh`／`base_tmu`／`index_value`，就等於把 `_zh` 與 TMU 值
    一起解凍——ADR-032 D4 明文只授權 `_en`。
    """

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields
        super().__init__(
            f"`_en` 寫入閘只准寫 {sorted(EN_WRITABLE_FIELDS)}，收到：{sorted(fields)}"
            "（要改中文標籤或 TMU 值請走一般選項編輯，且需 draft ＋ 非 certified_import）"
        )


class EnLabelNotUnique(ValueError):
    """同一 (rule_set, 參數表) 內，`label_en` 正規化後與另一條選項衝突（ADR-032 I5）。

    量化的理由（ADR-032 R1）：`g_grasp`（抓握，6 TMU）與 `g_touch`（接觸，3 TMU）
    在英文介面下若看起來一樣，IE 選錯格＝**TMU 差一倍**。灌值腳本在灌值當下就守這件事；
    D4 開了線上編輯之後，這條線上路徑必須守同一件事，否則 I5 只剩「腳本灌的那批」成立。
    句面（`sentence_text_en`）**不受此限**：句面本來就允許重複（多條「刻意不入句」
    的選項句面同為空字串），唯一性是下拉選單辨義的要求，不是句子的要求。
    """

    def __init__(self, option_code: str, clashing: list[str], label_en: str) -> None:
        super().__init__(
            f"英文標籤 {label_en!r} 與同表既有選項 {sorted(clashing)} 正規化後相同"
            f"（{option_code}）：同一參數內英文標籤必須可辨義（ADR-032 I5），請改用不同的字面"
        )


async def _assert_en_label_unique(
    session: AsyncSession, spec: OptionSpec, rs_id: uuid.UUID, row_id: uuid.UUID, label_en: str
) -> None:
    """I5：同表（同一 rule_set）內 `label_en` 正規化後唯一。空字串／純空白不檢查
    （那是「沒有英文標籤」的另一種寫法，不是一個會被誤選的字面）。

    **三條寫入路徑共用（2026-08-20 cr 覆審補上前兩條）**：`create_option`／
    `update_option`（`label_en` 是 `_OptionIn` 的可寫欄位，先前完全沒有唯一性檢查——
    在任何 draft 上都還能把 `g_grasp`(6 TMU) 的英文改成與 `g_touch`(3 TMU) 相同，
    等於 I5 只在 `_en` 專用閘那一條路成立）與 `update_option_en_text`。
    上線前實測既有資料 63 筆 `label_en` 零衝突，接上不會讓任何既有編輯操作開始 409。

    **`duplicate_option` 刻意不接**：它整列複製（含 `label_en`），接上等於整個複製功能
    對任何已有英文標籤的選項一律 409。複製出來的列本來就是「待改的半成品」
    （`code` 也只是 `{code}_copy`），這個缺口記在 ADR-032 的已知邊界，不在本輪處理。
    """
    norm = normalize(label_en)
    if not norm.strip():
        return
    clashing = [
        r.code for r in await _rows(session, spec, rs_id)
        if r.id != row_id and r.label_en and normalize(r.label_en) == norm
    ]
    if clashing:
        raise EnLabelNotUnique(spec.param, clashing, label_en)


async def update_option_en_text(
    session: AsyncSession, code: str, param: str, section: str | None, option_code: str,
    payload: dict[str, Any], actor: str | None = None,
) -> dict[str, Any]:
    """只寫 `label_en`／`sentence_text_en`（ADR-032 D4）。**不觸發 clone-on-write。**

    與 `update_option` 的三個差異，每一個都是刻意的：

    1. **gate**＝`assert_en_editable`（僅 retired 409），不是 `assert_editable`
       ——D4 修訂 ADR-023 §3.3 規則 1，`_en` 在 draft／published／published+active 皆可寫。
    2. **欄位**＝`EN_WRITABLE_FIELDS` 白名單，白名單外一律 `EnFieldNotWritable`
       （422）。刻意**不走** `validate_payload()`：那支會拿現有列鋪底再過完整 schema，
       payload 帶什麼欄位就寫什麼欄位——對這條繞過 `assert_editable` 的路徑而言，
       那等於把整列解凍。
    3. **I5 唯一性**在寫入前檢查（`label_en` 專屬，見 `EnLabelNotUnique`）。

    `payload` 的鍵語意：**有鍵才寫**（呼叫端請用 `model_dump(exclude_unset=True)`），
    值為 `None` ＝清空該欄。空 payload ＝不改任何欄，但仍會回傳現值（不寫 audit）。
    """
    spec = resolve(param, section)
    _require_options(spec)
    unknown = [f for f in payload if f not in EN_WRITABLE_FIELDS]
    if unknown:
        raise EnFieldNotWritable(unknown)
    rs = await assert_en_editable(session, code)
    row = await _find(session, spec, rs.id, option_code)
    before = {f: getattr(row, f) for f in sorted(EN_WRITABLE_FIELDS)}

    if "label_en" in payload and payload["label_en"] is not None:
        await _assert_en_label_unique(session, spec, rs.id, row.id, payload["label_en"])
    changed = {f: v for f, v in payload.items() if getattr(row, f) != v}
    for field, value in changed.items():
        setattr(row, field, value)
    await session.flush()
    after = {f: getattr(row, f) for f in sorted(EN_WRITABLE_FIELDS)}
    if changed:
        await _log_option_change(
            session, rs, spec, "option_en_update", actor,
            option_code=option_code, before=before, after=after,
            changed_fields={
                f: {"before": before.get(f), "after": after.get(f)} for f in sorted(changed)
            },
        )
    return {
        "rule_set_code": rs.code, "param": spec.param, "section": spec.section,
        "code": option_code, **after,
    }


async def delete_option(
    session: AsyncSession, code: str, param: str, section: str | None, option_code: str,
    actor: str | None = None,
) -> dict[str, Any]:
    """硬刪（見模組 docstring：draft 無人引用，不需 soft-delete）。"""
    spec = resolve(param, section)
    _require_options(spec)
    rs = await assert_editable(session, code)
    rs_id = rs.id
    row = await _find(session, spec, rs_id, option_code)
    before = _serialize(spec, row)  # 實體刪除後，這是唯一還說得清刪掉什麼值的紀錄
    await session.execute(delete(spec.model).where(spec.model.id == row.id))
    await session.flush()
    await _log_option_change(
        session, rs, spec, "option_delete", actor,
        option_code=option_code, before=before, after=None,
    )
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
    session: AsyncSession, code: str, param: str, section: str | None, option_code: str,
    actor: str | None = None,
) -> dict[str, Any]:
    spec = resolve(param, section)
    _require_options(spec)
    rs = await assert_editable(session, code)
    rs_id = rs.id
    src = await _find(session, spec, rs_id, option_code)
    new_code = await _next_copy_code(session, spec, rs_id, option_code)
    data = {f: getattr(src, f) for f in spec.schema.model_fields}
    data["code"] = new_code
    data["sort_order"] = max((r.sort_order for r in await _rows(session, spec, rs_id)), default=-1) + 1
    row = spec.model(id=uuid.uuid4(), rule_set_id=rs_id, **data)
    session.add(row)
    await session.flush()
    after = _serialize(spec, row)
    await _log_option_change(
        session, rs, spec, "option_duplicate", actor,
        option_code=new_code, source_option_code=option_code, before=None, after=after,
    )
    return after


async def replace_bands(
    session: AsyncSession, code: str, param: str, section: str | None, items: list[dict[str, Any]],
    actor: str | None = None,
) -> dict[str, Any]:
    """整組替換一個帶型區塊（A 依 component、M 依 section）。

    稽核 payload 存**整組前後快照**：帶型沒有「選項代碼」可指認單列（ADR-023 §2），
    改動的語意本來就是「這一組帶從 X 變成 Y」，逐列 diff 反而會誤導
    （中間插入一帶會讓其後每一帶看起來都被改過）。
    """
    spec = resolve(param, section)
    _require_bands(spec)
    rs = await assert_editable(session, code)
    rs_id = rs.id

    data = [validate_payload(spec, item) for item in items]
    validate_bands(spec, data)
    before = [_serialize(spec, r) for r in await _rows(session, spec, rs_id)]

    stmt: Any = delete(spec.model).where(spec.model.rule_set_id == rs_id)
    if spec.filter_field is not None:
        stmt = stmt.where(getattr(spec.model, spec.filter_field) == spec.filter_value)
    await session.execute(stmt)
    await session.flush()

    for i, item in enumerate(data):
        extra = {spec.filter_field: spec.filter_value} if spec.filter_field else {}
        session.add(spec.model(id=uuid.uuid4(), rule_set_id=rs_id, **{**item, "sort_order": i}, **extra))
    await session.flush()
    result = await list_options(session, code, param, section)
    await _log_option_change(
        session, rs, spec, "bands_replace", actor,
        before=before, after=result["items"],
        row_counts={"before": len(before), "after": len(result["items"])},
    )
    return result
