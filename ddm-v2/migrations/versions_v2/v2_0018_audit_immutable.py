"""impl-06d：workflow_audit_log DB 層 append-only 強制（trigger 方式）。

依 ADR-018 裁決 3：workflow_audit_log 為審計不可變日誌；應在 DB 層防止任何人
（除 superuser 外）執行 UPDATE / DELETE，以確保審計完整性。

注意：REVOKE FROM PUBLIC 無法限制 table owner（應用連線角色），因此改用
BEFORE UPDATE/DELETE trigger 在 PL/pgSQL 層拋出例外，對所有角色包含 owner
均有效（superuser 除外）。

Revision ID: v2_0018
Revises: v2_0017
Create Date: 2026-07-11
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "v2_0018"
down_revision = "v2_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 建立防寫 trigger function
    op.execute(text("""
        CREATE OR REPLACE FUNCTION audit_log_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'workflow_audit_log is append-only: UPDATE and DELETE are forbidden';
        END;
        $$
    """))
    # 對 UPDATE 和 DELETE 各綁一個 BEFORE trigger
    op.execute(text("""
        CREATE TRIGGER trg_audit_no_update
        BEFORE UPDATE ON workflow_audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()
    """))
    op.execute(text("""
        CREATE TRIGGER trg_audit_no_delete
        BEFORE DELETE ON workflow_audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()
    """))


def downgrade() -> None:
    op.execute(text("DROP TRIGGER IF EXISTS trg_audit_no_delete ON workflow_audit_log"))
    op.execute(text("DROP TRIGGER IF EXISTS trg_audit_no_update ON workflow_audit_log"))
    op.execute(text("DROP FUNCTION IF EXISTS audit_log_immutable()"))
