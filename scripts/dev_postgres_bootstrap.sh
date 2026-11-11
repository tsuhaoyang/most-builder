#!/usr/bin/env bash
# =============================================================================
# DDM v2 — PostgreSQL 開發環境：啟動 DB、等待就緒、執行 Alembic（可選重置 volume）
#
# 用法:
#   ./scripts/dev_postgres_bootstrap.sh           # 預設：up + migrate
#   ./scripts/dev_postgres_bootstrap.sh migrate   # 僅 alembic upgrade head（需 DB 已 reachable）
#   ./scripts/dev_postgres_bootstrap.sh reset     # 刪除 Postgres volume 後重建 + migrate（開發用）
#   ./scripts/dev_postgres_bootstrap.sh help
#
# 環境變數（與 docker-compose / src/ddm_v2/settings.py 一致）:
#   DATABASE_URL          預設 postgresql+asyncpg://ddm_user:ddm_pass@localhost:5432/ddm_v2
#   POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
#   POSTGRES_HOST_PORT    本機對應埠，預設 5432（與本機 Postgres 衝突時設 55432 等）
#
# -----------------------------------------------------------------------------
# 開發環境 PostgreSQL bootstrap；正式 schema 一律以 Alembic migrations 為準。
#
# 仍須討論／排程後再實作:
#   - 五區塊 IA、工序 topology UI、steps.group_id 與群組語意
#   - MiniMOST params.hand 與主數據「手勢」詞彙 id 的對應方式
#
# Migration 策略:
#   - 建議開發全程使用本倉庫的 Alembic revision 鏈；上線環境同樣執行 `alembic upgrade head`。
#   - 「還在開發、先初始化」在此專案 = 本機 Docker volume 空庫 + 跑完全部 migration（從 0001 到 head），
#     與之後 production 要跑的**是同一套檔案**；不是略過 migration。
#   - 若曾亂試資料想重來：用本腳本 `reset`（僅開發；會刪除 named volume 內資料）。
#   - 上線前若要「壓縮」多個 revision，屬另議（squash / baseline），不影響日常先照鏈遷移。
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

CMD="${1:-up}"

die() { echo "error: $*" >&2; exit 1; }

activate_venv() {
  if [[ -f "${ROOT}/.venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${ROOT}/.venv/bin/activate"
  elif [[ -f "${ROOT}/venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${ROOT}/venv/bin/activate"
  else
    die "找不到 ${ROOT}/.venv 或 ${ROOT}/venv。請先: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
  fi
}

export DDM_ROOT_DIR="${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

# Defaults aligned with docker-compose.yml + settings.py
export POSTGRES_USER="${POSTGRES_USER:-ddm_user}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ddm_pass}"
export POSTGRES_DB="${POSTGRES_DB:-ddm_v2}"
export POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_HOST_PORT}/${POSTGRES_DB}}"

compose() {
  docker compose -f "${ROOT}/docker-compose.yml" "$@"
}

wait_for_pg() {
  echo "[bootstrap] Waiting for PostgreSQL (inside container)..."
  local retries=60
  until compose exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    retries=$((retries - 1))
    if [[ "${retries}" -le 0 ]]; then
      die "Postgres did not become ready in time."
    fi
    sleep 1
  done
  echo "[bootstrap] PostgreSQL is ready."
}

run_migrate() {
  activate_venv
  if ! command -v alembic >/dev/null 2>&1; then
    die "alembic not found in venv; run: pip install -e '.[dev]'"
  fi
  echo "[bootstrap] DATABASE_URL -> ${DATABASE_URL}"
  alembic upgrade head
  echo "[bootstrap] Alembic at head."
}

case "${CMD}" in
  help|-h|--help)
    sed -n '1,35p' "$0"
    exit 0
    ;;
  migrate)
    run_migrate
    ;;
  reset)
    echo "[bootstrap] Stopping stack and removing named volumes (Postgres + ddm-v2 app data volume — 開發重來用)..."
    compose down -v
    echo "[bootstrap] Starting db only..."
    compose up -d db
    wait_for_pg
    run_migrate
    echo "[bootstrap] Done. Optional: docker compose up -d   # 啟動完整 app"
    ;;
  up|"")
    echo "[bootstrap] Starting PostgreSQL container..."
    compose up -d db
    wait_for_pg
    run_migrate
    echo "[bootstrap] Done. DB is on localhost port ${POSTGRES_HOST_PORT}."
    echo "[bootstrap] Optional: docker compose up -d   # 啟動 ddm-v2 + db"
    ;;
  *)
    die "unknown command: ${CMD} (use help)"
    ;;
esac
