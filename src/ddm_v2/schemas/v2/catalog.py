"""目錄/結構契約：Site / Product / Sku / 建立工序表。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel


class SiteOut(BaseModel):
    id: uuid.UUID
    external_code: str | None
    name_zh: str
    name_en: str | None
    is_active: bool


class ProductIn(BaseModel):
    site_id: uuid.UUID
    name_zh: str
    external_code: str | None = None
    name_en: str | None = None
    description: str | None = None


class ProductPatch(BaseModel):
    name_zh: str | None = None
    name_en: str | None = None
    description: str | None = None
    is_active: bool | None = None


class ProductOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    external_code: str | None
    name_zh: str
    name_en: str | None
    description: str | None
    is_active: bool


class SkuIn(BaseModel):
    product_id: uuid.UUID
    sku_code: str
    name_zh: str | None = None
    name_en: str | None = None


class SkuPatch(BaseModel):
    name_zh: str | None = None
    name_en: str | None = None
    is_active: bool | None = None


class SkuOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    sku_code: str
    name_zh: str | None
    name_en: str | None
    is_active: bool


class WorksheetCreateIn(BaseModel):
    model_label: str | None = None
    analyst: str | None = None


class WorksheetSummaryOut(BaseModel):
    worksheet_id: uuid.UUID
    version_no: str
    status: str
    analyst: str | None
    model_label: str | None


class WorksheetCreateOut(BaseModel):
    worksheet_id: uuid.UUID
    version_no: str
    status: str
    revision_no: int = 1
    modeling_policy_version_id: uuid.UUID | None = None
    level_policy_version_id: uuid.UUID | None = None
