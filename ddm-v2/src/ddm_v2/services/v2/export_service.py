"""匯出服務：WI 1128 預覽 / Excel / LB csv / LB API 接口（payload）/ 三 sheet 管理報表。

依據 system-architecture-v2 §8.1。皆由 worksheet_service.read_worksheet 的權威資料衍生。
LB API 的 request model 由 User 後續提供；此處先做 adapter 接口（先回 dry-run payload）。
"""
from __future__ import annotations

import io
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ValidationError
from ddm_v2.lb_projection.emit import CONTRACT_VERSION
from ddm_v2.lb_projection.models import ProjectionVocab
from ddm_v2.lb_projection.project import ProjectionResult, project_rows
from ddm_v2.models.v2.audit import WorkflowAuditLog
from ddm_v2.models.v2.org import Product, Site, Sku
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import MostCycle, MostWorksheet, ProcessVersion
from ddm_v2.most_engine.providers import load_rule_set_from_db
from ddm_v2.most_engine.rule_set_data import TMU_TO_SEC
from ddm_v2.services.v2.worksheet_service import WorksheetNotFound, read_worksheet


class LbExportBlocked(ValidationError):
    """LB 投影有 E 碼，擋匯出（ADR-034 D1 信封；code=LB_EXPORT_BLOCKED）。

    detail.errors[]／warnings[] 每筆帶 wi_row_id（可為 None＝跨列不變量）。
    """

    def __init__(self, errors: list, warnings: list) -> None:
        detail = {
            "code": ErrorCode.LB_EXPORT_BLOCKED.value,
            "count": len(errors),
            "errors": [{"code": e.code, "wi_row_id": e.wi_row_id, "message": e.message} for e in errors],
            "warnings": [{"code": w.code, "wi_row_id": w.wi_row_id, "message": w.message} for w in warnings],
        }
        super().__init__(f"LB 匯出被擋：{len(errors)} 個錯誤需先修正", detail=detail)


def _parse_tech(tech: str | None) -> list[dict[str, Any]]:
    """'A6 B0 G6 A10 B0 P6 A0' → [{letter:'A',value:'6'}, ...]。"""
    out: list[dict[str, Any]] = []
    for tok in (tech or "").split():
        i = 0
        while i < len(tok) and tok[i].isalpha():
            i += 1
        out.append({"letter": tok[:i], "value": tok[i:]})
    return out


async def wi_preview(session: AsyncSession, ws_id: uuid.UUID) -> dict[str, Any]:
    data = await read_worksheet(session, ws_id)
    rows = []
    for r in data["rows"]:
        cyc = r.get("cycle") or {}
        lv = r.get("level") or {}
        rows.append({
            "seq_no": r["seq_no"], "sub_activity": r.get("sub_activity") or "",
            "key_parts": r.get("key_parts") or "", "hand": r.get("hand") or "",
            "method": cyc.get("narrative") or "", "slots": _parse_tech(cyc.get("tech_line")),
            "freq": r["frequency"], "simo": bool(r["simo_group_id"]), "tmu": cyc.get("total_tmu"),
            "level": {  # Level System 關係欄（人看得懂工序限制）
                "ascription": lv.get("ascription"), "level": lv.get("level"),
                "countersignature": lv.get("countersignature"),
                "parent_countersignature": lv.get("parent_countersignature"),
                "order": lv.get("order"), "number": lv.get("number"), "number_count": lv.get("number_count"),
            },
        })
    return {"worksheet_id": str(ws_id), "status": data["status"], "rows": rows, "total_tmu": data["total_tmu"],
            # 時間投影：normal=引擎輸出；standard=normal×(1+allowance%/100)，allowance 未設＝None
            "normal_seconds": data["normal_seconds"], "allowance_percent": data["allowance_percent"],
            "standard_seconds": data["standard_seconds"]}


async def to_excel_bytes(session: AsyncSession, ws_id: uuid.UUID) -> bytes:
    """1128 式 WI 工序單 .xlsx。"""
    from openpyxl import Workbook

    prev = await wi_preview(session, ws_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "WI"
    ws.append(["MODEL", "", "ANALYST", "", "TOTAL TMU", prev["total_tmu"]])
    # 時間欄（impl-02 §3）：正常秒＝引擎輸出；標準秒＝normal×(1+allowance%/100)。
    # allowance 未設（NULL）→ 寬放%/標準秒留空，不得以 normal 假充 standard。
    ws.append(["正常秒", prev["normal_seconds"],
               "寬放%", prev["allowance_percent"] if prev["allowance_percent"] is not None else "",
               "標準秒", prev["standard_seconds"] if prev["standard_seconds"] is not None else ""])
    ws.append([])
    header = ["STEP", "SUB活動", "Key Parts", "HAND", "METHOD",
              "A", "B", "G", "A/M", "B/X", "P/I", "A", "Freq", "SIMO", "TMU",
              # ── Level System：工序關係（給 LB / 給人看）──
              "主序Level", "角色", "群組", "巢狀母組", "組內序", "不可同站nb", "nb上限"]
    ws.append(header)
    for r in prev["rows"]:
        slots = r["slots"] + [{"value": ""}] * (7 - len(r["slots"]))
        vals = [s["value"] for s in slots[:7]]
        lv = r.get("level") or {}
        cs = lv.get("countersignature") or ""
        role = "主" if (lv.get("ascription") == "main") else ("屬" if cs else "")
        ws.append([r["seq_no"], r["sub_activity"], r["key_parts"], r["hand"], r["method"],
                   *vals, r["freq"], "Y" if r["simo"] else "", r["tmu"],
                   lv.get("level") or "", role, cs, lv.get("parent_countersignature") or "",
                   lv.get("order") or "", lv.get("number") or "", lv.get("number_count") or ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _load_vocab(session: AsyncSession) -> dict[str, ProjectionVocab]:
    """vocab_id(str) → ProjectionVocab(kind, name_en)。SQLAlchemy 只在 service 層（投影層不 import）。"""
    res = await session.execute(select(WorkVocabItem))
    out: dict[str, ProjectionVocab] = {}
    for v in res.scalars().all():
        out[str(v.id)] = ProjectionVocab(kind=v.kind, name_en=v.name_en)
    return out


async def _load_rs_by_row(session: AsyncSession, ws_id: uuid.UUID) -> dict[str, Any]:
    """wi_row_id(str) → RuleSetData（逐列 most_cycles.rule_set_id → code → load_rule_set_from_db）。

    同 worksheet 多個 rule_set 版本時逐列取（reminder #2）；以 code 快取避免重複載入。
    """
    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.models.v2.worksheet import WiRow

    cycles = (
        await session.execute(
            select(MostCycle).join(WiRow, MostCycle.wi_row_id == WiRow.id).where(WiRow.worksheet_id == ws_id)
        )
    ).scalars().all()
    rs_cache: dict[str, Any] = {}
    out: dict[str, Any] = {}
    for cyc in cycles:
        code = rs_cache.get(f"__code__{cyc.rule_set_id}")
        if code is None:
            rsobj = await session.get(RuleSet, cyc.rule_set_id)
            code = rsobj.code if rsobj else None
            rs_cache[f"__code__{cyc.rule_set_id}"] = code
        if code is None:
            continue
        if code not in rs_cache:
            rs_cache[code] = await load_rule_set_from_db(session, code)
        out[str(cyc.wi_row_id)] = rs_cache[code]
    return out


async def _project(session: AsyncSession, ws_id: uuid.UUID) -> tuple[ProjectionResult, list]:
    """組裝 vocab＋rs（service 層）→ 呼叫投影層 project_rows。回 (result, proj_rows)。投影層不碰 DB。"""
    from ddm_v2.lb_projection.adapter import rows_from_worksheet

    data = await read_worksheet(session, ws_id)
    vocab = await _load_vocab(session)
    proj_rows = rows_from_worksheet(data, vocab)
    rs_by_row = await _load_rs_by_row(session, ws_id)
    slot_inputs_by_row = {
        pr.wi_row_id: pr.cycle.slot_inputs for pr in proj_rows if pr.cycle.slot_inputs
    }
    default_rs = next(iter(rs_by_row.values()), None)
    result = project_rows(proj_rows, vocab, rs=default_rs, slot_inputs_by_row=slot_inputs_by_row)
    return result, proj_rows


async def to_lb_csv(session: AsyncSession, ws_id: uuid.UUID) -> str:
    """投影層 24 欄 task CSV（ADR-035）。有 E 碼 → LbExportBlocked（擋匯出）。

    移除 machine_count／manpower 與所有 Level dump 欄（D16）：改由 project_rows 產出契約 CSV。
    """
    result, _rows = await _project(session, ws_id)
    if result.errors:
        raise LbExportBlocked(result.errors, result.warnings)
    return result.csv_text


async def lb_export_report(session: AsyncSession, ws_id: uuid.UUID, *, include_tasks: bool = False) -> dict[str, Any]:
    """匯出報告（不擋，永遠回；含 E 與 W；Spec §8.2）。走 build_report（B5）。"""
    from ddm_v2.lb_projection.report import build_report

    result, proj_rows = await _project(session, ws_id)
    report = build_report(result, proj_rows, include_tasks=include_tasks)
    report["worksheet_id"] = str(ws_id)
    return report


async def lb_preview_report(
    session: AsyncSession, ws_id: uuid.UUID, payload, *, include_tasks: bool = False
) -> dict[str, Any]:
    """未存檔預覽（dry-run，ADR-035 D10 B3）：與存檔後 lb-report 同一投影路徑、同一 builder。不寫 DB。"""
    from ddm_v2.lb_projection.adapter import rows_from_save_payload
    from ddm_v2.lb_projection.report import build_report
    from ddm_v2.services.v2.worksheet_service import compute_rows_for_save

    ws = await session.get(MostWorksheet, ws_id)
    if ws is None:
        raise WorksheetNotFound(str(ws_id))
    computed, _ctx = await compute_rows_for_save(session, ws, payload)  # 純計算，不寫 DB
    vocab = await _load_vocab(session)
    proj_rows = rows_from_save_payload(computed, vocab)
    slot_inputs_by_row = {pr.wi_row_id: pr.cycle.slot_inputs for pr in proj_rows if pr.cycle.slot_inputs}
    rs_by_row = await _load_rs_by_row(session, ws_id)
    default_rs = next(iter(rs_by_row.values()), None)
    result = project_rows(proj_rows, vocab, rs=default_rs, slot_inputs_by_row=slot_inputs_by_row)
    report = build_report(result, proj_rows, include_tasks=include_tasks)
    report["worksheet_id"] = str(ws_id)
    report["preview"] = True
    return report


async def lb_api_payload(session: AsyncSession, ws_id: uuid.UUID) -> dict[str, Any]:
    """LB API adapter：回 {contract_version, csv, tasks, report}（不再直送 build_output；保守邊不可沿用）。"""
    from ddm_v2.lb_projection.emit import to_row

    result, _rows = await _project(session, ws_id)
    if result.errors:
        raise LbExportBlocked(result.errors, result.warnings)
    report = await lb_export_report(session, ws_id)
    return {
        "status": "interface-ready",
        "contract_version": CONTRACT_VERSION,
        "csv": result.csv_text,
        "tasks": [to_row(t) for t in result.tasks],  # 24 欄 dict（順序＝COLUMNS）
        "report": report,
    }


_STATUS_ZH = {"draft": "草稿", "approved": "已核准", "retired": "已退役"}


async def to_report_xlsx_bytes(session: AsyncSession, ws_id: uuid.UUID) -> bytes:
    """三 sheet 管理報表：案件資訊 / 動作明細 / 簽核歷程。"""
    from openpyxl import Workbook

    ws_model = await session.get(MostWorksheet, ws_id)
    if ws_model is None:
        raise WorksheetNotFound(str(ws_id))

    pv = await session.get(ProcessVersion, ws_model.process_version_id)
    sku = await session.get(Sku, pv.sku_id)
    product = await session.get(Product, sku.product_id)
    site = await session.get(Site, product.site_id)

    # 計算彙總；allowance_percent 為百分比值（e.g. 15.0 代表 15%），None = 未設定。
    # allowance 未設定時標準秒留空，不得以 normal 假充 standard。
    data = await read_worksheet(session, ws_id)
    total_tmu = data["total_tmu"] or 0.0
    wi_row_count = len(data["rows"])
    total_normal_sec = round(total_tmu * TMU_TO_SEC, 3)
    allowance_percent: float | None = data.get("allowance_percent")  # None or float %
    total_standard_sec: float | None = (
        round(total_normal_sec * (1 + allowance_percent / 100), 3)
        if allowance_percent is not None
        else None
    )

    process_name = sku.name_zh or sku.sku_code

    wb = Workbook()

    # ── Sheet 1：案件資訊（垂直 key-value）──
    ws1 = wb.active
    ws1.title = "案件資訊"
    rows_info = [
        ("廠區", site.name_zh),
        ("產品", product.name_zh),
        ("機種", sku.name_zh or sku.sku_code),
        ("製程", process_name),
        ("版本號", pv.version_no),
        ("狀態", _STATUS_ZH.get(pv.status, pv.status)),
        ("步驟總數", wi_row_count),
        ("總 TMU", round(total_tmu, 2)),
        ("總正常秒", total_normal_sec),
        ("寬放率", allowance_percent if allowance_percent is not None else ""),
        ("總標準秒", total_standard_sec if total_standard_sec is not None else ""),
        ("核准時間", pv.published_at.strftime("%Y-%m-%d %H:%M:%S") if pv.published_at else ""),
    ]
    for key, val in rows_info:
        ws1.append([key, val])

    # ── Sheet 2：動作明細──
    ws2 = wb.create_sheet("動作明細")
    ws2.append(["序號", "說明", "序列模型", "頻率", "插槽明細", "步驟TMU", "正常秒(4位)", "標準秒(4位)", "SIMO組"])
    for r in data["rows"]:
        cyc = r.get("cycle") or {}
        slot_inputs: dict[str, Any] = cyc.get("slot_inputs") or {}
        # 展開 slot_inputs：把各 key 的 value dict 中各欄的 key=value 連接
        slot_parts: list[str] = []
        for slot_key, slot_val in slot_inputs.items():
            if isinstance(slot_val, dict):
                for k, v in slot_val.items():
                    if k != "manual_override" and v not in (None, 0, "", [], {}):
                        slot_parts.append(f"{slot_key}({k})={v}")
            else:
                if slot_val not in (None, 0, "", [], {}):
                    slot_parts.append(f"{slot_key}={slot_val}")
        slot_detail = " | ".join(slot_parts) if slot_parts else ""

        step_tmu = float(cyc.get("total_tmu") or 0)
        freq = float(r.get("frequency") or 1)
        normal_sec = round(step_tmu * TMU_TO_SEC, 4)
        standard_sec: float | None = (
            round(normal_sec * (1 + allowance_percent / 100), 4)
            if allowance_percent is not None
            else None
        )

        simo_gid = r.get("simo_group_id") or ""
        simo_display = str(simo_gid)[:8] if simo_gid else ""

        ws2.append([
            r["seq_no"],
            r.get("sub_activity") or "",
            cyc.get("seq_kind") or "",
            freq,
            slot_detail,
            step_tmu,
            normal_sec,
            standard_sec if standard_sec is not None else "",
            simo_display,
        ])

    # ── Sheet 3：簽核歷程──
    ws3 = wb.create_sheet("簽核歷程")
    ws3.append(["時間", "動作", "從狀態", "至狀態", "執行者", "備註"])
    audit_rows = (
        await session.execute(
            select(WorkflowAuditLog)
            .where(
                WorkflowAuditLog.entity_type == "process_version",
                WorkflowAuditLog.entity_id == pv.id,
            )
            .order_by(WorkflowAuditLog.created_at.asc())
        )
    ).scalars().all()
    for entry in audit_rows:
        ws3.append([
            entry.created_at.strftime("%Y-%m-%d %H:%M:%S") if entry.created_at else "",
            entry.action,
            _STATUS_ZH.get(entry.from_status or "", entry.from_status or ""),
            _STATUS_ZH.get(entry.to_status or "", entry.to_status or ""),
            entry.actor,
            entry.comment or "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
