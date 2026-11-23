"""區域、DSX 座標同步、物件歸區（ADR-038 D5.1–D5.5，W7a）。

- 區域按 SKU 保存（D5.1），綁 DSX 物件 id（D5.3）。中心座標**只**由 `sync_from_dsx` 寫入（D5.4、I6）：
  使用者按「同步」→ 拉 DSX `GET /api/v1/placements` → 存一份快照 → 綁了物件的區域取該物件的量測點當中心。
  沒按同步，3D 裡的拖動不會改變任何已存的座標。
- 物件歸區：(SKU, 物件) → 區域，按 SKU 記住（D5.2 步驟 3）；物件是 `work_vocab_items`。
- DSX 沒有認證，回應當不可信輸入（`dsx_client` 有筆數與字串上限、拒絕非有限數）。

權限只用既有四級角色（BL-ENG-19）：讀 viewer、寫 analyst、新增區域類別 admin。
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from ddm_v2.models.v2.org import Sku
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion, WiRow
from ddm_v2.models.v2.zone import SkuObjectZone, SkuPlacementSnapshot, SkuZone, ZoneCategory
from ddm_v2.schemas.v2.zone import MAX_ZONES_PER_SKU
from ddm_v2.services.v2 import dsx_client
from ddm_v2.settings import get_settings


class SkuNotFound(Exception):
    pass


class ZoneNotFound(Exception):
    pass


class CategoryNotFound(Exception):
    pass


class CategoryExists(Exception):
    pass


class ZoneNameTaken(Exception):
    pass


class ZoneInUse(Exception):
    """區域還有物件歸在它底下，不能刪（先取消歸區）。"""

    def __init__(self, count: int) -> None:
        super().__init__(f"還有 {count} 個物件歸在這個區域")
        self.count = count


class TooManyZones(Exception):
    pass


class VocabNotFound(Exception):
    def __init__(self, ids: Sequence[uuid.UUID]) -> None:
        super().__init__(", ".join(sorted(str(i) for i in ids)))
        self.ids = list(ids)


class DsxDisabled(Exception):
    """DSX 整合開關關著（`DDM_DSX_INTEGRATION_ENABLED`）。"""


class DsxMisconfigured(Exception):
    """DSX 整合開著但設定不完整（沒有 base URL）。"""


# 每個 SKU 保留最近幾份座標快照（區域只引用最新一份；舊的留著查歷史，太舊的刪掉）
KEEP_SNAPSHOTS_PER_SKU = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def point_of(x: Decimal | None, y: Decimal | None, z: Decimal | None) -> dict[str, float] | None:
    if x is None or y is None or z is None:
        return None
    return {"x": float(x), "y": float(y), "z": float(z)}


def zone_out(z: SkuZone) -> dict[str, Any]:
    return {
        "id": z.id, "sku_id": z.sku_id, "category_id": z.category_id, "name": z.name,
        "dsx_object_id": z.dsx_object_id, "center": point_of(z.center_x, z.center_y, z.center_z),
        "center_snapshot_id": z.center_snapshot_id, "updated_at": z.updated_at,
    }


def snapshot_out(s: SkuPlacementSnapshot) -> dict[str, Any]:
    return {
        "id": s.id, "sku_id": s.sku_id, "dsx_station_id": s.dsx_station_id,
        "placement_revision": s.placement_revision, "synced_by": s.synced_by, "synced_at": s.synced_at,
        "placement_count": s.placement_count,
    }


# ── 類別 ────────────────────────────────────────────────────────────────────

async def list_categories(session: AsyncSession) -> list[ZoneCategory]:
    return list((await session.execute(select(ZoneCategory).order_by(ZoneCategory.sort_order, ZoneCategory.code))).scalars())


async def add_category(
    session: AsyncSession, *, code: str, name_zh: str, name_en: str, sort_order: int, actor: str
) -> ZoneCategory:
    if (await session.execute(select(ZoneCategory.id).where(ZoneCategory.code == code))).first():
        raise CategoryExists(code)
    cat = ZoneCategory(id=uuid.uuid4(), code=code, name_zh=name_zh, name_en=name_en, sort_order=sort_order,
                       builtin=False, created_by=actor, created_at=_now())
    session.add(cat)
    await session.flush()
    return cat


# ── 區域 ────────────────────────────────────────────────────────────────────

async def _require_sku(session: AsyncSession, sku_id: uuid.UUID, *, lock: bool = False) -> Sku:
    stmt = select(Sku).where(Sku.id == sku_id)
    if lock:
        # 同一 SKU 的區域新增、同步、歸區依序執行（上限與名稱唯一不會被並行繞過）
        stmt = stmt.with_for_update()
    sku = (await session.execute(stmt)).scalar_one_or_none()
    if sku is None:
        raise SkuNotFound(str(sku_id))
    return sku


async def list_zones(session: AsyncSession, sku_id: uuid.UUID) -> tuple[list[SkuZone], SkuPlacementSnapshot | None]:
    await _require_sku(session, sku_id)
    zones = list((await session.execute(select(SkuZone).where(SkuZone.sku_id == sku_id).order_by(SkuZone.name))).scalars())
    return zones, await latest_snapshot(session, sku_id)


async def latest_snapshot(session: AsyncSession, sku_id: uuid.UUID) -> SkuPlacementSnapshot | None:
    """最近一次同步（不載入 placements 本體）。"""
    return (
        await session.execute(
            select(SkuPlacementSnapshot)
            .options(defer(SkuPlacementSnapshot.placements))
            .where(SkuPlacementSnapshot.sku_id == sku_id)
            .order_by(SkuPlacementSnapshot.synced_at.desc(), SkuPlacementSnapshot.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _require_category(session: AsyncSession, category_id: uuid.UUID) -> None:
    if await session.get(ZoneCategory, category_id) is None:
        raise CategoryNotFound(str(category_id))


async def _name_taken(session: AsyncSession, sku_id: uuid.UUID, name: str, *, except_id: uuid.UUID | None = None) -> bool:
    stmt = select(SkuZone.id).where(SkuZone.sku_id == sku_id, SkuZone.name == name)
    if except_id is not None:
        stmt = stmt.where(SkuZone.id != except_id)
    return (await session.execute(stmt)).first() is not None


async def create_zone(
    session: AsyncSession, sku_id: uuid.UUID, *, category_id: uuid.UUID, name: str, dsx_object_id: str | None,
    actor: str,
) -> SkuZone:
    await _require_sku(session, sku_id, lock=True)
    await _require_category(session, category_id)
    n = (await session.execute(select(func.count()).select_from(SkuZone).where(SkuZone.sku_id == sku_id))).scalar_one()
    if n >= MAX_ZONES_PER_SKU:
        raise TooManyZones(f"每個 SKU 最多 {MAX_ZONES_PER_SKU} 個區域")
    if await _name_taken(session, sku_id, name):
        raise ZoneNameTaken(name)
    now = _now()
    z = SkuZone(id=uuid.uuid4(), sku_id=sku_id, category_id=category_id, name=name, dsx_object_id=dsx_object_id,
                created_by=actor, created_at=now, updated_at=now)
    session.add(z)
    await session.flush()
    return z


async def _lock_zone(session: AsyncSession, zone_id: uuid.UUID) -> SkuZone:
    """鎖順序一律「先 SKU、再區域」（與新增、同步、歸區相同），避免互相等待而死結。"""
    sku_id = (await session.execute(select(SkuZone.sku_id).where(SkuZone.id == zone_id))).scalar_one_or_none()
    if sku_id is None:
        raise ZoneNotFound(str(zone_id))
    await _require_sku(session, sku_id, lock=True)
    z = (await session.execute(
        select(SkuZone).where(SkuZone.id == zone_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if z is None:
        raise ZoneNotFound(str(zone_id))
    return z


async def patch_zone(session: AsyncSession, zone_id: uuid.UUID, fields: dict[str, Any], *, actor: str) -> SkuZone:
    z = await _lock_zone(session, zone_id)
    if fields.get("category_id") is not None:
        await _require_category(session, fields["category_id"])
        z.category_id = fields["category_id"]
    if fields.get("name") is not None and fields["name"] != z.name:
        if await _name_taken(session, z.sku_id, fields["name"], except_id=z.id):
            raise ZoneNameTaken(fields["name"])
        z.name = fields["name"]
    if "dsx_object_id" in fields and fields["dsx_object_id"] != z.dsx_object_id:
        z.dsx_object_id = fields["dsx_object_id"]
        # 換了綁定的物件，舊座標就不屬於這個區域了；要重新同步
        z.center_x = z.center_y = z.center_z = None
        z.center_snapshot_id = None
    z.updated_by = actor
    z.updated_at = _now()
    await session.flush()
    return z


async def delete_zone(session: AsyncSession, zone_id: uuid.UUID) -> None:
    # 拿著 SKU 鎖計數：歸區也要先鎖 SKU，所以計數之後不會有人插進來
    z = await _lock_zone(session, zone_id)
    n = (await session.execute(select(func.count()).select_from(SkuObjectZone).where(SkuObjectZone.zone_id == z.id))).scalar_one()
    if n:
        raise ZoneInUse(n)
    await session.delete(z)
    await session.flush()


# ── DSX ─────────────────────────────────────────────────────────────────────

def _dsx_settings() -> tuple[str, float]:
    s = get_settings()
    if not s.dsx_integration_enabled:
        raise DsxDisabled("DSX 整合未開啟")
    if not s.dsx_api_base_url:
        raise DsxMisconfigured("DDM_DSX_INTEGRATION_ENABLED=1 但 DDM_DSX_API_BASE_URL 未設定")
    return s.dsx_api_base_url, s.dsx_timeout_s


async def dsx_objects() -> list[dsx_client.DsxObject]:
    base_url, timeout_s = _dsx_settings()
    return await dsx_client.list_objects(base_url=base_url, timeout_s=timeout_s)


async def sync_from_dsx(
    session: AsyncSession, sku_id: uuid.UUID, *, actor: str
) -> tuple[SkuPlacementSnapshot, SkuPlacementSnapshot | None, list[SkuZone], list[uuid.UUID], list[uuid.UUID]]:
    """拉 DSX 座標、存快照、更新綁定區域的中心。

    回傳 (新快照, 前一份快照, 區域, 快照裡找不到物件的區域, 沒綁物件的區域)。前一份讓畫面提示
    「DSX 站別或版本和上次不同」（DSX 共用一個場景，同步進哪個 SKU 靠使用者，D5.4）。

    呼叫端的 session 在這之前不能有未提交的寫入：呼叫 DSX 前會結束目前交易，等外部服務期間不占 DB 連線。
    """
    base_url, timeout_s = _dsx_settings()
    await _require_sku(session, sku_id)
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("sync_from_dsx requires a session without pending writes")
    await session.commit()
    data = await dsx_client.get_placements(base_url=base_url, timeout_s=timeout_s)
    await _require_sku(session, sku_id, lock=True)
    previous = await latest_snapshot(session, sku_id)
    points = {p.object_id: p for p in data.placements}
    now = _now()
    snap = SkuPlacementSnapshot(
        id=uuid.uuid4(), sku_id=sku_id, dsx_station_id=data.station_id, placement_revision=data.placement_revision,
        placements=[{"object_id": p.object_id, "x": p.x, "y": p.y, "z": p.z, "point_source": p.point_source}
                    for p in data.placements],
        placement_count=len(data.placements), synced_by=actor, synced_at=now,
    )
    session.add(snap)
    await session.flush()
    zones = list((await session.execute(
        select(SkuZone).where(SkuZone.sku_id == sku_id).order_by(SkuZone.name).with_for_update()
    )).scalars())
    missing: list[uuid.UUID] = []
    unbound: list[uuid.UUID] = []
    for z in zones:
        if not z.dsx_object_id:
            unbound.append(z.id)
            continue
        p = points.get(z.dsx_object_id)
        if p is None:
            # 不沿用舊座標：快照裡沒有就是現在不知道它在哪，算距離時會明確回報
            missing.append(z.id)
            z.center_x = z.center_y = z.center_z = None
            z.center_snapshot_id = None
        else:
            z.center_x, z.center_y, z.center_z = (Decimal(str(round(v, 2))) for v in (p.x, p.y, p.z))
            z.center_snapshot_id = snap.id
        z.updated_by = actor
        z.updated_at = now
    await session.flush()
    await _prune_snapshots(session, sku_id)
    return snap, previous, zones, missing, unbound


async def _prune_snapshots(session: AsyncSession, sku_id: uuid.UUID) -> None:
    """每個 SKU 只留最近 `KEEP_SNAPSHOTS_PER_SKU` 份；區域引用的快照（最新一份）一定在保留範圍內。"""
    keep = select(SkuPlacementSnapshot.id).where(SkuPlacementSnapshot.sku_id == sku_id).order_by(
        SkuPlacementSnapshot.synced_at.desc(), SkuPlacementSnapshot.id.desc()
    ).limit(KEEP_SNAPSHOTS_PER_SKU)
    await session.execute(
        delete(SkuPlacementSnapshot).where(
            SkuPlacementSnapshot.sku_id == sku_id, SkuPlacementSnapshot.id.not_in(keep.scalar_subquery())
        )
    )
    await session.flush()


# ── 物件歸區 ────────────────────────────────────────────────────────────────

async def list_object_zones(session: AsyncSession, sku_id: uuid.UUID) -> list[SkuObjectZone]:
    await _require_sku(session, sku_id)
    return list((await session.execute(
        select(SkuObjectZone).where(SkuObjectZone.sku_id == sku_id).order_by(SkuObjectZone.assigned_at)
    )).scalars())


async def set_object_zones(
    session: AsyncSession, sku_id: uuid.UUID, items: Sequence[tuple[uuid.UUID, uuid.UUID | None]], *, actor: str
) -> list[SkuObjectZone]:
    """一次設定多個物件的區域（zone_id=None＝取消歸區）。同一請求內同一物件以最後一筆為準。"""
    await _require_sku(session, sku_id, lock=True)
    wanted: dict[uuid.UUID, uuid.UUID | None] = {}
    for vocab_id, zone_id in items:
        wanted[vocab_id] = zone_id
    # 只擋「要歸區」的物件是否存在且未刪除；取消歸區不檢查（已刪除的物件也要能取消）
    to_assign = [v for v, z in wanted.items() if z is not None]
    found = set((await session.execute(
        select(WorkVocabItem.id).where(
            WorkVocabItem.id.in_(to_assign), WorkVocabItem.deleted_at.is_(None), WorkVocabItem.is_active.is_(True)
        )
    )).scalars()) if to_assign else set()
    if missing := [v for v in to_assign if v not in found]:
        raise VocabNotFound(missing)
    zone_ids = {z for z in wanted.values() if z is not None}
    if zone_ids:
        ok = set((await session.execute(
            select(SkuZone.id).where(SkuZone.id.in_(list(zone_ids)), SkuZone.sku_id == sku_id)
        )).scalars())
        if bad := sorted(zone_ids - ok, key=str):
            raise ZoneNotFound(", ".join(str(b) for b in bad))
    existing = {
        r.vocab_item_id: r
        for r in (await session.execute(
            select(SkuObjectZone).where(SkuObjectZone.sku_id == sku_id, SkuObjectZone.vocab_item_id.in_(list(wanted)))
            .with_for_update()
        )).scalars()
    }
    now = _now()
    for vocab_id, zone_id in wanted.items():
        row = existing.get(vocab_id)
        if zone_id is None:
            if row is not None:
                await session.delete(row)
            continue
        if row is None:
            session.add(SkuObjectZone(sku_id=sku_id, vocab_item_id=vocab_id, zone_id=zone_id,
                                      assigned_by=actor, assigned_at=now))
        elif row.zone_id != zone_id:
            row.zone_id = zone_id
            row.assigned_by = actor
            row.assigned_at = now
    await session.flush()
    return await list_object_zones(session, sku_id)


async def worksheet_sku_id(session: AsyncSession, worksheet_id: uuid.UUID) -> uuid.UUID | None:
    return (await session.execute(
        select(ProcessVersion.sku_id)
        .join(MostWorksheet, MostWorksheet.process_version_id == ProcessVersion.id)
        .where(MostWorksheet.id == worksheet_id)
    )).scalar_one_or_none()


_ROLE_COLUMNS = (
    ("object", WiRow.object_vocab_id),
    ("from", WiRow.from_vocab_id),
    ("to", WiRow.to_vocab_id),
    ("tool", WiRow.tool_vocab_id),
)


async def worksheet_objects(session: AsyncSession, worksheet_id: uuid.UUID) -> tuple[uuid.UUID, list[dict[str, Any]]]:
    """這份工時表用到的物件去重列出，附目前的歸區（D5.2 步驟 3）。"""
    sku_id = await worksheet_sku_id(session, worksheet_id)
    if sku_id is None:
        raise SkuNotFound(f"worksheet {worksheet_id}")
    rows = (await session.execute(
        select(WiRow.id, WiRow.object_vocab_id, WiRow.from_vocab_id, WiRow.to_vocab_id, WiRow.tool_vocab_id)
        .where(WiRow.worksheet_id == worksheet_id)
        .where(or_(*(c.is_not(None) for _, c in _ROLE_COLUMNS)))
    )).all()
    roles: dict[uuid.UUID, set[str]] = {}
    row_ids: dict[uuid.UUID, set[uuid.UUID]] = {}
    for r in rows:
        for role, vid in (("object", r.object_vocab_id), ("from", r.from_vocab_id), ("to", r.to_vocab_id),
                          ("tool", r.tool_vocab_id)):
            if vid is not None:
                roles.setdefault(vid, set()).add(role)
                row_ids.setdefault(vid, set()).add(r.id)
    if not roles:
        return sku_id, []
    items = {v.id: v for v in (await session.execute(
        select(WorkVocabItem).where(WorkVocabItem.id.in_(list(roles)))
    )).scalars()}
    assigned = {a.vocab_item_id: a.zone_id for a in (await session.execute(
        select(SkuObjectZone).where(SkuObjectZone.sku_id == sku_id, SkuObjectZone.vocab_item_id.in_(list(roles)))
    )).scalars()}
    order = {"object": 0, "from": 1, "to": 2, "tool": 3}
    out = []
    for vid, rs in roles.items():
        v = items.get(vid)
        if v is None:
            continue
        out.append({
            "vocab_item_id": vid, "kind": v.kind, "name_zh": v.name_zh, "name_en": v.name_en,
            "roles": sorted(rs, key=order.__getitem__), "row_count": len(row_ids[vid]), "zone_id": assigned.get(vid),
        })
    out.sort(key=lambda o: (o["zone_id"] is not None, o["name_zh"]))
    return sku_id, out
