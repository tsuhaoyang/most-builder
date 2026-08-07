"""NLP synonyms + nl-draft 端點整合測試（impl-05）。

涵蓋：
- synonyms CRUD：list(200) / create IE(201) / duplicate(409+SYNONYM_CONFLICT) /
  viewer 403 / delete(204)
- nl-draft：POST → 200，回傳 normalized_text + slots（7 個）+ F-05 GM 判型驗收

對應規格：
    NL draft 驗收：ADR-015 與 docs/architecture/wi-ai-parser-system-spec.md
    同義詞治理驗收：ADR-015、ADR-023 與 API 契約
"""
from __future__ import annotations

import os
import uuid

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration


async def _get_rs_code(client) -> str:
    """取第一個可用的 rule_set code；無 rule_set 則 skip。"""
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set，略過")
    return r.json()[0]["code"]


# ── synonyms ──────────────────────────────────────────────────────────────────


async def test_list_synonyms_empty_returns_200(client):
    """GET /rule-sets/{code}/synonyms → 200 list（viewer 可讀）。

    F-06 §4：「讀 user／寫 approver/admin」。
    """
    code = await _get_rs_code(client)
    r = await client.get(f"/api/v2/rule-sets/{code}/synonyms")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


async def test_create_synonym_analyst_role(client):
    """POST synonyms（analyst role）→ 201；回傳含 id / parameter / synonym_norm。

    F-06 §4：「增同義詞…200 且 nl-draft 立即可命中」（此處驗 201 建立）。
    """
    code = await _get_rs_code(client)
    sfx = uuid.uuid4().hex[:8]
    payload = {
        "parameter": "G",
        "option_code": "g_grasp",
        "synonym_raw": f"測試拿取{sfx}",
        "priority": 0,
    }
    r = await client.post(f"/api/v2/rule-sets/{code}/synonyms", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "id" in body
    assert body["parameter"] == "G"
    assert body["option_code"] == "g_grasp"
    assert "synonym_norm" in body


async def test_create_synonym_duplicate_returns_409(client):
    """重複 POST 同 rule-set/parameter/synonym_norm → 409 + SYNONYM_CONFLICT。

    F-06 §4：「增同義詞與既有同參數映射衝突，Then 409＋回傳既有映射」。
    """
    code = await _get_rs_code(client)
    sfx = uuid.uuid4().hex[:8]
    payload = {
        "parameter": "A",
        "option_code": "a_reach",
        "synonym_raw": f"伸手重複{sfx}",
        "priority": 0,
    }
    # 第一次：201
    first = await client.post(f"/api/v2/rule-sets/{code}/synonyms", json=payload)
    assert first.status_code == 201, first.text

    # 第二次（相同 synonym_raw → normalize 後產生相同 synonym_norm）：409
    second = await client.post(f"/api/v2/rule-sets/{code}/synonyms", json=payload)
    assert second.status_code == 409, second.text
    body = second.json()
    assert "detail" in body
    assert body["detail"]["code"] == "SYNONYM_CONFLICT"
    assert "existing" in body["detail"]


async def test_create_synonym_non_ie_returns_403(client):
    """viewer 角色 POST synonyms → 403（需 IE+）。

    F-06 §3：「讀 user／寫 approver/admin」。
    """
    code = await _get_rs_code(client)
    sfx = uuid.uuid4().hex[:8]
    payload = {
        "parameter": "G",
        "option_code": "g_grasp",
        "synonym_raw": f"viewer測試{sfx}",
        "priority": 0,
    }
    h = {"X-Username": "ZZZMMVIEWER999"}
    r = await client.post(f"/api/v2/rule-sets/{code}/synonyms", json=payload, headers=h)
    assert r.status_code == 403, r.text


async def test_create_synonym_invalid_option_code_returns_422(client):
    """非 A 參數的 option_code 不存在於子表 → 422 OPTION_CODE_NOT_FOUND。

    Fix-T1（H2 回歸）：
      F-06 §3 Fix-C1：B/G/P/M/X/I 各有離散 option code 子表；
      不存在的 code 應在應用層 FK 驗證時被攔截。
    """
    code = await _get_rs_code(client)
    resp = await client.post(
        f"/api/v2/rule-sets/{code}/synonyms",
        json={
            "parameter": "G",
            "option_code": "NONEXISTENT_CODE_XYZ",
            "synonym_raw": "測試無效選項",
            "priority": 0,
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "OPTION_CODE_NOT_FOUND"


async def test_create_synonym_empty_after_normalize_returns_422(client):
    """全形空白 synonym_raw 正規化後為空 → 422 VALIDATION_ERROR。

    Fix-T3：
      全形空白（U+3000）NFKC → 普通空白 → strip 後為空字串；
      服務層 Fix-L2 guard 捕捉並 raise ValueError → route → 422。
      注意：Pydantic min_length=1 以字元數計（兩個 U+3000 = 長度 2，可繞過），
      實際由服務層 normalize 後空值檢查攔截。
    """
    code = await _get_rs_code(client)
    resp = await client.post(
        f"/api/v2/rule-sets/{code}/synonyms",
        json={
            "parameter": "G",
            "option_code": "g_grasp",
            "synonym_raw": "　　",  # 兩個全形空白 U+3000（bypass Pydantic min_length）
            "priority": 0,
        },
    )
    # 422 from service ValueError（Fix-L2：synonym_norm 正規化後不得為空）
    assert resp.status_code == 422, resp.text


async def test_delete_synonym_analyst_role(client):
    """建立同義詞後 DELETE → 204；GET list 確認已移除。

    F-06 §3：DELETE /api/v2/rule-sets/{code}/synonyms/{syn_id}（IE+）。
    """
    code = await _get_rs_code(client)
    sfx = uuid.uuid4().hex[:8]
    payload = {
        "parameter": "P",
        "option_code": "p_place_none",
        "synonym_raw": f"放置刪除{sfx}",
        "priority": 0,
    }
    # 建立
    cr = await client.post(f"/api/v2/rule-sets/{code}/synonyms", json=payload)
    assert cr.status_code == 201, cr.text
    syn_id = cr.json()["id"]

    # 刪除
    dr = await client.delete(f"/api/v2/rule-sets/{code}/synonyms/{syn_id}")
    assert dr.status_code == 204, dr.text

    # 確認已從 list 移除
    lst = await client.get(f"/api/v2/rule-sets/{code}/synonyms")
    assert lst.status_code == 200
    ids = [s["id"] for s in lst.json()]
    assert syn_id not in ids


# ── nl-draft ──────────────────────────────────────────────────────────────────


async def test_nl_draft_basic(client):
    """POST /worksheets/nl-draft → 200；normalized_text 非空 + slots 7 個 + GM 判型。

    F-05 §4 驗收條目 1：
      Given「雙手抓握主板放到DIMM壓合治具」，
      Then 建議 GM（治具防護）且 normalized_text 存在。
    F-05 §4 驗收條目 3（正規化等價）的介面層確認（不跑全值，單元層已涵蓋）。
    L0：加法欄位 ai.* / multi_action_warning 必須存在且不破壞舊欄位。
    """
    code = await _get_rs_code(client)
    payload = {
        "text": "雙手抓握主板放到DIMM壓合治具",
        "rule_set_code": code,
    }
    r = await client.post("/api/v2/worksheets/nl-draft", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    # 介面完整性
    assert "normalized_text" in body
    assert body["normalized_text"] != ""
    assert "slots" in body
    assert len(body["slots"]) == 7  # GM 序列固定 7 slots（A B G A B P A）
    assert "overall_confidence" in body
    assert "provenance" in body

    # F-05 §4 條目 1：治具防護 → 建議 GM
    assert body["suggested_seq"] == "GM"

    # L0 加法欄位
    assert "ai" in body
    assert body["ai"]["run_id"]
    assert body["ai"]["plan"]["schema_version"] == "wi-plan-v1"
    assert body["ai"]["routing_status"] in {"review", "abstain", "invalid", "auto"}
    assert body["multi_action_warning"] is False


async def test_nl_draft_idempotent_reuses_run(client, db_session):
    """相同輸入兩次 → 第二次 provenance.cached=true 且 run_id 相同；DB 僅一列且 error IS NULL。"""
    from sqlalchemy import func, select

    from ddm_v2.models.v2.ai_ops import AiParseRun

    code = await _get_rs_code(client)
    payload = {
        "text": f"冪等測試治具{uuid.uuid4().hex[:8]}",
        "rule_set_code": code,
    }
    first = await client.post("/api/v2/worksheets/nl-draft", json=payload)
    assert first.status_code == 200, first.text
    body1 = first.json()
    run1 = body1["ai"]["run_id"]

    second = await client.post("/api/v2/worksheets/nl-draft", json=payload)
    assert second.status_code == 200, second.text
    body2 = second.json()
    assert body2["ai"]["run_id"] == run1
    assert body2["ai"]["provenance"]["cached"] is True

    run_row = await db_session.get(AiParseRun, uuid.UUID(run1))
    assert run_row is not None
    assert run_row.error is None
    total_same_hash = await db_session.scalar(
        select(func.count())
        .select_from(AiParseRun)
        .where(
            AiParseRun.input_hash == run_row.input_hash,
            AiParseRun.bundle_id == run_row.bundle_id,
        )
    )
    assert total_same_hash == 1
