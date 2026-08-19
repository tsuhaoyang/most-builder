"""ADR-032 Phase C 端點行為：`narrative_en` 的產生、持久化與讀取（含 RBAC 與邊界）。

分工（避免與既有檔重疊）：
- `tests/unit/test_narrative.py`：兩套樣板的組句規則本身（純函數、無 DB）。
- 本檔：**端點層**——存檔時中英同時產生、讀回兩語並列（D3.3 語言中立）、
  `motion_module_versions` 走「讀取時即時產生、不落盤」（D7.2）、RBAC 沿用既有守門。
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"   # dev_seed_v2 demo worksheet
OBJ = "66666666-6666-6666-6666-666666666666"  # dev_seed_v2 vocab「DIMM 內存」
V2 = "MINIMOST_FACTORY_V2"                    # active：Phase B/C 已灌 label_en/sentence_text_en
V1 = "MINIMOST_FACTORY_V1"                    # published 非 active：兩個 _en 欄位全 NULL

# 釘版對照的探針選項。挑它的唯一理由是 V2 的兩個英文欄**是不同的字**——
# `sentence_text_en='transfer'` vs `label_en='Hand change (transfer)'`；兩欄分開存的
# 理由就是 D7.3.1 的不同資料契約（句面＝乾淨動詞片語、標籤＝下拉辨義），測試必須分得出
# 引擎讀了哪一欄。V2 的 11 個 G 選項有 6 個兩欄只差首字母大小寫（g_grab／g_grasp／
# g_pat／g_regrasp／g_tap／g_touch），拿它們當探針時「`_sent()` 改成 label_en 優先」
# 這種讀錯欄的迴歸只靠一個大寫字母撐著（複審突變 W-b2 實測可穿透）。
# 附記：V1 的這個 code 是 `requires_modifier=True`，未給修飾 → 該格 TMU 記 0
# （`calculate.py:113`，不拋例外）。敘事不受影響，本檔也不斷言模組 TMU。
G_PROBE = "g_handchange"


def _gm_row(seq_no: int = 1, **extra) -> dict:
    """GM 黃金列（28 TMU）——與 test_worksheet_v2_engine 同一條，方便對照 TMU 不變。"""
    return {"id": str(uuid.uuid4()), "seq_no": seq_no, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": 1, "narrative": "ut narrative_en",
            "cycle": {"seq": "GM", "rule_set_code": V2,
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}, **extra}


async def _fresh_ws(client) -> str:
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    return (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]


async def test_save_generates_both_narratives_and_read_returns_both(client):
    """D7.5：新存檔的 cycle 同時產 `narrative_zh` 與 `narrative_en`；
    讀回**兩語並列**（D3.3：回應語言中立，由前端依 locale 挑欄，不做內容協商）。"""
    new = await _fresh_ws(client)
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()]})
    assert r.status_code == 200, r.text

    cyc = (await client.get(f"/api/v2/worksheets/{new}")).json()["rows"][0]["cycle"]
    assert cyc["narrative"], "narrative_zh 應存在（既有行為）"
    assert cyc["narrative_en"], "narrative_en 應同時產生（D7.5）"
    # 祈使句＋手別前綴（D7.4 案例 4），不是中文那種主謂結構
    assert cyc["narrative_en"].startswith("RH: ")
    # 語言只影響字串（I1）：黃金列 TMU 不因英文化而變
    assert cyc["total_tmu"] == 28


async def test_english_narrative_contains_no_chinese_when_material_is_seeded(client):
    """素材齊全（`dev_seed_i18n_labels.py` 跑過）時，英文敘事不得殘留中文。

    素材未齊時本測試 skip 而不是放寬斷言——ADR-032 D10 明說「沒有
    `sentence_text_en` 的素材，英文敘事只能回退中文」，那是**設計內的降級**，
    不該被當成迴歸；但也不能因此永遠不檢查齊全時的行為。
    """
    full = (await client.get(f"/api/v2/rule-sets/{V2}/full")).json()
    if not any(r.get("sentence_text_en") for r in full["g"]):
        pytest.skip("sentence_text_en 未灌值（先跑 dev_seed_i18n_labels.py）")

    new = await _fresh_ws(client)
    await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()]})
    en = (await client.get(f"/api/v2/worksheets/{new}")).json()["rows"][0]["cycle"]["narrative_en"]
    assert not any("一" <= ch <= "鿿" for ch in en), en


async def test_clone_worksheet_carries_narrative_en(client):
    """clone 是逐欄複製而非重算——`narrative_en` 必須跟著搬，否則 clone 出來的
    表英文欄整片空白（`narrative_zh` 早有此行為，兩者必須對稱）。"""
    new = await _fresh_ws(client)
    await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()]})
    src = (await client.get(f"/api/v2/worksheets/{new}")).json()["rows"][0]["cycle"]

    cloned = (await client.post(f"/api/v2/worksheets/{new}/clone")).json()["new_worksheet_id"]
    dst = (await client.get(f"/api/v2/worksheets/{cloned}")).json()["rows"][0]["cycle"]
    assert dst["narrative_en"] == src["narrative_en"]
    assert dst["narrative"] == src["narrative"]


async def test_generating_narrative_en_still_requires_analyst(client):
    """RBAC 沿用既有守門——產生 `narrative_en` 的唯一寫入路徑是 `PUT /worksheets/{id}`，
    它本來就 `require_role("analyst")`；Phase C 不另開端點、不放寬權限。"""
    new = await _fresh_ws(client)
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [_gm_row()]},
                         headers={"X-Username": "ZZZ_NARR_EN_VIEWER"})
    assert r.status_code == 403, r.text


# ── D7.2：motion_module_versions 讀取時即時產生，不落盤 ──────────────

async def _rule_set_id(client, code: str) -> str | None:
    """由 rule-set **code** 解析 id——刻意不撈清單「第一筆」。

    `list_rule_sets` 是 `ORDER BY created_at`，而 V1／V2 是同一支 seed 在同一個時間戳
    寫進去的（實測兩列 `created_at` 完全相同），「第一筆」既不是 active、跨環境也不穩定。
    本檔要驗的正是「釘哪一版就讀哪一版」，版本選錯會讓整組英文斷言失去方向性
    （B-1：釘到 V1 時整段輸出是中文，`startswith("RH: ")` 照樣通過）。
    「不要撈第一列／任一筆，自己建或自己指名」也是 `docs/CI_GATES.md` 硬性規則 7 第一則。
    """
    rs = await client.get("/api/v2/rule-sets")
    if rs.status_code != 200:
        return None
    return next((r["id"] for r in rs.json() if r["code"] == code), None)


async def _published_module(client, rs_code: str = V2) -> tuple[str, str] | None:
    """發一個釘住 `rs_code` 的模組版本；該 rule-set 不存在時回 None（由呼叫端 skip）。

    cycle 內**不寫死** `rule_set_code`：由 `resolve_cycle_rule_set` 依實際發布的版本回填，
    否則釘 V1 的快照會自稱 V2（ADR-023 §3.4 的回放權威原始輸入就對不上了）。
    """
    rs_id = await _rule_set_id(client, rs_code)
    if rs_id is None:
        return None
    sfx = uuid.uuid4().hex[:6]
    # `UT-` 前綴不是裝飾：`scripts/cleanup_test_data.py` 以 `name_zh LIKE 'UT-%'` 清殘留，
    # 新簽名要嘛沿用既有 pattern、要嘛同步進該腳本（CI_GATES 硬性規則 3b）。這裡選前者。
    m = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-PhaseC-{sfx}", "scope": "global", "category": "action"})
    assert m.status_code == 201, m.text
    mid = m.json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rs_id, "rows": [{
            "hand": "RH", "frequency": 1, "vocab_refs": {},
            "cycle": {"seq": "GM",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": G_PROBE},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
        }]})
    assert pub.status_code == 201, pub.text
    return mid, rs_id


async def _g_terms(client, code: str, opt_code: str) -> tuple[str | None, str | None, str | None]:
    """某版本某 G 選項的（中文句面, 英文句面, 英文標籤）。

    中文那項照 `narrative._sent()` 的回退鏈（`sentence_text_zh or label_zh`）；
    英文兩欄各自原樣回傳——本檔要用它們的**差異**去判斷引擎讀了哪一欄。
    """
    full = await client.get(f"/api/v2/rule-sets/{code}/full")
    if full.status_code != 200:
        return None, None, None
    row = next((r for r in full.json()["g"] if r["code"] == opt_code), None)
    if row is None:
        return None, None, None
    return (row["sentence_text_zh"] or row["label_zh"]), row["sentence_text_en"], row["label_en"]


def _has(haystack: str, needle: str) -> bool:
    """大小寫不敏感的包含判斷。

    這裡要守的是**引擎讀了哪一欄**（內容），不是大小寫。綁大小寫的話，「讀錯欄」的
    迴歸只要順手 `lower()` 一下就穿透——複審突變 W-b2（`_sent()` 改 `label_en` 優先
    ＋抹平大小寫）實測可以全綠通過。判別力改由 `G_PROBE` 兩欄的**用詞差異**提供。
    """
    return needle.casefold() in haystack.casefold()


async def _module_narrative_en(client, mid: str) -> str:
    return (await client.get(
        f"/api/v2/motion-modules/{mid}")).json()["current_version_detail"]["rows"][0]["narrative_en"]


async def test_module_version_narrative_en_reads_the_pinned_rule_sets_material(client):
    """I4（違反即否決）：英文敘事讀的是**該版本自己 pin 的** rule-set，不是現行 active 字典。

    兩版對照才有方向性。V2（active）灌過 `label_en`／`sentence_text_en`；V1（published
    非 active）兩欄全 NULL，英文敘事只能回退中文（D10 的設計內降級）。所以：

    - 釘 V2 → 出現 V2 的英文句面（實測 "grasp"），中文句面不得出現；
    - 釘 V1 → 出現 V1 的中文句面（實測 "抓握"），V2 的英文句面不得出現。

    這一條同時釘死三件事：(a) 釘版回放真的生效——若讀取路徑改用
    `load_options_from_db(session, "MINIMOST_FACTORY_V2")`，V1 那版也會吐英文而紅；
    (b) 英文素材真的被讀進去，不是「回退中文也算過」；(c) 版本由 code 指名而非撈第一筆。

    詞面取自 `/full`（不寫死字串）：IE 改動翻譯用詞時本測試不該假紅，要守的是
    「哪一版的素材」而不是「哪一個字」。
    """
    v2_mod = await _published_module(client, V2)
    v1_mod = await _published_module(client, V1)
    if v2_mod is None or v1_mod is None:
        pytest.skip("V1/V2 未同時種（先跑 dev_seed_v2.py），無法做釘版對照")
    zh_term, en_term, en_label = await _g_terms(client, V2, G_PROBE)
    if not en_term:
        pytest.skip("V2 的 sentence_text_en 未灌值（先跑 dev_seed_i18n_labels.py）")
    v1_zh_term, v1_en_term, _ = await _g_terms(client, V1, G_PROBE)
    assert not v1_en_term, "前提變了：V1 也有英文素材，這條對照就失去方向性"
    assert en_label and en_label != en_term, (
        f"探針失效：{G_PROBE} 的 label_en 與 sentence_text_en 必須是不同的字，"
        f"否則下面分不出引擎讀了哪一欄（見 G_PROBE 註解）：{en_label!r} / {en_term!r}")

    en_v2 = await _module_narrative_en(client, v2_mod[0])
    en_v1 = await _module_narrative_en(client, v1_mod[0])

    assert _has(en_v2, en_term) and zh_term not in en_v2, f"釘 V2 卻沒讀到 V2 的英文素材：{en_v2}"
    # **讀對欄位**，不只是「讀到英文」：句面與標籤是不同欄、不同契約（D7.3.1），
    # 而句面往往是標籤的子字串（"transfer" ⊂ "Hand change (transfer)"），只斷言
    # 「句面出現」分不出兩者。這一條讓「`_sent()` 改成 label_en 優先」直接紅。
    assert not _has(en_v2, en_label), (
        f"英文敘事用了 label_en 而不是 sentence_text_en（D7.3.1 兩欄契約不同）：{en_v2}")
    assert v1_zh_term in en_v1, f"釘 V1 應回退 V1 的中文素材（D10）：{en_v1}"
    assert not _has(en_v1, en_term), (
        f"釘 V1 的版本吐出了 active(V2) 的英文素材——以現行字典重新詮釋歷史版本，"
        f"違反 ADR-032 I4：{en_v1}")


async def test_module_version_rows_expose_narrative_en_without_persisting_it(client, db_session):
    """D7.2：該表是**不可變版本快照**，為舊快照回填等於改寫不可變列。
    因此 `narrative_en` 只在讀取時以該版本 pin 的 `rule_set_id` 產生，
    **不得**出現在落盤的 rows JSONB 裡。"""
    from sqlalchemy import text

    made = await _published_module(client)
    if made is None:
        pytest.skip("DB 無 rule_set，略過")
    mid, _ = made

    ver = (await client.get(f"/api/v2/motion-modules/{mid}")).json()["current_version_detail"]
    row = ver["rows"][0]
    assert row["narrative_zh"], "中文敘事仍是落盤欄（既有行為）"
    assert row["narrative_en"], "英文敘事應於讀取時即時產生"
    assert row["narrative_en"].startswith("RH: ")

    # 落盤的 JSONB 不得含 narrative_en——讀取路徑改的是複本，不是快照本身
    stored = (await db_session.execute(text(
        "SELECT rows FROM motion_module_versions WHERE module_id = :mid ORDER BY version_no DESC LIMIT 1"
    ), {"mid": mid})).scalar_one()
    assert "narrative_en" not in stored[0], stored[0]
    assert stored[0].get("narrative_zh"), "中文敘事仍應落盤"


async def test_module_version_list_endpoint_also_carries_narrative_en(client):
    """版本清單端點與 detail 端點走同一條產生路徑（不是只有 detail 補了英文）。"""
    made = await _published_module(client)
    if made is None:
        pytest.skip("DB 無 rule_set，略過")
    mid, _ = made

    versions = (await client.get(f"/api/v2/motion-modules/{mid}/versions")).json()
    assert versions, versions
    assert versions[0]["rows"][0]["narrative_en"]
