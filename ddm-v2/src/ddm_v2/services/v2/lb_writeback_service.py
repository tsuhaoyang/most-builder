"""LB 回寫解析／聚合／差異（ADR-036 B4；純函式優先）。

契約欄位權威在 LB `MOST_INTEGRATION_INPUT_SPEC.md` §8——本檔不重述欄位，衝突以該節為準並回報。
聚合規則見 ADR-036 D6；驗證與三類（matched/unmatched/missing）見 D7。

**general 判定用 MOST 自己的 is_general**（`level_entries.is_general`），不從 LB payload 猜（ADR-036 D6）。
**已知缺口（LB 修正中）**：本版 fixture 不含 general 列（LB 的 general 求解後插回、取得新 task id，
未登記進站清單而被回寫略過）。因此 general 列會落在 `missing`，reason 須能分辨：
- `general_not_written_back`：MOST 端是 general 列，但回寫沒有它（LB 缺口，會修）。
- `simo_subordinate`：SIMO 從屬列，MOST 本就不輸出（ADR-023 D10 追記），非缺口、正常。
- `no_result`：其餘 MOST 有、回寫沒有（如 offline 列不在結果、或該列未被排）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

WRITEBACK_CONTRACT_VERSION = "lb-most-writeback-v1"


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


@dataclass(frozen=True)
class MostRowInfo:
    """diff 需要的 MOST 端列資訊（由呼叫端自 level_entries／wi_rows 組出）。"""

    wi_row_id: str
    is_general: bool
    is_simo_subordinate: bool
    offline: bool
    expected_n: int | None = None  # frequency／repeat 的 N（Q>1 才有意義）


@dataclass
class WritebackDiff:
    matched: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)          # LB 有、MOST 沒有
    missing: list[dict[str, str]] = field(default_factory=list)  # MOST 有、LB 沒有：{wi_row_id, reason}
    offline_diffs: list[dict[str, Any]] = field(default_factory=list)
    unit_mismatches: list[dict[str, Any]] = field(default_factory=list)


# ── 純函式 ──────────────────────────────────────────────────────────────────

def parse(payload: dict) -> ParsedWriteback:
    """驗契約版本（不符 → LbWritebackContractMismatch）；逐 row 轉 RowPlacement；未知欄位忽略。"""
    cv = payload.get("contract_version")
    if cv != WRITEBACK_CONTRACT_VERSION:
        raise LbWritebackContractMismatch(cv)
    try:
        rows = [
            RowPlacement(
                source_wi_row_id=str(r["source_wi_row_id"]),
                task_id=int(r["task_id"]),
                offline_flag=bool(r["offline_flag"]),
                line_index=r.get("line_index"),
                station_index=r.get("station_index"),
                workers=list(r.get("workers") or []),
                units=r.get("units"),
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
        # units_total：逐 worker 加總（Q>1 才有 units）
        units_total: int | None = None
        for r in rs:
            if r.units:
                units_total = (units_total or 0) + sum(int(u.get("units", 0)) for u in r.units)
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
        )
    return out


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
            reason = "general_not_written_back"   # LB 缺口（會修）
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

    # units 不符（matched 且有 expected_n 且聚合有 units_total）
    for wi in d.matched:
        m = most_by_id[wi]
        mp = aggregated[wi]
        if m.expected_n is not None and mp.units_total is not None and m.expected_n != mp.units_total:
            d.unit_mismatches.append(
                {"wi_row_id": wi, "expected_n": m.expected_n, "units_total": mp.units_total}
            )
    return d


def build_most_rows_from_read(worksheet_read: dict) -> list[MostRowInfo]:
    """從 read_worksheet 的回應組出 diff 需要的 MostRowInfo（is_general／offline／simo 由 MOST 端資料）。

    SIMO 從屬列：`simo_group_id` 非空且非該群組主列——read_worksheet 已正規化 `simo_group_id`
    （標記列非空）；此處保守以「有 simo_group_id」視為從屬（主列不帶標記）。
    """
    out: list[MostRowInfo] = []
    for r in worksheet_read.get("rows", []) or []:
        tags = r.get("lb_tags") or {}
        simo = (r.get("simo_group_id") or "").strip()
        freq = r.get("frequency")
        out.append(MostRowInfo(
            wi_row_id=str(r["wi_row_id"]),
            is_general=bool(tags.get("is_general", False)),
            is_simo_subordinate=bool(simo),
            offline=bool(tags.get("offline", False)),
            expected_n=int(freq) if (freq is not None and float(freq) > 1) else None,
        ))
    return out


def general_ids_from_read(worksheet_read: dict) -> set[str]:
    """MOST 端 is_general 的 wi_row_id 集合（aggregate 的 general_ids 用；不從 LB payload 猜）。"""
    return {
        str(r["wi_row_id"])
        for r in worksheet_read.get("rows", []) or []
        if (r.get("lb_tags") or {}).get("is_general", False)
    }


def summarize(parsed: ParsedWriteback, agg: dict[str, MotionPlacement], d: WritebackDiff) -> dict[str, Any]:
    """給端點回應的摘要（人看＋前端用）。"""
    return {
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
        "motions": {
            wi: {
                "task_ids": mp.task_ids,
                "stations": sorted(mp.stations),
                "workers": sorted(mp.workers),
                "units_total": mp.units_total,
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
    d = diff(build_most_rows_from_read(worksheet_read), agg)
    snap_id = await persist(
        session, worksheet_id=worksheet_id, payload=payload, parsed=parsed,
        source_url=source_url, actor=actor,
    )
    return {"snapshot_id": str(snap_id), "summary": summarize(parsed, agg, d), "diff": diff_to_dict(agg, d)}


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
    d = diff(build_most_rows_from_read(worksheet_read), agg)
    return {
        "snapshot_id": str(snap.id), "fetched_at": snap.fetched_at.isoformat() if snap.fetched_at else None,
        "applied_at": snap.applied_at.isoformat() if snap.applied_at else None,
        "summary": summarize(parsed, agg, d), "diff": diff_to_dict(agg, d),
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
    d = diff(build_most_rows_from_read(read), agg)
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
        # 投影報告（E 碼擋）
        report = await exp.lb_export_report(session, worksheet_id)
        proj_errors = report.get("errors") or []

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
    snap.applied_rows = {"applied": sorted(applied), "propagated": propagated}
    await session.flush()
    return {"applied": sorted(applied), "propagated": propagated, "report": {"errors": [], "warnings": report.get("warnings", [])}}


async def _read(session: AsyncSession, worksheet_id: _uuid.UUID) -> dict:
    from ddm_v2.services.v2.worksheet_service import read_worksheet
    return await read_worksheet(session, worksheet_id)
