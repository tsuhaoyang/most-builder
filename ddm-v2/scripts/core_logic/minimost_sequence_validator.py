#!/usr/bin/env python3
"""MiniMOST Sequence Model — 核心邏輯驗證器（reference implementation + self-tests）.

權威依據：docs/core-logic/minimost-sequence-model-core-logic-spec.md ＋ ADR-014
（值權威＝docs/v3/reference/minimost_ai_dictionary_v1.json，v3 IE 認證字典）。
範圍：MiniMOST only，GM(一般移動 A B G A B P A) / CM(控制移動 A B G M X I A)。

設計目標：
  * 本檔是「規格的可執行版本」——任何 MiniMOST 計算實作都應對得上這裡的結果。
  * 把 edge case 全部封掉：非法 slot、超過 2 個附加、插入⊥卡合、CM 不可有 P、
    GM 不可有 M/X/I、距離邊界、超出值表、負值、未知選項… 一律 SequenceError 明確報錯。
  * 無第三方相依，可直接 `python minimost_sequence_validator.py` 跑全部測試。

已確認決策（V2 口徑，ADR-014；V1 舊口徑之差異見 impl-02 E8 過帳表）：
  Q1 合計 = (Σ slot index) × system_tmu_multiplier（不乘 10）；1 TMU = 0.036 秒。
  Q2 B 採 1205 值 {0,10,32,42} 且必須計入。
  X  = half-up 3 位（sec/0.036），固定類 0.216→6（取代舊 ceil 裁決）。
  A  = max(伸手, 手度, 腳步) 三分量；A3 返回格僅計伸手（E1）。
  M  階梯門檻＝cm 正確值 2.5/10/25/45/75、無 overflow（C1）；腳步獨立帶（C2）。
  G  無修飾 gating（選項即完整語意）。P 對準直接 +8；插入⊥卡合。
  slot 級 repeat（G/P/X/I 整格；M 僅乘動詞再 max）；人工覆寫留痕（E7）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

TMU_TO_SEC = 0.036
REPEAT_MAX = 99


class SequenceError(ValueError):
    """帶錯誤碼的驗證錯誤。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


# ─────────────────────────── 查表常數（V2＝v3 IE 認證字典） ───────────────────────────
# (upper_bound_inclusive, index)；value<=0 視為無此分量。最後一段為 (inf, idx)＝overflow。
A_REACH_BANDS = [(2.5, 0), (5, 1), (10, 3), (20, 6), (35, 10), (60, 16), (math.inf, 24)]
A_TWIST_BANDS = [(30, 0), (60, 1), (120, 3), (180, 6)]
A_FOOT_BANDS = [(20, 6), (30, 10), (45, 16), (65, 24), (math.inf, 32)]

# B 身體動作（1205，已確認）：index 值即為合法集合。
B_PERMITTED = {0, 10, 32, 42}

# G 取得（V2：無 gating——選項即完整語意）：id -> (label, base_tmu)
G_OPTIONS: dict[str, tuple[str, int]] = {
    "g_tap": ("輕按", 3), "g_touch": ("接觸", 3), "g_pat": ("輕拍", 3),
    "g_grasp": ("抓握", 6), "g_grab": ("抓取", 6), "g_regrasp": ("重新抓握", 6),
    "g_handchange": ("換手(轉移)", 10), "g_pick_sel": ("拿取(選取)", 10),
    "g_pick_small": ("拿取(選取-小)", 16), "g_pullout": ("拔出(分離)", 16),
    "g_pick_collect": ("拿取(收集)", 24),
}

# P 放置基底：id -> (label, direction, base_tmu)
P_BASES: dict[str, tuple[str, str | None, int]] = {
    "p_toss": ("丟", None, 3), "p_hold": ("保持住", None, 3),
    "p_place_none": ("放(無方向)", "none", 6), "p_place_multi": ("放(多種方向)", "multi", 10),
    "p_place_single": ("放(一種方向)", "single", 16),
    "p_asm_multi": ("組(多種方向)", "multi", 10), "p_asm_single": ("組(一種方向)", "single", 16),
}
# P 附加（V2：a_align 選項自含精度語意，直接 +8）：id -> (label, delta)
P_ADDONS: dict[str, tuple[str, int]] = {
    "a_align": ("對準(精度<4mm)", 8), "a_insert": ("插入", 8), "a_hard": ("較難處理", 8),
    "a_snap": ("卡合", 16), "a_press": ("施加壓力", 16),
}
P_ADDON_MAX = 2

# M 距離階梯（C1 定案：吋(cm) 正確值；無 overflow → 超界報錯）
M_LADDER = [(2.5, 3), (10, 6), (25, 10), (45, 16), (75, 24)]
# M 腳步獨立帶（C2 定案；含 overflow 42）
M_FOOT = [(25, 10), (40, 16), (55, 24), (75, 32), (math.inf, 42)]
# M 動詞：id -> pricing_kind
M_VERBS: dict[str, str] = {
    "m_btn": "fixed3", "m_screw": "fixed3",
    "m_li": "ladder", "m_through": "ladder", "m_push": "ladder",
    "m_pull": "ladder", "m_attach": "ladder", "m_remove": "ladder",
    "m_teartape": "ladder", "m_fold": "ladder", "m_wipe": "ladder", "m_tearopen": "ladder",
    "m_rotate": "rotate", "m_hand": "hand", "m_foot": "foot",
}
X_MODES = {"zero", "seconds", "fixed216"}
I_PERMITTED = {0, 6, 10, 16, 24, 32}  # V2 八檔（正常 6/6/10/16＋視線外 16/16/24/32）＋i_none

GM_LETTERS = ["A", "B", "G", "A", "B", "P", "A"]
CM_LETTERS = ["A", "B", "G", "M", "X", "I", "A"]


# ─────────────────────────── slot 計算 ───────────────────────────
def _band_index(value: float, bands: list[tuple[float, int]]) -> int | None:
    """value<=0 -> None（無此分量）；否則回傳第一個 value<=upper 的 index。"""
    if value is None:
        return None
    if value < 0:
        raise SequenceError("A_NEGATIVE", f"距離/角度不可為負：{value}")
    if value == 0:
        return None
    for upper, idx in bands:
        if value <= upper:
            return idx
    return bands[-1][1]


def _repeat(data: dict[str, Any] | None) -> int:
    """E4：slot 級重複次數。預設 1；非整數/超界 → REPEAT_INVALID。"""
    rc = (data or {}).get("repeat_count")
    if rc is None:
        return 1
    if isinstance(rc, bool) or not isinstance(rc, (int, float)) or float(rc) != int(rc) or not (1 <= int(rc) <= REPEAT_MAX):
        raise SequenceError("REPEAT_INVALID", f"repeat_count 須為 1..{REPEAT_MAX} 的整數，收到 {rc!r}")
    return int(rc)


def a_slot_tmu(reach_cm: float = 0, twist_deg: float = 0, foot_cm: float = 0) -> int:
    """A 格 = max(伸手, 手度, 腳步) 三分量 index；皆無 -> 0。"""
    parts = [
        _band_index(reach_cm, A_REACH_BANDS),
        _band_index(twist_deg, A_TWIST_BANDS),
        _band_index(foot_cm, A_FOOT_BANDS),
    ]
    present = [p for p in parts if p is not None]
    return max(present) if present else 0


def a_return_tmu(reach_cm: float = 0, twist_deg: float = 0, foot_cm: float = 0) -> int:
    """E1：A3 返回格僅計伸手；twist/foot 非零 → A_RETURN_COMPONENT（零值容忍）。"""
    if twist_deg:
        raise SequenceError("A_RETURN_COMPONENT", f"返回格僅計伸手，不可含 twist_deg={twist_deg}")
    if foot_cm:
        raise SequenceError("A_RETURN_COMPONENT", f"返回格僅計伸手，不可含 foot_cm={foot_cm}")
    idx = _band_index(reach_cm, A_REACH_BANDS)
    return idx if idx is not None else 0


def b_slot_tmu(b_index: int = 0) -> int:
    if b_index not in B_PERMITTED:
        raise SequenceError("B_INVALID", f"B 索引值非法：{b_index}（合法 {sorted(B_PERMITTED)}）")
    return b_index


def g_slot_tmu(g_id: str | None, repeat: int = 1) -> int:
    """V2：選項即完整語意，無修飾 gating（ADR-014）。"""
    if not g_id:
        return 0
    if g_id not in G_OPTIONS:
        raise SequenceError("G_UNKNOWN", f"未知 G 選項：{g_id}")
    return G_OPTIONS[g_id][1] * repeat


def p_slot_tmu(base_id: str | None, addon_ids: list[str] | None = None, repeat: int = 1) -> int:
    addon_ids = addon_ids or []
    if not base_id:
        if addon_ids:
            raise SequenceError("P_ADDON_NO_BASE", "P 有附加條件時必須選擇基礎動作")
        return 0
    if base_id not in P_BASES:
        raise SequenceError("P_UNKNOWN", f"未知 P 基底：{base_id}")
    if len(addon_ids) > P_ADDON_MAX:
        raise SequenceError("P_TOO_MANY_ADDONS", f"P 附加最多 {P_ADDON_MAX} 個，收到 {len(addon_ids)}")
    if len(set(addon_ids)) != len(addon_ids):
        raise SequenceError("P_DUP_ADDON", f"P 附加重複：{addon_ids}")
    if "a_insert" in addon_ids and "a_snap" in addon_ids:
        raise SequenceError("P_ADDON_CONFLICT", "插入與卡合不可同時選擇")
    total = P_BASES[base_id][2]
    for aid in addon_ids:
        if aid not in P_ADDONS:
            raise SequenceError("P_ADDON_UNKNOWN", f"未知 P 附加：{aid}")
        total += P_ADDONS[aid][1]
    return total * repeat


def _partial_m(comp: dict[str, Any], repeat: int) -> int:
    """repeat 只乘動詞類分量（fixed/ladder/rotate），手度/腳步不乘（v3 認證）。"""
    verb = comp.get("verb_id")
    if not verb:
        return 0
    if verb not in M_VERBS:
        raise SequenceError("M_UNKNOWN", f"未知 M 動詞：{verb}")
    kind = M_VERBS[verb]
    if kind == "fixed3":
        return 3 * repeat
    if kind == "ladder":
        return _ladder_tmu(comp.get("distance_cm", 0)) * repeat
    if kind == "foot":
        return _foot_tmu(comp.get("distance_cm", 0))
    if kind == "hand":
        return _hand_tmu(comp.get("angle_deg", 0))
    if kind == "rotate":
        return _rotate_tmu(comp.get("diameter_cm", 0), comp.get("revolutions", 1)) * repeat
    raise SequenceError("M_KIND", f"未支援的 M 計價：{kind}")


def _ladder_tmu(cm: float) -> int:
    if cm is None or cm <= 0:
        return 0
    for upper, tmu in M_LADDER:
        if cm <= upper:
            return tmu
    raise SequenceError("M_DISTANCE_RANGE", f"距離 {cm}cm 超出階梯值表（最大 75cm）")


def _foot_tmu(cm: float) -> int:
    if cm is None or cm <= 0:
        return 0
    for upper, tmu in M_FOOT:
        if cm <= upper:
            return tmu
    raise SequenceError("M_DISTANCE_RANGE", f"腳步 {cm}cm 超出值表")


def _hand_tmu(deg: float) -> int:
    if deg is None or deg <= 0:
        return 0
    if deg <= 90:
        return 6
    if deg <= 180:
        return 10
    raise SequenceError("M_HAND_RANGE", f"手度 {deg}° 超出值表（最大 180°）")


def _rotate_tmu(diameter_cm: float, revolutions: int) -> int:
    rev = max(1, min(3, int(round(revolutions or 1))))
    if diameter_cm <= 12.5:
        return {1: 16, 2: 32, 3: 42}[rev]
    if diameter_cm <= 50:
        got = {1: 24, 2: 42}.get(rev)
        if got is None:
            raise SequenceError("M_ROTATION_RANGE", f"旋轉 直徑{diameter_cm}cm×{rev}圈 超出值表（大直徑無 3 圈檔）")
        return got
    raise SequenceError("M_ROTATION_RANGE", f"旋轉 直徑{diameter_cm}cm 超出值表（最大 50cm）")


def m_slot_tmu(components: list[dict[str, Any]] | None, repeat: int = 1) -> int:
    """M 格 = 各分量 partial 取 max；無分量 -> 0。"""
    components = components or []
    parts = [_partial_m(c, repeat) for c in components if c.get("verb_id")]
    return max(parts) if parts else 0


def x_slot_tmu(mode: str = "zero", seconds: float = 0, repeat: int = 1) -> float:
    """X：half-up 3 位（sec/0.036，E2/ADR-014；取代舊 ceil 裁決）。

    CL-01 §2 X（v3 認證）：mode=seconds 必須輸入正數秒數——負值先攔 X_NEGATIVE、
    未填/0 → X_SECONDS_REQUIRED（與 most_engine._x_tmu 同語意）。
    """
    if mode not in X_MODES:
        raise SequenceError("X_MODE", f"未知 X 模式：{mode}")
    if mode == "zero":
        return 0
    if mode == "fixed216":
        seconds = 0.216
    else:
        if seconds is not None and seconds < 0:
            raise SequenceError("X_NEGATIVE", f"秒數不可為負：{seconds}")
        if not seconds:
            raise SequenceError("X_SECONDS_REQUIRED", "X 動態秒數項目必須輸入正數秒數")
    return float((Decimal(str(seconds)) / Decimal("0.036")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)) * repeat


def i_slot_tmu(i_value: int = 0, repeat: int = 1) -> int:
    if i_value not in I_PERMITTED:
        raise SequenceError("I_INVALID", f"I 索引值非法：{i_value}（合法 {sorted(I_PERMITTED)}）")
    return i_value * repeat


# ─────────────────────────── cycle / 整表 ───────────────────────────
@dataclass
class CycleResult:
    seq: str
    slot_tmus: list[float]
    letters: list[str]
    total_tmu: float
    total_seconds: float
    tech_line: str
    overrides: list[dict[str, Any]]


def compute_cycle(cycle: dict[str, Any], system_tmu_multiplier: float = 1.0) -> CycleResult:
    """計算一條 GM/CM cycle。會驗證序列結構與所有 slot（含 repeat/E7 覆寫）。"""
    seq = cycle.get("seq")
    if seq not in ("GM", "CM"):
        raise SequenceError("SEQ_KIND", f"sequence 必須是 GM 或 CM，收到：{seq!r}")
    s = cycle.get("slots", {})

    def sl(i: int) -> dict[str, Any]:
        return s.get(i, {}) or {}

    def aslot(i: int) -> int:
        d = sl(i)
        if d.get("repeat_count") not in (None, 1):
            raise SequenceError("REPEAT_INVALID", "A 格不支援 repeat_count")
        return a_slot_tmu(d.get("reach_cm", 0), d.get("twist_deg", 0), d.get("foot_cm", 0))

    def bslot(i: int) -> int:
        d = sl(i)
        if d.get("repeat_count") not in (None, 1):
            raise SequenceError("REPEAT_INVALID", "B 格不支援 repeat_count")
        return b_slot_tmu(d.get("b_index", 0))

    tmus: list[float] = [0] * 7
    tmus[0] = aslot(0)
    tmus[1] = bslot(1)
    g = sl(2)
    tmus[2] = g_slot_tmu(g.get("g_id"), _repeat(g))

    if seq == "GM":
        for i in (3, 4, 5):
            _reject_keys(seq, i, sl(i))
        tmus[3] = aslot(3)
        tmus[4] = bslot(4)
        p = sl(5)
        tmus[5] = p_slot_tmu(p.get("p_base"), p.get("p_addons"), _repeat(p))
        letters = GM_LETTERS
    else:  # CM
        for i in (3, 4, 5):
            _reject_keys(seq, i, sl(i))
        m = sl(3)
        tmus[3] = m_slot_tmu(m.get("m_components"), _repeat(m))
        x = sl(4)
        tmus[4] = x_slot_tmu(x.get("x_mode", "zero"), x.get("x_seconds", 0), _repeat(x))
        ii = sl(5)
        tmus[5] = i_slot_tmu(ii.get("i_value", 0), _repeat(ii))
        letters = CM_LETTERS

    d6 = sl(6)
    if d6.get("repeat_count") not in (None, 1):
        raise SequenceError("REPEAT_INVALID", "A 格不支援 repeat_count")
    tmus[6] = a_return_tmu(d6.get("reach_cm", 0), d6.get("twist_deg", 0), d6.get("foot_cm", 0))

    # E7：人工覆寫（值取代、全程留痕）
    overrides: list[dict[str, Any]] = []
    for i in range(7):
        ov = sl(i).get("manual_override")
        if ov is None:
            continue
        tmu, reason = ov.get("tmu"), (ov.get("reason") or "").strip()
        if isinstance(tmu, bool) or not isinstance(tmu, (int, float)) or tmu < 0 or not reason:
            raise SequenceError("OVERRIDE_INVALID", f"slot{i} 人工覆寫需 tmu≥0 且 reason 非空")
        overrides.append({"slot": i, "letter": letters[i], "auto_tmu": tmus[i],
                          "override_tmu": float(tmu), "reason": reason, "by": ov.get("by")})
        tmus[i] = float(tmu)

    ov_slots = {o["slot"] for o in overrides}
    total = round(sum(tmus) * system_tmu_multiplier, 3)
    tech = " ".join(f"{L}{t:g}{'*' if i in ov_slots else ''}" for i, (L, t) in enumerate(zip(letters, tmus)))
    return CycleResult(seq, tmus, letters, total, round(total * TMU_TO_SEC, 4), tech, overrides)


_COMMON_KEYS = {"repeat_count", "manual_override"}
_GM_SLOT_KEYS = {3: {"reach_cm", "twist_deg", "foot_cm"} | _COMMON_KEYS, 4: {"b_index"} | _COMMON_KEYS,
                 5: {"p_base", "p_addons"} | _COMMON_KEYS}
_CM_SLOT_KEYS = {3: {"m_components"} | _COMMON_KEYS, 4: {"x_mode", "x_seconds"} | _COMMON_KEYS, 5: {"i_value"} | _COMMON_KEYS}


def _reject_keys(seq: str, slot_idx: int, data: dict[str, Any]) -> None:
    """確保 GM 的 3/4/5 不帶 M/X/I 欄、CM 不帶 P 欄（結構不可混用）。"""
    allowed = (_GM_SLOT_KEYS if seq == "GM" else _CM_SLOT_KEYS)[slot_idx]
    foreign = set(data.keys()) - allowed
    if foreign:
        raise SequenceError(
            "SLOT_CROSS_MODEL",
            f"{seq} 的 slot{slot_idx} 不可含 {sorted(foreign)} 欄（GM↔CM 結構不可混用）",
        )


def compute_table(steps: list[dict[str, Any]], system_tmu_multiplier: float = 1.0) -> dict[str, Any]:
    """多列 WI：合計 = Σ(非SIMO tmu×freq) + Σ(每個 SIMO 群組的 max(tmu×freq))。"""
    rows = []
    non_simo = 0.0
    simo_groups: dict[str, float] = {}
    for idx, step in enumerate(steps):
        freq = step.get("frequency", 1)
        if freq is None or freq <= 0:
            raise SequenceError("FREQ_INVALID", f"列 {idx}: frequency 須 >0，收到 {freq}")
        r = compute_cycle(step, system_tmu_multiplier)
        eff = r.total_tmu * freq
        gid = step.get("simo_group_id")
        if gid:
            simo_groups[gid] = max(simo_groups.get(gid, 0.0), eff)
        else:
            non_simo += eff
        rows.append({"index": idx, "tech_line": r.tech_line, "tmu": r.total_tmu, "freq": freq, "eff_tmu": eff, "simo_group_id": gid})
    total = round(non_simo + sum(simo_groups.values()), 3)
    return {"rows": rows, "total_tmu": total, "total_seconds": round(total * TMU_TO_SEC, 4),
            "simo_groups": simo_groups}


# ─────────────────────────── 測試（golden + edge cases） ───────────────────────────
def _a(reach=0, twist=0, foot=0):
    return {"reach_cm": reach, "twist_deg": twist, "foot_cm": foot}


def _gm(a0, g, a3, p, a6, b1=0, b4=0):
    return {"seq": "GM", "slots": {0: a0, 1: {"b_index": b1}, 2: g, 3: a3,
                                   4: {"b_index": b4}, 5: p, 6: a6}}


def _cm(a0, g, m, x, i, a6, b1=0):
    return {"seq": "CM", "slots": {0: a0, 1: {"b_index": b1}, 2: g, 3: m, 4: x, 5: i, 6: a6}}


def _run_tests() -> int:
    passed = 0
    failed = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}  {detail}")

    def expect_error(name: str, code: str, fn) -> None:
        nonlocal passed, failed
        try:
            fn()
        except SequenceError as e:
            if e.code == code:
                passed += 1
                print(f"  ✅ {name}（正確擋下 {code}）")
            else:
                failed += 1
                print(f"  ❌ {name} 期望 {code} 但得到 {e.code}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ❌ {name} 期望 SequenceError({code}) 但得到 {type(e).__name__}: {e}")
        else:
            failed += 1
            print(f"  ❌ {name} 期望 {code} 但未報錯")

    print("\n── A. 黃金教學範例（V2 口徑，impl-02 E8）──")
    # GM: A6 B0 G6 A10 B0 P6 A0 = 28
    gm = _gm(_a(reach=20), {"g_id": "g_grasp"}, _a(reach=25),
             {"p_base": "p_place_none"}, _a())
    r = compute_cycle(gm)
    check("GM 範例 = 28 TMU", r.total_tmu == 28, f"got {r.total_tmu} ({r.tech_line})")
    check("GM 秒數 = 1.008", abs(r.total_seconds - 28 * 0.036) < 1e-9)
    # CM: A10 B0 G3 M16 X0 I0 A0 = 29
    # 【C1 定案】M16＝「推 18 吋＝45cm」（階梯 ≤45→16）。V1 曾把 18 誤讀為 cm；
    # 單位回歸反例見下：推 18cm 落 ≤25 檔 →10。
    cm = _cm(_a(reach=25), {"g_id": "g_touch"},
             {"m_components": [{"verb_id": "m_push", "distance_cm": 45}]},
             {"x_mode": "zero"}, {"i_value": 0}, _a())
    r = compute_cycle(cm)
    check("CM 範例 = 29 TMU (M16=推45cm=18吋檔)", r.total_tmu == 29, f"got {r.total_tmu} ({r.tech_line})")
    check("單位回歸反例：推 18cm → 10",
          m_slot_tmu([{"verb_id": "m_push", "distance_cm": 18}]) == 10)

    print("\n── B. A 三分量取 max ＋ A3 返回（E1）──")
    check("A 取 max(伸手6,手度3,腳步0)=6", a_slot_tmu(20, 120, 0) == 6)
    check("A 取 max(伸手3,手度6,腳步10)=10", a_slot_tmu(10, 180, 30) == 10)
    check("A 全 0 -> 0", a_slot_tmu(0, 0, 0) == 0)
    check("A 邊界 reach 20cm->6", a_slot_tmu(20) == 6)
    check("A 邊界 reach 20.01cm->10", a_slot_tmu(20.01) == 10)
    check("A reach 超大 ->24", a_slot_tmu(999) == 24)
    check("A foot 999 ->32", a_slot_tmu(0, 0, 999) == 32)
    expect_error("A 負距離擋下", "A_NEGATIVE", lambda: a_slot_tmu(-5))
    check("A3 返回 25cm -> 10", a_return_tmu(25) == 10)
    expect_error("A3 帶手度擋下", "A_RETURN_COMPONENT", lambda: a_return_tmu(25, twist_deg=90))
    expect_error("A3 帶腳步擋下", "A_RETURN_COMPONENT", lambda: a_return_tmu(25, foot_cm=30))

    print("\n── C. B 身體動作（1205 值 0/10/32/42）──")
    check("B0=0", b_slot_tmu(0) == 0)
    check("B 眼部=10", b_slot_tmu(10) == 10)
    check("B 起身彎腰坐=32", b_slot_tmu(32) == 32)
    check("B 站=42", b_slot_tmu(42) == 42)
    expect_error("B=3 非法（舊 SEED 值已廢）", "B_INVALID", lambda: b_slot_tmu(3))

    print("\n── D. G 取得（V2：無 gating，選項即語意）──")
    check("G 抓握=6", g_slot_tmu("g_grasp") == 6)
    check("G 接觸=3（無需勾修飾）", g_slot_tmu("g_touch") == 3)
    check("G 拿取(選取-小)=16", g_slot_tmu("g_pick_small") == 16)
    check("G 收集=24", g_slot_tmu("g_pick_collect") == 24)
    check("G 未選=0", g_slot_tmu(None) == 0)
    check("G 抓握×2=12（repeat）", g_slot_tmu("g_grasp", 2) == 12)
    expect_error("G 未知選項擋下", "G_UNKNOWN", lambda: g_slot_tmu("g_zzz"))

    print("\n── E. P 放置（base + ≤2 附加；插入⊥卡合；V2 對準直接加成）──")
    check("P 放無方向=6", p_slot_tmu("p_place_none") == 6)
    check("P 組一種+對準=24", p_slot_tmu("p_asm_single", ["a_align"]) == 24)
    check("P 放無方向+插入+施壓=30", p_slot_tmu("p_place_none", ["a_insert", "a_press"]) == 30)
    check("P 未選 base=0", p_slot_tmu(None) == 0)
    expect_error("P 插入⊥卡合擋下", "P_ADDON_CONFLICT",
                 lambda: p_slot_tmu("p_asm_single", ["a_insert", "a_snap"]))
    expect_error("P 有附加無 base 擋下", "P_ADDON_NO_BASE", lambda: p_slot_tmu(None, ["a_insert"]))
    expect_error("P 超過 2 附加擋下", "P_TOO_MANY_ADDONS",
                 lambda: p_slot_tmu("p_toss", ["a_insert", "a_hard", "a_press"]))
    expect_error("P 重複附加擋下", "P_DUP_ADDON",
                 lambda: p_slot_tmu("p_toss", ["a_insert", "a_insert"]))
    expect_error("P 未知附加擋下", "P_ADDON_UNKNOWN", lambda: p_slot_tmu("p_toss", ["a_zzz"]))

    print("\n── F. M 控制移動（cm 正確階梯／腳步獨立帶／範圍錯誤／repeat 只乘動詞）──")
    check("M 推 45cm=16（18 吋檔）", m_slot_tmu([{"verb_id": "m_push", "distance_cm": 45}]) == 16)
    check("M 推 45.1cm=24 / 75cm=24", _ladder_tmu(45.1) == 24 and _ladder_tmu(75) == 24)
    expect_error("M 推 76cm 超界擋下", "M_DISTANCE_RANGE", lambda: _ladder_tmu(76))
    check("M 腳步 30cm=16（獨立帶）/ 80cm=42", _foot_tmu(30) == 16 and _foot_tmu(80) == 42)
    check("M 多分量取 max(理10cm→6, 手度10)=10",
          m_slot_tmu([{"verb_id": "m_li", "distance_cm": 10}, {"verb_id": "m_hand", "angle_deg": 180}]) == 10)
    expect_error("M 手度 181° 超界擋下", "M_HAND_RANGE", lambda: _hand_tmu(181))
    check("M 按鈕固定=3", m_slot_tmu([{"verb_id": "m_btn"}]) == 3)
    check("M 旋轉 直徑10 2圈=32", m_slot_tmu([{"verb_id": "m_rotate", "diameter_cm": 10, "revolutions": 2}]) == 32)
    expect_error("M 旋轉 直徑60 超界擋下", "M_ROTATION_RANGE", lambda: _rotate_tmu(60, 1))
    expect_error("M 旋轉 直徑20×3圈 超界擋下", "M_ROTATION_RANGE", lambda: _rotate_tmu(20, 3))
    check("M 推45×3 只乘動詞再 max=48",
          m_slot_tmu([{"verb_id": "m_push", "distance_cm": 45}, {"verb_id": "m_hand", "angle_deg": 180}], repeat=3) == 48)
    check("M 無分量=0", m_slot_tmu([]) == 0)
    check("M 空 verb 跳過=0", m_slot_tmu([{"verb_id": ""}]) == 0)
    expect_error("M 未知動詞擋下", "M_UNKNOWN", lambda: m_slot_tmu([{"verb_id": "m_zzz"}]))

    print("\n── G. X 處理時間（half-up 3 位 + 固定 0.216）──")
    check("X 無機台=0", x_slot_tmu("zero") == 0)
    check("X 10 秒 -> 277.778（half-up；舊 ceil=278 已廢）", abs(x_slot_tmu("seconds", 10) - 277.778) < 1e-9)
    check("X 5 秒 -> 138.889", abs(x_slot_tmu("seconds", 5) - 138.889) < 1e-9)
    check("X 固定 0.216 -> 6", x_slot_tmu("fixed216") == 6)
    expect_error("X 0 秒擋下（動態秒數須正數）", "X_SECONDS_REQUIRED", lambda: x_slot_tmu("seconds", 0))
    expect_error("X 未填秒擋下（動態秒數須正數）", "X_SECONDS_REQUIRED", lambda: x_slot_tmu("seconds"))
    expect_error("X 未知模式擋下", "X_MODE", lambda: x_slot_tmu("bogus"))
    expect_error("X 負秒擋下", "X_NEGATIVE", lambda: x_slot_tmu("seconds", -1))

    print("\n── H. I 對齊（V2 八檔含視線外）──")
    check("I 不對齊=0", i_slot_tmu(0) == 0)
    check("I 並檢查/確認(正常)=6", i_slot_tmu(6) == 6)
    check("I 並對齊(正常·兩點)=16", i_slot_tmu(16) == 16)
    check("I 並對準(視線外·到點)=24", i_slot_tmu(24) == 24)
    check("I 並對齊(視線外·兩點)=32", i_slot_tmu(32) == 32)
    expect_error("I=3 非法擋下", "I_INVALID", lambda: i_slot_tmu(3))

    print("\n── I. 序列結構（GM↔CM 不可混用）＋ repeat/覆寫 ──")
    expect_error("GM 的 P slot 帶 m_components 擋下", "SLOT_CROSS_MODEL",
                 lambda: compute_cycle({"seq": "GM", "slots": {0: _a(), 1: {"b_index": 0}, 2: {"g_id": "g_grasp"},
                                                               3: _a(), 4: {"b_index": 0},
                                                               5: {"m_components": []}, 6: _a()}}))
    expect_error("CM 的 slot5 帶 p_base 擋下", "SLOT_CROSS_MODEL",
                 lambda: compute_cycle({"seq": "CM", "slots": {0: _a(), 1: {"b_index": 0}, 2: {"g_id": "g_grasp"},
                                                               3: {"m_components": []}, 4: {"x_mode": "zero"},
                                                               5: {"p_base": "p_toss"}, 6: _a()}}))
    expect_error("未知 seq 擋下", "SEQ_KIND", lambda: compute_cycle({"seq": "XX", "slots": {}}))
    expect_error("repeat=0 擋下", "REPEAT_INVALID",
                 lambda: compute_cycle(_gm(_a(), {"g_id": "g_grasp", "repeat_count": 0}, _a(), {"p_base": "p_toss"}, _a())))
    expect_error("A 格 repeat 擋下", "REPEAT_INVALID",
                 lambda: compute_cycle(_gm({**_a(reach=10), "repeat_count": 2}, {"g_id": "g_grasp"}, _a(), {"p_base": "p_toss"}, _a())))
    ovc = _gm(_a(reach=20), {"g_id": "g_grasp"}, _a(reach=25), {"p_base": "p_place_none", "manual_override": {"tmu": 10, "reason": "現場實測", "by": "E123"}}, _a())
    rov = compute_cycle(ovc)
    check("覆寫 P→10、總 32、tech 標*", rov.total_tmu == 32 and "P10*" in rov.tech_line and rov.overrides[0]["auto_tmu"] == 6)
    expect_error("覆寫 reason 空擋下", "OVERRIDE_INVALID",
                 lambda: compute_cycle(_gm(_a(), {"g_id": "g_grasp"}, _a(), {"p_base": "p_toss", "manual_override": {"tmu": 5, "reason": " "}}, _a())))

    print("\n── J. 整表 SIMO / frequency ──")
    table = compute_table([
        {**gm, "frequency": 2},                              # 28×2 = 56（非 SIMO）
        {**cm, "frequency": 1, "simo_group_id": "S1"},       # 29（SIMO S1）
        {**cm, "frequency": 1, "simo_group_id": "S1"},       # 29（SIMO S1）→群組取 max=29
    ])
    check("整表 SIMO 合計 = 56 + max(29,29) = 85", table["total_tmu"] == 85, f'got {table["total_tmu"]}')
    expect_error("frequency<=0 擋下", "FREQ_INVALID",
                 lambda: compute_table([{**gm, "frequency": 0}]))

    print("\n── K. 1205 第 96–117 列真實工步擴充黃金集（catalog §3，V2 過帳）──")
    # 3.1 真實 token → 索引（客觀；A 帶兩版一致故值不變）
    check("伸手 40cm → A16", a_slot_tmu(reach_cm=40) == 16)
    check("伸手 60cm → A16", a_slot_tmu(reach_cm=60) == 16)
    check("移動 10cm → A3", a_slot_tmu(reach_cm=10) == 3)
    check("移動 20cm → A6", a_slot_tmu(reach_cm=20) == 6)
    check("移動 40cm → A16", a_slot_tmu(reach_cm=40) == 16)
    check("移動 60cm → A16", a_slot_tmu(reach_cm=60) == 16)
    check("理 20cm (M階梯) → 10【值變更 C1：V1=24】",
          m_slot_tmu([{"verb_id": "m_li", "distance_cm": 20}]) == 10)
    check("壓合 10S → X 277.778【值變更 E2：V1=278】", abs(x_slot_tmu("seconds", 10) - 277.778) < 1e-9)

    # 3.3 兩則完整工步解構（詮釋性，⚠️ 假設見 catalog §3.3）
    r112 = _gm(_a(reach=60), {"g_id": "g_grasp"}, _a(),
               {"p_base": "p_asm_single", "p_addons": ["a_snap"]}, _a())  # 16+6+(16+16)=54
    t112 = compute_table([{**r112, "frequency": 2}])
    check("R112 GM 解構 ×2 = 108", t112["total_tmu"] == 108, f'got {t112["total_tmu"]}')
    r116 = _cm(_a(reach=60), {"g_id": "g_touch"},
               {"m_components": [{"verb_id": "m_btn"}]}, {"x_mode": "seconds", "x_seconds": 10},
               {"i_value": 0}, _a())  # 16+3+3+277.778=299.778
    check("R116 CM 解構 = 299.778【值變更 E2：V1=300】", abs(compute_cycle(r116).total_tmu - 299.778) < 1e-9,
          f"got {compute_cycle(r116).total_tmu}")

    print(f"\n{'='*52}\n結果：{passed} passed, {failed} failed\n{'='*52}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_run_tests())
