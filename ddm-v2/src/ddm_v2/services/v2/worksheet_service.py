"""worksheet 持久化服務：存/讀整份 WI（wi_row + most_cycle + level_entry）。

存的設計（data-model §1.5 / §2.9）：
- slot_inputs(JSONB) = 前端送的原始 CycleIn（權威真相）。
- total_tmu/total_seconds/seq_kind 升欄；computed/narrative 為可重生快取。
- rule_set_id 快照（可回放）。vocab 走 wi_row FK。
- 存採「整份取代」：刪舊 wi_rows（cascade 連帶 cycle/level）再以前端穩定 id 重建。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import LevelEntry, MostCycle, MostWorksheet, ProcessVersion, WiRow
from ddm_v2.most_engine import compute_cycle, load_rule_set_from_db
from ddm_v2.most_engine.narrative import HAND_NAMES, build_narrative
from ddm_v2.most_engine.providers import load_options_from_db
from ddm_v2.schemas.v2.most import cycle_in_to_engine
from ddm_v2.schemas.v2.worksheet import WorksheetSaveIn


class WorksheetNotFound(Exception):
    pass


class RuleSetNotFound(Exception):
    pass


class NotEditable(Exception):
    pass


async def save_worksheet(session: AsyncSession, worksheet_id: uuid.UUID, payload: WorksheetSaveIn) -> dict[str, Any]:
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv is not None and pv.status != "draft":
        raise NotEditable(f"版本狀態為 {pv.status}，已凍結不可存（請另存新檔）")

    code = payload.rows[0].cycle.rule_set_code if payload.rows else "MINIMOST_FACTORY_V1"
    rs_row = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs_row is None:
        raise RuleSetNotFound(code)
    rsdata = await load_rule_set_from_db(session, code)
    rsdata.validate_complete()  # 完整性 gating

    # 後端敘事（FE-2）：rule-set 標籤 + vocab 名 → METHOD 句（單一權威）
    opts = await load_options_from_db(session, code)
    labels = {"g": {o["code"]: o["label"] for o in opts["g"]},
              "p_base": {o["code"]: o["label"] for o in opts["p_bases"]},
              "m_verb": {o["code"]: o["label"] for o in opts["m_verbs"]}}
    vids = {vid for r in payload.rows for vid in (r.object_vocab_id, r.from_vocab_id, r.to_vocab_id) if vid}
    vname: dict[uuid.UUID, str] = {}
    if vids:
        for v in (await session.execute(select(WorkVocabItem).where(WorkVocabItem.id.in_(vids)))).scalars().all():
            vname[v.id] = v.name_zh

    # 整份取代（cascade 連帶刪 cycle/level）
    await session.execute(delete(WiRow).where(WiRow.worksheet_id == worksheet_id))
    await session.flush()

    now = datetime.now(timezone.utc)
    for r in payload.rows:
        engine_cycle = cycle_in_to_engine(r.cycle)
        result = compute_cycle(engine_cycle, rsdata)
        voc = {"object": vname.get(r.object_vocab_id, ""),
               "from": vname.get(r.from_vocab_id, "") if r.from_vocab_id else "",
               "to": vname.get(r.to_vocab_id, "") if r.to_vocab_id else "",
               "hand": HAND_NAMES.get(r.hand or "", "")}
        narrative = build_narrative(r.cycle.model_dump(mode="json"), labels, voc)
        session.add(WiRow(
            id=r.id, worksheet_id=worksheet_id, seq_no=r.seq_no,
            sub_activity=r.sub_activity, key_parts=r.key_parts, hand=r.hand,
            object_vocab_id=r.object_vocab_id, from_vocab_id=r.from_vocab_id,
            to_vocab_id=r.to_vocab_id, tool_vocab_id=r.tool_vocab_id,
            frequency=r.frequency, simo_group_id=r.simo_group_id, provenance="manual",
        ))
        session.add(MostCycle(
            id=uuid.uuid4(), wi_row_id=r.id, seq_kind=result.seq, rule_set_id=rs_row.id,
            slot_inputs=r.cycle.model_dump(mode="json"),  # 權威原始輸入
            computed={"breakdown": [{"letter": L, "tmu": t} for L, t in zip(result.letters, result.slot_tmus)],
                      "tech_line": result.tech_line},
            narrative_zh=narrative,
            total_tmu=result.total_tmu, total_seconds=result.total_seconds, computed_at=now,
        ))
        lv = r.level
        session.add(LevelEntry(
            id=uuid.uuid4(), wi_row_id=r.id, worksheet_id=worksheet_id,
            raw_seconds=result.total_seconds, coefficient=lv.coefficient,
            ascription=lv.ascription, level=lv.level, countersignature=lv.countersignature,
            parent_countersignature=lv.parent_countersignature,
            order_in_group=lv.order, number=lv.number, number_count=lv.number_count,
            machine_count=lv.machine_count, manpower=lv.manpower,
        ))
    await session.flush()
    return await read_worksheet(session, worksheet_id)


async def read_worksheet(session: AsyncSession, worksheet_id: uuid.UUID) -> dict[str, Any]:
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    wrs = (await session.execute(select(WiRow).where(WiRow.worksheet_id == worksheet_id).order_by(WiRow.seq_no))).scalars().all()
    rows: list[dict[str, Any]] = []
    total = 0.0
    for wr in wrs:
        cyc = (await session.execute(select(MostCycle).where(MostCycle.wi_row_id == wr.id))).scalar_one_or_none()
        lv = (await session.execute(select(LevelEntry).where(LevelEntry.wi_row_id == wr.id))).scalar_one_or_none()
        eff = float(cyc.total_tmu or 0) * float(wr.frequency or 1) if cyc else 0.0
        if not wr.simo_group_id:
            total += eff
        rows.append({
            "wi_row_id": str(wr.id), "seq_no": wr.seq_no, "hand": wr.hand,
            "sub_activity": wr.sub_activity, "key_parts": wr.key_parts,
            "object_vocab_id": str(wr.object_vocab_id),
            "from_vocab_id": str(wr.from_vocab_id) if wr.from_vocab_id else None,
            "to_vocab_id": str(wr.to_vocab_id) if wr.to_vocab_id else None,
            "tool_vocab_id": str(wr.tool_vocab_id) if wr.tool_vocab_id else None,
            "frequency": float(wr.frequency),
            "simo_group_id": wr.simo_group_id,
            "cycle": {"seq_kind": cyc.seq_kind, "total_tmu": float(cyc.total_tmu), "total_seconds": float(cyc.total_seconds),
                      "tech_line": (cyc.computed or {}).get("tech_line"), "narrative": cyc.narrative_zh,
                      "rule_set_id": str(cyc.rule_set_id), "slot_inputs": cyc.slot_inputs} if cyc else None,
            "level": {"second": float(lv.second), "coefficient": float(lv.coefficient),
                      "ascription": lv.ascription, "level": lv.level, "countersignature": lv.countersignature,
                      "parent_countersignature": lv.parent_countersignature,
                      "order": lv.order_in_group, "number": lv.number, "number_count": lv.number_count,
                      "machine_count": lv.machine_count, "manpower": lv.manpower} if lv else None,
        })
    return {"worksheet_id": worksheet_id, "status": ws.status, "rows": rows, "total_tmu": total}


async def _version_info(session: AsyncSession, worksheet_id: uuid.UUID) -> dict[str, Any]:
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    pv = await session.get(ProcessVersion, ws.process_version_id)
    # 同 SKU 的所有版本 + 各自的 worksheet id
    pvs = (await session.execute(select(ProcessVersion).where(ProcessVersion.sku_id == pv.sku_id).order_by(ProcessVersion.created_at))).scalars().all()
    siblings = []
    for v in pvs:
        w = (await session.execute(select(MostWorksheet).where(MostWorksheet.process_version_id == v.id))).scalar_one_or_none()
        siblings.append({"version_no": v.version_no, "status": v.status,
                         "worksheet_id": str(w.id) if w else None, "is_current": v.id == pv.id})
    return {"worksheet_id": str(worksheet_id), "version_no": pv.version_no, "status": pv.status,
            "sku_id": str(pv.sku_id), "versions": siblings}


async def publish_worksheet(session: AsyncSession, worksheet_id: uuid.UUID, actor: str | None = None) -> dict[str, Any]:
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv.status != "draft":
        raise NotEditable(f"版本狀態為 {pv.status}，無法發布")
    pv.status = "published"
    pv.published_at = datetime.now(timezone.utc)
    pv.published_by = actor
    ws.status = "published"
    await session.flush()
    return await _version_info(session, worksheet_id)


async def clone_worksheet(session: AsyncSession, worksheet_id: uuid.UUID, actor: str | None = None) -> dict[str, Any]:
    """另存新檔：深拷貝 version+worksheet+rows+cycles+level → 新 draft 版本。"""
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    pv = await session.get(ProcessVersion, ws.process_version_id)
    count = len((await session.execute(select(ProcessVersion).where(ProcessVersion.sku_id == pv.sku_id))).scalars().all())

    new_pv = ProcessVersion(id=uuid.uuid4(), sku_id=pv.sku_id, version_no=f"v{count + 1}",
                            status="draft", source_version_id=pv.id, created_by=actor)
    new_ws = MostWorksheet(id=uuid.uuid4(), process_version_id=new_pv.id, model_label=ws.model_label,
                           analyst=ws.analyst, study_date=ws.study_date, default_rule_set_id=ws.default_rule_set_id, status="draft")
    session.add(new_pv)
    session.add(new_ws)
    await session.flush()

    wrs = (await session.execute(select(WiRow).where(WiRow.worksheet_id == worksheet_id).order_by(WiRow.seq_no))).scalars().all()
    for wr in wrs:
        new_row_id = uuid.uuid4()
        session.add(WiRow(id=new_row_id, worksheet_id=new_ws.id, seq_no=wr.seq_no,
                          sub_activity=wr.sub_activity, key_parts=wr.key_parts, hand=wr.hand,
                          object_vocab_id=wr.object_vocab_id, from_vocab_id=wr.from_vocab_id,
                          to_vocab_id=wr.to_vocab_id, tool_vocab_id=wr.tool_vocab_id,
                          frequency=wr.frequency, simo_group_id=wr.simo_group_id,
                          provenance=wr.provenance, source_row_id=wr.id))
        cyc = (await session.execute(select(MostCycle).where(MostCycle.wi_row_id == wr.id))).scalar_one_or_none()
        if cyc:
            session.add(MostCycle(id=uuid.uuid4(), wi_row_id=new_row_id, seq_kind=cyc.seq_kind,
                                  rule_set_id=cyc.rule_set_id, slot_inputs=cyc.slot_inputs, computed=cyc.computed,
                                  narrative_zh=cyc.narrative_zh, total_tmu=cyc.total_tmu,
                                  total_seconds=cyc.total_seconds, computed_at=cyc.computed_at))
        lv = (await session.execute(select(LevelEntry).where(LevelEntry.wi_row_id == wr.id))).scalar_one_or_none()
        if lv:
            session.add(LevelEntry(id=uuid.uuid4(), wi_row_id=new_row_id, worksheet_id=new_ws.id,
                                   raw_seconds=lv.raw_seconds, coefficient=lv.coefficient, ascription=lv.ascription,
                                   level=lv.level, countersignature=lv.countersignature,
                                   parent_countersignature=lv.parent_countersignature, order_in_group=lv.order_in_group,
                                   number=lv.number, number_count=lv.number_count,
                                   machine_count=lv.machine_count, manpower=lv.manpower))
    await session.flush()
    return {"new_worksheet_id": str(new_ws.id), "version_no": new_pv.version_no, "status": "draft", "source_version_no": pv.version_no}


async def list_versions(session: AsyncSession, worksheet_id: uuid.UUID) -> dict[str, Any]:
    return await _version_info(session, worksheet_id)
