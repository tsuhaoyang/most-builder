#!/usr/bin/env python3
"""Level System — 核心邏輯驗證器（reference implementation + self-tests）.

權威依據：docs/core-logic/level-system-core-logic-spec.md (v1.x)
         （來源＝MOST系統邏輯1205.xlsx › 工作表2「Level System 教學檔案」）

職責：Level System 是 MOST 與 Line Balance 之間的邏輯層；本驗證器**只驗填寫邏輯
是否合法**（讓 IE 填寫不出錯），不做分站（分站＝LB project）。

實作 spec §8.1 規則 R1–R9，並把 IE 易犯錯誤（image5 三案例）全部封掉：
  R1 群組頭列/獨立列須帶 main+Level
  R2 群組成員(order≥2) 不可自帶 main+Level（重複定義歸屬）
  R3 非 main 且無 Countersignature = 歸屬不明（孤兒）
  R4 Countersignature 只能 sub*/cub*；main 永不當歸屬/從屬
  R5 sub=可移動群組 / cub=同站固定（結構語意）
  R6 nb 不可與 cub 矛盾（同 cub 成員被 nb 逼分站）
  R7 Level 為正整數或 ~範圍 / 列舉；可跳號；沿表非遞減（min level 為鍵）
  R8 每個 sub/cub/nb 標籤唯一且群組良構（order=1..k、單一頭列）
  R9 深度巢狀 main⊃sub⊃cub（>2 巢狀編碼待 IE 確認 → 本檔 best-effort）

無第三方相依，可直接 `python level_system_validator.py` 跑全部測試。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Row:
    content: str
    raw_seconds: float = 1.0
    coefficient: float = 1.0
    number: str = ""              # nb 標籤，如 "nb1"
    number_count: Any = ""        # 每站上限
    ascription: str = ""          # "main" 或 ""
    level: str = ""               # "1" / "1~2" / "1/3" / ""
    countersignature: str = ""    # 子群組標籤 sub*/cub*，或 ""
    order: Any = ""               # 群組內順序（1=頭列）

    @property
    def second(self) -> float:
        return self.raw_seconds * self.coefficient

    @property
    def has_main(self) -> bool:
        return self.ascription == "main" and str(self.level).strip() != ""

    @property
    def has_counter(self) -> bool:
        return str(self.countersignature).strip() != ""


@dataclass
class Issue:
    code: str
    row_index: int          # 0-based；-1 表整表層級
    message: str

    def __str__(self) -> str:
        loc = "整表" if self.row_index < 0 else f"列{self.row_index + 1}"
        return f"[{self.code}] {loc}: {self.message}"


_LABEL_RE = re.compile(r"^(sub|cub)\d+$")
_NB_RE = re.compile(r"^nb\d+$")


def _parse_level(level: str) -> tuple[set[int] | None, str | None]:
    """回傳 (允許的正整數集合, 錯誤訊息)。支援 'N' / 'a~b' / 'a/b/c'。"""
    s = str(level).strip()
    if s == "":
        return None, "level 為空"
    try:
        if "~" in s:
            a, b = s.split("~", 1)
            lo, hi = int(a), int(b)
            if lo < 1 or hi < 1:
                return None, f"level 範圍須為正整數：{s}"
            if lo > hi:
                return None, f"level 範圍起點不可大於終點：{s}"
            return set(range(lo, hi + 1)), None
        if "/" in s:
            vals = {int(x) for x in s.split("/")}
            if any(v < 1 for v in vals):
                return None, f"level 列舉須為正整數：{s}"
            return vals, None
        v = int(s)
        if v < 1:
            return None, f"level 須為正整數：{s}"
        return {v}, None
    except ValueError:
        return None, f"level 格式非法：{s!r}"


def _is_pos_int(x: Any) -> bool:
    try:
        return int(str(x).strip()) >= 1
    except (ValueError, TypeError):
        return False


def validate(rows: list[Row]) -> list[Issue]:
    """回傳所有違規 Issue；空 list = 合法。"""
    issues: list[Issue] = []

    # ── 逐列基本欄位 + R1/R2/R3/R4 + Number/Count 配對 ──
    for i, r in enumerate(rows):
        # 寬放係數
        if r.coefficient is None or r.coefficient <= 0:
            issues.append(Issue("COEF_INVALID", i, f"系數須 >0，收到 {r.coefficient}"))

        # R4：欄位用字合法性
        if r.ascription not in ("", "main"):
            issues.append(Issue("R4_ASCRIPTION", i, f"Ascription 只能是 main 或空，收到 {r.ascription!r}"))
        if r.has_counter and not _LABEL_RE.match(str(r.countersignature).strip()):
            issues.append(Issue("R4_COUNTERSIG", i,
                                 f"Countersignature 只能是 sub*/cub*（main 永不當歸屬），收到 {r.countersignature!r}"))

        # Number / Number_Count 配對
        num = str(r.number).strip()
        cnt = str(r.number_count).strip()
        if num:
            if not _NB_RE.match(num):
                issues.append(Issue("NB_FORMAT", i, f"Number 須為 nb+數字，收到 {num!r}"))
            if not _is_pos_int(cnt):
                issues.append(Issue("NB_COUNT_MISSING", i, f"填了 Number={num} 必須有正整數 Number_Count，收到 {cnt!r}"))
        elif cnt:
            issues.append(Issue("NB_NAME_MISSING", i, f"填了 Number_Count={cnt} 卻無 Number 標籤"))

        order_is_member = False
        order_val = None
        if str(r.order).strip() != "":
            if not _is_pos_int(r.order):
                issues.append(Issue("ORDER_INVALID", i, f"order 須為正整數，收到 {r.order!r}"))
            else:
                order_val = int(str(r.order).strip())
                order_is_member = order_val >= 2

        if r.has_counter:
            # 群組列：必須有 order
            if order_val is None:
                issues.append(Issue("ORDER_MISSING", i, f"屬於群組 {r.countersignature} 的列必須有 order"))
            # R1/R2：頭列(order1)須帶 main；成員(order≥2)不可帶 main
            if order_val == 1 and not r.has_main:
                issues.append(Issue("R1_HEAD_NO_MAIN", i, f"群組 {r.countersignature} 頭列(order1)須帶 main+Level"))
            if order_is_member and r.has_main:
                issues.append(Issue("R2_REDEFINE", i,
                                    f"群組成員(order{order_val}) 不可自帶 main+Level（重複定義歸屬）—應繼承頭列"))
        else:
            # 非群組列：須為獨立 main 列，否則孤兒
            if not r.has_main:
                issues.append(Issue("R3_ORPHAN", i, "歸屬不明：既非 main 獨立列、也無 Countersignature"))

        # R7：level 格式（僅檢查帶 level 的列）
        if str(r.level).strip() != "":
            _vals, err = _parse_level(r.level)
            if err:
                issues.append(Issue("R7_LEVEL_FORMAT", i, err))

    # ── R8：群組良構（每個 sub/cub 標籤）──
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        if r.has_counter:
            groups.setdefault(str(r.countersignature).strip(), []).append(i)
    for label, idxs in groups.items():
        orders = []
        for i in idxs:
            try:
                orders.append(int(str(rows[i].order).strip()))
            except (ValueError, TypeError):
                pass  # 已在上面報 ORDER_*
        if not orders:
            continue
        if len(orders) != len(set(orders)):
            issues.append(Issue("R8_DUP_ORDER", idxs[0], f"群組 {label} 內 order 重複：{sorted(orders)}"))
        if sorted(orders) != list(range(1, len(orders) + 1)):
            issues.append(Issue("R8_ORDER_GAP", idxs[0],
                                f"群組 {label} order 須為 1..{len(orders)} 連續，收到 {sorted(orders)}"))
        heads = [i for i in idxs if str(rows[i].order).strip() == "1"]
        if len(heads) > 1:
            issues.append(Issue("R8_MULTI_HEAD", heads[1], f"群組 {label} 有多個頭列(order1)：{[h + 1 for h in heads]}"))

    # ── R6：nb 不可與 cub 矛盾 ──
    for label, idxs in groups.items():
        if not label.startswith("cub"):
            continue
        # 該 cub 群組成員若帶同一 nb，且 count < 成員中帶此 nb 的數量 → 衝突
        nb_in_cub: dict[str, list[int]] = {}
        for i in idxs:
            num = str(rows[i].number).strip()
            if num:
                nb_in_cub.setdefault(num, []).append(i)
        for nb, carriers in nb_in_cub.items():
            counts = {str(rows[i].number_count).strip() for i in carriers}
            cnt = next(iter(counts)) if len(counts) == 1 and _is_pos_int(next(iter(counts))) else None
            limit = int(cnt) if cnt else 0
            if len(carriers) > limit:
                issues.append(Issue("R6_NB_VS_CUB", carriers[0],
                                    f"cub「{label}」要求同站，但其 {len(carriers)} 個成員帶 {nb}(上限 {limit}) 會被逼分站 → 矛盾"))

    # ── R8(nb)：同一 nb 標籤 count 一致 ──
    nb_counts: dict[str, set[str]] = {}
    for i, r in enumerate(rows):
        num = str(r.number).strip()
        if num and _NB_RE.match(num):
            nb_counts.setdefault(num, set()).add(str(r.number_count).strip())
    for nb, cset in nb_counts.items():
        valid = {c for c in cset if _is_pos_int(c)}
        if len(valid) > 1:
            issues.append(Issue("NB_COUNT_INCONSISTENT", -1, f"nb 標籤 {nb} 的 Number_Count 不一致：{sorted(valid)}"))

    # ── R7：main 列 min-level 沿表非遞減（成員繼承、跳號允許）──
    prev_min = None
    prev_row = None
    for i, r in enumerate(rows):
        if not r.has_main:
            continue
        vals, err = _parse_level(r.level)
        if err or not vals:
            continue
        cur_min = min(vals)
        if prev_min is not None and cur_min < prev_min:
            issues.append(Issue("R7_NON_DECREASING", i,
                                f"主序倒退：列{i + 1} 的 level({cur_min}) 小於前一 main 列{prev_row + 1}({prev_min})"))
        prev_min = cur_min
        prev_row = i

    return issues


def build_output(rows: list[Row]) -> dict[str, Any]:
    """對 Line Balance 的輸出合約（spec §9）；僅在 validate() 無誤時呼叫。"""
    nodes = []
    precedence: list[dict[str, int]] = []
    cub_groups: dict[str, list[str]] = {}
    number_constraints: dict[str, dict[str, Any]] = {}
    main_seq_of: list[tuple[int, str]] = []  # (min_level, content)

    for r in rows:
        nodes.append({
            "content": r.content,
            "second": round(r.second, 4),
            "ascription": r.ascription,
            "level": r.level,
            "countersignature": r.countersignature,
            "order": r.order,
            "number": r.number,
            "number_count": r.number_count,
        })
        if r.has_counter and str(r.countersignature).startswith("cub"):
            cub_groups.setdefault(str(r.countersignature), []).append(r.content)
        if str(r.number).strip():
            number_constraints.setdefault(str(r.number), {"limit": r.number_count, "members": []})["members"].append(r.content)
        if r.has_main:
            vals, _ = _parse_level(r.level)
            if vals:
                main_seq_of.append((min(vals), r.content))

    main_seq_of.sort(key=lambda x: x[0])
    for a, b in zip(main_seq_of, main_seq_of[1:]):
        if a[0] < b[0]:
            precedence.append({"from": a[1], "to": b[1]})
    return {"nodes": nodes, "precedence_edges": precedence,
            "cub_groups": cub_groups, "number_constraints": number_constraints}


# ─────────────────────────── 測試 ───────────────────────────
def main_row(content, level, **kw):
    return Row(content=content, ascription="main", level=str(level), **kw)


def head_row(content, level, counter, **kw):
    return Row(content=content, ascription="main", level=str(level),
               countersignature=counter, order=1, **kw)


def member_row(content, counter, order, **kw):
    return Row(content=content, countersignature=counter, order=order, **kw)


def _run_tests() -> int:
    passed = failed = 0

    def ok(name, rows, expect_valid=True):
        nonlocal passed, failed
        issues = validate(rows)
        valid = len(issues) == 0
        if valid == expect_valid:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}  issues={[str(x) for x in issues]}")

    def err(name, rows, code):
        nonlocal passed, failed
        codes = [x.code for x in validate(rows)]
        if code in codes:
            passed += 1
            print(f"  ✅ {name}（正確擋下 {code}）")
        else:
            failed += 1
            print(f"  ❌ {name} 期望 {code}，實得 {codes}")

    print("\n── A. 七個教學範例（spec §7，皆應合法）──")
    # Ex1：A~J 純序列
    ok("Ex1 純序列 main 1..10", [main_row(c, i + 1) for i, c in enumerate("ABCDEFGHIJ")])
    # Ex2：A,B,C 同層並行
    ok("Ex2 ABC 同層(level1) 並行", [main_row("A", 1), main_row("B", 1), main_row("C", 1)] +
       [main_row(c, i + 2) for i, c in enumerate("DEFGHIJ")])
    # Ex3：D,E,F 用 sub1 給獨立順序
    ok("Ex3 sub1 群組(D,E,F)", [main_row("A", 1), main_row("B", 2), main_row("C", 3),
                                head_row("D", 4, "sub1"), member_row("E", "sub1", 2), member_row("F", "sub1", 3),
                                main_row("G", 5), main_row("H", 6), main_row("I", 7), main_row("J", 8)])
    # Ex4：改 cub1（不可分割）
    ok("Ex4 cub1 群組(D,E,F)", [main_row("A", 1), main_row("B", 2), main_row("C", 3),
                                head_row("D", 4, "cub1"), member_row("E", "cub1", 2), member_row("F", "cub1", 3),
                                main_row("G", 5), main_row("H", 6), main_row("I", 7), main_row("J", 8)])
    # Ex5：A 跳躍 1~2；B,C cub1@1；D,E,F sub1@2
    ok("Ex5 變動層級 A=1~2 + cub1 + sub1", [
        main_row("A", "1~2"),
        head_row("B", 1, "cub1"), member_row("C", "cub1", 2),
        head_row("D", 2, "sub1"), member_row("E", "sub1", 2), member_row("F", "sub1", 3),
        main_row("G", 3), main_row("H", 4), main_row("I", 5), main_row("J", 6)])
    # Ex6：nb1 逼 G、H 不同站
    ok("Ex6 nb1 count1 逼 G/H 分站", [
        main_row("A", 1), main_row("B", 2), main_row("C", 3), main_row("D", 4),
        main_row("E", 5), main_row("F", 6),
        main_row("G", 7, number="nb1", number_count=1),
        main_row("H", 8, number="nb1", number_count=1),
        main_row("I", 9), main_row("J", 10)])
    # 跳號 + 列舉
    ok("變動層級列舉 1/3 合法", [main_row("A", "1/3"), main_row("B", 4)])
    ok("跳號填寫 1,2,5 合法", [main_row("A", 1), main_row("B", 2), main_row("C", 5)])

    print("\n── B. image5 三個錯誤案例（IE 易犯，應擋下）──")
    # 「歸屬不明」：C 是成員位卻無 countersignature 也無 main
    err("歸屬不明(C)", [head_row("B", 2, "sub1"),
                       Row(content="C", order=2)], "R3_ORPHAN")
    # 「sub2 重複定義歸屬」：G 成員(order3) 卻自帶 main L5
    err("sub2 重複定義歸屬(G)", [head_row("E", 4, "sub2"), member_row("F", "sub2", 2),
                               Row(content="G", ascription="main", level="5", countersignature="sub2", order=3)],
        "R2_REDEFINE")
    # 「cub 內又加分割」：cub1 兩成員都 nb1 count1 → 同站與分站矛盾
    err("cub 內加 nb 分割矛盾(H/I)", [head_row("H", 3, "cub1", number="nb1", number_count=1),
                                    member_row("I", "cub1", 2, number="nb1", number_count=1)], "R6_NB_VS_CUB")

    print("\n── C. R1–R9 其他 edge cases ──")
    err("R1 頭列無 main", [Row(content="A", countersignature="sub1", order=1)], "R1_HEAD_NO_MAIN")
    err("R4 Ascription 非法", [Row(content="A", ascription="sub1", level="1")], "R4_ASCRIPTION")
    err("R4 main 當 Countersignature", [head_row("A", 1, "main1")], "R4_COUNTERSIG")
    err("R7 level=0 非法", [main_row("A", 0)], "R7_LEVEL_FORMAT")
    err("R7 level=abc 非法", [main_row("A", "abc")], "R7_LEVEL_FORMAT")
    err("R7 範圍反向 2~1", [main_row("A", "2~1")], "R7_LEVEL_FORMAT")
    err("R7 主序倒退", [main_row("A", 3), main_row("B", 1)], "R7_NON_DECREASING")
    err("R8 order 跳號", [head_row("A", 1, "sub1"), member_row("B", "sub1", 3)], "R8_ORDER_GAP")
    err("R8 order 重複", [head_row("A", 1, "sub1"), Row(content="B", countersignature="sub1", order=1)], "R8_MULTI_HEAD")
    err("Number 無 Count", [main_row("A", 1, number="nb1")], "NB_COUNT_MISSING")
    err("Count 無 Number", [main_row("A", 1, number_count=2)], "NB_NAME_MISSING")
    err("nb count 不一致", [main_row("A", 1, number="nb1", number_count=1),
                          main_row("B", 2, number="nb1", number_count=2)], "NB_COUNT_INCONSISTENT")
    err("系數 0 非法", [main_row("A", 1, coefficient=0)], "COEF_INVALID")
    err("群組列缺 order", [head_row("A", 1, "sub1"), Row(content="B", countersignature="sub1")], "ORDER_MISSING")

    print("\n── D. 輸出合約（對 LB）──")
    rows = [main_row("A", 1), head_row("B", 2, "cub1"), member_row("C", "cub1", 2), main_row("D", 3)]
    out = build_output(rows)
    ok2 = (out["cub_groups"] == {"cub1": ["B", "C"]}
           and len(out["precedence_edges"]) == 2
           and abs(out["nodes"][0]["second"] - 1.0) < 1e-9)
    if ok2:
        passed += 1
        print("  ✅ build_output：cub_groups / precedence / second 正確")
    else:
        failed += 1
        print(f"  ❌ build_output 不符：{out}")

    print(f"\n{'='*52}\n結果：{passed} passed, {failed} failed\n{'='*52}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_run_tests())
