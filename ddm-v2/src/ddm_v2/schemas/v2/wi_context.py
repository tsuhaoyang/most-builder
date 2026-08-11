"""wi-context-v1 契約與 hash（R3a）。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

WI_CONTEXT_V1 = "wi-context-v1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({WI_CONTEXT_V1})

SourceLiteral = Literal["manual", "imported", "ai_assisted", "system"]


class WiContextDataV1(BaseModel):
    """正式工序 context_data（§7.2 初始 keys；額外 key 拒絕）。"""

    model_config = ConfigDict(extra="forbid")

    quality_checks: list[Any] = Field(default_factory=list)
    safety_notes: list[Any] = Field(default_factory=list)
    tool_settings: list[Any] = Field(default_factory=list)
    machine_refs: list[Any] = Field(default_factory=list)
    visual_refs: list[Any] = Field(default_factory=list)
    sop_refs: list[Any] = Field(default_factory=list)
    business_tags: list[Any] = Field(default_factory=list)


class WiContextUpsertIn(BaseModel):
    schema_version: str = WI_CONTEXT_V1
    context_data: dict[str, Any] = Field(default_factory=dict)
    source: SourceLiteral = "manual"


class WiContextOut(BaseModel):
    id: UUID
    wi_row_id: UUID
    schema_version: str
    context_data: dict[str, Any]
    context_hash: str
    source: str
    created_by: str | None = None
    updated_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def context_hash_for(data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def validate_context_payload(
    *, schema_version: str, context_data: dict[str, Any]
) -> dict[str, Any]:
    """未知 schema_version／額外 key → 失敗；回傳標準化 dict。"""
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported schema_version: {schema_version}")
    if schema_version == WI_CONTEXT_V1:
        return WiContextDataV1.model_validate(context_data).model_dump(mode="json")
    raise ValueError(f"unsupported schema_version: {schema_version}")
