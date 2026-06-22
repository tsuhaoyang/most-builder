"""Excel 匯入服務（Phase 2a，ADR-013）：解析 → 暫存 → 欄位對應 → 正規化預覽。

容錯：壞列跳過/標記、缺欄留空、不整批失敗。MOST 仍權威（2a 只到 staging，不進 worksheet）。
"""
from __future__ import annotations

import io
from typing import Any

from ddm_v2.schemas.v2.import_excel import REQUIRED_FIELDS

_MAX_ROWS = 1000   # 每分頁存進 staging 的上限（避免巨大 JSONB）
_MAX_COLS = 60
_HAND_MAP = {"lh": "LH", "left": "LH", "左": "LH", "左手": "LH",
             "rh": "RH", "right": "RH", "右": "RH", "右手": "RH",
             "bh": "BH", "both": "BH", "雙": "BH", "雙手": "BH"}


def parse_workbook(content: bytes) -> dict[str, Any]:
    """讀 .xlsx 全分頁 → raw_payload（截斷）。"""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sheets = []
    for ws in wb.worksheets:
        grid: list[list[Any]] = []
        for r, row in enumerate(ws.iter_rows(values_only=True)):
            if r >= _MAX_ROWS:
                break
            cells = list(row[:_MAX_COLS])
            grid.append([_cell(c) for c in cells])
        n_cols = max((len(r) for r in grid), default=0)
        sheets.append({"name": ws.title, "grid": grid, "n_rows": len(grid), "n_cols": n_cols})
    wb.close()
    return {"sheets": sheets}


def _cell(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)  # date/time 等轉字串


def suggest_header_row(grid: list[list[Any]]) -> int:
    """啟發式：取「非空字串儲存格最多」的列當表頭（前 15 列內）。"""
    best, best_score = 0, -1
    for i, row in enumerate(grid[:15]):
        score = sum(1 for c in row if isinstance(c, str) and c.strip())
        if score > best_score:
            best, best_score = i, score
    return best


def apply_mapping(raw_payload: dict, sheet: str, header_row: int,
                  column_map: dict[str, int], time_unit: str) -> tuple[list[dict], list[str]]:
    """套欄位對應 → 正規化列 + warnings。"""
    sheets = {s["name"]: s for s in raw_payload.get("sheets", [])}
    if sheet not in sheets:
        return [], [f"找不到分頁：{sheet}"]
    grid = sheets[sheet]["grid"]
    warnings: list[str] = []
    rows: list[dict] = []
    factor = 60.0 if time_unit == "min" else 1.0

    for ri in range(header_row + 1, len(grid)):
        raw = grid[ri]
        rec: dict[str, Any] = {"_row": ri + 1}
        for field, col in column_map.items():
            rec[field] = raw[col] if (isinstance(col, int) and 0 <= col < len(raw)) else None
        # 整列皆空 → 跳過
        if all(rec.get(f) in (None, "") for f in column_map):
            continue
        # 正規化
        if "description" in rec and rec["description"] is not None:
            rec["description"] = str(rec["description"]).strip()
        if "hand" in rec and rec.get("hand") is not None:
            rec["hand"] = _HAND_MAP.get(str(rec["hand"]).strip().lower(), None)
        if "seconds" in column_map:
            rec["seconds"], w = _num(rec.get("seconds"))
            if rec["seconds"] is not None:
                rec["seconds"] = round(rec["seconds"] * factor, 4)
            elif w:
                warnings.append(f"列{ri + 1}：工時無法解析（{raw[column_map['seconds']]!r}）")
        if "quantity" in column_map:
            rec["quantity"], _ = _num(rec.get("quantity"))
        # 必填檢查
        for rf in REQUIRED_FIELDS:
            if not rec.get(rf):
                warnings.append(f"列{ri + 1}：缺必填「{rf}」")
        rows.append(rec)
    return rows, warnings


def _num(v: Any) -> tuple[float | None, bool]:
    """轉數字；回 (值, 是否原本有值但解析失敗)。"""
    if v is None or v == "":
        return None, False
    if isinstance(v, (int, float)):
        return float(v), False
    try:
        return float(str(v).strip().replace(",", "")), False
    except ValueError:
        return None, True
