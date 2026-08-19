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

from ddm_v2.models.v2.policy import LevelPolicyVersion, ModelingPolicyVersion
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import LevelEntry, MostCycle, MostWorksheet, ProcessVersion, WiRow
from ddm_v2.most_engine import compute_cycle, load_rule_set_from_db
from ddm_v2.most_engine.narrative import HAND_NAMES, build_narrative
from ddm_v2.most_engine.narrative_en import build_narrative_en
from ddm_v2.most_engine.providers import build_label_map, load_options_from_db
from ddm_v2.most_engine.rule_set_data import TMU_TO_SEC
from ddm_v2.schemas.v2.most import cycle_in_to_engine, resolve_cycle_rule_set
from ddm_v2.schemas.v2.worksheet import WorksheetSaveIn
from ddm_v2.services.v2.audit_service import log_audit
from ddm_v2.services.v2.level_validation_service import assert_publishable, validate_and_persist
from ddm_v2.services.v2.outbox_service import enqueue_worksheet_saved
from ddm_v2.services.v2.policy_service import level_summary, modeling_summary
from ddm_v2.services.v2.rule_set_service import get_active_rule_set_code
from ddm_v2.services.v2.worksheet_revision import (
    bump_worksheet_revision,
    content_hash_from_read,
    set_content_hash,
)


class WorksheetNotFound(Exception):
    pass


class RuleSetNotFound(Exception):
    pass


class NotEditable(Exception):
    pass


class SimoPairInvalid(Exception):
    pass


async def save_worksheet(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    payload: WorksheetSaveIn,
    *,
    edited_by: str | None = None,
) -> dict[str, Any]:
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv is not None and pv.status != "draft":
        raise NotEditable(f"版本狀態為 {pv.status}，已凍結不可存（請另存新檔）")

    # R1：任何內容 mutation 前先 CAS revision（失敗則不刪 rows）。
    # bump 走 raw SQL，但它會把 `ws` 這一顆（且只有這一顆）同步回 DB 真值，
    # 所以下面直接沿用 `ws` 就是 bump 後的狀態，不需要再 get 一次。
    await bump_worksheet_revision(
        session,
        worksheet_id=worksheet_id,
        base_revision=payload.base_revision,
        edited_by=edited_by,
    )

    # 工序表級寬放%（data-model §2.5）：payload 有帶才更新（加法相容）；帶 null＝清除。
    if "allowance_percent" in payload.model_fields_set:
        ws.allowance_percent = payload.allowance_percent

    # ADR-023 §3.5：規則版本以 payload 的 cycle 為準；未指定（空 rows 或 client 未帶）→ 目前 active。
    code = (payload.rows[0].cycle.rule_set_code if payload.rows else None) or await get_active_rule_set_code(session)
    rs_row = (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()
    if rs_row is None:
        raise RuleSetNotFound(code)
    rsdata = await load_rule_set_from_db(session, code)
    rsdata.validate_complete()  # 完整性 gating

    # 後端敘事（FE-2/E6）：rule-set 標籤/句字/display_rule + vocab 名 → METHOD 句（單一權威）
    opts = await load_options_from_db(session, code)

    labels = build_label_map(opts)

    # E5（ADR-020）：SIMO 正規化 — simo_group_id＝SIMO 標記（該列貢獻 0，時間由主列吸收）。
    # 配對輸入 simo_with_row_id：僅「宣告配對的從屬列」被標記，被指向的主列不標記；
    # 同一配對鏈的從屬列共用一個 gid（附配對資訊）。顯式 simo_group_id 輸入＝已標記，原值保留。
    row_ids = {r.id for r in payload.rows}
    parent: dict[Any, Any] = {}

    def _find(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    dependents: list[Any] = []  # 宣告配對的從屬列（僅這些列被標記）
    pair_targets: set[Any] = set()  # 被指為配對目標的主列
    for r in payload.rows:
        pid = getattr(r, "simo_with_row_id", None)
        if pid is None:
            continue
        if pid == r.id or pid not in row_ids:
            raise SimoPairInvalid(f"列 {r.id} 的 SIMO 配對無效：{pid}")
        dependents.append(r.id)
        pair_targets.add(pid)
        _union(r.id, pid)
    # ADR-020 寫入守門：被指為配對目標（主列）的列不得自身宣告配對——
    # 否則互指/鏈式配對會讓整組都被標記 → 全部貢獻 0（靜默歸零）。
    mutual = pair_targets & set(dependents)
    if mutual:
        raise SimoPairInvalid(
            f"SIMO 配對無效：列 {sorted(str(x) for x in mutual)} 被指為主列、卻又自身宣告配對（主列不得標記）")
    simo_group_of: dict[Any, str] = {}
    if dependents:
        roots: dict[Any, list] = {}
        for rid in dependents:
            roots.setdefault(_find(rid), []).append(rid)
        for n, (_root, members) in enumerate(sorted(roots.items(), key=lambda kv: str(kv[0])), start=1):
            gid = f"SIMO-{n}"
            for m in members:
                simo_group_of[m] = gid
    vids = {vid for r in payload.rows for vid in (r.object_vocab_id, r.from_vocab_id, r.to_vocab_id) if vid}
    vname: dict[uuid.UUID, str] = {}
    vname_en: dict[uuid.UUID, str] = {}
    if vids:
        for v in (await session.execute(select(WorkVocabItem).where(WorkVocabItem.id.in_(vids)))).scalars().all():
            vname[v.id] = v.name_zh
            vname_en[v.id] = v.name_en or v.name_zh  # 未翻譯的詞彙回退中文，不留空受詞

    # 整份取代（cascade 連帶刪 cycle/level）
    await session.execute(delete(WiRow).where(WiRow.worksheet_id == worksheet_id))
    await session.flush()

    now = datetime.now(timezone.utc)
    for r in payload.rows:
        # slot_inputs 是回放的權威原始輸入 → 必須自帶解析後的規則版本，不可留 None（ADR-023 §3.4）
        resolve_cycle_rule_set(r.cycle, code)
        engine_cycle = cycle_in_to_engine(r.cycle)
        result = compute_cycle(engine_cycle, rsdata)
        voc = {"object": vname.get(r.object_vocab_id, ""),
               "from": vname.get(r.from_vocab_id, "") if r.from_vocab_id else "",
               "to": vname.get(r.to_vocab_id, "") if r.to_vocab_id else "",
               "hand": HAND_NAMES.get(r.hand or "", "")}
        # 英文 vocab 與中文分開組：hand 給的是**原始代碼**（narrative_en 以 "RH:" 當
        # 祈使句前綴），不是 HAND_NAMES 轉出來的顯示字串。
        voc_en = {"object": vname_en.get(r.object_vocab_id, ""),
                  "from": vname_en.get(r.from_vocab_id, "") if r.from_vocab_id else "",
                  "to": vname_en.get(r.to_vocab_id, "") if r.to_vocab_id else "",
                  "hand": r.hand or ""}
        cycle_json = r.cycle.model_dump(mode="json")
        narrative = build_narrative(cycle_json, labels, voc)
        narrative_en = build_narrative_en(cycle_json, labels, voc_en)
        session.add(WiRow(
            id=r.id, worksheet_id=worksheet_id, seq_no=r.seq_no,
            sub_activity=r.sub_activity, key_parts=r.key_parts, hand=r.hand,
            object_vocab_id=r.object_vocab_id, from_vocab_id=r.from_vocab_id,
            to_vocab_id=r.to_vocab_id, tool_vocab_id=r.tool_vocab_id,
            frequency=r.frequency, simo_group_id=simo_group_of.get(r.id, r.simo_group_id), provenance="manual",
        ))
        session.add(MostCycle(
            id=uuid.uuid4(), wi_row_id=r.id, seq_kind=result.seq, rule_set_id=rs_row.id,
            slot_inputs=r.cycle.model_dump(mode="json"),  # 權威原始輸入
            computed={"breakdown": [{"letter": L, "tmu": t} for L, t in zip(result.letters, result.slot_tmus)],
                      "tech_line": result.tech_line},
            narrative_zh=narrative, narrative_en=narrative_en,
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
    out = await read_worksheet(session, worksheet_id)
    ch = content_hash_from_read(out)
    await set_content_hash(session, worksheet_id=worksheet_id, content_hash=ch)
    await session.flush()
    out["content_hash"] = ch
    # R2b：save 後 append validation run（含 invalid）；不阻擋存檔
    if ws.level_policy_version_id is not None:
        await validate_and_persist(
            session, worksheet_id, trigger="save", actor=edited_by or "unknown"
        )
    # R3b：同交易寫 outbox（reference only）
    await enqueue_worksheet_saved(
        session,
        worksheet_id=worksheet_id,
        revision_no=int(ws.revision_no or 1),
        content_hash=ch,
        edited_by=edited_by,
    )
    return out


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
        if not wr.simo_group_id:  # ADR-020：SIMO 標記列貢獻 0（時間由未標記主列吸收）
            total += eff
        rows.append({
            "wi_row_id": str(wr.id), "seq_no": wr.seq_no, "hand": wr.hand,
            "sub_activity": wr.sub_activity, "key_parts": wr.key_parts,
            "object_vocab_id": str(wr.object_vocab_id) if wr.object_vocab_id else None,
            "from_vocab_id": str(wr.from_vocab_id) if wr.from_vocab_id else None,
            "to_vocab_id": str(wr.to_vocab_id) if wr.to_vocab_id else None,
            "tool_vocab_id": str(wr.tool_vocab_id) if wr.tool_vocab_id else None,
            "frequency": float(wr.frequency),
            "simo_group_id": wr.simo_group_id,
            # F-03b §2 provenance（軟參考，非 FK）
            "source_module_id": str(wr.source_module_id) if wr.source_module_id else None,
            "source_module_version": wr.source_module_version,
            "cycle": {"seq_kind": cyc.seq_kind, "total_tmu": float(cyc.total_tmu), "total_seconds": float(cyc.total_seconds),
                      "tech_line": (cyc.computed or {}).get("tech_line"), "narrative": cyc.narrative_zh,
                      # 回應語言中立（ADR-032 D3.3）：兩語並列，由前端依 locale 挑欄
                      "narrative_en": cyc.narrative_en,
                      "rule_set_id": str(cyc.rule_set_id), "slot_inputs": cyc.slot_inputs} if cyc else None,
            "level": {"second": float(lv.second), "coefficient": float(lv.coefficient),
                      "ascription": lv.ascription, "level": lv.level, "countersignature": lv.countersignature,
                      "parent_countersignature": lv.parent_countersignature,
                      "order": lv.order_in_group, "number": lv.number, "number_count": lv.number_count,
                      "machine_count": lv.machine_count, "manpower": lv.manpower} if lv else None,
        })
    total = round(total, 3)
    normal_seconds = round(total * TMU_TO_SEC, 4)
    allowance = float(ws.allowance_percent) if ws.allowance_percent is not None else None
    standard_seconds = round(normal_seconds * (1 + allowance / 100), 4) if allowance is not None else None
    # ADR-023 §3.4-4：帶 default_rule_set 現況狀態供警示徽章（純顯示，不進計算路徑）。
    # 單筆 lookup（非每列）→ 不構成 N+1；default_rule_set_id 可為 NULL → 回 None。
    default_rule_set: dict[str, Any] | None = None
    if ws.default_rule_set_id is not None:
        drs = await session.get(RuleSet, ws.default_rule_set_id)
        if drs is not None:
            default_rule_set = {"code": drs.code, "status": drs.status, "is_active": drs.is_active}
    modeling_policy = None
    if ws.modeling_policy_version_id is not None:
        mp = await session.get(ModelingPolicyVersion, ws.modeling_policy_version_id)
        modeling_policy = modeling_summary(mp)
    level_policy = None
    if ws.level_policy_version_id is not None:
        lp = await session.get(LevelPolicyVersion, ws.level_policy_version_id)
        level_policy = level_summary(lp)
    return {"worksheet_id": worksheet_id, "status": ws.status, "rows": rows, "total_tmu": total,
            "normal_seconds": normal_seconds, "allowance_percent": allowance, "standard_seconds": standard_seconds,
            "default_rule_set": default_rule_set,
            "modeling_policy": modeling_policy,
            "level_policy": level_policy,
            "revision_no": int(ws.revision_no or 1),
            "content_hash": ws.content_hash,
            "last_edited_by": ws.last_edited_by,
            "last_edited_at": ws.last_edited_at.isoformat() if ws.last_edited_at else None}


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
        raise NotEditable(f"版本狀態為 {pv.status}，無法核准")
    # R2b §9.5：publish 前查現有 valid run；不得在此新建證據
    await assert_publishable(session, worksheet_id)
    pv.status = "approved"
    pv.published_at = datetime.now(timezone.utc)
    pv.published_by = actor
    ws.status = "approved"
    await log_audit(
        session,
        entity_type="process_version",
        entity_id=pv.id,
        action="approve",
        from_status="draft",
        to_status="approved",
        actor=actor or "unknown",
    )
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
                           analyst=ws.analyst, study_date=ws.study_date, default_rule_set_id=ws.default_rule_set_id,
                           modeling_policy_version_id=ws.modeling_policy_version_id,
                           level_policy_version_id=ws.level_policy_version_id,
                           allowance_percent=ws.allowance_percent, status="draft",
                           revision_no=1, content_hash=None,
                           last_edited_by=actor, last_edited_at=datetime.now(timezone.utc))
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
                                  narrative_zh=cyc.narrative_zh, narrative_en=cyc.narrative_en,
                                  total_tmu=cyc.total_tmu,
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
    # clone 內容 hash 在首次讀取／儲存前可為空；採源內容再算一次供診斷
    out_src = await read_worksheet(session, new_ws.id)
    ch = content_hash_from_read(out_src)
    await set_content_hash(session, worksheet_id=new_ws.id, content_hash=ch)
    await session.flush()
    # R2b：clone 後對 revision=1 建立 validation 證據，使後續 publish 可過 gate
    if new_ws.level_policy_version_id is not None:
        await validate_and_persist(
            session, new_ws.id, trigger="revalidate", actor=actor or "unknown"
        )
    return {
        "new_worksheet_id": str(new_ws.id),
        "version_no": new_pv.version_no,
        "status": "draft",
        "source_version_no": pv.version_no,
        "revision_no": 1,
        "content_hash": ch,
    }


async def list_versions(session: AsyncSession, worksheet_id: uuid.UUID) -> dict[str, Any]:
    return await _version_info(session, worksheet_id)


async def retire_worksheet(session: AsyncSession, worksheet_id: uuid.UUID, actor: str | None = None) -> dict[str, Any]:
    """將已核准的工序表退役（admin 專屬）。"""
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv is None:
        raise WorksheetNotFound(str(worksheet_id))
    if pv.status != "approved":
        raise NotEditable("not_approved")
    pv.status = "retired"
    ws.status = "retired"
    await log_audit(
        session,
        entity_type="process_version",
        entity_id=pv.id,
        action="retire",
        from_status="approved",
        to_status="retired",
        actor=actor or "unknown",
    )
    await session.flush()
    return await _version_info(session, worksheet_id)
