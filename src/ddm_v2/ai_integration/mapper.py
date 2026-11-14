"""ai_service 回應 → `MotionSuggestion`（ADR-037 D3 的入站檢查；實作計畫 S2）。

ai_service 的 `content` 是外部可控資料（WI 語句來自 Excel，使用者可控，可能夾帶 prompt
injection）。本模組把它當**不可信輸入**處理：

1. **allow-list**：每個 slot code 必須存在於**目標 worksheet 的 rule-set**（呼叫端傳入
   `allow_lists`，形狀同 `most_compiler.compile.allow_lists_from_rule_set`）；不存在 → 置 None
   並記 issue，不靜默忽略。
2. **上限**：每句 motion 數、自由文字長度、addon 數、數值範圍（ADR-037 D8）。motion 數超過上限
   視為整筆無效（fail-closed），不截斷——截斷會讓「被丟掉的那幾個 motion」在審核畫面上消失。
3. **不採信**：`hand`、`seq_kind` 只降為 `*_hint`；magnitude 只降為 `*_hint`（不進 `role.value`）。
4. **不透傳**：未知欄位丟棄；issue 只用 MOST 自己的代碼，不夾帶外部字串
   （同 `inbound_guard` 對 `reasons` 的規則，避免外部字串經 issue 落 DB／回 API）。
5. **SIMO**：一律不產生（`MotionSuggestion` 的 SIMO 欄位恆為 None）。

形狀依據：ai_service `packs/most/schemas/wi-motion-parse.schema.json`（MOST 複本見 `schema.py`）。
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind
from ddm_v2.ai_integration.ports import (
    AllowLists,
    ASlotSuggestion,
    MotionSuggestion,
    PSlotSuggestion,
)

MAX_MOTIONS = 20
MAX_TEXT_LEN = 200
MAX_ADDON = 2
MAX_DISTANCE_CM = 1000.0
MAX_ANGLE_DEG = 360.0

_HANDS = {"LH", "RH", "BH"}
_SEQ_KINDS = {"GM", "CM"}
_A_KINDS = {"reach", "foot", "twist", "return"}
_MOTION_KEYS = {"hand", "seq_kind", "sub_activity", "object", "slots"}
_SLOT_KEYS = {"s0_A", "s1_B", "s2_G", "s3", "s4", "s5", "s6_A"}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Hangul 填充字元（NFKC 會把 U+3164／U+FFA0 轉成 U+1160）與點字空白
_BLANK_FILLERS = frozenset("\u115f\u1160\u3164\uffa0\u2800")


def _clean_text(value: Any, issues: list[str], where: str) -> str:
    """NFKC 正規化；控制字元（C0／C1）換成空白；移除格式字元（Cf：bidi override、零寬字元）與
    行／段分隔符（Zl／Zp）。這些字元會讓審核畫面顯示的文字與實際內容不同。"""
    if not isinstance(value, str):
        issues.append(f"text_invalid:{where}")
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    # Cs：孤立 surrogate（寫 DB／UTF-8 編碼會出錯）；_BLANK_FILLERS 是看起來空白的填充字元
    text = "".join(
        c for c in normalized if unicodedata.category(c) not in {"Cf", "Zl", "Zp", "Cs"} and c not in _BLANK_FILLERS
    )
    text = re.sub(r"\s+", " ", _CONTROL_CHARS.sub(" ", text)).strip()
    if len(text) > MAX_TEXT_LEN:
        issues.append(f"text_truncated:{where}")
        text = text[:MAX_TEXT_LEN]
    return text


def _finite_in_range(value: Any, upper: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int) and not 0 <= value <= upper:  # 先比大整數，避免 float() OverflowError
        return None
    f = float(value)
    if not math.isfinite(f) or f < 0 or f > upper:
        return None
    return f


def _is_one_of(value: Any, allowed: set[str]) -> bool:
    """外部值可能是 list／dict（不可雜湊）；先確認是字串再比對，避免 TypeError 逃出降級。"""
    return isinstance(value, str) and value in allowed


def _a_slot(value: Any, issues: list[str], where: str) -> ASlotSuggestion | None:
    if not isinstance(value, dict) or not _is_one_of(value.get("kind"), _A_KINDS):
        issues.append(f"a_slot_invalid:{where}")
        return None
    if set(value) - {"kind", "magnitude_cm", "magnitude_deg"}:
        issues.append(f"unknown_fields_dropped:{where}")
    kind = value["kind"]
    cm = deg = None
    if value.get("magnitude_cm") is not None:
        cm = _finite_in_range(value["magnitude_cm"], MAX_DISTANCE_CM)
        if cm is None:
            issues.append(f"magnitude_out_of_range:{where}")
    if value.get("magnitude_deg") is not None:
        deg = _finite_in_range(value["magnitude_deg"], MAX_ANGLE_DEG)
        if deg is None:
            issues.append(f"magnitude_out_of_range:{where}")
    if cm is not None or deg is not None:
        # ADR-037 D3：估計值須經人確認才進引擎
        issues.append(f"magnitude_estimate_unconfirmed:{where}")
    if kind == "return":
        # compile 尚無 return 型 A 位置的分支（ADR-037 D3；ADR-033 P3 第三項不在前置內）
        issues.append(f"a_return_needs_review:{where}")
    return ASlotSuggestion(kind=kind, magnitude_cm_hint=cm, magnitude_deg_hint=deg)


def _code(value: Any, allowed: frozenset[str] | set[str], issues: list[str], where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in allowed:
        issues.append(f"unknown_code:{where}")
        return None
    return value


def _p_slot(value: Any, allow_lists: AllowLists, issues: list[str], where: str) -> PSlotSuggestion | None:
    if not isinstance(value, dict):
        issues.append(f"p_slot_invalid:{where}")
        return None
    base = _code(value.get("base"), allow_lists.get("P", set()), issues, f"{where}.base")
    raw_addon = value.get("addon") or []
    if not isinstance(raw_addon, list):
        issues.append(f"p_addon_invalid:{where}")
        raw_addon = []
    addon: list[str] = []
    for i, a in enumerate(raw_addon):
        code = _code(a, allow_lists.get("P_ADDON", set()), issues, f"{where}.addon[{i}]")
        if code is not None and code not in addon:
            addon.append(code)
    if len(addon) > MAX_ADDON:
        issues.append(f"p_addon_over_limit:{where}")
        addon = addon[:MAX_ADDON]
    return PSlotSuggestion(base=base, addon=tuple(addon))


def _motion(index: int, raw: Any, allow_lists: AllowLists) -> MotionSuggestion:
    issues: list[str] = []
    m = raw if isinstance(raw, dict) else {}
    if not isinstance(raw, dict):
        issues.append("motion_invalid")
    if set(m) - _MOTION_KEYS:
        issues.append("unknown_fields_dropped:motion")

    hand = m.get("hand") if _is_one_of(m.get("hand"), _HANDS) else None
    if hand is None:
        issues.append("hand_invalid")
    seq = m.get("seq_kind") if _is_one_of(m.get("seq_kind"), _SEQ_KINDS) else None
    if seq is None:
        issues.append("seq_kind_invalid")

    raw_slots = m.get("slots")
    slots: dict[str, Any] = raw_slots if isinstance(raw_slots, dict) else {}
    if not slots:
        issues.append("slots_invalid")
    if set(slots) - _SLOT_KEYS:
        issues.append("unknown_fields_dropped:slots")

    fields: dict[str, Any] = {
        "a0": _a_slot(slots.get("s0_A"), issues, "s0_A"),
        "b1": _code(slots.get("s1_B"), allow_lists.get("B", set()), issues, "s1_B"),
        "g2": _code(slots.get("s2_G"), allow_lists.get("G", set()), issues, "s2_G"),
        "a6": _a_slot(slots.get("s6_A"), issues, "s6_A"),
    }
    if seq == "GM":
        fields["a3"] = _a_slot(slots.get("s3"), issues, "s3")
        fields["b4"] = _code(slots.get("s4"), allow_lists.get("B", set()), issues, "s4")
        fields["p5"] = _p_slot(slots.get("s5"), allow_lists, issues, "s5")
    elif seq == "CM":
        fields["m3"] = _code(slots.get("s3"), allow_lists.get("M", set()), issues, "s3")
        fields["x4"] = _code(slots.get("s4"), allow_lists.get("X", set()), issues, "s4")
        fields["i5"] = _code(slots.get("s5"), allow_lists.get("I", set()), issues, "s5")
    # seq_kind 無效時中段無法解讀：三格一律留空（issue 已記 seq_kind_invalid）

    return MotionSuggestion(
        index=index,
        hand_hint=hand,
        seq_kind_hint=seq,
        sub_activity=_clean_text(m.get("sub_activity"), issues, "sub_activity"),
        object_text=_clean_text(m.get("object", ""), issues, "object"),
        issues=tuple(issues),
        **fields,
    )


def map_content(content: Any, allow_lists: AllowLists) -> tuple[list[MotionSuggestion], list[str]]:
    """回傳 (motions, result 層 issues)。形狀不可解讀或超過上限時丟 `AiServiceError(CONTRACT_MISMATCH)`。"""
    if not isinstance(content, dict) or not isinstance(content.get("motions"), list):
        raise AiServiceError(AiServiceErrorKind.CONTRACT_MISMATCH, upstream_code="motions_missing")
    result_issues: list[str] = []
    if set(content) - {"motions"}:
        result_issues.append("unknown_fields_dropped:content")
    raw_motions = content["motions"]
    if not raw_motions:
        raise AiServiceError(AiServiceErrorKind.CONTRACT_MISMATCH, upstream_code="motions_empty")
    if len(raw_motions) > MAX_MOTIONS:
        raise AiServiceError(AiServiceErrorKind.CONTRACT_MISMATCH, upstream_code="too_many_motions")
    motions = [_motion(i, raw, allow_lists) for i, raw in enumerate(raw_motions)]
    return motions, result_issues
