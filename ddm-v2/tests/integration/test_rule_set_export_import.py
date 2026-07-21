"""Rule-set 匯出／匯入 draft（ADR-023 §3.6 / D3）。

核心不變式：**export 去掉三個 metadata 欄後，可原樣 `PUT /full` 回一個 draft**，
且 `import` 建出的版本與來源逐欄相等。這條對稱性是 export→離線編輯→import 閉環的地基；
一旦破裂，使用者匯出再匯入會**靜默**拿到不同的字典（值變了卻無錯誤訊息）。

⚠️ 測試紀律（沿 D1/D2）：
- 寫入一律打拋棄式版本；**絕不**對 V1/V2 動手（它們是回放基準）。
- skip 條件只看資料前置條件（rule-set 有沒有種），不看被測端點的回應碼。
- 400/409 的案例一律加驗「DB 沒有任何殘留列」——只擋回應不擋落盤＝gate 失效。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration

CERTIFIED = "MINIMOST_FACTORY_V2"  # active / certified_import（ADR-014 值權威）
META = ("schema_version", "exported_at", "exported_by")

# 12 張子表在 load_full 的區塊名
FULL_SECTIONS = [
    "a_bands", "b", "g", "p_bases", "p_addons", "m_ladder", "m_foot",
    "m_verbs", "m_rotation", "m_hand", "x", "i",
]

_CHILD_MODELS = [
    "RuleABand", "RuleBOption", "RuleGAction", "RulePBase", "RulePAddon",
    "RuleMLadderBand", "RuleMFootBand", "RuleMVerb", "RuleMRotationBand",
    "RuleMHandBand", "RuleXOption", "RuleIOption",
]
_IGNORED_COLS = {"id", "rule_set_id"}


async def _seeded(db_session) -> bool:
    """資料前置條件：認證版本是否已種（不看被測端點的回應）。"""
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet

    return (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == CERTIFIED))).first() is not None


@pytest_asyncio.fixture
async def exported(client, db_session) -> dict:
    """V2 的匯出負載（唯讀操作，不動 V2）。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    r = await client.get(f"/api/v2/rule-sets/{CERTIFIED}/export")
    assert r.status_code == 200, r.text
    return r.json()


@pytest_asyncio.fixture
async def draft_rs(db_session) -> str:
    """拋棄式 draft（provenance=cloned），供 PUT /full 對稱性測試。"""
    from ddm_v2.services.v2 import rule_set_service as svc

    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    code = f"UT_EXP_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, CERTIFIED, code, "匯出入測試草稿")
    await db_session.commit()
    return code


async def _rule_set_count(db_session) -> int:
    from sqlalchemy import func, select

    from ddm_v2.models.v2.rule_set import RuleSet

    return int((await db_session.execute(select(func.count()).select_from(RuleSet))).scalar_one())


async def _child_row_count(db_session, code: str) -> int:
    """該 code 名下所有子表列數總和（版本不存在 → 0）。"""
    from sqlalchemy import func, select

    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet

    rs_id = (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == code))).scalar_one_or_none()
    if rs_id is None:
        return 0
    total = 0
    for name in _CHILD_MODELS:
        model = getattr(rt, name)
        total += int((await db_session.execute(
            select(func.count()).select_from(model).where(model.rule_set_id == rs_id)
        )).scalar_one())
    return total


def _strip_meta(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in META}


# ══════════════════════════════════════════════════════════════════
# D3-1 匯出
# ══════════════════════════════════════════════════════════════════

async def test_export_is_full_plus_metadata(client, exported):
    """匯出＝`GET /full` 的形狀 ＋ 三個 metadata 欄，一欄不多一欄不少。

    多出的欄位會讓「去 metadata 即可 PUT」的規則失準（PUT /full 對未知鍵是靜默忽略），
    少的欄位則直接讓 round-trip 掉資料。
    """
    full = (await client.get(f"/api/v2/rule-sets/{CERTIFIED}/full")).json()
    assert set(exported) - set(full) == set(META), (
        f"匯出與 full 的欄位差異不等於 metadata：{set(exported) - set(full)}"
    )
    assert set(full) - set(exported) == set(), "匯出漏掉了 full 的欄位"
    assert exported["schema_version"] == "1"
    assert exported["exported_by"] == "IEC141289"
    assert exported["exported_at"]


async def test_export_contains_every_section_including_d2_fields(exported):
    """匯出必須含全部 12 區塊，且含 D2 才補齊的 4 類欄位（否則 round-trip 會靜默掉值）。

    D2 修好的漏欄：`sentence_text_zh`（7 張表，缺 → narrative 回退 label_zh 產生不同 METHOD 句）、
    `display_rule` / `max_select`（p_addons）、`vision_scope`（i_options），以及整張
    `rule_m_foot_bands`（原本連區塊都沒有）。這裡逐一確認匯出確實帶出來。
    """
    for sec in FULL_SECTIONS:
        assert exported.get(sec), f"匯出區塊 {sec} 是空的"
    assert any(r.get("sentence_text_zh") for r in exported["g"]), "g.sentence_text_zh 全空"
    assert all("display_rule" in r and "max_select" in r for r in exported["p_addons"])
    assert all("vision_scope" in r for r in exported["i"])
    assert exported["m_foot"], "m_foot 整表缺失（D2 修過的漏表）"


async def test_export_visible_to_viewer(client, exported):
    """RBAC：export 是 current_user 級（IE/viewer 都要能看），不得誤掛寫入角色 gate。"""
    viewer = "GAPTEST_VIEWER_EXPORT_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": viewer, "display_name": "Gap Test Viewer Export",
        "roles": [], "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    r = await client.get(f"/api/v2/rule-sets/{CERTIFIED}/export", headers={"X-Username": viewer})
    assert r.status_code == 200, r.text
    assert r.json()["exported_by"] == viewer


async def test_export_unknown_code_returns_404(client):
    r = await client.get("/api/v2/rule-sets/NO_SUCH_RULE_SET/export")
    assert r.status_code == 404, r.text


# ══════════════════════════════════════════════════════════════════
# D3-2/D3-3 round-trip（本批核心不變式）
# ══════════════════════════════════════════════════════════════════

async def test_export_import_round_trip_preserves_every_column(client, db_session, exported):
    """export → import → **逐欄**與來源相等（12 張子表 × 每一欄 × 每一列）。

    欄位集合以 `inspect(model).mapper.column_attrs` 動態取得而非列舉欄位名：
    日後任何人新增子表欄位卻忘了加進 `load_full`/`_insert_children`，本測試會自動變紅。
    """
    from sqlalchemy import inspect, select

    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.services.v2 import rule_set_service as svc

    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    r = await client.post("/api/v2/rule-sets/import", json={**exported, "new_code": new_code})
    assert r.status_code == 200, r.text

    async def _rows(model, code: str) -> list:
        # 用服務層同一組決定性排序（sort_order → 內容欄 → id）。只用 sort_order 的話，
        # `rule_a_bands` 三個 component 共用一張表、各自從 0 起算會產生三向 tie，
        # 兩次查詢打不同 heap 就會錯位——本測試曾因此紅過（code-review MED-2）。
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
        dst_rows = await _rows(model, new_code)
        assert len(dst_rows) == len(src_rows) and src_rows, (
            f"{model_name}: 匯入列數不符（來源 {len(src_rows)} / 匯入 {len(dst_rows)}）"
        )
        for idx, (src, dst) in enumerate(zip(src_rows, dst_rows, strict=True)):
            for col in cols:
                assert getattr(dst, col) == getattr(src, col), (
                    f"{model_name}[{idx}].{col} 匯入後不同："
                    f"來源={getattr(src, col)!r} 匯入={getattr(dst, col)!r}"
                )
                total_cells += 1
    assert total_cells > 400, f"比對的欄位格數過少（{total_cells}），測試可能沒真的走到"

    # load_full 層級的深度相等（除版本身分欄外一字不差）
    dst_full = (await client.get(f"/api/v2/rule-sets/{new_code}/full")).json()
    src_full = (await client.get(f"/api/v2/rule-sets/{CERTIFIED}/full")).json()
    for k in ("id", "code", "name_zh", "status"):
        dst_full.pop(k), src_full.pop(k)
    assert dst_full == src_full


async def test_export_payload_is_put_full_compatible(client, draft_rs, exported):
    """對稱性：export 去掉三個 metadata 欄後，可**原樣** PUT 回一個 draft。

    這是 §3.6「與 PUT /full 對稱」的機械化定義。若 export 加了 PUT 不吃的欄位，
    或 PUT 需要 export 不產出的欄位，這裡會斷。

    ⚠️ 目標 draft 是從同一份來源 clone 的，內容本來就一樣——若直接 PUT 原樣負載，
    即使 PUT 整個沒生效也會「通過」。故先在負載裡改掉一個可觀測的值（離線編輯的模擬），
    再要求回寫結果反映該修改（LOW-3）。
    """
    body = _strip_meta(exported)
    edited_label = "離線編輯後的標籤"
    body["b"] = [{**body["b"][0], "label_zh": edited_label}, *body["b"][1:]]

    r = await client.put(f"/api/v2/rule-sets/{draft_rs}/full", json=body)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["b"][0]["label_zh"] == edited_label, "離線編輯的值沒有寫進去（PUT 可能整個沒生效）"
    for sec in FULL_SECTIONS:
        assert after[sec] == body[sec], f"PUT 回寫後 {sec} 與送出的內容不符"


async def test_import_creates_draft_manual_only(client, db_session, exported):
    """§3.6 明文：匯入**只建** status=draft + provenance=manual。

    來源是 certified_import 的 V2，若匯入沿用來源血緣，等於讓使用者用上傳檔案的方式
    製造「認證版本」——那正是 ADR-014 要防的（值權威不交給 runtime）。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet

    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    r = await client.post("/api/v2/rule-sets/import", json={**exported, "new_code": new_code})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "code": new_code, "status": "draft", "provenance": "manual", "warnings": [],
    }

    rs = (await db_session.execute(
        select(RuleSet).where(RuleSet.code == new_code))).scalar_one()
    assert rs.status == "draft", f"匯入版本狀態應為 draft，實際 {rs.status}"
    assert rs.provenance == "manual", f"匯入版本血緣應為 manual，實際 {rs.provenance}"
    assert rs.is_active is False


async def test_import_auto_names_code_when_omitted(client, db_session, exported):
    """new_code 缺省 → 沿用 clone-draft 的自動命名規則 `{code}_DRAFT_{YYYYMMDDHHMM}`。"""
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet

    r = await client.post("/api/v2/rule-sets/import", json=exported)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert code.startswith(f"{CERTIFIED}_DRAFT_"), code
    assert (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == code))).first() is not None


# ══════════════════════════════════════════════════════════════════
# D3-3 拒收路徑（一律加驗零殘留）
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mutate", [
    pytest.param(lambda p: p.pop("schema_version"), id="missing"),
    pytest.param(lambda p: p.update(schema_version="2"), id="future"),
    pytest.param(lambda p: p.update(schema_version=1), id="int-not-str"),
])
async def test_import_bad_schema_version_returns_400(client, db_session, exported, mutate):
    """schema_version 必填且須為 "1"；缺/不符一律 400，且不得建出任何版本。

    `1`（int）也要擋：契約寫的是字串 `"1"`，若用 `str(got)` 寬鬆比對，型別錯誤的負載
    會被靜默接受——版本協商一旦開始猜測，日後 schema v2 的相容判斷就不可靠。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    mutate(payload)
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert "schema_version" in r.json()["detail"]
    assert await _rule_set_count(db_session) == before, "400 後不得建出版本"
    assert await _child_row_count(db_session, new_code) == 0


async def test_import_bad_rotation_band_order_returns_400_and_rolls_back(client, db_session, exported):
    """帶界驗證必須套用在 import（否則 import 成為繞過 `PUT /full` 契約的後門）。

    用 D2 的 rotation 亂序案例：`build_rule_set_data` 對 m_rotation 是 `tuple(rows)`，
    **唯一不經 `_sort_bands` 的帶族**，overflow 帶（max_diameter_cm=null）排在有限帶之前，
    `rotation_tmu()` 首次匹配即命中 overflow → 靜默回錯 TMU。故必須在寫入前擋下，
    且交易完整回滾（不得留半個版本）。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload["m_rotation"] = [
        {"max_diameter_cm": None, "revolutions": 1, "tmu": 99, "sort": 0},
        {"max_diameter_cm": 5.0, "revolutions": 1, "tmu": 6, "sort": 1},
    ]
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert "最後一帶" in r.json()["detail"], r.text
    assert await _rule_set_count(db_session) == before, "400 後不得建出版本"
    assert await _child_row_count(db_session, new_code) == 0, "400 後不得留下任何子表列"


async def test_import_missing_required_section_returns_400(client, db_session, exported):
    """缺必要子表（整個 `g` 陣列缺失）→ 400，**不得靜默建立不完整版本**。

    若放行，這個版本會在 publish 時（validate_complete）才炸，最壞情況是使用者已在
    UI 上以為建好了字典。錯誤訊息須指名缺哪一塊。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload.pop("g")
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert "g" in r.json()["detail"] and "缺少區塊" in r.json()["detail"], r.text
    assert await _rule_set_count(db_session) == before
    assert await _child_row_count(db_session, new_code) == 0


async def test_import_missing_a_component_returns_400(client, db_session, exported):
    """A 三分量共用一張表：只缺 `foot` 分量時，列數仍非零，靠陣列非空判斷會漏掉。"""
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload["a_bands"] = [b for b in exported["a_bands"] if b["component"] != "foot"]
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert "a_bands[foot]" in r.json()["detail"], r.text
    # 兩者都要驗：_child_row_count 回 0 分不出「沒建版本」與「建了空殼版本」（LOW-4）
    assert await _rule_set_count(db_session) == before, "400 後不得留下空殼版本"
    assert await _child_row_count(db_session, new_code) == 0


async def test_import_malformed_row_returns_400_and_rolls_back(client, db_session, exported):
    """列內欄位缺漏（g 少了 base_tmu）→ 400 而非 500，且已 flush 的版本列必須回滾。

    這一條是**交易完整性**的證據：表頭列在 `_insert_children` 之前就已 flush 進 DB，
    若沒有回滾，失敗的匯入會留下一個空殼版本。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload["g"] = [{k: v for k, v in row.items() if k != "base_tmu"} for row in exported["g"]]
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert await _rule_set_count(db_session) == before, "400 後不得留下空殼版本"
    assert await _child_row_count(db_session, new_code) == 0


async def test_import_duplicate_code_returns_409(client, db_session, exported, draft_rs):
    """new_code 撞既有 code → 409（code 有 UNIQUE，不能讓它變成 500）。且既有版本不得被覆寫。"""
    before_rows = await _child_row_count(db_session, draft_rs)
    r = await client.post("/api/v2/rule-sets/import", json={**exported, "new_code": draft_rs})
    assert r.status_code == 409, r.text
    assert draft_rs in r.json()["detail"]
    assert await _child_row_count(db_session, draft_rs) == before_rows, "409 不得動到既有版本"


async def test_import_requires_analyst(client, db_session, exported):
    """RBAC：匯入是寫入 → analyst 以上；無角色使用者（JIT viewer，level 0）→ 403 且零殘留。"""
    viewer = "GAPTEST_VIEWER_IMPORT_001"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": viewer, "display_name": "Gap Test Viewer Import",
        "roles": [], "site_ids": [],
    })
    assert ur.status_code == 200, ur.text
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    before = await _rule_set_count(db_session)

    r = await client.post(
        "/api/v2/rule-sets/import",
        json={**exported, "new_code": new_code},
        headers={"X-Username": viewer},
    )
    assert r.status_code == 403, r.text
    assert await _rule_set_count(db_session) == before, "403 後不得留下寫入副作用"


async def test_import_certified_source_still_needs_publish_to_be_usable(client, db_session, exported):
    """匯入版本是 draft → 不可被 activate（須先 publish）。

    §3.6 的「只建 draft」若被繞過（例如直接建 published），這條會綠燈放行 activate；
    故此測試同時是「只建 draft」的第二道證據。
    """
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    assert (await client.post(
        "/api/v2/rule-sets/import", json={**exported, "new_code": new_code})).status_code == 200
    r = await client.post(f"/api/v2/rule-sets/{new_code}/activate")
    assert r.status_code == 400, r.text
    assert "僅 published 版本可啟用" in r.json()["detail"], r.text


# ══════════════════════════════════════════════════════════════════
# code-review HIGH-1：m_foot 缺席是「靜默算錯值」路徑，不是單純的選配
# ══════════════════════════════════════════════════════════════════

async def test_import_missing_m_foot_key_returns_400(client, db_session, exported):
    """掉整塊 `m_foot`（鍵不見）→ 400。

    為什麼 m_foot 與其他三個選配表不同：`rule_set_data.foot_tmu()` 在 `self.m_foot` 為空時
    **靜默回退** `ladder_tmu()`（p_addons/m_rotation/m_hand 缺席都是顯式錯誤：
    P_ADDON_UNKNOWN / M_ROTATION_RANGE / M_HAND_RANGE）。實測偏差：1cm 10→3（−70%）、
    5cm 10→6（−40%）、80cm 42→硬錯。而 `validate_complete()` 與 `validate_active_options()`
    都不檢查 m_foot ⇒ 這種版本可以 publish 也可以 activate，之後每個腳步動作低估 40–70%
    且全鏈無錯誤無警告。回退在「V1 回放」是正當的，在「建立新版本」不正當。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload.pop("m_foot")
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "m_foot" in detail and "缺少區塊" in detail, r.text
    assert await _rule_set_count(db_session) == before, "400 後不得建出版本"


async def test_import_explicit_empty_m_foot_succeeds_with_warning(client, db_session, exported):
    """顯式空陣列 `"m_foot": []` → 200 ＋ warning。

    這是鍵存在性檢查與非空檢查必須分開的理由：V1 本來就沒有 foot 表，它的 export 帶
    `"m_foot": []`，必須能匯入；但回退行為要在匯入當下講出來，不能等到工時已經低估才發現。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet

    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload["m_foot"] = []

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 200, r.text
    warnings = r.json()["warnings"]
    assert any("m_foot" in w and "回退" in w for w in warnings), warnings

    rs_id = (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == new_code))).scalar_one()
    rows = (await db_session.execute(
        select(rt.RuleMFootBand).where(rt.RuleMFootBand.rule_set_id == rs_id))).scalars().all()
    assert list(rows) == [], "顯式空陣列不該長出任何 m_foot 列"


async def test_import_full_payload_has_no_warnings(client, exported):
    """對照組：m_foot 有資料時 warnings 必須是空的（否則 warning 變成永遠亮著的雜訊）。"""
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    r = await client.post("/api/v2/rule-sets/import", json={**exported, "new_code": new_code})
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []


async def test_import_empty_required_section_returns_400(client, db_session, exported):
    """必要子表給了鍵但陣列是空的 → 400（與「鍵不見」不同訊息，但同樣不得放行）。"""
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload["g"] = []
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert "g" in r.json()["detail"] and "空的" in r.json()["detail"], r.text
    assert await _rule_set_count(db_session) == before


async def test_put_full_missing_section_returns_400(client, db_session, draft_rs, exported):
    """`PUT /full` 有同一個洞（D2 遺留）：它同樣是「建立版本內容」的入口。

    既有呼叫端（前端字典 UI、4 支整合測試）一律送完整 `GET /full` 負載，故此檢查
    不破壞既有契約。
    """
    body = _strip_meta(exported)
    body.pop("m_foot")
    r = await client.put(f"/api/v2/rule-sets/{draft_rs}/full", json=body)
    assert r.status_code == 400, r.text
    assert "m_foot" in r.json()["detail"], r.text


# ══════════════════════════════════════════════════════════════════
# code-review HIGH-2：畸形「帶」列必須是 400 不是 500
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(("section", "rows"), [
    pytest.param("m_ladder", [{"tmu": 6, "sort": 0}], id="ladder-missing-max_cm"),
    pytest.param("m_rotation", [{"max_diameter_cm": 5.0, "tmu": 6, "sort": 0}], id="rotation-missing-revolutions"),
    pytest.param("m_hand", [{"tmu": 6, "sort": 0}], id="hand-missing-max_deg"),
    pytest.param("m_ladder", ["not-a-dict"], id="row-not-a-dict"),
    pytest.param("m_ladder", [{"max_cm": 10.0, "tmu": 6, "sort": "x"}], id="sort-not-an-int"),
])
async def test_import_malformed_band_row_returns_400(client, db_session, exported, section, rows):
    """帶列畸形一律 400 ＋ 零殘留。

    這組是 D3 初版漏掉的：`KeyError` 多半在 `validate_bands` **內部**就拋了
    （guard 卻只包住 `_insert_children`），所以 6 種畸形負載有 5 種回 500。
    `sort:"x"` 走的是另一條路——型別在 Python 層合法、到 DB 才被拒（DataError）。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload[section] = rows
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert await _rule_set_count(db_session) == before, "400 後不得留下空殼版本"
    assert await _child_row_count(db_session, new_code) == 0


async def test_import_malformed_a_band_row_returns_400(client, db_session, exported):
    """`a_bands` 某一列缺 `max_value`：A 是唯一「超界會靜默夾取」的帶族，畸形列更不能放行。

    ⚠️ 三個 component 都保持齊全——若整組只留 reach，400 其實來自「缺 a_bands[twist]」
    的區塊檢查，帶列 guard 根本沒被走到（測試會變成假綠/假紅）。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    reach = [b for b in exported["a_bands"] if b["component"] == "reach"]
    others = [b for b in exported["a_bands"] if b["component"] != "reach"]
    broken = {k: v for k, v in reach[0].items() if k != "max_value"}
    payload["a_bands"] = [broken, *reach[1:], *others]
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert "帶" in r.json()["detail"], r.text
    assert await _rule_set_count(db_session) == before
    assert await _child_row_count(db_session, new_code) == 0


# ══════════════════════════════════════════════════════════════════
# code-review MED-1：multiplier 會等比縮放整個版本的 TMU
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad", ["abc", 0, -1, -0.5, True], ids=[
    "string", "zero", "negative-int", "negative-float", "bool",
])
async def test_import_invalid_multiplier_returns_400(client, db_session, exported, bad):
    """非正數 multiplier → 400。

    未擋時：`"abc"` → asyncpg DataError 500；`0` / 負數會被**接受**並靜默把該版本
    每一個 TMU 歸零或反號（`system_tmu_multiplier` 是全域縮放係數）。
    `True` 也要擋——Python 的 bool 是 int 子類，`True > 0` 為真會讓它溜過去。
    """
    payload = dict(exported)
    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    payload["new_code"] = new_code
    payload["multiplier"] = bad
    before = await _rule_set_count(db_session)

    r = await client.post("/api/v2/rule-sets/import", json=payload)
    assert r.status_code == 400, r.text
    assert "multiplier" in r.json()["detail"], r.text
    assert await _rule_set_count(db_session) == before


# ══════════════════════════════════════════════════════════════════
# code-review MED-2：查詢順序的決定性
# ══════════════════════════════════════════════════════════════════

async def test_a_bands_sort_order_has_ties_and_export_is_deterministic(client, exported):
    """`rule_a_bands` 三個 component 共用一張表、sort_order 各自從 0 起算 → 有 tie。

    前半段先釘住「tie 真的存在」（否則後半段的決定性斷言是空的）；後半段要求
    重複匯出的 `a_bands` 順序完全一致——tie 若無 tiebreaker，`ORDER BY sort_order`
    的結果由 heap 決定，API 就不是決定性的，而 round-trip 的位置比對也只是運氣。
    """
    sorts = [b["sort"] for b in exported["a_bands"]]
    assert len(sorts) != len(set(sorts)), "前提不成立：a_bands 的 sort 沒有重複，本測試失去意義"

    again = (await client.get(f"/api/v2/rule-sets/{CERTIFIED}/export")).json()
    assert again["a_bands"] == exported["a_bands"], "重複匯出的 a_bands 順序不一致（非決定性）"


async def test_a_bands_order_survives_physical_row_rewrite(client, db_session, exported):
    """實體列順序被改寫後，匯出的 `a_bands` 順序仍須不變（MED-2 的可重現證明）。

    單純「連打兩次匯出」多半會湊巧同序，證不出 tie 的危險。這裡直接 UPDATE 一列
    （PostgreSQL 的 MVCC 會寫新 tuple 到 heap 尾端 → seq scan 的實體順序改變）：
    若 `ORDER BY` 只有 `sort_order`，三向 tie 的相對順序就會跟著改變，API 於是
    「同一份資料、不同回應」；有內容欄 tiebreaker 才穩得住。
    """
    from sqlalchemy import select, update

    from ddm_v2.models.v2 import rule_set_tables as rt
    from ddm_v2.models.v2.rule_set import RuleSet

    rs_id = (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == CERTIFIED))).scalar_one()
    first_reach = (await db_session.execute(
        select(rt.RuleABand.id).where(
            rt.RuleABand.rule_set_id == rs_id, rt.RuleABand.component == "reach"
        ).order_by(rt.RuleABand.sort_order).limit(1))).scalar_one()
    await db_session.execute(
        update(rt.RuleABand).where(rt.RuleABand.id == first_reach)
        .values(index_value=rt.RuleABand.index_value)
    )
    await db_session.commit()

    after = (await client.get(f"/api/v2/rule-sets/{CERTIFIED}/export")).json()
    assert after["a_bands"] == exported["a_bands"], (
        "實體列順序改變後匯出順序就跟著變＝ORDER BY 不是全序（tie 無 tiebreaker）"
    )


# ══════════════════════════════════════════════════════════════════
# code-review LOW-5：ADR-014 繞道防線
# ══════════════════════════════════════════════════════════════════

async def test_import_ignores_governance_fields_in_payload(client, db_session, exported):
    """負載內的治理欄位一律忽略：手改 JSON 不得製造出 published / active / certified_import 版本。

    這是 ADR-014「值權威不交給 runtime」的直接防線——認證血緣只能由
    `scripts/import_v3_dictionary.py` ＋ git ＋ CI Gate 3 產生。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet

    new_code = f"UT_IMP_{uuid.uuid4().hex[:8]}"
    injected_id = str(uuid.uuid4())
    r = await client.post("/api/v2/rule-sets/import", json={
        **exported, "new_code": new_code,
        "provenance": "certified_import", "is_active": True, "status": "published",
        "published_by": "SOMEONE", "id": injected_id,
    })
    assert r.status_code == 200, r.text

    rs = (await db_session.execute(
        select(RuleSet).where(RuleSet.code == new_code))).scalar_one()
    assert rs.provenance == "manual", "負載的 provenance 不得被採信（ADR-014 繞道）"
    assert rs.status == "draft"
    assert rs.is_active is False
    assert rs.published_by is None
    assert str(rs.id) != injected_id, "id 必須由伺服器產生，不得採信負載"
