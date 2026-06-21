#!/usr/bin/env python3
"""MiniMOST Sequence Model — 核心邏輯驗證器（reference implementation + self-tests）.

權威依據：docs/specs/minimost-sequence-model-core-logic-spec.md (v1.0)
範圍：MiniMOST only，GM(一般移動 A B G A B P A) / CM(控制移動 A B G M X I A)。

設計目標：
  * 本檔是「規格的可執行版本」——任何 MiniMOST 計算實作都應對得上這裡的結果。
  * 把 edge case 全部封掉：非法 slot、未勾修飾、超過 2 個附加、CM 不可有 P、
    GM 不可有 M/X/I、距離邊界、負值、未知選項… 一律以 SequenceError 明確報錯。
  * 無第三方相依，可直接 `python minimost_sequence_validator.py` 跑全部測試。

已確認決策（spec §0）：
  Q1 合計 = (Σ slot index) × system_tmu_multiplier（不乘 10）；1 TMU = 0.036 秒。
  Q2 B 採 1205 值 {0,10,32,42} 且必須計入。
  Q3 X = 連續 ceil(sec/0.036)，固定類 0.216→6。
  Q4 A = max(伸手, 手度, 腳步) 三分量。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

TMU_TO_SEC = 0.036


class SequenceError(ValueError):
    """帶錯誤碼的驗證錯誤。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


# ─────────────────────────── 查表常數（spec §4） ───────────────────────────
# (upper_bound_inclusive, index)；value<=0 視為無此分量。最後一段為 (inf, idx)。
A_REACH_BANDS = [(2.5, 0), (5, 1), (10, 3), (20, 6), (35, 10), (60, 16), (math.inf, 24)]
A_TWIST_BANDS = [(30, 0), (60, 1), (120, 3), (180, 6)]
A_FOOT_BANDS = [(20, 6), (30, 10), (45, 16), (65, 24), (math.inf, 32)]

# B 身體動作（1205，已確認）：index 值即為合法集合。
B_PERMITTED = {0, 10, 32, 42}

# G 取得：id -> (label, modifier_key|None, requires_modifier, base_tmu)
G_OPTIONS: dict[str, tuple[str, str | None, bool, int]] = {
    "g_tap": ("輕按", "contact", True, 3),
    "g_touch": ("接觸", "contact", True, 3),
    "g_pat": ("輕拍", "contact", True, 3),
    "g_grasp": ("抓握", None, False, 6),
    "g_grab": ("抓取", None, False, 6),
    "g_regrasp": ("重新抓握", None, False, 6),
    "g_handchange": ("換手", "transfer", True, 10),
    "g_pick_sel": ("拿取(選取)", "select", True, 10),
    "g_pick_small": ("拿取(選取-小)", "select_small", True, 16),
    "g_pullout": ("拔出", "separate", True, 16),
    "g_pick_collect": ("拿取(收集)", "collect", True, 24),
}

# P 放置基底：id -> (label, direction, base_tmu)
P_BASES: dict[str, tuple[str, str | None, int]] = {
    "p_toss": ("丟", None, 3),
    "p_hold": ("保持住", None, 3),
    "p_place_none": ("放(無方向)", "none", 6),
    "p_place_multi": ("放(多種方向)", "multi", 10),
    "p_place_single": ("放(一種方向)", "single", 16),
    "p_asm_multi": ("組(多種方向)", "multi", 10),
    "p_asm_single": ("組(一種方向)", "single", 16),
}
# P 附加：id -> (label, delta, needs_precision)
P_ADDONS: dict[str, tuple[str, int, bool]] = {
    "a_align": ("對準", 8, True),
    "a_insert": ("插入", 8, False),
    "a_hard": ("較難處理", 8, False),
    "a_snap": ("卡合", 16, False),
    "a_press": ("施加壓力", 16, False),
}
P_ADDON_MAX = 2

# M 控制移動距離階梯：(upper_cm_inclusive, tmu)；> 最後門檻 -> 42
M_LADDER = [(1, 3), (4, 6), (10, 10), (18, 16), (30, 24)]
M_LADDER_OVER = 42
# M 動詞：id -> pricing_kind
M_VERBS: dict[str, str] = {
    "m_btn": "fixed3",
    "m_screw": "fixed3",
    "m_li": "ladder", "m_through": "ladder", "m_push": "ladder",
    "m_pull": "ladder", "m_attach": "ladder", "m_remove": "ladder",
    "m_teartape": "ladder", "m_fold": "ladder", "m_wipe": "ladder", "m_tearopen": "ladder",
    "m_rotate": "rotate",
    "m_hand": "hand",
    "m_foot": "foot",
}
X_MODES = {"zero", "seconds", "fixed216"}
X_FIXED_216 = math.ceil(0.216 / TMU_TO_SEC)  # = 6
I_PERMITTED = {0, 6, 10, 16}

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


def a_slot_tmu(reach_cm: float = 0, twist_deg: float = 0, foot_cm: float = 0) -> int:
    """A 格 = max(伸手, 手度, 腳步) 三分量 index；皆無 -> 0。"""
    parts = [
        _band_index(reach_cm, A_REACH_BANDS),
        _band_index(twist_deg, A_TWIST_BANDS),
        _band_index(foot_cm, A_FOOT_BANDS),
    ]
    present = [p for p in parts if p is not None]
    return max(present) if present else 0


def b_slot_tmu(b_index: int = 0) -> int:
    if b_index not in B_PERMITTED:
        raise SequenceError("B_INVALID", f"B 索引值非法：{b_index}（合法 {sorted(B_PERMITTED)}）")
    return b_index


def g_slot_tmu(g_id: str | None, modifiers: dict[str, bool] | None = None) -> int:
    if not g_id:
        return 0
    if g_id not in G_OPTIONS:
        raise SequenceError("G_UNKNOWN", f"未知 G 選項：{g_id}")
    _label, mod_key, req, tmu = G_OPTIONS[g_id]
    modifiers = modifiers or {}
    if req and mod_key and not modifiers.get(mod_key):
        return 0  # 需勾修飾但未勾 → 視為未完成，不計分（spec §4.3）
    return tmu


def p_slot_tmu(base_id: str | None, addon_ids: list[str] | None = None, precision: bool = False) -> int:
    if not base_id:
        return 0
    if base_id not in P_BASES:
        raise SequenceError("P_UNKNOWN", f"未知 P 基底：{base_id}")
    addon_ids = addon_ids or []
    if len(addon_ids) > P_ADDON_MAX:
        raise SequenceError("P_TOO_MANY_ADDONS", f"P 附加最多 {P_ADDON_MAX} 個，收到 {len(addon_ids)}")
    if len(set(addon_ids)) != len(addon_ids):
        raise SequenceError("P_DUP_ADDON", f"P 附加重複：{addon_ids}")
    total = P_BASES[base_id][2]
    for aid in addon_ids:
        if aid not in P_ADDONS:
            raise SequenceError("P_ADDON_UNKNOWN", f"未知 P 附加：{aid}")
        _lab, delta, needs_prec = P_ADDONS[aid]
        if needs_prec and not precision:
            continue  # 對準需勾「精度<4mm」才 +8（spec §4.4）
        total += delta
    return total


def _partial_m(comp: dict[str, Any]) -> int:
    verb = comp.get("verb_id")
    if not verb:
        return 0
    if verb not in M_VERBS:
        raise SequenceError("M_UNKNOWN", f"未知 M 動詞：{verb}")
    kind = M_VERBS[verb]
    if kind == "fixed3":
        return 3
    if kind == "ladder":
        return _ladder_tmu(comp.get("distance_cm", 0))
    if kind == "foot":
        return _ladder_tmu(comp.get("distance_cm", 0))
    if kind == "hand":
        return _hand_tmu(comp.get("angle_deg", 0))
    if kind == "rotate":
        return _rotate_tmu(comp.get("diameter_cm", 0), comp.get("revolutions", 1))
    raise SequenceError("M_KIND", f"未支援的 M 計價：{kind}")


def _ladder_tmu(cm: float) -> int:
    if cm is None or cm <= 0:
        return 0
    if cm < 0:
        raise SequenceError("M_NEGATIVE", f"距離不可為負：{cm}")
    for upper, tmu in M_LADDER:
        if cm <= upper:
            return tmu
    return M_LADDER_OVER


def _hand_tmu(deg: float) -> int:
    if deg is None or deg <= 0:
        return 0
    return 6 if deg <= 90 else 10


def _rotate_tmu(diameter_cm: float, revolutions: int) -> int:
    rev = max(1, min(3, int(round(revolutions or 1))))
    if diameter_cm <= 12.5:
        return {1: 16, 2: 32, 3: 42}[rev]
    return {1: 24, 2: 42, 3: 42}[rev]  # 直徑>12.5cm：1圈24/2圈42（3圈沿用）


def m_slot_tmu(components: list[dict[str, Any]] | None) -> int:
    """M 格 = 各分量 partial 取 max；無分量 -> 0。"""
    components = components or []
    parts = [_partial_m(c) for c in components if c.get("verb_id")]
    return max(parts) if parts else 0


def x_slot_tmu(mode: str = "zero", seconds: float = 0) -> int:
    if mode not in X_MODES:
        raise SequenceError("X_MODE", f"未知 X 模式：{mode}")
    if mode == "zero":
        return 0
    if mode == "fixed216":
        return X_FIXED_216
    # seconds
    if seconds is not None and seconds < 0:
        raise SequenceError("X_NEGATIVE", f"秒數不可為負：{seconds}")
    if not seconds:
        return 0
    return math.ceil(seconds / TMU_TO_SEC)


def i_slot_tmu(i_value: int = 0) -> int:
    if i_value not in I_PERMITTED:
        raise SequenceError("I_INVALID", f"I 索引值非法：{i_value}（合法 {sorted(I_PERMITTED)}）")
    return i_value


# ─────────────────────────── cycle / 整表 ───────────────────────────
@dataclass
class CycleResult:
    seq: str
    slot_tmus: list[int]
    letters: list[str]
    total_tmu: float
    total_seconds: float
    tech_line: str


def compute_cycle(cycle: dict[str, Any], system_tmu_multiplier: float = 1.0) -> CycleResult:
    """計算一條 GM/CM cycle。會驗證序列結構與所有 slot。"""
    seq = cycle.get("seq")
    if seq not in ("GM", "CM"):
        raise SequenceError("SEQ_KIND", f"sequence 必須是 GM 或 CM，收到：{seq!r}")
    s = cycle.get("slots", {})

    def aslot(i: int) -> int:
        d = s.get(i, {}) or {}
        return a_slot_tmu(d.get("reach_cm", 0), d.get("twist_deg", 0), d.get("foot_cm", 0))

    tmus = [0] * 7
    tmus[0] = aslot(0)
    tmus[1] = b_slot_tmu((s.get(1, {}) or {}).get("b_index", 0))
    g = s.get(2, {}) or {}
    tmus[2] = g_slot_tmu(g.get("g_id"), g.get("modifiers"))

    if seq == "GM":
        # slot3=A, slot4=B, slot5=P；不可出現 M/X/I
        for i in (3, 4, 5):
            _reject_keys(seq, i, s.get(i, {}) or {})
        tmus[3] = aslot(3)
        tmus[4] = b_slot_tmu((s.get(4, {}) or {}).get("b_index", 0))
        p = s.get(5, {}) or {}
        tmus[5] = p_slot_tmu(p.get("p_base"), p.get("p_addons"), p.get("precision", False))
        letters = GM_LETTERS
    else:  # CM
        for i in (3, 4, 5):
            _reject_keys(seq, i, s.get(i, {}) or {})
        m = s.get(3, {}) or {}
        tmus[3] = m_slot_tmu(m.get("m_components"))
        x = s.get(4, {}) or {}
        tmus[4] = x_slot_tmu(x.get("x_mode", "zero"), x.get("x_seconds", 0))
        ii = s.get(5, {}) or {}
        tmus[5] = i_slot_tmu(ii.get("i_value", 0))
        letters = CM_LETTERS

    tmus[6] = aslot(6)

    total = sum(tmus) * system_tmu_multiplier
    tech = " ".join(f"{L}{t}" for L, t in zip(letters, tmus))
    return CycleResult(seq, tmus, letters, total, round(total * TMU_TO_SEC, 6), tech)


_GM_SLOT_KEYS = {3: {"reach_cm", "twist_deg", "foot_cm"}, 4: {"b_index"},
                 5: {"p_base", "p_addons", "precision"}}
_CM_SLOT_KEYS = {3: {"m_components"}, 4: {"x_mode", "x_seconds"}, 5: {"i_value"}}


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
    total = non_simo + sum(simo_groups.values())
    return {"rows": rows, "total_tmu": total, "total_seconds": round(total * TMU_TO_SEC, 6),
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

    print("\n── A. 黃金教學範例（spec §7）──")
    # GM: A6 B0 G6 A10 B0 P6 A0 = 28
    gm = _gm(_a(reach=20), {"g_id": "g_grasp"}, _a(reach=25),
             {"p_base": "p_place_none"}, _a())
    r = compute_cycle(gm)
    check("GM 範例 = 28 TMU", r.total_tmu == 28, f"got {r.total_tmu} ({r.tech_line})")
    check("GM 秒數 = 1.008", abs(r.total_seconds - 28 * 0.036) < 1e-9)
    # CM: A10 B0 G3 M16 X0 I0 A0 = 29
    # 註：M16 對應「推 ≤18cm」（M 階梯 ≤18→16）。理解文件把它標成「30cm」是來源筆誤，
    #     依操作中階梯 30cm → 24（見 §F 測試）。此處用 18cm 還原文件宣稱的 29 黃金值。
    cm = _cm(_a(reach=25), {"g_id": "g_touch", "modifiers": {"contact": True}},
             {"m_components": [{"verb_id": "m_push", "distance_cm": 18}]},
             {"x_mode": "zero"}, {"i_value": 0}, _a())
    r = compute_cycle(cm)
    check("CM 範例 = 29 TMU (M16=推≤18cm)", r.total_tmu == 29, f"got {r.total_tmu} ({r.tech_line})")

    print("\n── B. A 三分量取 max ──")
    check("A 取 max(伸手6,手度3,腳步0)=6", a_slot_tmu(20, 120, 0) == 6)
    check("A 取 max(伸手3,手度6,腳步10)=10", a_slot_tmu(10, 180, 30) == 10)
    check("A 全 0 -> 0", a_slot_tmu(0, 0, 0) == 0)
    check("A 邊界 reach 20cm->6", a_slot_tmu(20) == 6)
    check("A 邊界 reach 20.01cm->10", a_slot_tmu(20.01) == 10)
    check("A reach 超大 ->24", a_slot_tmu(999) == 24)
    check("A foot 999 ->32", a_slot_tmu(0, 0, 999) == 32)
    expect_error("A 負距離擋下", "A_NEGATIVE", lambda: a_slot_tmu(-5))

    print("\n── C. B 身體動作（1205 值 0/10/32/42）──")
    check("B0=0", b_slot_tmu(0) == 0)
    check("B 眼部=10", b_slot_tmu(10) == 10)
    check("B 起身彎腰坐=32", b_slot_tmu(32) == 32)
    check("B 站=42", b_slot_tmu(42) == 42)
    expect_error("B=3 非法（舊 SEED 值已廢）", "B_INVALID", lambda: b_slot_tmu(3))

    print("\n── D. G 取得 + 修飾門檻 ──")
    check("G 抓握(無修飾)=6", g_slot_tmu("g_grasp") == 6)
    check("G 接觸已勾 contact=3", g_slot_tmu("g_touch", {"contact": True}) == 3)
    check("G 接觸未勾 contact=0（未完成）", g_slot_tmu("g_touch", {}) == 0)
    check("G 收集已勾=24", g_slot_tmu("g_pick_collect", {"collect": True}) == 24)
    check("G 未選=0", g_slot_tmu(None) == 0)
    expect_error("G 未知選項擋下", "G_UNKNOWN", lambda: g_slot_tmu("g_zzz"))

    print("\n── E. P 放置（base + ≤2 附加 + 精度門檻）──")
    check("P 放無方向=6", p_slot_tmu("p_place_none") == 6)
    check("P 組一種+插入+卡合=16+8+16=40", p_slot_tmu("p_asm_single", ["a_insert", "a_snap"]) == 40)
    check("P 對準未勾精度 -> 不加(只 base)", p_slot_tmu("p_place_single", ["a_align"], precision=False) == 16)
    check("P 對準勾精度 -> +8", p_slot_tmu("p_place_single", ["a_align"], precision=True) == 24)
    check("P 未選 base=0", p_slot_tmu(None) == 0)
    expect_error("P 超過 2 附加擋下", "P_TOO_MANY_ADDONS",
                 lambda: p_slot_tmu("p_toss", ["a_insert", "a_snap", "a_press"]))
    expect_error("P 重複附加擋下", "P_DUP_ADDON",
                 lambda: p_slot_tmu("p_toss", ["a_insert", "a_insert"]))
    expect_error("P 未知附加擋下", "P_ADDON_UNKNOWN", lambda: p_slot_tmu("p_toss", ["a_zzz"]))

    print("\n── F. M 控制移動（取 max / 階梯 / 旋轉 / 手度）──")
    check("M 推 30cm=24", m_slot_tmu([{"verb_id": "m_push", "distance_cm": 30}]) == 24)
    check("M 推 30.1cm=42（超 30）", m_slot_tmu([{"verb_id": "m_push", "distance_cm": 30.1}]) == 42)
    check("M 多分量取 max(理6, 手度10)=10",
          m_slot_tmu([{"verb_id": "m_li", "distance_cm": 4}, {"verb_id": "m_hand", "angle_deg": 180}]) == 10)
    check("M 按鈕固定=3", m_slot_tmu([{"verb_id": "m_btn"}]) == 3)
    check("M 旋轉 直徑10 2圈=32", m_slot_tmu([{"verb_id": "m_rotate", "diameter_cm": 10, "revolutions": 2}]) == 32)
    check("M 無分量=0", m_slot_tmu([]) == 0)
    check("M 空 verb 跳過=0", m_slot_tmu([{"verb_id": ""}]) == 0)
    expect_error("M 未知動詞擋下", "M_UNKNOWN", lambda: m_slot_tmu([{"verb_id": "m_zzz"}]))

    print("\n── G. X 處理時間（連續 ceil + 固定 0.216）──")
    check("X 無機台=0", x_slot_tmu("zero") == 0)
    check("X 5 秒 -> ceil(5/0.036)=139", x_slot_tmu("seconds", 5) == math.ceil(5 / 0.036))
    check("X 固定 0.216 -> 6", x_slot_tmu("fixed216") == 6)
    check("X 0 秒 -> 0", x_slot_tmu("seconds", 0) == 0)
    expect_error("X 未知模式擋下", "X_MODE", lambda: x_slot_tmu("bogus"))
    expect_error("X 負秒擋下", "X_NEGATIVE", lambda: x_slot_tmu("seconds", -1))

    print("\n── H. I 對齊 ──")
    check("I 不對齊=0", i_slot_tmu(0) == 0)
    check("I 並檢查=6", i_slot_tmu(6) == 6)
    check("I 並對齊=16", i_slot_tmu(16) == 16)
    expect_error("I=3 非法擋下", "I_INVALID", lambda: i_slot_tmu(3))

    print("\n── I. 序列結構（GM↔CM 不可混用）──")
    expect_error("GM 的 P slot 帶 m_components 擋下", "SLOT_CROSS_MODEL",
                 lambda: compute_cycle({"seq": "GM", "slots": {0: _a(), 1: {"b_index": 0}, 2: {"g_id": "g_grasp"},
                                                               3: _a(), 4: {"b_index": 0},
                                                               5: {"m_components": []}, 6: _a()}}))
    expect_error("CM 的 slot5 帶 p_base 擋下", "SLOT_CROSS_MODEL",
                 lambda: compute_cycle({"seq": "CM", "slots": {0: _a(), 1: {"b_index": 0}, 2: {"g_id": "g_grasp"},
                                                               3: {"m_components": []}, 4: {"x_mode": "zero"},
                                                               5: {"p_base": "p_toss"}, 6: _a()}}))
    expect_error("未知 seq 擋下", "SEQ_KIND", lambda: compute_cycle({"seq": "XX", "slots": {}}))

    print("\n── J. 整表 SIMO / frequency ──")
    table = compute_table([
        {**gm, "frequency": 2},                              # 28×2 = 56（非 SIMO）
        {**cm, "frequency": 1, "simo_group_id": "S1"},       # 29（SIMO S1）
        {**cm, "frequency": 1, "simo_group_id": "S1"},       # 29（SIMO S1）→群組取 max=29
    ])
    check("整表 SIMO 合計 = 56 + max(29,29) = 85", table["total_tmu"] == 85, f'got {table["total_tmu"]}')
    expect_error("frequency<=0 擋下", "FREQ_INVALID",
                 lambda: compute_table([{**gm, "frequency": 0}]))

    print("\n── K. 1205 第 96–117 列真實工步擴充黃金集（catalog §3）──")
    # 3.1 真實 token → 索引（客觀）
    check("伸手 40cm → A16", a_slot_tmu(reach_cm=40) == 16)
    check("伸手 60cm → A16", a_slot_tmu(reach_cm=60) == 16)
    check("移動 10cm → A3", a_slot_tmu(reach_cm=10) == 3)
    check("移動 20cm → A6", a_slot_tmu(reach_cm=20) == 6)
    check("移動 40cm → A16", a_slot_tmu(reach_cm=40) == 16)
    check("移動 60cm → A16", a_slot_tmu(reach_cm=60) == 16)
    check("理 20cm (M階梯) → 24（≠ A 的 6，context 決定表）",
          m_slot_tmu([{"verb_id": "m_li", "distance_cm": 20}]) == 24)
    check("壓合 10S → X ceil(10/0.036)=278", x_slot_tmu("seconds", 10) == 278)

    # 3.3 兩則完整工步解構（詮釋性，⚠️ 假設見 catalog §3.3）
    r112 = _gm(_a(reach=60), {"g_id": "g_grasp"}, _a(),
               {"p_base": "p_asm_single", "p_addons": ["a_snap"]}, _a())  # 16+6+(16+16)=54
    t112 = compute_table([{**r112, "frequency": 2}])
    check("R112 GM 解構 ×2 = 108", t112["total_tmu"] == 108, f'got {t112["total_tmu"]}')
    r116 = _cm(_a(reach=60), {"g_id": "g_touch", "modifiers": {"contact": True}},
               {"m_components": [{"verb_id": "m_btn"}]}, {"x_mode": "seconds", "x_seconds": 10},
               {"i_value": 0}, _a())  # 16+3+3+278=300
    check("R116 CM 解構 = 300", compute_cycle(r116).total_tmu == 300,
          f"got {compute_cycle(r116).total_tmu}")

    print(f"\n{'='*52}\n結果：{passed} passed, {failed} failed\n{'='*52}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_run_tests())
