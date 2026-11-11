"""WI 數值／數量抽取（距離、中文數量）。

規則（spec §6.2）：保留原始單位與原值；cm 正規化值另存，band/ladder 留給 engine。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

UNIT_TO_CM: dict[str, float] = {
    "cm": 1.0,
    "公分": 1.0,
    "mm": 0.1,
    "毫米": 0.1,
    "吋": 2.54,
    "英寸": 2.54,
    "inch": 2.54,
}

ZH_NUM: dict[str, int] = {
    "一": 1,
    "兩": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_DIST_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>cm|公分|mm|毫米|吋|英寸|inch)",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"(?P<zh>[一二兩二三四五六七八九十])\s*(?P<unit>顆|件|個|次)"
    r"|(?P<num>\d+)\s*(?P<unit2>顆|件|個|次)"
    r"|(?:[x×*]\s*(?P<xnum>\d+))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedQuantity:
    value: float
    unit: str
    normalized_cm: float | None
    start: int
    end: int
    text: str
    kind: str  # "distance" | "count"


def extract_distances(norm: str) -> list[ExtractedQuantity]:
    out: list[ExtractedQuantity] = []
    for m in _DIST_RE.finditer(norm):
        raw = float(m.group("value"))
        unit = m.group("unit").lower()
        # 公分／毫米保持原字；ascii unit 已小寫
        unit_key = m.group("unit")
        factor = UNIT_TO_CM.get(unit, UNIT_TO_CM.get(unit_key, 1.0))
        out.append(
            ExtractedQuantity(
                value=raw,
                unit=unit_key,
                normalized_cm=raw * factor,
                start=m.start(),
                end=m.end(),
                text=m.group(0),
                kind="distance",
            )
        )
    return out


def extract_counts(norm: str) -> list[ExtractedQuantity]:
    out: list[ExtractedQuantity] = []
    for m in _COUNT_RE.finditer(norm):
        if m.group("zh"):
            value = float(ZH_NUM[m.group("zh")])
            unit = m.group("unit")
        elif m.group("num"):
            value = float(m.group("num"))
            unit = m.group("unit2")
        else:
            value = float(m.group("xnum"))
            unit = "count"
        out.append(
            ExtractedQuantity(
                value=value,
                unit=unit,
                normalized_cm=None,
                start=m.start(),
                end=m.end(),
                text=m.group(0),
                kind="count",
            )
        )
    return out
