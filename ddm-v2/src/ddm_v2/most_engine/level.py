"""Level System 驗證引擎（R1–R9）+ 對 LB 輸出合約。

production 版（API 用）；演算法與 scripts/core_logic/level_system_validator.py 一致，
由同一組教學 7 範例 + image5 反例鎖定（不漂移）。依據 level-system-core-logic-spec §8.1。
空值統一以 None 表示（API 友善）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_LABEL_RE = re.compile(r"^(sub|cub)\d+$")
_NB_RE = re.compile(r"^nb\d+$")


@dataclass
class LevelRow:
    content: str
    raw_seconds: float = 1.0
    coefficient: float = 1.0
    number: str | None = None
    number_count: int | None = None
    ascription: str | None = None       # "main" or None
    level: str | None = None            # "1" / "1~2" / "1/3"
    countersignature: str | None = None
    parent_countersignature: str | None = None  # 巢狀外層群組（cub 在 sub 內 = 該 sub）
    order: int | None = None

    @property
    def parent(self) -> str | None:
        p = self.parent_countersignature
        return p.strip() if p and str(p).strip() else None

    @property
    def second(self) -> float:
        return self.raw_seconds * self.coefficient

    @property
    def has_main(self) -> bool:
        return self.ascription == "main" and self.level is not None and str(self.level).strip() != ""

    @property
    def has_counter(self) -> bool:
        return self.countersignature is not None and str(self.countersignature).strip() != ""


@dataclass
class Issue:
    code: str
    row_index: int
    message: str


def _parse_level(level: str) -> tuple[set[int] | None, str | None]:
    s = str(level).strip()
    if s == "":
        return None, "level 為空"
    try:
        if "~" in s:
            a, b = s.split("~", 1)
            lo, hi = int(a), int(b)
            if lo < 1 or hi < 1:
                return None, f"level 範圍須正整數：{s}"
            if lo > hi:
                return None, f"level 範圍起點不可大於終點：{s}"
            return set(range(lo, hi + 1)), None
        if "/" in s:
            vals = {int(x) for x in s.split("/")}
            if any(v < 1 for v in vals):
                return None, f"level 列舉須正整數：{s}"
            return vals, None
        v = int(s)
        if v < 1:
            return None, f"level 須正整數：{s}"
        return {v}, None
    except ValueError:
        return None, f"level 格式非法：{s!r}"


def validate(rows: list[LevelRow]) -> list[Issue]:
    issues: list[Issue] = []

    for i, r in enumerate(rows):
        if r.coefficient is None or r.coefficient <= 0:
            issues.append(Issue("COEF_INVALID", i, f"系數須 >0，收到 {r.coefficient}"))
        if r.ascription not in (None, "", "main"):
            issues.append(Issue("R4_ASCRIPTION", i, f"Ascription 只能 main 或空，收到 {r.ascription!r}"))
        if r.has_counter and not _LABEL_RE.match(str(r.countersignature).strip()):
            issues.append(Issue("R4_COUNTERSIG", i, f"Countersignature 只能 sub*/cub*，收到 {r.countersignature!r}"))

        num = (r.number or "").strip()
        if num:
            if not _NB_RE.match(num):
                issues.append(Issue("NB_FORMAT", i, f"Number 須 nb+數字，收到 {num!r}"))
            if r.number_count is None or r.number_count < 1:
                issues.append(Issue("NB_COUNT_MISSING", i, f"Number={num} 需正整數 Number_Count"))
        elif r.number_count is not None:
            issues.append(Issue("NB_NAME_MISSING", i, f"有 Number_Count={r.number_count} 卻無 Number"))

        order_val = r.order
        if order_val is not None and order_val < 1:
            issues.append(Issue("ORDER_INVALID", i, f"order 須正整數，收到 {order_val}"))

        if r.has_counter:
            if order_val is None:
                issues.append(Issue("ORDER_MISSING", i, f"群組 {r.countersignature} 列必須有 order"))
            elif order_val == 1 and not r.has_main:
                issues.append(Issue("R1_HEAD_NO_MAIN", i, f"群組 {r.countersignature} 頭列(order1)須帶 main+Level"))
            elif order_val and order_val >= 2 and r.has_main:
                issues.append(Issue("R2_REDEFINE", i, f"群組成員(order{order_val}) 不可自帶 main+Level（重複定義歸屬）"))
        elif not r.has_main:
            issues.append(Issue("R3_ORPHAN", i, "歸屬不明：非 main 獨立列、也無 Countersignature"))

        if r.level is not None and str(r.level).strip() != "":
            _vals, errmsg = _parse_level(r.level)
            if errmsg:
                issues.append(Issue("R7_LEVEL_FORMAT", i, errmsg))

    # R8 群組良構
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        if r.has_counter:
            groups.setdefault(str(r.countersignature).strip(), []).append(i)
    for label, idxs in groups.items():
        orders = [rows[i].order for i in idxs if rows[i].order is not None]
        if not orders:
            continue
        if len(orders) != len(set(orders)):
            issues.append(Issue("R8_DUP_ORDER", idxs[0], f"群組 {label} order 重複：{sorted(orders)}"))
        if sorted(orders) != list(range(1, len(orders) + 1)):
            issues.append(Issue("R8_ORDER_GAP", idxs[0], f"群組 {label} order 須 1..{len(orders)} 連續，收到 {sorted(orders)}"))
        heads = [i for i in idxs if rows[i].order == 1]
        if len(heads) > 1:
            issues.append(Issue("R8_MULTI_HEAD", heads[1], f"群組 {label} 多個頭列(order1)"))

    # R9 巢狀良構：深度 main→sub→cub，只允許 sub⊃cub
    for label, idxs in groups.items():
        parents = {rows[i].parent for i in idxs}
        if len(parents) > 1:
            issues.append(Issue("R9_PARENT_INCONSISTENT", idxs[0], f"群組 {label} 各列的 parent 不一致：{sorted(str(p) for p in parents)}"))
            continue
        parent = next(iter(parents))
        if parent is None:
            continue
        if label.startswith("sub"):
            issues.append(Issue("R9_SUB_NESTED", idxs[0], f"sub「{label}」不可被巢狀（深度上限 main→sub→cub，sub 直屬 main）"))
        elif not parent.startswith("sub"):
            issues.append(Issue("R9_NEST_ILLEGAL", idxs[0], f"只允許 sub⊃cub；cub「{label}」的 parent「{parent}」不是 sub"))
        elif parent not in groups:
            issues.append(Issue("R9_PARENT_MISSING", idxs[0], f"cub「{label}」的 parent「{parent}」不存在"))

    # R6 nb 不可與 cub 矛盾
    for label, idxs in groups.items():
        if not label.startswith("cub"):
            continue
        nb_carriers: dict[str, list[int]] = {}
        for i in idxs:
            num = (rows[i].number or "").strip()
            if num:
                nb_carriers.setdefault(num, []).append(i)
        for nb, carriers in nb_carriers.items():
            limits = {rows[i].number_count for i in carriers if rows[i].number_count}
            limit = next(iter(limits)) if len(limits) == 1 else 0
            if len(carriers) > (limit or 0):
                issues.append(Issue("R6_NB_VS_CUB", carriers[0], f"cub「{label}」要同站，但 {len(carriers)} 成員帶 {nb}(上限 {limit}) 會被逼分站 → 矛盾"))

    # nb count 一致
    nb_counts: dict[str, set[int]] = {}
    for r in rows:
        num = (r.number or "").strip()
        if num and _NB_RE.match(num) and r.number_count:
            nb_counts.setdefault(num, set()).add(r.number_count)
    for nb, cset in nb_counts.items():
        if len(cset) > 1:
            issues.append(Issue("NB_COUNT_INCONSISTENT", -1, f"nb {nb} 的 Number_Count 不一致：{sorted(cset)}"))

    # R7 主序非遞減（min level）
    prev_min = None
    prev_row = None
    for i, r in enumerate(rows):
        if not r.has_main:
            continue
        vals, errmsg = _parse_level(r.level or "")
        if errmsg or not vals:
            continue
        cur_min = min(vals)
        if prev_min is not None and cur_min < prev_min:
            issues.append(Issue("R7_NON_DECREASING", i, f"主序倒退：列{i + 1} level({cur_min}) < 前列{(prev_row or 0) + 1}({prev_min})"))
        prev_min, prev_row = cur_min, i

    return issues


def build_output(rows: list[LevelRow]) -> dict[str, Any]:
    """對 Line Balance 的完整約束模型（spec §9）。僅在 validate() 無誤時呼叫。

    設計目的：把 LB 演算法要的「限制 + 自由度」一次交清，**不塌縮**變動層級：
    - 每個 node 帶 `levels`（允許主序集合）/`level_min`/`level_max`/`variable`
      → `1~2`/`1/3` 的「可挪動」自由度完整保留，LB 自行在集合內擇優。
    - `groups`：sub（可移動·內部定序）/ cub（同站不可拆），含 `parent`（巢狀）、ordered `members`。
    - `number_constraints`：nb 分站上限（不可同站）。
    - `precedence_edges`：以 level_min 推得的「保守先後」便利視圖（真正自由度看 node.levels）。
    """
    nodes: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    number_constraints: dict[str, dict[str, Any]] = {}
    main_seq: list[tuple[int, str]] = []

    # 1) 群組骨架（型別/巢狀/排序成員）
    for r in rows:
        if r.has_counter:
            lab = str(r.countersignature).strip()
            is_cub = lab.startswith("cub")
            g = groups.setdefault(lab, {"label": lab, "type": "cub" if is_cub else "sub",
                                        "parent": None, "same_station": is_cub, "movable": not is_cub,
                                        "_members": []})
            if r.parent and not g["parent"]:
                g["parent"] = r.parent
            g["_members"].append((r.order or 0, r.content))
    for g in groups.values():
        g["members"] = [c for _, c in sorted(g["_members"], key=lambda x: x[0])]
        del g["_members"]

    # 2) 節點（含自由度集合）
    for r in rows:
        vals = None
        if r.level is not None and str(r.level).strip() != "":
            vals, _ = _parse_level(r.level)
        levels = sorted(vals) if vals else []
        nodes.append({
            "content": r.content, "second": round(r.second, 4),
            "ascription": r.ascription, "level": r.level,
            "levels": levels, "level_min": (levels[0] if levels else None),
            "level_max": (levels[-1] if levels else None), "variable": len(levels) > 1,
            "countersignature": r.countersignature, "parent_countersignature": r.parent,
            "order": r.order, "number": r.number, "number_count": r.number_count,
        })
        if (r.number or "").strip():
            number_constraints.setdefault(r.number, {"kind": "max_per_station", "limit": r.number_count, "members": []})["members"].append(r.content)
        if r.has_main and levels:
            main_seq.append((levels[0], r.content))

    main_seq.sort(key=lambda x: x[0])
    edges = [{"from": a[1], "to": b[1]} for a, b in zip(main_seq, main_seq[1:]) if a[0] < b[0]]
    cub_groups = {lab: g["members"] for lab, g in groups.items() if g["type"] == "cub"}
    sub_groups = {lab: g["members"] for lab, g in groups.items() if g["type"] == "sub"}
    group_parents = {lab: g["parent"] for lab, g in groups.items() if g["parent"]}
    return {"nodes": nodes, "precedence_edges": edges,
            "groups": list(groups.values()),
            "cub_groups": cub_groups, "sub_groups": sub_groups,
            "group_parents": group_parents, "number_constraints": number_constraints}
