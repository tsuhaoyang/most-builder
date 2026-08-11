from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _parse_csv(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return fallback
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed or fallback


def _parse_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    tmu_factor: float
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
        tmu_factor=float(os.getenv("DDM_TMU_FACTOR", "0.036")),
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
    )


ROOT_DIR = get_settings().root_dir
DATA_DIR = get_settings().data_dir

SECRET_KEY = get_settings().secret_key
ACCESS_TOKEN_EXPIRE_HOURS = get_settings().access_token_expire_hours
TMU_FACTOR = get_settings().tmu_factor

APP_NAME = get_settings().app_name
APP_VERSION = get_settings().app_version
