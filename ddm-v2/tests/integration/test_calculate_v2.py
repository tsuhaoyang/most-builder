"""calculate API × V2 rule-set（ADR-014/impl-02）：黃金錨 + 新錯誤碼 422（檢查 detail.code）。

引擎層黃金/反例在 tests/unit/test_most_engine.py（36 條，勿動）；本檔補 **API 層**缺口：
- POST /api/v2/minimost/calculate 走 MINIMOST_FACTORY_V2（DB 載入路徑）的 GM=28 / CM=29（推45cm）。
- 新錯誤碼經 API 邊界的 422 合約：A_RETURN_COMPONENT / P_ADDON_CONFLICT / OVERRIDE_INVALID /
  REPEAT_INVALID / M_COMPANION_WITHOUT_VERB 以 {detail: {code, message}} 呈現；
  repeat 範圍驗證權威＝引擎 _repeat/_no_repeat（schema 只驗型別 int|None，單一驗證來源）。
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

V2 = "MINIMOST_FACTORY_V2"

GM_GOLD = {"seq": "GM", "rule_set_code": V2,
           "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
           "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}

CM_GOLD = {"seq": "CM", "rule_set_code": V2,
           "a0": {"reach_cm": 25}, "g2": {"g_code": "g_touch"},
           "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 45}]},
           "x4": {"x_code": "x_none"}, "i5": {"i_code": "i_none"}}


async def _calc(client, cycle):
    r = await client.post("/api/v2/minimost/calculate", json=cycle)
    if r.status_code in (404, 409):  # rule-set 未種/不完整 → 環境問題，skip 而非誤紅
        pytest.skip(f"rule-set {V2} 未就緒（status {r.status_code}）")
    return r


# ── 黃金錨（E8：V2 為權威；V1 黃金已在 test_v2_api.py 作回放）──
async def test_calculate_gm_golden_v2_28(client):
    r = await _calc(client, GM_GOLD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_tmu"] == 28
    assert body["rule_set_code"] == V2
    assert [b["letter"] for b in body["breakdown"]] == list("ABGABPA")


async def test_calculate_cm_golden_v2_29_push_45cm(client):
    """CM=29：推 45cm（=18 吋檔 → M16）。C1 單位語意定案後的權威輸入。"""
    r = await _calc(client, CM_GOLD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_tmu"] == 29
    assert body["breakdown"][3] == {"letter": "M", "tmu": 16}


async def test_calculate_cm_push_18cm_is_10_anti_regression(client):
    """單位回歸反例（C1）：推 18『cm』落 ≤25 檔 → M10，不是 16（防吋/cm 回歸）。"""
    cyc = dict(CM_GOLD, m3={"m_components": [{"verb_code": "m_push", "distance_cm": 18}]})
    r = await _calc(client, cyc)
    assert r.status_code == 200, r.text
    assert r.json()["breakdown"][3]["tmu"] == 10


# ── 新錯誤碼（impl-02 §2）：API 邊界 422 + detail.code ──
async def test_calculate_a_return_component_422(client):
    """E1：返回格（a6）帶 twist → 422 A_RETURN_COMPONENT。"""
    cyc = dict(GM_GOLD, a6={"reach_cm": 25, "twist_deg": 90})
    r = await _calc(client, cyc)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "A_RETURN_COMPONENT"


async def test_calculate_p_addon_conflict_422(client):
    """E3：插入⊥卡合 → 422 P_ADDON_CONFLICT。"""
    cyc = dict(GM_GOLD, p5={"p_base_code": "p_place_none", "p_addon_codes": ["a_insert", "a_snap"]})
    r = await _calc(client, cyc)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "P_ADDON_CONFLICT"


async def test_calculate_override_invalid_422(client):
    """E7：reason 空 / tmu 負 → 422 OVERRIDE_INVALID（兩種都要擋）。"""
    for bad in ({"tmu": 5, "reason": "   "}, {"tmu": -1, "reason": "實測"}):
        cyc = dict(GM_GOLD, g2={"g_code": "g_grasp", "manual_override": bad})
        r = await _calc(client, cyc)
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "OVERRIDE_INVALID"


async def test_calculate_repeat_invalid_422(client):
    """E4：repeat_count 超界（0 / -1 / 100）→ 422 REPEAT_INVALID（單一驗證來源＝引擎）。

    schema 已卸下 ge/le 範圍約束（只留 int|None 型別），範圍驗證權威在引擎 _repeat
    → API 統一回 {detail: {code: REPEAT_INVALID}}。非整數（如 1.5）屬型別違規，
    仍由 Pydantic 型別驗證擋（標準 422 list detail）。
    """
    for bad in (0, -1, 100):
        cyc = dict(GM_GOLD, g2={"g_code": "g_grasp", "repeat_count": bad})
        r = await _calc(client, cyc)
        assert r.status_code == 422, f"repeat_count={bad!r} 應 422，得 {r.status_code}"
        assert r.json()["detail"]["code"] == "REPEAT_INVALID"


async def test_calculate_repeat_on_a_slot_422(client):
    """E4：A/B 格禁 repeat——a0.repeat_count=2 經 API 可達引擎 _no_repeat → 422 REPEAT_INVALID。"""
    cyc = dict(GM_GOLD, a0={"reach_cm": 20, "repeat_count": 2})
    r = await _calc(client, cyc)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "REPEAT_INVALID"


async def test_calculate_x_seconds_required_422(client):
    """Fix-3（CL-01 §2 X）：x_press（mode=seconds）帶 x_seconds=0 或未填 → 422 X_SECONDS_REQUIRED。
    負值走 X_NEGATIVE（語意區分，impl-02 §2 決策；不合併至 X_SECONDS_REQUIRED）。
    """
    base_cm = dict(CM_GOLD)
    # x_seconds=0 → X_SECONDS_REQUIRED
    cyc_zero = dict(base_cm, x4={"x_code": "x_press", "x_seconds": 0})
    r = await _calc(client, cyc_zero)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "X_SECONDS_REQUIRED"

    # x_seconds 未填（預設 0）→ X_SECONDS_REQUIRED
    cyc_missing = dict(base_cm, x4={"x_code": "x_press"})
    r = await _calc(client, cyc_missing)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "X_SECONDS_REQUIRED"

    # x_seconds=-1 → X_NEGATIVE（語意區分：方向/符號錯誤 ≠ 必填未填）
    cyc_neg = dict(base_cm, x4={"x_code": "x_press", "x_seconds": -1})
    r = await _calc(client, cyc_neg)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "X_NEGATIVE"


async def test_calculate_override_applies_and_marks_star(client):
    """E7 正常路徑：覆寫值取代 + tech_line 標 *（G6→16：28-6+16=38）。"""
    cyc = dict(GM_GOLD, g2={"g_code": "g_grasp", "manual_override": {"tmu": 16, "reason": "IE 實測", "by": "IEC141289"}})
    r = await _calc(client, cyc)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_tmu"] == 38
    assert "G16*" in body["tech_line"]


# ── M 伴隨維度：`M_COMPANION_WITHOUT_VERB`（字典 M.controls.verb.required=true）──

async def test_calculate_m_companion_without_verb_422(client):
    """手度單獨成格 → 422 M_COMPANION_WITHOUT_VERB（訊息要點得出是哪個碼）。

    值域判斷需要 rule-set 才知道 `pricing_kind`，所以這條在引擎不在 schema
    （ADR-028 §2 決策 C-1／ADR-023 §3.5）——因此必須驗它真的走到 API 的 422 合約，
    而不是被 Pydantic 攔成一個形狀錯誤。
    """
    cyc = dict(CM_GOLD, m3={"m_components": [{"verb_code": "m_hand", "angle_deg": 90}]})
    r = await _calc(client, cyc)
    assert r.status_code == 422, r.text
    body = r.json()["detail"]
    assert body["code"] == "M_COMPANION_WITHOUT_VERB"
    assert "m_hand" in body["message"]


async def test_calculate_m_companion_with_verb_200_and_takes_max(client):
    """正向對照：真動詞＋手度合法，M 仍取 max（推45→16 vs 手度180→10 ⇒ 16，總計 29）。

    沒有這條，上一條就證明不了加嚴的是「缺動詞」而不是「用了手度」。
    """
    cyc = dict(CM_GOLD, m3={"m_components": [{"verb_code": "m_push", "distance_cm": 45},
                                             {"verb_code": "m_hand", "angle_deg": 180}]})
    r = await _calc(client, cyc)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["breakdown"][3] == {"letter": "M", "tmu": 16}
    assert body["total_tmu"] == 29


async def test_calculate_requires_authentication(client, monkeypatch):
    """RBAC：calculate 只要求登入（`current_user`，無角色門檻）——匿名 → 401。

    conftest 會設 `AUTH_DEV_USER`（dev fallback 身分），此處必須拿掉，
    否則匿名請求被解析成 dev 使用者而回 200。
    """
    import httpx

    from ddm_v2.main import create_app

    monkeypatch.delenv("AUTH_DEV_USER", raising=False)
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        r = await anon.post("/api/v2/minimost/calculate", json=CM_GOLD)
    assert r.status_code == 401, r.text
