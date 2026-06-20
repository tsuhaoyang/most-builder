"""most_engine：MiniMOST GM/CM 唯一計算引擎（讀 RuleSetData，演算法由黃金測試鎖）。

這是 scripts/core_logic 驗證器與 seed mini-compute 的「正式版」：演算法相同，但**讀資料**而非硬編。
cycle DTO（slot_inputs 形狀）＝本引擎與前端的共同契約；以各表 `code` 作穩定參照。
TMU 口徑：合計 = (Σ slot index) × rule_set.multiplier；1 TMU = 0.036 秒（spec 已確認）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ddm_v2.most_engine.rule_set_data import TMU_TO_SEC, RuleSetData

GM_LETTERS = ("A", "B", "G", "A", "B", "P", "A")
CM_LETTERS = ("A", "B", "G", "M", "X", "I", "A")


class SequenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


@dataclass(frozen=True)
class CycleResult:
    seq: str
    slot_tmus: list[int]
    letters: tuple[str, ...]
    total_tmu: float
    total_seconds: float
    tech_line: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "slot_tmus": self.slot_tmus,
            "breakdown": [{"letter": L, "tmu": t} for L, t in zip(self.letters, self.slot_tmus)],
            "total_tmu": self.total_tmu,
            "total_seconds": self.total_seconds,
            "tech_line": self.tech_line,
        }


# ── slot 計算（讀 rs）──
def _a_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    for key in ("reach_cm", "twist_deg", "foot_cm"):
        v = slot.get(key, 0)
        if v is not None and v < 0:
            raise SequenceError("A_NEGATIVE", f"{key} 不可為負：{v}")
    parts = [
        rs.band_index("reach", slot.get("reach_cm", 0) or 0),
        rs.band_index("twist", slot.get("twist_deg", 0) or 0),
        rs.band_index("foot", slot.get("foot_cm", 0) or 0),
    ]
    present = [p for p in parts if p is not None]
    return max(present) if present else 0


def _b_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    code = slot.get("b_code") or rs.b_default
    if code is None:
        return 0
    if code not in rs.b_index:
        raise SequenceError("B_UNKNOWN", f"未知 B 選項：{code}")
    return rs.b_index[code]


def _g_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    code = slot.get("g_code")
    if not code:
        return 0
    if code not in rs.g_actions:
        raise SequenceError("G_UNKNOWN", f"未知 G 選項：{code}")
    g = rs.g_actions[code]
    modifiers = slot.get("modifiers") or {}
    if g.requires_modifier and g.modifier_key and not modifiers.get(g.modifier_key):
        return 0  # 需勾修飾但未勾 → 視為未完成
    return g.base_tmu


def _p_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    base = slot.get("p_base_code")
    if not base:
        return 0
    if base not in rs.p_bases:
        raise SequenceError("P_UNKNOWN", f"未知 P 基底：{base}")
    addons = slot.get("p_addon_codes") or []
    if len(addons) > rs.p_addon_max:
        raise SequenceError("P_TOO_MANY_ADDONS", f"P 附加最多 {rs.p_addon_max} 個，收到 {len(addons)}")
    if len(set(addons)) != len(addons):
        raise SequenceError("P_DUP_ADDON", f"P 附加重複：{addons}")
    precision = bool(slot.get("precision"))
    total = rs.p_bases[base]
    for a in addons:
        if a not in rs.p_addons:
            raise SequenceError("P_ADDON_UNKNOWN", f"未知 P 附加：{a}")
        addon = rs.p_addons[a]
        if addon.needs_precision and not precision:
            continue
        total += addon.delta_tmu
    return total


def _m_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    vals: list[int] = []
    for comp in slot.get("m_components") or []:
        code = comp.get("verb_code")
        if not code:
            continue
        if code not in rs.m_verbs:
            raise SequenceError("M_UNKNOWN", f"未知 M 動詞：{code}")
        kind, fixed = rs.m_verbs[code]
        if kind == "fixed":
            vals.append(int(fixed or 0))
        elif kind in ("ladder", "foot"):
            vals.append(rs.ladder_tmu(comp.get("distance_cm", 0) or 0))
        elif kind == "hand":
            vals.append(rs.hand_tmu(comp.get("angle_deg", 0) or 0))
        elif kind == "rotate":
            vals.append(rs.rotation_tmu(comp.get("diameter_cm", 0) or 0, comp.get("revolutions", 1) or 1))
        else:
            raise SequenceError("M_KIND", f"未支援的 M 計價：{kind}")
    return max(vals) if vals else 0


def _x_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    code = slot.get("x_code")
    if not code:
        return 0
    if code not in rs.x_options:
        raise SequenceError("X_UNKNOWN", f"未知 X 選項：{code}")
    mode, fixed_seconds = rs.x_options[code]
    if mode == "zero":
        return 0
    if mode == "fixed":
        return rs.seconds_to_tmu(float(fixed_seconds or 0))
    seconds = slot.get("x_seconds", 0)
    if seconds is not None and seconds < 0:
        raise SequenceError("X_NEGATIVE", f"秒數不可為負：{seconds}")
    return rs.seconds_to_tmu(seconds or 0)


def _i_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    code = slot.get("i_code")
    if not code:
        return 0
    if code not in rs.i_index:
        raise SequenceError("I_UNKNOWN", f"未知 I 選項：{code}")
    return rs.i_index[code]


_GM_SLOT_KEYS = {3: {"reach_cm", "twist_deg", "foot_cm"}, 4: {"b_code"}, 5: {"p_base_code", "p_addon_codes", "precision"}}
_CM_SLOT_KEYS = {3: {"m_components"}, 4: {"x_code", "x_seconds"}, 5: {"i_code"}}


def _reject_cross_model(seq: str, idx: int, slot: dict[str, Any]) -> None:
    allowed = (_GM_SLOT_KEYS if seq == "GM" else _CM_SLOT_KEYS)[idx]
    foreign = set(slot.keys()) - allowed
    if foreign:
        raise SequenceError("SLOT_CROSS_MODEL", f"{seq} slot{idx} 不可含 {sorted(foreign)}（GM↔CM 不可混用）")


def compute_cycle(cycle: dict[str, Any], rs: RuleSetData) -> CycleResult:
    """計算一條 GM/CM cycle。會驗證序列結構與所有 slot。"""
    seq = cycle.get("seq")
    if seq not in ("GM", "CM"):
        raise SequenceError("SEQ_KIND", f"sequence 必須是 GM/CM，收到 {seq!r}")
    s = cycle.get("slots", {})

    def slot(i: int) -> dict[str, Any]:
        return s.get(i) or {}

    t = [0] * 7
    t[0] = _a_tmu(slot(0), rs)
    t[1] = _b_tmu(slot(1), rs)
    t[2] = _g_tmu(slot(2), rs)
    for i in (3, 4, 5):
        _reject_cross_model(seq, i, slot(i))
    if seq == "GM":
        t[3] = _a_tmu(slot(3), rs)
        t[4] = _b_tmu(slot(4), rs)
        t[5] = _p_tmu(slot(5), rs)
        letters = GM_LETTERS
    else:
        t[3] = _m_tmu(slot(3), rs)
        t[4] = _x_tmu(slot(4), rs)
        t[5] = _i_tmu(slot(5), rs)
        letters = CM_LETTERS
    t[6] = _a_tmu(slot(6), rs)

    total = sum(t) * rs.multiplier
    tech = " ".join(f"{L}{v}" for L, v in zip(letters, t))
    return CycleResult(seq, t, letters, total, round(total * TMU_TO_SEC, 6), tech)


def compute_table(steps: list[dict[str, Any]], rs: RuleSetData) -> dict[str, Any]:
    """多列 WI 合計：Σ(非SIMO tmu×freq) + Σ(每 SIMO 群組 max(tmu×freq))。"""
    non_simo = 0.0
    simo: dict[str, float] = {}
    rows = []
    for idx, step in enumerate(steps):
        freq = step.get("frequency", 1)
        if freq is None or freq <= 0:
            raise SequenceError("FREQ_INVALID", f"列 {idx}: frequency 須 >0")
        r = compute_cycle(step, rs)
        eff = r.total_tmu * freq
        gid = step.get("simo_group_id")
        if gid:
            simo[gid] = max(simo.get(gid, 0.0), eff)
        else:
            non_simo += eff
        rows.append({"index": idx, "tmu": r.total_tmu, "freq": freq, "eff_tmu": eff, "tech_line": r.tech_line})
    total = non_simo + sum(simo.values())
    return {"rows": rows, "total_tmu": total, "total_seconds": round(total * TMU_TO_SEC, 6)}
