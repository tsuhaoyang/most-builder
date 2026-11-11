"""normalize_with_map / quantities 單元測試（L0）。"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.normalization import normalize, normalize_with_map
from ddm_v2.nlp.quantities import extract_counts, extract_distances

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "hello",
        "  hello   world  ",
        "Ａ１２３",
        "測试机器",
        "取料 SMT 壓合",
        "拿起DIMM，插入插座",
        "伸手 30cm 拿取",
    ],
)
def test_normalize_with_map_equals_normalize(raw: str):
    norm, offset_map = normalize_with_map(raw)
    assert norm == normalize(raw)
    assert len(offset_map) == len(norm)
    for i in range(1, len(offset_map)):
        assert offset_map[i] >= offset_map[i - 1]
    if raw and norm:
        assert 0 <= offset_map[0] < len(raw)
        assert offset_map[-1] < len(raw)


def test_extract_distances_mm_and_inch():
    dists = extract_distances("移動 20mm 再推 1吋")
    assert len(dists) >= 2
    mm = next(d for d in dists if d.unit.lower() == "mm")
    assert mm.value == pytest.approx(20.0)
    assert mm.normalized_cm == pytest.approx(2.0)
    inch = next(d for d in dists if "吋" in d.unit or d.unit.lower() == "inch")
    assert inch.normalized_cm == pytest.approx(2.54)


def test_extract_counts_zh_and_x():
    counts = extract_counts("鎖附兩顆螺絲 x2")
    values = {c.value for c in counts}
    assert 2.0 in values
