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

__all__ = ["CONTRACT_VERSION", "COLUMNS"]
