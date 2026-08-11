"""R2b level validation：input_hash 穩定。"""
from __future__ import annotations

from ddm_v2.most_engine import level as level_engine
from ddm_v2.services.v2.level_validation_service import input_hash_for_rows


def test_input_hash_empty_stable():
    assert input_hash_for_rows([]) == input_hash_for_rows([])


def test_input_hash_changes_with_content():
    a = [level_engine.LevelRow(content="A", raw_seconds=1.0, ascription="main", level="1")]
    b = [level_engine.LevelRow(content="B", raw_seconds=1.0, ascription="main", level="1")]
    assert input_hash_for_rows(a) != input_hash_for_rows(b)
    assert len(input_hash_for_rows(a)) == 64
