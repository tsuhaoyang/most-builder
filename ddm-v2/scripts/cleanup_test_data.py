"""清理 integration 測試殘留資料（P0-0.2 測試資料汙染治理）。

背景：conftest 隔離改造（transaction rollback fixture）之前，integration 測試直接
commit 到真實 DB，累積了大量 `UT-*` 等命名的殘留（審查報告
docs/v3/v3-to-v2-migration-audit-202607.md §0.2）。本腳本按 tests/integration
的命名慣例清除可安全識別的殘留。

用法：
    export DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/DBNAME"
    python scripts/cleanup_test_data.py                            # 不帶參數＝dry-run：只列數量與樣本
    python scripts/cleanup_test_data.py --execute                  # 真刪：印出盤點後要求輸入 DB 名稱確認
    python scripts/cleanup_test_data.py --execute --yes-i-know DBNAME   # 非互動環境：DB 名稱仍須完全比對

安全守衛：--execute 會先印出 current_database() 與各類刪除筆數，之後必須輸入
（或以 --yes-i-know 提供）與目標 DB 名稱**完全一致**的字串才進 transaction；
比對失敗直接印錯誤退出，不刪任何資料。

識別 pattern（掃 tests/integration 命名慣例所得）：
    motion_modules.name_zh      : 'UT-%' / 'ut-%' / 'SM4-OwnerTest' / 'SM5-Personal-PubGuard'
                                  / 'SM7-ApplyBack%' / '測試模組-%'
                                  （versions 由 DB CASCADE；wi_rows.source_module_id SET NULL；
                                   wi_set_items 為 soft-ref 不受影響）
    wi_set_projects.project_code: 'UT-WISET-%'（items 由 DB CASCADE）
    skus.sku_code               : 'UTSKU-%' / 'AGGTEST\\_%' / 'GUARDTEST\\_%'
                                  （process_versions→worksheets→rows→cycles/levels 全 CASCADE）
    products                    : external_code 'UTPRD-%' 或 name_zh='UT產品' / 'AGGTEST\\_%'
                                  / 'GUARDTEST\\_%'，且已無 SKU（FK RESTRICT）
    sites.name_zh               : 'AGGTEST\\_%' / 'GUARDTEST\\_%'，且已無 product（FK RESTRICT）
                                  （AGGTEST=案件聚合測試 test_cases.py；
                                   GUARDTEST=隔離保險絲 test_isolation_guard.py）
    work_vocab_items.name_zh    : 'UT詞彙%' / 'UT分頁詞彙%' / 'UTnoLimit%' / 'UT搜尋%' / 'UT停用%'
                                  / 'UT RBAC%'，且未被任何 wi_rows 引用（FK RESTRICT，引用中的跳過）
    rule_option_synonyms        : synonym_raw '測試拿取%' / '放置刪除%' / '伸手重複%' / 'viewer測試%'
                                  / '測試無效選項'
    excel_imports.source_name   : 'Touchtime.xlsx'（測試上傳固定檔名；wi_rows.source_import_id SET NULL）
    app_users.employee_no       : 'ZZZ%' / 'SMTEST_%' / 'GAPTEST_%' / 'GAP_APPROVER_RETIRE_%'
                                  / 'UT_TESTUSER_%'（測試 JIT 建立的假員編）

不自動刪（僅回報數量）：
    - clone 自 demo worksheet 的 draft process_versions：與真實使用者的 clone 無法
      安全區分（model_label/analyst 皆複製自來源），需人工判斷。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@dataclass(frozen=True)
class Target:
    label: str
    table: str
    where: str  # SQL WHERE 子句（不含 WHERE）
    sample_col: str  # dry-run 樣本顯示欄


# 依 FK 依賴排序：projects → skus → products(需 skus 先清) → sites(需 products 先清)
#                → modules → vocab → 其餘
TARGETS: list[Target] = [
    Target(
        label="wi_set_projects (UT-WISET-%)",
        table="wi_set_projects",
        where="project_code LIKE 'UT-WISET-%'",
        sample_col="project_code",
    ),
    Target(
        label="skus (UTSKU-% / AGGTEST_% / GUARDTEST_%)",
        table="skus",
        where=(
            "sku_code LIKE 'UTSKU-%' OR sku_code LIKE 'AGGTEST\\_%' "
            "OR sku_code LIKE 'GUARDTEST\\_%'"
        ),
        sample_col="sku_code",
    ),
    Target(
        label="products (UTPRD-% / UT產品 / AGGTEST_% / GUARDTEST_%，且無非測試 SKU)",
        table="products",
        where=(
            "(external_code LIKE 'UTPRD-%' OR name_zh = 'UT產品' "
            "OR name_zh LIKE 'AGGTEST\\_%' OR name_zh LIKE 'GUARDTEST\\_%') "
            "AND NOT EXISTS (SELECT 1 FROM skus s WHERE s.product_id = products.id "
            "AND s.sku_code NOT LIKE 'UTSKU-%' AND s.sku_code NOT LIKE 'AGGTEST\\_%' "
            "AND s.sku_code NOT LIKE 'GUARDTEST\\_%')"
        ),
        sample_col="name_zh",
    ),
    Target(
        # AGGTEST=案件聚合測試（test_cases.py:_make_case）；
        # GUARDTEST=隔離保險絲（test_isolation_guard.py）。兩者都自建 site→product→sku 鏈。
        label="sites (AGGTEST_% / GUARDTEST_%，且已無 product)",
        table="sites",
        where=(
            "(name_zh LIKE 'AGGTEST\\_%' OR name_zh LIKE 'GUARDTEST\\_%') "
            "AND NOT EXISTS (SELECT 1 FROM products p WHERE p.site_id = sites.id)"
        ),
        sample_col="name_zh",
    ),
    Target(
        label="motion_modules (UT-% / ut-% / SM4/SM5/SM7 / 測試模組-%)",
        table="motion_modules",
        where=(
            "name_zh LIKE 'UT-%' OR name_zh LIKE 'ut-%' "
            "OR name_zh = 'SM4-OwnerTest' OR name_zh = 'SM5-Personal-PubGuard' "
            "OR name_zh LIKE 'SM7-ApplyBack%' OR name_zh LIKE '測試模組-%'"
        ),
        sample_col="name_zh",
    ),
    Target(
        label="work_vocab_items (UT詞彙/分頁/noLimit/搜尋/停用/RBAC，未被引用)",
        table="work_vocab_items",
        where=(
            "(name_zh LIKE 'UT詞彙%' OR name_zh LIKE 'UT分頁詞彙%' OR name_zh LIKE 'UTnoLimit%' "
            "OR name_zh LIKE 'UT搜尋%' OR name_zh LIKE 'UT停用%' OR name_zh LIKE 'UT RBAC%') "
            "AND NOT EXISTS (SELECT 1 FROM wi_rows r WHERE r.object_vocab_id = work_vocab_items.id "
            "OR r.from_vocab_id = work_vocab_items.id OR r.to_vocab_id = work_vocab_items.id "
            "OR r.tool_vocab_id = work_vocab_items.id)"
        ),
        sample_col="name_zh",
    ),
    Target(
        label="rule_option_synonyms (測試拿取/放置刪除/伸手重複/viewer測試/測試無效選項)",
        table="rule_option_synonyms",
        where=(
            "synonym_raw LIKE '測試拿取%' OR synonym_raw LIKE '放置刪除%' "
            "OR synonym_raw LIKE '伸手重複%' OR synonym_raw LIKE 'viewer測試%' "
            "OR synonym_raw = '測試無效選項'"
        ),
        sample_col="synonym_raw",
    ),
    Target(
        label="excel_imports (Touchtime.xlsx 測試上傳)",
        table="excel_imports",
        where="source_name = 'Touchtime.xlsx'",
        sample_col="source_name",
    ),
    Target(
        label="app_users (ZZZ% / SMTEST_% / GAPTEST_% / GAP_APPROVER_RETIRE_% / UT_TESTUSER_% / UT_AUDIT_% / TESTIE% / EMP_FROM_LB)",
        table="app_users",
        where=(
            "employee_no LIKE 'ZZZ%' OR employee_no LIKE 'SMTEST\\_%' "
            "OR employee_no LIKE 'GAPTEST\\_%' OR employee_no LIKE 'GAP\\_APPROVER\\_RETIRE\\_%' "
            "OR employee_no LIKE 'UT\\_TESTUSER\\_%' OR employee_no LIKE 'UT\\_AUDIT\\_%' "
            "OR employee_no LIKE 'TESTIE%' OR employee_no = 'EMP_FROM_LB'"
        ),
        sample_col="employee_no",
    ),
]

# 只回報、不刪：無法與真實使用安全區分的疑似殘留
INFO_ONLY: list[tuple[str, str]] = [
    (
        "疑似測試 clone 的 draft process_versions（不自動刪，需人工判斷）",
        "SELECT count(*) FROM process_versions WHERE source_version_id IS NOT NULL AND status = 'draft'",
    ),
]


def _confirm_target_db(db_name: str, yes_i_know: str | None) -> bool:
    """--execute 守衛：要求與 current_database() 完全一致的確認字串。

    - 互動：input() 輸入 DB 名稱；非互動：--yes-i-know <dbname>。
    - 比對失敗 → False（呼叫端印錯誤退出，不進 transaction）。
    """
    if yes_i_know is not None:
        if yes_i_know == db_name:
            return True
        print(f"錯誤：--yes-i-know 的值 {yes_i_know!r} 與目標資料庫 {db_name!r} 不一致，拒絕執行。",
              file=sys.stderr)
        return False
    try:
        answer = input(f"確認刪除？請輸入目標資料庫名稱（{db_name}）：")
    except EOFError:
        print("錯誤：無法讀取互動輸入（非互動環境請用 --yes-i-know <dbname>），拒絕執行。",
              file=sys.stderr)
        return False
    if answer.strip() == db_name:
        return True
    print(f"錯誤：輸入 {answer.strip()!r} 與目標資料庫 {db_name!r} 不一致，拒絕執行。", file=sys.stderr)
    return False


async def run(execute: bool, yes_i_know: str | None = None) -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("錯誤：請設定 DATABASE_URL（postgresql+asyncpg://...）", file=sys.stderr)
        return 2

    engine = create_async_engine(url)
    total = 0
    try:
        # 先盤點（dry-run 與 execute 都先列清單）
        async with engine.connect() as conn:
            db_name = (await conn.execute(text("SELECT current_database()"))).scalar()
            print(f"目標資料庫：{db_name}")
            print(f"模式：{'EXECUTE（真刪）' if execute else 'DRY-RUN（預設，不刪）'}")
            print("─" * 72)
            for t in TARGETS:
                n = (await conn.execute(text(f"SELECT count(*) FROM {t.table} WHERE {t.where}"))).scalar()
                total += n or 0
                print(f"{t.label}: {n} 筆")
                if n:
                    rows = (await conn.execute(
                        text(f"SELECT {t.sample_col} FROM {t.table} WHERE {t.where} LIMIT 5")
                    )).scalars().all()
                    for s in rows:
                        print(f"    · {s}")
            print("─" * 72)
            print(f"可刪除殘留合計：{total} 筆")
            for label, q in INFO_ONLY:
                n = (await conn.execute(text(q))).scalar()
                print(f"[僅回報] {label}: {n} 筆")

        if not execute:
            print("\nDry-run 完成，未刪除任何資料。確認後加 --execute 執行。")
            return 0

        # --execute 守衛：DB 名稱完全比對，失敗不進 transaction
        if not _confirm_target_db(db_name, yes_i_know):
            return 3

        # 真刪：單一 transaction，依 FK 依賴順序
        deleted = 0
        async with engine.begin() as conn:
            for t in TARGETS:
                r = await conn.execute(text(f"DELETE FROM {t.table} WHERE {t.where}"))
                print(f"DELETE {t.label}: {r.rowcount} 筆")
                deleted += r.rowcount or 0
        print(f"\n完成：共刪除 {deleted} 筆（關聯資料由 DB CASCADE 處理）。")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="清理 integration 測試殘留資料。不帶參數＝dry-run（只列數量與樣本，不刪）。",
    )
    parser.add_argument("--execute", action="store_true",
                        help="真正刪除（單一 transaction）。會先印盤點，再要求輸入目標 DB 名稱確認。")
    parser.add_argument("--yes-i-know", metavar="DBNAME", default=None,
                        help="非互動環境跳過 input()：值必須與 current_database() 完全一致，否則拒絕執行。")
    args = parser.parse_args()
    return asyncio.run(run(execute=args.execute, yes_i_know=args.yes_i_know))


if __name__ == "__main__":
    raise SystemExit(main())
