"""most_engine：MiniMOST GM/CM 唯一計算引擎（讀 RuleSetData，演算法由黃金測試鎖）。

這是 scripts/core_logic 驗證器與 seed mini-compute 的「正式版」：演算法相同，但**讀資料**而非硬編。
cycle DTO（slot_inputs 形狀）＝本引擎與前端的共同契約；以各表 `code` 作穩定參照。
TMU 口徑：合計 = (Σ slot index) × rule_set.multiplier；1 TMU = 0.036 秒；X 為 half-up 3 位（ADR-014 E2）。
V2（ADR-014）：A3 僅 reach、G 無 gating（資料驅動）、P 插入⊥卡合、slot repeat、人工覆寫留痕。
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
    slot_tmus: list[float]
    letters: tuple[str, ...]
    total_tmu: float
    total_seconds: float
    tech_line: str
    overrides: tuple[dict[str, Any], ...] = ()  # E7：人工覆寫紀錄（auto/override/reason/by）

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "slot_tmus": self.slot_tmus,
            "breakdown": [{"letter": L, "tmu": t} for L, t in zip(self.letters, self.slot_tmus)],
            "total_tmu": self.total_tmu,
            "total_seconds": self.total_seconds,
            "tech_line": self.tech_line,
            "overrides": list(self.overrides),
        }


_REPEAT_MAX = 99  # 殘項#4：上限待 IE 拍板


def _repeat(slot: dict[str, Any]) -> int:
    """E4：slot 級重複次數（G/P/M/X/I）。預設 1；非整數/超界 → REPEAT_INVALID。"""
    rc = slot.get("repeat_count")
    if rc is None:
        return 1
    if isinstance(rc, bool) or not isinstance(rc, (int, float)) or float(rc) != int(rc) or not (1 <= int(rc) <= _REPEAT_MAX):
        raise SequenceError("REPEAT_INVALID", f"repeat_count 須為 1..{_REPEAT_MAX} 的整數，收到 {rc!r}")
    return int(rc)


def _no_repeat(slot: dict[str, Any], letter: str) -> None:
    if slot.get("repeat_count") not in (None, 1):
        raise SequenceError("REPEAT_INVALID", f"{letter} 格不支援 repeat_count")


# ── slot 計算（讀 rs）──
def _a_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    _no_repeat(slot, "A")
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


def _a_return_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    """E1（ADR-014）：返回格僅計伸手；twist/foot 非零 → A_RETURN_COMPONENT（零值容忍，兼容舊 payload 形狀）。"""
    _no_repeat(slot, "A")
    for key in ("twist_deg", "foot_cm"):
        v = slot.get(key)
        if v:
            raise SequenceError("A_RETURN_COMPONENT", f"返回格僅計伸手，不可含 {key}={v}")
    reach = slot.get("reach_cm", 0) or 0
    if reach < 0:
        raise SequenceError("A_NEGATIVE", f"reach_cm 不可為負：{reach}")
    idx = rs.band_index("reach", reach)
    return idx if idx is not None else 0


def _b_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    _no_repeat(slot, "B")
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
        return 0  # 需勾修飾但未勾 → 視為未完成（V1 資料；V2 全 requires_modifier=False——ADR-014）
    return g.base_tmu * _repeat(slot)


def _p_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    base = slot.get("p_base_code")
    addons = slot.get("p_addon_codes") or []
    if not base:
        if addons:
            raise SequenceError("P_ADDON_NO_BASE", "P 有附加條件時必須選擇基礎動作")  # E3（v3 認證）
        return 0
    if base not in rs.p_bases:
        raise SequenceError("P_UNKNOWN", f"未知 P 基底：{base}")
    if len(addons) > rs.p_addon_max:
        raise SequenceError("P_TOO_MANY_ADDONS", f"P 附加最多 {rs.p_addon_max} 個，收到 {len(addons)}")
    if len(set(addons)) != len(addons):
        raise SequenceError("P_DUP_ADDON", f"P 附加重複：{addons}")
    if "a_insert" in addons and "a_snap" in addons:
        raise SequenceError("P_ADDON_CONFLICT", "插入與卡合不可同時選擇")  # E3（v3 認證）
    precision = bool(slot.get("precision"))
    total = rs.p_bases[base]
    for a in addons:
        if a not in rs.p_addons:
            raise SequenceError("P_ADDON_UNKNOWN", f"未知 P 附加：{a}")
        addon = rs.p_addons[a]
        if addon.needs_precision and not precision:
            continue
        total += addon.delta_tmu
    return total * _repeat(slot)


def _m_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    """E4/E9：repeat 只乘動詞類分量（fixed/ladder/rotate）再進 max，手度/腳步不乘（v3 認證）；
    超出值表（V2 無 overflow 檔）→ 範圍錯誤，不得靜默套最大檔。"""
    rep = _repeat(slot)
    vals: list[float] = []
    for comp in slot.get("m_components") or []:
        code = comp.get("verb_code")
        if not code:
            continue
        if code not in rs.m_verbs:
            raise SequenceError("M_UNKNOWN", f"未知 M 動詞：{code}")
        kind, fixed = rs.m_verbs[code]
        if kind == "fixed":
            vals.append(int(fixed or 0) * rep)
        elif kind == "ladder":
            cm = comp.get("distance_cm", 0) or 0
            t = rs.ladder_tmu(cm)
            if t is None:
                raise SequenceError("M_DISTANCE_RANGE", f"距離 {cm}cm 超出階梯值表（最大 75cm）")
            vals.append(t * rep)
        elif kind == "foot":
            cm = comp.get("distance_cm", 0) or 0
            t = rs.foot_tmu(cm)
            if t is None:
                raise SequenceError("M_DISTANCE_RANGE", f"腳步 {cm}cm 超出值表")
            vals.append(t)
        elif kind == "hand":
            deg = comp.get("angle_deg", 0) or 0
            t = rs.hand_tmu(deg)
            if t is None:
                raise SequenceError("M_HAND_RANGE", f"手度 {deg}° 超出值表（最大 180°）")
            vals.append(t)
        elif kind == "rotate":
            dia, rev = comp.get("diameter_cm", 0) or 0, comp.get("revolutions", 1) or 1
            t = rs.rotation_tmu(dia, rev)
            if t is None:
                raise SequenceError("M_ROTATION_RANGE", f"旋轉 直徑{dia}cm×{rev}圈 超出值表")
            vals.append(t * rep)
        else:
            raise SequenceError("M_KIND", f"未支援的 M 計價：{kind}")
    return max(vals) if vals else 0


def _x_tmu(slot: dict[str, Any], rs: RuleSetData) -> float:
    code = slot.get("x_code")
    if not code:
        return 0
    if code not in rs.x_options:
        raise SequenceError("X_UNKNOWN", f"未知 X 選項：{code}")
    rep = _repeat(slot)
    mode, fixed_seconds = rs.x_options[code]
    if mode == "zero":
        return 0
    if mode == "fixed":
        if fixed_seconds is None:
            raise ValueError("Rule-set X entry has mode='fixed' but fixed_seconds is NULL")
        return rs.seconds_to_tmu(float(fixed_seconds)) * rep
    # CL-01 §2 X（v3 認證）：mode=seconds 必須輸入正數秒數。負值先攔為 X_NEGATIVE（語意
    # 區分「方向錯誤」與「未填/0」，且沿用既有反例）；未填/0 → X_SECONDS_REQUIRED。
    seconds = slot.get("x_seconds", 0)
    if seconds is not None and seconds < 0:
        raise SequenceError("X_NEGATIVE", f"秒數不可為負：{seconds}")
    if not seconds:
        raise SequenceError("X_SECONDS_REQUIRED", "X 動態秒數項目必須輸入正數秒數")
    return rs.seconds_to_tmu(seconds) * rep


def _i_tmu(slot: dict[str, Any], rs: RuleSetData) -> int:
    code = slot.get("i_code")
    if not code:
        return 0
    if code not in rs.i_index:
        raise SequenceError("I_UNKNOWN", f"未知 I 選項：{code}")
    return rs.i_index[code] * _repeat(slot)


_COMMON_SLOT_KEYS = {"repeat_count", "manual_override"}
_GM_SLOT_KEYS = {3: {"reach_cm", "twist_deg", "foot_cm"} | _COMMON_SLOT_KEYS, 4: {"b_code"} | _COMMON_SLOT_KEYS, 5: {"p_base_code", "p_addon_codes", "precision"} | _COMMON_SLOT_KEYS}
_CM_SLOT_KEYS = {3: {"m_components"} | _COMMON_SLOT_KEYS, 4: {"x_code", "x_seconds"} | _COMMON_SLOT_KEYS, 5: {"i_code"} | _COMMON_SLOT_KEYS}


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

    t: list[float] = [0] * 7
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
    t[6] = _a_return_tmu(slot(6), rs)

    # E7：人工覆寫（值取代、驗證嚴格、全程留痕）
    overrides: list[dict[str, Any]] = []
    for i in range(7):
        ov = slot(i).get("manual_override")
        if ov is None:
            continue
        tmu, reason = ov.get("tmu"), (ov.get("reason") or "").strip()
        if isinstance(tmu, bool) or not isinstance(tmu, (int, float)) or tmu < 0 or not reason:
            raise SequenceError("OVERRIDE_INVALID", f"slot{i} 人工覆寫需 tmu≥0 且 reason 非空")
        overrides.append({"slot": i, "letter": letters[i], "auto_tmu": t[i],
                          "override_tmu": float(tmu), "reason": reason, "by": ov.get("by")})
        t[i] = float(tmu)

    ov_slots = {o["slot"] for o in overrides}
    total = round(sum(t) * rs.multiplier, 3)
    tech = " ".join(f"{L}{v:g}{'*' if i in ov_slots else ''}" for i, (L, v) in enumerate(zip(letters, t)))
    return CycleResult(seq, t, letters, total, round(total * TMU_TO_SEC, 4), tech, tuple(overrides))


def compute_table(steps: list[dict[str, Any]], rs: RuleSetData) -> dict[str, Any]:
    """多列 WI 合計（ADR-020，對齊 v3 認證語義）：帶 SIMO 標記（simo_group_id 非空）
    的列貢獻 0——其時間由未標記的主列吸收；總計 = Σ(未標記列 tmu×freq)。"""
    total_f = 0.0
    rows = []
    for idx, step in enumerate(steps):
        freq = step.get("frequency", 1)
        if freq is None or freq <= 0:
            raise SequenceError("FREQ_INVALID", f"列 {idx}: frequency 須 >0")
        r = compute_cycle(step, rs)
        eff = r.total_tmu * freq
        is_simo = bool(step.get("simo_group_id"))
        if not is_simo:
            total_f += eff
        rows.append({"index": idx, "tmu": r.total_tmu, "freq": freq, "eff_tmu": eff,
                     "simo": is_simo, "tech_line": r.tech_line})
    total = round(total_f, 3)
    return {"rows": rows, "total_tmu": total, "total_seconds": round(total * TMU_TO_SEC, 4)}
