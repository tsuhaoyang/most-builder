"""ADR-023 D7b：import 稽核錨點、is_active 型別脅迫、diff 血緣揭露。

複驗 D7 後新發現的三項：

- **M-2**：`import_draft` 的稽核 payload 只有 `{code, source_code, provenance}`——
  無值、無 digest、無列數。而 import 是**系統外部撰寫的值進入系統的唯一入口**
  （clone 的來源在庫內、delete 有全量快照，唯獨 import 的來源是一份離線 JSON，
  系統裡沒有副本）。事後問「這份 draft 匯入當下是什麼值」無錨點可驗證。
- **L-1**：`bool(src.get("is_active", True))` → `bool("false") is True`。離線編輯／
  CSV 轉出的 JSON 常把布林寫成字串，`"false"` 會被靜默翻成**啟用**，直接改變引擎
  讀得到的選項集合。這正落在硬規則「不得為了避免例外而脅迫型別」上。
- **L-3**：若 draft 是從**非 active** 版本 clone 出來的，`GET /diff` 會把「兩條血緣的
  既有落差」與「作者這次的編輯」混在一起，覆核者可能誤讀成全部都是本次改動。

⚠️ 一律對拋棄式版本動手，**不得**改 V1/V2（回放基準）。
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from ddm_v2.models.v2.rule_set import RuleSet

pytestmark = pytest.mark.integration

ACTIVE = "MINIMOST_FACTORY_V2"


async def _seeded(db_session) -> bool:
    return (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == ACTIVE))).first() is not None


@pytest_asyncio.fixture
async def exported(client, db_session) -> dict:
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    r = await client.get(f"/api/v2/rule-sets/{ACTIVE}/export")
    assert r.status_code == 200, r.text
    return r.json()


def _new_code(tag: str) -> str:
    return f"UT_D7B_{tag}_{uuid.uuid4().hex[:6]}"


async def _audit(db_session, code: str, action: str) -> dict[str, Any]:
    rs_id = (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == code))).scalar_one()
    rows = (await db_session.execute(text(
        "SELECT payload FROM workflow_audit_log WHERE entity_type='rule_set' "
        "AND entity_id=:i AND action=:a ORDER BY created_at"
    ), {"i": rs_id, "a": action})).all()
    assert len(rows) == 1, f"action={action} 應恰好一筆稽核，收到 {len(rows)}"
    return rows[0][0]


async def _import(client, payload: dict, code: str, name_zh: str | None = None):
    body = {**payload, "new_code": code}  # import 需要完整負載（含 schema_version）
    if name_zh is not None:
        body["name_zh"] = name_zh
    return await client.post("/api/v2/rule-sets/import", json=body)


# ══════════════════════════════════════════════════════════════════
# M-2：import 的稽核必須留下值的錨點
# ══════════════════════════════════════════════════════════════════
async def test_import_audit_records_digest_and_row_counts(client, db_session, exported):
    code = _new_code("IMP")
    r = await _import(client, exported, code)
    assert r.status_code == 200, r.text

    payload = await _audit(db_session, code, "import")
    assert payload["snapshot_sha256"], "import 必須釘住「匯入當下是什麼值」"
    assert len(payload["snapshot_sha256"]) == 64  # sha256 hex

    # 列數不能是空殼：必須是這份負載真正的列數，否則 digest 對不上時無從定位差在哪個區塊。
    counts = payload["row_counts"]
    assert len(counts) == 12, f"12 個區塊都要有列數，收到 {sorted(counts)}"
    for section, n in counts.items():
        assert n == len(exported[section]), f"{section} 列數 {n} != 負載的 {len(exported[section])}"
    assert counts["g"] > 0, "前置：本測試比對的是有內容的負載（否則全 0 也會通過）"


async def test_import_digest_matches_clone_digest_for_same_content(client, db_session, exported):
    """同一份內容經 import 與 clone 兩條路徑必須得到**相同** digest。

    這是本項的重點：digest 若兩邊各算各的（不同欄位集／不同序列化），事後根本無法
    用它比對「這份 draft 跟當初那一版是不是同樣的值」——那 digest 就只是裝飾。
    """
    imported_code = _new_code("DGI")
    cloned_code = _new_code("DGC")

    # import 時把 name_zh 對齊來源：digest 涵蓋表頭（name_zh/multiplier），
    # 改名本來就該讓 digest 改變，這裡要比的是「值」。
    r = await _import(client, exported, imported_code, name_zh=exported["name_zh"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v2/rule-sets/{ACTIVE}/clone-draft",
                          json={"new_code": cloned_code, "name_zh": exported["name_zh"]})
    assert r.status_code == 200, r.text

    import_digest = (await _audit(db_session, imported_code, "import"))["snapshot_sha256"]
    clone_digest = (await _audit(db_session, cloned_code, "clone_draft"))["snapshot_sha256"]
    assert import_digest == clone_digest


async def test_import_digest_changes_when_a_value_changes(client, db_session, exported):
    """反例：改一個 TMU，digest 必須不同——否則它偵測不到任何竄改。"""
    baseline_code = _new_code("DGA")
    tampered_code = _new_code("DGB")
    r = await _import(client, exported, baseline_code, name_zh=exported["name_zh"])
    assert r.status_code == 200, r.text

    tampered = {**exported, "g": [dict(row) for row in exported["g"]]}
    tampered["g"][0] = {**tampered["g"][0], "base_tmu": tampered["g"][0]["base_tmu"] + 1}
    r = await _import(client, tampered, tampered_code, name_zh=exported["name_zh"])
    assert r.status_code == 200, r.text

    a = (await _audit(db_session, baseline_code, "import"))["snapshot_sha256"]
    b = (await _audit(db_session, tampered_code, "import"))["snapshot_sha256"]
    assert a != b


# ══════════════════════════════════════════════════════════════════
# L-1：is_active 不得被 bool() 脅迫
# ══════════════════════════════════════════════════════════════════
async def _b_option(client, code: str, option_code: str) -> dict[str, Any]:
    r = await client.get(f"/api/v2/rule-sets/{code}/params/B/options")
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["code"] == option_code)


@pytest.mark.parametrize("raw,expected", [("false", False), ("true", True), (False, False)])
async def test_import_is_active_string_is_parsed_not_coerced(
    client, db_session, exported, raw, expected
):
    """`"false"` 必須落成停用。`bool("false") is True` → 舊實作會靜默把它啟用。"""
    code = _new_code("ACT")
    target = exported["b"][0]["code"]
    payload = {**exported, "b": [
        {**row, "is_active": raw} if row["code"] == target else row
        for row in exported["b"]
    ]}
    r = await _import(client, payload, code)
    assert r.status_code == 200, r.text
    assert (await _b_option(client, code, target))["is_active"] is expected


async def test_import_is_active_null_still_means_disabled(client, db_session, exported):
    """既有語意保留：明寫 null → False（不得被「None 就吃 schema 預設 True」蓋掉）。"""
    code = _new_code("ACN")
    target = exported["b"][0]["code"]
    payload = {**exported, "b": [
        {**row, "is_active": None} if row["code"] == target else row
        for row in exported["b"]
    ]}
    r = await _import(client, payload, code)
    assert r.status_code == 200, r.text
    assert (await _b_option(client, code, target))["is_active"] is False


async def test_import_is_active_garbage_is_rejected_not_guessed(client, db_session, exported):
    """無法解讀的值要 400，不得猜成 True（那正是被禁止的型別脅迫）。"""
    code = _new_code("ACX")
    payload = {**exported, "b": [
        {**row, "is_active": "maybe"} if row["code"] == exported["b"][0]["code"] else row
        for row in exported["b"]
    ]}
    r = await _import(client, payload, code)
    assert r.status_code == 400, r.text
    assert "is_active" in r.text
    # 擋回應不擋落盤＝gate 失效：確認沒有半成品版本留下。
    assert (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == code))).first() is None


# ══════════════════════════════════════════════════════════════════
# L-3：diff 必須揭露血緣
# ══════════════════════════════════════════════════════════════════
async def test_diff_reports_source_when_cloned_from_active(client, db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    code = _new_code("LIN1")
    r = await client.post(f"/api/v2/rule-sets/{ACTIVE}/clone-draft",
                          json={"new_code": code, "name_zh": "血緣測試"})
    assert r.status_code == 200, r.text

    body = (await client.get(f"/api/v2/rule-sets/{code}/diff")).json()
    assert body["source_code"] == ACTIVE
    assert body["base_is_source"] is True
    assert "lineage_note" not in body, "來源就是基準時不該有雜訊提示"


async def test_diff_flags_when_base_is_not_the_clone_source(client, db_session):
    """從**非 active** 版本 clone 出來 → 必須明說 diff 混了兩條血緣的落差。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    mid = _new_code("LIN2A")
    leaf = _new_code("LIN2B")
    assert (await client.post(f"/api/v2/rule-sets/{ACTIVE}/clone-draft",
                              json={"new_code": mid, "name_zh": "中繼"})).status_code == 200
    assert (await client.post(f"/api/v2/rule-sets/{mid}/clone-draft",
                              json={"new_code": leaf, "name_zh": "葉"})).status_code == 200

    body = (await client.get(f"/api/v2/rule-sets/{leaf}/diff")).json()
    assert body["base_code"] == ACTIVE          # 基準仍是 active（不改既有語意）
    assert body["source_code"] == mid
    assert body["base_is_source"] is False
    assert mid in body["lineage_note"] and ACTIVE in body["lineage_note"]


async def test_diff_says_unknown_source_instead_of_guessing(client, db_session, exported):
    """匯入建立的 draft 沒有 clone 紀錄 → `None`，不得猜成「來源＝active」。"""
    code = _new_code("LIN3")
    assert (await _import(client, exported, code)).status_code == 200

    body = (await client.get(f"/api/v2/rule-sets/{code}/diff")).json()
    assert body["source_code"] is None
    assert body["base_is_source"] is None
    assert "lineage_note" not in body
