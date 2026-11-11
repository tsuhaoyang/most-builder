"""ADR-023 D7b · M-1：CORS 的「未設定」不得等於「最寬鬆」。

`allow_origins=['*']` ＋ `allow_credentials=True` 這個組合下 Starlette **不會**回
`Access-Control-Allow-Origin: *`，而是鏡射請求的 `Origin` 並加 `Vary: Origin`——
效果是「允許任意來源攜帶憑證」。在 `DDM_AUTH_MODE=verify`（.env.example 的建議值）下，
受害者於 LB 登入後造訪惡意站，該站 `fetch(..., {credentials:'include'})` 就能讀走整份
字典/worksheet/使用者清單，並發得出 PUT/DELETE（methods 原本也 fallback `*`）。

本檔鎖兩件事：fallback 本身安全（結構），以及顯式的互斥設定會 fail-closed（行為）。
最後一個測試用真的 Starlette middleware 驗「鏡射 Origin」確實會發生——
否則前面的斷言只是在描述一個沒人證實過的威脅。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from ddm_v2.main import _validate_cors_security, create_app
from ddm_v2.settings import Settings, get_settings

pytestmark = pytest.mark.unit

_CORS_ENV = (
    "DDM_CORS_ALLOW_ORIGINS",
    "DDM_CORS_ALLOW_CREDENTIALS",
    "DDM_CORS_ALLOW_METHODS",
    "DDM_CORS_ALLOW_HEADERS",
)


@pytest.fixture(autouse=True)
def _no_cors_env(monkeypatch):
    """清掉 CORS 環境變數 → 測到的就是「未設定」時的預設。"""
    for name in _CORS_ENV:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _with(**overrides) -> Settings:
    from dataclasses import replace

    return replace(get_settings(), **overrides)


def test_default_origins_are_not_wildcard():
    """未設定時的 fallback 不得是 `*`（那是「最寬鬆」）。"""
    settings = get_settings()
    assert "*" not in settings.cors_allow_origins
    assert settings.cors_allow_origins, "也不能是空清單（那會讓合法的本機開發無聲失敗）"
    assert all(o.startswith("http://127.0.0.1") or o.startswith("http://localhost")
               for o in settings.cors_allow_origins), \
        f"預設只該放本機來源，收到 {settings.cors_allow_origins}"


def test_default_methods_and_headers_are_not_wildcard():
    """methods/headers 一起收斂：`*` 的 methods 讓惡意站發得出 PUT/DELETE。"""
    settings = get_settings()
    assert "*" not in settings.cors_allow_methods
    assert "*" not in settings.cors_allow_headers


def test_default_config_does_not_form_the_dangerous_combo():
    """本檔的核心命題：未設定任何環境變數時，不得出現 `*` ＋ credentials。"""
    settings = get_settings()
    assert not ("*" in settings.cors_allow_origins and settings.cors_allow_credentials)


def test_default_config_starts_up():
    """fail-closed 不得誤傷預設路徑——沒設環境變數時 app 必須照常建得起來。"""
    assert create_app() is not None


def test_wildcard_with_credentials_fails_closed():
    """顯式設成互斥組合 → 啟動失敗，不得只 warn、更不得靜默降級 credentials。"""
    settings = _with(cors_allow_origins=["*"], cors_allow_credentials=True)
    with pytest.raises(RuntimeError) as exc:
        _validate_cors_security(settings)
    msg = str(exc.value)
    # 訊息要說得出「哪兩個設定衝突」與「兩條可行的解」，否則營運者只能亂試。
    assert "DDM_CORS_ALLOW_ORIGINS" in msg
    assert "DDM_CORS_ALLOW_CREDENTIALS" in msg


def test_wildcard_among_other_origins_still_fails():
    """`*` 混在清單裡一樣危險（Starlette 只要看到 `*` 就進 wildcard 分支）。"""
    settings = _with(
        cors_allow_origins=["https://most.example.com", "*"], cors_allow_credentials=True
    )
    with pytest.raises(RuntimeError):
        _validate_cors_security(settings)


def test_wildcard_without_credentials_is_allowed():
    """沒有 credentials 就沒有這個攻擊面——不要順手把公開唯讀 API 一起擋掉。"""
    _validate_cors_security(_with(cors_allow_origins=["*"], cors_allow_credentials=False))


def test_explicit_origins_with_credentials_is_allowed():
    """列出具體來源＋credentials 是正當設定（正式部署就是這樣）。"""
    _validate_cors_security(
        _with(cors_allow_origins=["https://most.example.com"], cors_allow_credentials=True)
    )


def test_starlette_really_mirrors_origin_in_the_forbidden_combo():
    """證明被禁的組合確實會鏡射任意 Origin（本檔的威脅前提不是傳說）。

    沒有這個案例，上面所有斷言都只是在複述一個未經驗證的說法。
    """
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    resp = TestClient(app).get("/ping", headers={"Origin": "https://evil.example"})
    assert resp.headers["access-control-allow-origin"] == "https://evil.example"
    assert resp.headers["access-control-allow-credentials"] == "true"
