"""v2 schema 模型彙總（定點重建）。

import 此模組即註冊所有 v2 表到 v2 Base.metadata，供 Alembic baseline 使用。
2a：org / worksheet 聚合 / vocab / rule_set 表頭。
2b（待補）：rule_set 子表（A 三分量、B 1205 值、G/P/M/X/I）。
2c（待補）：code_prefix_registry / bom / audit。
"""
from __future__ import annotations

from ddm_v2.models.v2.audit import AuditLog
from ddm_v2.models.v2.auth import AppUser
from ddm_v2.models.v2.base import Base, TimestampMixin
from ddm_v2.models.v2.bom import BomImport, BomItem
from ddm_v2.models.v2.codes import CodePrefixRegistry
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.models.v2.org import Product, Site, Sku
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.rule_set_tables import (
    RuleABand,
    RuleBOption,
    RuleGAction,
    RuleIOption,
    RuleMHandBand,
    RuleMLadderBand,
    RuleMRotationBand,
    RuleMVerb,
    RulePAddon,
    RulePBase,
    RuleXOption,
)
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import (
    LevelEntry,
    MostCycle,
    MostWorksheet,
    ProcessVersion,
    WiRow,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "Site",
    "Product",
    "Sku",
    "ProcessVersion",
    "MostWorksheet",
    "WiRow",
    "MostCycle",
    "LevelEntry",
    "WorkVocabItem",
    "RuleSet",
    "RuleABand",
    "RuleBOption",
    "RuleGAction",
    "RulePBase",
    "RulePAddon",
    "RuleMLadderBand",
    "RuleMVerb",
    "RuleMRotationBand",
    "RuleMHandBand",
    "RuleXOption",
    "RuleIOption",
    "CodePrefixRegistry",
    "BomImport",
    "BomItem",
    "AuditLog",
    "AppUser",
    "MotionTemplate",
]
