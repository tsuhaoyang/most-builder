from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_csv(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return fallback
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed or fallback


def _parse_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_http_url(value: str | None, *, env_var: str) -> str | None:
    """防禦性 scheme 檢查：這個值會被前端原樣塞進 `<iframe src>`，不是即時漏洞
    （ops 控制的設定值），但把「這是頁面網址」這個不變式寫進程式很便宜。格式不符時
    視同未設定（回 None），只記 WARNING，不讓應用啟動失敗。
    """
    if not value:
        return None
    if not (value.startswith("http://") or value.startswith("https://")):
        logger.warning(
            "%s 值不是合法的 http(s) URL，視同未設定：%r", env_var, value
        )
        return None
    return value


def _resolve_path(raw: str | None, default: Path, root_dir: Path) -> Path:
    if not raw:
        return default
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (root_dir / candidate).resolve()
    return candidate


# ── CORS 的「未設定」預設（D7b · M-1）────────────────────────────────
# 原本三個 CORS 設定的 fallback 都是 `["*"]`，且 `allow_credentials` fallback 為 True。
# 「未設定」＝「最寬鬆」是危險的預設：Starlette 遇到 `*` ＋ credentials 會鏡射任意
# Origin（見 main._validate_cors_security），等於對所有網站開放已登入的 API。
# 這裡改成 fail-closed——列出本專案實際會用到的本機來源，要放寬必須顯式設環境變數。
#
# 正式部署其實用不到 CORS（前端與 API 同源）；這份預設只服務本機開發：
#   5173＝Vite dev server、8099＝preview_server、8877＝docker compose 對外 port。
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173", "http://localhost:5173",
    "http://127.0.0.1:8099", "http://localhost:8099",
    "http://127.0.0.1:8877", "http://localhost:8877",
)
DEFAULT_CORS_METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
# 身分 header 保留：gateway 模式的前端/測試會帶 X-Username（見 auth/identity.py）。
DEFAULT_CORS_HEADERS: tuple[str, ...] = (
    "Authorization", "Content-Type", "X-Username", "X-User-Id", "X-Plant-Code",
)


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    app_name: str
    app_version: str
    secret_key: str
    access_token_expire_hours: int
    cors_allow_origins: list[str]
    cors_allow_credentials: bool
    cors_allow_methods: list[str]
    cors_allow_headers: list[str]
    database_url: str
    database_echo: bool
    wi_ai_enabled: bool
    wi_ai_auto_enabled: bool
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str
    llm_timeout_s: float
    wi_ai_bundle_code: str
    parse_worker_enabled: bool
    parse_worker_interval_s: float
    parse_worker_batch: int
    dsx_api_base_url: str | None
    dsx_integration_enabled: bool
    dsx_timeout_s: float
    dsx_ui_url: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = Path(os.getenv("DDM_ROOT_DIR", Path(__file__).resolve().parents[2])).resolve()
    data_dir = _resolve_path(os.getenv("DDM_DATA_DIR"), root_dir / "data", root_dir)
    return Settings(
        root_dir=root_dir,
        data_dir=data_dir,
        app_name=os.getenv("DDM_APP_NAME", "DDM v2"),
        app_version=os.getenv("DDM_APP_VERSION", "2.0.0-rc1"),
        secret_key=os.getenv("DDM_SECRET_KEY", "ddm-v2-release-candidate-202603-rc1-secure-key"),
        access_token_expire_hours=int(os.getenv("DDM_ACCESS_TOKEN_EXPIRE_HOURS", "8")),
        cors_allow_origins=_parse_csv(os.getenv("DDM_CORS_ALLOW_ORIGINS"), list(DEFAULT_CORS_ORIGINS)),
        cors_allow_credentials=_parse_bool(os.getenv("DDM_CORS_ALLOW_CREDENTIALS"), True),
        cors_allow_methods=_parse_csv(os.getenv("DDM_CORS_ALLOW_METHODS"), list(DEFAULT_CORS_METHODS)),
        cors_allow_headers=_parse_csv(os.getenv("DDM_CORS_ALLOW_HEADERS"), list(DEFAULT_CORS_HEADERS)),
        database_url=os.getenv("DATABASE_URL", "postgresql+asyncpg://ddm_user:ddm_pass@localhost:5432/ddm_v2"),
        database_echo=_parse_bool(os.getenv("DATABASE_ECHO"), False),
        wi_ai_enabled=_parse_bool(os.getenv("DDM_WI_AI_ENABLED"), False),
        wi_ai_auto_enabled=_parse_bool(os.getenv("DDM_WI_AI_AUTO_ENABLED"), False),
        llm_base_url=os.getenv("DDM_LLM_BASE_URL", "http://127.0.0.1:11434"),
        llm_api_key=os.getenv("DDM_LLM_API_KEY") or None,
        llm_model=os.getenv("DDM_LLM_MODEL", "qwen2.5:32b-instruct"),
        llm_timeout_s=float(os.getenv("DDM_LLM_TIMEOUT_S", "8.0")),
        wi_ai_bundle_code=os.getenv("DDM_WI_AI_BUNDLE_CODE", "wi-ai-dev-000"),
        # ai_parse_jobs 背景 worker（services/v2/parse_job_worker.py）。
        # 預設**開啟**：compose 部署不另設環境變數，預設關閉的 worker 等於沒做
        # （守門存在≠守門有在跑）。測試在 tests/conftest.py 顯式關閉以保確定性。
        parse_worker_enabled=_parse_bool(os.getenv("DDM_PARSE_WORKER_ENABLED"), True),
        parse_worker_interval_s=float(os.getenv("DDM_PARSE_WORKER_INTERVAL_S", "3.0")),
        # 實際上限＝parse_job_service.MAX_TICK_LIMIT（4）：tick 為保 lease 窗
        # （LEASE_SECONDS=60 vs 批次 LLM 耗時）而封頂。設超過時 worker 啟動會
        # WARNING 並以上限執行，不會靜默照單全收。
        parse_worker_batch=int(os.getenv("DDM_PARSE_WORKER_BATCH", "4")),
        dsx_api_base_url=os.getenv("DDM_DSX_API_BASE_URL") or None,
        # 預設關閉：兩邊都在內網、MVP 裁決不加認證層（ADR-031 §5.1），這個旗標不是
        # 資安控制，是變更管理——讓部署環境明確知道「這條會打外部系統的路徑」有沒有開。
        dsx_integration_enabled=_parse_bool(os.getenv("DDM_DSX_INTEGRATION_ENABLED"), False),
        dsx_timeout_s=float(os.getenv("DDM_DSX_TIMEOUT_S", "5.0")),
        # DSX 的 3D 場景 UI 網址（給人看的頁面，不是 data-service API）——與
        # dsx_integration_enabled 無關：a3 距離查詢開關跟能不能看到 UI 網址是分開的兩件事。
        dsx_ui_url=_parse_http_url(os.getenv("DDM_DSX_UI_URL"), env_var="DDM_DSX_UI_URL"),
    )


ROOT_DIR = get_settings().root_dir
DATA_DIR = get_settings().data_dir

SECRET_KEY = get_settings().secret_key
ACCESS_TOKEN_EXPIRE_HOURS = get_settings().access_token_expire_hours

# ⚠️ 不要在這裡加 TMU→秒 的換算設定。
# 這裡曾有 `tmu_factor` / `DDM_TMU_FACTOR`（預設 0.036），但 `most_engine/` 從未讀它——
# 設了完全沒作用，卻看起來像能改換算基準，是會騙人的設定。權威常數是
# `most_engine/rule_set_data.py` 的 `TMU_TO_SEC`（值屬核心邏輯，改動要走 ADR ＋
# scripts/core_logic/run_all.py 的黃金值驗證）。

APP_NAME = get_settings().app_name
APP_VERSION = get_settings().app_version
