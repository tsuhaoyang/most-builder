"""ADR-022 批次 E-1 回歸守門：get_db_session 依賴必須全數 scope="function"。

根因：FastAPI 預設 request scope 會把 dependency generator 的 teardown（含
get_db_session 的 commit）排在 response 送出之後，造成 create→立即讀取 的
可見性 race（POST 回應先於 commit 可見）。

本測試靜態走訪 app 全部路由的 dependant tree：
1. 任何指向 get_db_session 的依賴，都必須**顯式**宣告 `Depends(..., scope="function")`
   （commit 在 response 送出前執行）。
2. 不得混用 scope——dependency cache key 含 scope，混用會在同一請求
   開出兩條 session（auth 與路由各拿一條，交易語意破裂）。

⚠️ 兩處版本相依，都是被 FastAPI 0.141 絆過的：
- 路由走訪一律經 `route_registry.iter_mounted_api_routes`：0.141 起 include_router
  改成延遲展開，`for route in app.routes` 會一條 API 都撈不到，本測試會退化成
  「迴圈跑 0 次」的假綠（當時是靠 total > 0 才變紅）。
- 斷言看 `Dependant.scope`（宣告值）而不是 `Dependant.computed_scope`：後者在 0.141
  從 cached_property 變成模組私有函式 `_get_computed_scope()`，直接讀會 AttributeError。
  兩者對本測試等價——`get_db_session` 是 async generator，沒顯式宣告時 computed 出來
  一定是 "request"（就是我們要防的那個 bug），所以「宣告值必須是 function」與
  「computed 值必須是 function」對每一種輸入都同結論，且不依賴框架私有 API。
"""
from __future__ import annotations

import inspect

from ddm_v2.api.route_registry import iter_mounted_api_routes
from ddm_v2.database import get_db_session
from ddm_v2.main import create_app


def test_premise_get_db_session_is_an_async_generator():
    """「宣告值＝computed 值」的等價前提（見模組 docstring）。

    若哪天 get_db_session 不再是 generator，未宣告 scope 的 computed 值會變成 None
    而不是 "request"，等價論證要重新檢查——所以把前提釘在這裡，而不是留在註解裡。
    """
    assert inspect.isasyncgenfunction(get_db_session)


def _walk(dependant, found: list) -> None:
    for sub in dependant.dependencies:
        if sub.call is get_db_session:
            found.append(sub)
        _walk(sub, found)


def test_all_db_session_dependencies_are_function_scoped():
    app = create_app()
    offenders: list[str] = []
    total = 0
    for route in iter_mounted_api_routes(app):
        found: list = []
        _walk(route.dependant, found)
        for dep in found:
            total += 1
            if dep.scope != "function":
                offenders.append(f"{route.label} -> scope={dep.scope!r}")
    assert total > 0, "找不到任何 get_db_session 依賴——測試走訪邏輯失效"
    assert not offenders, (
        "以下路由的 get_db_session 依賴不是 scope='function'（commit 會在 "
        "response 送出後才跑，重現 create→404 race）：\n" + "\n".join(offenders)
    )
