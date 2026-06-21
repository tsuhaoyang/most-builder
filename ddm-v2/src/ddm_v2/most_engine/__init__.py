"""most_engine：唯一核心計算引擎（讀 RuleSetData，演算法由黃金測試鎖）。

P0-1：rule_set_data（值物件）+ providers（in-memory/DB adapter）。
P0-2（待補）：sequence calculate（讀 RuleSetData 算 GM/CM）。
"""
from __future__ import annotations

from ddm_v2.most_engine.calculate import (
    CycleResult,
    SequenceError,
    compute_cycle,
    compute_table,
)
from ddm_v2.most_engine.providers import build_from_seed, load_rule_set_from_db
from ddm_v2.most_engine.rule_set_data import RuleSetData, RuleSetIncomplete, build_rule_set_data

__all__ = [
    "RuleSetData",
    "RuleSetIncomplete",
    "build_rule_set_data",
    "build_from_seed",
    "load_rule_set_from_db",
    "compute_cycle",
    "compute_table",
    "CycleResult",
    "SequenceError",
]
