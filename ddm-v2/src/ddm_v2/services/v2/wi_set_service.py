"""WI Set project orchestration services."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ddm_v2.models.v2.motion_module import MotionModule
from ddm_v2.models.v2.wi_set import WiSetProject
from ddm_v2.schemas.v2.catalog import WorksheetCreateIn
from ddm_v2.schemas.v2.motion_module import FromModuleRequest
from ddm_v2.schemas.v2.wi_set import WiSetInstantiateIn
from ddm_v2.services.v2 import catalog_service, motion_module_service


class WiSetInstantiationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def instantiate_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: WiSetInstantiateIn,
    actor: str,
) -> dict[str, Any]:
    project = (
        await session.execute(
            select(WiSetProject)
            .where(WiSetProject.id == project_id)
            .options(selectinload(WiSetProject.items))
        )
    ).scalar_one_or_none()
    if project is None:
        raise WiSetInstantiationError("PROJECT_NOT_FOUND", f"專案不存在：{project_id}")

    items = sorted(project.items, key=lambda item: item.seq_no)
    if not items:
        raise WiSetInstantiationError("EMPTY_PROJECT", "WI 專案沒有任何 WI，無法建立分析案件")
    if any(item.wi_template_id is None for item in items):
        raise WiSetInstantiationError(
            "MANUAL_ITEM_UNSUPPORTED",
            "專案含手動 WI 條目，請先改用已發布的 WI 範本後再建立分析案件",
        )

    template_ids = {item.wi_template_id for item in items if item.wi_template_id is not None}
    modules = (
        await session.execute(select(MotionModule).where(MotionModule.id.in_(template_ids)))
    ).scalars().all()
    modules_by_id = {module.id: module for module in modules}
    for item in items:
        assert item.wi_template_id is not None
        module = modules_by_id.get(item.wi_template_id)
        if module is None:
            raise WiSetInstantiationError(
                "WI_TEMPLATE_NOT_FOUND",
                f"WI「{item.wi_name_snapshot}」的範本不存在",
            )
        if module.category != "wi-template":
            raise WiSetInstantiationError(
                "INVALID_WI_TEMPLATE",
                f"「{item.wi_name_snapshot}」不是 WI 範本",
            )
        if module.current_version <= 0:
            raise WiSetInstantiationError(
                "WI_TEMPLATE_UNPUBLISHED",
                f"WI「{item.wi_name_snapshot}」尚未發布，無法建立分析案件",
            )
        if module.status == "retired":
            raise WiSetInstantiationError(
                "WI_TEMPLATE_RETIRED",
                f"WI「{item.wi_name_snapshot}」已退役，無法建立分析案件",
            )

    worksheet = await catalog_service.create_worksheet(
        session,
        payload.sku_id,
        WorksheetCreateIn(
            model_label=payload.model_label,
            analyst=payload.analyst or actor,
        ),
        actor=actor,
    )

    imported_rows = 0
    drift_warnings: list[dict[str, Any]] = []
    for item in items:
        assert item.wi_template_id is not None
        try:
            result = await motion_module_service.instantiate_to_worksheet(
                session,
                worksheet["worksheet_id"],
                FromModuleRequest(module_id=item.wi_template_id),
                actor,
            )
        except motion_module_service.ModuleVersionNotFound as error:
            raise WiSetInstantiationError(
                "WI_TEMPLATE_VERSION_NOT_FOUND",
                f"WI「{item.wi_name_snapshot}」的發布版本不存在",
            ) from error
        except motion_module_service.RuleSetNotFound as error:
            raise WiSetInstantiationError(
                "WORKSHEET_RULE_SET_NOT_FOUND",
                "分析案件使用的規則版本不存在",
            ) from error
        except motion_module_service.PublishValidationError as error:
            raise WiSetInstantiationError(
                error.code,
                f"WI「{item.wi_name_snapshot}」第 {error.row_index + 1} 列：{error.message}",
            ) from error
        imported_rows += len(result["new_rows"])
        drift_warnings.extend(
            {
                "wi_set_item_id": str(item.id),
                "item_seq_no": item.seq_no,
                "wi_template_id": str(item.wi_template_id),
                **warning,
            }
            for warning in result["tmu_drift"]
        )

    return {
        **worksheet,
        "imported_wi_count": len(items),
        "imported_row_count": imported_rows,
        "tmu_drift": drift_warnings,
    }
