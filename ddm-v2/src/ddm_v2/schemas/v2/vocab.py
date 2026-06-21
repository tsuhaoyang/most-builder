"""v2 詞彙庫主數據 API 契約（FE-5）。"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

VocabKind = Literal["object", "component", "tool", "from", "to", "hand"]


class VocabItemIn(BaseModel):
    kind: VocabKind
    name_zh: str
    name_en: str | None = None
    external_code: str | None = None
    source_system: str = "local"
    site_id: uuid.UUID | None = None


class VocabPatchIn(BaseModel):
    name_zh: str | None = None
    name_en: str | None = None
    external_code: str | None = None


class VocabItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    name_zh: str
    name_en: str | None
    external_code: str | None
    source_system: str
    is_active: bool
