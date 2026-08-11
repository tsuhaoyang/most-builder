"""v2 schema 模型彙總（定點重建）。

import 此模組即註冊所有 v2 表到 v2 Base.metadata，供 Alembic baseline 使用。
2a：org / worksheet 聚合 / vocab / rule_set 表頭。
2b（待補）：rule_set 子表（A 三分量、B 1205 值、G/P/M/X/I）。
2c（待補）：code_prefix_registry / bom / audit。
"""
from __future__ import annotations

from ddm_v2.models.v2.ai_ops import (
    AiDeploymentBundle,
    AiFeedbackCandidate,
    AiParseJob,
    AiParseJobItem,
    AiParseRun,
    AiReviewEvent,
)
from ddm_v2.models.v2.audit import WorkflowAuditLog
from ddm_v2.models.v2.auth import AppUser
from ddm_v2.models.v2.base import Base, TimestampMixin
from ddm_v2.models.v2.bom import BomImport, BomItem
from ddm_v2.models.v2.codes import CodePrefixRegistry
from ddm_v2.models.v2.import_staging import ExcelImport, ImportProfile, ImportRow
from ddm_v2.models.v2.level_validation import LevelValidationRun
from ddm_v2.models.v2.motion_module import MotionModule, MotionModuleVersion
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.models.v2.org import Product, Site, Sku
from ddm_v2.models.v2.outbox import OutboxEvent
from ddm_v2.models.v2.policy import LevelPolicyVersion, ModelingPolicyVersion
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.rule_set_tables import (
    RuleABand,
    RuleBOption,
    RuleGAction,
    RuleIOption,
    RuleMFootBand,
    RuleMHandBand,
    RuleMLadderBand,
    RuleMRotationBand,
    RuleMVerb,
    RulePAddon,
    RulePBase,
    RuleXOption,
)
from ddm_v2.models.v2.synonym import RuleOptionSynonym
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.wi_context import WiRowContext
from ddm_v2.models.v2.wi_set import WiSetItem, WiSetProject
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
    "RuleMFootBand",
    "RuleMVerb",
    "RuleMRotationBand",
    "RuleMHandBand",
    "RuleXOption",
    "RuleIOption",
    "CodePrefixRegistry",
    "BomImport",
    "BomItem",
    "WorkflowAuditLog",
    "AppUser",
    "MotionModule",
    "MotionModuleVersion",
    "MotionTemplate",
    "ExcelImport",
    "ImportProfile",
    "ImportRow",
    "LevelValidationRun",
    "RuleOptionSynonym",
    "WiSetProject",
    "WiSetItem",
    "WiRowContext",
    "AiDeploymentBundle",
    "AiParseRun",
    "AiReviewEvent",
    "AiFeedbackCandidate",
    "AiParseJob",
    "AiParseJobItem",
    "ModelingPolicyVersion",
    "LevelPolicyVersion",
    "OutboxEvent",
]
