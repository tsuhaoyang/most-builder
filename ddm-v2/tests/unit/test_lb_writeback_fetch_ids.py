"""回寫端點的 id 驗證：LB 座標（fetch）與 apply-offline 的 UUID 欄位。

座標（安全修正）：三個座標直接成為 LB URL 的路徑段，必須擋住路徑改寫。

`lb_project_id="x/../../../admin/users?"` 原本會讓 MOST 帶著身分 header 對 LB 主機的
`/api/admin/users` 發 GET。修正：路由層 `FetchIn` 以 `LB_ID_PATTERN` 回 422；`lb_client.fetch_writeback`
再以同一規則擋一次（縱深防線），不合格就不發任何請求。
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import ValidationError

from ddm_v2.api.routes.v2.lb_writeback import ApplyOfflineIn, FetchIn
from ddm_v2.services.v2.lb_client import fetch_writeback

VALID_IDS = [
    "ba0dba3c1b6a4674a330ba56cda38cc7",          # LB project id（32 位 hex）
    "cb43da21-98fd-4fad-a799-148eea42b778",      # UUID
    "original",
    "v_1a2b3c",
    "demo-result",
    "a" * 64,                                    # 上限
]

BAD_IDS = [
    "x/../../../admin/users?",                   # 實測可改寫路徑的 payload
    "../admin",
    "..",
    ".",
    "a/b",
    "a\\b",
    "a%2Fb",                                     # 預先編碼的斜線
    "a?b=1",
    "a#frag",
    "a b",
    " a",
    "a\tb",
    "abc\n",                                     # 結尾換行（Python re 的 `$` 會放過）
    "a\x00b",
    "a\x7fb",
    "ａｂｃ",                                     # 全形
    "\u212a",                                   # Kelvin 符號 K（同形字）
    "a\u200bb",                                 # 零寬空白
    "",
    "a" * 65,                                    # 超長
]

FIELDS = ["lb_project_id", "lb_version_id", "lb_result_id"]


def _body(**override: str) -> dict:
    return {"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R", **override}


@pytest.mark.parametrize("value", VALID_IDS)
def test_fetchin_accepts_lb_id_formats(value):
    for f in FIELDS:
        assert getattr(FetchIn(**_body(**{f: value})), f) == value


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", BAD_IDS)
def test_fetchin_rejects_unsafe_ids(field, value):
    with pytest.raises(ValidationError):
        FetchIn(**_body(**{field: value}))


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [123, 1.5, ["a"], {"a": 1}, None, True])
def test_fetchin_rejects_non_string_json(field, value):
    """JSON 送非字串不得被強制轉型成字串後放行。"""
    import json
    with pytest.raises(ValidationError):
        FetchIn.model_validate_json(json.dumps(_body(**{field: value})))


def _recording_server():
    hits: list[str] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, hits


@pytest.mark.parametrize("field", ["project_id", "version_id", "result_id"])
@pytest.mark.parametrize("value", ["x/../../../admin/users?", "a/b", "..", "abc\n", "a" * 65, ""])
async def test_client_refuses_unsafe_ids_without_request(field, value):
    """縱深防線：就算呼叫端漏驗，client 也不發請求。"""
    server, hits = _recording_server()
    try:
        ids = {"project_id": "P", "version_id": "V", "result_id": "R", field: value}
        with pytest.raises(ValueError, match=field):
            await fetch_writeback(base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout_s=2.0, **ids)
        assert hits == []
    finally:
        server.shutdown()


async def test_client_valid_ids_still_reach_lb():
    """對照組：合法座標照常送出，路徑就是預期的 writeback 路徑。"""
    server, hits = _recording_server()
    try:
        await fetch_writeback(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout_s=2.0,
            project_id="ba0dba3c1b6a4674a330ba56cda38cc7", version_id="original",
            result_id="cb43da21-98fd-4fad-a799-148eea42b778",
        )
        assert hits == ["/api/v3/projects/ba0dba3c1b6a4674a330ba56cda38cc7/versions/original"
                        "/results/cb43da21-98fd-4fad-a799-148eea42b778/writeback"]
    finally:
        server.shutdown()


# ── apply-offline：snapshot_id／wi_row_ids 收 UUID 型別（非 UUID 原本在 route 內轉換 → 無信封 500）──

_UUID = "cb43da21-98fd-4fad-a799-148eea42b778"


def _apply_body(**override):
    return {"snapshot_id": _UUID, "wi_row_ids": [_UUID], **override}


@pytest.mark.parametrize("value", [
    _UUID,
    _UUID.replace("-", ""),              # 32 位無連字號
    "{" + _UUID + "}",                   # 大括號
    "urn:uuid:" + _UUID,                 # urn 形式
    _UUID.upper(),                       # 大寫
])
def test_apply_offline_in_accepts_uuid_forms_and_normalizes(value):
    """接受 canonical／32 位無連字號／大括號／urn／大小寫，並正規化為小寫連字號形式。
    注意：pydantic 的 parser 比 D7 追記（2026-09-18）第 3 點的 `uuid.UUID()` **略嚴**（怪位置的連字號它不收），
    兩者對正常輸入等價；那個邊界由下面 reject 清單的 `cb43da2198fd-...` 釘住。"""
    body = ApplyOfflineIn(**_apply_body(snapshot_id=value, wi_row_ids=[value]))
    assert str(body.snapshot_id) == _UUID
    assert [str(x) for x in body.wi_row_ids] == [_UUID]


@pytest.mark.parametrize("bad", [
    "not-a-uuid", "", "  ", _UUID[:-1], 123, None, {}, [_UUID],
    "cb43da2198fd-4fad-a799-148eea42b778",  # 連字號位置怪：stdlib uuid.UUID() 收、pydantic 拒（刻意從嚴）
])
def test_apply_offline_in_rejects_non_uuid_snapshot_id(bad):
    with pytest.raises(ValidationError):
        ApplyOfflineIn(**_apply_body(snapshot_id=bad))


@pytest.mark.parametrize("bad", [[], ["not-a-uuid"], [_UUID, "x"], _UUID, [123], [None]])
def test_apply_offline_in_rejects_bad_wi_row_ids(bad):
    with pytest.raises(ValidationError):
        ApplyOfflineIn(**_apply_body(wi_row_ids=bad))


def test_apply_offline_in_rejects_oversized_wi_row_ids():
    """上限：pydantic 對 list 逐項收集錯誤並回吐輸入值，無上限時一份壞 payload 會被放大成巨大回應。"""
    with pytest.raises(ValidationError):
        ApplyOfflineIn(**_apply_body(wi_row_ids=[_UUID] * 1001))
    ApplyOfflineIn(**_apply_body(wi_row_ids=[_UUID] * 1000))  # 剛好上限仍可用


def test_projection_raises_covers_every_projection_exception():
    """絆線：投影層日後新增例外類別而沒被 `_projection_raises()` 接住 → apply-offline／fetch 會回到 500。

    範圍限於 `lb_projection` 各模組**直接定義**的 Exception 子類（不遞迴子套件）。**不涵蓋**投影過程中
    由別處拋出的例外——例如 `tmu.decompose_engine` 會經 `most_engine.calculate` 拋 `SequenceError`；
    那條路今天不活（`project.py` 走 `decompose_static`），接上去時這支測試不會變紅。
    """
    import importlib
    import inspect
    import pkgutil

    import ddm_v2.lb_projection as pkg
    from ddm_v2.services.v2.lb_writeback_service import _projection_raises

    caught = set(_projection_raises())
    declared = set()
    for mod in pkgutil.iter_modules(pkg.__path__):
        m = importlib.import_module(f"{pkg.__name__}.{mod.name}")
        declared |= {
            obj for _, obj in inspect.getmembers(m, inspect.isclass)
            if issubclass(obj, Exception) and obj.__module__ == m.__name__
        }
    assert declared - caught == set(), f"投影層新增了沒被接住的例外：{declared - caught}"

    # 只「接住」不夠：處理器會讀 exc.err.code／wi_row_id／message／params，沒有 err 的例外
    # 被加進清單後會在 except 區塊裡丟 AttributeError——仍是無信封 500，而且更難追。
    for cls in caught:
        assert "err" in inspect.signature(cls.__init__).parameters, f"{cls.__name__} 沒有 err 參數"


@pytest.mark.parametrize("params", [
    None,
    {"frequency": 1.5},                        # quantity.py 實際會塞的形狀
    {"counts": {"3": 2, "4": None}},           # tmu.py 實際會塞的形狀
    {"frequency": float("nan")},               # jsonb 拒收 → 不處理的話會在 commit 時 500
    {"frequency": float("inf")},
    {"x": object()},                           # 不可序列化
])
def test_jsonable_err_never_raises_and_output_is_strict_json(params):
    """留痕本身不准失敗：這段程式存在的理由就是「投影出問題時不准 500」。"""
    import json as _json

    from ddm_v2.lb_projection.errors import ProjectionError
    from ddm_v2.services.v2.lb_writeback_service import _jsonable_err

    out = _jsonable_err(ProjectionError("E_X", None, "msg", params))
    # allow_nan=False：PostgreSQL jsonb 不收 NaN／Infinity，這裡先擋住
    _json.loads(_json.dumps(out, allow_nan=False))
    assert out["code"] == "E_X"


def test_jsonable_err_truncates_long_message():
    """message 直接吃工序表欄位（level 原字串無長度上限），不截斷會整包進 jsonb 並每次回吐。"""
    from ddm_v2.lb_projection.errors import ProjectionError
    from ddm_v2.services.v2.lb_writeback_service import _ERR_MESSAGE_MAX, _jsonable_err

    out = _jsonable_err(ProjectionError("E_X", None, "長" * 100000, None))
    assert len(out["message"]) == _ERR_MESSAGE_MAX
