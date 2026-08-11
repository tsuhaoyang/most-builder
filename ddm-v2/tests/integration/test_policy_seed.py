"""`seed/v2/policy_seed.py` 必須回傳 ORM 列，不是 coroutine（R2a 補種；CI「Migrate + seed」守衛）。

事故形態：三個函式曾宣告成同步 `def` 卻對 `AsyncSession` 呼叫 `session.get(...)`——
coroutine 恆為真 → `existing is not None` 永遠成立 → **從不建列、回傳 coroutine**，
呼叫端 `scripts/dev_seed_v2.py` 一取 `.name` 就 `AttributeError`，
CI 的 backend 與 e2e 兩個 job 都掛在那一步（型別註記在說謊，mypy 也沒攔到）。

兩個分支都要測：
- migration `v2_0030` 已種過（正常環境）→ 原樣取回；
- 列不存在（表由 create_all 建、或列被清掉）→ 真的建出來。
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import text

from ddm_v2.models.v2.policy import LevelPolicyVersion, ModelingPolicyVersion
from ddm_v2.seed.v2.policy_seed import (
    seed_level_policy_factory_v1,
    seed_modeling_policy_factory_v1,
    seed_policy_factory_v1,
)
from ddm_v2.services.v2.policy_service import (
    LEVEL_FACTORY_V1_ID,
    MODELING_FACTORY_V1_ID,
    level_v1_content_hash,
    modeling_v1_content_hash,
)

pytestmark = pytest.mark.integration


def test_seed_entrypoints_are_coroutine_functions():
    """同步/非同步錯配的最短檢查：三個函式都必須是 async（否則 await 不到、也不會建列）。"""
    for fn in (
        seed_modeling_policy_factory_v1,
        seed_level_policy_factory_v1,
        seed_policy_factory_v1,
    ):
        assert inspect.iscoroutinefunction(fn), f"{fn.__name__} 必須是 async def"


async def test_seed_returns_orm_rows_when_already_seeded(db_session):
    """migration 已種過 → 回既有列。`.name` 可讀＝dev_seed_v2.py 掛掉的那一行的回歸測。"""
    mp, lp = await seed_policy_factory_v1(db_session)

    assert isinstance(mp, ModelingPolicyVersion), f"回傳型別錯誤：{type(mp)!r}"
    assert isinstance(lp, LevelPolicyVersion), f"回傳型別錯誤：{type(lp)!r}"
    assert (mp.name, lp.name) == ("MODELING_FACTORY_V1", "LEVEL_FACTORY_V1")
    assert (mp.id, lp.id) == (MODELING_FACTORY_V1_ID, LEVEL_FACTORY_V1_ID)


async def test_seed_creates_rows_when_absent(db_session):
    """列不存在 → 真的建出來（舊版永遠走不到這條分支，這是它最大的問題）。

    全程在 conftest 的 rollback transaction 內：先解掉三個引用方（RESTRICT FK），
    刪掉 manifest 列，補種後再驗。teardown ROLLBACK → 真實 DB 零殘留。
    """
    await db_session.execute(text(
        "UPDATE most_worksheets SET modeling_policy_version_id=NULL, level_policy_version_id=NULL"))
    await db_session.execute(text("UPDATE ai_parse_jobs SET modeling_policy_version_id=NULL"))
    await db_session.execute(text("DELETE FROM level_validation_runs"))
    await db_session.execute(text("DELETE FROM modeling_policy_versions"))
    await db_session.execute(text("DELETE FROM level_policy_versions"))
    db_session.expunge_all()  # identity map 可能還握著剛被刪的列，會讓 session.get 誤判為存在

    mp, lp = await seed_policy_factory_v1(db_session)
    await db_session.flush()

    assert mp.content_hash == modeling_v1_content_hash()
    assert lp.content_hash == level_v1_content_hash()
    assert mp.status == "published" and lp.status == "published"

    for table, pk in (("modeling_policy_versions", MODELING_FACTORY_V1_ID),
                      ("level_policy_versions", LEVEL_FACTORY_V1_ID)):
        got = (await db_session.execute(
            text(f"SELECT count(*) FROM {table} WHERE id = :i"),  # noqa: S608 - 表名為測試常數
            {"i": pk},
        )).scalar_one()
        assert got == 1, f"{table} 應補種出 1 列，實得 {got}"


async def test_seed_is_idempotent(db_session):
    """重跑不新增列、不換 id（seed 的基本要求）。"""
    before = (await db_session.execute(
        text("SELECT count(*) FROM modeling_policy_versions"))).scalar_one()
    first = await seed_policy_factory_v1(db_session)
    second = await seed_policy_factory_v1(db_session)
    await db_session.flush()

    assert first[0].id == second[0].id and first[1].id == second[1].id
    after = (await db_session.execute(
        text("SELECT count(*) FROM modeling_policy_versions"))).scalar_one()
    assert after == before, "重跑補種不得新增列"
