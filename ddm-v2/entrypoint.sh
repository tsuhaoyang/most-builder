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

echo "[entrypoint] Starting DDM v2..."
exec uvicorn ddm_v2.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --app-dir src
