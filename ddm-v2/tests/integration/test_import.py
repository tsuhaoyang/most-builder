"""Excel 匯入 2a 整合測試（ADR-013）：upload → map(preview) → profile；含邊界。"""
from __future__ import annotations

import io

import pytest

pytestmark = pytest.mark.integration


def _xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Assembly"
    ws.append(["Model:", "DL360", None, None, None])      # metadata
    ws.append([None, None, None, None, None])             # blank
    ws.append(["No.", "Element Description", "Average TT", "Quantity", "IEC PN"])  # header @ idx 2
    ws.append([1, "take out chassis", 5.9, 1, "PN1"])
    ws.append([2, "stick label", 4.85, 1, None])
    ws.append([None, None, None, None, None])             # empty row → skip
    ws.append([3, "screw bolt", "bad", 1, "PN3"])         # bad time → warn
    wb.create_sheet("Tests").append(["x"])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _files():
    return {"file": ("Touchtime.xlsx", _xlsx(),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


async def test_upload_detects_sheets_and_header(client):
    r = await client.post("/api/v2/imports/upload", files=_files())
    assert r.status_code == 200
    j = r.json()
    assert [s["name"] for s in j["sheets"]] == ["Assembly", "Tests"]
    assert j["suggested_header_row"] == 2          # 啟發式抓到真表頭
    assert "description" in j["target_fields"]


async def test_map_normalizes_and_warns(client):
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    r = await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1, "seconds": 2, "quantity": 3, "part_no": 4}, "time_unit": "sec"})
    assert r.status_code == 200
    j = r.json()
    assert j["n"] == 3                              # 空列被跳過
    assert j["rows"][0]["description"] == "take out chassis"
    assert j["rows"][0]["seconds"] == 5.9
    assert j["rows"][2]["seconds"] is None          # 壞工時 → None
    assert any("工時無法解析" in w for w in j["warnings"])


async def test_map_time_unit_minutes(client):
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    j = (await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1, "seconds": 2}, "time_unit": "min"})).json()
    assert j["rows"][0]["seconds"] == round(5.9 * 60, 4)   # 分→秒換算


async def test_profile_crud(client):
    p = await client.post("/api/v2/imports/profiles", json={
        "name": "ut-profile", "header_row": 2, "column_map": {"description": 1}, "time_unit": "sec"})
    assert p.status_code == 201
    pid = p.json()["id"]
    assert any(x["name"] == "ut-profile" for x in (await client.get("/api/v2/imports/profiles/list")).json())
    assert (await client.delete(f"/api/v2/imports/profiles/{pid}")).status_code == 204


async def test_rbac_viewer_cannot_upload(client):
    r = await client.post("/api/v2/imports/upload", files=_files(), headers={"X-Username": "ZZZUTVIEW2"})
    assert r.status_code == 403


# ───────────────────────────────────────────────────────────────
# Phase 2b submit tests（ADR-013 §2b；對應 F 規格驗收）
# ───────────────────────────────────────────────────────────────

# dev_seed_v2.py WORKSHEET = uuid.UUID("55555555-5555-5555-5555-555555555555")
_WS_SEEDED = "55555555-5555-5555-5555-555555555555"


async def test_submit_creates_wi_rows(client):
    """Happy path：staged rows → WiRow/MostCycle/LevelEntry 建立。
    同時驗 Fix-H2 迴歸：重複提交同一 import_id → 409。
    """
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1, "seconds": 2, "quantity": 3},
        "time_unit": "sec",
    })
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": _WS_SEEDED},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["n_rows"] == 3          # _xlsx() 有 3 筆非空列（空列被 apply_mapping 跳過）
    assert isinstance(j["n_with_analysis"], int)
    assert isinstance(j["n_need_review"], int)

    # Fix-H2 迴歸：status 已變為 "submitted"，再 submit 同一 import_id → 409
    r2 = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": _WS_SEEDED},
    )
    assert r2.status_code == 409


async def test_submit_not_mapped_returns_409(client):
    """upload 後（status=uploaded）直接 submit → 409（尚未欄位對應）。"""
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 409


async def test_submit_worksheet_not_found_returns_404(client):
    """map 完成後，submit 給不存在的 worksheet_id → 404。"""
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1},
        "time_unit": "sec",
    })
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 404


async def test_submit_viewer_returns_403(client):
    """viewer 身分無法 submit（require_role("analyst") 守門）。"""
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": "00000000-0000-0000-0000-000000000001"},
        headers={"X-Username": "ZZZUTVIEW2"},
    )
    assert r.status_code == 403
