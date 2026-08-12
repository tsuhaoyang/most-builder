"""路由掛載守門：`create_app()` 不得產出「起得來但沒有 API」的服務。

## 這組測試在防哪個具體事故

FastAPI 0.137 把 `include_router()` 從「攤平複製子路由」改成「放一個延遲展開的
`_IncludedRouter` 節點」。路由本身照常運作，但**直接走訪 `app.routes` 撈 `APIRoute`
會一條都撈不到**。因為 `pyproject.toml` 對 fastapi 只寫 `>=0.115,<1.0`，CI 每次
`pip install -e .` 都拿最新版 → CI（0.141）紅、本機（0.136）綠，且
`python -c "create_app()"` 那個 smoke step 照樣印 `app OK`（它只檢查沒有例外）。

所以這裡釘四件事：
1. 走訪邏輯（`iter_mounted_api_routes`）必須與 FastAPI 自己產的 OpenAPI 一致——
   框架再改內部結構時，這條會紅，而不是讓其他守衛測試靜默退化成「迴圈跑 0 次」。
2. 走訪器碰到**不認得的節點型別**必須 `RouteTraversalUnsupported`，不得回報一個
   看似正常的空／少報結果（fastapi 0.137.0/0.137.1 實測就是這個空窗：已經有
   `_IncludedRouter`、還沒有 `iter_route_contexts`）。
3. `mount_v2_routers()` 掛完會對帳，但**只有證明得了「沒有 API」才 fail loud**；
   「我們的走訪器瞎了、路由其實都在」不得變成一次自找的停機。對帳單位是
   **(path, method)** 不是 path：19 支 router 的 106 條路由只塌成 83 條 path，
   只比 path 會讓「同路徑掛上 GET、掉了 PUT/DELETE」整批溜過去。
4. 每一支 `api/routes/v2/*.py` 的 router 都在清單裡，且 preview_server 不只「用同一份
   清單」，而是**實際掛出同一組 API**（少掛不出聲的檢查等於沒檢查）。
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
import pkgutil
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from starlette.routing import BaseRoute, Host, Match, Mount, Route, WebSocketRoute

from ddm_v2.api import route_registry
from ddm_v2.api.route_registry import (
    V2_ROUTERS,
    RouteTraversalUnsupported,
    count_mounted_api_routes,
    iter_mounted_api_routes,
    mount_v2_routers,
)
from ddm_v2.main import create_app

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIEW_SERVER = REPO_ROOT / "scripts" / "preview_server.py"
ROUTES_PKG = "ddm_v2.api.routes.v2"


class _OpaqueRouteContainer(BaseRoute):
    """模擬「未來版本把子路由包進的容器」。

    刻意直接繼承 `BaseRoute`（`fastapi.routing._IncludedRouter` 就是這樣），
    因此不是 `Route`/`Mount`/`WebSocketRoute`/`Host` 任何一種葉節點——
    攤平走訪看到它時，唯一誠實的反應是「我看不懂，別信我的結果」。
    """

    def matches(self, scope: Any) -> tuple[Match, dict]:
        return Match.NONE, {}

    async def handle(self, scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
        raise AssertionError("本測試不送請求")


def _force_flat_traversal(monkeypatch) -> None:
    """把走訪器釘在「沒有官方走訪器」的分支，讓測試在任何 fastapi 版本上意義一致。"""
    monkeypatch.setattr(route_registry, "_iter_route_contexts", None)


def _openapi_operations(app: FastAPI) -> set[tuple[str, str]]:
    """對照組：從 app 自產的 OpenAPI 讀出 `{(path, METHOD)}`。

    刻意在測試裡自己算一遍，而不是 import `route_registry._openapi_operations`——
    對照組跟被測程式共用實作就不是對照組了。
    """
    return {
        (path, method.upper())
        for path, item in (app.openapi().get("paths") or {}).items()
        for method in item
    }


# ── 1. 走訪邏輯本身要正確（對照組＝FastAPI 自己的 OpenAPI）──────────────
def test_route_traversal_agrees_with_openapi():
    """`iter_mounted_api_routes` 必須看到 OpenAPI 裡的每一條 path。

    對照組刻意選 OpenAPI：它由 FastAPI 自己產生，等於「框架眼中真正掛上去的路由」。
    若哪天框架又改路由表結構而我們的走訪跟不上，這條會直接紅，不會靜默失效。
    """
    app = create_app()
    walked = {r.path for r in iter_mounted_api_routes(app)}
    from_openapi = set(app.openapi()["paths"])

    assert from_openapi, "前提失效：OpenAPI 一條 path 都沒有"
    missing = sorted(from_openapi - walked)
    assert missing == [], (
        "iter_mounted_api_routes 漏掉了這些 OpenAPI 有的路由（走訪邏輯跟不上 FastAPI 版本）："
        f"{missing}"
    )


def test_app_exposes_the_v2_api_surface():
    """實掛路由數必須 ≥ 19 支 router 宣告的總數（不是只有 /docs 那幾條）。"""
    app = create_app()
    declared = sum(count_mounted_api_routes(router) for _name, router in V2_ROUTERS)

    assert declared > 0, "前提失效：所有 v2 router 都是空的"
    assert count_mounted_api_routes(app) >= declared

    paths = {r.path for r in iter_mounted_api_routes(app)}
    # 具名抽樣：跨三個不同 prefix，避免只驗到某一支
    for path in ("/api/v2/me", "/api/v2/rule-sets/{code}/full", "/api/v2/admin/users"):
        assert path in paths, f"{path} 沒掛上去"


def test_every_v2_router_contributes_routes():
    app = create_app()
    paths = {r.path for r in iter_mounted_api_routes(app)}
    for name, router in V2_ROUTERS:
        declared = {r.path for r in iter_mounted_api_routes(router)}
        assert declared, f"router {name} 一條路由都沒有"
        assert declared <= paths, f"router {name} 的路由沒有全部掛進 app：{sorted(declared - paths)}"


# ── 2. 走訪器不得「看不懂卻裝作看懂」（fastapi 0.137.0/0.137.1 空窗）──────
def test_flat_traversal_rejects_route_objects_it_does_not_understand(monkeypatch):
    """攤平走訪碰到不認得的節點型別 → raise，不得靜默少報。

    這是 0.137.0 的真實處境：`_IncludedRouter` 已經在了、`iter_route_contexts`
    還沒有，兩邊條件都不成立。舊版探測（「有沒有 iter_route_contexts」）會判成
    舊結構、走攤平路徑、**一條都撈不到卻不出聲**——所有靠走訪的守衛同時假綠。
    """
    _force_flat_traversal(monkeypatch)
    router = APIRouter(prefix="/api/v2")

    @router.get("/probe")
    def probe() -> dict:
        return {}

    routes = [*router.routes, _OpaqueRouteContainer()]
    with pytest.raises(RouteTraversalUnsupported) as excinfo:
        list(iter_mounted_api_routes(routes))
    assert "_OpaqueRouteContainer" in str(excinfo.value), "訊息要指名到底是哪個型別看不懂"


@pytest.mark.parametrize("flat", [True, False], ids=["flat", "iter_route_contexts"])
def test_traversal_accepts_an_iterator_of_routes(monkeypatch, flat):
    """傳 iterator 進來不得靜默回 `[]`。

    `_flat_api_routes` 對 `routes` 走兩趟（先驗型別、再取值），第一趟就把 iterator
    吃光 → 第二趟空 → 回 `[]`，而且還「驗過型別」了。實測修正前
    `iter_mounted_api_routes(iter(router.routes))` 回 `[]`、傳 list 回 1 條。
    靜默回空正是本模組立志消滅的失效模式，所以兩條走訪路徑都釘。

    mutation 實測（把 `_as_routes` 改回不物化）：
    - fastapi 0.136（無官方走訪器，兩個參數都走攤平路徑）：兩條都紅。
    - fastapi 0.141.1：`[flat]` 紅、`[iter_route_contexts]` 綠——框架自己的走訪器
      只走一趟，所以那一邊今天是**等價變異**。仍然留著：它釘的是「context 路徑也吃
      iterator」這個性質，哪天上游改成走兩趟（或我們在中間加一趟預檢），這條會接住。
    """
    if flat:
        _force_flat_traversal(monkeypatch)
    router = APIRouter(prefix="/api/v2")

    @router.get("/probe")
    def probe() -> dict:
        return {}

    from_list = [r.path for r in iter_mounted_api_routes(list(router.routes))]
    from_iterator = [r.path for r in iter_mounted_api_routes(iter(router.routes))]
    assert from_list == ["/api/v2/probe"], "前提失效：傳 list 就該看得到這條"
    assert from_iterator == from_list


def test_flat_traversal_accepts_the_known_starlette_node_types(monkeypatch):
    """白名單不能矯枉過正：正常 app 本來就混著非 API 的 starlette 節點。

    沒有這條，上面那條可以靠「看到任何非 APIRoute 就 raise」作弊通過，
    然後每一個真實 app（有 /docs、StaticFiles mount）都起不來。
    """
    _force_flat_traversal(monkeypatch)
    router = APIRouter(prefix="/api/v2")

    @router.get("/probe")
    def probe() -> dict:
        return {}

    async def _noop(scope, receive, send):  # pragma: no cover - 只當佔位端點
        raise AssertionError("本測試不送請求")

    routes = [
        *router.routes,
        Route("/docs", endpoint=_noop),
        Mount("/assets", app=_noop),
        WebSocketRoute("/ws", endpoint=_noop),
        Host("example.com", app=_noop),
    ]
    assert [r.path for r in iter_mounted_api_routes(routes)] == ["/api/v2/probe"]


def test_opaque_route_container_does_not_abort_a_healthy_app(monkeypatch, caplog):
    """走訪器看不懂 app.routes，但路由其實都在 → ERROR 記錄、照常啟動。

    「撈不到路由」≠「沒有路由」。裁決交給框架自己的 OpenAPI，不是我們的走訪器。
    """
    _force_flat_traversal(monkeypatch)
    app = FastAPI()
    app.router.routes.append(_OpaqueRouteContainer())

    with caplog.at_level(logging.ERROR, logger=route_registry.__name__):
        mount_v2_routers(app)
    assert [r for r in caplog.records if r.levelno == logging.ERROR], "至少要大聲記一筆 ERROR"
    assert "/api/v2/me" in app.openapi()["paths"], "前提：路由其實好好的在上面"


# ── 3. 掛不上去必須大聲失敗（不得靜默給出無 API 的 app）──────────────────
def test_mount_rejects_empty_router():
    """空 router 對 include_router 是 no-op；沒有這道檢查就會靜默少掉一整組 API。"""
    with pytest.raises(RuntimeError, match="一條路由都沒有"):
        mount_v2_routers(FastAPI(), [("空的", APIRouter(prefix="/api/v2"))])


def test_mount_rejects_one_empty_router_among_healthy_ones():
    """部分 router 空掉＝真實迴歸（那一組 API 全 404），必須點名並拒絕啟動。

    這條釘住「降級不是無條件放行」：上面那些放行分支的前提是**框架說路由都在**，
    框架說某支沒有路由時就沒有可放行的餘地。
    """
    healthy = dict(V2_ROUTERS)["calculate"]
    with pytest.raises(RuntimeError, match="一條路由都沒有") as excinfo:
        mount_v2_routers(FastAPI(), [("calculate", healthy), ("空的", APIRouter(prefix="/api/v2"))])
    assert "空的" in str(excinfo.value)
    assert "'calculate'" not in str(excinfo.value), "不該連累有路由的那支"


def test_all_routers_looking_empty_is_treated_as_traversal_failure(monkeypatch, caplog):
    """19 支 router **同時**看起來是空的 → 走訪器失效的機率遠高於全體迴歸。

    實測過的反例：把 `APIRouter.routes` 也換成不透明結構時，舊版的「空 router 無條件
    raise」會對一個 OpenAPI 83 條 path、`/api/v2/me` 好好在的 app 喊「一條路由都沒有」
    並拒絕啟動——而且 raise 在 include_router 之前，連第二意見都問不到。
    """
    real_iter = route_registry.iter_mounted_api_routes
    monkeypatch.setattr(
        route_registry,
        "iter_mounted_api_routes",
        lambda source: iter(()) if isinstance(source, APIRouter) else real_iter(source),
    )
    app = FastAPI()
    with caplog.at_level(logging.ERROR, logger=route_registry.__name__):
        mount_v2_routers(app)
    assert [r for r in caplog.records if r.levelno == logging.ERROR], "至少要大聲記一筆 ERROR"
    assert "/api/v2/me" in app.openapi()["paths"], "前提：路由其實好好的在上面"


def test_all_routers_unreadable_is_treated_as_traversal_failure(monkeypatch, caplog):
    """同上，但走訪器是**明講**看不懂（raise）而不是回空——一樣不該擋啟動。"""
    real_iter = route_registry.iter_mounted_api_routes

    def unreadable(source):
        if isinstance(source, APIRouter):
            raise RouteTraversalUnsupported(["tests._Opaque"])
        return real_iter(source)

    monkeypatch.setattr(route_registry, "iter_mounted_api_routes", unreadable)
    app = FastAPI()
    with caplog.at_level(logging.ERROR, logger=route_registry.__name__):
        mount_v2_routers(app)
    assert "/api/v2/me" in app.openapi()["paths"]


def test_mount_fails_loud_when_include_router_mounts_nothing(monkeypatch):
    """模擬「include_router 等於沒掛」——必須 raise，不能回傳一個空殼 app。

    這是本次事故的真實災難版本：呼叫成功、沒有例外、但 app 一條 API 都沒有。
    """
    monkeypatch.setattr(FastAPI, "include_router", lambda self, *a, **k: None)
    with pytest.raises(RuntimeError, match="少了上列 API"):
        mount_v2_routers(FastAPI())


def test_create_app_propagates_mount_failure(monkeypatch):
    """自我檢查必須真的接在 create_app() 上（否則只是個沒人叫的函式）。"""
    monkeypatch.setattr(FastAPI, "include_router", lambda self, *a, **k: None)
    with pytest.raises(RuntimeError, match="少了上列 API"):
        create_app()


def test_mount_detects_a_dropped_method_on_a_still_present_path(monkeypatch):
    """少掛的是「同一個 path 的另一個 method」時，也必須擋下來。

    這是逐 path 對帳看不見的那半邊：19 支 router 的 106 條路由只塌成 83 條 path，
    所以「GET 還在、PUT/DELETE 掉了」在 path 集合上差集為空 → 記 ERROR 放行 →
    那批寫入 API 全 404，而自我檢查一聲不吭。對帳單位必須是 (path, method)。
    """
    router = APIRouter(prefix="/api/v2")

    @router.get("/thing/{thing_id}")
    def read(thing_id: str) -> dict:
        return {}

    @router.put("/thing/{thing_id}")
    def write(thing_id: str) -> dict:
        return {}

    real_include = FastAPI.include_router

    def include_dropping_writes(self, source, *args, **kwargs):
        """模擬「掛上去時掉了非 GET 的那半」——path 一條沒少，method 少一半。"""
        partial = APIRouter()
        partial.routes.extend(r for r in source.routes if "PUT" not in getattr(r, "methods", set()))
        return real_include(self, partial, *args, **kwargs)

    monkeypatch.setattr(FastAPI, "include_router", include_dropping_writes)
    app = FastAPI()
    with pytest.raises(RuntimeError, match="少了上列 API") as excinfo:
        mount_v2_routers(app, [("thing", router)])
    assert "PUT /api/v2/thing/{thing_id}" in str(excinfo.value), "訊息要指名少的是哪一個 method"


def test_broken_traversal_does_not_abort_a_healthy_app(monkeypatch, caplog):
    """走訪器跟不上版本、但路由其實都在 → 不擋啟動，改為 ERROR 記錄。

    分辨這兩種情況才是重點：抓不到路由 ≠ 沒有路由。若一律 raise，下一次 FastAPI
    改結構就是「明明服務好好的卻起不來」的自找停機；這裡以 OpenAPI（框架自產）
    當第二意見，只有連 OpenAPI 都看不到才拒絕啟動。
    ERROR 不是靜默：CI 有 `test_route_traversal_agrees_with_openapi` 會先變紅。
    """
    real_iter = route_registry.iter_mounted_api_routes

    def blind_on_apps(source):
        # 只對 app 瞎掉（router 仍數得出來）＝「走訪器認不得新的 app.routes 結構」
        return iter(()) if isinstance(source, FastAPI) else real_iter(source)

    monkeypatch.setattr(route_registry, "iter_mounted_api_routes", blind_on_apps)
    with caplog.at_level(logging.ERROR, logger=route_registry.__name__):
        app = FastAPI()
        assert mount_v2_routers(app) == 0
    assert [r for r in caplog.records if r.levelno == logging.ERROR], "至少要大聲記一筆 ERROR"
    assert "/api/v2/me" in app.openapi()["paths"], "前提：路由其實好好的在上面"


def test_self_check_does_not_poison_the_openapi_cache(monkeypatch):
    """自我檢查問 OpenAPI 時是在 `create_app()` **中途**（之後還會加 `GET /`）。

    `app.openapi()` 會把結果快取進 `app.openapi_schema`，中途叫一次就等於把一份
    「少了後面那些路由」的 schema 釘死給線上的 /openapi.json 用（前端 gen:api 也吃它）。
    """
    real_iter = route_registry.iter_mounted_api_routes
    monkeypatch.setattr(
        route_registry,
        "iter_mounted_api_routes",
        lambda source: iter(()) if isinstance(source, FastAPI) else real_iter(source),
    )
    app = create_app()  # 走降級分支 → 一定會呼叫到 app.openapi()
    assert "/" in app.openapi()["paths"], "掛載檢查之後才註冊的 GET / 不見了＝schema 是過期快取"


# ── 4. 清單是唯一的（新檔案不掛 / preview 漂移都要當場被抓）──────────────
def test_registry_covers_every_route_module():
    """`api/routes/v2/` 底下每一支有 `router` 的模組都必須在 V2_ROUTERS 裡。

    少掛一支的症狀是「某個分頁整組 404」，而且沒有任何錯誤訊息。
    """
    pkg = importlib.import_module(ROUTES_PKG)
    registered = {id(router) for _name, router in V2_ROUTERS}
    missing = []
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        module = importlib.import_module(f"{ROUTES_PKG}.{mod_info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter) and id(router) not in registered:
            missing.append(mod_info.name)
    assert missing == [], f"這些 route 模組沒被掛進 app：{missing}（請加進 V2_ROUTERS）"


def test_registry_has_no_duplicate_routers():
    names = [name for name, _ in V2_ROUTERS]
    assert len(names) == len(set(names))
    assert len({id(router) for _n, router in V2_ROUTERS}) == len(names)


def test_preview_server_does_not_list_routers_itself():
    """preview_server 不得自己列 include_router（它曾漂移成少掛 3 支）。

    e2e 是打 preview_server 的，兩份清單一旦分岔，預覽/e2e 的 API 面就跟正式 app 不同。
    用 AST 而非字串比對，避免註解裡提到 include_router 就誤判。

    ⚠️ 這條是**單向**的（只證明「沒有自己列」）：把 `mount_v2_routers(app)` 整行換成
    `pass` 它照樣綠。「有沒有掛」由下面那條負責，兩條缺一不可。
    """
    tree = ast.parse(PREVIEW_SERVER.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
    ]
    assert calls == [], (
        "scripts/preview_server.py 自行呼叫了 include_router——請改用 "
        "route_registry.mount_v2_routers(app)，否則清單會再次與 main.py 漂移。"
    )


def _load_preview_server(monkeypatch):
    """把 `scripts/preview_server.py` 當模組載入（它不在 package 裡，只能按路徑載）。

    先用 monkeypatch 佔住 `AUTH_DEV_USER`：該模組頂層有
    `os.environ.setdefault("AUTH_DEV_USER", "IEC141289")`，不隔離的話這個 import 會把
    dev 身分留給同一個 pytest process 的其他測試（teardown 時 monkeypatch 會還原）。
    模組名刻意不叫 `preview_server` 也不塞進 sys.modules：載入即建立一個新的 app，
    不需要、也不應該被別的測試重用。
    """
    monkeypatch.setenv("AUTH_DEV_USER", "IEC141289")
    spec = importlib.util.spec_from_file_location("_preview_server_under_test", PREVIEW_SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_server_exposes_the_same_api_surface(monkeypatch):
    """preview_server 的 API 面必須**逐條等於** `create_app()`（不是「不多不少」的口號）。

    上面那條 AST 測試只證明 preview 沒有自己列清單；`mount_v2_routers(app)` 被刪掉
    （換成 `pass`）時它仍然全綠——而那正是這組測試存在的理由所在的災難：預覽/e2e
    拿到一個只有前端、零 API 的服務。實測 mutation：把該行換成 `pass`，舊測試 17 條
    全綠，本條紅（差集是全部 106 條 v2 路由）。

    比 (path, method) 而不是 path：同一個 path 掛多個 method 是常態
    （107 條 operation 只塌成 84 條 path），只比 path 會漏掉方法級的漂移。
    用 `==` 而不是單向包含：preview 多出正式 app 沒有的 API 一樣是漂移
    （那是「只有預覽環境才有的端點」，e2e 會綠、production 會 404）。
    """
    preview = _load_preview_server(monkeypatch)
    preview_ops = _openapi_operations(preview.app)
    app_ops = _openapi_operations(create_app())

    assert app_ops, "前提失效：create_app() 一條 API 都沒有"
    only_in_app = sorted(f"{m} {p}" for p, m in app_ops - preview_ops)
    only_in_preview = sorted(f"{m} {p}" for p, m in preview_ops - app_ops)
    assert not (only_in_app or only_in_preview), (
        "preview_server 與 create_app() 的 API 面已分岔（e2e 打的不是正式 app 的那組 API）："
        f"preview 少了 {len(only_in_app)} 條 {only_in_app[:10]}；"
        f"preview 多了 {len(only_in_preview)} 條 {only_in_preview[:10]}"
    )
