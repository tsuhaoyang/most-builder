"""依區域座標算距離建議，並在使用者確認後套用到工時表（ADR-038 D5.2 步驟 3–4、D5.6 修訂，W7b）。

端點（沿用 DSX 現行語句模型）：
- `a0`＝人 → 「從哪裡」（沒有 from 時用 object）
- `a3`（GM）／`m3`（CM）＝從哪裡 → 到哪裡
- `a6`＝到哪裡 → 人
人的位置＝作業員站位（站內座標原點）＋人端偏移（建模政策，預設肩高 140 cm）。物件的位置：歸區時有物件座標就用它
（`object_coordinate`），否則用所屬區域的中心（`zone_center`，ADR-038 D5.5）。距離一律直線 3D（ADR-031 D5）。

填哪個欄位（D5.6 (b)(c)）：
- a0／a3：≤ 門檻填 `reach_cm`，> 門檻填 `foot_cm`。
- a6：≤ 門檻填 `reach_cm`；> 門檻標「需 IE 裁決」（A6 不得填 foot，不自動改填、不歸零）。
- m3：只填唯一一個 ladder 動詞分量的 `distance_cm`；> 75 cm 標「需 IE 裁決」（引擎視為錯誤，不截斷，ADR-031 I5）；
  沒有或有多個 ladder 分量也標「需 IE 裁決」。

MOST 只算公分；TMU 一律由引擎在套用（整份存檔）時算（ADR-031 I1）。建議存在 `wi_row_distance_suggestions`，
套用前重新計算一次，和使用者看到的不同就拒絕（409），不會套用使用者沒看過的值。
"""
from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.distance import WiRowDistanceSuggestion
from ddm_v2.models.v2.policy import ModelingPolicyVersion
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.worksheet import LevelEntry, MostCycle, MostWorksheet, ProcessVersion, WiRow
from ddm_v2.models.v2.zone import SkuObjectZone, SkuPlacementSnapshot, SkuZone
from ddm_v2.most_engine import load_rule_set_from_db
from ddm_v2.schemas.v2.most import CycleIn
from ddm_v2.schemas.v2.worksheet import LevelFieldsIn, WiRowSaveIn, WorksheetSaveIn
from ddm_v2.services.v2.policy_service import distance_settings

M_MAX_CM = 75.0  # 引擎 ladder 值表上限（超過是錯誤，不是飽和）
ROUND_DIGITS = 1


class WorksheetNotFound(Exception):
    pass


class NotEditable(Exception):
    pass


class NotApplicable(Exception):
    """要套用的列有格位不是 `suggested`（需 IE 裁決、算不出來），或根本沒有建議。"""

    def __init__(self, rows: dict[uuid.UUID, str]) -> None:
        self.rows = rows
        super().__init__(f"{len(rows)} 列的距離建議不能直接套用")


class SuggestionChanged(Exception):
    """重新計算的結果和使用者看到的不同（區域、歸區、快照或列內容變了），要重新算再確認。"""

    def __init__(self, rows: Sequence[uuid.UUID]) -> None:
        self.rows = sorted(rows, key=str)
        super().__init__(f"{len(self.rows)} 列的距離建議已改變，請重新計算後再確認")


# ── 純計算 ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Endpoint:
    role: str  # person｜from｜object｜to
    vocab_item_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    point: tuple[float, float, float] | None = None
    source: str | None = None  # person_offset｜zone_center｜object_coordinate
    point_source: str | None = None  # DSX：anchor｜station_local
    snapshot_id: uuid.UUID | None = None  # zone_center 時：中心座標來自哪一份快照
    reason: str | None = None  # 沒有座標時：endpoint_missing｜not_assigned｜zone_not_synced

    def as_json(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "vocab_item_id": str(self.vocab_item_id) if self.vocab_item_id else None,
            "zone_id": str(self.zone_id) if self.zone_id else None,
            "point": list(self.point) if self.point else None,
            "source": self.source, "point_source": self.point_source,
            "snapshot_id": str(self.snapshot_id) if self.snapshot_id else None, "reason": self.reason,
        }


@dataclass(frozen=True)
class SlotSuggestion:
    slot: str
    status: str  # suggested｜needs_ie｜unavailable
    field: str | None
    distance_cm: float | None
    reason: str | None
    start: Endpoint
    end: Endpoint

    def key(self) -> tuple[Any, ...]:
        """比對「使用者看到的」與「現在算的」是否相同用。"""
        return (self.slot, self.status, self.field, self.distance_cm, self.reason,
                self.start.point, self.end.point)


def _round(d: float) -> float:
    return round(d, ROUND_DIGITS)


def suggest_slot(
    slot: str, start: Endpoint, end: Endpoint, *, threshold_cm: float, ladder_components: int | None = None
) -> SlotSuggestion:
    """一格的建議。純函式。`ladder_components` 只用於 m3（該格 ladder 動詞分量的個數）。"""
    if start.point is None or end.point is None:
        missing = start if start.point is None else end
        return SlotSuggestion(slot, "unavailable", None, None, missing.reason, start, end)
    # 用原始距離比門檻與 75 cm，只在記錄與寫入時取到 0.1 cm（不讓取整把 70.04 悄悄算成 ≤ 70）
    raw = math.dist(start.point, end.point)
    d = _round(raw)
    if slot == "m3":
        if ladder_components != 1:
            reason = "m_component_missing" if not ladder_components else "m_components_multiple"
            return SlotSuggestion(slot, "needs_ie", None, d, reason, start, end)
        if raw > M_MAX_CM:
            return SlotSuggestion(slot, "needs_ie", None, d, "m_over_75", start, end)
        return SlotSuggestion(slot, "suggested", "distance_cm", d, None, start, end)
    if raw <= threshold_cm:
        return SlotSuggestion(slot, "suggested", "reach_cm", d, None, start, end)
    if slot == "a6":
        return SlotSuggestion(slot, "needs_ie", None, d, "a6_over_threshold", start, end)
    return SlotSuggestion(slot, "suggested", "foot_cm", d, None, start, end)


def suggest_row(
    seq: str,
    *,
    person: Endpoint,
    origin: Endpoint,
    destination: Endpoint,
    threshold_cm: float,
    ladder_components: int,
) -> list[SlotSuggestion]:
    """一列的建議：GM → a0、a3、a6；CM → a0、m3、a6。"""
    out = [suggest_slot("a0", person, origin, threshold_cm=threshold_cm)]
    if seq == "CM":
        out.append(suggest_slot("m3", origin, destination, threshold_cm=threshold_cm,
                                ladder_components=ladder_components))
    else:
        out.append(suggest_slot("a3", origin, destination, threshold_cm=threshold_cm))
    out.append(suggest_slot("a6", destination, person, threshold_cm=threshold_cm))
    return out


def apply_to_cycle(cycle: dict[str, Any], suggestions: Sequence[SlotSuggestion], ladder_codes: set[str]) -> dict[str, Any]:
    """把 `suggested` 的格位寫進 cycle 的複本（A 格：目標欄位寫入、另一個距離欄位清 0；m3：唯一 ladder 分量）。"""
    out = {**cycle}
    for s in suggestions:
        if s.status != "suggested" or s.distance_cm is None:
            continue
        if s.slot == "m3":
            m3 = dict(out.get("m3") or {})
            comps = [dict(c) for c in (m3.get("m_components") or [])]
            for c in comps:
                if c.get("verb_code") in ladder_codes:
                    c["distance_cm"] = s.distance_cm
            m3["m_components"] = comps
            out["m3"] = m3
            continue
        a = dict(out.get(s.slot) or {})
        a["reach_cm"] = s.distance_cm if s.field == "reach_cm" else 0
        a["foot_cm"] = s.distance_cm if s.field == "foot_cm" else 0
        out[s.slot] = a
    return out


# ── 讀資料、算、存 ──────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _worksheet_context(session: AsyncSession, worksheet_id: uuid.UUID, *, lock: bool = False):
    stmt = select(MostWorksheet).where(MostWorksheet.id == worksheet_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    ws = (await session.execute(stmt)).scalar_one_or_none()
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv is None:
        raise WorksheetNotFound(str(worksheet_id))
    return ws, pv


@dataclass
class _Locator:
    """SKU 的物件 → 端點（座標與出處）。"""

    zones: dict[uuid.UUID, SkuZone]
    assignments: dict[uuid.UUID, SkuObjectZone]
    point_sources: dict[tuple[uuid.UUID, str], str]

    def endpoint(self, role: str, vocab_id: uuid.UUID | None) -> Endpoint:
        if vocab_id is None:
            return Endpoint(role, reason="endpoint_missing")
        a = self.assignments.get(vocab_id)
        if a is None:
            return Endpoint(role, vocab_id, reason="not_assigned")
        if a.object_x is not None and a.object_y is not None and a.object_z is not None:
            return Endpoint(role, vocab_id, a.zone_id, (float(a.object_x), float(a.object_y), float(a.object_z)),
                            "object_coordinate")
        z = self.zones.get(a.zone_id)
        if z is None or z.center_x is None or z.center_y is None or z.center_z is None:
            return Endpoint(role, vocab_id, a.zone_id, reason="zone_not_synced")
        ps = self.point_sources.get((z.center_snapshot_id, z.dsx_object_id or "")) if z.center_snapshot_id else None
        return Endpoint(role, vocab_id, z.id, (float(z.center_x), float(z.center_y), float(z.center_z)),
                        "zone_center", ps, z.center_snapshot_id)


async def _locator(session: AsyncSession, sku_id: uuid.UUID) -> _Locator:
    zones = {z.id: z for z in (await session.execute(select(SkuZone).where(SkuZone.sku_id == sku_id))).scalars()}
    assignments = {a.vocab_item_id: a for a in (await session.execute(
        select(SkuObjectZone).where(SkuObjectZone.sku_id == sku_id)
    )).scalars()}
    snap_ids = {z.center_snapshot_id for z in zones.values() if z.center_snapshot_id}
    point_sources: dict[tuple[uuid.UUID, str], str] = {}
    for snap in (await session.execute(
        select(SkuPlacementSnapshot).where(SkuPlacementSnapshot.id.in_(list(snap_ids)))
    )).scalars() if snap_ids else []:
        for p in snap.placements or []:
            # 沒記就是不知道，不補猜測值（出處不能編造）
            point_sources[(snap.id, p.get("object_id") or "")] = p.get("point_source")
    return _Locator(zones, assignments, point_sources)


async def _ladder_codes(session: AsyncSession, cycles: Sequence[dict[str, Any]], ws: MostWorksheet) -> set[str]:
    """ladder 類 M 動詞代碼，取自存檔時會用的同一個規則版本（第一列的 rule_set_code；沒有就用工時表預設）。"""
    code = next((c.get("rule_set_code") for c in cycles if c.get("rule_set_code")), None)
    if code is None and ws.default_rule_set_id:
        rs = await session.get(RuleSet, ws.default_rule_set_id)
        code = rs.code if rs else None
    if code is None:
        return set()
    data = await load_rule_set_from_db(session, code)
    return {c for c, (kind, _fixed) in data.m_verbs.items() if kind == "ladder"}


async def _compute(
    session: AsyncSession, ws: MostWorksheet, pv: ProcessVersion
) -> tuple[dict[uuid.UUID, list[SlotSuggestion]], dict[str, Any], uuid.UUID | None, uuid.UUID | None]:
    policy = await session.get(ModelingPolicyVersion, ws.modeling_policy_version_id) if ws.modeling_policy_version_id else None
    settings, _source = distance_settings(policy)
    threshold = float(settings["reach_foot_threshold_cm"])
    ox, oy, oz = (float(v) for v in settings["person_offset_cm"])
    person = Endpoint("person", point=(ox, oy, oz), source="person_offset")
    from ddm_v2.services.v2.zone_service import latest_snapshot

    loc = await _locator(session, pv.sku_id)
    # 建議記錄計算當下該 SKU 最新的快照；每個端點另記自己的中心座標來自哪一份（換綁未重新同步時會不同）
    latest = await latest_snapshot(session, pv.sku_id)
    snapshot_id = latest.id if latest else None
    rows = (await session.execute(
        select(WiRow, MostCycle).join(MostCycle, MostCycle.wi_row_id == WiRow.id)
        .where(WiRow.worksheet_id == ws.id).order_by(WiRow.seq_no)
    )).all()
    ladder = await _ladder_codes(session, [c.slot_inputs or {} for _w, c in rows], ws)
    out: dict[uuid.UUID, list[SlotSuggestion]] = {}
    for wr, cyc in rows:
        cycle = cyc.slot_inputs or {}
        origin = loc.endpoint("from", wr.from_vocab_id) if wr.from_vocab_id else loc.endpoint("object", wr.object_vocab_id)
        destination = loc.endpoint("to", wr.to_vocab_id)
        n_ladder = sum(1 for c in ((cycle.get("m3") or {}).get("m_components") or []) if c.get("verb_code") in ladder)
        out[wr.id] = suggest_row(cyc.seq_kind or cycle.get("seq") or "GM", person=person, origin=origin,
                                 destination=destination, threshold_cm=threshold, ladder_components=n_ladder)
    return out, settings, snapshot_id, policy.id if policy else None


def _require_draft(pv: ProcessVersion) -> None:
    if pv.status != "draft":
        raise NotEditable(f"版本狀態為 {pv.status}，已凍結不可修改（請另存新檔）")


async def compute_and_store(session: AsyncSession, worksheet_id: uuid.UUID, *, actor: str) -> list[WiRowDistanceSuggestion]:
    """重新算整份工時表的距離建議並存起來（取代舊的建議）。只在草稿版本可用。"""
    ws, pv = await _worksheet_context(session, worksheet_id, lock=True)
    _require_draft(pv)
    by_row, settings, snapshot_id, policy_id = await _compute(session, ws, pv)
    await session.execute(delete(WiRowDistanceSuggestion).where(WiRowDistanceSuggestion.worksheet_id == ws.id))
    now = _now()
    for row_id, items in by_row.items():
        for s in items:
            session.add(WiRowDistanceSuggestion(
                id=uuid.uuid4(), worksheet_id=ws.id, wi_row_id=row_id, slot=s.slot, status=s.status, field=s.field,
                distance_cm=Decimal(str(s.distance_cm)) if s.distance_cm is not None else None, reason=s.reason,
                endpoints={"from": s.start.as_json(), "to": s.end.as_json()}, snapshot_id=snapshot_id,
                threshold_cm=Decimal(str(settings["reach_foot_threshold_cm"])),
                person_offset_cm=list(settings["person_offset_cm"]), modeling_policy_version_id=policy_id,
                computed_by=actor, computed_at=now,
            ))
    await session.flush()
    return await list_suggestions(session, worksheet_id)


async def list_suggestions(session: AsyncSession, worksheet_id: uuid.UUID) -> list[WiRowDistanceSuggestion]:
    """存著的建議；只回仍存在的列（列被刪後留下的建議不顯示，下次計算時清掉）。"""
    await _worksheet_context(session, worksheet_id)
    existing = select(WiRow.id).where(WiRow.worksheet_id == worksheet_id)
    return list((await session.execute(
        select(WiRowDistanceSuggestion).where(
            WiRowDistanceSuggestion.worksheet_id == worksheet_id, WiRowDistanceSuggestion.wi_row_id.in_(existing)
        )
        .order_by(WiRowDistanceSuggestion.wi_row_id, WiRowDistanceSuggestion.slot)
    )).scalars())


def _stored_key(s: WiRowDistanceSuggestion) -> tuple[Any, ...]:
    def pt(e: dict[str, Any]) -> tuple[float, ...] | None:
        return tuple(e["point"]) if e.get("point") else None

    return (s.slot, s.status, s.field, float(s.distance_cm) if s.distance_cm is not None else None, s.reason,
            pt(s.endpoints.get("from") or {}), pt(s.endpoints.get("to") or {}))


async def save_payload_from_db(session: AsyncSession, worksheet_id: uuid.UUID) -> WorksheetSaveIn:
    """把目前的工時表原樣組成整份存檔的 payload（套用距離走既有存檔路徑，不另寫一套計算或寫入）。"""
    rows = (await session.execute(
        select(WiRow, MostCycle, LevelEntry)
        .join(MostCycle, MostCycle.wi_row_id == WiRow.id)
        .outerjoin(LevelEntry, LevelEntry.wi_row_id == WiRow.id)
        .where(WiRow.worksheet_id == worksheet_id).order_by(WiRow.seq_no)
    )).all()
    out = []
    for wr, cyc, lv in rows:
        level = LevelFieldsIn() if lv is None else LevelFieldsIn(
            coefficient=float(lv.coefficient), ascription=lv.ascription, level=lv.level,
            countersignature=lv.countersignature, parent_countersignature=lv.parent_countersignature,
            order=lv.order_in_group, number=lv.number, number_count=lv.number_count,
            machine_count=lv.machine_count, manpower=lv.manpower, worker_cub=lv.worker_cub, offline=lv.offline,
            segment=lv.segment, station_pin=lv.station_pin, is_general=lv.is_general, general_role=lv.general_role,
            merge_lock=lv.merge_lock, action_type=lv.action_type, machine_unattended=lv.machine_unattended,
        )
        out.append(WiRowSaveIn(
            id=wr.id, seq_no=wr.seq_no, sub_activity=wr.sub_activity, key_parts=wr.key_parts, hand=wr.hand,
            object_vocab_id=wr.object_vocab_id, from_vocab_id=wr.from_vocab_id, to_vocab_id=wr.to_vocab_id,
            tool_vocab_id=wr.tool_vocab_id, frequency=float(wr.frequency), simo_group_id=wr.simo_group_id,
            narrative=cyc.narrative_zh, wi_group=wr.wi_group, distance_status=wr.distance_status,
            cycle=CycleIn.model_validate(cyc.slot_inputs), level=level,
        ))
    return WorksheetSaveIn(rows=out)


class MixedRuleSets(Exception):
    """工時表各列的規則版本不一致。整份存檔會以第一列的版本重算全部列（既有行為），套用是伺服器端動作、
    使用者沒看到其他列被改版，所以先拒絕。"""


async def apply_suggestions(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    wi_row_ids: Sequence[uuid.UUID],
    *,
    base_revision: int,
    computed_at: datetime,
    actor: str,
) -> dict[str, Any]:
    """使用者確認後套用：重算一次、和存著的建議比對、寫進 cycle、該列距離狀態設 confirmed，走整份存檔。

    每一列的每一格都要是 `suggested` 才能套用（需 IE 裁決或算不出來的格位，請人工填並標 manual）。
    """
    from ddm_v2.services.v2.worksheet_service import save_worksheet

    ws, pv = await _worksheet_context(session, worksheet_id, lock=True)
    _require_draft(pv)
    wanted = list(dict.fromkeys(wi_row_ids))
    stored: dict[uuid.UUID, list[WiRowDistanceSuggestion]] = {}
    for s in (await session.execute(
        select(WiRowDistanceSuggestion).where(
            WiRowDistanceSuggestion.worksheet_id == worksheet_id, WiRowDistanceSuggestion.wi_row_id.in_(wanted)
        ).with_for_update()
    )).scalars():
        stored.setdefault(s.wi_row_id, []).append(s)
    marks = dict((await session.execute(
        select(WiRow.id, WiRow.distance_status).where(WiRow.worksheet_id == worksheet_id, WiRow.id.in_(wanted))
    )).all())
    blocked: dict[uuid.UUID, str] = {}
    for rid in wanted:
        items = stored.get(rid)
        if rid not in marks or not items:
            blocked[rid] = "no_suggestion"
        elif marks[rid] == "not_applicable":
            # 人標了「此動作無距離」，不讓套用把它蓋成 confirmed（要改請先改標示）
            blocked[rid] = "marked_not_applicable"
        elif any(s.status != "suggested" for s in items):
            blocked[rid] = next(s.reason or s.status for s in items if s.status != "suggested")
    if blocked:
        raise NotApplicable(blocked)
    # 使用者看到的那一次計算之後有人重新算過 → 不套用沒看過的值
    seen = {s.computed_at for items in stored.values() for s in items}
    if seen != {computed_at}:
        raise SuggestionChanged(wanted)
    fresh, _settings, _snap, _policy = await _compute(session, ws, pv)
    changed = [
        rid for rid in wanted
        if sorted(s.key() for s in fresh.get(rid, [])) != sorted(_stored_key(s) for s in stored[rid])
    ]
    if changed:
        raise SuggestionChanged(changed)
    payload = await save_payload_from_db(session, worksheet_id)
    codes = {r.cycle.rule_set_code for r in payload.rows}
    if len(codes) > 1:
        raise MixedRuleSets(sorted(c or "" for c in codes))
    ladder = await _ladder_codes(session, [r.cycle.model_dump(mode="json") for r in payload.rows], ws)
    targets = set(wanted)
    rows = []
    for r in payload.rows:
        if r.id in targets:
            cycle = apply_to_cycle(r.cycle.model_dump(mode="json"), fresh[r.id], ladder)
            r = r.model_copy(update={"cycle": CycleIn.model_validate(cycle), "distance_status": "confirmed"})
        rows.append(r)
    out = await save_worksheet(
        session, worksheet_id, WorksheetSaveIn(rows=rows, base_revision=base_revision), edited_by=actor
    )
    now = _now()
    for items in stored.values():
        for s in items:
            s.applied_by = actor
            s.applied_at = now
    await session.flush()
    return out
