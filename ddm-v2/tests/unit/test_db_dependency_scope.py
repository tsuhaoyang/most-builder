"""ADR-022 批次 E-1 回歸守門：get_db_session 依賴必須全數 scope="function"。

根因：FastAPI 預設 request scope 會把 dependency generator 的 teardown（含
get_db_session 的 commit）排在 response 送出之後，造成 create→立即讀取 的
可見性 race（POST 回應先於 commit 可見）。

本測試靜態走訪 app 全部路由的 dependant tree：
1. 任何指向 get_db_session 的依賴，computed_scope 必須是 "function"
   （commit 在 response 送出前執行）。
2. 不得混用 scope——dependency cache key 含 scope，混用會在同一請求
   開出兩條 session（auth 與路由各拿一條，交易語意破裂）。
"""
from __future__ import annotations

from fastapi.routing import APIRoute

from ddm_v2.database import get_db_session
from ddm_v2.main import create_app


def _walk(dependant, found: list) -> None:
    for sub in dependant.dependencies:
        if sub.call is get_db_session:
            found.append(sub)
        _walk(sub, found)


def test_all_db_session_dependencies_are_function_scoped():
    app = create_app()
    offenders: list[str] = []
    total = 0
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        found: list = []
        _walk(route.dependant, found)
        for dep in found:
            total += 1
            if dep.computed_scope != "function":
                offenders.append(f"{route.methods} {route.path} -> scope={dep.computed_scope!r}")
    assert total > 0, "找不到任何 get_db_session 依賴——測試走訪邏輯失效"
    assert not offenders, (
        "以下路由的 get_db_session 依賴不是 scope='function'（commit 會在 "
        "response 送出後才跑，重現 create→404 race）：\n" + "\n".join(offenders)
    )
