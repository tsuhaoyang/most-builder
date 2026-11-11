"""`scripts/audit_slot_inputs.py` 的正向對照測試（ADR-028 斷言 #32）。

為什麼這支測試存在，而且必須用**合成的違規 payload**：

> 本機 dev DB 目前 0 筆 cycle，這支腳本在本機必然綠——**本機綠燈不構成任何證據**
> （先例：`Always-True-Assertion-Detector-Self-Disable` 型二，「差集守門的待驗集合是空的」）。
> —— ADR-028 §4

所以下面每一條 A 類規則（A1–A7）都自己造一筆違規 payload，斷言偵測器**真的紅**；
再配一組反向對照（合法 payload 不得誤報），證明加嚴是**資料驅動**而非一律報錯——
最關鍵的一對是 A3：reach 有 overflow 帶 → 9999cm 合法；twist 沒有 → 9999° 報錯。
兩者用同一份 rule-set、同一條規則，差別只在資料。

測試不撈 DB、不依賴環境既存資料（CI_GATES 硬性規則 7 第一條）：rule-set 一律用
`build_from_seed_v2()`（in-memory），payload 一律當場合成。
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import types
import uuid
from dataclasses import replace

import pytest
from sqlalchemy import select

from ddm_v2.most_engine import SequenceError, build_from_seed_v2, compute_cycle
from ddm_v2.schemas.v2.most import ASlot, CycleIn, cycle_in_to_engine

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "audit_slot_inputs.py"


def _load():
    """按路徑載入腳本（`scripts/` 不是 package）——與 test_seed_templates_* 同慣例。

    必須先塞進 `sys.modules`：`@dataclass` 在處理欄位時會查 `sys.modules[cls.__module__]`，
    沒登記就 `AttributeError: 'NoneType' object has no attribute '__dict__'`。
    模組名加後綴，不與任何真實 import 名稱衝突。
    """
    name = "_audit_slot_inputs_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


AUDIT = _load()
RS = build_from_seed_v2()

pytestmark = pytest.mark.unit


# ── 合成 payload 的最小工具（刻意用 CycleIn 產生「乾淨底稿」再故意弄壞一處）──
def _gm(**overrides) -> dict:
    """黃金錨 GM=28（A6 B0 G6 A10 B0 P6 A0），dump 成 DB 裡 slot_inputs 的實際形狀。"""
    base = CycleIn.model_validate({
        "seq": "GM",
        "a0": {"reach_cm": 20},
        "g2": {"g_code": "g_grasp"},
        "a3": {"reach_cm": 25},
        "p5": {"p_base_code": "p_place_none"},
    }).model_dump(mode="json")
    base.update(overrides)
    return base


def _cm(**overrides) -> dict:
    """黃金錨 CM=29（推 45cm＝18 吋檔 →16）。"""
    base = CycleIn.model_validate({
        "seq": "CM",
        "a0": {"reach_cm": 25},
        "g2": {"g_code": "g_touch"},
        "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 45}]},
        "x4": {"x_code": "x_none"},
        "i5": {"i_code": "i_none"},
    }).model_dump(mode="json")
    base.update(overrides)
    return base


def _m(*components, **slot) -> dict:
    """組一個 M 格位；分量直接給 raw dict（刻意繞過 MComponent，才測得到 Pydantic 之前的形狀）。"""
    return {"m_components": list(components), "repeat_count": None, "manual_override": None, **slot}


def _rules(findings) -> list[str]:
    return [f.rule for f in findings]


def _blocking(payload: dict) -> list:
    return [f for f in AUDIT.scan_cycle_payload(payload, RS) if f.blocking]


# ═══════════════════════════════════════════════════════════════════════════
# 基線：合法 payload 零命中（沒有這條，下面每一條「有命中」都可能是恆真）
# ═══════════════════════════════════════════════════════════════════════════
def test_clean_gm_payload_has_no_findings():
    assert AUDIT.scan_cycle_payload(_gm(), RS) == []


def test_clean_cm_payload_has_no_findings():
    assert AUDIT.scan_cycle_payload(_cm(), RS) == []


# ═══════════════════════════════════════════════════════════════════════════
# A1–A7 正向對照：每條規則一筆合成違規，斷言偵測器紅
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("field_name,value", [
    ("distance_cm", -5),
    ("angle_deg", -30),
    ("diameter_cm", -1),
])
def test_a1_negative_m_component_is_detected(field_name, value):
    """A1：M 分量三個尺寸欄位為負 → M_NEGATIVE（今天引擎回 0.0／16，不報錯）。"""
    comp = {"verb_code": "m_push", "distance_cm": 0, "angle_deg": 0,
            "revolutions": 1, "diameter_cm": 0}
    comp[field_name] = value
    findings = AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS)

    hits = [f for f in findings if f.rule == "A1"]
    assert len(hits) == 1, f"A1 未命中：{findings}"
    assert hits[0].code == "M_NEGATIVE"
    assert field_name in hits[0].where


@pytest.mark.parametrize("revolutions", [99, 0, 2.6, -1])
def test_a2_rotation_revolutions_out_of_ruleset_set_is_detected(revolutions):
    """A2：圈數非整數或不在該 rule-set 的圈數集合（V2＝{1,2,3}）內 → M_ROTATION_RANGE。"""
    comp = {"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": revolutions,
            "distance_cm": 0, "angle_deg": 0}
    findings = AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS)

    hits = [f for f in findings if f.rule == "A2"]
    assert len(hits) == 1, f"A2 未命中（revolutions={revolutions!r}）：{findings}"
    assert hits[0].code == "M_ROTATION_RANGE"


def _a_slot(**values) -> dict:
    """完整的 A 格 dump 形狀（`ASlot.model_dump()` 恆含三個分量 + repeat/override）。"""
    return {"reach_cm": 0, "twist_deg": 0, "foot_cm": 0,
            "repeat_count": None, "manual_override": None, **values}


# reach/foot 有 overflow 帶 `(None, …)`，所以只有 twist 能在出貨 rule-set 上示範 A3。
# 要驗返回格（slot6，只計伸手）就得把 reach 的 overflow 帶拿掉——同一條規則、換一份資料。
_RS_REACH_NO_OVERFLOW = replace(
    RS, a_bands={**RS.a_bands, "reach": tuple(b for b in RS.a_bands["reach"] if b[0] is not None)})


@pytest.mark.parametrize("seq,field_name,slot,rule_set,component", [
    # GM 的 A 格索引是 (0, 3, 6)：三格都必須被掃到。
    ("GM", "a0", _a_slot(twist_deg=9999), RS, "twist"),
    ("GM", "a3", _a_slot(twist_deg=9999), RS, "twist"),
    ("GM", "a6", _a_slot(reach_cm=9999), _RS_REACH_NO_OVERFLOW, "reach"),
    # CM 的 A 格索引是 (0, 6)。
    ("CM", "a0", _a_slot(twist_deg=9999), RS, "twist"),
    ("CM", "a6", _a_slot(reach_cm=9999), _RS_REACH_NO_OVERFLOW, "reach"),
])
def test_a3_a_band_without_overflow_is_detected(seq, field_name, slot, rule_set, component):
    """A3：分量超出帶表且該分量**無** overflow 帶 → A_BAND_RANGE（今天靜默夾到最後一檔）。

    **每一個 A 格位都要有正向對照**。原本只有 `a0` 有：實測把 `_A_SLOT_INDEXES_GM`
    從 `(0, 3, 6)` 改成 `(0,)`，unit 53 passed／integration 7 passed 全綠，
    而 `{"seq":"GM","a3":{"twist_deg":9999}}` 從報 `['A3']` 變成報 `[]`（假陰性）。
    """
    base = _gm() if seq == "GM" else _cm()
    findings = AUDIT.scan_cycle_payload({**base, field_name: slot}, rule_set)

    hits = [f for f in findings if f.rule == "A3"]
    assert len(hits) == 1, f"A3 未命中（{seq}.{field_name}）：{findings}"
    assert hits[0].code == "A_BAND_RANGE"
    assert component in hits[0].detail
    assert field_name in hits[0].where


def test_a4_cross_model_key_in_slot0_is_detected():
    """A4：GM slot0（A 格）夾帶 m_components/x_code → SLOT_CROSS_MODEL。

    今天的引擎只守 slot 3/4/5（`calculate.py:247-248`），slot 0/1/2/6 的外來鍵被靜默忽略。
    """
    payload = _gm(a0={"reach_cm": 30, "twist_deg": 0, "foot_cm": 0,
                      "repeat_count": None, "manual_override": None,
                      "m_components": [{"verb_code": "m_push"}], "x_code": "x_none"})
    findings = AUDIT.scan_cycle_payload(payload, RS)

    hits = [f for f in findings if f.rule == "A4"]
    assert len(hits) == 1, f"A4 未命中：{findings}"
    assert hits[0].code == "SLOT_CROSS_MODEL"
    assert "m_components" in hits[0].detail and "x_code" in hits[0].detail


def test_a5_string_slot_keys_from_json_roundtrip_are_detected():
    """A5：引擎形狀 payload 經 JSON 往返 → int 鍵變字串鍵 → SLOT_KEY_INVALID。

    這是 ADR-028 最危險的一條（斷言 #9）：今天 `compute_cycle` 對它回 **0.0 且不報錯**，
    `tech_line` 還是一串看起來合理的 `A0 B0 G0 ...`。
    """
    engine_cycle = cycle_in_to_engine(CycleIn.model_validate(_gm()))
    assert compute_cycle(engine_cycle, RS).total_tmu == 28.0  # 黃金錨：往返前是 28

    roundtripped = json.loads(json.dumps(engine_cycle))
    assert compute_cycle(roundtripped, RS).total_tmu == 0.0   # 往返後靜默變 0（今天的病灶）

    findings = AUDIT.scan_cycle_payload(roundtripped, RS)
    hits = [f for f in findings if f.rule == "A5"]
    assert len(hits) == 7, f"A5 應對 7 個字串鍵各命中一次：{findings}"
    assert {f.code for f in hits} == {"SLOT_KEY_INVALID"}


@pytest.mark.parametrize("bad_key", [7, -1, "0"])
def test_a5_out_of_range_or_string_slot_key_is_detected(bad_key):
    """A5：非 0..6 的整數鍵（含字串鍵）。"""
    findings = AUDIT.scan_cycle_payload({"seq": "GM", "slots": {bad_key: {}}}, RS)

    hits = [f for f in findings if f.rule == "A5"]
    assert len(hits) == 1, f"A5 未命中（key={bad_key!r}）：{findings}"
    assert hits[0].code == "SLOT_KEY_INVALID"


def test_a6_m_component_without_verb_code_is_detected():
    """A6：m_components 內有分量但缺 verb_code → M_VERB_REQUIRED（今天靜默略過該分量）。"""
    findings = AUDIT.scan_cycle_payload(_cm(m3=_m({"distance_cm": 45})), RS)

    hits = [f for f in findings if f.rule == "A6"]
    assert len(hits) == 1, f"A6 未命中：{findings}"
    assert hits[0].code == "M_VERB_REQUIRED"


def test_a7_x_fixed_without_seconds_is_detected():
    """A7：payload 指到 mode='fixed' 但 fixed_seconds 為 NULL 的 X 選項。

    這是 **rule-set 資料缺陷**，不是 payload 內容錯——所以違規樣本要造在 rule-set 那一側
    （V2 認證字典本身沒有這種選項，見同檔 `test_shipped_rule_sets_have_no_fixed_x_without_seconds`）。
    今天引擎在此拋裸 `ValueError` → 500 而非 422（ADR-028 §5）。
    """
    broken = AUDIT.RuleSetData(**{**RS.__dict__, "x_options": {**RS.x_options, "x_bad": ("fixed", None)}})
    findings = AUDIT.scan_cycle_payload(
        _cm(x4={"x_code": "x_bad", "x_seconds": 0, "repeat_count": None, "manual_override": None}),
        broken,
    )

    hits = [f for f in findings if f.rule == "A7"]
    assert len(hits) == 1, f"A7 未命中：{findings}"
    assert hits[0].code == "X_FIXED_SECONDS_MISSING"


def test_all_seven_a_rules_have_a_positive_control():
    """後設守門：A1–A7 每一條都必須被上面某條測試實際命中過（少一條就紅）。

    沒有這條，日後有人把某條偵測器改壞、順手刪掉對應測試，本檔仍會全綠。
    """
    covered = set()
    comp = {"verb_code": "m_push", "distance_cm": -5, "angle_deg": 0, "revolutions": 1, "diameter_cm": 0}
    rot = {"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": 99, "distance_cm": 0, "angle_deg": 0}
    broken_rs = AUDIT.RuleSetData(**{**RS.__dict__, "x_options": {**RS.x_options, "x_bad": ("fixed", None)}})
    samples = [
        (_cm(m3=_m(comp)), RS),
        (_cm(m3=_m(rot)), RS),
        (_gm(a0={"reach_cm": 0, "twist_deg": 9999, "foot_cm": 0, "repeat_count": None, "manual_override": None}), RS),
        (_gm(a0={"reach_cm": 30, "twist_deg": 0, "foot_cm": 0, "repeat_count": None,
                 "manual_override": None, "x_code": "x_none"}), RS),
        ({"seq": "GM", "slots": {"0": {}}}, RS),
        (_cm(m3=_m({"distance_cm": 45})), RS),
        (_cm(x4={"x_code": "x_bad", "x_seconds": 0, "repeat_count": None, "manual_override": None}), broken_rs),
    ]
    for payload, rs in samples:
        covered |= {f.rule for f in AUDIT.scan_cycle_payload(payload, rs)}
    assert {"A1", "A2", "A3", "A4", "A5", "A6", "A7"} <= covered, f"未被任何樣本命中：{covered}"


# ═══════════════════════════════════════════════════════════════════════════
# 反向對照：不得過度加嚴（ADR-028 斷言 #13–#19 的稽核側對應）
# ═══════════════════════════════════════════════════════════════════════════
def test_a3_does_not_fire_when_the_component_has_an_overflow_band():
    """反向對照（最關鍵的一條）：reach **有** overflow 帶 `(None, 24)` → 9999cm 合法。

    與 `test_a3_a_band_without_overflow_is_detected` 是同一條規則、同一份 rule-set，
    差別只在資料——這證明 A3 是資料驅動，不是「超過表格就報錯」。
    """
    assert RS.band_index("reach", 9999) == 24  # 引擎今天就回 24，不是夾取

    payload = _gm(a0={"reach_cm": 9999, "twist_deg": 0, "foot_cm": 0,
                      "repeat_count": None, "manual_override": None})
    assert [f for f in AUDIT.scan_cycle_payload(payload, RS) if f.rule == "A3"] == []


def test_a3_does_not_fire_for_foot_which_also_has_an_overflow_band():
    payload = _gm(a0={"reach_cm": 0, "twist_deg": 0, "foot_cm": 9999,
                      "repeat_count": None, "manual_override": None})
    assert [f for f in AUDIT.scan_cycle_payload(payload, RS) if f.rule == "A3"] == []


def test_a2_does_not_fire_for_a_legal_rotation():
    """反向對照：直徑 10cm × 2 圈是 rule-set 有的組合（斷言 #14：32 TMU）。"""
    comp = {"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": 2,
            "distance_cm": 0, "angle_deg": 0}
    assert AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS) == []


def test_a2_does_not_fire_for_non_rotate_verbs_carrying_default_revolutions():
    """反向對照：ladder／hand 分量帶著 `revolutions` 預設值是無害的，不得誤殺。

    這正是 ADR-028〈考慮過的選項〉C-2 否決「schema 層一律 ge=1,le=3」的理由。
    刻意用一個**不在** rule-set 圈數集合內的值：若偵測器忘了按動詞區分就會紅。
    """
    comp = {"verb_code": "m_push", "distance_cm": 45, "angle_deg": 0,
            "revolutions": 99, "diameter_cm": 0}
    assert [f for f in AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS) if f.rule == "A2"] == []


def test_a6_does_not_fire_for_an_empty_component_list():
    """反向對照（斷言 #15）：`m_components=[]` 合法。"""
    assert AUDIT.scan_cycle_payload(_cm(m3=_m()), RS) == []


def test_a1_does_not_fire_for_zero_values():
    """反向對照（斷言 #16）：0 代表「未使用該分量」，是合法輸入。"""
    comp = {"verb_code": "m_push", "distance_cm": 0, "angle_deg": 0,
            "revolutions": 1, "diameter_cm": 0}
    assert [f for f in AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS) if f.rule == "A1"] == []


def test_a4_allows_modifiers_on_the_g_slot():
    """反向對照（斷言 #17）：G 格的允許鍵集合必須含 `modifiers`，否則每一筆真實資料都誤報。"""
    payload = _gm(g2={"g_code": "g_grasp", "modifiers": {"contact": True},
                      "repeat_count": None, "manual_override": None})
    assert [f for f in AUDIT.scan_cycle_payload(payload, RS) if f.rule == "A4"] == []


def test_a4_allows_zero_twist_and_foot_on_the_return_slot():
    """反向對照（斷言 #18）：`ASlot.model_dump()` 恆含 twist_deg/foot_cm，slot6 帶 0 值合法。"""
    payload = _gm(a6={"reach_cm": 0, "twist_deg": 0, "foot_cm": 0,
                      "repeat_count": None, "manual_override": None})
    assert AUDIT.scan_cycle_payload(payload, RS) == []


def test_missing_slots_are_still_legal():
    """反向對照（斷言 #19 / B6）：缺格位視為空 dict，仍合法。"""
    assert AUDIT.scan_cycle_payload({"seq": "GM"}, RS) == []


def test_null_variant_slots_are_legal():
    """反向對照：DB 裡 GM 列的 `m3/x4/i5` 就是 null——這是常態，不得命中任何規則。"""
    payload = _gm()
    assert payload["m3"] is None and payload["x4"] is None and payload["i5"] is None
    assert AUDIT.scan_cycle_payload(payload, RS) == []


# ═══════════════════════════════════════════════════════════════════════════
# 字串型數值：DB 裡的 JSONB 不保證是數字型別
# ═══════════════════════════════════════════════════════════════════════════
def test_a1_detects_a_negative_value_stored_as_a_string():
    """`"distance_cm": "-5"` 必須命中 A1。

    原本 `_num()` 只認 int/float，字串直接回 None 跳過 → 稽核判 `[]`（算成乾淨），
    但 Pydantic coerce 後是 `-5.0`，**加嚴後引擎會擋**——這是不折不扣的假陰性。
    dev DB 目前沒有字串型數值，但正式環境的 AI parser 與匯入正是最會產生字串的來源。
    """
    comp = {"verb_code": "m_push", "distance_cm": "-5", "angle_deg": 0,
            "revolutions": 1, "diameter_cm": 0}
    hits = [f for f in AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS) if f.rule == "A1"]

    assert len(hits) == 1, "字串型負值必須與數字型負值同樣命中 A1"
    assert hits[0].code == "M_NEGATIVE"
    # 對照：Pydantic 真的會把它 coerce 成負數（所以加嚴後引擎確實會擋）
    from ddm_v2.schemas.v2.most import MComponent
    assert MComponent.model_validate(comp).distance_cm == -5.0


def test_a3_detects_an_out_of_band_value_stored_as_a_string():
    payload = _gm(a0=_a_slot(twist_deg="9999"))
    hits = [f for f in AUDIT.scan_cycle_payload(payload, RS) if f.rule == "A3"]
    assert len(hits) == 1 and hits[0].code == "A_BAND_RANGE"


@pytest.mark.parametrize("revolutions,reason", [
    ("99", "不在 rule-set"),        # 字串但是整數 → 應報「不在圈數集合」
    ("2.6", "非整數圈數"),           # 字串但有小數 → 應報「非整數」
    ("abc", "不是數值"),             # 根本不是數值
])
def test_a2_message_matches_the_actual_cause(revolutions, reason):
    """A2 的訊息要與成因相符。

    原本 `_int_or_none` 把 `revolutions: "99"` 判成 A2 卻寫「非整數圈數」——訊息與成因不符，
    看報告的人會照著訊息去改小數點，而真正的問題是 99 不在該 rule-set 的圈數集合裡。
    """
    comp = {"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": revolutions,
            "distance_cm": 0, "angle_deg": 0}
    hits = [f for f in AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS) if f.rule == "A2"]

    assert len(hits) == 1, f"A2 未命中（revolutions={revolutions!r}）"
    assert reason in hits[0].detail, f"訊息與成因不符：{hits[0].detail}"


def test_a2_reads_the_revolution_set_from_the_rule_set_not_a_hardcoded_1_2_3():
    """出貨的兩份 rule-set 圈數集合都是 {1,2,3}，所以「硬編 1..3」在它們身上測不出來。

    用一份合成的 rule-set（圈數集合 {5}）才有鑑別力：2 圈要紅、5 圈要綠。
    """
    synthetic = replace(RS, m_rotation=((None, 5, 40),))
    assert {rv for _mx, rv, _tmu in synthetic.m_rotation} == {5}

    def _a2(revolutions):
        comp = {"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": revolutions,
                "distance_cm": 0, "angle_deg": 0}
        return [f for f in AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), synthetic) if f.rule == "A2"]

    assert len(_a2(2)) == 1, "2 圈不在合成 rule-set 的集合內，必須命中"
    assert _a2(5) == [], "5 圈在合成 rule-set 的集合內，不得誤報"


def test_a_huge_integer_does_not_abort_the_whole_scan():
    """JSONB 可以存任意精度整數，`float()` 會 OverflowError——一筆荒謬的值不該炸掉整趟掃描。"""
    comp = {"verb_code": "m_push", "distance_cm": -(10 ** 400), "angle_deg": 0,
            "revolutions": 1, "diameter_cm": 0}
    hits = [f for f in AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS) if f.rule == "A1"]
    assert len(hits) == 1 and hits[0].code == "M_NEGATIVE"


# ═══════════════════════════════════════════════════════════════════════════
# S1：斷言 #33「歷史 slot_inputs 的鍵集合 ⊆ 現行 CycleIn 鍵集合」
# ═══════════════════════════════════════════════════════════════════════════
def test_s1_detects_top_level_key_outside_current_cycle_in():
    """歷史 payload 帶了現行 `CycleIn` 沒有的頂層鍵 → `extra='forbid'` 上線後 load→save 會 422。"""
    findings = AUDIT.scan_cycle_payload(_gm(legacy_field="x"), RS)

    hits = [f for f in findings if f.rule == "S1"]
    assert len(hits) == 1, f"S1 未命中：{findings}"
    assert hits[0].code == "CYCLE_KEY_UNKNOWN"
    assert "legacy_field" in hits[0].detail


def test_s1_detects_unknown_key_inside_m_component():
    findings = AUDIT.scan_cycle_payload(
        _cm(m3=_m({"verb_code": "m_push", "distance_cm": 45, "legacy_unit": "inch"})), RS)

    hits = [f for f in findings if f.rule == "S1"]
    assert len(hits) == 1 and "legacy_unit" in hits[0].detail


def test_s1_detects_unknown_key_inside_manual_override():
    payload = _gm(a0={"reach_cm": 30, "twist_deg": 0, "foot_cm": 0, "repeat_count": None,
                      "manual_override": {"tmu": 5, "reason": "r", "by": "X", "legacy": 1}})
    hits = [f for f in AUDIT.scan_cycle_payload(payload, RS) if f.rule == "S1"]
    assert len(hits) == 1 and "legacy" in hits[0].detail


def test_s1_allowed_key_sets_come_from_the_real_contract_not_a_copy():
    """S1/A4 的允許鍵集合必須**取自** `schemas/v2/most.py` 的欄位，不是本檔另抄一份。

    有這條，日後 `CycleIn` 加欄位時稽核自動跟上；沒有這條，允許集合會慢慢漂成第三份權威。
    """
    from ddm_v2.schemas.v2 import most as most_schema

    assert AUDIT._fields(most_schema.CycleIn) == set(most_schema.CycleIn.model_fields)
    for i, model in enumerate(AUDIT._SLOT_MODELS_GM):
        assert AUDIT._fields(model) == set(model.model_fields), f"slot{i}"


# ═══════════════════════════════════════════════════════════════════════════
# 格位覆蓋圖：必須從 `cycle_in_to_engine()` 導出，不是第二份手抄契約
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("seq", ["GM", "CM"])
def test_slot_map_is_derived_from_cycle_in_to_engine(seq):
    """`_CYCLE_FIELDS_*` / `_SLOT_MODELS_*` 的每一格都要能被真契約獨立複驗。

    這張覆蓋圖原本是手抄 `schemas/v2/most.py::cycle_in_to_engine()` 的常數。實測突變：
      `"b4"` → `"b4_TYPO"`            → unit 53 passed / integration 7 passed（全綠）
      `"i5"` → `"i5_TYPO"`            → unit 53 passed / integration 7 passed（全綠）
      `_A_SLOT_INDEXES_GM (0,3,6)` → `(0,)` → 同上全綠，而 A3 出現假陰性
    現在它由哨兵過 `cycle_in_to_engine()` 反推；本測試用**獨立的**哨兵再走一次同一條真路徑，
    確認第 i 格真的來自第 i 個欄位名、且型別就是宣告的那個格位模型。
    """
    names = AUDIT._CYCLE_FIELDS_GM if seq == "GM" else AUDIT._CYCLE_FIELDS_CM
    models = AUDIT._SLOT_MODELS_GM if seq == "GM" else AUDIT._SLOT_MODELS_CM
    assert len(names) == len(models) == 7
    assert len(set(names)) == 7, f"同一個欄位不可對到兩格：{names}"

    for i, name in enumerate(names):
        marker = 4242.0 + i
        cycle = cycle_in_to_engine(CycleIn.model_validate(
            {"seq": seq, name: {"manual_override": {"tmu": marker, "reason": "probe"}}}))
        got = (cycle["slots"][i] or {}).get("manual_override") or {}
        assert got.get("tmu") == marker, f"{seq} slot{i} 不是來自欄位 {name!r}：{cycle['slots']}"
        # 欄位型別必須就是覆蓋圖記的那個模型（A4 的允許鍵集合直接取自它）
        assert AUDIT._slot_model_of(name) is models[i], f"{seq} slot{i} 模型對不上"


def test_a_slot_indexes_are_derived_from_the_slot_models():
    """`_A_SLOT_INDEXES_*` 必須等於「模型是 ASlot 的格位」，不是另抄的 (0,3,6)/(0,6)。"""
    assert AUDIT._A_SLOT_INDEXES_GM == tuple(
        i for i, m in enumerate(AUDIT._SLOT_MODELS_GM) if m is ASlot)
    assert AUDIT._A_SLOT_INDEXES_CM == tuple(
        i for i, m in enumerate(AUDIT._SLOT_MODELS_CM) if m is ASlot)
    # 現行契約下的具體值（換了就代表 cycle_in_to_engine 變了，要有人重新裁決）
    assert (AUDIT._A_SLOT_INDEXES_GM, AUDIT._A_SLOT_INDEXES_CM) == ((0, 3, 6), (0, 6))


def test_m_x_and_return_slot_indexes_are_derived_too_not_hand_copied():
    """M／X 的格位索引與返回格索引也必須由覆蓋圖導出——它們原本是覆蓋圖裡僅存的手抄常數。

    「不手抄任何一份契約」是本檔的立論（`_derive_slot_map` 的 docstring）：留三個手抄的
    `3` / `4` / `6` 在旁邊，等於留三個無人看守的第二份契約。
    """
    from ddm_v2.schemas.v2.most import MSlot, XSlot

    assert AUDIT._M_SLOT_INDEX_CM == AUDIT._SLOT_MODELS_CM.index(MSlot) == 3
    assert AUDIT._X_SLOT_INDEX_CM == AUDIT._SLOT_MODELS_CM.index(XSlot) == 4
    # 返回格＝最後一格，且 GM/CM 的最後一個 A 格都在那裡（模組載入時已交叉驗證過一次）
    assert AUDIT._RETURN_SLOT == AUDIT._SLOT_COUNT - 1 == 6
    assert AUDIT._A_SLOT_INDEXES_GM[-1] == AUDIT._A_SLOT_INDEXES_CM[-1] == AUDIT._RETURN_SLOT


def test_a_component_pairs_match_what_the_engine_actually_looks_up():
    """`_a_pairs()` 的 (ASlot 欄位 → 帶表家族) 對照必須與引擎 `_a_tmu` 實際查的一致。

    原本這是手抄 `most_engine/calculate.py:73-75` 的 `_A_COMPONENTS` 常數。這裡不比對字面，
    而是**問引擎**：造一份只有目標家族有帶表、且 >0 一律落在獨特 index 的 rule-set，
    只填一個欄位跑 `compute_cycle`——總和等於該 index 就代表引擎真的用這個欄位查這個家族。
    """
    probe_index = 77
    all_pairs, _return_pairs = AUDIT._a_pairs(RS)
    numeric_fields = [f for f in ASlot.model_fields if f not in ("repeat_count", "manual_override")]

    for family in sorted(RS.a_bands):
        probe_rs = replace(RS, a_bands={
            comp: (((0.5, 0), (None, probe_index)) if comp == family else ())
            for comp in RS.a_bands
        })
        for field_name in numeric_fields:
            total = compute_cycle({"seq": "GM", "slots": {0: {field_name: 1}}}, probe_rs).total_tmu
            engine_uses_it = total == probe_index
            assert ((field_name, family) in all_pairs) is engine_uses_it, (
                f"稽核對照與引擎不一致：{field_name} ↔ {family}（引擎算出 {total}）")


def test_return_slot_components_come_from_asking_the_engine():
    """返回格（slot6）只由 A3 管「引擎會收的分量」——E1：僅計伸手，twist/foot 由引擎自己擋。"""
    _all_pairs, return_pairs = AUDIT._a_pairs(RS)
    assert return_pairs == (("reach_cm", "reach"),)

    # 對照組：引擎確實對返回格的非零 twist/foot 報 A_RETURN_COMPONENT（所以 A3 不該重複報）
    for field_name in ("twist_deg", "foot_cm"):
        with pytest.raises(SequenceError) as excinfo:
            compute_cycle({"seq": "GM", "slots": {6: {field_name: 1}}}, RS)
        assert excinfo.value.code == "A_RETURN_COMPONENT"


# ═══════════════════════════════════════════════════════════════════════════
# S2 / W1：加嚴前就存在的狀態（**兩者都是 WARN**）
# ═══════════════════════════════════════════════════════════════════════════
def test_s2_detects_payload_that_fails_current_cycle_in_validation():
    assert [f.rule for f in AUDIT.scan_cycle_payload({"seq": "XX"}, RS)] == ["S2"]
    hits = [f for f in AUDIT.scan_cycle_payload(_gm(frequency="not-a-number"), RS) if f.rule == "S2"]
    assert len(hits) == 1


def test_s2_is_a_warning_not_a_gate():
    """S2 不進 exit code：**閘門要量的是差值**——「加嚴之後**新增**會被擋下的列」。

    一筆驗不過現行 `CycleIn` 的列**今天就已經會 422**，不是加嚴造成的。把它算進 exit code
    會讓正式環境掃描非 0，讀報告的人以為「加嚴不安全」，真相卻是「你本來就有壞列」——
    誤導性訊號會讓一個正確的部署決策被錯誤的資料擋下。
    （對照組：S1 維持 BLOCK，那是 ADR-028 斷言 #33 明文授權的。）
    """
    for payload in ({"seq": "XX"}, _gm(frequency="not-a-number")):
        findings = AUDIT.scan_cycle_payload(payload, RS)
        assert [f for f in findings if f.rule == "S2"], f"S2 應命中：{findings}"
        assert _blocking(payload) == [], f"S2 不得進 BLOCK：{findings}"

    # S1 是對照組：同樣是「歷史形狀問題」，但它**必須**是 BLOCK
    assert [f.rule for f in _blocking(_gm(legacy_field="x"))] == ["S1"]


def test_blocking_rule_set_is_explicit_not_derived_from_naming():
    """分級來自顯式集合，不是「開頭不是 W 就 BLOCK」——否則調整分級就得改命名。"""
    assert AUDIT._BLOCKING_RULES == {"A1", "A2", "A3", "A4", "A5", "A6", "A7", "S1"}
    assert AUDIT.Finding("S2", "X", "$", "d").blocking is False
    assert AUDIT.Finding("S1", "X", "$", "d").blocking is True
    # 判準表列出的每一條都要有分級歸屬（新增規則忘了歸類會在這裡紅）
    assert set(AUDIT._RULE_TEXT) == AUDIT._BLOCKING_RULES | {"S2", "W1", "W2", "W3", "W4"}


def test_warn_block_says_out_loud_that_s2_rows_are_already_broken_today():
    """S2 必須在 WARN 區塊**顯眼**：它與加嚴無關，但修補批次要一起帶走。"""
    rec = _record([AUDIT.Finding("S2", "CYCLE_SHAPE_INVALID", "$", "CycleIn 驗證失敗")])
    report, code = AUDIT.render([rec], {"most_cycles.slot_inputs": 1}, [], verbose=False)

    assert code == 0
    warn_section = report.split("【WARN：不影響 exit code】")[1]
    assert "CYCLE_SHAPE_INVALID" in warn_section
    assert "今天就已經會 422" in warn_section          # 「與加嚴無關」
    assert "既然要做修補批次就一起修" in warn_section    # 「但仍要修」


def test_s2_records_are_listed_first_in_the_warn_section():
    """S2 排在 WARN 區塊最前面是刻意的（修補批次要一起帶走），所以那個排序要有測試。

    實測：把 `sorted(..., key=...)` 的 key 拿掉 → 全綠。
    """
    w2_first = _record([AUDIT.Finding("W2", "TMU_CACHE_DRIFT", "$", "d")])
    w2_first.entity_id = "id-w2"
    s2_later = _record([AUDIT.Finding("S2", "CYCLE_SHAPE_INVALID", "$", "d")])
    s2_later.entity_id = "id-s2"

    report, _ = AUDIT.render([w2_first, s2_later], {}, [], verbose=False)
    warn_section = report.split("【WARN：不影響 exit code】")[1]

    assert warn_section.index("id-s2") < warn_section.index("id-w2"), "S2 沒有排在 WARN 區塊最前面"


def test_w1_reports_but_does_not_block_what_the_engine_already_rejects():
    """W1（現行引擎已拒絕）是 WARN：ADR-028 §4 的放行條件只問「A 類加嚴會不會擋下現有資料」。"""
    payload = _gm(g2={"g_code": "g_does_not_exist", "modifiers": {},
                      "repeat_count": None, "manual_override": None})
    findings = AUDIT.scan_cycle_payload(payload, RS)

    assert [f.rule for f in findings] == ["W1"]
    assert findings[0].code == "G_UNKNOWN"
    assert _blocking(payload) == []


@pytest.mark.parametrize("slots", [None, "x", [], 3])
def test_a_malformed_slots_value_is_reported_not_a_scan_wide_crash(slots):
    """`{"slots": null}` 這種畸形 payload 不得炸掉整趟掃描。

    實測（修補前）：`_engine_cycle()` 在 engine_shape 時把 raw 原封不動交給 `compute_cycle()`，
    而 `calculate.py:238` 的 `s.get(i)` 對非 dict 拋 **`AttributeError`**——不在被捕捉的
    三種例外內 → 整趟 exit 2，且 traceback 裡**沒有 entity_id／path**，正式庫上只能靠
    二分法找那一筆。而本檔自己在 `_slots_from_engine_shape` 已經守了 `isinstance(dict)`、
    `_num()` 的註解也明寫「不該讓整趟掃描因為一筆荒謬的值而中止」——是檔內自相矛盾。
    """
    findings = AUDIT.scan_cycle_payload({"seq": "GM", "slots": slots}, RS)   # 不得拋例外

    assert [f.rule for f in findings] == ["S2"]
    assert findings[0].code == "CYCLE_SHAPE_INVALID" and findings[0].where == "$.slots"
    assert AUDIT.recompute({"seq": "GM", "slots": slots}, RS)[0] is None


def test_an_unexpected_engine_exception_becomes_a_finding_with_a_location(monkeypatch):
    """引擎對某筆資料行為未定義時，記進報告（帶 entity_id／path）而不是中止閘門。

    **這不是吞錯**：閘門要的是「哪一筆」。原本的行為是整趟 exit 2 + 一份沒有實體位置的
    traceback。仍歸 W1（WARN）：它描述的是**現行**引擎的狀態，與 A 類加嚴的差值無關。
    """
    def _boom(cycle, rs):
        raise AttributeError("'NoneType' object has no attribute 'get'")

    monkeypatch.setattr(AUDIT, "compute_cycle", _boom)
    findings = AUDIT.scan_cycle_payload(_gm(), RS)

    assert [f.rule for f in findings] == ["W1"]
    assert findings[0].code == "UNEXPECTED_ENGINE_ERROR"
    assert "AttributeError" in findings[0].detail
    assert findings[0].blocking is False, "未預期例外不得把閘門推成 exit 1"
    assert AUDIT.recompute(_gm(), RS) == (None, "UNEXPECTED_ENGINE_ERROR")


def test_an_audit_abort_from_the_engine_layer_is_not_downgraded_to_a_finding(monkeypatch):
    """對照組：掃描層的中止（exit 2 語意）不得被那個寬捕捉降級成一條 WARN。"""
    def _abort(cycle, rs):
        raise AUDIT.AuditAbort("[FATAL] 測試用中止")

    monkeypatch.setattr(AUDIT, "compute_cycle", _abort)
    with pytest.raises(AUDIT.AuditAbort):
        AUDIT.scan_cycle_payload(_gm(), RS)


def test_a_nan_dimension_surfaces_as_a_warning_rather_than_silently_passing():
    """`"distance_cm": "nan"` → `_num` 回 NaN，A1（`< 0`）與 A3（`> max`）都不成立。

    這**不是**靜默略過：現行引擎查不到帶 → `M_DISTANCE_RANGE`，該列以 W1 出現在報告上。
    釘住這件事，免得日後有人「順手」讓 `_num` 對 NaN 回 None 而讓這種列完全消失。
    """
    comp = {"verb_code": "m_push", "distance_cm": "nan", "angle_deg": 0,
            "revolutions": 1, "diameter_cm": 0}
    findings = AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS)

    assert [(f.rule, f.code) for f in findings] == [("W1", "M_DISTANCE_RANGE")]


@pytest.mark.parametrize("value", [True, False])
def test_a_boolean_is_not_a_number(value):
    """Python 的 `bool` 是 `int` 子類：放行的話 `True` 會被當成 1（假的合法值）。"""
    assert AUDIT._num(value) is None

    comp = {"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": value,
            "distance_cm": 0, "angle_deg": 0}
    hits = [f for f in AUDIT.scan_cycle_payload(_cm(m3=_m(comp)), RS) if f.rule == "A2"]
    assert len(hits) == 1, "布林圈數必須報 A2（不是被當成 1 圈放行）"
    assert "不是數值" in hits[0].detail


def test_a3_does_not_double_report_what_the_engine_already_rejects_on_the_return_slot():
    """返回格的 twist／foot 由引擎的 `A_RETURN_COMPONENT` 管，A3 再報一次就是雙重誤報。

    正向對照（`a6` + reach 超帶表）單獨存在時沒有鑑別力：把 `return_slot=(i == _RETURN_SLOT)`
    改成恆 `False`，reach 那條照樣命中 → 全綠。要這條反向對照才守得住。
    """
    payload = _gm(a6=_a_slot(twist_deg=9999))
    findings = AUDIT.scan_cycle_payload(payload, RS)

    assert [f.rule for f in findings if f.rule == "A3"] == [], f"返回格 twist 被 A3 重複報：{findings}"
    assert [(f.rule, f.code) for f in findings] == [("W1", "A_RETURN_COMPONENT")]


def test_recompute_returns_engine_value_or_error_code():
    assert AUDIT.recompute(_gm(), RS) == (28.0, None)
    assert AUDIT.recompute(_cm(), RS) == (29.0, None)
    assert AUDIT.recompute({"seq": "GM", "a0": {"reach_cm": -1}}, RS) == (None, "A_NEGATIVE")


def test_unused_variant_slots_flags_silently_dropped_data():
    assert AUDIT.unused_variant_slots(_gm()) == []
    assert AUDIT.unused_variant_slots(_gm(m3=_m())) == ["m3"]
    assert AUDIT.unused_variant_slots(_cm(p5={"p_base_code": "p_place_single"})) == ["p5"]


# ═══════════════════════════════════════════════════════════════════════════
# 深走訪：staged_rows / import_rows 裡的 cycle 形狀 payload
# ═══════════════════════════════════════════════════════════════════════════
def test_iter_cycle_payloads_finds_nested_cycles():
    blob = {"rows": [{"description": "x"}, {"description": "y", "cycle": _gm()}],
            "meta": {"tpl": {"seq": "CM", "m3": None}}}
    found = dict(AUDIT.iter_cycle_payloads(blob, "staged_rows"))

    assert set(found) == {"staged_rows.rows[1].cycle", "staged_rows.meta.tpl"}


def test_iter_cycle_payloads_ignores_rows_without_cycles():
    """匯入暫存列平常**不含** cycle（只有 description/seconds/hand/quantity）→ 不得誤抓。"""
    rows = [{"_row": 3, "description": "取螺絲", "seconds": 1.2, "hand": "RH", "quantity": 1}]
    assert list(AUDIT.iter_cycle_payloads(rows, "staged_rows")) == []


@pytest.mark.parametrize("payload", [
    {"slots": {"0": {"reach_cm": 30}}},                 # 引擎形狀但沒有 seq
    {"seq": None, "slots": {"0": {"reach_cm": 30}}},    # seq 是 null
    {"seq": "gm", "slots": {"0": {"reach_cm": 30}}},    # seq 大小寫壞掉
])
def test_iter_cycle_payloads_finds_engine_shaped_blobs_with_a_broken_seq(payload):
    """`"slots" in obj` 這半邊判準必須有測試守著。

    實測突變：把 `if obj.get("seq") in ("GM","CM") or "slots" in obj:` 的 `or "slots" in obj`
    拿掉 → unit 53 passed／integration 7 passed（全綠）。兩個 staging 整合測試種的都只有
    帶合法 `seq` 的 payload，所以這半邊從來沒被觸發過。

    **修正一則審查敘述**：被弄丟的不是「斷言 #9 的形狀」——那種 payload 自己帶著
    `seq="GM"`，另一半判準照樣撈得到。真正被弄丟的是**引擎形狀但 seq 壞掉／缺席**的 blob：
    它們今天由 `scan_cycle_payload` 判 S2（WARN，不影響 exit code），但少了這半邊會
    **整筆從報告上消失**，而【掃描範圍】的列數不變——即「報告謊報掃描量」的同型問題。
    """
    found = dict(AUDIT.iter_cycle_payloads({"rows": [payload]}, "staged_rows"))
    assert set(found) == {"staged_rows.rows[0]"}, "引擎形狀 blob 必須被撈出來，不能靜默消失"
    # 撈出來之後的歸類：S2（WARN），不是 BLOCK——這條也一併釘住，免得日後被誤升級為閘門
    assert [f.rule for f in AUDIT.scan_cycle_payload(payload, RS)] == ["S2"]


# ═══════════════════════════════════════════════════════════════════════════
# 報告與 exit code
# ═══════════════════════════════════════════════════════════════════════════
def _record(findings) -> object:
    return AUDIT.ScanRecord(source="most_cycles", entity_id="id-1", path="slot_inputs",
                            rule_set_code=RS.code, orig_tmu=28.0, engine_tmu=28.0,
                            engine_error=None, findings=list(findings))


def test_render_exit_code_is_nonzero_only_for_blocking_findings():
    warn_only = _record([AUDIT.Finding("W2", "TMU_CACHE_DRIFT", "$", "d")])
    s2_only = _record([AUDIT.Finding("S2", "CYCLE_SHAPE_INVALID", "$", "d")])
    block = _record([AUDIT.Finding("A1", "M_NEGATIVE", "$.m3", "d")])

    _, code_clean = AUDIT.render([_record([])], {"most_cycles.slot_inputs": 1}, [], verbose=False)
    _, code_warn = AUDIT.render([warn_only], {"most_cycles.slot_inputs": 1}, [], verbose=False)
    _, code_s2 = AUDIT.render([s2_only], {"most_cycles.slot_inputs": 1}, [], verbose=False)
    report, code_block = AUDIT.render([block], {"most_cycles.slot_inputs": 1}, [], verbose=False)

    assert (code_clean, code_warn, code_s2, code_block) == (0, 0, 0, 1)
    assert "M_NEGATIVE" in report and "id-1" in report and "原 total_tmu=28" in report


def test_render_says_out_loud_that_a_green_small_dataset_proves_nothing():
    """ADR-028 斷言 #34：放行條件是「對正式環境全量資料 exit 0」，不是 CI 條件。"""
    report, code = AUDIT.render([], {}, [], verbose=False)
    assert code == 0
    assert "正式環境全量資料" in report


# ═══════════════════════════════════════════════════════════════════════════
# 指標區塊：ai_parse_runs.drafts[].cycle（**不影響 exit code**）
# ═══════════════════════════════════════════════════════════════════════════
def _draft_record(findings) -> object:
    return AUDIT.ScanRecord(source="ai_parse_runs", entity_id="run-9 (routing=review)",
                            path="drafts[0].cycle", rule_set_code=RS.code, orig_tmu=None,
                            engine_tmu=0.0, engine_error=None, findings=list(findings))


def test_ai_draft_findings_are_reported_but_never_change_the_exit_code():
    """合成一筆違規的 AI 草稿 → 出現在【指標】區塊，但 exit code 仍為 0。

    為什麼它不是閘門：`drafts[].cycle` 是**尚未被採用**的建議，不會被原樣重存回
    `most_cycles`；被採用時會重過 `CycleIn` + `compute_cycle`（`most_compiler/engine_gate.py`），
    屆時被加嚴版本擋下**正是預期行為**。這裡量的是「加嚴後有多少草稿會開始被拒」的**觀測值**。
    """
    dirty = _draft_record([AUDIT.Finding("A1", "M_NEGATIVE", "$.m3.m_components[0].distance_cm", "-5 < 0")])
    report, code = AUDIT.render([_record([])], {"most_cycles.slot_inputs": 1}, [],
                                verbose=False, draft_records=[dirty])

    assert code == 0, "AI 草稿命中不得影響 exit code"
    section = report.split("【指標：AI 草稿（不影響 exit code）】")[1]
    assert "M_NEGATIVE" in section, "違規草稿必須顯示在指標區塊"
    assert "run-9" in section
    assert "加嚴後會被拒 1 個" in section


def test_ai_draft_findings_are_not_mixed_into_the_block_or_warn_sections():
    """指標不得混進既有分類：BLOCK／WARN 區塊裡不能出現這筆草稿。"""
    dirty = _draft_record([AUDIT.Finding("A1", "M_NEGATIVE", "$.m3", "d"),
                           AUDIT.Finding("W2", "TMU_CACHE_DRIFT", "$", "d")])
    report, _ = AUDIT.render([_record([])], {}, [], verbose=False, draft_records=[dirty])

    head, indicator = report.split("【指標：AI 草稿（不影響 exit code）】")
    assert "run-9" not in head, "草稿不得出現在 BLOCK／WARN 區塊"
    assert "run-9" in indicator


def test_audit_returns_ai_drafts_as_a_separate_value_not_a_filtered_view():
    """結構性保證：`audit()` 的簽章把草稿分開回傳，不是靠 render 過濾。

    若哪天有人把草稿併回 `records` 再於 render 篩掉，別處重用 `records` 就會把指標算成閘門。
    """
    import inspect

    ret = inspect.signature(AUDIT.audit).return_annotation
    assert ret.count("list[ScanRecord]") == 2, f"audit() 應回傳兩份獨立的紀錄清單：{ret}"
    assert "draft_records" in inspect.signature(AUDIT.render).parameters


# ═══════════════════════════════════════════════════════════════════════════
# 命中率：讓 ADR-028〈重評訊號〉的 1% 門檻可以直接對照
# ═══════════════════════════════════════════════════════════════════════════
def test_report_prints_the_hit_rate_against_the_one_percent_threshold():
    records = [_record([AUDIT.Finding("A1", "M_NEGATIVE", "$", "d")])] + [_record([]) for _ in range(199)]
    report, code = AUDIT.render(records, {"most_cycles.slot_inputs": 200}, [], verbose=False)

    assert code == 1
    assert "BLOCK 命中率：1/200 = 0.50%" in report
    assert "1.00%" in report                       # 門檻本身要印出來
    assert "已超過" not in report                   # 0.5% 未超過門檻


def test_report_escalates_when_the_hit_rate_exceeds_one_percent():
    """>1% → 報告要直說「不要直接修資料了事」，而不是讓人默默修完就上線。"""
    records = [_record([AUDIT.Finding("A1", "M_NEGATIVE", "$", "d")]) for _ in range(3)]
    records += [_record([]) for _ in range(97)]
    report, _ = AUDIT.render(records, {"most_cycles.slot_inputs": 100}, [], verbose=False)

    assert "BLOCK 命中率：3/100 = 3.00%" in report
    assert "已超過" in report
    assert "退回 B 類" in report and "不要直接修資料了事" in report


def test_hit_rate_does_not_divide_by_zero_on_an_empty_scan():
    report, _ = AUDIT.render([], {}, [], verbose=False)
    assert "BLOCK 命中率：0/0 = n/a（掃描 0 筆）" in report


# ═══════════════════════════════════════════════════════════════════════════
# Runbook：`--help` 必須自足（正式環境跑法不能只存在於某次對話裡）
# ═══════════════════════════════════════════════════════════════════════════
def test_help_carries_the_production_runbook():
    """`--help` 帶著完整 runbook；且它是**單一權威**（檔頭 docstring 由它拼出來，不是另抄）。"""
    help_text = AUDIT.build_parser().format_help()

    for needle in (
        "| tee",                                          # 存檔
        "2>&1",                                           # 不接 stderr 的話證據檔會是 0 bytes
        "PIPESTATUS",                                     # tee 之後 $? 會騙人
        "workflow_audit_log",                             # 命中時先留痕（目前待 ADR 修訂）
        "退回 B 類",                                       # ADR 重評訊號
    ):
        assert needle in help_text, f"--help 缺少 {needle!r}"
    assert AUDIT._RUNBOOK in help_text
    assert AUDIT._RUNBOOK in AUDIT.__doc__, "runbook 必須與檔頭 docstring 同一份"


@pytest.mark.parametrize("needle,why", [
    ("cd <repo>/ddm-v2", "沒交代工作目錄，非本專案的人第一步就卡住"),
    ("python3.11 -m venv", "沒建 venv → 系統 python3 會 ModuleNotFoundError: pydantic"),
    ("--require-hashes", "不從鎖檔裝＝裝出與 CI/Docker 不同的一組依賴（ADR-029）"),
    ('"$AUDIT_VENV/bin/python"', "沒指明用 venv 的直譯器，Debian/Ubuntu 連 `python` 都沒有"),
])
def test_runbook_tells_a_non_developer_how_to_get_a_working_interpreter(needle, why):
    """runbook 的讀者是 DBA／SRE，不是本專案的開發者。

    實測（修補前）：`cd`／`venv`／`pip`／`requirements`／`python3`／`bash` 關鍵字命中數全部 0，
    用系統 python3 直接跑 → `ModuleNotFoundError: No module named 'pydantic'`。
    """
    assert needle in AUDIT._RUNBOOK, f"runbook 缺少 {needle!r}：{why}"


def test_runbook_does_not_install_the_dev_lock_on_the_credential_holding_host():
    """跳板機只需要 pydantic / sqlalchemy / asyncpg / greenlet——四個都在 runtime 鎖檔裡。

    裝 `requirements-dev.lock` 會額外帶進 pytest / mypy / ruff / coverage / httpx，
    而**這台是唯一持有正式庫憑證的機器**。
    """
    assert "-r requirements-dev.lock" not in AUDIT._RUNBOOK
    assert "-r requirements.lock" in AUDIT._RUNBOOK
    lock = (_REPO / "requirements.lock").read_text(encoding="utf-8")
    for package in ("pydantic==", "sqlalchemy==", "asyncpg==", "greenlet=="):
        assert package in lock, f"runtime 鎖檔缺 {package}，runbook 第 0 步會裝不起來"


def test_runbook_decides_whether_to_fix_before_explaining_how_to_fix():
    """【命中率】那一步必須排在「怎麼修」之前：>1% 的正解是回頭改 ADR，不是把資料修乾淨。

    順序顛倒的話，照著讀的人會先做完一次性修補 migration，才讀到「其實不該修」。
    """
    body = AUDIT._RUNBOOK
    assert body.index("先看報告結尾的【命中率】") < body.index("先留痕再修"), (
        "runbook 仍然先教「怎麼修」才教「要不要修」")


@pytest.mark.parametrize("needle,why", [
    ("NOLOGIN", "登入角色必須能登入 → 授權要拆成 NOLOGIN 群組 + LOGIN 成員兩層"),
    ("VALID UNTIL", "一次性閘門不該在正式庫留下永久帳號"),
    ("CONNECTION LIMIT", "同上：一次性帳號要有連線上限"),
    ("default_transaction_read_only", "即使日後誤 GRANT INSERT 仍被擋在 25006"),
    ("statement_timeout", "長交易要有上限"),
    ("idle_in_transaction_session_timeout", "掛住的交易會一直卡住 VACUUM 與 DDL"),
    ("DROP ROLE ddm_audit_run", "收工要把一次性帳號收掉"),
    (r"\password", "CREATE ROLE ... PASSWORD '<明文>' 會進 server log 與 command history"),
    ("FOR ROLE", "不帶 FOR ROLE 的 ALTER DEFAULT PRIVILEGES 等於沒生效，且製造錯誤的安心感"),
    ("percent-encode", "密碼含 @ 會被解析成 host，錯誤訊息完全誤導"),
    ("不要同時部署 migration", "長交易會擋住 DDL，該表在等待期間實質不可用"),
    ("VACUUM", "長交易期間 dead tuple 無法回收"),
    ("read replica", "量大時的正解（本腳本全程唯讀）"),
    ("pg_last_xact_replay_timestamp", "replica 落後 N 分鐘 → 那段時間的髒列不在快照裡，卻仍 exit 0"),
    ("恆為 on", "hot standby 上 transaction_read_only 由 PG 強制，不再證明腳本的唯讀設定生效"),
    ("REVOKE CONNECT ON DATABASE", "少這行，收尾的 DROP ROLE ddm_audit_ro 會因為權限依賴而失敗"),
    ("137", "OOM kill 的 exit code 不在 0/1/2 的圖例裡，而 tee 存下的檔案長得跟 FATAL 一樣"),
    ("requirements.lock", "跳板機是唯一持有正式庫憑證的機器：只裝 runtime，不裝 pytest/mypy/ruff"),
    ("--no-index", "正式跳板機通常無對外 egress，要有離線安裝路徑"),
    ("git -C <repo> archive", "沒交代 repo 怎麼上跳板機，第 0 步就卡住"),
    ("prepared_statement_cache_size", "pgbouncer transaction pooling 下 asyncpg 會撞名 → exit 2"),
])
def test_runbook_states_the_operational_facts_it_used_to_get_wrong(needle, why):
    """B 類審查逐條：這段文字會變成有人對正式環境下的指令，錯一個字就是實質事故。"""
    assert needle in AUDIT._RUNBOOK, f"runbook 缺少 {needle!r}：{why}"


def test_runbook_does_not_grant_select_on_all_tables():
    """`ON ALL TABLES` 遠超所需：會一併給出 app_users（員編／姓名／角色）、

    `ai_parse_runs.llm_raw_response`、`excel_imports.raw_payload`（整份上傳的 Excel）。
    本腳本只讀 6 張業務表 + rule_sets/rule_*。
    """
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA public" not in AUDIT._RUNBOOK
    assert "**不要**用 GRANT SELECT ON ALL TABLES" in AUDIT._RUNBOOK, "要說明為什麼不用"
    for table in ("most_cycles", "motion_module_versions", "motion_templates",
                  "excel_imports", "import_rows", "ai_parse_runs", "rule_sets"):
        assert table in AUDIT._RUNBOOK, f"逐表授權清單漏了 {table}"


@pytest.mark.parametrize("table,forbidden_column", [
    ("excel_imports", "raw_payload"),          # 整份上傳的 Excel
    ("ai_parse_runs", "llm_raw_response"),     # 整段模型輸出
])
def test_runbook_grants_the_sensitive_tables_column_by_column(table, forbidden_column):
    """否決 `ON ALL TABLES` 的三個理由裡，有兩個是**欄位**——表級 GRANT 解不掉。

    原本 runbook 用 app_users／`ai_parse_runs.llm_raw_response`／`excel_imports.raw_payload`
    三個理由否決 `GRANT SELECT ON ALL TABLES`，然後給出的逐表授權**包含後兩張表**，
    而表級 GRANT 不排除欄位——三個理由裡兩個沒被解決。
    腳本的查詢本來就是逐欄的（`audit()`），改欄級授權零成本。
    """
    lines = [ln for ln in AUDIT._RUNBOOK.splitlines()
             if "GRANT SELECT (" in ln and f"ON {table} " in ln]
    assert len(lines) == 1, f"{table} 不是欄級授權：{lines}"
    columns = lines[0].split("(", 1)[1].split(")", 1)[0]      # 只看括號內的欄位清單
    assert forbidden_column not in columns, f"{table} 的欄級授權仍含 {forbidden_column}"
    # 表級授權清單裡不得再出現這兩張表（否則欄級那行等於白寫）
    table_level = AUDIT._RUNBOOK.split("GRANT SELECT ON\n")[1].split("TO ddm_audit_ro;")[0]
    assert table not in table_level, f"{table} 同時出現在表級授權清單裡"


def test_runbook_keeps_the_rule_set_family_at_table_level():
    """`load_rule_set_from_db()` 用 `select(Model)` 取整列——rule-set 家族改欄級會在加欄位時炸。"""
    table_level = AUDIT._RUNBOOK.split("GRANT SELECT ON\n")[1].split("TO ddm_audit_ro;")[0]
    for table in ("rule_sets", "rule_a_bands", "rule_m_rotation_bands", "rule_x_options"):
        assert table in table_level, f"{table} 應維持表級授權"


def test_runbook_documents_the_three_exit_codes():
    """exit 1（有命中）與 exit 2（掃描沒跑完）必須分得開，且 runbook 要說清楚。

    原本兩者都是 1：`[FATAL]` 中止走 `SystemExit(str)`（預設 exit 1）而且訊息走 stderr，
    只接 stdout 的 `| tee` 會存下一個 **0 bytes** 的證據檔——「掃描炸掉」與「有 BLOCK 命中」
    在放行者眼中長得一模一樣。
    """
    assert (AUDIT._EXIT_CLEAN, AUDIT._EXIT_BLOCKED, AUDIT._EXIT_FATAL) == (0, 1, 2)
    for needle in ("0 = ", "1 = ", "2 = ", "這份報告不存在", "0 bytes"):
        assert needle in AUDIT._RUNBOOK, f"runbook 缺少 {needle!r}"


def test_runbook_writes_the_evidence_file_outside_the_repo():
    """repo 內沒有 *.txt 的 ignore 規則：一份正式環境資料報告會直接出現在 git status。"""
    assert "OUT=~/adr028_audit_" in AUDIT._RUNBOOK
    ignore = (_REPO / ".gitignore").read_text(encoding="utf-8").split()
    assert "*.txt" not in ignore, "若日後加了 *.txt ignore 規則，runbook 的理由要一起改"


def test_runbook_survives_python_optimise_mode():
    """`python -OO` 會把 docstring 剝成 None——runbook 不能只存在於 docstring 字面裡。

    原本 `_RUNBOOK = MARKER + (__doc__ or "").split(MARKER)[-1]`，-OO 下整段 runbook
    靜默消失（`--help` 只剩 marker）。現在 `_RUNBOOK` 是常數，docstring 反過來由它拼成。
    """
    assert AUDIT._RUNBOOK.startswith(AUDIT._RUNBOOK_MARKER)
    assert len(AUDIT._RUNBOOK) > 2000, "runbook 不該只剩下標題"

    out = subprocess.run(
        [sys.executable, "-OO", str(_SCRIPT), "--help"],
        env={**os.environ, "PYTHONPATH": str(_REPO / "src")},
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr
    assert "PIPESTATUS" in out.stdout, "-OO 下 runbook 消失了"


def test_runbook_shell_continuation_survives_into_help():
    """runbook 若不是 raw 字串，shell 續行會被 Python 吃掉，指令印成一整行貼不能用。"""
    help_text = AUDIT.build_parser().format_help()
    assert "audit_slot_inputs.py \\\n" in help_text


# ═══════════════════════════════════════════════════════════════════════════
# 閘門本身的正確性：連線來源、唯讀、分頁、exit code
# ═══════════════════════════════════════════════════════════════════════════
def test_missing_database_url_aborts_instead_of_using_the_settings_default(monkeypatch):
    """未設 `DATABASE_URL` → 立即中止，**不得**吃 settings 的預設值。

    `settings.py` 的 fallback 是 `postgresql+asyncpg://ddm_user:ddm_pass@localhost:5432/ddm_v2`。
    export 掉在別的 shell、改用 `sudo`（env_reset 清環境變數）、或包成 cron，都會靜默連到
    跳板機上的本機 dev PG，然後產出一份格式完全正確、結論寫「零命中」的假報告。
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(AUDIT.AuditAbort) as excinfo:
        AUDIT.require_database_url()
    assert "DATABASE_URL" in str(excinfo.value)

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    assert AUDIT.require_database_url() == "postgresql+asyncpg://u:p@h:5432/d"


@pytest.mark.parametrize("url,missing", [
    ("postgresql+asyncpg:///ddm", "host"),                    # 兩者皆空
    ("postgresql+asyncpg://ddm_audit_run@/ddm", "host"),      # 只有使用者
    ("postgresql+asyncpg://@dbhost:5432/ddm", "username"),    # 只有主機
])
def test_database_url_without_host_or_username_aborts(monkeypatch, url, missing):
    """`postgresql+asyncpg:///db` 是合法 URL，但 host／username 皆空 → 落到 libpq 預設。

    那就是 `PGHOST` / `~/.pgpass` / unix socket ＋ OS 使用者：在 DB 主機上跑，peer auth
    連上的通常是 **superuser**，runbook 第 1 步那個唯讀角色等於沒發生——而報告會長得
    完全正確（【連線身分】區塊仍會印出一個看起來合理的 current_user）。
    """
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(AUDIT.AuditAbort) as excinfo:
        AUDIT.require_database_url()
    assert missing in str(excinfo.value)


def test_redact_url_never_prints_a_password_even_in_the_query_string():
    """`render_as_string(hide_password=True)` **只遮 `URL.password`**，`URL.query` 逐字 render。

    而 asyncpg dialect 會 `opts.update(url.query)`——所以 `?password=` 是合法且會生效的寫法。
    被 runbook 的 percent-encode 警告勸退的操作者，最自然的迴避動作就是把密碼搬進 query：
    連得上、掃描正常跑完，然後正式庫密碼明文落進一份要附進 ADR 核可、被傳閱的報告。

    **修正一則假測試**：原本唯一守這件事的斷言是
    `assert "***" in rendered or "@" not in <authority>`——帶 `or` 逃生門，
    而且從未斷言真正的密碼字串不在輸出裡。標準 URL 下 `***` 恆真，另一半永遠不會被求值。
    """
    from sqlalchemy.engine import make_url

    secret = "P@ss/w0rd"
    query_secret = "q-s3cr3t-in-query"
    url = ("postgresql+asyncpg://ddm_audit_run:P%40ss%2Fw0rd@dbhost:5432/ddm"
           f"?password={query_secret}&sslpassword=another-s3cr3t&sslmode=require")

    # 前提：SQLAlchemy 自己的遮罩**擋不住** query 那一半（沒有這行，下面的斷言看不出鑑別力）
    assert query_secret in make_url(url).render_as_string(hide_password=True)

    rendered = AUDIT.redact_url(url)

    assert secret not in rendered and query_secret not in rendered
    assert "another-s3cr3t" not in rendered
    assert rendered == "postgresql+asyncpg://ddm_audit_run@dbhost:5432/ddm?password=***&sslmode=***&sslpassword=***"


def test_redact_url_keeps_what_the_approver_needs_to_identify_the_database():
    """遮罩不能遮過頭：核可者要靠 driver／使用者／主機／庫名判斷這是不是正式庫。"""
    assert AUDIT.redact_url("postgresql+asyncpg://ddm_audit_run:pw@db.prod:5432/ddm_prod") == (
        "postgresql+asyncpg://ddm_audit_run@db.prod:5432/ddm_prod")


def test_cli_exits_2_and_says_why_when_database_url_is_unset():
    """端對端：真的跑一次腳本（不設 DATABASE_URL），確認它中止而不是連上預設庫。"""
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["PYTHONPATH"] = str(_REPO / "src")
    out = subprocess.run([sys.executable, str(_SCRIPT)], env=env,
                         capture_output=True, text=True, timeout=180)

    assert out.returncode == AUDIT._EXIT_FATAL, f"應為 exit 2，實得 {out.returncode}"
    assert "[FATAL]" in out.stderr and "DATABASE_URL" in out.stderr
    assert out.stdout == "", "中止時不得印出任何看起來像報告的東西"


# ── 模組載入期的失敗：只有 subprocess 測得到（monkeypatch `_main_async` 結構上碰不到 import 期）──
def _run_with_shim(tmp_path, shim_name: str, source: str, *args: str):
    """在 PYTHONPATH 最前面放一個 shim 後，用 subprocess **實跑**腳本。

    `DATABASE_URL` 刻意不設：這樣「沒設 URL 的 AuditAbort」也會走到 exit 2，
    所以每條測試都必須額外斷言 stderr 是**模組載入期**的訊息，才不會用錯理由通過。
    """
    (tmp_path / shim_name).write_text(source, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(_REPO / "src")])
    return subprocess.run([sys.executable, str(_SCRIPT), *args], env=env,
                          capture_output=True, text=True, timeout=180)


_SHIM_MISSING_PYDANTIC = 'raise ImportError("simulated: pydantic is not installed")\n'

_SHIM_CONTRACT_DRIFT = """\
import ddm_v2.schemas.v2.most as most
_orig = most.cycle_in_to_engine
def _drifted(cycle_in):
    out = _orig(cycle_in)
    out["slots"] = {i: {} for i in out["slots"]}   # 模擬：格位模型不再有 manual_override
    return out
most.cycle_in_to_engine = _drifted
"""

_SHIM_NEW_REQUIRED_FIELD = """\
import pydantic
import ddm_v2.schemas.v2.most as most

class _RequiresTicket(pydantic.BaseModel):
    ticket_id: str

class _CycleIn:                       # 模擬：ManualOverride 新增必填欄位 → 哨兵 payload 驗不過
    model_fields = most.CycleIn.model_fields
    @staticmethod
    def model_validate(data):
        _RequiresTicket.model_validate({})        # 真的 pydantic ValidationError
most.CycleIn = _CycleIn
"""


@pytest.mark.parametrize("shim_name,source,needle", [
    ("pydantic.py", _SHIM_MISSING_PYDANTIC, "ModuleNotFoundError|ImportError"),
    ("sitecustomize.py", _SHIM_CONTRACT_DRIFT, "無法從 cycle_in_to_engine"),
    ("sitecustomize.py", _SHIM_NEW_REQUIRED_FIELD, "ValidationError"),
])
def test_module_load_failures_exit_2_not_1(tmp_path, shim_name, source, needle):
    """import 期／覆蓋圖反推期的失敗必須是 exit **2**（掃描沒跑完），不是 exit 1。

    實測（修補前）三條全部拿到 exit **1**：
      /usr/bin/python3 …            → ModuleNotFoundError: pydantic          exit=1
      契約漂移                       → AuditAbort: [FATAL] 無法反推格位覆蓋圖   exit=1
      ManualOverride 新增必填欄位     → pydantic ValidationError               exit=1
    也就是說 `AuditAbort`——一個**專門為了 exit 2 而發明的型別**——在它自己被丟出的第一個
    現場拿到 1。而 runbook 的圖例寫著「1 = 有 BLOCK 命中 → 去修資料」：拿到 exit 1＋空 stdout
    的 DBA 會判成「有命中」然後去改正式資料，真相卻是**掃描根本沒跑**。

    這三條只有 subprocess 測得到：`monkeypatch.setattr(AUDIT, "_main_async", ...)` 那組測試
    在**模組已經載入成功之後**才生效，結構上不可能覆蓋 import 期。
    """
    import re

    out = _run_with_shim(tmp_path, shim_name, source)

    assert out.returncode == AUDIT._EXIT_FATAL, f"應為 exit 2，實得 {out.returncode}\n{out.stderr}"
    assert "模組載入期失敗" in out.stderr, f"沒說出是載入期失敗：{out.stderr[-800:]}"
    assert re.search(needle, out.stderr), f"traceback 沒指出真正的成因：{out.stderr[-800:]}"
    assert "未設定 DATABASE_URL" not in out.stderr, "用錯理由通過了（守衛沒有先於連線檢查生效）"
    assert out.stdout == "", "中止時不得印出任何看起來像報告的東西"


def test_help_still_works_without_the_third_party_dependencies(tmp_path):
    """缺依賴時 `--help` 仍要印得出 runbook——runbook 第 0 步講的正是怎麼把依賴裝起來。

    把 import 收進守衛後這件事才成立：原本 `import pydantic` 在 module 層直接炸，
    連「怎麼建 venv」都讀不到。
    """
    out = _run_with_shim(tmp_path, "pydantic.py", _SHIM_MISSING_PYDANTIC, "--help")

    assert out.returncode == 0, out.stderr
    assert "python3.11 -m venv" in out.stdout and "PIPESTATUS" in out.stdout


@pytest.mark.parametrize("stub_kind,expected", [
    ("clean", 0),
    ("blocked", 1),
    ("abort", 2),
    ("crash", 2),
])
def test_main_maps_outcomes_to_distinct_exit_codes(monkeypatch, stub_kind, expected):
    """`[FATAL]` 中止與未捕捉例外都必須是 exit 2，不能與「有 BLOCK 命中」的 exit 1 混淆。"""
    async def _stub(verbose):
        if stub_kind == "abort":
            raise AUDIT.AuditAbort("[FATAL] 測試用中止")
        if stub_kind == "crash":
            raise RuntimeError("boom")
        return 0 if stub_kind == "clean" else 1

    monkeypatch.setattr(sys, "argv", ["audit_slot_inputs.py"])
    monkeypatch.setattr(AUDIT, "_main_async", _stub)
    with pytest.raises(SystemExit) as excinfo:
        AUDIT.main()
    assert excinfo.value.code == expected


async def test_readonly_snapshot_uses_postgres_level_enforcement():
    """唯讀要有**機械保證**，不能只寫在 runbook 的 role 步驟裡（那是一段人工步驟）。

    runbook 第 2 步叫人 export 一整條 URL，最省事的做法就是貼手邊的 app 帳號 URL——
    那時「先建 read-only role」那一步等於沒發生。`postgresql_readonly` 讓保證回到腳本內：
    之後任何寫入當場 25006（已對真 PG 實測）。
    """
    captured = {}

    class _Session:
        async def connection(self, execution_options=None):
            captured.update(execution_options or {})

    await AUDIT.begin_readonly_snapshot(_Session())

    assert captured.get("postgresql_readonly") is True, "少了它，任何寫入都不會被 25006 擋下"
    assert captured.get("isolation_level") == "REPEATABLE READ", "沒有單一快照＝掃描期間資料會漂"
    # DEFERRABLE 只在 SERIALIZABLE READ ONLY 下有作用，在 REPEATABLE READ 下是 no-op。
    # 留著一個 no-op 旗標會招來「那把 isolation 改成 SERIALIZABLE 讓它生效吧」的誤修——
    # 而那會讓這條長交易可能被 serialization failure 中斷（DEFERRABLE 還會沉默等待）。
    assert "postgresql_deferrable" not in captured, "no-op 旗標會招來把 isolation 升成 SERIALIZABLE 的誤修"


async def test_pagination_is_keyset_and_the_cursor_is_the_last_row_of_the_page():
    """OFFSET + 隨機 UUID 排序 + READ COMMITTED → 線上只要有插入就會漏列（漏到髒列＝假綠）。

    排序鍵是 uuid4 主鍵，新列會隨機插進既有順序的任何位置；掃描期間每插入一筆排在目前
    offset 之前的列，後面每頁整體位移一列 → 恰好有一列永遠不會被讀到。

    **假 session 必須真的套用 keyset 條件**，否則守不住游標本身。實測突變：
    `last = getattr(rows[-1], key)` → `rows[0]` 時，舊版假 session（照順序發預先排好的頁）
    完全不受影響 → 全綠；而真實行為是**每頁只前進一列、下一頁重吐 `_PAGE-1` 筆已讀過的列**，
    【命中率】的分母 `len(records)` 被灌水，ADR-028 的 1% 門檻直接失效。
    """
    from ddm_v2.models.v2.worksheet import MostCycle

    sql_seen: list[str] = []
    all_rows = [types.SimpleNamespace(id=i) for i in range(AUDIT._PAGE + 1)]

    class _Session:
        async def execute(self, stmt):
            sql_seen.append(str(stmt))
            params = stmt.compile().params
            cursor = params.get("id_1")
            visible = all_rows if cursor is None else [r for r in all_rows if r.id > cursor]
            return _FakeResult(visible[:AUDIT._PAGE])

    rows = [r async for r in AUDIT._page(_Session(), select(MostCycle.id), MostCycle.id)]

    assert [r.id for r in rows] == list(range(AUDIT._PAGE + 1)), (
        "keyset 游標沒有落在本頁最後一列：出現漏列或重複列")
    assert all("OFFSET" not in sql.upper() for sql in sql_seen), f"仍在用 OFFSET 分頁：{sql_seen}"
    assert "most_cycles.id >" in sql_seen[1], f"第二頁沒有 keyset 條件：{sql_seen[1]}"
    assert len(sql_seen) == 2, f"多發了頁＝游標沒有走到底：{len(sql_seen)} 頁"


# ── 假 session：讓 `audit()` 的守衛與計數在不碰 DB 的情況下也測得到 ──────────────
class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeScanSession:
    """依 `select()` 的目標 model 回傳預先種好的列；同一個 model 只回一次（第二頁為空）。"""

    def __init__(self, rows_by_model):
        self._rows_by_model = rows_by_model
        self._served: set[str] = set()

    async def execute(self, stmt):
        model = stmt.column_descriptions[0]["entity"]
        if model.__name__ in self._served:
            return _FakeResult([])
        self._served.add(model.__name__)
        return _FakeResult(self._rows_by_model.get(model, []))


def _rule_set_rows(*, active_count: int = 1):
    from ddm_v2.models.v2.rule_set import RuleSet

    rows = [types.SimpleNamespace(id=uuid.UUID(int=1), code=RS.code, is_active=True)]
    if active_count == 0:
        rows[0].is_active = False
    elif active_count > 1:
        rows.append(types.SimpleNamespace(id=uuid.UUID(int=2), code="OTHER", is_active=True))
    return {RuleSet: rows}


def _audit_session(rows_by_model, monkeypatch, *, active_count: int = 1):
    async def _fake_load(_session, code):
        assert code == RS.code, f"不該去載 {code!r}"
        return RS

    monkeypatch.setattr(AUDIT, "load_rule_set_from_db", _fake_load)
    return _FakeScanSession({**_rule_set_rows(active_count=active_count), **rows_by_model})


async def test_a_dangling_rule_set_id_aborts_the_scan_instead_of_skipping_the_row(monkeypatch):
    """FK 指到不存在的 rule-set → 中止（exit 2），**不得** `continue`。

    實測：把這個守衛改成 `continue` → unit 53 passed / integration 7 passed（全綠）。
    那是**最危險**的一種靜默 fallback：它朝「恆綠」的方向丟列——被丟掉的列剛好是髒列，
    報告就會寫「零命中」。
    """
    from ddm_v2.models.v2.worksheet import MostCycle

    session = _audit_session({MostCycle: [types.SimpleNamespace(
        id=uuid.UUID(int=9), wi_row_id=uuid.UUID(int=8), rule_set_id=uuid.UUID(int=99),
        slot_inputs=_gm(), total_tmu=28)]}, monkeypatch)

    with pytest.raises(AUDIT.AuditAbort) as excinfo:
        await AUDIT.audit(session)
    assert "rule_set_id" in str(excinfo.value)


async def test_a_dangling_rule_set_id_on_motion_module_versions_also_aborts(monkeypatch):
    """三個同型守衛必須**每一個**都有測試。

    實測：`most_cycles` 與 `ai_parse_runs` 兩處補了測試，`motion_module_versions` 沒有——
    把它的 `raise AuditAbort` 改成 `continue` → 全套測試仍然全綠。而那正是本檔 docstring
    自己稱為「最危險」的一類靜默 fallback：朝「恆綠」的方向丟列，被丟掉的剛好是髒列時，
    報告就會寫「零命中」。
    """
    from ddm_v2.models.v2.motion_module import MotionModuleVersion

    session = _audit_session({MotionModuleVersion: [types.SimpleNamespace(
        id=uuid.UUID(int=20), module_id=uuid.UUID(int=21), version_no=1,
        rule_set_id=uuid.UUID(int=99), rows=[{"cycle": _gm()}])]}, monkeypatch)

    with pytest.raises(AUDIT.AuditAbort) as excinfo:
        await AUDIT.audit(session)
    assert "rule_set_id" in str(excinfo.value)


async def test_a_dangling_rule_set_id_on_ai_parse_runs_also_aborts(monkeypatch):
    from ddm_v2.models.v2.ai_ops import AiParseRun

    session = _audit_session({AiParseRun: [types.SimpleNamespace(
        id=uuid.UUID(int=7), routing_status="review", rule_set_id=uuid.UUID(int=99),
        drafts=[{"cycle": _gm()}])]}, monkeypatch)

    with pytest.raises(AUDIT.AuditAbort):
        await AUDIT.audit(session)


@pytest.mark.parametrize("active_count", [0, 2])
async def test_templates_abort_when_the_active_rule_set_is_ambiguous(monkeypatch, active_count):
    """`motion_templates` 不帶 rule_set_code → 需要 active；沒有或不只一個都是設定錯誤。

    實測兩處守衛都可以被拆成靜默猜測而測試全綠：
      `_require_active` 的中止 → 猜第一個；
      `active[0] if len(active)==1 else None` → `if active else None`。
    """
    from ddm_v2.models.v2.motion_template import MotionTemplate

    session = _audit_session(
        {MotionTemplate: [types.SimpleNamespace(
            id=uuid.UUID(int=5), name_zh="T", cycle_template=_gm())]},
        monkeypatch, active_count=active_count)

    with pytest.raises(AUDIT.AuditAbort) as excinfo:
        await AUDIT.audit(session)
    assert "is_active" in str(excinfo.value)


async def test_require_active_returns_the_single_active_code():
    """正向對照：剛好一個 active 時要正常回傳（否則上面兩條可能是恆真）。"""
    cache = AUDIT._RuleSetCache(session=None)
    cache.active_code = RS.code
    assert AUDIT._require_active(cache, "motion_templates") == RS.code


async def test_counts_report_the_real_number_of_rows_scanned(monkeypatch):
    """報告的【掃描範圍】不得謊報。

    實測：把 `counts[...] = n` 改成 `= 0` → 全綠。runbook 要人**讀這份報告決定正式部署**，
    一份印「掃描 0 筆」但閘門其實正常的報告，和一份閘門壞掉的報告，讀起來一模一樣。
    """
    from ddm_v2.models.v2.ai_ops import AiParseRun
    from ddm_v2.models.v2.import_staging import ExcelImport, ImportRow
    from ddm_v2.models.v2.motion_module import MotionModuleVersion
    from ddm_v2.models.v2.motion_template import MotionTemplate
    from ddm_v2.models.v2.worksheet import MostCycle

    rs_id = uuid.UUID(int=1)
    session = _audit_session({
        MostCycle: [types.SimpleNamespace(id=uuid.UUID(int=10 + i), wi_row_id=uuid.UUID(int=1),
                                          rule_set_id=rs_id, slot_inputs=_gm(), total_tmu=28)
                    for i in range(3)],
        MotionModuleVersion: [types.SimpleNamespace(
            id=uuid.UUID(int=20), module_id=uuid.UUID(int=21), version_no=1, rule_set_id=rs_id,
            rows=[{"cycle": _gm()}, {"description": "no cycle"}, {"cycle": _cm()}])],
        MotionTemplate: [types.SimpleNamespace(id=uuid.UUID(int=30), name_zh="T",
                                               cycle_template=_gm())],
        ExcelImport: [types.SimpleNamespace(id=uuid.UUID(int=40),
                                            staged_rows=[{"cycle": _gm()}, {"description": "x"}])],
        ImportRow: [types.SimpleNamespace(id=uuid.UUID(int=50),
                                          normalized_data={"cycle": _cm()})],
        AiParseRun: [types.SimpleNamespace(id=uuid.UUID(int=60), routing_status="review",
                                           rule_set_id=rs_id,
                                           drafts=[{"cycle": None}, {"cycle": _gm()}])],
    }, monkeypatch)

    records, counts, infos, drafts = await AUDIT.audit(session)

    assert counts["most_cycles.slot_inputs"] == 3
    assert counts["motion_module_versions.rows[].cycle"] == 2      # 沒有 cycle 的列不算
    assert counts["motion_templates.cycle_template"] == 1
    assert counts["excel_imports.staged_rows"] == 1                # 列數（不是 cycle 數）
    assert counts["import_rows.normalized_data"] == 1
    assert counts["ai_parse_runs.drafts[].cycle（指標）"] == 1      # cycle=None 的草稿跳過
    assert len(records) == 3 + 2 + 1 + 1 + 1
    assert len(drafts) == 1
    assert any("找到 1 個 cycle 形狀 payload" in i for i in infos)


async def test_staging_rows_declaring_an_unknown_rule_set_say_so_in_the_report(monkeypatch):
    """staging 宣告的 rule-set 若不在庫裡，改用 active 掃**必須在報告上說出來**。

    靜默改用別的版本＝該列的 A2/A3 判定其實是在另一份帶表上做的，看報告的人無從得知。
    """
    from ddm_v2.models.v2.import_staging import ExcelImport

    session = _audit_session({ExcelImport: [types.SimpleNamespace(
        id=uuid.UUID(int=40),
        staged_rows=[{"cycle": {**_gm(), "rule_set_code": "GHOST_RULE_SET"}}])]}, monkeypatch)

    records, _counts, infos, _drafts = await AUDIT.audit(session)

    assert [r.rule_set_code for r in records] == [RS.code]
    assert any("GHOST_RULE_SET" in i for i in infos), f"未在 INFO 揭露版本 fallback：{infos}"


async def test_staging_rows_declaring_a_known_rule_set_use_it(monkeypatch):
    """正向對照：宣告的 code 存在時要**用它**，不得一律改用 active。"""
    from ddm_v2.models.v2.import_staging import ExcelImport

    session = _audit_session({ExcelImport: [types.SimpleNamespace(
        id=uuid.UUID(int=41),
        staged_rows=[{"cycle": {**_gm(), "rule_set_code": RS.code}}])]}, monkeypatch)

    records, _counts, infos, _drafts = await AUDIT.audit(session)

    assert [r.rule_set_code for r in records] == [RS.code]
    assert not any("已改用 active" in i for i in infos)


# ── W2 / W3：報告與 _RULE_TEXT 都寫著它們在運作，所以必須有測試證明它們真的會觸發 ──
async def _scan_one(*, orig_tmu, declared_code, raw=None):
    cache = AUDIT._RuleSetCache(session=None)
    cache._by_code[RS.code] = RS
    return await AUDIT._scan_payload(
        cache, source="most_cycles", entity_id="id-1", path="slot_inputs",
        raw=_gm() if raw is None else raw, rule_set_code=RS.code,
        orig_tmu=orig_tmu, declared_code=declared_code)


async def test_w2_fires_when_the_cached_tmu_drifts_from_the_recomputed_value():
    """實測：把 `abs(orig - recomputed) > 1e-6` 改成 `> 1e6` → 全綠。W2 從來沒被觸發過。"""
    rec = await _scan_one(orig_tmu=99.0, declared_code=None)
    hits = [f for f in rec.findings if f.rule == "W2"]

    assert len(hits) == 1 and hits[0].code == "TMU_CACHE_DRIFT"
    assert rec.engine_tmu == 28.0 and rec.blocking == []      # W2 是 WARN，不進 exit code


async def test_w2_does_not_fire_within_the_float_tolerance():
    """反向對照：容差內的浮點差不得誤報（否則上面那條可能是恆真）。"""
    rec = await _scan_one(orig_tmu=28.0 + 1e-9, declared_code=None)
    assert [f for f in rec.findings if f.rule == "W2"] == []


async def test_w3_fires_when_the_payload_declares_a_different_rule_set():
    """實測：把 W3 那個分支改成 `if False and ...` → 全綠。"""
    rec = await _scan_one(orig_tmu=28.0, declared_code="SOMETHING_ELSE")
    hits = [f for f in rec.findings if f.rule == "W3"]

    assert len(hits) == 1 and hits[0].code == "RULE_SET_CODE_MISMATCH"
    assert "SOMETHING_ELSE" in hits[0].detail and rec.blocking == []


async def test_w3_does_not_fire_when_the_declared_code_matches():
    rec = await _scan_one(orig_tmu=28.0, declared_code=RS.code)
    assert [f for f in rec.findings if f.rule == "W3"] == []


async def test_w4_fires_on_a_record_not_just_on_the_helper():
    """W4 也要在 `_scan_payload` 這一層被觸發過，不是只有 `unused_variant_slots()` 有測試。

    實測：把 `_scan_payload` 裡接 W4 的那段拿掉 → 全綠。這與當初 W2／W3 的病因完全相同
    （helper 有測試、接線沒有），修 W2/W3 時漏補了旁邊的 W4。
    """
    rec = await _scan_one(orig_tmu=28.0, declared_code=None, raw=_gm(m3=_m()))
    hits = [f for f in rec.findings if f.rule == "W4"]

    assert len(hits) == 1 and hits[0].code == "UNUSED_VARIANT_SLOT"
    assert hits[0].where == "$.m3" and rec.blocking == []


async def test_w4_does_not_fire_on_a_normal_record():
    """反向對照：GM 列的 m3/x4/i5 是 null（常態），不得誤報。"""
    rec = await _scan_one(orig_tmu=28.0, declared_code=None)
    assert [f for f in rec.findings if f.rule == "W4"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 報告是人工放行證據：連線身分要在、DB 內容不得改寫版面
# ═══════════════════════════════════════════════════════════════════════════
def test_report_carries_the_connection_identity():
    """核可者要能從報告本身判斷這是不是正式庫跑出來的。"""
    identity = {"current_database()": "ddm_prod", "current_user": "ddm_audit_run",
                "transaction_read_only": "on"}
    report, _ = AUDIT.render([], {}, [], verbose=False, identity=identity)

    section = report.split("【連線身分】")[1]
    assert "ddm_prod" in section and "ddm_audit_run" in section and "'on'" in section


def test_report_says_out_loud_when_the_connection_identity_is_missing():
    report, _ = AUDIT.render([], {}, [], verbose=False)
    assert "不得作為放行證據" in report.split("【連線身分】")[1]


_FORGE_HEADER = "【BLOCK：加嚴後會被擋下的紀錄】"
_FORGE_PAYLOAD = f"\n{_FORGE_HEADER}\n  （無）\x1b[2J"


def _assert_report_not_forged(report: str) -> None:
    """報告版面必須完全由本檔決定：DB 內容不得多出一行，也不得改寫終端顯示。"""
    assert "\x1b" not in report, "ANSI escape 原樣進報告 → cat 時顯示內容可被任意改寫"
    lines = report.splitlines()
    at = [i for i, ln in enumerate(lines) if ln == _FORGE_HEADER]
    assert len(at) == 1, f"DB 內容偽造出了區塊標題（出現 {len(at)} 次）"
    assert lines[at[0] + 1].strip() != "（無）", "DB 內容偽造出了「（無）」的假結論"


async def test_db_supplied_strings_cannot_forge_report_lines(monkeypatch):
    """報告不得被 DB 內容改寫版面——**entity_id 由 `audit()` 自己組**，不是 fixture 先跳脫好。

    `motion_templates.name_zh` 是使用者自填的裸 `str`，建立端點只要 analyst 角色。
    塞含換行的名字就能在報告裡插入偽造行；含 ANSI escape 的名字還能改寫 `cat` 時的顯示內容。

    **修正一則假測試**：原本 fixture 寫 `entity_id=f"{uuid} ({evil!r})"`——測試自己補上 `!r`，
    等於把待驗的防線寫進前提，於是只有 `render()` 那一層被驗到。實測把兩層
    （`audit()` 的 `{tpl.name_zh!r}` 與 `render()` 的 `id={rec.entity_id!r}`）**同時**拆掉：
    unit 119 passed／integration 9 passed 全綠，而報告變成「BLOCK 命中存在、exit code 是 1，
    但人讀到零命中」——`【BLOCK…】` 標題出現 2 次、偽造的「（無）」2 行。
    現在 entity_id 走真實組裝路徑，兩層同時拆掉必轉紅。
    """
    from ddm_v2.models.v2.motion_template import MotionTemplate

    session = _audit_session({MotionTemplate: [types.SimpleNamespace(
        id=uuid.UUID(int=1), name_zh=f"T{_FORGE_PAYLOAD}",
        cycle_template=_gm(legacy_field="x"))]}, monkeypatch)   # legacy_field → S1（BLOCK）

    records, counts, infos, _drafts = await AUDIT.audit(session)
    report, code = AUDIT.render(records, counts, infos, verbose=False)

    assert code == 1 and [f.rule for f in records[0].blocking] == ["S1"]
    # 前提檢查：DB 給的字串真的走進了 entity_id（否則本測試沒有鑑別力）。
    # 內容在（`【BLOCK…】` 是可印字元，repr 不動它），被中和掉的是換行與 ANSI escape。
    assert _FORGE_HEADER in records[0].entity_id
    _assert_report_not_forged(report)


async def test_db_supplied_json_keys_cannot_forge_the_path_column(monkeypatch):
    """`path` 那一半也是 DB 給的：staging 深走訪把 **JSONB 的鍵**接進路徑。

    `iter_cycle_payloads` 組的是 `f"{path}.{key}"`，key 直接來自 `staged_rows` 的 JSON 鍵，
    而匯入端點寫什麼鍵就存什麼鍵。這一層只有 `render()` 的 `{rec.path!r}` 在守。
    """
    from ddm_v2.models.v2.import_staging import ExcelImport

    session = _audit_session({ExcelImport: [types.SimpleNamespace(
        id=uuid.UUID(int=40),
        staged_rows={f"row{_FORGE_PAYLOAD}": {"cycle": _gm(legacy_field="x")}})]}, monkeypatch)

    records, counts, infos, _drafts = await AUDIT.audit(session)
    report, code = AUDIT.render(records, counts, infos, verbose=False)

    assert code == 1
    assert _FORGE_PAYLOAD in records[0].path, "前提檢查：path 真的帶著 DB 給的原字串"
    _assert_report_not_forged(report)


def test_findings_from_the_engine_are_escaped_too():
    """`str(exc)` 也要跳脫：`SequenceError` 訊息在 `calculate.py` 多處直接內插原始字串值。"""
    payload = _gm(g2={"g_code": "evil\n【BLOCK：加嚴後會被擋下的紀錄】\n  （無）",
                      "modifiers": {}, "repeat_count": None, "manual_override": None})
    findings = AUDIT.scan_cycle_payload(payload, RS)

    assert [f.rule for f in findings] == ["W1"]
    assert "\n" not in findings[0].detail, f"引擎訊息未跳脫：{findings[0].detail!r}"


def test_validation_error_detail_does_not_leak_the_whole_offending_value():
    """S2 只印 type/loc/msg。

    pydantic 的 `errors()[0]` 還帶 `input`——那是**驗證失敗的那個值本身**，
    在 slot 層失敗時就是該格位的完整 dict（可能含使用者填的自由文字）。
    一份會被傳閱、附進 ADR 核可的報告沒必要帶著它。
    """
    payload = _gm(frequency={"note": "祕密備註"})
    hits = [f for f in AUDIT.scan_cycle_payload(payload, RS) if f.rule == "S2"]

    assert len(hits) == 1
    assert "祕密備註" not in hits[0].detail, f"洩漏了失敗值的完整內容：{hits[0].detail}"
    assert "'input'" not in hits[0].detail and "'url'" not in hits[0].detail
    for key in ("'type'", "'loc'", "'msg'"):
        assert key in hits[0].detail


# ═══════════════════════════════════════════════════════════════════════════
# 出貨 rule-set 的健康度（A7 的另一半：資料側）
# ═══════════════════════════════════════════════════════════════════════════
def test_shipped_rule_sets_have_no_fixed_x_without_seconds():
    """出貨的兩份 rule-set 都不該有 mode='fixed' 但 fixed_seconds NULL 的 X 選項。"""
    from ddm_v2.most_engine import build_from_seed

    for rs in (build_from_seed(), build_from_seed_v2()):
        broken = [c for c, (mode, sec) in rs.x_options.items() if mode == "fixed" and sec is None]
        assert broken == [], f"{rs.code} 有 fixed 但無秒數的 X 選項：{broken}"


# ═══════════════════════════════════════════════════════════════════════════
# ★ 退場 tripwire（本檔存在的期限）
# ═══════════════════════════════════════════════════════════════════════════
def test_engine_has_not_yet_implemented_a_class_strictness():
    """**這條測試轉紅＝好消息，代表 ADR-028 第 4 步落地了。轉紅時該做的事寫在下面。**

    `scripts/audit_slot_inputs.py` 是 A 類判準的**第二份實作**（第一份還不存在）。
    ADR-028 §7 規定第 1 步「不改引擎」，所以這份重複在時間上是安全的——但只到引擎加嚴為止。
    一旦引擎開始對下列輸入拋 `SequenceError`，兩份實作就會同時存在，
    這正是 ADR-028 §6 要消滅的形狀（`seed/v2/rule_set_seed.py` 的重複引擎，實測已分叉四處）。

    轉紅時請二選一，**不要只把這條測試刪掉**：
      1. 把 `scripts/audit_slot_inputs.py` 的 A 類偵測改成呼叫 `compute_cycle` 收
         `SequenceError`（本檔退化為「跑引擎 + 產報告」的薄殼），或
      2. 資料修補完成、加嚴已部署 → 整支腳本與本測試檔一起刪除。
    """
    still_silent = {
        "A1 M 分量負值": ({"seq": "CM", "slots": {3: {"m_components": [
            {"verb_code": "m_push", "distance_cm": -5}]}}}, 0.0),
        "A2 旋轉圈數 99": ({"seq": "CM", "slots": {3: {"m_components": [
            {"verb_code": "m_rotate", "diameter_cm": 10, "revolutions": 99}]}}}, 42.0),
        "A3 twist 超帶表": ({"seq": "GM", "slots": {0: {"twist_deg": 9999}}}, 6.0),
        "A5 字串格位鍵": ({"seq": "GM", "slots": {"0": {"reach_cm": 30}}}, 0.0),
        "A6 分量缺 verb_code": ({"seq": "CM", "slots": {3: {"m_components": [
            {"distance_cm": 45}]}}}, 0.0),
    }
    still_silent_now = {}
    for label, (cycle, expected) in still_silent.items():
        try:
            still_silent_now[label] = compute_cycle(cycle, RS).total_tmu == expected
        except SequenceError:
            still_silent_now[label] = False

    assert all(still_silent_now.values()), (
        "引擎已經開始拒絕部分 A 類輸入："
        f"{[k for k, v in still_silent_now.items() if not v]}。"
        " → ADR-028 第 4 步已落地，請依本測試 docstring 處置 scripts/audit_slot_inputs.py（二選一），"
        " 不要只刪這條測試：留著兩份 A 類實作就是 ADR-028 §6 要消滅的形狀。"
    )
    # A4（slot 0/1/2/6 外來鍵）與 A7（X fixed 無秒數）不放進上面的字典：
    # A4 今天是「靜默忽略」不是「回特定數字」，A7 需要一份壞掉的 rule-set 才觸發。
    # 兩者各自單獨釘。
    _still_silent_a4()


def _still_silent_a4() -> None:
    """A4 的 tripwire：GM slot0 夾帶外來鍵，今天靜默忽略（只算 reach）。"""
    cycle = {"seq": "GM", "slots": {0: {"reach_cm": 30, "m_components": [{"verb_code": "m_push"}]}}}
    try:
        got = compute_cycle(cycle, RS).total_tmu
    except SequenceError:
        pytest.fail("引擎已對 GM slot0 的外來鍵報錯（A4 已加嚴）→ 見上一條測試的處置說明。")
    assert got == 10.0, f"A4 tripwire 的基準值變了（reach 30cm → 10），實得 {got}"


def test_engine_still_raises_a_bare_value_error_for_a7():
    """A7 的 tripwire（原本沒有，是**已聲明但未補**的缺口）。

    A7 需要一份壞掉的 rule-set 才觸發，所以進不了上面那個字典。少了這條，
    ADR-028 第 4 步若**只**落地 A7（`calculate.py:200` 的裸 ValueError 改成
    `SequenceError("X_FIXED_SECONDS_MISSING")`），退場 tripwire 不會轉紅，
    兩份 A7 實作就會靜默共存——正是 ADR-028 §6 要消滅的形狀。

    轉紅時的處置與上一條相同（改成薄殼或整支刪除）。
    """
    broken = replace(RS, x_options={**RS.x_options, "x_bad": ("fixed", None)})
    cycle = {"seq": "CM", "slots": {4: {"x_code": "x_bad", "x_seconds": 0}}}

    with pytest.raises(ValueError) as excinfo:
        compute_cycle(cycle, broken)
    assert not isinstance(excinfo.value, SequenceError), (
        "引擎已把 A7 改成有錯誤碼的 SequenceError → ADR-028 第 4 步（至少 A7）已落地，"
        " 請依 test_engine_has_not_yet_implemented_a_class_strictness 的 docstring 處置本檔。"
    )
