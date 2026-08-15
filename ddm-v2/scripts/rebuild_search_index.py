"""rebuild_search_index.py — 全量重建 search_documents 投影表

用法：
    PYTHONPATH=src .venv/bin/python scripts/rebuild_search_index.py --yes

動作：
1. DELETE search_documents WHERE doc_type = 'motion_module'
2. 取 motion_modules（current_version > 0 的 published 模組）
3. 對每個模組 upsert content_norm（含 scope/owner；embedding 留 NULL，待 backfill_embeddings.py 補算）

環境變數：
    DATABASE_URL — 必要
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def main(yes: bool) -> None:
    if not yes:
        print("需要 --yes 確認", file=sys.stderr)
        sys.exit(1)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL 未設定", file=sys.stderr)
        sys.exit(1)

    # 在 event loop 內 import，避免 asyncpg 初始化問題
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from ddm_v2.search.normalization import build_content_norm

    engine = create_async_engine(database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        print("DELETE search_documents WHERE doc_type = 'motion_module' ...")
        await session.execute(text("DELETE FROM search_documents WHERE doc_type = 'motion_module'"))
        await session.commit()

        # 取 published 的 motion_modules（current_version > 0）
        result = await session.execute(text("""
            SELECT mm.id, mm.name_zh, mm.keywords, mm.scope, mm.owner,
                   mmv.rule_set_id
            FROM motion_modules mm
            JOIN motion_module_versions mmv
              ON mmv.module_id = mm.id
             AND mmv.version_no = mm.current_version
            WHERE mm.current_version > 0
            ORDER BY mm.updated_at
        """))
        modules = result.fetchall()
        print(f"找到 {len(modules)} 個已發布模組，開始 upsert ...")

        for i, mod in enumerate(modules, 1):
            keywords = mod.keywords if isinstance(mod.keywords, list) else []
            content = build_content_norm(mod.name_zh, "", keywords)
            await session.execute(text("""
                INSERT INTO search_documents
                    (id, doc_type, ref_id, rule_set_id, content_norm, scope, owner, updated_at)
                VALUES
                    (gen_random_uuid(), 'motion_module', :ref_id, :rule_set_id, :content, :scope, :owner, now())
                ON CONFLICT (doc_type, ref_id) DO UPDATE
                  SET content_norm = EXCLUDED.content_norm,
                      rule_set_id = EXCLUDED.rule_set_id,
                      scope = EXCLUDED.scope,
                      owner = EXCLUDED.owner,
                      embedding = NULL,
                      embedding_model = NULL,
                      updated_at = now()
            """), {
                "ref_id": str(mod.id),
                "rule_set_id": str(mod.rule_set_id),
                "content": content,
                "scope": mod.scope,
                "owner": mod.owner,
            })

            if i % 50 == 0 or i == len(modules):
                print(f"  進度：{i}/{len(modules)}")

        await session.commit()

    await engine.dispose()
    print("rebuild_search_index 完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="全量重建 search_documents 投影表")
    parser.add_argument("--yes", action="store_true", help="確認執行（必要旗標）")
    args = parser.parse_args()
    asyncio.run(main(yes=args.yes))
