"""Gold plan 迴歸（spec §14.3）：tests/gold/wi_plans → link/compile/engine。"""
from __future__ import annotations

from pathlib import Path

import pytest

from ddm_v2.nlp.gold_eval import evaluate_gold_case, load_gold_cases

GOLD_DIR = Path(__file__).resolve().parents[1] / "gold" / "wi_plans"


def _case_ids() -> list[str]:
    return [p.name for p, _ in load_gold_cases(GOLD_DIR)]


@pytest.mark.asyncio
@pytest.mark.parametrize("fname", _case_ids())
async def test_gold_plan_case(fname: str):
    data = next(d for p, d in load_gold_cases(GOLD_DIR) if p.name == fname)
    assert data.get("gold_schema_version") == "wi-gold-v1"
    result = await evaluate_gold_case(data)
    assert result.ok, f"{result.case_id}: {result.errors}"


@pytest.mark.asyncio
async def test_gold_suite_has_seed_cases():
    names = {p.name for p, _ in load_gold_cases(GOLD_DIR)}
    assert "g01_acquire_dimm.json" in names
    assert "g02_screwdriver_screw_x2.json" in names
    assert "g05_composite_unknown.json" in names
