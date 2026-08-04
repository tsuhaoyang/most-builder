"""案件清單服務：案件級聚合（P1-A）。

**聚合語意**（`docs/architecture/v2-authoritative-model-guide.md` §1/§6）：
v3 的「案件」是平面清單＋狀態機，不存在版本鏈；v2 保留版本鏈（稽核優勢），
但清單不再一版一列 —— 以 `(sku_id, model_label)` 聚合成「案件」，
呈現**代表版（最新版）** 的既有欄位＋ `version_count` ＋可展開的 `versions[]` 歷史。

代表版 = `created_at DESC` 最新者（version_no 是自由文字，字典序會把 v10 排在 v9 前）。

total_tmu 由 SUM(MostCycle.total_tmu * WiRow.frequency) 批次聚合（MostWorksheet 無存儲欄），
僅計未帶 SIMO 標記的列（simo_group_id IS NULL）——ADR-020：SIMO 標記列貢獻 0，
與 most_engine.compute_table / read_worksheet 口徑一致。

**效能鐵則**：無 N+1。固定 3 趟查詢（count / 代表版分頁 / 該頁案件的完整歷史），
代表版與歷史都靠 `ROW_NUMBER() OVER (PARTITION BY case_key ...)` 單趟撈齊。
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, cast, func, literal, over, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.org import Product, Site, Sku
from ddm_v2.models.v2.worksheet import MostCycle, MostWorksheet, ProcessVersion, WiRow


def _build_ranked_subquery(
    site_id: uuid.UUID | None,
) -> Any:
    """所有版本 + 案件分群 + 代表版排名（單趟 window function）。

    case_key = "<sku_id>|<model_label>"（model_label 為 NULL 時以空字串代表，
    避免 NULL 在後續 IN 比對中永不相等）。
    """
    # 批次聚合 total_tmu：SUM(mc.total_tmu * wr.frequency) per worksheet（單一 JOIN，非 N+1）。
    # ADR-020：SIMO 標記列（simo_group_id 非空）貢獻 0 → WHERE simo_group_id IS NULL。
    tmu_sub = (
        select(
            WiRow.worksheet_id.label("ws_id"),
            func.sum(MostCycle.total_tmu * WiRow.frequency).label("total_tmu"),
        )
        .join(MostCycle, MostCycle.wi_row_id == WiRow.id)
        .where(WiRow.simo_group_id.is_(None))
        .group_by(WiRow.worksheet_id)
        .subquery("tmu_agg")
    )

    case_key = func.concat(
        cast(ProcessVersion.sku_id, String),
        literal("|"),
        func.coalesce(MostWorksheet.model_label, literal("")),
    ).label("case_key")

    # 代表版排序鍵：created_at DESC（version_no 是 TEXT，字典序不可靠），id 作決勝
    rep_order = (ProcessVersion.created_at.desc(), ProcessVersion.id.desc())

    q = (
        select(
            ProcessVersion.id.label("process_version_id"),
            ProcessVersion.version_no.label("version_no"),
            ProcessVersion.status.label("status"),
            ProcessVersion.published_at.label("approved_at"),
            ProcessVersion.created_at.label("created_at"),
            MostWorksheet.id.label("worksheet_id"),
            MostWorksheet.model_label.label("model_label"),
            Sku.id.label("sku_id"),
            Sku.name_zh.label("sku_name_zh"),
            Sku.sku_code.label("sku_code"),
            Product.id.label("product_id"),
            Product.name_zh.label("product_name"),
            Site.id.label("site_id"),
            Site.name_zh.label("site_name"),
            tmu_sub.c.total_tmu.label("ws_total_tmu"),
            case_key,
            over(func.row_number(), partition_by=case_key, order_by=rep_order).label("rn"),
            over(func.count(), partition_by=case_key).label("version_count"),
        )
        .join(MostWorksheet, MostWorksheet.process_version_id == ProcessVersion.id)
        .outerjoin(tmu_sub, tmu_sub.c.ws_id == MostWorksheet.id)
        .join(Sku, Sku.id == ProcessVersion.sku_id)
        .join(Product, Product.id == Sku.product_id)
        .join(Site, Site.id == Product.site_id)
    )
    # ⚠️ site_id 是案件屬性（跟著 SKU 走），在排名前過濾不影響代表版選擇；
    #    status 則**不可**在此過濾——代表版必須是「所有版本中的最新版」，
    #    否則 status=draft 會誤把舊的 draft 當成代表版。
    if site_id:
        q = q.where(Site.id == site_id)
    return q.subquery("ranked")


def _tmu(value: Any) -> float | None:
    return float(value) if value is not None else None


async def list_cases(
    session: AsyncSession,
    status: str | None = None,
    site_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """案件清單（案件級聚合＋歷史折疊＋分頁）。

    - 聚合鍵：`(sku_id, model_label)`
    - 代表版：最新版（created_at DESC）
    - `status` 篩選代表版狀態（案件的「當前狀態」），`versions[]` 仍給完整歷史
    - `total` / `limit` / `offset` 都在**案件**層級
    """
    ranked = _build_ranked_subquery(site_id)

    reps_q = select(ranked).where(ranked.c.rn == 1)
    if status:
        reps_q = reps_q.where(ranked.c.status == status)

    # total = 案件數（非版本數）
    total: int = (
        await session.execute(select(func.count()).select_from(reps_q.subquery("reps_cnt")))
    ).scalar_one()

    page_q = reps_q.order_by(ranked.c.created_at.desc(), ranked.c.process_version_id.desc()).offset(offset).limit(limit)
    reps = (await session.execute(page_q)).all()

    keys = [r.case_key for r in reps]
    history: dict[str, list[dict[str, Any]]] = {k: [] for k in keys}
    if keys:
        # 單趟撈本頁所有案件的完整版本歷史（非 N+1）；按版本序（created_at ASC）
        hist_q = (
            select(
                ranked.c.case_key,
                ranked.c.process_version_id,
                ranked.c.worksheet_id,
                ranked.c.version_no,
                ranked.c.status,
                ranked.c.ws_total_tmu,
                ranked.c.created_at,
                ranked.c.approved_at,
            )
            .where(ranked.c.case_key.in_(keys))
            .order_by(ranked.c.created_at.asc(), ranked.c.process_version_id.asc())
        )
        for h in (await session.execute(hist_q)).all():
            history[h.case_key].append({
                "process_version_id": h.process_version_id,
                "worksheet_id": h.worksheet_id,
                "version_no": h.version_no,
                "status": h.status,
                "total_tmu": _tmu(h.ws_total_tmu),
                "created_at": h.created_at,
                "approved_at": h.approved_at,
            })

    items: list[dict[str, Any]] = []
    for row in reps:
        items.append({
            "process_version_id": row.process_version_id,
            "worksheet_id": row.worksheet_id,
            "version_no": row.version_no,
            "status": row.status,
            "site_id": row.site_id,
            "site_name": row.site_name,
            "product_id": row.product_id,
            "product_name": row.product_name,
            "sku_id": row.sku_id,
            "sku_name": row.sku_name_zh or row.sku_code,
            "process_name": row.sku_name_zh or row.sku_code,
            "approved_at": row.approved_at,
            "created_at": row.created_at,
            "total_tmu": _tmu(row.ws_total_tmu),
            "model_label": row.model_label,
            "version_count": row.version_count,
            "versions": history.get(row.case_key, []),
        })

    return {"total": total, "items": items}
