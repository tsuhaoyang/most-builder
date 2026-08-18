"""v2 router 的唯一掛載入口 ＋ 「掛完真的有路由」的啟動期自我檢查。

## 為什麼需要這個檔（2026-08 CI-only 紅燈的根因）

FastAPI 0.137 改了 `include_router()` 的資料結構：以前是把子 router 的 `APIRoute`
**攤平複製**進 `app.router.routes`，現在改成在 `app.routes` 放一個
`fastapi.routing._IncludedRouter` 節點，真正的路由延遲到 match/OpenAPI 時才展開。

行為面沒有壞（請求分派、OpenAPI 都正常；實測 84 條 path 全在），但
**任何直接走訪 `app.routes` 撈 `APIRoute` 的程式碼會一條都撈不到**——
`{getattr(r, "path", None) for r in app.routes}` 會退化成
`{'/openapi.json', '/docs', '/redoc', '/docs/oauth2-redirect', '/', None}`。
我們兩支守衛測試因此在 CI（`pip install -e .` 裝到最新版）變紅、在本機（0.136）全綠。

同一個變更也意味著：這類走訪若沒人守，**未來會靜默退化成「什麼都沒檢查」**
（測試照樣綠，但迴圈跑 0 次）。所以走訪邏輯只留這一份，並由
`tests/unit/test_route_mounting.py` 用 OpenAPI 當對照組釘死。

## 兩條鐵律（都是被實測打臉換來的）

1. **偵測「結構」，不要偵測「有沒有新 API」。**
   實測三個 fastapi overlay：

   | 版本 | `_IncludedRouter`（延遲展開） | `iter_route_contexts`（官方走訪器） |
   |---|---|---|
   | ≤ 0.136.3 | 無 | 無 |
   | 0.137.0 / 0.137.1 | **有** | **無** |
   | ≥ 0.137.2 | 有 | 有 |

   中間那兩版是真實空窗：拿「有沒有 `iter_route_contexts`」當旗標會判成舊版、
   走攤平路徑、**一條都撈不到卻不出聲**。所以舊路徑改成看 `routes` 裡的**節點型別**：
   出現不認得的型別就 `RouteTraversalUnsupported`，寧可紅也不回一個看似正常的空結果。

2. **「撈不到路由」≠「沒有路由」。** 任何異常一律交給 FastAPI 自己的 OpenAPI 產生器
   (`get_openapi`) 當第二意見——它跟框架同版本、必然懂當版結構，而且不經
   `include_router`，所以「router 真的空」與「走訪器瞎了」分得開。
   只有連框架都說沒有 API 才拒絕啟動；否則記 ERROR 放行（自找的停機比漏檢更貴）。

## 本檔提供

1. `V2_ROUTERS`：19 支 router 的唯一清單。`main.py` 與 `scripts/preview_server.py`
   共用同一份（原本兩邊各抄一份，preview 已漂移成少掛 3 支）。
2. `mount_v2_routers(app)`：掛載 ＋ 掛完對帳，證明得了「沒有 API」才 `RuntimeError`。
   寧可啟動時大聲失敗，也不要跑出一個「HTTP 200 首頁、但沒有任何 API」的服務。
3. `iter_mounted_api_routes(...)`：跨 FastAPI 版本的路由走訪（測試與自我檢查共用）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi import routing as _fastapi_routing
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from starlette.routing import Host, Mount, Route, WebSocketRoute

from ddm_v2.api.routes.v2.admin_users import router as v2_admin_router
from ddm_v2.api.routes.v2.ai_review import router as v2_ai_review_router
from ddm_v2.api.routes.v2.audit_log import router as v2_audit_log_router
from ddm_v2.api.routes.v2.calculate import router as v2_calculate_router
from ddm_v2.api.routes.v2.cases import router as v2_cases_router
from ddm_v2.api.routes.v2.catalog import router as v2_catalog_router
from ddm_v2.api.routes.v2.export import router as v2_export_router
from ddm_v2.api.routes.v2.i18n import router as v2_i18n_router
from ddm_v2.api.routes.v2.import_excel import router as v2_import_router
from ddm_v2.api.routes.v2.motion_module import router as v2_motion_module_router
from ddm_v2.api.routes.v2.motion_template import router as v2_motion_template_router
from ddm_v2.api.routes.v2.nl_draft import router as v2_nl_draft_router
from ddm_v2.api.routes.v2.parse_jobs import router as v2_parse_jobs_router
from ddm_v2.api.routes.v2.rule_set import router as v2_ruleset_router
from ddm_v2.api.routes.v2.search import router as v2_search_router
from ddm_v2.api.routes.v2.synonyms import router as v2_synonyms_router
from ddm_v2.api.routes.v2.vocab import router as v2_vocab_router
from ddm_v2.api.routes.v2.wi_context import router as v2_wi_context_router
from ddm_v2.api.routes.v2.wi_set import router as v2_wi_set_router
from ddm_v2.api.routes.v2.worksheet import router as v2_worksheet_router

logger = logging.getLogger(__name__)

# FastAPI >= 0.137.2：include_router 延遲展開，且有官方走訪器看得到子路由。
# 用 getattr 而不是 try/except import：兩版都不需要 `type: ignore`
# （mypy 開了 warn_unused_ignores，寫 ignore 會在另一個版本變成新的錯誤）。
#
# ⚠️ 這個旗標只回答「有沒有官方走訪器」，**不**回答「app.routes 是什麼結構」。
# 0.137.0/0.137.1 兩者不一致（見模組 docstring 的表），所以 fallback 路徑不能假設
# 自己一定看得懂結構——它必須自己驗（`_flat_api_routes`）。
_iter_route_contexts: Callable[[Sequence[Any]], Iterable[Any]] | None = getattr(
    _fastapi_routing, "iter_route_contexts", None
)

# 攤平路由表裡「合法出現、但不是 API 路由」的節點型別。
# APIRoute / APIWebSocketRoute 分別是 Route / WebSocketRoute 的子類，故已被涵蓋。
# 刻意列白名單而不是黑名單（`!= _IncludedRouter`）：黑名單只擋得住**已經知道名字**的
# 那個容器，下一次改名或換新容器又會靜默漏掉——正是這次要根治的失效模式。
#
# ⚠️ 已知邊界：白名單只掃**頂層**節點，它保證的是「這個節點不是已知的葉節點型別」，
# **不是**「我看得進去它裡面」。今天成立是因為 `_IncludedRouter` 直接繼承 `BaseRoute`；
# 若未來的延遲展開容器改成繼承 `Mount` 或 `Route`（兩者都在白名單裡），白名單會放行
# 而我們仍然看不到它包住的子路由 → 回到「靜默少報」。屆時要改成遞迴下探 `.routes`／
# `.app.routes`，或直接以 `iter_route_contexts` 為唯一路徑。
_KNOWN_NON_API_ROUTE_TYPES: tuple[type, ...] = (Route, WebSocketRoute, Mount, Host)

# 掛載順序＝原 main.py 的順序（FastAPI 先掛先比對，改順序可能改變同路徑的優先權）。
# 名稱只用於錯誤訊息，取模組名以便直接對到檔案。
V2_ROUTERS: tuple[tuple[str, APIRouter], ...] = (
    ("calculate", v2_calculate_router),
    ("worksheet", v2_worksheet_router),
    ("vocab", v2_vocab_router),
    ("motion_template", v2_motion_template_router),
    ("motion_module", v2_motion_module_router),
    ("export", v2_export_router),
    ("import_excel", v2_import_router),
    ("rule_set", v2_ruleset_router),
    ("admin_users", v2_admin_router),
    ("catalog", v2_catalog_router),
    ("search", v2_search_router),
    ("synonyms", v2_synonyms_router),
    ("nl_draft", v2_nl_draft_router),
    ("ai_review", v2_ai_review_router),
    ("parse_jobs", v2_parse_jobs_router),
    ("audit_log", v2_audit_log_router),
    ("cases", v2_cases_router),
    ("wi_set", v2_wi_set_router),
    ("wi_context", v2_wi_context_router),
    ("i18n", v2_i18n_router),
)


class RouteTraversalUnsupported(RuntimeError):
    """路由表裡有本走訪器不認得的節點 → 走訪結果不可信（**不是**「沒有路由」）。

    存在的理由就是把這兩件事分開。靜默少報會讓所有靠走訪的守衛（DB session scope、
    gateway 警告…）退化成「迴圈跑 0 次」的假綠；實測 fastapi 0.137.0 正是這個組合
    （已有延遲展開的容器、還沒有官方走訪器）。
    """

    def __init__(self, unknown: Sequence[str]) -> None:
        self.unknown_types: tuple[str, ...] = tuple(unknown)
        super().__init__(
            f"路由表裡有本走訪器不認得的節點型別：{list(self.unknown_types)}。"
            "多半是 FastAPI 又改了 include_router 的資料結構（把子路由包進延遲展開的容器）。"
            "在它提供官方走訪器（fastapi.routing.iter_route_contexts）之前，攤平走訪會少報，"
            f"故拒絕回傳看似正常的結果——請更新 {__name__}.iter_mounted_api_routes。"
        )


@dataclass(frozen=True)
class MountedApiRoute:
    """一條**實際生效**的 API 路由（已含 include_router 套上的 prefix/依賴）。

    刻意不直接把 FastAPI 內部物件外流：0.140 前後那個物件的型別完全不同
    （`APIRoute` vs `RouteContext`），呼叫端只該依賴這裡列出的欄位。
    """

    path: str
    methods: frozenset[str]
    dependant: Any
    endpoint: Callable[..., Any] | None
    route: APIRoute  # 原始 APIRoute（需要 response_model 等細節時用）

    @property
    def label(self) -> str:
        return f"{sorted(self.methods)} {self.path}"


def _as_routes(source: FastAPI | APIRouter | Sequence[Any]) -> list[Any]:
    """統一成 list——因為呼叫端可能傳 iterator，而下游要走訪兩次。

    `_flat_api_routes` 先驗型別、再取值，走的是同一個 `routes` 兩趟；傳 iterator 進去
    第二趟必定是空的，於是**靜默回 `[]`**（型別檢查那趟把它吃光了，還「驗過」了）。
    實測修正前：`iter_mounted_api_routes(iter(router.routes))` → `[]`，傳 list 則正常。
    靜默回空正是本模組立志消滅的東西，所以在唯一入口就物化，而不是叮嚀呼叫端。
    """
    if isinstance(source, (FastAPI, APIRouter)):
        return list(source.routes)
    return list(source)


def _flat_api_routes(routes: Sequence[Any]) -> list[MountedApiRoute]:
    """攤平路由表的走訪（FastAPI 沒有官方走訪器時的路徑）。

    先驗結構再走：只要出現既不是 `APIRoute`、也不是已知 starlette 節點的東西，
    就代表這個版本把路由藏進了我們不認得的容器 → `RouteTraversalUnsupported`。
    這正是 0.137.0/0.137.1 的處境（`_IncludedRouter` 直接繼承 `BaseRoute`，
    不是 `Route` 的子類，所以白名單一定攔得到）。

    ⚠️ 白名單只掃頂層、不下探（見 `_KNOWN_NON_API_ROUTE_TYPES` 的已知邊界）。
    ⚠️ `routes` 必須是可重複走訪的序列（本函式走兩趟）；呼叫端一律經 `_as_routes` 物化。
    """
    unknown = sorted(
        {
            f"{type(route).__module__}.{type(route).__qualname__}"
            for route in routes
            if not isinstance(route, (APIRoute, *_KNOWN_NON_API_ROUTE_TYPES))
        }
    )
    if unknown:
        raise RouteTraversalUnsupported(unknown)
    return [
        MountedApiRoute(
            path=route.path,
            methods=frozenset(route.methods or ()),
            dependant=route.dependant,
            endpoint=route.endpoint,
            route=route,
        )
        for route in routes
        if isinstance(route, APIRoute)
    ]


def _context_api_routes(routes: Sequence[Any]) -> list[MountedApiRoute]:
    """官方走訪器路徑（FastAPI >= 0.137.2）：結構由框架自己解讀，不必我們猜。

    ⚠️ 已知的「等價變異」：本 repo 今天沒有任何 router 宣告 router 級 `dependencies=`，
    也沒有 `include_router(..., prefix=...)`（prefix 都寫在 `APIRouter(prefix=...)` 裡），
    所以 `ctx.path/methods/dependant/endpoint` 與 `original.*` **恆等**——把下面的
    `ctx.x or original.x` 改成只讀 `original.x`，測試殺不掉它，那是等價變異而非假測試。
    一旦有 router 開始宣告 `dependencies=`，兩者就會分岔：`test_db_dependency_scope`
    那道 DB session scope 守衛會退回看 `original.dependant`、**看不到 router 級依賴**，
    屆時要補一條「router 級 `dependencies=` 也要被走訪看到」的測試。
    """
    assert _iter_route_contexts is not None  # 由呼叫端保證
    mounted: list[MountedApiRoute] = []
    for ctx in _iter_route_contexts(routes):
        original = ctx.original_route
        if not isinstance(original, APIRoute):
            continue
        # ctx.* 是「掛上去之後」的樣子（prefix 已套用、router 級依賴已合併）；
        # 取不到才退回原始 route，避免因版本差異靜默少報。
        dependant = getattr(ctx, "dependant", None)
        mounted.append(
            MountedApiRoute(
                path=ctx.path or original.path,
                methods=frozenset(ctx.methods or original.methods or ()),
                dependant=dependant if dependant is not None else original.dependant,
                endpoint=ctx.endpoint or original.endpoint,
                route=original,
            )
        )
    return mounted


def iter_mounted_api_routes(source: FastAPI | APIRouter | Sequence[Any]) -> Iterator[MountedApiRoute]:
    """走訪 app／router 上實際生效的 API 路由（跨 FastAPI 版本）。

    ⚠️ 這是本 repo **唯一**允許走訪路由表的地方。直接寫 `for r in app.routes` 在
    FastAPI >= 0.137 會漏掉所有 `include_router` 進來的路由（見模組 docstring）。

    :raises RouteTraversalUnsupported: 路由表的結構本走訪器看不懂（結果會少報）。
        刻意在呼叫當下就丟、不等到第一次 `next()`：讓 `list(...)`／`for` 以外的
        用法（例如放進 `sum(1 for _ in ...)`）也不會把失敗延後到看不出因果的地方。
    """
    routes = _as_routes(source)
    if _iter_route_contexts is None:
        return iter(_flat_api_routes(routes))
    return iter(_context_api_routes(routes))


def count_mounted_api_routes(source: FastAPI | APIRouter | Sequence[Any]) -> int:
    return sum(1 for _ in iter_mounted_api_routes(source))


# OpenAPI 的 path item object 裡，哪些 key 才是「一條路由」。
# 規格允許 path item 同時放 `parameters` / `summary` / `description` / `servers` / `$ref`
# 等非 operation 欄位（FastAPI 目前不產，但那是實作巧合、不是保證）。把它們當成路由會
# 憑空生出「缺少的路由」而誤擋啟動，所以只認這八個 HTTP method。
_OPENAPI_OPERATION_KEYS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def _openapi_operations(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """把 OpenAPI schema 攤成 `{(path, METHOD)}`——本模組對帳的**唯一單位**。

    刻意不是 path 集合。本 repo 的 19 支 router 共 106 條路由，只塌成 83 條 path：
    以 path 對帳等於自願放掉方法級的解析度，「掛上了 GET、卻掉了同路徑的 PUT/DELETE」
    會讓差集為空 → 記 ERROR 放行 → 那批寫入 API 全 404 而自我檢查一聲不吭。
    （`mount_v2_routers` 的快樂路徑早就是逐 path＋method 對帳，這裡是把第二意見那層
    也拉到同一個單位——三種「路由數量」單位並存時，下一個人最可能踩的就是把
    「走訪器的 path＋method 條數」拿去減「OpenAPI 的 path 數」。）
    """
    return {
        (path, method.upper())
        for path, item in (schema.get("paths") or {}).items()
        for method in (item or {})
        if method.lower() in _OPENAPI_OPERATION_KEYS
    }


def _framework_operations(routes: Sequence[Any], what: str) -> set[tuple[str, str]]:
    """第二意見：用 FastAPI 自己的 OpenAPI 產生器看這批 routes 有哪些 (path, method)。

    為什麼是它而不是我們的走訪器：`get_openapi()` 跟框架同版本、必然懂當版的路由
    結構（實測 0.121/0.136.3/0.137.0/0.137.2/0.141.1 全部認得，含 0.137.0 那個
    「有容器、沒走訪器」的空窗）。而且它吃的是 routes 序列、不經 `include_router`，
    所以「router 本身真的空」跟「掛載被弄壞了」可以分開判。

    只在對帳出現異常時才呼叫（產 schema 不便宜）。
    """
    try:
        schema = get_openapi(title="route-registry probe", version="0", routes=list(routes))
    except Exception as exc:  # noqa: BLE001 — 連第二意見都拿不到就沒有放行的理由
        raise RuntimeError(
            f"v2 router 掛載自我檢查失敗，且無法對「{what}」產生 OpenAPI 作為交叉驗證："
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return _openapi_operations(schema)


def _app_openapi_operations(app: FastAPI) -> set[tuple[str, str]]:
    """app 眼中真正掛上去的 (path, method)（框架自產）。

    產完把 `openapi_schema` 快取清掉：本函式是在 `create_app()` **中途**被呼叫的
    （`mount_v2_routers` 之後還會加 `GET /`），留著快取會讓線上 /openapi.json
    供應一份少了那幾條的過期 schema。
    """
    try:
        return _openapi_operations(app.openapi())
    except Exception as exc:  # noqa: BLE001 — 連第二意見都拿不到就沒有放行的理由
        raise RuntimeError(
            "v2 router 掛載自我檢查失敗，且無法產生 app 的 OpenAPI 作為交叉驗證："
            f"{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        app.openapi_schema = None


def _try_count(source: FastAPI | APIRouter | Sequence[Any]) -> int | None:
    """數得出來回數字；走訪器看不懂結構回 `None`（不可信 ≠ 0 條）。"""
    try:
        return count_mounted_api_routes(source)
    except RouteTraversalUnsupported:
        return None


def mount_v2_routers(
    app: FastAPI,
    routers: Iterable[tuple[str, APIRouter]] = V2_ROUTERS,
) -> int:
    """把全部 v2 router 掛上 `app`，並確認**真的掛上去了**。回傳新增的路由數。

    對帳而不是比對魔術數字：期望值直接由 router 自己宣告的路由數加總而來，
    所以新增/刪除端點不用同步改門檻，但「掛了等於沒掛」一定當場爆。

    判準只有一條：**只要無法證明 API 面存在，就 raise；證明得了就放行。**
    快樂路徑完全由我們的走訪器對帳（便宜）；一旦出現任何異常
    （走訪器看不懂結構／有 router 看起來是空的／掛完條數短少），就不再相信自己的
    走訪結果，改由 FastAPI 自己的 OpenAPI 產生器裁決：

    - 框架說「這些 router 本來就沒有路由」→ 真實迴歸 → raise（那組 API 一定全 404）。
    - 框架說「有路由，但 app 上找不到」→ 路由真的沒掛上 → raise（服務起得來但少 API）。
    - 框架說「有路由，app 上也都在」→ API 面完整，是**我們的走訪器**壞了。
      abort 只會製造一次自找的停機，故改記 `logger.error`，由
      `tests/unit/test_route_mounting.py` 的 OpenAPI 對照測試在 CI 擋下。

    ⚠️ 這裡刻意**不**再用「某支 router 是空的就無條件 raise」：那條規則跟上一段的
    取捨自相矛盾（同一個走訪器，一邊拿 OpenAPI 覆核、一邊直接 abort），而且
    raise 在 `include_router` 之前，連第二意見都問不到。實測「把 `APIRouter.routes`
    也換成不透明結構」時，它會對一個 OpenAPI 有 83 條 path、`/api/v2/me` 好好的 app
    喊「19 支 router 一條路由都沒有」並拒絕啟動——正是要避免的那種停機。
    """
    pairs = list(routers)
    declared: dict[str, list[MountedApiRoute] | None] = {}
    for name, router in pairs:
        try:
            declared[name] = list(iter_mounted_api_routes(router))
        except RouteTraversalUnsupported as exc:
            logger.error("走訪 v2 router %r 的路由表失敗：%s", name, exc)
            declared[name] = None

    readable = {name: routes for name, routes in declared.items() if routes is not None}
    suspect = len(readable) < len(pairs) or any(not routes for routes in readable.values())

    # 逐條（path＋method）對帳，不是逐 path：同一路徑掛 GET/PUT 算兩條，
    # 用 path 數當期望值會讓「少掛一半的 method」溜過去。
    expected = sum(len(routes) for routes in readable.values())
    before = _try_count(app)
    for _name, router in pairs:
        app.include_router(router)
    after = _try_count(app)
    added = None if before is None or after is None else after - before

    if not suspect and added is not None and added >= expected:
        return added

    _reconcile_with_framework(app, pairs, declared, expected, added)
    return added or 0


def _reconcile_with_framework(
    app: FastAPI,
    pairs: Sequence[tuple[str, APIRouter]],
    declared: dict[str, list[MountedApiRoute] | None],
    expected: int,
    added: int | None,
) -> None:
    """異常時的裁決：一律以框架自產的 OpenAPI 為準（見 `mount_v2_routers` docstring）。"""
    counted = "走訪器看不懂 app.routes 的結構" if added is None else f"掛上後只數到 {added} 條"
    shortfall = (
        f"v2 router 掛載自我檢查：走訪器宣告 {expected} 條、{counted}。"
        "可能原因：(a) FastAPI 又改了路由表的資料結構，"
        f"`{__name__}.iter_mounted_api_routes` 需要跟上（0.137 起子路由改成延遲展開的 "
        "_IncludedRouter，直接走訪 app.routes 會一條都看不到）；(b) 路由真的沒掛上去。"
    )

    truly_empty = sorted(
        name for name, router in pairs if not _framework_operations(router.routes, f"router {name}")
    )
    if truly_empty:
        raise RuntimeError(
            f"{shortfall} 且框架自己的 OpenAPI 也證實這些 v2 router 一條路由都沒有：{truly_empty}。"
            "include_router() 對空 router 是靜默 no-op，服務會起得來但那些 API 全部 404——"
            "請確認對應模組的 @router.<method> 裝飾器仍在，且模組沒有被 import 失敗後吞掉。"
        )

    # 逐 (path, method) 對帳：只比 path 的話，「同路徑掛上 GET、掉了 PUT/DELETE」
    # 會讓差集為空而放行（106 條路由只有 83 條 path，一半以上的方法沒有獨立 path）。
    declared_ops = _framework_operations(
        [route for _name, router in pairs for route in router.routes], "全部 v2 router"
    )
    missing = sorted(declared_ops - _app_openapi_operations(app))
    if missing:
        shown = [f"{method} {path}" for path, method in missing[:10]]
        raise RuntimeError(
            f"{shortfall} OpenAPI 也看不到這些路由：{shown}"
            f"{'…' if len(missing) > 10 else ''}——"
            f"這個 app 少了上列 API（共 {len(missing)} 條 path＋method），拒絕啟動。"
        )

    blind = sorted(name for name, routes in declared.items() if routes is None)
    logger.error(
        "%s 但 OpenAPI 顯示路由都在（API 面完整，%d 條 path＋method），故不擋啟動。%s"
        "請儘快更新走訪器：在它修好之前，所有靠走訪路由的守衛（DB session scope 等）等於沒在跑。",
        shortfall,
        len(declared_ops),
        f"看不懂結構的 router：{blind}。" if blind else "",
    )
