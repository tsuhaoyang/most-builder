"""v2_0013: search_documents table (pg_trgm + pgvector optional)

pg_trgm 是 Postgres 內建 extension，此 migration 一定能建。
vector extension 需要 pgvector image——不可用時 embedding 欄位降為 TEXT NULL（見 upgrade()）。

Downgrade: drop table + indexes; extension 保留（可能他表使用）。

Revision ID: v2_0013
Revises: v2_0012
Create Date: 2026-07-09
"""
from __future__ import annotations

import logging

from alembic import op

logger = logging.getLogger(__name__)

revision = "v2_0013"
down_revision = "v2_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. pg_trgm（內建 extension，一定能建）
    conn.execute(
        __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    )

    # 2. pgvector（需要 pgvector image；不可用時記錄 warning 並繼續）
    vector_available = False
    try:
        conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        vector_available = True
        logger.info("v2_0013: pgvector extension 建立成功")
    except Exception as e:  # pragma: no cover
        logger.warning(
            "v2_0013: pgvector extension 不可用（%s）；embedding 欄位降為 TEXT NULL", e
        )

    # 3. 建 search_documents 表
    if vector_available:
        embedding_col = "embedding vector(1024) NULL"
    else:
        embedding_col = "embedding TEXT NULL"

    conn.execute(__import__("sqlalchemy").text(f"""
        CREATE TABLE IF NOT EXISTS search_documents (
            id              uuid PRIMARY KEY,
            doc_type        text NOT NULL CHECK (doc_type IN ('motion_module', 'wi_row', 'vocab', 'worksheet')),
            ref_id          uuid NOT NULL,
            rule_set_id     uuid NULL,
            content_norm    text NOT NULL,
            {embedding_col},
            embedding_model text NULL,
            scope           text NULL,
            owner           text NULL,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (doc_type, ref_id)
        )
    """))

    # 4. trgm GIN index on content_norm
    conn.execute(__import__("sqlalchemy").text("""
        CREATE INDEX IF NOT EXISTS ix_searchdoc_trgm
            ON search_documents USING gin (content_norm gin_trgm_ops)
    """))

    # 5. hnsw index（只在 vector extension 可用時建）
    if vector_available:
        try:
            conn.execute(__import__("sqlalchemy").text("""
                CREATE INDEX IF NOT EXISTS ix_searchdoc_vec
                    ON search_documents USING hnsw (embedding vector_cosine_ops)
            """))
        except Exception as e:  # pragma: no cover
            logger.warning("v2_0013: hnsw index 建立失敗（%s），略過", e)


def downgrade() -> None:
    conn = op.get_bind()
    # DROP TABLE（CASCADE 自動刪 indexes）；extension 不 DROP（可能他表使用）
    conn.execute(__import__("sqlalchemy").text("DROP TABLE IF EXISTS search_documents CASCADE"))
