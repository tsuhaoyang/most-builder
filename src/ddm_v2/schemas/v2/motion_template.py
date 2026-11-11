"""動作範本庫契約。cycle_template 直接用 CycleIn（與工時表同一形狀）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from ddm_v2.schemas.v2.most import CycleIn


class MotionTemplateIn(BaseModel):
    name_zh: str
    name_en: str | None = None
    category: str | None = None
    keywords: list[str] = Field(default_factory=list)
    seq_kind: str  # GM / CM
    cycle_template: CycleIn


class MotionTemplatePatchIn(BaseModel):
    name_zh: str | None = None
    name_en: str | None = None
    category: str | None = None
    keywords: list[str] | None = None
    seq_kind: str | None = None
    cycle_template: CycleIn | None = None
    is_active: bool | None = None


class MotionTemplateOut(BaseModel):
    id: uuid.UUID
    name_zh: str
    name_en: str | None
    category: str | None
    keywords: list[str]
    seq_kind: str
    cycle_template: dict
    status: str            # draft / standard
    owner: str | None
    is_active: bool


class MatchIn(BaseModel):
    """匯入用：以描述比對範本（P2）。"""
    description: str
    limit: int = 3


class MatchHit(BaseModel):
    template: MotionTemplateOut
    score: float
    matched_keywords: list[str]
