"""RuleSetData：引擎消費的「已載入規則集」純值物件（無 DB、無框架）。

設計（system-architecture-v2 §3 / data-model §1.5）：
- 規則＝資料；演算法＝程式。本物件持有「資料」與「如何正確讀這份資料」的純查表 helper。
- 由 providers 從 DB 或 seed 建構（見 providers.py）；most_engine 只依賴本物件。
- band 以 (max_value, ...) 排序，max_value=None 代表 overflow（超過所有有限帶時採用）。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

TMU_TO_SEC = 0.036
_TMU_TO_SEC_D = Decimal("0.036")
_Q3 = Decimal("0.001")

# 認證字典的 `parameters.M.controls` 是三個平行控制群（verb／hand_degree／foot_step），
# v2 把它們壓扁成單一 `rule_m_verbs` 清單、靠 `pricing_kind` 區辨：`hand`／`foot` 是**伴隨
# 維度**（按手轉角度／腳步距離查表），其餘是動詞。字典的兩條規則都掛在這個集合上——
# `verb.required=true`（伴隨維度不得單獨成格）與「伴隨維度無句面」（不入敘事句）——
# 所以它只能有一份：引擎驗證（`calculate._m_tmu`）與中英兩套敘事樣板共用同一個定義。
M_COMPANION_KINDS = frozenset({"hand", "foot"})


class RuleSetIncomplete(ValueError):
    """rule-set 缺必要表 → 不可用於計算（完整性 gating，E5）。"""


class GAction(NamedTuple):
    modifier_key: str | None
    requires_modifier: bool
    base_tmu: int


class PAddon(NamedTuple):
    delta_tmu: int
    needs_precision: bool


@dataclass(frozen=True)
class RuleSetData:
    code: str
    multiplier: float
    # A 三分量：component -> 已排序 ((max_value|None, index), ...)
    a_bands: dict[str, tuple[tuple[float | None, int], ...]]
    b_index: dict[str, int]
    b_default: str | None
    g_actions: dict[str, GAction]
    p_bases: dict[str, int]
    p_addons: dict[str, PAddon]
    p_addon_max: int
    m_ladder: tuple[tuple[float | None, int], ...]
    m_verbs: dict[str, tuple[str, int | None]]  # code -> (pricing_kind, fixed_tmu)
    m_rotation: tuple[tuple[float | None, int, int], ...]  # (max_dia, revolutions, tmu)
    m_hand: tuple[tuple[float | None, int], ...]
    x_options: dict[str, tuple[str, float | None]]  # code -> (mode, fixed_seconds)
    i_index: dict[str, int]
    m_foot: tuple[tuple[float | None, int], ...] = ()  # V2 起：M 腳步獨立帶；空=回退 ladder（V1 回放相容）

    # ── 純查表 helper（「如何讀這份資料」）──
    def band_index(self, component: str, value: float) -> int | None:
        """A 單一分量：value<=0 → None（無貢獻）；否則第一個 max>=value 的 index；overflow 用 None 帶。"""
        if value is None or value <= 0:
            return None
        bands = self.a_bands.get(component, ())
        for max_value, idx in bands:
            if max_value is None or value <= max_value:
                return idx
        return bands[-1][1] if bands else None

    def ladder_tmu(self, cm: float) -> int | None:
        """距離階梯。超出最大有限帶且無 overflow 帶 → None（引擎轉 M_DISTANCE_RANGE）。"""
        if not cm or cm <= 0:
            return 0
        for max_cm, tmu in self.m_ladder:
            if max_cm is None or cm <= max_cm:
                return tmu
        return None

    def foot_tmu(self, cm: float) -> int | None:
        """M 腳步帶（V2）；rule-set 無 foot 資料（V1）→ 回退 ladder（回放相容，E9）。"""
        if not self.m_foot:
            return self.ladder_tmu(cm)
        if not cm or cm <= 0:
            return 0
        for max_cm, tmu in self.m_foot:
            if max_cm is None or cm <= max_cm:
                return tmu
        return None

    def rotation_tmu(self, diameter_cm: float, revolutions: int) -> int | None:
        """旋轉查表。無對應（直徑/圈數超出值表）→ None（引擎轉 M_ROTATION_RANGE）。"""
        rev = max(1, min(3, int(round(revolutions or 1))))
        for max_dia, rv, tmu in self.m_rotation:
            if rv == rev and (max_dia is None or diameter_cm <= max_dia):
                return tmu
        return None

    def hand_tmu(self, deg: float) -> int | None:
        """手度查表。超出（>180 且無 overflow）→ None（引擎轉 M_HAND_RANGE）。"""
        if not deg or deg <= 0:
            return 0
        for max_deg, tmu in self.m_hand:
            if max_deg is None or deg <= max_deg:
                return tmu
        return None

    @staticmethod
    def seconds_to_tmu(seconds: float) -> float:
        """秒→TMU：Decimal 除法 ROUND_HALF_UP 保留 3 位（E2，ADR-014 取代舊 ceil 裁決）。"""
        if seconds is None or seconds <= 0:
            return 0.0
        return float((Decimal(str(seconds)) / _TMU_TO_SEC_D).quantize(_Q3, rounding=ROUND_HALF_UP))

    def validate_complete(self) -> None:
        """發布/使用前完整性檢查：缺任一必要表即報錯（不可默默回 0）。"""
        missing: list[str] = []
        for comp in ("reach", "twist", "foot"):
            if not self.a_bands.get(comp):
                missing.append(f"a_bands[{comp}]")
        if not self.b_index:
            missing.append("b_options")
        if not self.g_actions:
            missing.append("g_actions")
        if not self.p_bases:
            missing.append("p_bases")
        if not self.m_ladder:
            missing.append("m_ladder")
        if not self.m_verbs:
            missing.append("m_verbs")
        if not self.x_options:
            missing.append("x_options")
        if not self.i_index:
            missing.append("i_options")
        if missing:
            raise RuleSetIncomplete(f"rule-set '{self.code}' 缺必要表：{', '.join(missing)}")


def _sort_bands(rows: list[tuple[float | None, int]]) -> tuple[tuple[float | None, int], ...]:
    """有限帶由小到大，overflow（None）置末。"""
    return tuple(sorted(rows, key=lambda r: (r[0] is None, r[0] if r[0] is not None else 0.0)))


def build_rule_set_data(
    *,
    code: str,
    multiplier: float,
    a_bands_rows: list[tuple[str, float | None, int]],   # (component, max_value, index)
    b_rows: list[tuple[str, int, bool]],                  # (code, index, is_default)
    g_rows: list[tuple[str, str | None, bool, int]],      # (code, modifier_key, requires_modifier, base_tmu)
    p_base_rows: list[tuple[str, int]],                   # (code, base_tmu)
    p_addon_rows: list[tuple[str, int, bool]],            # (code, delta, needs_precision)
    p_addon_max: int,
    m_ladder_rows: list[tuple[float | None, int]],        # (max_cm, tmu)
    m_verb_rows: list[tuple[str, str, int | None]],       # (code, pricing_kind, fixed_tmu)
    m_rotation_rows: list[tuple[float | None, int, int]], # (max_dia, revolutions, tmu)
    m_hand_rows: list[tuple[float | None, int]],          # (max_deg, tmu)
    x_rows: list[tuple[str, str, float | None]],          # (code, mode, fixed_seconds)
    i_rows: list[tuple[str, int]],                        # (code, index)
    m_foot_rows: list[tuple[float | None, int]] | None = None,  # (max_cm, tmu)；None/空＝V1 無獨立腳步帶
) -> RuleSetData:
    """通用建構：供 providers（in-memory / DB）共用，確保形狀一致。"""
    a_bands: dict[str, list[tuple[float | None, int]]] = {}
    for comp, mx, idx in a_bands_rows:
        a_bands.setdefault(comp, []).append((mx, idx))
    b_default = next((c for c, _i, d in b_rows if d), None)
    return RuleSetData(
        code=code,
        multiplier=multiplier,
        a_bands={c: _sort_bands(v) for c, v in a_bands.items()},
        b_index={c: i for c, i, _d in b_rows},
        b_default=b_default,
        g_actions={c: GAction(mk, req, tmu) for c, mk, req, tmu in g_rows},
        p_bases={c: tmu for c, tmu in p_base_rows},
        p_addons={c: PAddon(delta, prec) for c, delta, prec in p_addon_rows},
        p_addon_max=p_addon_max,
        m_ladder=_sort_bands(m_ladder_rows),
        m_verbs={c: (kind, ftmu) for c, kind, ftmu in m_verb_rows},
        m_rotation=tuple(m_rotation_rows),
        m_hand=_sort_bands(m_hand_rows),
        x_options={c: (mode, fsec) for c, mode, fsec in x_rows},
        i_index={c: i for c, i in i_rows},
        m_foot=_sort_bands(m_foot_rows) if m_foot_rows else (),
    )
