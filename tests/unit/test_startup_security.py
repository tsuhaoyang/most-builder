"""ADR-023 D7b：啟動期安全設定（C-1 殘留 ＋ M-1 CORS）。

三件被複驗點名的事，各自鎖住：

1. **dev override 必須被講出來**：`AUTH_DEV_USER` 有值時服務是「以某員編免認證運作」
   ——比 gateway 前提更嚴重（連 header 都不用偽造）。
2. **警告不得只掛在 `create_app()`**：不走 factory 的入口（`scripts/preview_server.py`）
   同樣要發；而且**未來新增的入口忘了叫，測試要變紅**。
3. **preview_server 預設綁 loopback**：它以 admin 身分免認證運作，綁 0.0.0.0
   等同把零憑證 admin 開給整個網段。
4. **CORS 的「未設定」不得等於「最寬鬆」**：`allow_origins=['*']` ＋
   `allow_credentials=True` 會讓 Starlette 鏡射任意 Origin。
"""
from __future__ import annotations

import ast
import importlib
import logging
from pathlib import Path

import pytest

from ddm_v2.auth.startup_checks import (
    DEV_USER_ENV,
    TRUSTED_GATEWAY_ENV,
    warn_if_identity_config_insecure,
)

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
PREVIEW_SERVER = SCRIPTS_DIR / "preview_server.py"
WARN_FUNC = "warn_if_identity_config_insecure"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DDM_AUTH_MODE", raising=False)
    monkeypatch.delenv(TRUSTED_GATEWAY_ENV, raising=False)
    monkeypatch.delenv(DEV_USER_ENV, raising=False)
    monkeypatch.delenv("ENV", raising=False)


def _warnings(caplog, marker: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and marker in r.getMessage()
    ]


# ── 1. dev override 警告 ──────────────────────────────────────────
def test_dev_override_emits_warning(caplog, monkeypatch):
    """`AUTH_DEV_USER` 有值 → 警告必須指名道姓「以誰的身分免認證運作」。"""
    monkeypatch.setenv(DEV_USER_ENV, "IEC141289")
    with caplog.at_level(logging.WARNING):
        warn_if_identity_config_insecure()
    msgs = _warnings(caplog, DEV_USER_ENV)
    assert len(msgs) == 1, f"dev override 應發且只發一筆警告，收到 {msgs}"
    # 只斷言「有警告」會空洞通過（同一次呼叫本來就會發 gateway 那筆）。
    # 必須含員編＋「免認證」語意，讀的人才知道嚴重性。
    assert "IEC141289" in msgs[0]
    assert "免認證" in msgs[0]


def test_no_dev_user_no_warning(caplog):
    """沒設 AUTH_DEV_USER → 不得發這筆（否則警告變噪音）。"""
    with caplog.at_level(logging.WARNING):
        warn_if_identity_config_insecure()
    assert _warnings(caplog, DEV_USER_ENV) == []


def test_dev_override_warns_it_is_ignored_in_production(caplog, monkeypatch):
    """production 下 identity.py 會忽略 dev override → 訊息必須說「被忽略」而不是嚇人。"""
    monkeypatch.setenv(DEV_USER_ENV, "IEC141289")
    monkeypatch.setenv("ENV", "production")
    with caplog.at_level(logging.WARNING):
        warn_if_identity_config_insecure()
    msgs = _warnings(caplog, DEV_USER_ENV)
    assert len(msgs) == 1
    assert "忽略" in msgs[0]
    assert "免認證" not in msgs[0], "production 下它不生效，不該宣稱服務正在免認證運作"


def test_dev_override_and_gateway_warn_independently(caplog, monkeypatch):
    """兩個問題同時成立時要各發一筆——合併成一筆會讓其中一個被漏讀。"""
    monkeypatch.setenv(DEV_USER_ENV, "IEC141289")
    with caplog.at_level(logging.WARNING):
        warn_if_identity_config_insecure()
    assert len(_warnings(caplog, DEV_USER_ENV)) == 1
    assert len(_warnings(caplog, "DDM_AUTH_MODE=gateway")) == 1


def test_trusted_gateway_declaration_leaves_a_trace(caplog, monkeypatch):
    """已宣告 → 不再警告，但必須留一筆 INFO，且說明這是**宣告不是驗證**（D7b · L-2）。"""
    monkeypatch.setenv(TRUSTED_GATEWAY_ENV, "1")
    with caplog.at_level(logging.INFO):
        warn_if_identity_config_insecure()
    infos = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.INFO and TRUSTED_GATEWAY_ENV in r.getMessage()
    ]
    assert len(infos) == 1, f"宣告本身應留下軌跡，收到 {infos}"
    assert "不是驗證" in infos[0]
    assert _warnings(caplog, "DDM_AUTH_MODE=gateway") == []


# ── 2. 入口涵蓋（結構性，不只修 preview_server 一支）─────────────────
def _entrypoint_scripts() -> list[Path]:
    """`scripts/` 底下自行起 server 的檔案（呼叫 `uvicorn.run`）。"""
    found = []
    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        if "uvicorn.run" in path.read_text(encoding="utf-8"):
            found.append(path)
    return found


def _warn_calls(path: Path) -> list[ast.Call]:
    """檔案裡對 `warn_if_identity_config_insecure(...)` 的呼叫（AST，不是字串比對）。

    字串比對會被 `import` 那一行滿足——「匯入了但沒呼叫」正是要抓的失效模式。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) == WARN_FUNC
             or getattr(node.func, "attr", None) == WARN_FUNC)
    ]


def test_every_uvicorn_entrypoint_calls_the_warning():
    """任何自己 `uvicorn.run` 的入口都必須呼叫 `warn_if_identity_config_insecure()`。

    這條是本批的**結構性**要求：D7 把警告掛在 `create_app()` 裡，等於預設「不走 factory
    的入口默默沒有警告」。修好 preview_server 一支不夠——未來有人再加一支 script，
    這個測試要替他發現漏掉。
    """
    entrypoints = _entrypoint_scripts()
    assert PREVIEW_SERVER in entrypoints, "掃描器失效（找不到已知的 preview_server 入口）"
    missing = [p.name for p in entrypoints if not _warn_calls(p)]
    assert missing == [], (
        f"這些入口自行啟動 server 卻沒呼叫 {WARN_FUNC}()："
        f"{missing}——不走 create_app() 就拿不到啟動期安全警告。"
    )


def test_preview_server_warning_is_module_level_not_main_guard():
    """警告必須在 module 匯入時就發，不能藏在 `if __name__ == '__main__'` 裡。

    否則以 `uvicorn scripts.preview_server:app` 之類的方式載入就再次靜默。
    """
    tree = ast.parse(PREVIEW_SERVER.read_text(encoding="utf-8"))
    module_level_calls = [
        node for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == WARN_FUNC
    ]
    assert len(module_level_calls) == 1, (
        f"preview_server.py 應在 module 層呼叫一次 {WARN_FUNC}()"
    )
    assert len(_warn_calls(PREVIEW_SERVER)) == 1, "只該呼叫一次（重複＝同一筆警告發兩次）"


# ── 3. preview_server 綁定位址 ─────────────────────────────────────
def _preview_module():
    import sys

    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        mod = importlib.import_module("preview_server")
        return importlib.reload(mod)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_preview_server_binds_loopback_by_default():
    """預設 127.0.0.1：它以 admin 身分免認證運作，0.0.0.0 等同開放零憑證 admin。"""
    assert _preview_module().resolve_bind_host() == "127.0.0.1"


def test_preview_server_host_is_overridable(monkeypatch):
    """要對外必須做得到（同事看 demo 是真需求），但得是顯式的決定。"""
    mod = _preview_module()
    monkeypatch.setenv("DDM_PREVIEW_HOST", "0.0.0.0")
    assert mod.resolve_bind_host() == "0.0.0.0"


def test_preview_server_does_not_hardcode_bind_host():
    """`uvicorn.run(...)` 的 host 必須來自 `resolve_bind_host()`，不得是字面值。

    只測 `resolve_bind_host()` 會空洞通過：函式回 loopback，`uvicorn.run` 卻仍可寫死
    `"0.0.0.0"`。這裡直接檢查實際傳給 uvicorn 的 argument。
    """
    tree = ast.parse(PREVIEW_SERVER.read_text(encoding="utf-8"))
    hosts = [
        kw.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        for kw in node.keywords
        if kw.arg == "host"
    ]
    assert len(hosts) == 1, "找不到（或找到多個）uvicorn.run(host=...)"
    assert isinstance(hosts[0], ast.Call), "host 不得寫死，應呼叫 resolve_bind_host()"
    assert getattr(hosts[0].func, "id", None) == "resolve_bind_host"
