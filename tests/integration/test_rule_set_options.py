"""選項級 CRUD ＋不可變 gate（ADR-023 D2）。

⚠️ 測試紀律（沿 test_rule_set.py）：
- 任何寫入一律打 `draft_rs` fixture clone 出來的拋棄式版本；**絕不**對 V1/V2 動手。
- 針對 V1/V2 的測試只驗「被 409 擋下」，並額外斷言 DB 未變（gate 若只擋回應不擋落盤＝失效）。
- skip 條件一律用**資料前置條件**（rule-set 有沒有種），不得用被測程式的回應碼當 skip 依據。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration

CERTIFIED = "MINIMOST_FACTORY_V2"  # provenance=certified_import（ADR-014 值權威）

# (param, section 查詢字串, 形狀)——涵蓋全部 12 張子表
OPTION_SECTIONS = [
    ("B", None), ("G", None), ("X", None), ("I", None),
    ("P", "base"), ("P", "addon"), ("M", "verb"),
]
BAND_SECTIONS = [
    ("A", "reach"), ("A", "twist"), ("A", "foot"),
    ("M", "ladder"), ("M", "foot"), ("M", "rotation"), ("M", "hand"),
]

# 每個選項型區塊的最小合法 create payload（欄位＝各子表實際 column）
NEW_OPTION = {
    ("B", None): {"code": "ut_b", "label_zh": "測試身體動作", "index_value": 7},
    ("G", None): {"code": "ut_g", "label_zh": "測試取得", "base_tmu": 5},
    ("X", None): {"code": "ut_x", "label_zh": "測試處理", "mode": "seconds"},
    ("I", None): {"code": "ut_i", "label_zh": "測試對齊", "index_value": 4},
    ("P", "base"): {"code": "ut_pb", "label_zh": "測試放置", "base_tmu": 9},
    ("P", "addon"): {"code": "ut_pa", "label_zh": "測試附加", "delta_tmu": 3},
    ("M", "verb"): {"code": "ut_mv", "label_zh": "測試動詞", "pricing_kind": "fixed", "fixed_tmu": 12},
}

# 每個帶型區塊的最小合法整組替換 payload
NEW_BANDS = {
    ("A", "reach"): [{"max_value": 5.0, "index_value": 1}, {"max_value": None, "index_value": 9}],
    ("A", "twist"): [{"max_value": 30.0, "index_value": 0}, {"max_value": 90.0, "index_value": 3}],
    ("A", "foot"): [{"max_value": 20.0, "index_value": 6}, {"max_value": None, "index_value": 30}],
    ("M", "ladder"): [{"max_cm": 10.0, "tmu": 6}, {"max_cm": None, "tmu": 20}],
    ("M", "foot"): [{"max_cm": 25.0, "tmu": 10}, {"max_cm": None, "tmu": 40}],
    ("M", "rotation"): [
        {"max_diameter_cm": 5.0, "revolutions": 1, "tmu": 6},
        {"max_diameter_cm": None, "revolutions": 1, "tmu": 12},
        {"max_diameter_cm": 5.0, "revolutions": 2, "tmu": 10},
    ],
    ("M", "hand"): [{"max_deg": 90.0, "tmu": 6}, {"max_deg": None, "tmu": 12}],
}


def _q(section: str | None, param: str) -> dict:
    """A 的次級選擇在規格中叫 component，其餘叫 section。"""
    if section is None:
        return {}
    return {"component" if param == "A" else "section": section}


async def _seeded(db_session) -> bool:
    """資料前置條件：認證版本是否已種（不看被測端點的回應）。"""
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet

    return (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == CERTIFIED))).first() is not None


@pytest_asyncio.fixture
async def draft_rs(db_session) -> str:
    """clone 出拋棄式 draft（provenance=cloned）供寫入測試；測後隨外層 transaction rollback。"""
    from ddm_v2.services.v2 import rule_set_service as svc

    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    code = f"UT_OPT_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, CERTIFIED, code, "選項級 CRUD 測試草稿")
    await db_session.commit()
    return code


async def _count_rows(db_session, model) -> int:
    from sqlalchemy import func, select

    return int((await db_session.execute(select(func.count()).select_from(model))).scalar_one())


# ══════════════════════════════════════════════════════════════════
# D2-3 不可變 gate
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(("param", "section"), OPTION_SECTIONS)
async def test_certified_import_option_write_returns_409(client, db_session, param, section):
    """ADR-023 §3.3 規則 3：certified_import 版本的任何選項級寫入一律 409（每參數各測一次）。

    逐參數參數化＝確保 gate 沒有漏掛在某一組端點上（單一 smoke 測不出漏掛）。
    POST/PATCH/DELETE/duplicate 四個寫入動作全打。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    q = _q(section, param)
    base = f"/api/v2/rule-sets/{CERTIFIED}/params/{param}/options"

    r = await client.post(base, params=q, json=NEW_OPTION[(param, section)])
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "CERTIFIED_IMMUTABLE", r.text

    # 讀一筆真實存在的 code 來打 PATCH/DELETE/duplicate——若 gate 漏掛，這些會真的改到值權威。
    lst = await client.get(base, params=q)
    assert lst.status_code == 200, lst.text
    victim = lst.json()["items"][0]["code"]
    for call in (
        client.patch(f"{base}/{victim}", params=q, json={"label_zh": "GATE 應攔下"}),
        client.delete(f"{base}/{victim}", params=q),
        client.post(f"{base}/{victim}/duplicate", params=q),
    ):
        resp = await call
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "CERTIFIED_IMMUTABLE", resp.text

    after = await client.get(base, params=q)
    assert after.json()["items"] == lst.json()["items"], "409 後值權威不得有任何變動"


@pytest.mark.parametrize(("param", "section"), BAND_SECTIONS)
async def test_certified_import_band_write_returns_409(client, db_session, param, section):
    """帶型區塊（A 三分量 ＋ M 四張帶表）的整組替換同樣被 gate 擋下。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    q = _q(section, param)
    url = f"/api/v2/rule-sets/{CERTIFIED}/params/{param}/bands"
    before = await client.get(f"/api/v2/rule-sets/{CERTIFIED}/params/{param}/options", params=q)
    assert before.status_code == 200, before.text

    r = await client.put(url, params=q, json={"items": NEW_BANDS[(param, section)]})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "CERTIFIED_IMMUTABLE", r.text

    after = await client.get(f"/api/v2/rule-sets/{CERTIFIED}/params/{param}/options", params=q)
    assert after.json()["items"] == before.json()["items"], "409 後帶界不得有任何變動"


async def test_certified_import_put_full_returns_409(client, db_session):
    """ADR-023 §3.3 規則 3 明文含 `PUT /full`——整份替換也不得繞過 gate。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    full = (await client.get(f"/api/v2/rule-sets/{CERTIFIED}/full")).json()
    r = await client.put(f"/api/v2/rule-sets/{CERTIFIED}/full", json=full)
    assert r.status_code == 409, r.text
    assert "認證匯入" in r.json()["error"]["message"]


async def test_published_non_certified_write_returns_409(client, db_session, draft_rs):
    """published 但**非**認證的版本 → 409 RULE_SET_FROZEN（訊息與認證版本不同，指引使用者建草稿）。

    先 publish 拋棄式 draft，讓 409 一定來自 status 凍結而非 provenance。
    """
    from ddm_v2.services.v2 import rule_set_service as svc

    await svc.publish(db_session, draft_rs, actor="UT_D2")
    await db_session.commit()

    r = await client.post(
        f"/api/v2/rule-sets/{draft_rs}/params/B/options", json=NEW_OPTION[("B", None)]
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "RULE_SET_FROZEN", r.text
    assert "請先建立草稿" in r.json()["error"]["message"]


async def test_option_write_requires_analyst(client, db_session, draft_rs):
    """RBAC：寫入需 analyst 以上；無角色使用者（＝JIT viewer，level 0）→ 403，且不得留下副作用。"""
    viewer = "GAPTEST_VIEWER_OPT_001"
    # roles=[] 即 rbac-spec 的 viewer（"viewer" 不是可指派角色，見 admin_users 的合法值檢查）
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": viewer, "display_name": "Gap Test Viewer Option",
        "roles": [], "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    h = {"X-Username": viewer}
    url = f"/api/v2/rule-sets/{draft_rs}/params/B/options"

    before = (await client.get(url)).json()["items"]
    r = await client.post(url, json=NEW_OPTION[("B", None)], headers=h)
    assert r.status_code == 403, r.text
    assert (await client.get(url)).json()["items"] == before, "403 後不得留下寫入副作用"


# ══════════════════════════════════════════════════════════════════
# D2-2 section 分派
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(("param", "allowed"), [
    ("P", ["base", "addon"]),
    ("M", ["verb", "ladder", "foot", "rotation", "hand"]),
    ("A", ["reach", "twist", "foot"]),
])
async def test_section_missing_returns_400_with_allowed_values(client, db_session, param, allowed):
    """section/component 缺省 → 400 並列出合法值；**不得靜默選一個**（ADR-023 D2）。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    r = await client.get(f"/api/v2/rule-sets/{CERTIFIED}/params/{param}/options")
    assert r.status_code == 400, r.text
    for value in allowed:
        assert value in r.json()["error"]["message"], r.text
    # A 的查詢參數名是 component（規格用語），P/M 是 section
    assert ("component" if param == "A" else "section") in r.json()["error"]["message"]


async def test_band_section_rejects_single_option_crud(client, draft_rs):
    """帶型區塊沒有「選項代碼」概念 → 單筆 CRUD 一律 400，引導改用整組替換（ADR-023 §2）。"""
    r = await client.post(
        f"/api/v2/rule-sets/{draft_rs}/params/M/options",
        params={"section": "ladder"}, json={"max_cm": 10.0, "tmu": 6},
    )
    assert r.status_code == 400, r.text
    assert "整組替換" in r.json()["error"]["message"]


# ══════════════════════════════════════════════════════════════════
# D2-2 draft 全流程
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(("param", "section"), OPTION_SECTIONS)
async def test_draft_option_crud_lifecycle(client, draft_rs, param, section):
    """clone 出的 draft 可完成 增 → 改 → 複製 → 停用 → 刪 全流程（每個選項型區塊各一輪）。"""
    q = _q(section, param)
    base = f"/api/v2/rule-sets/{draft_rs}/params/{param}/options"
    payload = NEW_OPTION[(param, section)]
    code = payload["code"]

    created = await client.post(base, params=q, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["code"] == code
    assert created.json()["is_active"] is True

    # 重複 code → 409
    dup = await client.post(base, params=q, json=payload)
    assert dup.status_code == 409, dup.text

    # 改：部分更新，未給的欄位沿用現值
    patched = await client.patch(f"{base}/{code}", params=q, json={"label_zh": "改過的標籤"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["label_zh"] == "改過的標籤"
    for key, value in payload.items():
        if key != "label_zh":
            assert patched.json()[key] == value, f"PATCH 不得動到未給的欄位 {key}"

    # 複製
    copied = await client.post(f"{base}/{code}/duplicate", params=q)
    assert copied.status_code == 200, copied.text
    assert copied.json()["code"] == f"{code}_copy"

    # 停用（is_active=false）→ 仍在清單內，但 active_only 看不到
    off = await client.patch(f"{base}/{code}", params=q, json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False, off.text
    all_codes = [i["code"] for i in (await client.get(base, params=q)).json()["items"]]
    active_codes = [i["code"] for i in (await client.get(base, params=q | {"active_only": "true"})).json()["items"]]
    assert code in all_codes, "編輯畫面必須看得到已停用的選項"
    assert code not in active_codes and f"{code}_copy" in active_codes

    # 刪（硬刪）
    gone = await client.delete(f"{base}/{code}", params=q)
    assert gone.status_code == 200, gone.text
    assert code not in [i["code"] for i in (await client.get(base, params=q)).json()["items"]]
    assert (await client.delete(f"{base}/{code}", params=q)).status_code == 404


async def test_duplicate_code_uniqueness(client, draft_rs):
    """連續 duplicate 兩次 → `_copy`、`_copy_2`（不得撞 UNIQUE(rule_set_id, code)）。"""
    base = f"/api/v2/rule-sets/{draft_rs}/params/G/options"
    src = (await client.get(base)).json()["items"][0]["code"]

    first = await client.post(f"{base}/{src}/duplicate")
    assert first.status_code == 200, first.text
    assert first.json()["code"] == f"{src}_copy"

    second = await client.post(f"{base}/{src}/duplicate")
    assert second.status_code == 200, second.text
    assert second.json()["code"] == f"{src}_copy_2"

    codes = [i["code"] for i in (await client.get(base)).json()["items"]]
    assert len(codes) == len(set(codes)), "duplicate 產生的 code 必須唯一"


async def test_p_addon_max_select_must_be_uniform(client, draft_rs):
    """引擎 `p_addon_max = min(max_select)`（providers.py）→ 該值是全表語意，不得逐列不同。

    寫入層若放行不一致的 max_select，改一列就會靜默壓低整體上限（使用者無從察覺）。
    """
    base = f"/api/v2/rule-sets/{draft_rs}/params/P/options"
    q = {"section": "addon"}
    existing = (await client.get(base, params=q)).json()["items"]
    assert {i["max_select"] for i in existing} == {2}, "V2 認證資料的 p_addon_max 應為 2"

    bad = await client.post(base, params=q, json={**NEW_OPTION[("P", "addon")], "max_select": 1})
    assert bad.status_code == 400, bad.text
    assert "max_select" in bad.json()["error"]["message"]

    ok = await client.post(base, params=q, json={**NEW_OPTION[("P", "addon")], "max_select": 2})
    assert ok.status_code == 200, ok.text


# ══════════════════════════════════════════════════════════════════
# D2-2 A 帶界驗證
# ══════════════════════════════════════════════════════════════════

async def test_a_bands_replace_happy_path(client, draft_rs):
    """整組替換 A.reach → 200，且只影響該 component（twist/foot 不動）。"""
    url = f"/api/v2/rule-sets/{draft_rs}/params/A/bands"
    twist_before = (await client.get(
        f"/api/v2/rule-sets/{draft_rs}/params/A/options", params={"component": "twist"})).json()["items"]

    items = [
        {"max_value": 5.0, "index_value": 1},
        {"max_value": 20.0, "index_value": 6},
        {"max_value": None, "index_value": 24},   # 末帶 open-ended：允許
    ]
    r = await client.put(url, params={"component": "reach"}, json={"items": items})
    assert r.status_code == 200, r.text
    got = r.json()["items"]
    assert [(i["max_value"], i["index_value"]) for i in got] == [(5.0, 1), (20.0, 6), (None, 24)]
    assert [i["sort_order"] for i in got] == [0, 1, 2], "整組替換須重排 sort_order"

    twist_after = (await client.get(
        f"/api/v2/rule-sets/{draft_rs}/params/A/options", params={"component": "twist"})).json()["items"]
    assert twist_after == twist_before, "替換 reach 不得動到其他分量"


async def test_a_bands_non_ascending_returns_400(client, draft_rs):
    """帶界未遞增（不連續）→ 400。"""
    r = await client.put(
        f"/api/v2/rule-sets/{draft_rs}/params/A/bands", params={"component": "reach"},
        json={"items": [{"max_value": 20.0, "index_value": 6}, {"max_value": 5.0, "index_value": 1}]},
    )
    assert r.status_code == 400, r.text
    assert "未遞增" in r.json()["error"]["message"]


async def test_a_bands_overlap_returns_400(client, draft_rs):
    """帶界重疊（上界相同）→ 400。"""
    r = await client.put(
        f"/api/v2/rule-sets/{draft_rs}/params/A/bands", params={"component": "reach"},
        json={"items": [{"max_value": 5.0, "index_value": 1}, {"max_value": 5.0, "index_value": 3}]},
    )
    assert r.status_code == 400, r.text
    assert "重疊" in r.json()["error"]["message"]


async def test_a_bands_open_ended_must_be_last(client, draft_rs):
    """open-ended（max_value=null）不在末位 → 400（否則其後的帶永遠取不到）。"""
    r = await client.put(
        f"/api/v2/rule-sets/{draft_rs}/params/A/bands", params={"component": "reach"},
        json={"items": [{"max_value": None, "index_value": 24}, {"max_value": 5.0, "index_value": 1}]},
    )
    assert r.status_code == 400, r.text
    assert "最後一帶" in r.json()["error"]["message"]


async def test_m_rotation_bands_validated_per_revolution(client, draft_rs):
    """rotation 依 revolutions 分組各自成序：組內未遞增才算錯，跨組回頭是合法的。"""
    url = f"/api/v2/rule-sets/{draft_rs}/params/M/bands"
    q = {"section": "rotation"}

    ok = await client.put(url, params=q, json={"items": [
        {"max_diameter_cm": 5.0, "revolutions": 1, "tmu": 6},
        {"max_diameter_cm": None, "revolutions": 1, "tmu": 12},
        {"max_diameter_cm": 5.0, "revolutions": 2, "tmu": 10},   # 回到 5.0 但屬 rev=2 → 合法
    ]})
    assert ok.status_code == 200, ok.text

    bad = await client.put(url, params=q, json={"items": [
        {"max_diameter_cm": 10.0, "revolutions": 1, "tmu": 6},
        {"max_diameter_cm": 5.0, "revolutions": 1, "tmu": 12},   # 同組回頭 → 400
    ]})
    assert bad.status_code == 400, bad.text
    assert "revolutions=1" in bad.json()["error"]["message"]


# ══════════════════════════════════════════════════════════════════
# D2-4 publish 前的啟用完整性
# ══════════════════════════════════════════════════════════════════

async def test_publish_blocked_when_all_options_of_a_param_inactive(client, draft_rs):
    """某參數的選項全部 is_active=false → publish 409。

    引擎的 `validate_complete()` 看不到 is_active（§3.4：引擎不看治理狀態），
    所以這道檢查必須在治理層（`rule_set_service.validate_active_options`）補上；
    否則會發布出「表有列但 UI 一個都選不到」的版本。
    """
    base = f"/api/v2/rule-sets/{draft_rs}/params/B/options"
    codes = [i["code"] for i in (await client.get(base)).json()["items"]]
    assert codes, "clone 出的 draft 應帶有 B 選項"

    ok = await client.post(f"/api/v2/rule-sets/{draft_rs}/publish")
    assert ok.status_code == 200, f"停用前應可發布：{ok.text}"

    # 回到 draft 不可能（published 是單向），故用另一個 clone 驗證停用後被擋
    fresh = f"UT_OPT_{uuid.uuid4().hex[:8]}"
    cl = await client.post(f"/api/v2/rule-sets/{draft_rs}/clone-draft", json={"new_code": fresh})
    assert cl.status_code == 200, cl.text

    fresh_base = f"/api/v2/rule-sets/{fresh}/params/B/options"
    for code in [i["code"] for i in (await client.get(fresh_base)).json()["items"]]:
        off = await client.patch(f"{fresh_base}/{code}", json={"is_active": False})
        assert off.status_code == 200, off.text

    blocked = await client.post(f"/api/v2/rule-sets/{fresh}/publish")
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "RULE_SET_INCOMPLETE", blocked.text
    assert "b_options" in blocked.json()["error"]["message"], blocked.text


async def test_clone_draft_preserves_m_foot_bands(client, db_session, draft_rs):
    """clone 必須完整帶走 M 腳步獨立帶（V2 起 foot 與 ladder 分離）。

    D2 之前 `load_full`/`_insert_children` 漏了 rule_m_foot_bands → clone 出來的草稿
    會退回用 ladder 算腳步（`RuleSetData.foot_tmu` 的 V1 回退路徑），編輯 M.foot 形同無效。
    """
    src = (await client.get(
        f"/api/v2/rule-sets/{CERTIFIED}/params/M/options", params={"section": "foot"})).json()["items"]
    assert src, "V2 認證資料應有 M 腳步帶"
    cloned = (await client.get(
        f"/api/v2/rule-sets/{draft_rs}/params/M/options", params={"section": "foot"})).json()["items"]
    assert [(i["max_cm"], i["tmu"]) for i in cloned] == [(i["max_cm"], i["tmu"]) for i in src]


# ══════════════════════════════════════════════════════════════════
# D2 code-review 修正輪
# ══════════════════════════════════════════════════════════════════

# 12 張子表 → 逐欄比對用的 (model, 忽略欄位) 清單。
# 忽略 id/rule_set_id 是必然不同的主鍵與外鍵；其餘**每一欄都必須相等**。
_CHILD_MODELS = [
    "RuleABand", "RuleBOption", "RuleGAction", "RulePBase", "RulePAddon",
    "RuleMLadderBand", "RuleMFootBand", "RuleMVerb", "RuleMRotationBand",
    "RuleMHandBand", "RuleXOption", "RuleIOption",
]
_IGNORED_COLS = {"id", "rule_set_id"}


async def test_clone_preserves_every_column_of_every_child_table(client, db_session, draft_rs):
    """HIGH-1：clone 必須逐欄完整搬家——12 張子表、每一欄、每一列。

    §3.3 規則 2 強制 clone-on-write：IE 想改 V2 只能先 clone。若 clone 漏搬欄位，
    使用者拿到的「同一份字典」其實已經變了值，且**沒有任何錯誤訊息**。
    實際漏過的欄位：`sentence_text_zh`（7 張表，V2 多數列有值）→ `narrative.py` 回退
    label_zh 產生不同 METHOD 句；`display_rule`/`max_select`（p_addons）→ 敘事三態退回
    show_self、addon 上限靜默重設；`vision_scope`（i_options）。
    本測試以「欄位集合」而非列舉欄位名比對，日後新增欄位若漏搬也會自動變紅。
    """
    from sqlalchemy import inspect, select

    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.services.v2 import rule_set_service as svc

    async def _rows(model, code: str) -> list:
        # 決定性排序（D3 code-review MED-2）：只用 sort_order 的話，rule_a_bands 三個
        # component 共用一張表、各自從 0 起算會產生三向 tie，來源與 clone 兩次查詢
        # 打不同 heap 就會錯位。本測試原本靠運氣通過。
        rs_id = (await db_session.execute(
            select(RuleSet.id).where(RuleSet.code == code))).scalar_one()
        return list((await db_session.execute(
            select(model).where(model.rule_set_id == rs_id)
            .order_by(*svc._deterministic_order(model))
        )).scalars().all())

    total_cells = 0
    for model_name in _CHILD_MODELS:
        model = getattr(rt, model_name)
        cols = [c.key for c in inspect(model).mapper.column_attrs if c.key not in _IGNORED_COLS]
        src_rows = await _rows(model, CERTIFIED)
        dst_rows = await _rows(model, draft_rs)
        assert len(dst_rows) == len(src_rows) and src_rows, (
            f"{model_name}: clone 列數不符（來源 {len(src_rows)} / clone {len(dst_rows)}）"
        )
        for idx, (src, dst) in enumerate(zip(src_rows, dst_rows, strict=True)):
            for col in cols:
                assert getattr(dst, col) == getattr(src, col), (
                    f"{model_name}[{idx}].{col} 未正確搬家："
                    f"來源={getattr(src, col)!r} clone={getattr(dst, col)!r}"
                )
                total_cells += 1
    assert total_cells > 400, f"比對的欄位格數過少（{total_cells}），測試可能沒真的走到"


async def test_put_full_rejects_bad_rotation_band_order(client, db_session, draft_rs):
    """HIGH-2：`PUT /full` 不得繞過帶界驗證——rotation 是唯一不經 `_sort_bands` 的帶族。

    `build_rule_set_data` 對 m_rotation 是 `tuple(rows)`，順序完全由 sort_order 決定。
    若 overflow 帶（max_diameter_cm=null）排在有限帶之前，`rotation_tmu(3, 1)` 的首次
    匹配就命中 overflow → **靜默回錯 TMU**。故此 payload 必須在寫入前被擋下。
    """
    full = (await client.get(f"/api/v2/rule-sets/{draft_rs}/full")).json()
    before = full["m_rotation"]
    full["m_rotation"] = [
        {"max_diameter_cm": None, "revolutions": 1, "tmu": 99, "sort": 0},
        {"max_diameter_cm": 5.0, "revolutions": 1, "tmu": 6, "sort": 1},
    ]
    r = await client.put(f"/api/v2/rule-sets/{draft_rs}/full", json=full)
    assert r.status_code == 400, r.text
    assert "最後一帶" in r.json()["error"]["message"], r.text

    after = (await client.get(f"/api/v2/rule-sets/{draft_rs}/full")).json()["m_rotation"]
    assert after == before, "400 後不得留下任何寫入副作用"


async def test_put_full_rejects_non_ascending_a_bands(client, draft_rs):
    """HIGH-2 同源：A 帶界未遞增經 `PUT /full` 也必須被擋。"""
    full = (await client.get(f"/api/v2/rule-sets/{draft_rs}/full")).json()
    full["a_bands"] = [
        {"component": "reach", "max_value": 20.0, "index": 6, "sort": 0},
        {"component": "reach", "max_value": 5.0, "index": 1, "sort": 1},
        {"component": "reach", "max_value": None, "index": 24, "sort": 2},
    ] + [b for b in full["a_bands"] if b["component"] != "reach"]
    r = await client.put(f"/api/v2/rule-sets/{draft_rs}/full", json=full)
    assert r.status_code == 400, r.text
    assert "未遞增" in r.json()["error"]["message"], r.text


@pytest.mark.parametrize("component", ["reach", "foot"])
async def test_a_bands_unbounded_component_requires_open_ended_last_band(client, draft_rs, component):
    """MEDIUM-3：reach/foot 物理上無上界 → 末帶必須 open-ended。

    理由是引擎實測行為：`rule_set_data.band_index` 末行 `return bands[-1][1]` 會把超界輸入
    **靜默夾取**到末帶（例：帶止於 20.0 時 reach=999 仍回 index 6），而非像 ladder/hand
    那樣回 None 轉顯式 range 錯誤。允許有限末帶＝允許靜默 fallback。
    """
    r = await client.put(
        f"/api/v2/rule-sets/{draft_rs}/params/A/bands", params={"component": component},
        json={"items": [{"max_value": 5.0, "index_value": 1}, {"max_value": 20.0, "index_value": 6}]},
    )
    assert r.status_code == 400, r.text
    assert "open-ended" in r.json()["error"]["message"] and "靜默夾取" in r.json()["error"]["message"], r.text


async def test_a_twist_may_end_with_finite_band(client, draft_rs):
    """MEDIUM-3 反面：twist 物理有界（180°），末帶為有限值合法——認證資料本來就是這樣。"""
    r = await client.put(
        f"/api/v2/rule-sets/{draft_rs}/params/A/bands", params={"component": "twist"},
        json={"items": [{"max_value": 30.0, "index_value": 0}, {"max_value": 180.0, "index_value": 6}]},
    )
    assert r.status_code == 200, r.text


async def test_option_is_active_never_affects_replay(client, db_session, draft_rs):
    """MEDIUM-4：選項級 `is_active` 的回放鐵則（ADR-023 §3.4）。

    停用一個**已被既有 cycle 引用**的選項後，重算的 TMU 必須完全不變——
    引擎載入不看治理狀態。若日後有人在 `providers.rows()` 加上 `.where(is_active)`，
    黃金測試仍會全綠（黃金資料的選項都是啟用的），只有這條會變紅。
    """
    from ddm_v2.most_engine import compute_cycle, load_rule_set_from_db
    from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine

    # 引用 g_grasp（G）與 p_place_none（P.base）的 GM cycle
    cycle = {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
             "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}

    async def _tmu() -> int:
        db_session.expire_all()
        rsdata = await load_rule_set_from_db(db_session, draft_rs)
        return compute_cycle(cycle_in_to_engine(CycleIn(**cycle)), rsdata).total_tmu

    before = await _tmu()
    assert before > 0

    off_g = await client.patch(
        f"/api/v2/rule-sets/{draft_rs}/params/G/options/g_grasp", json={"is_active": False})
    assert off_g.status_code == 200 and off_g.json()["is_active"] is False, off_g.text
    off_p = await client.patch(
        f"/api/v2/rule-sets/{draft_rs}/params/P/options/p_place_none",
        params={"section": "base"}, json={"is_active": False})
    assert off_p.status_code == 200 and off_p.json()["is_active"] is False, off_p.text

    assert await _tmu() == before, (
        "停用選項改變了重算結果＝回放鐵則破裂（ADR-023 §3.4）："
        "引擎載入路徑不得依 is_active 過濾"
    )
