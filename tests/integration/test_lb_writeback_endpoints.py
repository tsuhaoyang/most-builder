"""B5/B6（ADR-036）：LB 回寫端點整合測試。

import → latest → apply-offline（含組內傳染與 rollback）；未設 base URL → 503；契約不符 → 422；
LB 不可達 → 502；retention 只留 10。需 DB。

wi_rows.id 為全域 PK，不能用 fixture 的固定 id（跨 case 會撞 PK）。改為：建 worksheet 用隨機 id，
再把 fixture payload 的 source_wi_row_id 重映到本 worksheet 的實際 id（保留 fixture 的 offline/units 等情境）。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"
FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "writeback_sample.json"
GM = {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1", "a0": {"reach_cm": 20},
      "g2": {"g_code": "g_grasp"}, "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


def _row(seq_no: int, wi_id: str, level: dict) -> dict:
    base = {"ascription": "main", "level": "1"}
    base.update(level)
    return {"id": wi_id, "seq_no": seq_no, "hand": "RH", "object_vocab_id": OBJ, "frequency": 1,
            "narrative": f"row{seq_no}", "cycle": GM, "level": base}


async def _make_worksheet(client) -> tuple[str, dict, dict]:
    """建 3 列 worksheet（隨機 id）：seq1+seq2 同 cub10（傳染，order2 不帶 main/level 避 R2）、seq3 loose。
    回 (worksheet_id, id_by_role, remapped_payload)。remapped：把 fixture 前 3 個 source_wi_row_id
    映到本 worksheet 的 (cub-order1, cub-order2, loose)，其中 loose 對 fixture 的 offline 列（offline=True）。"""
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    cub1, cub2, loose = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    rows = [
        _row(1, cub1, {"countersignature": "cub10", "order": 1}),
        _row(2, cub2, {"ascription": None, "level": None, "countersignature": "cub10", "order": 2}),
        _row(3, loose, {"level": "2"}),
    ]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": rows})
    assert r.status_code == 200, r.text

    # 重映 fixture：挑一個 offline=True 的列給 loose、兩個非 offline 給 cub1/cub2，其餘略去 source（→unmatched 不計）
    # 挑列用**語意條件**而非檔案順序：vendor 換版時 34 列的順序會變（2026-09-21 的 106bf14 就重排過），
    # 依順序挑會讓測到的情境悄悄換掉（單列 motion ↔ 工具三列之一）而測試照樣綠。
    fx = _fixture()
    off_row = next(x for x in fx["rows"] if x["offline_flag"])
    single_ids = {i for i in {x["source_wi_row_id"] for x in fx["rows"]}
                  if sum(1 for y in fx["rows"] if y["source_wi_row_id"] == i) == 1}
    non_off = [x for x in fx["rows"]
               if not x["offline_flag"] and x["source_wi_row_id"] in single_ids][:2]
    assert len(non_off) == 2, "fixture 應有至少兩個非 offline 的單列 motion"
    off_row["source_wi_row_id"] = loose
    non_off[0]["source_wi_row_id"] = cub1
    non_off[1]["source_wi_row_id"] = cub2
    return new, {"cub1": cub1, "cub2": cub2, "loose": loose}, fx


async def test_import_latest_and_snapshots(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["contract_version"] == "lb-most-writeback-v1"
    assert body["summary"]["rows_in"] == 34

    latest = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")
    assert latest.status_code == 200
    # 只重映單列 motion（見 _make_worksheet），不會把工具三列拆開 → motions 恆為 24
    assert latest.json()["summary"]["motions"] == 24

    snaps = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/snapshots")
    assert len(snaps.json()["snapshots"]) == 1


async def test_import_contract_mismatch_422(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    fx["contract_version"] = "lb-most-writeback-v2"
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "LB_WRITEBACK_CONTRACT_MISMATCH"


async def test_apply_offline_propagates_within_cub(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    imp = (await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)).json()
    offdiffs = {od["wi_row_id"] for od in imp["diff"]["offline_diffs"]}
    assert ids["loose"] in offdiffs, imp["diff"]["offline_diffs"]

    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/apply-offline",
                          json={"snapshot_id": imp["snapshot_id"], "wi_row_ids": [ids["loose"]]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert ids["loose"] in body["applied"]
    assert body["report"]["errors"] == []

    read = (await client.get(f"/api/v2/worksheets/{ws}")).json()
    row = next(x for x in read["rows"] if x["wi_row_id"] == ids["loose"])
    assert row["lb_tags"]["offline"] is True
    latest = (await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")).json()
    assert latest["applied_at"] is not None


async def test_apply_offline_rejects_row_not_in_diffs(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    imp = (await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)).json()
    # cub1 MOST/LB offline 一致（都 False）→ 不在 offline_diffs → 422
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/apply-offline",
                          json={"snapshot_id": imp["snapshot_id"], "wi_row_ids": [ids["cub1"]]})
    assert r.status_code == 422


async def test_apply_offline_rollback_on_projection_error_no_partial_apply(client):
    """B6 核心保證：套用後任一 E（此處用離散 level 觸發投影 E_LEVEL_INVALID/DISCRETE）→ 整批 rollback，
    一列都不套（level_entries.offline 全未變）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    loose = str(uuid.uuid4())
    # 離散 level "1/2"（a/b 跳號）→ 投影 E_LEVEL_DISCRETE_UNSUPPORTED / E_LEVEL_INVALID
    rows = [_row(1, loose, {"level": "1/2"})]
    assert (await client.put(f"/api/v2/worksheets/{new}", json={"rows": rows})).status_code == 200
    fx = _fixture()
    off_row = next(x for x in fx["rows"] if x["offline_flag"])
    off_row["source_wi_row_id"] = loose
    imp = (await client.post(f"/api/v2/worksheets/{new}/lb-writeback/import", json=fx)).json()
    if loose not in {od["wi_row_id"] for od in imp["diff"]["offline_diffs"]}:
        pytest.skip("此環境未產生 offline_diff（離散 level 可能先擋 diff）")
    r = await client.post(f"/api/v2/worksheets/{new}/lb-writeback/apply-offline",
                          json={"snapshot_id": imp["snapshot_id"], "wi_row_ids": [loose]})
    assert r.status_code == 422, r.text
    # 一列都不套：offline 仍為 False
    read = (await client.get(f"/api/v2/worksheets/{new}")).json()
    row = next(x for x in read["rows"] if x["wi_row_id"] == loose)
    assert row["lb_tags"]["offline"] is False


async def test_fetch_not_configured_503(client, monkeypatch):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    monkeypatch.delenv("DDM_LB_API_BASE_URL", raising=False)
    from ddm_v2.settings import get_settings
    get_settings.cache_clear()
    ws, ids, fx = await _make_worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/fetch",
                          json={"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "LB_NOT_CONFIGURED"
    get_settings.cache_clear()


async def test_fetch_lb_unreachable_502(client, monkeypatch):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    monkeypatch.setenv("DDM_LB_API_BASE_URL", "http://127.0.0.1:1")  # 連線立即被拒
    from ddm_v2.settings import get_settings
    get_settings.cache_clear()
    ws, ids, fx = await _make_worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/fetch",
                          json={"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R"})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "LB_UNREACHABLE"
    get_settings.cache_clear()


async def test_fetch_lb_timeout_504(client, monkeypatch):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Slow(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            time.sleep(1.0)  # 慢於 DDM_LB_TIMEOUT_S=0.2 → 逾時
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("DDM_LB_API_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
        monkeypatch.setenv("DDM_LB_TIMEOUT_S", "0.2")
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()
        ws, ids, fx = await _make_worksheet(client)
        r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/fetch",
                              json={"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R"})
        assert r.status_code == 504, r.text
        assert r.json()["error"]["code"] == "LB_TIMEOUT"
    finally:
        server.shutdown()
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()


async def test_fetch_lb_auth_required_502(client, monkeypatch):
    """LB 需三個身分 header，未設 DDM_LB_AUTH_HEADERS → LB 回 401 → 502 LB_AUTH_REQUIRED，訊息可辨識。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Auth(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            need = ("X-User-Id", "X-Plant-Code", "X-Username")
            ok = all(self.headers.get(h) for h in need)
            body = (json.dumps({"contract_version": "lb-most-writeback-v1", "rows": []})
                    if ok else json.dumps({"detail": "missing gateway headers"})).encode()
            self.send_response(200 if ok else 401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Auth)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("DDM_LB_API_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
        monkeypatch.delenv("DDM_LB_AUTH_HEADERS", raising=False)
        monkeypatch.delenv("DDM_LB_AUTH_HEADER_NAME", raising=False)
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()
        ws, ids, fx = await _make_worksheet(client)
        r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/fetch",
                              json={"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R"})
        assert r.status_code == 502, r.text
        assert r.json()["error"]["code"] == "LB_AUTH_REQUIRED"
        assert "DDM_LB_AUTH_HEADERS" in r.json()["error"]["message"]
    finally:
        server.shutdown()
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()


async def test_fetch_full_headers_reaches_lb(client, monkeypatch):
    """設 DDM_LB_AUTH_HEADERS 三個 header → LB 收到全部 → 200（此處 stub 回空 rows，驗管路通）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    seen = {}

    class _Auth(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            for h in ("X-User-Id", "X-Plant-Code", "X-Username"):
                seen[h] = self.headers.get(h)
            ok = all(seen.get(h) for h in ("X-User-Id", "X-Plant-Code", "X-Username"))
            body = json.dumps({"contract_version": "lb-most-writeback-v1", "project_id": "P",
                               "version_id": "V", "result_id": "R", "unattended_machine_policy": "free",
                               "unattended_machine_policy_source": "persisted", "rows": []}).encode()
            self.send_response(200 if ok else 401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Auth)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("DDM_LB_API_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
        monkeypatch.setenv("DDM_LB_AUTH_HEADERS", "X-User-Id=devuser,X-Plant-Code=WBTEST,X-Username=@me")
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()
        ws, ids, fx = await _make_worksheet(client)
        r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/fetch",
                              json={"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R"})
        assert r.status_code == 200, r.text
        # 三個 header 都送達；@me 解析為當前使用者員編（IEC141289）
        assert seen["X-User-Id"] == "devuser"
        assert seen["X-Plant-Code"] == "WBTEST"
        assert seen["X-Username"] == "IEC141289"
    finally:
        server.shutdown()
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()


async def test_retention_keeps_10(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    from ddm_v2.services.v2 import lb_writeback_service as wb
    ws, ids, fx = await _make_worksheet(client)
    for _ in range(12):
        r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
        assert r.status_code == 200
    snaps = (await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/snapshots")).json()["snapshots"]
    assert len(snaps) == wb.RETENTION_PER_WORKSHEET == 10


@pytest.mark.parametrize("field", ["lb_project_id", "lb_version_id", "lb_result_id"])
@pytest.mark.parametrize("value", ["x/../../../admin/users?", "../admin", "a/b", "a%2Fb", "a b", "abc\n", "a" * 65])
async def test_fetch_rejects_unsafe_lb_ids_422(client, monkeypatch, field, value):
    """安全修正：座標直接成為 LB URL 路徑段 → 格式不合回 422（ADR-034 信封），且 LB 完全沒收到請求。"""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    hits: list[str] = []

    class _Rec(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Rec)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("DDM_LB_API_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()
        body = {"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R", field: value}
        r = await client.post(f"/api/v2/worksheets/{WS}/lb-writeback/fetch", json=body)
        assert r.status_code == 422, r.text
        err = r.json()["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert [e["loc"][-1] for e in err["detail"]["errors"]] == [field]
        assert hits == []
    finally:
        server.shutdown()
        from ddm_v2.settings import get_settings
        get_settings.cache_clear()


@pytest.mark.parametrize("body", [
    {"snapshot_id": "not-a-uuid", "wi_row_ids": ["cb43da21-98fd-4fad-a799-148eea42b778"]},
    {"snapshot_id": "cb43da21-98fd-4fad-a799-148eea42b778", "wi_row_ids": ["nope"]},
    {"snapshot_id": "cb43da21-98fd-4fad-a799-148eea42b778", "wi_row_ids": []},
])
async def test_apply_offline_non_uuid_is_422(client, body):
    """非 UUID／空清單 → 422 信封（原本在 route 內 uuid.UUID() 轉換，會落成無信封 500）。"""
    r = await client.post(f"/api/v2/worksheets/{WS}/lb-writeback/apply-offline", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_apply_offline_accepts_non_canonical_uuid(client):
    """32 位無連字號的 id 可被 uuid.UUID 解析 → 放行並正規化（ADR-036 D7 追記第 3 點同判準）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    imp = (await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)).json()
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/apply-offline", json={
        "snapshot_id": imp["snapshot_id"].replace("-", ""),
        "wi_row_ids": [ids["loose"].replace("-", "")],
    })
    assert r.status_code == 200, r.text
    assert ids["loose"] in r.json()["applied"]
    assert r.json()["report"]["status"] == "ok"


# ── RBAC（ADR-019）：寫 IE+、讀 viewer+ ────────────────────────────────
# 用「從未出現過的員編」讓 current_user JIT 出 roles=[] 的 viewer（沿用 test_i18n_review_mutations 的作法）；
# JIT 建出來的 app_users 列在 conftest 的外層交易裡會被 rollback，不污染共用 dev DB。
def _viewer_headers() -> dict[str, str]:
    return {"X-Username": f"wbviewer_{uuid.uuid4().hex[:6]}"}


@pytest.mark.parametrize("suffix,body", [
    ("fetch", {"lb_project_id": "p" * 32, "lb_version_id": "original", "lb_result_id": str(uuid.uuid4())}),
    ("import", {"contract_version": "lb-most-writeback-v1"}),
    ("apply-offline", {"snapshot_id": str(uuid.uuid4()), "wi_row_ids": [str(uuid.uuid4())]}),
])
async def test_writeback_writes_require_analyst(client, suffix, body):
    """viewer 打三支寫入端點 → 403。require_role 是 sub-dependency，在 body／DB 查詢之前就擋下，
    所以不必先建 worksheet；用隨機 worksheet_id 即可。"""
    ws = str(uuid.uuid4())
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/{suffix}", json=body, headers=_viewer_headers())
    assert r.status_code == 403, f"{suffix}: {r.status_code} {r.text}"


@pytest.mark.parametrize("suffix", ["latest", "snapshots"])
async def test_writeback_reads_allow_viewer(client, suffix):
    """viewer 讀 latest／snapshots 不得 403（ADR-019 Option A：讀對已登入者全開）。"""
    ws = str(uuid.uuid4())
    r = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/{suffix}", headers=_viewer_headers())
    assert r.status_code != 403, f"{suffix}: {r.text}"


# ── export_warnings（LB §8；bb0d340 起）：走 import 端點的完整產品路徑 ────────────

def _ew(**kw) -> dict:
    return {"units_degraded": [], "dropped_rows": [], "truncated": False, **kw}


# 每個情境各用一份工序表：同一份內連續 import 兩次時，兩筆快照的 fetched_at 相同（server_default=now()
# 是交易開始時間，而整合測試跑在同一個外層交易裡），latest 只按 fetched_at 排序、沒有 tiebreaker，
# 會隨機挑到任一筆（BL-ENG-11）。整合測試的外層交易會 rollback，多建幾份不留殘留。
async def _import(client, ws: str, fx: dict):
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
    latest = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")
    return r, latest


async def test_export_warnings_normal_empty_and_absent(client):
    """正常無警告：三個欄都在且為空。舊 LB（fixture 106bf14 不帶此欄）→ present=false，三欄 null（＝不知道）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, _ids, fx = await _make_worksheet(client)
    r, latest = await _import(client, ws, fx)
    assert r.status_code == 200, r.text
    absent = {"present": False, "units_degraded": None, "dropped_rows": None, "truncated": None, "limit": 50}
    assert r.json()["diff"]["export_warnings"] == absent
    assert latest.json()["diff"]["export_warnings"] == absent

    ws, _ids, fx = await _make_worksheet(client)
    fx["export_warnings"] = _ew()
    r, latest = await _import(client, ws, fx)
    assert r.status_code == 200, r.text
    want = {"present": True, "units_degraded": [], "dropped_rows": [], "truncated": False, "limit": 50,
            "unattached_units_degraded": 0}
    assert r.json()["diff"]["export_warnings"] == want
    assert latest.json()["diff"]["export_warnings"] == want


@pytest.mark.parametrize("reason, units_sum", [("conservation", 7), ("setup_not_one", 2)])
async def test_export_warnings_units_degraded_attaches_to_motion(client, reason, units_sum):
    """units_degraded 掛到正確的 motion 上——LB 送的是**非正規拼法**（無連字號），MOST 要正規化後才對得上。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    fx["export_warnings"] = _ew(units_degraded=[{
        "task_id": 9001, "source_wi_row_id": ids["cub1"].replace("-", "").upper(),
        "units_sum": units_sum, "quantity": 8, "reason": reason}])
    r, latest = await _import(client, ws, fx)
    assert r.status_code == 200, r.text
    for body in (r.json(), latest.json()):
        assert body["diff"]["motions"][ids["cub1"]]["units_degraded"] == [
            {"task_id": 9001, "units_sum": units_sum, "quantity": 8, "reason": reason}]
        assert body["diff"]["motions"][ids["cub2"]]["units_degraded"] == []
        assert body["diff"]["export_warnings"]["units_degraded"][0]["source_wi_row_id"] == ids["cub1"]


async def test_export_warnings_dropped_rows_change_missing_attribution(client):
    """丟列存在時，MOST 缺的那一步加上「可能是 LB 丟掉的」旗標；reason（原本的歸因）不改。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    fx["rows"] = [x for x in fx["rows"] if x["source_wi_row_id"] != ids["cub2"]]  # cub2 在 LB 那邊不見了
    r, _ = await _import(client, ws, fx)
    assert {"wi_row_id": ids["cub2"], "reason": "no_result"} in r.json()["diff"]["missing"]  # 沒丟列：照舊

    ws, ids, fx = await _make_worksheet(client)
    fx["rows"] = [x for x in fx["rows"] if x["source_wi_row_id"] != ids["cub2"]]
    fx["export_warnings"] = _ew(dropped_rows=[{"task_id": 77, "reason": "source_wi_row_id_not_uuid"}])
    r, latest = await _import(client, ws, fx)
    assert r.status_code == 200, r.text
    for body in (r.json(), latest.json()):
        assert {"wi_row_id": ids["cub2"], "reason": "no_result",
                "lb_dropped_possible": True} in body["diff"]["missing"]
        assert body["diff"]["export_warnings"]["dropped_rows"] == [
            {"task_id": 77, "reason": "source_wi_row_id_not_uuid"}]


async def test_export_warnings_truncated_carried_through(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, _ids, fx = await _make_worksheet(client)
    fx["export_warnings"] = _ew(truncated=True, dropped_rows=[
        {"task_id": i, "reason": "source_wi_row_id_not_uuid"} for i in range(50)])
    r, latest = await _import(client, ws, fx)
    assert r.status_code == 200, r.text
    assert latest.json()["diff"]["export_warnings"]["truncated"] is True
    assert len(latest.json()["diff"]["export_warnings"]["dropped_rows"]) == 50


async def test_export_warnings_unknown_reason_is_stored_not_422(client):
    """未知 reason：照常 200、照常存快照（latest 讀得回來），reason 降級為 unknown 並留原值。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    fx["export_warnings"] = _ew(
        units_degraded=[{"task_id": 1, "source_wi_row_id": ids["cub1"], "units_sum": 3, "quantity": 8,
                         "reason": "lb_future_reason"}],
        dropped_rows=[{"task_id": 2, "reason": "lb_future_reason"}])
    r, latest = await _import(client, ws, fx)
    assert r.status_code == 200, r.text
    assert latest.status_code == 200
    ew = latest.json()["diff"]["export_warnings"]
    assert ew["units_degraded"][0]["reason"] == "unknown"
    assert ew["units_degraded"][0]["reason_raw"] == "lb_future_reason"
    assert ew["dropped_rows"] == [{"task_id": 2, "reason": "unknown", "reason_raw": "lb_future_reason"}]
    snaps = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/snapshots")
    assert len(snaps.json()["snapshots"]) == 1


async def test_export_warnings_structural_error_is_422(client):
    """結構錯仍是壞資料 → 422 VALIDATION_ERROR，不存快照。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, _ids, fx = await _make_worksheet(client)
    fx["export_warnings"] = {"units_degraded": "not-a-list"}
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    snaps = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/snapshots")
    assert snaps.json()["snapshots"] == []
