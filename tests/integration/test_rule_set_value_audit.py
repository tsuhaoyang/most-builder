"""ADR-023 D7：改「值」的路徑必須留下前後值稽核 ＋ 數值契約不得被繞過。

三項資安發現的端點級防回歸：

- **H-1**：`log_audit` 原本只掛在 6 個**狀態遷移**（import/publish/activate/delete/
  unretire/retire），真正改 TMU 的 7 支路徑（clone-draft、`PUT /full`、選項級
  create/update/delete/duplicate、`PUT /bands`）**一筆紀錄都沒有**。
  攻擊鏈：analyst clone 草稿（無紀錄）→ 把 G 動作 `base_tmu` 6 改成 3（無紀錄）→
  請 approver 發布。事後 log 上只有 approver 的員編，分不出誰改值、誰覆核。
- **H-1 delete**：`delete_rule_set` 的 payload 原本只有各表列數。實體刪掉之後，
  列數說不出被刪的是什麼值。
- **M-1**：`import` / `PUT /full` 直接 `int(r["base_tmu"])` 寫 DB，繞過
  `schemas/v2/rule_set_options.py` 的 `Field(ge=0)`，而 DB 數值欄無 CHECK
  → 負數 TMU 可一路通過 publish/activate。

⚠️ 一律對 `throwaway_draft` 建的拋棄式版本動手，**不得**改 V1/V2（回放基準）。
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from ddm_v2.models.v2.rule_set import RuleSet

pytestmark = pytest.mark.integration

ACTIVE = "MINIMOST_FACTORY_V2"   # active 版本（本檔唯讀）
ACTOR = "IEC141289"              # conftest 的 client 身分（admin）

# V2 字典裡的實際值，用來證明斷言拿到的是「真的那個值」而不是任意數字。
G_CODE, G_TMU = "g_grasp", 6


@pytest_asyncio.fixture
async def draft(client, db_session) -> str:
    """經 **API** clone 出拋棄式草稿——順便把 clone-draft 的稽核走一遍（route→service 的 actor）。"""
    code = f"UT_D7_{uuid.uuid4().hex[:8]}"
    r = await client.post(f"/api/v2/rule-sets/{ACTIVE}/clone-draft",
                          json={"new_code": code, "name_zh": "D7 拋棄式草稿"})
    assert r.status_code == 200, r.text
    return code


async def _rs_id(db_session, code: str) -> uuid.UUID:
    return (await db_session.execute(select(RuleSet.id).where(RuleSet.code == code))).scalar_one()


async def _audits(db_session, rs_id: uuid.UUID, action: str) -> list[dict[str, Any]]:
    rows = (await db_session.execute(text(
        "SELECT actor, payload FROM workflow_audit_log "
        "WHERE entity_type='rule_set' AND entity_id=:i AND action=:a ORDER BY created_at"
    ), {"i": rs_id, "a": action})).all()
    for actor, _payload in rows:
        assert actor == ACTOR, f"稽核必須記下實際操作者，收到 {actor!r}"
    return [payload for _actor, payload in rows]


async def _one_audit(db_session, code: str, action: str) -> dict[str, Any]:
    rs_id = await _rs_id(db_session, code)
    payloads = await _audits(db_session, rs_id, action)
    assert len(payloads) == 1, f"action={action} 應恰好一筆稽核，收到 {len(payloads)} 筆"
    return payloads[0]


async def _g_row(client, code: str, option_code: str) -> dict[str, Any]:
    r = await client.get(f"/api/v2/rule-sets/{code}/params/G/options")
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["code"] == option_code)


# ══════════════════════════════════════════════════════════════════
# H-1：7 支改值路徑各自留下含「前後值」的稽核
# ══════════════════════════════════════════════════════════════════


async def test_clone_draft_writes_audit_pinning_the_source_content(client, db_session, draft):
    """(1/7) clone-draft＝值改動鏈的起點，原本完全無紀錄。

    payload 不存全量快照（見 service docstring 的理由），但必須釘住「從哪一版 clone、
    內容有多少、內容的 hash 是什麼」——否則連「這個草稿哪來的」都答不出來。
    """
    p = await _one_audit(db_session, draft, "clone_draft")
    assert p["code"] == draft
    assert p["source_code"] == ACTIVE
    assert p["source_is_active"] is True
    assert len(p["snapshot_sha256"]) == 64
    assert p["row_counts"]["g"] > 0 and p["row_counts"]["a_bands"] > 0
    assert len(p["row_counts"]) == 12


async def test_option_update_audit_carries_before_and_after_tmu(client, db_session, draft):
    """(2/7) 這就是資安席描述的那一步：G 動作 base_tmu 6 → 3。"""
    r = await client.patch(
        f"/api/v2/rule-sets/{draft}/params/G/options/{G_CODE}", json={"base_tmu": 3})
    assert r.status_code == 200, r.text

    p = await _one_audit(db_session, draft, "option_update")
    assert (p["param"], p["section"], p["option_code"]) == ("G", "default", G_CODE)
    # 只斷言「有一列」會空洞通過——必須拿得到具體數值。
    assert p["before"]["base_tmu"] == G_TMU
    assert p["after"]["base_tmu"] == 3
    assert p["changed_fields"] == {"base_tmu": {"before": G_TMU, "after": 3}}


async def test_option_create_audit_carries_the_created_values(client, db_session, draft):
    """(3/7)"""
    r = await client.post(f"/api/v2/rule-sets/{draft}/params/G/options", json={
        "code": "g_ut_new", "label_zh": "D7 新動作", "base_tmu": 42, "sort_order": 99})
    assert r.status_code == 200, r.text

    p = await _one_audit(db_session, draft, "option_create")
    assert p["option_code"] == "g_ut_new"
    assert p["before"] is None
    assert p["after"]["base_tmu"] == 42


async def test_option_delete_audit_carries_the_deleted_values(client, db_session, draft):
    """(4/7) 硬刪：不留前值就再也查不到被刪的是什麼。"""
    r = await client.delete(f"/api/v2/rule-sets/{draft}/params/G/options/{G_CODE}")
    assert r.status_code == 200, r.text

    p = await _one_audit(db_session, draft, "option_delete")
    assert p["option_code"] == G_CODE
    assert p["before"]["base_tmu"] == G_TMU
    assert p["after"] is None


async def test_option_duplicate_audit_names_source_and_values(client, db_session, draft):
    """(5/7) 複製本身不改值，但它會生出一個「看起來很像官方」的新 code。"""
    r = await client.post(
        f"/api/v2/rule-sets/{draft}/params/G/options/{G_CODE}/duplicate")
    assert r.status_code == 200, r.text
    new_code = r.json()["code"]

    p = await _one_audit(db_session, draft, "option_duplicate")
    assert p["option_code"] == new_code
    assert p["source_option_code"] == G_CODE
    assert p["after"]["base_tmu"] == G_TMU


async def test_bands_replace_audit_carries_whole_group_snapshots(client, db_session, draft):
    """(6/7) 帶型無 code → 稽核存整組前後快照。"""
    before_rows = (await client.get(
        f"/api/v2/rule-sets/{draft}/params/M/options?section=ladder")).json()["items"]
    assert before_rows[0]["tmu"] == 3, "前提：V2 的 ladder 首帶為 3 TMU"

    r = await client.put(f"/api/v2/rule-sets/{draft}/params/M/bands?section=ladder", json={
        "items": [{"max_cm": 2.5, "tmu": 1}, {"max_cm": 10.0, "tmu": 2}]})
    assert r.status_code == 200, r.text

    p = await _one_audit(db_session, draft, "bands_replace")
    assert (p["param"], p["section"]) == ("M", "ladder")
    assert [b["tmu"] for b in p["before"]] == [b["tmu"] for b in before_rows]
    assert [a["tmu"] for a in p["after"]] == [1, 2]
    assert p["row_counts"] == {"before": len(before_rows), "after": 2}


async def test_put_full_audit_carries_value_diff(client, db_session, draft):
    """(7/7) `PUT /full` 是改值最強力的一條路徑（整份 12 張子表替換），原本無紀錄。"""
    full = (await client.get(f"/api/v2/rule-sets/{draft}/full")).json()
    target = next(r for r in full["g"] if r["code"] == G_CODE)
    target["base_tmu"] = 1
    full["g"] = [r for r in full["g"] if r["code"] != "g_touch"]      # 刪一列
    full["g"].append({**target, "code": "g_ut_added", "base_tmu": 77})  # 加一列

    r = await client.put(f"/api/v2/rule-sets/{draft}/full", json=full)
    assert r.status_code == 200, r.text

    p = await _one_audit(db_session, draft, "update_full")
    g = p["diff"]["sections"]["g"]
    assert next(c for c in g["changed"] if c["key"] == G_CODE)["fields"]["base_tmu"] == {
        "before": G_TMU, "after": 1}
    assert [x["key"] for x in g["removed"]] == ["g_touch"]
    assert next(a for a in g["added"] if a["key"] == "g_ut_added")["after"]["base_tmu"] == 77
    assert p["diff"]["row_counts"]["g"]["before"] == p["diff"]["row_counts"]["g"]["after"]


async def test_delete_audit_snapshot_can_restore_the_deleted_values(client, db_session, draft):
    """H-1 第 2 點：實體刪除後，稽核 payload 必須還原得出被刪版本的**值**。

    改動前 payload 只有 `children_deleted`（各表列數）——列數還原不了任何一個 TMU。
    """
    rs_id = await _rs_id(db_session, draft)
    assert (await client.delete(f"/api/v2/rule-sets/{draft}")).status_code == 200

    payloads = await _audits(db_session, rs_id, "delete")
    assert len(payloads) == 1
    p = payloads[0]
    assert p["children_deleted"]["rule_g_actions"] > 0
    snapshot = p["snapshot"]
    restored = next(r for r in snapshot["g"] if r["code"] == G_CODE)
    assert restored["base_tmu"] == G_TMU, "只有具體 TMU 取得到，才算真的還原得了值"
    assert len(snapshot["a_bands"]) > 0 and len(snapshot["m_ladder"]) > 0
    assert len(p["snapshot_sha256"]) == 64


# ══════════════════════════════════════════════════════════════════
# H-1 第 3 點：publish 前的 diff（覆核者看得到被覆核的是什麼）
# ══════════════════════════════════════════════════════════════════


async def test_diff_reports_value_change_against_active_base(client, db_session, draft):
    await client.patch(f"/api/v2/rule-sets/{draft}/params/G/options/{G_CODE}",
                       json={"base_tmu": 3})

    r = await client.get(f"/api/v2/rule-sets/{draft}/diff")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["base_code"] == ACTIVE, "回應必須標明比較基準版本 code"
    assert body["base_is_active"] is True
    assert body["target_code"] == draft

    changed = body["diff"]["sections"]["g"]["changed"]
    assert [c["key"] for c in changed] == [G_CODE]
    assert changed[0]["fields"]["base_tmu"] == {"before": G_TMU, "after": 3}
    assert body["diff"]["summary"]["identical"] is False


async def test_diff_reports_added_option(client, db_session, draft):
    await client.post(f"/api/v2/rule-sets/{draft}/params/G/options", json={
        "code": "g_ut_added", "label_zh": "新增", "base_tmu": 55})

    body = (await client.get(f"/api/v2/rule-sets/{draft}/diff")).json()
    added = body["diff"]["sections"]["g"]["added"]
    assert [a["key"] for a in added] == ["g_ut_added"]
    assert added[0]["after"]["base_tmu"] == 55
    assert body["diff"]["sections"]["g"]["removed"] == []


async def test_diff_reports_removed_option(client, db_session, draft):
    await client.delete(f"/api/v2/rule-sets/{draft}/params/G/options/{G_CODE}")

    body = (await client.get(f"/api/v2/rule-sets/{draft}/diff")).json()
    removed = body["diff"]["sections"]["g"]["removed"]
    assert [x["key"] for x in removed] == [G_CODE]
    assert removed[0]["before"]["base_tmu"] == G_TMU, "被刪的值要看得到，否則覆核者不知失去什麼"


async def test_diff_of_untouched_clone_has_no_value_differences(client, db_session, draft):
    """剛 clone 未改 → 12 張子表逐欄相同。這條是上面三個案例的鑑別力保證：
    若 diff 對任何輸入都吐出一堆差異，前三個測試會空洞通過。

    唯一的差異是 `name_zh`（clone 本來就會取新名字），它屬 header 而非值——
    順便鎖住「header 差異不會被誤算進子表差異」。
    """
    body = (await client.get(f"/api/v2/rule-sets/{draft}/diff")).json()
    assert body["diff"]["sections"] == {}, body["diff"]["summary"]
    assert body["diff"]["summary"]["changed_sections"] == []
    assert set(body["diff"]["header"]) == {"name_zh"}, body["diff"]["header"]


async def test_diff_404_for_unknown_code(client):
    assert (await client.get("/api/v2/rule-sets/NO_SUCH_VERSION/diff")).status_code == 404


async def test_diff_requires_analyst(client, db_session, draft):
    """RBAC 邊界：viewer 看不到（字典內容與 `GET /full` 同級）。"""
    await db_session.execute(text(
        "INSERT INTO app_users (id, employee_no, display_name, roles, site_ids, is_active) "
        "VALUES (:i, :e, :e, '{}', '{}', true)"),
        {"i": uuid.uuid4(), "e": "UT_D7_VIEWER"})
    await db_session.commit()

    r = await client.get(f"/api/v2/rule-sets/{draft}/diff",
                         headers={"X-Username": "UT_D7_VIEWER"})
    assert r.status_code == 403, r.text


# ══════════════════════════════════════════════════════════════════
# M-1：欄位級數值契約不得被 import / PUT /full 繞過
# ══════════════════════════════════════════════════════════════════


def _with_negative_g_tmu(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["g"] = [dict(r) for r in payload["g"]]
    payload["g"][0]["base_tmu"] = -50
    return payload


async def test_import_rejects_negative_base_tmu_with_field_level_detail(client, db_session):
    """負的 TMU 原本會一路綠燈：import 200 → validate_complete（不看值）→ publish → activate。"""
    export = (await client.get(f"/api/v2/rule-sets/{ACTIVE}/export")).json()
    new_code = f"UT_D7_NEG_{uuid.uuid4().hex[:6]}"

    r = await client.post("/api/v2/rule-sets/import",
                          json={**_with_negative_g_tmu(export), "new_code": new_code})
    assert r.status_code == 400, r.text
    detail = r.json()["error"]["message"]
    # 只斷言 400 會空洞通過：本端點有 6 種 400（schema_version、缺區塊、multiplier、帶界…）。
    assert "g[0]" in detail, detail
    assert "base_tmu" in detail, detail
    assert "-50" in detail, detail

    # 零寫入：不得留下半份版本。
    assert (await db_session.execute(
        select(RuleSet).where(RuleSet.code == new_code))).scalar_one_or_none() is None


async def test_put_full_rejects_negative_base_tmu_without_touching_stored_values(
    client, db_session, draft
):
    """`PUT /full` 會先 DELETE 全部子表再插入——驗證若晚一步，非法負載就能把字典刪光。"""
    before = (await client.get(f"/api/v2/rule-sets/{draft}/full")).json()

    r = await client.put(f"/api/v2/rule-sets/{draft}/full",
                         json=_with_negative_g_tmu(before))
    assert r.status_code == 400, r.text
    detail = r.json()["error"]["message"]
    assert "g[0]" in detail and "base_tmu" in detail, detail

    # 零寫入：12 張子表逐一比對，不是只看 g（DELETE 是整批的）。
    after = (await client.get(f"/api/v2/rule-sets/{draft}/full")).json()
    for section in ("a_bands", "b", "g", "p_bases", "p_addons", "m_ladder", "m_foot",
                    "m_verbs", "m_rotation", "m_hand", "x", "i"):
        assert after[section] == before[section], f"{section} 在被拒的 PUT 後改變了"

    rs_id = await _rs_id(db_session, draft)
    assert await _audits(db_session, rs_id, "update_full") == [], "被拒的寫入不得留下稽核"


async def test_put_full_rejects_negative_band_tmu(client, draft):
    """帶型的數值欄同樣有 `Field(ge=0)`，同樣原本繞得過。"""
    full = (await client.get(f"/api/v2/rule-sets/{draft}/full")).json()
    full["m_ladder"][1]["tmu"] = -7

    r = await client.put(f"/api/v2/rule-sets/{draft}/full", json=full)
    assert r.status_code == 400, r.text
    assert "m_ladder[1]" in r.json()["error"]["message"], r.json()["error"]["message"]


async def test_put_full_rejects_negative_p_addon_delta(client, draft):
    """`delta` → `delta_tmu` 有改名，最容易在對映表漏掉——負值必須照樣擋下。"""
    full = (await client.get(f"/api/v2/rule-sets/{draft}/full")).json()
    full["p_addons"][0]["delta"] = -8

    r = await client.put(f"/api/v2/rule-sets/{draft}/full", json=full)
    assert r.status_code == 400, r.text
    detail = r.json()["error"]["message"]
    assert "p_addons[0]" in detail and "delta_tmu" in detail, detail


async def test_put_full_still_accepts_a_valid_round_trip(client, draft):
    """鑑別力保證：驗證加得太嚴會讓 export→import／GET→PUT 閉環整條壞掉。"""
    full = (await client.get(f"/api/v2/rule-sets/{draft}/full")).json()
    r = await client.put(f"/api/v2/rule-sets/{draft}/full", json=full)
    assert r.status_code == 200, r.text
    assert r.json()["g"] == full["g"]
