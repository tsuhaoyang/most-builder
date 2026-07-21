"""選項級 CRUD 的 payload schema ＋ (param, section) → 子表/schema 分派表（ADR-023 D2）。

**為什麼不是 Pydantic 的 `Field(discriminator=...)`**：v3 用單一泛型表 `parameter_options`，
所以能靠 body 內的欄位判別；v2 是 12 張**不同構**的專用子表（ADR-023 §2），判別鍵在
**URL 的 param + section**，不在 body。因此這裡的「discriminated union」實作為
`resolve(param, section)` 的顯式分派表——同樣的效果（一種 payload 對一種 schema），
但判別來源正確。

兩種形狀（ADR-023 §2 的結構性約束）：
- `kind="options"`：有 `code` 的選項表 → 單筆 CRUD（B / G / P.base / P.addon / M.verb / X / I）
- `kind="bands"`：**區間帶**表，無「選項代碼」概念 → 只能整組替換（A / M.ladder /
  M.foot / M.rotation / M.hand）。單筆增刪不提供，因為帶界必須整體遞增無重疊，
  逐筆編輯會讓中間態非法。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ddm_v2.models.v2 import rule_set_tables as rt


class SectionRequired(ValueError):
    """param 有多個次級區塊但呼叫端未指定 section（不得靜默選一個）。"""

    def __init__(self, param: str, allowed: list[str], query_name: str = "section") -> None:
        self.param = param
        self.allowed = allowed
        self.query_name = query_name
        super().__init__(
            f"參數 {param} 需指定 ?{query_name}=，合法值：{'|'.join(allowed)}"
        )


class SectionInvalid(ValueError):
    def __init__(self, param: str, section: str, allowed: list[str], query_name: str = "section") -> None:
        self.param = param
        self.allowed = allowed
        self.query_name = query_name
        super().__init__(
            f"參數 {param} 不接受 {query_name}={section}，合法值：{'|'.join(allowed)}"
        )


class ParamInvalid(ValueError):
    def __init__(self, param: str, allowed: list[str]) -> None:
        super().__init__(f"未知參數 {param}，合法值：{'|'.join(allowed)}")


class _Strict(BaseModel):
    # 未知欄位一律拒收：打錯欄位名要 422，不能靜默丟棄（否則使用者以為改了值其實沒改）。
    model_config = ConfigDict(extra="forbid")


# ── 選項型（有 code）──────────────────────────────────────────────
class _OptionIn(_Strict):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    label_zh: str = Field(min_length=1)
    label_en: str | None = None
    sentence_text_zh: str | None = None
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class BOptionIn(_OptionIn):
    index_value: int = Field(ge=0)
    is_default: bool = False


class GActionIn(_OptionIn):
    modifier_key: str | None = None
    requires_modifier: bool = False
    base_tmu: int = Field(ge=0)


class PBaseIn(_OptionIn):
    category: str | None = None
    direction_mode: str | None = None
    base_tmu: int = Field(ge=0)


class PAddonIn(_OptionIn):
    delta_tmu: int = Field(ge=0)
    needs_precision: bool = False
    # 引擎取 min(max_select) 當 p_addon_max（providers.py），故全表須一致——
    # 一致性由 service 層跨列檢查（本 schema 只管單列合法性）。
    max_select: int = Field(default=2, ge=1, le=10)
    display_rule: Literal["show_self", "hidden", "prefix_visible_term"] = "show_self"


class MVerbIn(_OptionIn):
    pricing_kind: Literal["fixed", "ladder", "foot", "hand", "rotate"]
    fixed_tmu: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _fixed_needs_tmu(self) -> MVerbIn:
        if self.pricing_kind == "fixed" and self.fixed_tmu is None:
            raise ValueError("pricing_kind=fixed 時必須給 fixed_tmu（否則引擎算不出值）")
        return self


class XOptionIn(_OptionIn):
    mode: Literal["zero", "seconds", "fixed"]
    fixed_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _fixed_needs_seconds(self) -> XOptionIn:
        if self.mode == "fixed" and self.fixed_seconds is None:
            raise ValueError("mode=fixed 時必須給 fixed_seconds")
        return self


class IOptionIn(_OptionIn):
    index_value: int = Field(ge=0)
    vision_scope: Literal["normal", "outside"] | None = None


# ── 帶型（無 code，整組替換）────────────────────────────────────────
class ABandIn(_Strict):
    max_value: float | None = Field(default=None, gt=0)  # NULL＝open-ended（僅末帶可用）
    index_value: int = Field(ge=0)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class MLadderBandIn(_Strict):
    max_cm: float | None = Field(default=None, gt=0)
    tmu: int = Field(ge=0)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class MFootBandIn(MLadderBandIn):
    pass


class MRotationBandIn(_Strict):
    max_diameter_cm: float | None = Field(default=None, gt=0)
    revolutions: int = Field(ge=1, le=3)
    tmu: int = Field(ge=0)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class MHandBandIn(_Strict):
    max_deg: float | None = Field(default=None, gt=0)
    tmu: int = Field(ge=0)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class BandsReplaceIn(_Strict):
    """整組替換的 body。"""

    items: list[dict[str, Any]] = Field(min_length=1)


class BandInvalid(ValueError):
    """帶界不合法：未遞增 / 重疊 / open-ended 不在末位 / 物理無上界者缺 open-ended 末帶。"""


@dataclass(frozen=True)
class OptionSpec:
    param: str
    section: str
    # Any 而非 type[Base]：12 張子表無共同 mixin 宣告 rule_set_id/code/sort_order，
    # 標成 type 會讓 mypy 對每個欄位存取報 attr-defined（見 D2 mypy 基線）。
    model: Any
    schema: type[BaseModel]
    kind: Literal["options", "bands"]
    bound_field: str | None = None       # 帶型的上界欄位名
    group_field: str | None = None       # 帶型的分組欄位（rotation 依 revolutions 各自成序）
    filter_field: str | None = None      # A 三分量共用一張表 → 需 component 欄位過濾
    filter_value: str | None = None
    # 物理上無上界的量 → 末帶必須 open-ended，否則超界輸入會被引擎靜默夾取（見 validate_bands）
    require_open_ended: bool = False


PARAM_SECTIONS: dict[str, list[str]] = {
    "A": ["reach", "twist", "foot"],   # 次級選擇名為 component（ADR-023 D2 規格）
    "B": ["default"],
    "G": ["default"],
    "P": ["base", "addon"],
    "M": ["verb", "ladder", "foot", "rotation", "hand"],
    "X": ["default"],
    "I": ["default"],
}

# A 的次級選擇在規格中叫 component（`?component=reach|twist|foot`），其餘叫 section。
SECTION_QUERY_NAME: dict[str, str] = {"A": "component"}

_SPECS: dict[tuple[str, str], OptionSpec] = {
    ("A", "reach"): OptionSpec("A", "reach", rt.RuleABand, ABandIn, "bands", "max_value", None, "component", "reach", require_open_ended=True),
    ("A", "twist"): OptionSpec("A", "twist", rt.RuleABand, ABandIn, "bands", "max_value", None, "component", "twist"),
    ("A", "foot"): OptionSpec("A", "foot", rt.RuleABand, ABandIn, "bands", "max_value", None, "component", "foot", require_open_ended=True),
    ("B", "default"): OptionSpec("B", "default", rt.RuleBOption, BOptionIn, "options"),
    ("G", "default"): OptionSpec("G", "default", rt.RuleGAction, GActionIn, "options"),
    ("P", "base"): OptionSpec("P", "base", rt.RulePBase, PBaseIn, "options"),
    ("P", "addon"): OptionSpec("P", "addon", rt.RulePAddon, PAddonIn, "options"),
    ("M", "verb"): OptionSpec("M", "verb", rt.RuleMVerb, MVerbIn, "options"),
    ("M", "ladder"): OptionSpec("M", "ladder", rt.RuleMLadderBand, MLadderBandIn, "bands", "max_cm"),
    ("M", "foot"): OptionSpec("M", "foot", rt.RuleMFootBand, MFootBandIn, "bands", "max_cm"),
    ("M", "rotation"): OptionSpec("M", "rotation", rt.RuleMRotationBand, MRotationBandIn, "bands", "max_diameter_cm", "revolutions"),
    ("M", "hand"): OptionSpec("M", "hand", rt.RuleMHandBand, MHandBandIn, "bands", "max_deg"),
    ("X", "default"): OptionSpec("X", "default", rt.RuleXOption, XOptionIn, "options"),
    ("I", "default"): OptionSpec("I", "default", rt.RuleIOption, IOptionIn, "options"),
}

# 分派表必須覆蓋 PARAM_SECTIONS 宣告的每一組——漏一組會在 runtime 才 KeyError。
assert set(_SPECS) == {(p, s) for p, secs in PARAM_SECTIONS.items() for s in secs}


def resolve(param: str, section: str | None) -> OptionSpec:
    """(param, section) → OptionSpec。section 缺省時**不得靜默選一個**：多區塊 param 一律 400。"""
    p = (param or "").strip().upper()
    if p not in PARAM_SECTIONS:
        raise ParamInvalid(param, list(PARAM_SECTIONS))
    allowed = PARAM_SECTIONS[p]
    qname = SECTION_QUERY_NAME.get(p, "section")
    s = (section or "").strip().lower() or None
    if s is None:
        if len(allowed) > 1:
            raise SectionRequired(p, allowed, qname)
        s = allowed[0]
    elif s not in allowed:
        raise SectionInvalid(p, s, allowed, qname)
    return _SPECS[(p, s)]


def effective_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """依「實際落盤順序」排序。

    引擎讀帶表是 `order_by(sort_order)`，而 payload 可能帶顯式 `sort`/`sort_order`
    且與陣列順序不同。驗證必須看引擎會看到的順序，否則「陣列看起來遞增、存進去卻不是」
    會逃過檢查。
    """
    return [
        item for _k, item in sorted(
            ((item.get("sort", item.get("sort_order", i)), i), item)
            for i, item in enumerate(items)
        )
    ]


def validate_bands(spec: OptionSpec, items: list[dict[str, Any]]) -> None:
    """帶界契約：遞增、無重疊、open-ended（None）只能在末位；必要時強制末帶 open-ended。

    表示法是「上界（含）」，所以序列嚴格遞增就天然無洞。末帶為有限值時的行為**依帶族而異**
    （實測，非推測）：
    - **A 三分量**（`rule_set_data.band_index` 末行 `return bands[-1][1]`）→ 超界輸入被
      **靜默夾取到末帶**。例：reach 帶止於 20.0 時輸入 999 仍回 index 6。這違反
      「禁止靜默 fallback」，故對**物理無上界**的 `A.reach` / `A.foot` 強制末帶 open-ended
      （`require_open_ended`）；`A.twist` 物理有界（180°）維持放寬。
    - **ladder / foot / hand / rotation**（`ladder_tmu` 等末行 `return None`）→ 超界回 None，
      引擎轉 `M_DISTANCE_RANGE` / `M_HAND_RANGE` / `M_ROTATION_RANGE` 顯式錯誤，
      故末帶可為有限值。

    rotation 依 `revolutions` 分組，各組各自成序（引擎查表時先比對圈數）。
    """
    bound = spec.bound_field
    assert bound is not None
    ordered = effective_order(items)
    groups: dict[Any, list[dict[str, Any]]] = {}
    for item in ordered:
        key = item[spec.group_field] if spec.group_field else None
        groups.setdefault(key, []).append(item)

    for key, group in groups.items():
        where = f"（{spec.group_field}={key}）" if spec.group_field else ""
        prev: float | None = None
        for pos, item in enumerate(group):
            value = item[bound]
            if value is None:
                if pos != len(group) - 1:
                    raise BandInvalid(
                        f"{spec.param}.{spec.section}{where} 的 open-ended 帶（{bound}=null）"
                        f"只能是最後一帶，目前在第 {pos + 1} 帶"
                    )
                continue
            if prev is not None:
                if value == prev:
                    raise BandInvalid(
                        f"{spec.param}.{spec.section}{where} 帶界重疊：第 {pos + 1} 帶的 {bound}={value} "
                        f"與前一帶相同"
                    )
                if value < prev:
                    raise BandInvalid(
                        f"{spec.param}.{spec.section}{where} 帶界未遞增（不連續）：第 {pos + 1} 帶的 "
                        f"{bound}={value} 小於前一帶的 {prev}"
                    )
            prev = value
        if spec.require_open_ended and group and group[-1][bound] is not None:
            raise BandInvalid(
                f"{spec.param}.{spec.section}{where} 的末帶必須是 open-ended（{bound}=null）："
                f"該量測值物理上無上界，末帶若為有限值（目前 {group[-1][bound]}），"
                f"超出的輸入會被引擎靜默夾取到末帶而不報錯"
            )
