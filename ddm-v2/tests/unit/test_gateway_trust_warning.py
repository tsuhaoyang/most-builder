"""C-1（ADR-023 D7）：gateway 模式的信任前提必須在啟動時講出來。

背景：`DDM_AUTH_MODE=gateway`（預設）時 `auth/identity.py` **無條件採信入站的
`X-Username`**——安全性 100% 依賴「本服務只經 gateway 可達」這個部署前提。
這個前提在程式碼裡看不出來，所以 app factory 至少要發一筆 WARNING。

⚠️ 純 log：本檔同時鎖住「不得改變行為」——警告不擋啟動、也不影響路由掛載。

D7b：實作已從 `main.py` 搬到 `auth/startup_checks.py`（讓不走 factory 的入口也叫得到），
本檔改測「經由 `create_app()` 仍然照發」——搬家不得讓既有入口失去警告。
dev-override 與入口涵蓋見 `test_startup_security.py`。
"""
from __future__ import annotations

import logging

import pytest

from ddm_v2.api.route_registry import iter_mounted_api_routes
from ddm_v2.auth.startup_checks import DEV_USER_ENV
from ddm_v2.main import TRUSTED_GATEWAY_ENV, create_app

pytestmark = pytest.mark.unit

_MARKER = "DDM_AUTH_MODE=gateway"  # 警告必須點名模式，否則讀者不知道前提是什麼


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    monkeypatch.delenv("DDM_AUTH_MODE", raising=False)
    monkeypatch.delenv(TRUSTED_GATEWAY_ENV, raising=False)
    # dev override 也會發一筆提到 X-Username 的警告；本檔只驗 gateway 那筆，
    # 且不能因為執行者 shell 裡剛好有 AUTH_DEV_USER 就變紅。
    monkeypatch.delenv(DEV_USER_ENV, raising=False)


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and _MARKER in r.getMessage()
    ]


def test_gateway_mode_emits_warning(caplog):
    """預設（未設 DDM_AUTH_MODE ＝ gateway）就必須警告。"""
    with caplog.at_level(logging.WARNING, logger="ddm_v2.main"):
        create_app()
    msgs = _warnings(caplog)
    assert len(msgs) == 1, f"gateway 模式應發且只發一筆 X-Username 信任警告，收到 {msgs}"
    # 只斷言「有 WARNING」會空洞通過：main.py 本來就會為 DDM_SECRET_KEY 發警告。
    # 訊息必須說得出「信任什麼」與「該怎麼辦」，否則讀到的人無法行動。
    assert "X-Username" in msgs[0]      # 點名被信任的到底是什麼
    assert TRUSTED_GATEWAY_ENV in msgs[0]


def test_explicit_gateway_mode_emits_warning(caplog, monkeypatch):
    monkeypatch.setenv("DDM_AUTH_MODE", "GATEWAY")  # 大小寫不敏感
    with caplog.at_level(logging.WARNING, logger="ddm_v2.main"):
        create_app()
    assert len(_warnings(caplog)) == 1


def test_trusted_gateway_declared_silences_warning(caplog, monkeypatch):
    """營運者宣告「已確認只經 gateway 可達」後不再嘮叨（否則警告會被當噪音忽略）。"""
    monkeypatch.setenv(TRUSTED_GATEWAY_ENV, "1")
    with caplog.at_level(logging.WARNING, logger="ddm_v2.main"):
        create_app()
    assert _warnings(caplog) == []


def test_verify_mode_does_not_warn(caplog, monkeypatch):
    """verify 模式不讀 client 的 X-Username（身分來自 LB 驗證回應）→ 不適用本警告。"""
    monkeypatch.setenv("DDM_AUTH_MODE", "verify")
    with caplog.at_level(logging.WARNING, logger="ddm_v2.main"):
        create_app()
    assert _warnings(caplog) == []


def test_warning_does_not_block_startup(caplog):
    """純 log：不得擋啟動、不得改變路由掛載（本機開發與 CI 必須照常跑）。"""
    with caplog.at_level(logging.WARNING, logger="ddm_v2.main"):
        app = create_app()
    assert _warnings(caplog), "前提：本案例確實走到會警告的分支"
    # ⚠️ 不要改回 `for r in app.routes`：FastAPI >= 0.141 的 include_router 是延遲展開
    # （app.routes 只放 _IncludedRouter），直接走訪會一條 API 都看不到 —— 這正是本測試
    # 曾經在 CI（新版）紅、本機（舊版）綠的原因。走訪一律走 route_registry。
    paths = {r.path for r in iter_mounted_api_routes(app)}
    assert "/api/v2/rule-sets/{code}/full" in paths
