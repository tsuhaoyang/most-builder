"""匯出整合測試：wi-preview / excel / lb-csv / lb-api。

特別守住「openpyxl 等 runtime 依賴漏宣告」這類回歸——excel 端點會載 openpyxl，
依賴缺失時會 500。需 demo worksheet（dev_seed_v2 的 5555…）；未種則 skip。
"""
from __future__ import annotations

import io
import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"


def _gm_row():
    return {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": 1, "narrative": "export allowance",
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}}


def _gm_row_en():
    """投影可用的乾淨 GM 列：帶 narrative_en、level=1、action_type 標籤（ruling B）。"""
    return {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": 1, "narrative": "拿取並放置",
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"},
                      "narrative_en": "take and place part"},
            "level": {"ascription": "main", "level": "1", "action_type": "place"}}


async def _seeded(client) -> bool:
    r = await client.get(f"/api/v2/worksheets/{WS}/export/wi-preview")
    return r.status_code == 200


async def test_wi_preview(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r = await client.get(f"/api/v2/worksheets/{WS}/export/wi-preview")
    assert r.status_code == 200
    assert "total_tmu" in r.json()


async def test_export_excel(client):
    """守 openpyxl：缺依賴會 500。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    r = await client.get(f"/api/v2/worksheets/{WS}/export/excel")
    assert r.status_code == 200, f"excel 匯出失敗（檢查 openpyxl 是否在 runtime 依賴）：{r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "octet-stream" in ct, ct


async def test_export_excel_normal_standard_seconds(client):
    """impl-02 §3：Excel 增正常秒/標準秒欄；allowance=10 → 標準秒 = 正常秒 × 1.1。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    from openpyxl import load_workbook

    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()], "allowance_percent": 10})
    assert r.status_code == 200, r.text
    xls = await client.get(f"/api/v2/worksheets/{new}/export/excel")
    assert xls.status_code == 200
    sheet = load_workbook(io.BytesIO(xls.content)).active
    meta = {}  # 第 2 列：label-value 對（正常秒/寬放%/標準秒）
    row2 = [c.value for c in sheet[2]]
    for i in range(0, len(row2) - 1, 2):
        meta[row2[i]] = row2[i + 1]
    assert meta.get("正常秒") and meta["正常秒"] > 0
    assert meta.get("寬放%") == 10
    assert meta.get("標準秒") == pytest.approx(meta["正常秒"] * 1.1, abs=1e-4)


async def test_export_excel_no_allowance_standard_blank(client):
    """allowance 未設 → 標準秒留空（不得以 normal 假充 standard）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    from openpyxl import load_workbook

    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()], "allowance_percent": None})
    assert r.status_code == 200, r.text
    xls = await client.get(f"/api/v2/worksheets/{new}/export/excel")
    sheet = load_workbook(io.BytesIO(xls.content)).active
    row2 = [c.value for c in sheet[2]]
    meta = {row2[i]: row2[i + 1] for i in range(0, len(row2) - 1, 2)}
    assert meta.get("正常秒") and meta["正常秒"] > 0
    assert meta.get("寬放%") in (None, "")
    assert meta.get("標準秒") in (None, "")


async def test_export_lb_csv(client):
    """ADR-035 WP8：lb-csv 改為投影層 24 欄契約。用 clone 隔離；demo 5555 可能含 level 離散跳號等。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row_en()]})
    assert r.status_code == 200, r.text
    csv_r = await client.get(f"/api/v2/worksheets/{new}/export/lb-csv")
    assert csv_r.status_code == 200, csv_r.text
    header = csv_r.text.splitlines()[0].strip().lstrip("﻿")  # UTF-8 BOM
    from ddm_v2.lb_projection.emit import COLUMNS

    assert header == ",".join(COLUMNS), f"lb-csv 表頭非投影 24 欄契約：{header}"
    # 移除 machine_count／manpower（D16）
    assert "machine_count" not in header and "manpower" not in header


async def test_export_lb_csv_blocked_422(client):
    """有 E 碼 → 422 且 error.code == LB_EXPORT_BLOCKED 且 detail.errors[0].wi_row_id 存在（ADR-034 信封）。

    註：缺 narrative_en 在 API 路徑不可達（save 一律以 build_narrative_en 合成英文，D14），
    故以可經 save 觸發的 E_LEVEL_DISCRETE_UNSUPPORTED（level='1/3'）驗同一條 422 信封契約。
    """
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    row = _gm_row_en()
    row["level"] = {"ascription": "main", "level": "1/3", "action_type": "place"}  # 離散跳號 → E 碼
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row]})
    assert r.status_code == 200, r.text
    csv_r = await client.get(f"/api/v2/worksheets/{new}/export/lb-csv")
    assert csv_r.status_code == 422, csv_r.text
    body = csv_r.json()
    assert body["error"]["code"] == "LB_EXPORT_BLOCKED"
    errs = body["error"]["detail"]["errors"]
    assert len(errs) >= 1
    assert "wi_row_id" in errs[0]  # 每筆帶 wi_row_id 欄（跨列不變量可為 None）


async def test_export_lb_csv_narrative_null_blocked_422(client, db_session):
    """舊資料／匯入列 narrative_en=NULL（ADR-032 fill-then-fix；backfill_narrative_en.py 的對象）→
    422、detail.errors[].code == E_NARRATIVE_EN_MISSING、帶 wi_row_id；lb-report 回同一筆。

    save 一律合成 narrative_en，故以 raw UPDATE 模擬 NULL 真實狀態（db_session 與 client 同 connection/savepoint）。
    """
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    from sqlalchemy import text as _sql

    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    row = _gm_row_en()
    wi_row_id = row["id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row]})
    assert r.status_code == 200, r.text
    # 模擬舊資料：把 narrative_en 清成 NULL
    await db_session.execute(
        _sql("UPDATE most_cycles SET narrative_en = NULL WHERE wi_row_id = :rid"), {"rid": wi_row_id}
    )
    await db_session.commit()

    csv_r = await client.get(f"/api/v2/worksheets/{new}/export/lb-csv")
    assert csv_r.status_code == 422, csv_r.text
    body = csv_r.json()
    assert body["error"]["code"] == "LB_EXPORT_BLOCKED"
    errs = body["error"]["detail"]["errors"]
    hit = [e for e in errs if e["code"] == "E_NARRATIVE_EN_MISSING"]
    assert hit, f"expected E_NARRATIVE_EN_MISSING, got {[e['code'] for e in errs]}"
    assert hit[0]["wi_row_id"] == wi_row_id

    # lb-report 回同一筆
    rep = await client.get(f"/api/v2/worksheets/{new}/export/lb-report")
    assert rep.status_code == 200
    rep_errs = rep.json()["errors"]
    assert any(e["code"] == "E_NARRATIVE_EN_MISSING" and e["wi_row_id"] == wi_row_id for e in rep_errs)


async def test_export_lb_report_200_with_warnings(client):
    """lb-report 永遠 200（不擋），回 tasks_out/groups/atomic/errors/warnings（Spec §8.2）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row_en()]})
    assert r.status_code == 200, r.text
    rep = await client.get(f"/api/v2/worksheets/{new}/export/lb-report")
    assert rep.status_code == 200, rep.text
    body = rep.json()
    assert "tasks_out" in body and "groups" in body and "atomic_groups" in body
    assert "errors" in body and "warnings" in body
    assert body["contract_version"] == "most-lb-csv-v1.1"


async def test_export_lb_api_payload_shape(client):
    """lb-api：回 {contract_version, csv, tasks, report}，不再直送 build_output。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row_en()]})
    assert r.status_code == 200, r.text
    api = await client.post(f"/api/v2/worksheets/{new}/export/lb-api")
    assert api.status_code == 200, api.text
    body = api.json()
    assert set(["contract_version", "csv", "tasks", "report"]).issubset(body.keys())
    assert "payload" not in body  # build_output 不再直送


async def test_export_report_xlsx_happy_path(client):
    """三 sheet 報表：200、content-type=xlsx、Content-Disposition 含 MOST_Report。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    r = await client.get(f"/api/v2/worksheets/{WS}/export/report.xlsx")
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "octet-stream" in ct, ct
    cd = r.headers.get("content-disposition", "")
    assert "MOST_Report" in cd, cd


async def test_export_report_xlsx_sheets_structure(client):
    """三 sheet 各自存在，Sheet1 含「廠區」row，Sheet2 含欄位標頭，Sheet3 含簽核欄位。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    from openpyxl import load_workbook

    r = await client.get(f"/api/v2/worksheets/{WS}/export/report.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    # Sheet 1：案件資訊
    assert "案件資訊" in wb.sheetnames
    ws1 = wb["案件資訊"]
    keys = [ws1.cell(row=i, column=1).value for i in range(1, ws1.max_row + 1)]
    assert "廠區" in keys
    assert "總 TMU" in keys
    assert "總標準秒" in keys
    # Sheet 2：動作明細
    assert "動作明細" in wb.sheetnames
    ws2 = wb["動作明細"]
    header2 = [ws2.cell(row=1, column=c).value for c in range(1, 10)]
    assert "序號" in header2
    assert "步驟TMU" in header2
    # Sheet 3：簽核歷程
    assert "簽核歷程" in wb.sheetnames
    ws3 = wb["簽核歷程"]
    header3 = [ws3.cell(row=1, column=c).value for c in range(1, 7)]
    assert "時間" in header3
    assert "執行者" in header3


async def test_export_report_xlsx_not_found(client):
    """不存在的 worksheet_id → 404。"""
    fake_id = uuid.uuid4()
    r = await client.get(f"/api/v2/worksheets/{fake_id}/export/report.xlsx")
    assert r.status_code == 404
