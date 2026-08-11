"""Strict intermediate drafts（extra=forbid）；轉 CycleIn 前的型別關卡。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictASlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reach_cm: float = 0
    twist_deg: float = 0
    foot_cm: float = 0


class StrictBSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    b_code: str | None = None


class StrictGSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    g_code: str | None = None
    modifiers: dict[str, bool] = Field(default_factory=dict)


class StrictPSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p_base_code: str | None = None
    p_addon_codes: list[str] = Field(default_factory=list)
    precision: bool = False


class StrictMComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verb_code: str | None = None
    distance_cm: float = 0
    angle_deg: float = 0
    revolutions: int = 1
    diameter_cm: float = 0


class StrictMSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    m_components: list[StrictMComponent] = Field(default_factory=list)


class StrictXSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_code: str | None = None
    x_seconds: float = 0


class StrictISlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    i_code: str | None = None


class StrictGmDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: Literal["GM"] = "GM"
    a0: StrictASlot = Field(default_factory=StrictASlot)
    b1: StrictBSlot = Field(default_factory=StrictBSlot)
    g2: StrictGSlot = Field(default_factory=StrictGSlot)
    a3: StrictASlot = Field(default_factory=StrictASlot)
    b4: StrictBSlot = Field(default_factory=StrictBSlot)
    p5: StrictPSlot = Field(default_factory=StrictPSlot)
    a6: StrictASlot = Field(default_factory=StrictASlot)
    frequency: float = 1


class StrictCmDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: Literal["CM"] = "CM"
    a0: StrictASlot = Field(default_factory=StrictASlot)
    b1: StrictBSlot = Field(default_factory=StrictBSlot)
    g2: StrictGSlot = Field(default_factory=StrictGSlot)
    m3: StrictMSlot = Field(default_factory=StrictMSlot)
    x4: StrictXSlot = Field(default_factory=StrictXSlot)
    i5: StrictISlot = Field(default_factory=StrictISlot)
    a6: StrictASlot = Field(default_factory=StrictASlot)
    frequency: float = 1
