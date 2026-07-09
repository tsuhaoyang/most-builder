"""backfill_embeddings.py — 批次補算 search_documents.embedding

用法：
    PYTHONPATH=src .venv/bin/python scripts/backfill_embeddings.py [--dry-run]

環境變數：
    DATABASE_URL      — 必要
    EMBEDDING_URL     — embedding 服務位址（預設 http://localhost:8080）
    EMBEDDING_PROVIDER— null（跳過）/ bge_m3_http（預設）

無 EMBEDDING_URL 時不呼叫服務，直接印出待補算筆數後結束。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

BATCH_SIZE = 32


async def main(dry_run: bool) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL 未設定，跳過", file=sys.stderr)
        return

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    engine = create_async_engine(database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        result = await session.execute(
            text("SELECT id, content_norm FROM search_documents WHERE embedding IS NULL ORDER BY updated_at")
        )
        rows = result.fetchall()

    print(f"待補算：{len(rows)} 筆")

    if dry_run:
        print("[dry-run] 不實際呼叫 embedding 服務")
        await engine.dispose()
        return

    embedding_url = os.getenv("EMBEDDING_URL", "")
    if not embedding_url:
        print("EMBEDDING_URL 未設定，跳過 embedding 呼叫")
        await engine.dispose()
        return

    try:
        import httpx
    except ImportError:
        print("httpx 未安裝，跳過 embedding 呼叫", file=sys.stderr)
        await engine.dispose()
        return

    updated = 0
    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]
        ids = [str(r.id) for r in batch]
        texts = [r.content_norm for r in batch]

        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                resp = await c.post(f"{embedding_url}/embed", json={"inputs": texts})
                resp.raise_for_status()
                vecs = resp.json()
        except Exception as e:
            print(f"  批次 {batch_start}–{batch_start+len(batch)-1} 失敗：{e}", file=sys.stderr)
            continue

        if len(vecs) != len(batch):
            print(f"[WARN] 回傳向量數 {len(vecs)} ≠ 批次數 {len(batch)}，跳過此批")
            continue

        async with Session() as session:
            for row_id, vec in zip(ids, vecs):
                vec_str = "[" + ",".join(str(v) for v in vec) + "]"
                await session.execute(
                    text("""
                        UPDATE search_documents
                        SET embedding = :vec::vector,
                            embedding_model = 'bge-m3',
                            updated_at = now()
                        WHERE id = :id
                    """),
                    {"vec": vec_str, "id": row_id},
                )
            await session.commit()

        updated += len(batch)
        print(f"  已更新 {updated}/{len(rows)}")

    await engine.dispose()
    print(f"完成：共補算 {updated} 筆")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill search_documents embeddings")
    parser.add_argument("--dry-run", action="store_true", help="僅統計，不實際呼叫 embedding 服務")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
