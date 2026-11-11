"""GET /api/v2/dsx/ui-url——DSX 3D 擺放介面網址（給前端開 iframe modal 用）。

`dsx_ui_url` 與 `dsx_integration_enabled`（a3 距離查詢開關）無關，是獨立設定
（查詢 API 開關 vs 能不能看到 UI 網址是分開的兩件事）；只走 `current_user`（唯讀，
不寫任何東西），比照本檔其他讀取端點的角色門檻。
"""
from __future__ import annotations

import pytest

from ddm_v2.api.routes.v2.dsx import dsx_ui_url
from ddm_v2.auth.deps import CurrentUser
from ddm_v2.settings import get_settings

pytestmark = pytest.mark.unit

_FAKE_USER = CurrentUser(employee_no="IEC141289", roles=["viewer"], site_ids=[])


def test_settings_reads_dsx_ui_url_from_env(monkeypatch):
    monkeypatch.setenv("DDM_DSX_UI_URL", "http://172.32.3.60:8081/most.html")
    get_settings.cache_clear()
    try:
        assert get_settings().dsx_ui_url == "http://172.32.3.60:8081/most.html"
    finally:
        get_settings.cache_clear()


def test_settings_dsx_ui_url_defaults_to_none(monkeypatch):
    monkeypatch.delenv("DDM_DSX_UI_URL", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().dsx_ui_url is None
    finally:
        get_settings.cache_clear()


def test_settings_dsx_ui_url_with_invalid_scheme_treated_as_unset(monkeypatch, caplog):
    """非 http(s) 的值（例如 javascript: 或裸主機名）視同未設定，且記一行 WARNING。"""
    monkeypatch.setenv("DDM_DSX_UI_URL", "javascript:alert(1)")
    get_settings.cache_clear()
    try:
        with caplog.at_level("WARNING"):
            assert get_settings().dsx_ui_url is None
        assert "DDM_DSX_UI_URL" in caplog.text
    finally:
        get_settings.cache_clear()


def test_settings_dsx_ui_url_is_independent_of_integration_enabled(monkeypatch):
    """未開 `DDM_DSX_INTEGRATION_ENABLED` 時 `dsx_ui_url` 仍照常讀出（兩者不綁定）。"""
    monkeypatch.delenv("DDM_DSX_INTEGRATION_ENABLED", raising=False)
    monkeypatch.setenv("DDM_DSX_UI_URL", "http://172.32.3.60:8081/most.html")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.dsx_integration_enabled is False
        assert settings.dsx_ui_url == "http://172.32.3.60:8081/most.html"
    finally:
        get_settings.cache_clear()


async def test_endpoint_returns_configured_url(monkeypatch):
    monkeypatch.setenv("DDM_DSX_UI_URL", "http://172.32.3.60:8081/most.html")
    get_settings.cache_clear()
    try:
        result = await dsx_ui_url(_FAKE_USER)
        assert result.url == "http://172.32.3.60:8081/most.html"
    finally:
        get_settings.cache_clear()


async def test_endpoint_returns_null_when_unset(monkeypatch):
    monkeypatch.delenv("DDM_DSX_UI_URL", raising=False)
    get_settings.cache_clear()
    try:
        result = await dsx_ui_url(_FAKE_USER)
        assert result.url is None
    finally:
        get_settings.cache_clear()


async def test_endpoint_returns_null_when_scheme_invalid(monkeypatch):
    monkeypatch.setenv("DDM_DSX_UI_URL", "ftp://172.32.3.60/most.html")
    get_settings.cache_clear()
    try:
        result = await dsx_ui_url(_FAKE_USER)
        assert result.url is None
    finally:
        get_settings.cache_clear()
