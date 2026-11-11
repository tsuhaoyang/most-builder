SHELL := /bin/bash

# Default: local development compose (includes db host port publish).
COMPOSE_FILES ?= -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE := docker compose $(COMPOSE_FILES)

# Optional .env import (does not fail if missing).
ifneq (,$(wildcard .env))
include .env
export
endif

BACKUP_DIR ?= data/backups
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)
BACKUP_FILE ?= $(BACKUP_DIR)/ddm_v2_$(TIMESTAMP).sql
V3_DB_HOST ?= ../ddm-v3/apps/api/minimost.db
V3_DB_CONTAINER ?= /tmp/minimost.db

.PHONY: help \
	lock audit docker-smoke \
	up down stop restart build rebuild-app ps logs \
	db-shell db-backup db-restore db-reset db-wipe \
	seed-demo v3-db-stage v3-migrate-dryrun v3-migrate v3-migration-dryrun v3-migration \
	guard-dev-only backup-before-destroy destroy-safe destroy

help:
	@echo "DDM v2 Make targets"
	@echo ""
	@echo "Dependencies (see docs/CI_GATES.md「依賴鎖版與安全稽核」):"
	@echo "  make lock               Regenerate all three requirements*.lock after editing pyproject deps."
	@echo "  make audit              pip-audit all three lock files (same script CI runs)."
	@echo "  make docker-smoke       Build image + run container smoke (endpoints + GM=28/CM=29)."
	@echo ""
	@echo "Service lifecycle:"
	@echo "  make up                 Start db + app (with dev overlay)."
	@echo "  make down               Stop and remove containers (keep volumes)."
	@echo "  make stop               Stop containers only."
	@echo "  make restart            Restart services."
	@echo "  make build              Build app image."
	@echo "  make rebuild-app        Rebuild and start app only."
	@echo "  make ps                 Show compose status."
	@echo "  make logs               Tail app+db logs."
	@echo ""
	@echo "Database:"
	@echo "  make db-shell           Open psql in db container."
	@echo "  make db-backup          Dump DB to data/backups/."
	@echo "  make db-restore BACKUP=path CONFIRM=YES"
	@echo "                          Restore SQL dump into current DB."
	@echo "  make db-reset CONFIRM=YES"
	@echo "                          Drop+recreate public schema (destructive)."
	@echo "  make db-wipe CONFIRM=YES"
	@echo "                          Alias of db-reset."
	@echo ""
	@echo "Seeds / migration:"
	@echo "  make seed-demo          Run dev seeds in app container (idempotent)."
	@echo "  make v3-db-stage        Copy v3 SQLite from host to app container."
	@echo "  make v3-migrate-dryrun  Dry run v3 user-data migration."
	@echo "  make v3-migrate CONFIRM=YES"
	@echo "                          Execute v3 user-data migration."
	@echo "  make v3-migration-dryrun"
	@echo "                          Alias of v3-migrate-dryrun."
	@echo "  make v3-migration CONFIRM=YES"
	@echo "                          Alias of v3-migrate."
	@echo ""
	@echo "Danger zone:"
	@echo "  make destroy-safe CONFIRM=YES"
	@echo "                          Guard dev-only + auto backup + down -v."
	@echo "  make destroy CONFIRM=YES"
	@echo "                          Alias of destroy-safe."
	@echo "  ALLOW_PROD_DESTRUCTIVE=YES"
	@echo "                          Bypass dev-only guard (not recommended)."
	@echo ""
	@echo "Advanced:"
	@echo "  COMPOSE_FILES='-f docker-compose.yml' make up"
	@echo "  BACKUP_FILE=data/backups/custom.sql make db-backup"
	@echo "  V3_DB_HOST=/path/minimost.db make v3-migrate-dryrun"

# 改了 pyproject 的依賴宣告（含 [build-system].requires）後必跑，
# 三個 .lock 與 requirements-build.in 一起 commit（否則 CI 的 deps job 會紅）。
# 顯式升級：make lock ARGS="--upgrade-package fastapi"
lock:
	./scripts/lock_deps.sh $(ARGS)

audit:
	./scripts/audit_deps.sh

docker-smoke:
	./scripts/docker_smoke.sh

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

stop:
	$(COMPOSE) stop

restart:
	$(COMPOSE) restart

build:
	$(COMPOSE) build

rebuild-app:
	$(COMPOSE) up -d --build ddm-v2

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f ddm-v2 db

db-shell:
	$(COMPOSE) exec db sh -lc 'psql -U "$$POSTGRES_USER" "$$POSTGRES_DB"'

db-backup:
	@mkdir -p "$(BACKUP_DIR)"
	$(COMPOSE) exec -T db sh -lc 'pg_dump -U "$$POSTGRES_USER" "$$POSTGRES_DB"' > "$(BACKUP_FILE)"
	@echo "Backup created: $(BACKUP_FILE)"

db-restore:
	@test -n "$(BACKUP)" || (echo "ERROR: BACKUP=<path> is required"; exit 1)
	@test -f "$(BACKUP)" || (echo "ERROR: backup file not found: $(BACKUP)"; exit 1)
	@test "$(CONFIRM)" = "YES" || (echo "ERROR: set CONFIRM=YES to proceed"; exit 1)
	cat "$(BACKUP)" | $(COMPOSE) exec -T db sh -lc 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" "$$POSTGRES_DB"'
	@echo "Restore completed from: $(BACKUP)"

db-reset:
	@test "$(CONFIRM)" = "YES" || (echo "ERROR: set CONFIRM=YES to proceed"; exit 1)
	$(COMPOSE) exec -T db sh -lc 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" "$$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
	@echo "Database schema reset completed."

db-wipe: db-reset

seed-demo:
	$(COMPOSE) exec ddm-v2 python3 scripts/dev_seed_v2.py
	$(COMPOSE) exec ddm-v2 python3 scripts/dev_seed_templates.py

v3-db-stage:
	@test -f "$(V3_DB_HOST)" || (echo "ERROR: v3 SQLite not found on host: $(V3_DB_HOST)"; exit 1)
	docker cp "$(V3_DB_HOST)" ddm-v2:$(V3_DB_CONTAINER)

v3-migrate-dryrun: v3-db-stage
	$(COMPOSE) exec ddm-v2 sh -lc 'PYTHONPATH=src python3 scripts/migrate_v3_user_data.py --v3-db $(V3_DB_CONTAINER)'

v3-migrate: v3-db-stage
	@test "$(CONFIRM)" = "YES" || (echo "ERROR: set CONFIRM=YES to proceed"; exit 1)
	$(COMPOSE) exec ddm-v2 sh -lc 'PYTHONPATH=src python3 scripts/migrate_v3_user_data.py --v3-db $(V3_DB_CONTAINER) --execute'

v3-migration-dryrun: v3-migrate-dryrun

v3-migration: v3-migrate


guard-dev-only:
	@if [[ "$(ALLOW_PROD_DESTRUCTIVE)" != "YES" && "$(COMPOSE_FILES)" != *"docker-compose.dev.yml"* ]]; then \
		echo "ERROR: destructive target is blocked without docker-compose.dev.yml"; \
		echo "       If you really need this, set ALLOW_PROD_DESTRUCTIVE=YES"; \
		exit 1; \
	fi

backup-before-destroy:
	$(MAKE) db-backup BACKUP_FILE="$(BACKUP_FILE)"
	@echo "Pre-destroy backup completed: $(BACKUP_FILE)"

destroy-safe: guard-dev-only
	@test "$(CONFIRM)" = "YES" || (echo "ERROR: set CONFIRM=YES to proceed"; exit 1)
	$(MAKE) backup-before-destroy BACKUP_FILE="$(BACKUP_FILE)"
	$(COMPOSE) down -v
	@echo "Destroy completed. Backup saved to: $(BACKUP_FILE)"

destroy: destroy-safe
