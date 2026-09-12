"""RowEmitter：LbTask → 24 欄 dict；CSV 輸出（\\n、UTF-8、無 BOM）。

WP0：僅定義凍結表頭（`COLUMNS`）與 `CONTRACT_VERSION`；`to_row`/`write_csv` 於 WP6 落地。
表頭順序與名稱由 `tests/unit/test_lb_projection_contract_freeze.py` 鎖定——
任何變動＝升 `CONTRACT_VERSION`＋同步 LB 契約（Spec §10、實作書 §6 禁止事項#5）。

出處：Spec §6（24 欄順序凍結）、§10（版本規則）。
"""
from __future__ import annotations

# Spec §0：v1.0 → v1.1 新增第 24 欄 general_role。以 Spec 標題宣告的版本為準（權威順序 Spec ＞ 實作書）。
CONTRACT_VERSION = "most-lb-csv-v1.1"

# Spec §6：輸出 24 欄，順序凍結。前 21 欄 = LB TASK_CSV_COLUMN_DEFS 順序；後 3 欄為擴充（LB reader 現況忽略）。
COLUMNS: tuple[str, ...] = (
    "task_id",
    "action",
    "part_id",
    "group",
    "atomic_group",
    "duration",
    "predecessors",
    "station_name",
    "action_type",
    "complexity_level",
    "adjustable",
    "fixed_station",
    "offline_flag",
    "tool_id",
    "tool_action",
    "divisible",
    "p2",
    "quantity",
    "segment",
    "qty_scope",
    "duration_basis",
    "source_wi_row_id",
    "role_type",
    "general_role",
)

__all__ = ["CONTRACT_VERSION", "COLUMNS", "LbTask", "to_row", "write_csv"]

import csv  # noqa: E402
import io  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402


@dataclass
class LbTask:
    """一個輸出列（24 欄）。空值以 None 表示，to_row 轉 ''；bool → 0/1。"""

    task_id: int
    action: str
    source_wi_row_id: str
    action_type: str
    adjustable: int = 0
    offline_flag: int = 0
    divisible: int = 0
    quantity: int = 1
    role_type: str = "human"
    part_id: str | None = None
    group: int | None = None
    atomic_group: int | None = None
    duration: int = 0
    predecessors: list[int] = field(default_factory=list)
    station_name: str | None = None
    fixed_station: int | None = None
    tool_id: str | None = None
    tool_action: str | None = None
    segment: str | None = None
    qty_scope: str | None = None
    duration_basis: str | None = None
    general_role: str | None = None
    complexity_level: str | None = None  # 恆空
    p2: str | None = None  # 恆空


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def to_row(task: LbTask) -> dict[str, str]:
    """LbTask → 24 欄 dict（鍵＝COLUMNS）。空值→''、bool→0/1、predecessors→逗號串。"""
    preds = ",".join(str(p) for p in task.predecessors) if task.predecessors else ""
    values = {
        "task_id": _cell(task.task_id),
        "action": _cell(task.action),
        "part_id": _cell(task.part_id),
        "group": _cell(task.group),
        "atomic_group": _cell(task.atomic_group),
        "duration": _cell(task.duration),
        "predecessors": preds,
        "station_name": _cell(task.station_name),
        "action_type": _cell(task.action_type),
        "complexity_level": _cell(task.complexity_level),
        "adjustable": _cell(task.adjustable),
        "fixed_station": _cell(task.fixed_station),
        "offline_flag": _cell(task.offline_flag),
        "tool_id": _cell(task.tool_id),
        "tool_action": _cell(task.tool_action),
        "divisible": _cell(task.divisible),
        "p2": _cell(task.p2),
        "quantity": _cell(task.quantity),
        "segment": _cell(task.segment),
        "qty_scope": _cell(task.qty_scope),
        "duration_basis": _cell(task.duration_basis),
        "source_wi_row_id": _cell(task.source_wi_row_id),
        "role_type": _cell(task.role_type),
        "general_role": _cell(task.general_role),
    }
    return {c: values[c] for c in COLUMNS}


def write_csv(tasks: list[LbTask]) -> str:
    """24 欄 CSV 文字（lineterminator='\\n'、fieldnames=COLUMNS、無 BOM）。"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(COLUMNS), lineterminator="\n")
    writer.writeheader()
    for t in tasks:
        writer.writerow(to_row(t))
    return buf.getvalue()
