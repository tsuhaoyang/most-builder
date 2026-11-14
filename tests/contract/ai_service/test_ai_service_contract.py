"""MOST ↔ ai_service 契約測試（ADR-037 D2；實作計畫 S2）。

不連真服務。比對對象是兩份釘住的快照：

- `openapi_structured_completion.json`：ai_service `docs/api/openapi.json` 中
  `POST /v1/llm/structured-completion` 與其三個 schema（來源 commit 記在檔內 `source`）。
- `golden/structured_completion_cases.json`：依 openapi 回應形狀組成的 golden 回應，content 取自
  ai_service pack 的 IE 核凍 few-shot（不是真服務錄製；S3 進入條件的量測時補錄）。

升級 ai_service 時：重新匯出快照 → 本檔變紅的地方就是 MOST 要跟著改的地方。

執行：`PYTHONPATH=src pytest tests/contract -q`（不與 unit／integration 合併執行）。
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fakes.ai_service_app import FakeAiService, golden_cases

from ddm_v2.ai_integration.adapter import AiServiceWiParser
from ddm_v2.ai_integration.client import CONTRACT_VERSION, ENDPOINT_PATH, AiServiceClient
from ddm_v2.ai_integration.config import MIN_KEY_LENGTH, load_config
from ddm_v2.ai_integration.ports import WiParseRequest
from ddm_v2.ai_integration.schema import SCHEMA_SHA256, schema_sha256, wi_motion_parse_schema
from ddm_v2.most_compiler.compile import allow_lists_from_rule_set
from ddm_v2.most_engine.providers import build_from_seed_v2

pytestmark = pytest.mark.contract

HERE = Path(__file__).parent
SNAPSHOT = json.loads((HERE / "openapi_structured_completion.json").read_text(encoding="utf-8"))
ALLOW = allow_lists_from_rule_set(build_from_seed_v2())
HOST = "ai-service.internal"
ENV = {
    "DDM_AI_SERVICE_ENABLED": "1",
    "DDM_AI_SERVICE_BASE_URL": f"https://{HOST}",
    "DDM_AI_SERVICE_ALLOWED_HOSTS": HOST,
    "DDM_AI_SERVICE_KEY": "k" * MIN_KEY_LENGTH,
}


def _parser(fake: FakeAiService) -> AiServiceWiParser:
    return AiServiceWiParser(
        AiServiceClient(load_config(ENV), transport=httpx.ASGITransport(app=fake.app()), resolver=lambda h, p: ["10.0.0.9"])
    )


def test_endpoint_exists_in_snapshot():
    assert ENDPOINT_PATH in SNAPSHOT["path"]
    assert "post" in SNAPSHOT["path"][ENDPOINT_PATH]


async def test_we_send_every_header_the_endpoint_declares():
    """比對的是 fake **實際收到**的 header，不是設定物件（client 少送一個要紅）。"""
    declared = {p["name"].lower() for p in SNAPSHOT["path"][ENDPOINT_PATH]["post"]["parameters"] if p["in"] == "header"}
    assert {"x-ai-service-key", "x-user-id", "x-user-role", "x-plant-code", "x-username"} <= declared
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    await _parser(fake).parse(
        [WiParseRequest(item_id="h", wi_statement="拿起DIMM", source_lang="zh")], allow_lists=ALLOW, lane="interactive"
    )
    sent = {k.lower() for k, v in fake.received[0]["headers"].items() if v}
    assert declared <= sent, f"ai_service 宣告了 MOST 沒送的 header：{sorted(declared - sent)}"


async def test_request_body_matches_the_request_schema():
    req_schema = SNAPSHOT["schemas"]["StructuredCompletionRequest"]
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    await _parser(fake).parse(
        [WiParseRequest(item_id="c", wi_statement="拿起DIMM", source_lang="zh")], allow_lists=ALLOW, lane="interactive"
    )
    body = fake.received[0]["body"]
    assert set(req_schema["required"]) <= set(body), "缺必填欄位"
    assert set(body) <= set(req_schema["properties"]), f"送了 schema 未宣告的欄位：{sorted(set(body) - set(req_schema['properties']))}"
    assert body["contract_version"] == CONTRACT_VERSION
    assert isinstance(body["deadline_ms"], int) and body["deadline_ms"] >= 0


def test_response_schema_fields_are_the_ones_the_client_reads():
    resp = SNAPSHOT["schemas"]["StructuredCompletionResponse"]
    prov = SNAPSHOT["schemas"]["ProvenanceSummary"]
    assert set(resp["required"]) == {"contract_version", "content", "provenance"}
    read_by_client = {"run_id", "bundle_code", "bundle_status", "model_requested", "model_served", "retry_count"}
    assert read_by_client <= set(prov["required"]), "client 依賴的 provenance 欄位不再是必填"


@pytest.mark.parametrize("case_id", sorted(golden_cases()))
async def test_golden_cases_parse_end_to_end(case_id: str):
    case = golden_cases()[case_id]
    resp = case["response"]
    assert set(SNAPSHOT["schemas"]["StructuredCompletionResponse"]["required"]) <= set(resp)
    prov_schema = SNAPSHOT["schemas"]["ProvenanceSummary"]
    assert set(prov_schema["required"]) <= set(resp["provenance"]), "golden provenance 缺必填欄位"
    assert set(resp["provenance"]) <= set(prov_schema["properties"]), "golden provenance 有 schema 未宣告的欄位"
    fake = FakeAiService(script=[f"ok:{case_id}"])
    (res,) = await _parser(fake).parse(
        [WiParseRequest(item_id=case_id, wi_statement=case["input"]["wi_statement"], source_lang=case["input"]["source_lang"])],
        allow_lists=ALLOW,
        lane="interactive",
    )
    assert res.status == "ok", res
    assert len(res.motions) == len(resp["content"]["motions"])
    for m in res.motions:
        assert not any(i.startswith("unknown_code") for i in m.issues), (case_id, m.issues)


def test_vendored_schema_hash_is_pinned():
    assert schema_sha256() == SCHEMA_SHA256
    assert wi_motion_parse_schema()["$id"] == "wi-motion-parse.schema.json"


def test_schema_code_enums_match_the_seed_rule_set():
    """漂移偵測：ai_service bundle 內的 code 清單是 MOST rule-set 的複本，不會自動同步。

    任一邊增刪 code 這裡就紅——MOST rule-set 改版後要請 ai_service 發新 bundle（計畫 §7 第 2 項）。
    """
    d = wi_motion_parse_schema()["$defs"]
    pairs = {
        "B": d["b_code"]["enum"],
        "G": d["g_code"]["enum"],
        "M": d["m_code"]["enum"],
        "X": d["x_code"]["enum"],
        "I": d["i_code"]["enum"],
        "P": d["p_slot"]["properties"]["base"]["enum"],
        "P_ADDON": d["p_slot"]["properties"]["addon"]["items"]["enum"],
    }
    for family, codes in pairs.items():
        assert set(codes) == set(ALLOW[family]), (family, sorted(set(codes) ^ set(ALLOW[family])))
