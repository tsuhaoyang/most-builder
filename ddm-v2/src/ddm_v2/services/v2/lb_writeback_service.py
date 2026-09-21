"""LB 回寫解析／聚合／差異（ADR-036 B4；純函式優先）。

契約欄位權威在 LB `MOST_INTEGRATION_INPUT_SPEC.md` §8——本檔不重述欄位，衝突以該節為準並回報。
聚合規則見 ADR-036 D6；驗證與三類（matched/unmatched/missing）見 D7。

**general 判定用 MOST 自己的 is_general**（`level_entries.is_general`），不從 LB payload 猜（ADR-036 D6）。
LB 自 aac992f 起會回寫 general（插回的 general 保留 source_wi_row_id；2026-09-18 真機複驗確認）。
missing 的 reason 須能分辨：
- `general_not_written_back`：MOST 端是 general 列，但回寫沒有它——代表回歸或 LB 版本過舊，要查。
- `simo_subordinate`：SIMO 從屬列，MOST 本就不輸出（ADR-023 D10 追記），非缺口、正常。
- `no_result`：其餘 MOST 有、回寫沒有（如 offline 列不在結果、或該列未被排）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

WRITEBACK_CONTRACT_VERSION = "lb-most-writeback-v1"

logger = logging.getLogger(__name__)

QtyScope = Literal["setup", "cyclic"]
UnitsSource = Literal["cyclic", "inferred_max"]
_QTY_SCOPES: frozenset[str] = frozenset({"setup", "cyclic"})

# 件數來源（MotionPlacement.units_source）：cyclic＝取 qty_scope=="cyclic" 那列；inferred_max＝payload
# 沒有 qty_scope（舊快照／LB 尚未加欄）時退回「各列 Σunits 取最大值」的推算值。
UNITS_SOURCE_CYCLIC: UnitsSource = "cyclic"
UNITS_SOURCE_INFERRED: UnitsSource = "inferred_max"

# 件數比對基準（summary.units_baseline.status）：ok＝已用 MOST 投影 Q 比對；unavailable＝MOST 目前投影不出來
# （reasons 帶 E 碼），件數沒有比對——不可讀成「一致」；not_needed＝MOST 投影沒有任何 Q>1 的 motion，不必比。
# 判斷一律以 MOST 投影為準，不從 LB 缺值推論（LB 對 Q>1 也可能不帶 units，例如 lot 被搬站後的重放）。
UNITS_BASELINE_OK = "ok"
UNITS_BASELINE_UNAVAILABLE = "unavailable"
UNITS_BASELINE_NOT_NEEDED = "not_needed"

# apply-offline 的投影報告狀態（同一降級模式）：ok＝報告算得出來（E 碼照常擋並整批 rollback）；
# unavailable＝投影此刻拋例外（reasons 附 E 碼），E 碼那一關無從判定，端點仍回 200 並明確標示。
REPORT_STATUS_OK = "ok"
REPORT_STATUS_UNAVAILABLE = "unavailable"


class LbWritebackContractMismatch(Exception):
    """回寫 payload 的 contract_version 不是 lb-most-writeback-v1（ADR-036 D7，擋）。"""

    def __init__(self, got: str | None) -> None:
        self.got = got
        super().__init__(
            f"回寫契約版本不符：預期 {WRITEBACK_CONTRACT_VERSION!r}，得 {got!r}"
        )


class LbWritebackMalformed(Exception):
    """回寫 payload 契約版本對，但 row 缺必要欄位／型別錯（route 映 422，不落 500）。"""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"回寫 payload 格式錯誤：{detail}")


# ── 資料型別（純資料，無 IO）────────────────────────────────────────────────

@dataclass(frozen=True)
class RowPlacement:
    """回寫 rows[] 的一列（LB §8）。未知欄位忽略（加法相容）。"""

    source_wi_row_id: str
    task_id: int
    offline_flag: bool
    line_index: int | None
    station_index: int | None
    workers: list[str]
    units: list[dict[str, Any]] | None  # [{worker, units}] 或 None
    qty_scope: QtyScope | None = None  # LB 加欄後才有；缺欄＝None，件數走推算退路


@dataclass(frozen=True)
class ParsedWriteback:
    contract_version: str
    project_id: str
    version_id: str
    result_id: str
    generated_at: str | None
    unattended_machine_policy: str
    unattended_machine_policy_source: str
    rows: list[RowPlacement]


@dataclass(frozen=True)
class MotionPlacement:
    """同一 source_wi_row_id 聚合後的一個 motion 的實際結果（ADR-036 D6）。"""

    source_wi_row_id: str
    task_ids: list[int]
    stations: set[int]
    workers: set[str]
    units_total: int | None
    offline_values: set[bool]
    cross_station: bool
    offline_conflict: bool
    units_source: UnitsSource | None = None  # 無件數為 None


@dataclass(frozen=True)
class MostRowInfo:
    """diff 需要的 MOST 端列資訊（由呼叫端自 level_entries／wi_rows 組出）。"""

    wi_row_id: str
    is_general: bool
    is_simo_subordinate: bool
    offline: bool
    expected_n: int | None = None  # MOST 投影出的 quantity Q（契約 §3.2；只在 Q>1 時有值）


@dataclass
class WritebackDiff:
    matched: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)          # LB 有、MOST 沒有
    missing: list[dict[str, str]] = field(default_factory=list)  # MOST 有、LB 沒有：{wi_row_id, reason}
    offline_diffs: list[dict[str, Any]] = field(default_factory=list)
    unit_mismatches: list[dict[str, Any]] = field(default_factory=list)
    # MOST 投影 Q>1、但 LB 沒給出件數（非 offline）：沒得比，明列出來而不是靜默略過
    units_uncomparable: list[dict[str, Any]] = field(default_factory=list)


# ── 純函式 ──────────────────────────────────────────────────────────────────

def _parse_int(raw: Any, name: str, *, nullable: bool = False) -> int | None:
    """整數欄：bool、小數、字串一律不收（不做 int() 截斷或轉型）；nullable 時 None 放行。"""
    if raw is None and nullable:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{name} 必須是整數{'或 null' if nullable else ''}，得 {raw!r}")
    return raw


def _parse_bool(raw: Any, name: str) -> bool:
    """布林欄：只收 true／false（"false" 字串會被 bool() 變成 True，套 offline 時會寫錯）。"""
    if not isinstance(raw, bool):
        raise ValueError(f"{name} 必須是 true／false，得 {raw!r}")
    return raw


def _parse_workers(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(w, str) and w for w in raw):
        raise ValueError("workers 必須是非空字串陣列或 null")
    return list(raw)


def _parse_units(raw: Any) -> list[dict[str, Any]] | None:
    """units：null 或 [{worker: 非空字串, units: 非負整數}]。其餘（字串、物件、小數、NaN、bool、負數）→ ValueError。"""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("units 必須是陣列或 null")
    out: list[dict[str, Any]] = []
    for u in raw:
        if not isinstance(u, dict):
            raise ValueError("units 的元素必須是物件")
        worker, n = u.get("worker"), u.get("units")
        if not isinstance(worker, str) or not worker:
            raise ValueError("units.worker 必須是非空字串")
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError(f"units.units 必須是非負整數，得 {n!r}")
        out.append({"worker": worker, "units": n})
    return out


def _parse_qty_scope(raw: Any) -> QtyScope | None:
    """qty_scope：缺欄／null 或 setup｜cyclic（大小寫、空字串、其他值都不收——未知值會讓件數比對失真）。"""
    if raw is None:
        return None
    if not isinstance(raw, str) or raw not in _QTY_SCOPES:
        raise ValueError(f"qty_scope 只能是 setup／cyclic 或缺欄，得 {raw!r}")
    return raw  # type: ignore[return-value]


def parse(payload: dict) -> ParsedWriteback:
    """驗契約版本（不符 → LbWritebackContractMismatch）；逐 row 轉 RowPlacement；未知欄位忽略。

    row 的必要欄位／型別錯（source_wi_row_id 非 UUID、task_id／index 非整數、offline_flag 非布林、workers／units
    形狀錯、qty_scope 值域外）→ LbWritebackMalformed
    （路由 422），不讓壞 payload 落到後段變成 500。
    """
    cv = payload.get("contract_version")
    if cv != WRITEBACK_CONTRACT_VERSION:
        raise LbWritebackContractMismatch(cv)
    try:
        rows = [
            RowPlacement(
                source_wi_row_id=str(UUID(str(r["source_wi_row_id"]))),
                task_id=_parse_int(r["task_id"], "task_id"),
                offline_flag=_parse_bool(r["offline_flag"], "offline_flag"),
                line_index=_parse_int(r.get("line_index"), "line_index", nullable=True),
                station_index=_parse_int(r.get("station_index"), "station_index", nullable=True),
                workers=_parse_workers(r.get("workers")),
                units=_parse_units(r.get("units")),
                qty_scope=_parse_qty_scope(r.get("qty_scope")),
            )
            for r in payload.get("rows", [])
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise LbWritebackMalformed(f"row 缺必要欄位或型別錯：{exc}") from exc
    return ParsedWriteback(
        contract_version=cv,
        project_id=str(payload.get("project_id", "")),
        version_id=str(payload.get("version_id", "")),
        result_id=str(payload.get("result_id", "")),
        generated_at=payload.get("generated_at"),
        unattended_machine_policy=str(payload.get("unattended_machine_policy", "")),
        unattended_machine_policy_source=str(payload.get("unattended_machine_policy_source", "")),
        rows=rows,
    )


def aggregate(
    rows: list[RowPlacement],
    *,
    general_ids: set[str] | None = None,
) -> dict[str, MotionPlacement]:
    """同一 source_wi_row_id 聚合（ADR-036 D6）。

    general_ids：MOST 端 is_general 的 wi_row_id 集合（**用 MOST 自己的判定**，不從 payload 猜）。
    general 列的多站是預期，不標 cross_station。
    """
    general_ids = general_ids or set()
    by_wi: dict[str, list[RowPlacement]] = {}
    for r in rows:
        by_wi.setdefault(r.source_wi_row_id, []).append(r)

    out: dict[str, MotionPlacement] = {}
    for wi, rs in by_wi.items():
        stations = {r.station_index for r in rs if r.station_index is not None}
        workers = {w for r in rs for w in r.workers}
        offline_values = {r.offline_flag for r in rs}
        units_total, units_source = _motion_units(rs)
        is_general = wi in general_ids
        out[wi] = MotionPlacement(
            source_wi_row_id=wi,
            task_ids=[r.task_id for r in rs],
            stations=stations,
            workers=workers,
            units_total=units_total,
            offline_values=offline_values,
            # 跨站：站集合 >1 且非 general（general 多站是預期，不算異常）
            cross_station=(len(stations) > 1 and not is_general),
            offline_conflict=(len(offline_values) > 1),
            units_source=units_source,
        )
    return out


def _motion_units(rs: list[RowPlacement]) -> tuple[int | None, UnitsSource | None]:
    """一個 motion 的件數（Howard 2026-09-18 裁：C＋退路；ADR-036 D6 待整合架構師修訂）。

    LB 的 setup 列 units 是 used（0／1，跨 worker 加總＝經手人數），不是件數（LB ADR-008 D3）——不能跨列加總
    （舊做法把工具 1/8/1 加成 10）。每列先逐 worker 加總，再：
    - payload 有 qty_scope（LB 加欄後）→ 取 cyclic 列的值（持工具 F>1 三列皆 cyclic、值相同，取最大）。
    - 沒有（舊快照／LB 尚未加欄）→ 退回各列取最大值（cyclic 列 Σ＝Q ≥ setup 列 Σ＝k），標為推算值。
    Q＝1 的列 LB 不帶 units → (None, None)。
    """
    per_row = [(r, sum(u["units"] for u in r.units)) for r in rs if r.units]  # units 已在 parse 驗過形狀
    if not per_row:
        return None, None
    if any(r.qty_scope is not None for r, _ in per_row):
        cyclic = [n for r, n in per_row if r.qty_scope == "cyclic"]
        return (max(cyclic), UNITS_SOURCE_CYCLIC) if cyclic else (None, None)
    return max(n for _, n in per_row), UNITS_SOURCE_INFERRED


def diff(
    most_rows: list[MostRowInfo],
    aggregated: dict[str, MotionPlacement],
) -> WritebackDiff:
    """三類比對（ADR-036 D7）＋ offline 差異 ＋ units 不符。"""
    d = WritebackDiff()
    most_by_id = {m.wi_row_id: m for m in most_rows}
    most_ids = set(most_by_id)
    agg_ids = set(aggregated)

    # matched：兩邊都有
    d.matched = sorted(most_ids & agg_ids)
    # unmatched：LB 有、MOST 沒有（可能別份 worksheet 的結果）
    d.unmatched = sorted(agg_ids - most_ids)
    # missing：MOST 有、LB 沒有——分 reason
    for wi in sorted(most_ids - agg_ids):
        m = most_by_id[wi]
        if m.is_general:
            reason = "general_not_written_back"   # LB 應回寫 general（aac992f 起）；出現＝回歸或舊版 LB
        elif m.is_simo_subordinate:
            reason = "simo_subordinate"            # 本就不輸出（正常）
        else:
            reason = "no_result"                   # offline 列不在結果／未排
        d.missing.append({"wi_row_id": wi, "reason": reason})

    # offline 差異（matched 列）：MOST offline != 聚合 offline
    for wi in d.matched:
        m = most_by_id[wi]
        mp = aggregated[wi]
        lb_offline = any(mp.offline_values) if mp.offline_values else False
        if m.offline != lb_offline:
            d.offline_diffs.append({"wi_row_id": wi, "most_offline": m.offline, "lb_offline": lb_offline})

    # units 不符（matched 且有 expected_n（MOST 投影 Q）且聚合有 units_total）；
    # MOST Q>1 而 LB 沒給件數（非 offline）→ units_uncomparable（沒得比，明列，不可讀成一致）
    for wi in d.matched:
        m = most_by_id[wi]
        mp = aggregated[wi]
        if m.expected_n is None:
            continue
        if mp.units_total is None:
            if not any(mp.offline_values):
                d.units_uncomparable.append({"wi_row_id": wi, "expected_n": m.expected_n, "reason": "no_units"})
        elif m.expected_n != mp.units_total:
            d.unit_mismatches.append({"wi_row_id": wi, "expected_n": m.expected_n,
                                      "units_total": mp.units_total, "units_source": mp.units_source})
    return d


def build_most_rows_from_read(worksheet_read: dict, *, projected_quantity: dict[str, int]) -> list[MostRowInfo]:
    """從 read_worksheet 的回應組出 diff 需要的 MostRowInfo（is_general／offline／simo 由 MOST 端資料）。

    projected_quantity：MOST 投影出的 {wi_row_id: Q}（只含 Q>1；`export_service.projected_quantities`）——件數比對
    的基準。不用 frequency：持工具 F>1、repeat 列的 Q 由投影矩陣決定（契約 §3.2），frequency 對不上。

    SIMO 從屬列：`simo_group_id` 非空且非該群組主列——read_worksheet 已正規化 `simo_group_id`
    （標記列非空）；此處保守以「有 simo_group_id」視為從屬（主列不帶標記）。
    """
    out: list[MostRowInfo] = []
    for r in worksheet_read.get("rows", []) or []:
        tags = r.get("lb_tags") or {}
        simo = (r.get("simo_group_id") or "").strip()
        wi = str(r["wi_row_id"])
        out.append(MostRowInfo(
            wi_row_id=wi,
            is_general=bool(tags.get("is_general", False)),
            is_simo_subordinate=bool(simo),
            offline=bool(tags.get("offline", False)),
            expected_n=projected_quantity.get(wi),
        ))
    return out


def general_ids_from_read(worksheet_read: dict) -> set[str]:
    """MOST 端 is_general 的 wi_row_id 集合（aggregate 的 general_ids 用；不從 LB payload 猜）。"""
    return {
        str(r["wi_row_id"])
        for r in worksheet_read.get("rows", []) or []
        if (r.get("lb_tags") or {}).get("is_general", False)
    }


def summarize(
    parsed: ParsedWriteback, agg: dict[str, MotionPlacement], d: WritebackDiff,
    units_baseline: dict[str, Any],
) -> dict[str, Any]:
    """給端點回應的摘要（人看＋前端用）。units_baseline：件數比對基準狀態（見 UNITS_BASELINE_*）；必填——
    漏傳就等於無聲宣稱「不必比」。"""
    return {
        "units_baseline": units_baseline,
        "contract_version": parsed.contract_version,
        "project_id": parsed.project_id,
        "version_id": parsed.version_id,
        "result_id": parsed.result_id,
        "unattended_machine_policy": parsed.unattended_machine_policy,
        "unattended_machine_policy_source": parsed.unattended_machine_policy_source,
        "rows_in": len(parsed.rows),
        "motions": len(agg),
        "matched": len(d.matched),
        "unmatched": len(d.unmatched),
        "missing": len(d.missing),
        "cross_station": [wi for wi, mp in agg.items() if mp.cross_station],
        "offline_conflicts": [wi for wi, mp in agg.items() if mp.offline_conflict],
    }


def diff_to_dict(agg: dict[str, MotionPlacement], d: WritebackDiff) -> dict[str, Any]:
    """diff ＋逐 motion 聚合 → JSON-able（前端產線視角用）。"""
    return {
        "matched": d.matched,
        "unmatched": d.unmatched,
        "missing": d.missing,
        "offline_diffs": d.offline_diffs,
        "unit_mismatches": d.unit_mismatches,
        "units_uncomparable": d.units_uncomparable,
        "motions": {
            wi: {
                "task_ids": mp.task_ids,
                "stations": sorted(mp.stations),
                "workers": sorted(mp.workers),
                "units_total": mp.units_total,
                "units_source": mp.units_source,
                "offline": any(mp.offline_values) if mp.offline_values else False,
                "cross_station": mp.cross_station,
                "offline_conflict": mp.offline_conflict,
            }
            for wi, mp in agg.items()
        },
    }


# ── DB-facing（B5）：persist／retention／orchestration ────────────────────────
# 這一段碰 session（非純函式）；純解析／聚合／差異在上方。

import uuid as _uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from ddm_v2.errors.registry import ErrorCode  # noqa: E402
from ddm_v2.exceptions import (  # noqa: E402
    BadGatewayError,
    GatewayTimeoutError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from ddm_v2.models.v2.lb_writeback import LbRowPlacement, LbWritebackSnapshot  # noqa: E402
from ddm_v2.services.v2.lb_client import (  # noqa: E402
    LbAuthRequired,
    LbRequestFailed,
    LbTimeout,
    LbUnreachable,
    fetch_writeback,
)
from ddm_v2.settings import get_settings  # noqa: E402

RETENTION_PER_WORKSHEET = 10  # ADR-036 D4


async def persist(
    session: AsyncSession,
    *,
    worksheet_id: _uuid.UUID,
    payload: dict,
    parsed: ParsedWriteback,
    source_url: str | None,
    actor: str,
) -> _uuid.UUID:
    """存一筆 snapshot ＋逐列 placement，套保留策略（每 worksheet 最近 N 筆）。回 snapshot_id。"""
    snap = LbWritebackSnapshot(
        id=_uuid.uuid4(), worksheet_id=worksheet_id,
        contract_version=parsed.contract_version,
        lb_project_id=parsed.project_id, lb_version_id=parsed.version_id, lb_result_id=parsed.result_id,
        generated_at=_parse_dt(parsed.generated_at),
        unattended_machine_policy=parsed.unattended_machine_policy,
        unattended_machine_policy_source=parsed.unattended_machine_policy_source,
        source_url=source_url, payload=payload, created_by=actor,
    )
    session.add(snap)
    await session.flush()
    for r in parsed.rows:
        session.add(LbRowPlacement(
            id=_uuid.uuid4(), snapshot_id=snap.id,
            source_wi_row_id=_uuid.UUID(r.source_wi_row_id),
            task_id=r.task_id, line_index=r.line_index, station_index=r.station_index,
            workers=r.workers, units=r.units, offline_flag=r.offline_flag,
        ))
    await session.flush()
    await _enforce_retention(session, worksheet_id)
    return snap.id


async def _enforce_retention(session: AsyncSession, worksheet_id: _uuid.UUID) -> None:
    ids = (await session.execute(
        select(LbWritebackSnapshot.id)
        .where(LbWritebackSnapshot.worksheet_id == worksheet_id)
        .order_by(LbWritebackSnapshot.fetched_at.desc())
    )).scalars().all()
    stale = ids[RETENTION_PER_WORKSHEET:]
    if stale:
        # placements 靠 FK ON DELETE CASCADE 連帶刪
        await session.execute(delete(LbWritebackSnapshot).where(LbWritebackSnapshot.id.in_(stale)))
        await session.flush()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _not_configured() -> ServiceUnavailableError:
    return ServiceUnavailableError(
        "LB 回寫未設定：DDM_LB_API_BASE_URL 未設（v1 直連，設定後才能取得）",
        detail={"code": ErrorCode.LB_NOT_CONFIGURED},
    )


async def fetch_and_store(
    session: AsyncSession,
    *,
    worksheet_id: _uuid.UUID,
    worksheet_read: dict,
    lb_project_id: str,
    lb_version_id: str,
    lb_result_id: str,
    actor: str,
) -> dict[str, Any]:
    """呼叫 LB → 解析 → 存快照 → 回 {snapshot_id, summary, diff}（ADR-036 B5 fetch）。"""
    s = get_settings()
    if not s.lb_api_base_url:
        raise _not_configured()
    # 身分 header（ADR-036 D1 追記）：@me → 當前使用者員編；其餘為固定字串。LB 需三個 header 才 200。
    headers = {k: (actor if v == "@me" else v) for k, v in (s.lb_auth_headers or {}).items()}
    try:
        payload = await fetch_writeback(
            base_url=s.lb_api_base_url, project_id=lb_project_id, version_id=lb_version_id,
            result_id=lb_result_id, timeout_s=s.lb_timeout_s, headers=headers or None,
        )
    except LbTimeout as exc:
        # 逾時（單次操作／總時限）→ 504：LB 還在回應中或太慢，稍後再試。
        raise GatewayTimeoutError(
            "LB 還在回應中或太慢，稍後再試", detail={"code": ErrorCode.LB_TIMEOUT}
        ) from exc
    except LbAuthRequired as exc:
        # LB 回 401/403：缺身分 header（D1 追記）→ 502＋明確提示設定 DDM_LB_AUTH_HEADERS。
        raise BadGatewayError(
            "LB 需要身分 header（X-User-Id／X-Plant-Code／X-Username），請設定 DDM_LB_AUTH_HEADERS",
            detail={"code": ErrorCode.LB_AUTH_REQUIRED},
        ) from exc
    except LbUnreachable as exc:
        # 連不到（連線失敗／5xx／非預期狀態）→ 502。
        raise BadGatewayError(
            "連不到 LB，請確認服務與 DDM_LB_API_BASE_URL", detail={"code": ErrorCode.LB_UNREACHABLE}
        ) from exc
    except LbRequestFailed as exc:
        raise BadGatewayError(
            f"LB 回報請求失敗（HTTP {exc.status_code}）", detail={"code": ErrorCode.LB_UNREACHABLE}
        ) from exc
    source_url = (
        f"{s.lb_api_base_url.rstrip('/')}/api/v3/projects/{lb_project_id}"
        f"/versions/{lb_version_id}/results/{lb_result_id}/writeback"
    )
    return await _consume(session, worksheet_id, worksheet_read, payload, source_url, actor)


async def import_and_store(
    session: AsyncSession,
    *,
    worksheet_id: _uuid.UUID,
    worksheet_read: dict,
    payload: dict,
    actor: str,
) -> dict[str, Any]:
    """測試／離線驗證：直接吃 payload，走同一解析／存檔路徑（ADR-036 D1）。"""
    return await _consume(session, worksheet_id, worksheet_read, payload, None, actor)


async def _consume(
    session: AsyncSession,
    worksheet_id: _uuid.UUID,
    worksheet_read: dict,
    payload: dict,
    source_url: str | None,
    actor: str,
) -> dict[str, Any]:
    parsed = parse(payload)  # 契約不符 → LbWritebackContractMismatch（route 映 422）
    gids = general_ids_from_read(worksheet_read)
    agg = aggregate(parsed.rows, general_ids=gids)
    # 先存快照，再算件數基準與 diff（已知的投影例外在 _units_baseline 降級，不會讓這筆快照跟著失敗）
    snap_id = await persist(
        session, worksheet_id=worksheet_id, payload=payload, parsed=parsed,
        source_url=source_url, actor=actor,
    )
    pq, baseline = await _units_baseline(session, worksheet_id, worksheet_read)
    d = diff(build_most_rows_from_read(worksheet_read, projected_quantity=pq), agg)
    return {"snapshot_id": str(snap_id), "summary": summarize(parsed, agg, d, baseline), "diff": diff_to_dict(agg, d)}


# 留痕的 message 直接吃工序表欄位（例如 level 原字串，schema 上沒有長度上限），不截斷的話
# 會原樣進 jsonb，並在之後每一次 latest 回應裡回吐。診斷用不到那麼長。
_ERR_MESSAGE_MAX = 500


def _jsonable_err(err: Any) -> dict[str, Any]:
    """把 ProjectionError 壓成可寫進 jsonb 的 dict。

    這段程式存在的理由就是「投影出問題時不准 500」，所以它自己**不准失敗**：
    - `allow_nan=False`：NaN／inf 穿得過 `default=str`，但 PostgreSQL jsonb 直接拒收，
      會在 commit 時炸（frequency 是 Numeric，`CHECK (frequency > 0)` 擋不住 NaN）。
    - `default=str`：Decimal／date 之類壓成字串。
    - 壓不平就整個放棄 params（留 code／message 仍足以診斷），絕不把例外往外丟。
    """
    params: Any = None
    if err.params:
        try:
            params = json.loads(json.dumps(err.params, allow_nan=False, default=str))
        except (TypeError, ValueError) as exc:  # 不可序列化／NaN／inf
            logger.warning("投影錯誤 %s 的 params 無法序列化，已捨棄：%s", err.code, type(exc).__name__)
    message = (err.message or "")[:_ERR_MESSAGE_MAX]
    return {"code": err.code, "wi_row_id": err.wi_row_id, "message": message, "params": params}


def _projection_raises() -> tuple[type[Exception], ...]:
    """投影層**直接拋出**（而非收集進 `ProjectionResult.errors`）的例外——根因見 BL-ENG-2。

    實際逃得出投影的是前三類；`PrecedenceError` 在 `project_rows` 內就被接住轉成收集型 E，
    這裡仍列著它只是縱深（留著無害）。

    收斂根因前，每個呼叫投影的路徑都要各自降級（不得讓端點落成無信封 500）；這裡是那份清單的單一來源。
    延遲 import：投影層不該在 service 匯入時被拉進來。
    """
    from ddm_v2.lb_projection.precedence import PrecedenceError
    from ddm_v2.lb_projection.quantity import QuantityError
    from ddm_v2.lb_projection.tmu import TmuDecompositionError
    from ddm_v2.lb_projection.tools import ToolResolveError

    return (QuantityError, ToolResolveError, TmuDecompositionError, PrecedenceError)


async def _units_baseline(
    session: AsyncSession, worksheet_id: _uuid.UUID, worksheet_read: dict,
) -> tuple[dict[str, int], dict[str, Any]]:
    """件數比對基準＝MOST 目前投影出的 Q。回 (projected_quantity, {status, reasons})。

    - 一律投影（不從 LB 缺值推論「全為 Q=1」）；投影沒有任何 Q>1 → not_needed。
    - 投影拋出（持工具 F>1 且 N>1、非整數 frequency、工具解析、TMU 分解）或收集到 E 碼 → unavailable＋E 碼：
      件數不比，但明確標示，回寫端點本身不因 MOST 端工序暫時投影不出來而失敗。
    """
    from ddm_v2.services.v2 import export_service as exp

    try:
        pq = await exp.projected_quantities(session, worksheet_id, worksheet_read=worksheet_read)
    except _projection_raises() as exc:
        logger.warning(
            "回寫件數基準不可用（worksheet %s 投影失敗）：%s（列 %s）", worksheet_id, exc.err.code, exc.err.wi_row_id
        )
        return {}, {"status": UNITS_BASELINE_UNAVAILABLE, "reasons": [exc.err.code]}
    if pq.error_codes:
        return {}, {"status": UNITS_BASELINE_UNAVAILABLE, "reasons": pq.error_codes}
    if not pq.by_row:
        return {}, {"status": UNITS_BASELINE_NOT_NEEDED, "reasons": []}
    return pq.by_row, {"status": UNITS_BASELINE_OK, "reasons": []}


async def latest(session: AsyncSession, *, worksheet_id: _uuid.UUID, worksheet_read: dict) -> dict[str, Any]:
    snap = (await session.execute(
        select(LbWritebackSnapshot)
        .where(LbWritebackSnapshot.worksheet_id == worksheet_id)
        .order_by(LbWritebackSnapshot.fetched_at.desc()).limit(1)
    )).scalar_one_or_none()
    if snap is None:
        raise NotFoundError("此 worksheet 尚無 LB 回寫快照", detail={"code": ErrorCode.NOT_FOUND, "resource": "lb_writeback_snapshot"})
    parsed = parse(snap.payload)
    gids = general_ids_from_read(worksheet_read)
    agg = aggregate(parsed.rows, general_ids=gids)
    pq, baseline = await _units_baseline(session, worksheet_id, worksheet_read)
    d = diff(build_most_rows_from_read(worksheet_read, projected_quantity=pq), agg)
    return {
        "snapshot_id": str(snap.id), "fetched_at": snap.fetched_at.isoformat() if snap.fetched_at else None,
        "applied_at": snap.applied_at.isoformat() if snap.applied_at else None,
        "applied_report_status": (snap.applied_rows or {}).get("report_status"),
        "applied_report_reasons": (snap.applied_rows or {}).get("report_reasons") or [],
        "applied_report_errors": (snap.applied_rows or {}).get("report_errors") or [],
        "summary": summarize(parsed, agg, d, baseline), "diff": diff_to_dict(agg, d),
    }


async def list_snapshots(session: AsyncSession, *, worksheet_id: _uuid.UUID) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(LbWritebackSnapshot)
        .where(LbWritebackSnapshot.worksheet_id == worksheet_id)
        .order_by(LbWritebackSnapshot.fetched_at.desc()).limit(RETENTION_PER_WORKSHEET)
    )).scalars().all()
    return [
        {
            "snapshot_id": str(s.id),
            "lb_project_id": s.lb_project_id, "lb_version_id": s.lb_version_id, "lb_result_id": s.lb_result_id,
            "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
            "applied_at": s.applied_at.isoformat() if s.applied_at else None,
            # 下一次 fetch 會產生新快照、latest 只回最新那筆；歷史清單不帶狀態的話，
            # 舊那筆的降級紀錄就整個 API 都讀不到了（本 service 沒有其他稽核寫入）
            "applied_report_status": (s.applied_rows or {}).get("report_status"),
            "applied_report_reasons": (s.applied_rows or {}).get("report_reasons") or [],
            "unattended_machine_policy": s.unattended_machine_policy,
        }
        for s in rows
    ]


async def count_snapshots(session: AsyncSession, *, worksheet_id: _uuid.UUID) -> int:
    return (await session.execute(
        select(func.count()).select_from(LbWritebackSnapshot)
        .where(LbWritebackSnapshot.worksheet_id == worksheet_id)
    )).scalar_one()


# ── B6：apply-offline（走正門：組內傳染 + R1–R9 + 投影；任一 E 整批 rollback）─────

from ddm_v2.models.v2.worksheet import LevelEntry, WiRow  # noqa: E402


async def apply_offline(
    session: AsyncSession,
    *,
    worksheet_id: _uuid.UUID,
    snapshot_id: _uuid.UUID,
    wi_row_ids: list[_uuid.UUID],
    actor: str,
) -> dict[str, Any]:
    """套用 LB 的 offline（ADR-036 D2）。走正門：
    1. 只接受該 snapshot 的 offline_diffs 出現過的 wi_row_id（其餘 422）。
    2. 寫 level_entries.offline=True ＋**組內傳染**（同 countersignature cub 或同 worker_cub wcub），
       規則與前端 store.toggleOffline 一致（後端才是權威，client 端只是 UX）。
    3. 跑 R1–R9（level 驗證）與投影（lb_export_report）；任一 E → 整批 rollback 並回報。
       投影**拋例外**（BL-ENG-2 的四類）時無從判定 E 碼那一關：不 rollback、不 500，回應的 `report.status`
       標 `unavailable`＋E 碼（同 fetch 的 units_baseline 降級模式）；R1–R9 仍照常擋。
    4. snapshot 記 applied_at／applied_rows。
    """
    from ddm_v2.services.v2 import export_service as exp
    from ddm_v2.services.v2 import level_validation_service as lvs

    snap = await session.get(LbWritebackSnapshot, snapshot_id)
    if snap is None or snap.worksheet_id != worksheet_id:
        raise NotFoundError(
            "找不到該 worksheet 的回寫快照",
            detail={"code": ErrorCode.NOT_FOUND, "resource": "lb_writeback_snapshot", "snapshot_id": str(snapshot_id)},
        )

    # 只接受 offline_diffs 出現過的 wi_row_id（重算 diff 取權威清單）
    read = await _read(session, worksheet_id)
    parsed = parse(snap.payload)
    agg = aggregate(parsed.rows, general_ids=general_ids_from_read(read))
    d = diff(build_most_rows_from_read(read, projected_quantity={}), agg)  # 只取 offline_diffs，不比件數
    diffable = {od["wi_row_id"] for od in d.offline_diffs}
    req = {str(x) for x in wi_row_ids}
    bad = req - diffable
    if bad:
        raise ValidationError(
            f"以下列不在此快照的 offline 差異清單中，不可套用：{sorted(bad)}",
            detail={"code": ErrorCode.VALIDATION_ERROR, "invalid_wi_row_ids": sorted(bad)},
        )

    # 載入本 worksheet 全部 level_entries（用 wi_row → LevelEntry），算傳染集合
    entries = (await session.execute(
        select(LevelEntry).join(WiRow, LevelEntry.wi_row_id == WiRow.id)
        .where(WiRow.worksheet_id == worksheet_id)
    )).scalars().all()
    by_wi = {str(e.wi_row_id): e for e in entries}

    def _group_members(seed_ids: set[str]) -> set[str]:
        """同 countersignature（cub）或同 worker_cub（wcub）視為同組，一起翻 offline。"""
        cubs = {(by_wi[i].countersignature or "").strip() for i in seed_ids if i in by_wi}
        cubs.discard("")
        wcubs = {(by_wi[i].worker_cub or "").strip() for i in seed_ids if i in by_wi}
        wcubs.discard("")
        members = set(seed_ids)
        for wi, e in by_wi.items():
            if (e.countersignature or "").strip() in cubs or (e.worker_cub or "").strip() in wcubs:
                members.add(wi)
        return members

    applied = _group_members(req)
    propagated = sorted(applied - req)

    async with session.begin_nested() as sp:
        for wi in applied:
            e = by_wi.get(wi)
            if e is not None:
                e.offline = True
        await session.flush()

        # R1–R9 驗證
        val = await lvs.validate_and_persist(session, worksheet_id, trigger="revalidate", actor=actor)
        level_ok = bool(val.get("valid", not val.get("issues")))
        level_issues = val.get("issues") or []
        # 投影報告（E 碼擋）；投影拋例外 → 降級標示，不 rollback、不 500
        report_status, report_reasons, report_errors = REPORT_STATUS_OK, [], []
        try:
            report = await exp.lb_export_report(session, worksheet_id)
            proj_errors = report.get("errors") or []
        except _projection_raises() as exc:
            logger.warning(
                "apply-offline 的投影報告不可用（worksheet %s 投影失敗）：%s（列 %s）",
                worksheet_id, exc.err.code, exc.err.wi_row_id,
            )
            # errors／warnings 給 None 而不是 []：[] 等於對消費端斷言「沒有錯誤也沒有警告」，
            # 但這裡是「沒算出來」。只讀 errors 不讀 status 的消費端應該炸，不該讀成一切正常。
            report, proj_errors = {"errors": None, "warnings": None}, []
            report_status, report_reasons = REPORT_STATUS_UNAVAILABLE, [exc.err.code]
            # 連 wi_row_id／params 一起留下：applied_rows 是 jsonb 歷史，現在不存，日後補欄也救不回
            # 已寫進去的那些。UI 要把 E 碼翻成「第 n 步：…」需要這些欄（levelSystem.plain.* 的模板參數）。
            report_errors = [_jsonable_err(exc.err)]

        if not level_ok or proj_errors:
            await sp.rollback()  # 任一 E → 整批 rollback，一列都不套
            raise ValidationError(
                "套用離線設定後驗證未過，已整批取消（未套用任何一列）",
                detail={
                    "code": ErrorCode.LEVEL_VALIDATION_FAILED if not level_ok else ErrorCode.LB_EXPORT_BLOCKED,
                    "level_issues": level_issues,
                    "projection_errors": [e_.get("code") if isinstance(e_, dict) else str(e_) for e_ in proj_errors],
                },
            )

    # 成功：記套用紀錄
    snap.applied_at = datetime.now(timezone.utc)
    snap.applied_rows = {
        "applied": sorted(applied), "propagated": propagated,
        "applied_by": actor,                 # 套用者（快照的 created_by 記的是取得的人，不是套用的人）
        "report_status": report_status,      # 投影那一關有沒有跑得起來——只活在當下回應會事後查不到
        "report_reasons": report_reasons,    # 裸 E 碼（相容既有讀取端）
        "report_errors": report_errors,      # 完整 ProjectionError（code/wi_row_id/message/params）
    }
    await session.flush()
    return {
        "applied": sorted(applied), "propagated": propagated,
        "report": {
            "status": report_status, "reasons": report_reasons, "reason_details": report_errors,
            # status=="ok" 時 errors 必為空（非空早已 rollback）；unavailable 時為 null＝沒算出來
            "errors": [] if report_status == REPORT_STATUS_OK else None,
            "warnings": report.get("warnings"),
        },
    }


async def _read(session: AsyncSession, worksheet_id: _uuid.UUID) -> dict:
    from ddm_v2.services.v2.worksheet_service import read_worksheet
    return await read_worksheet(session, worksheet_id)
