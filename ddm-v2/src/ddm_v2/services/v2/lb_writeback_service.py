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
