#!/bin/sh
set -e

echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head

echo "[entrypoint] Seeding bootstrap admin (app_users) if not exists..."
python3 - <<'PYEOF'
import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/src")

from sqlalchemy import text

from ddm_v2.database import get_engine

# v2 RBAC：以員工編號為鍵的 app_users（非 legacy users 表）
ADMIN_EMP = os.getenv("DDM_ADMIN_EMPLOYEE_NO", "IEC141289")


async def seed():
    engine = get_engine()
    async with engine.begin() as conn:
        row = await conn.execute(
            text("SELECT id FROM app_users WHERE employee_no = :e"), {"e": ADMIN_EMP}
        )
        if row.fetchone():
            print(f"[seed] admin '{ADMIN_EMP}' already exists, skipping.")
        else:
            await conn.execute(
                text(
                    "INSERT INTO app_users (id, employee_no, display_name, roles, site_ids, is_active) "
                    "VALUES (:id, :e, :e, ARRAY['admin']::text[], '{}'::uuid[], TRUE)"
                ),
                {"id": uuid.uuid4(), "e": ADMIN_EMP},
            )
            print(f"[seed] created admin '{ADMIN_EMP}'.")
    await engine.dispose()


asyncio.run(seed())
PYEOF

# 種子資料：rule-set（MINIMOST_FACTORY_V1，計算必需）+ demo worksheet(5555) + 詞彙 + 範本。
# 皆 idempotent。DDM_SEED_DEMO=true 才執行（過渡部署建議開；正式上線改自管資料時關掉）。
if [ "${DDM_SEED_DEMO:-false}" = "true" ]; then
  echo "[entrypoint] DDM_SEED_DEMO=true → seeding rule-set + demo worksheet + templates (idempotent)..."
  python3 scripts/dev_seed_v2.py || echo "[entrypoint] dev_seed_v2 failed (continuing)"
  python3 scripts/dev_seed_templates.py || echo "[entrypoint] dev_seed_templates failed (continuing)"
fi

echo "[entrypoint] Starting DDM v2..."
exec uvicorn ddm_v2.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --app-dir src
