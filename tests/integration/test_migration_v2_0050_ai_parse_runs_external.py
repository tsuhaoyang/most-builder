"""v2_0050 migration 驗證（ADR-037 S3 第一步）。

1. bundle kind 的 CHECK：放行 rule_based／llm／external，擋第四種值。
2. 佔位 bundle `external-ai-service` 存在、active、kind=external。
3. ai_parse_runs 的兩個新欄可為 NULL（舊列不受影響）、可寫入，ORM 與 DB 對得上。
4. downgrade 前的檢查 SQL（直接執行 migration 匯出的同一份常數；斷言增量）：
   佔位 bundle 自己不算「external 資料」；有 run／job 指向 external bundle、或有佔位以外的 external bundle 就會被計到。
5. 佔位 bundle 不可被 rule_based／llm 路徑選為 parse bundle（wi_ai_service、parse_job_service）。
   真正的 `alembic downgrade` 拒絕行為另在測試 DB 手動驗證（見 PR 描述）；這裡不在 rollback transaction 內跑 alembic。

全程走 conftest 的 rollback fixture，不落真實 DB。
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ddm_v2.models.v2.ai_ops import AiParseRun

pytestmark = pytest.mark.integration


def _load_migration():
    p = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions_v2" / "v2_0050_ai_parse_runs_external.py"
    spec = importlib.util.spec_from_file_location("_v2_0050", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()


async def _insert_bundle(session, kind: str, *, code: str | None = None) -> uuid.UUID:
    bid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ai_deployment_bundles (id, code, kind, config, status, created_by) "
            "VALUES (:id, :code, :kind, '{}'::jsonb, 'draft', 'test')"
        ),
        {"id": bid, "code": code or f"mig50-{uuid.uuid4().hex[:8]}", "kind": kind},
    )
    return bid


async def _rule_set_id(session) -> uuid.UUID:
    rid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO rule_sets (id, code, name_zh, status, created_at, updated_at) "
            "VALUES (:id, :code, 'mig50', 'draft', NOW(), NOW())"
        ),
        {"id": rid, "code": f"MIG50-{uuid.uuid4().hex[:8]}"},
    )
    return rid


async def _insert_run(session, bundle_id, rule_set_id, **extra) -> uuid.UUID:
    rid = uuid.uuid4()
    cols = {
        "id": rid,
        "source_kind": "interactive",
        "raw_text": "x",
        "normalized_text": "x",
        "input_hash": f"h-{uuid.uuid4().hex}",
        "context_hash": "c",
        "rule_set_id": rule_set_id,
        "bundle_id": bundle_id,
        "routing_status": "review",
        "created_by": "test",
        **extra,
    }
    names = ", ".join(cols)
    params = ", ".join(f":{k}" for k in cols)
    await session.execute(
        text(f"INSERT INTO ai_parse_runs ({names}, plan) VALUES ({params}, '{{}}'::jsonb)"),
        cols,
    )
    return rid


# ═════════ 1. CHECK ═════════

@pytest.mark.parametrize("kind", ["rule_based", "llm", "external"])
async def test_bundle_kind_check_allows_the_three_kinds(db_session, kind):
    bid = await _insert_bundle(db_session, kind)
    got = await db_session.execute(text("SELECT kind FROM ai_deployment_bundles WHERE id = :id"), {"id": bid})
    assert got.scalar_one() == kind


async def test_bundle_kind_check_rejects_other_values(db_session):
    with pytest.raises(IntegrityError) as exc:
        await _insert_bundle(db_session, "remote")
    assert "ck_ai_deployment_bundles_ck_ai_deployment_bundles_kind" in str(exc.value)
    await db_session.rollback()


# ═════════ 2. 佔位 bundle ═════════

async def test_placeholder_bundle_is_seeded_active_and_external(db_session):
    row = (
        await db_session.execute(
            text("SELECT kind, status, model, prompt_version, config FROM ai_deployment_bundles WHERE code = :c"),
            {"c": MIG.PLACEHOLDER_BUNDLE_CODE},
        )
    ).one()
    assert (row.kind, row.status, row.model, row.prompt_version, row.config) == ("external", "active", None, None, {})


async def test_seed_sql_is_idempotent(db_session):
    await db_session.execute(text(MIG.SQL_SEED_PLACEHOLDER_BUNDLE))
    n = await db_session.execute(
        text("SELECT COUNT(*) FROM ai_deployment_bundles WHERE code = :c"), {"c": MIG.PLACEHOLDER_BUNDLE_CODE}
    )
    assert n.scalar_one() == 1


# ═════════ 3. 新欄位 ═════════

async def test_new_columns_are_nullable_so_existing_style_rows_are_unaffected(db_session):
    rs = await _rule_set_id(db_session)
    bid = await _insert_bundle(db_session, "llm")
    rid = await _insert_run(db_session, bid, rs)
    row = (
        await db_session.execute(text("SELECT provenance, upstream_run_id FROM ai_parse_runs WHERE id = :id"), {"id": rid})
    ).one()
    assert row.provenance is None and row.upstream_run_id is None


async def test_new_columns_round_trip_through_the_orm(db_session):
    rs = await _rule_set_id(db_session)
    bid = (
        await db_session.execute(
            text("SELECT id FROM ai_deployment_bundles WHERE code = :c"), {"c": MIG.PLACEHOLDER_BUNDLE_CODE}
        )
    ).scalar_one()
    run = AiParseRun(
        source_kind="interactive",
        raw_text="x",
        normalized_text="x",
        input_hash=f"h-{uuid.uuid4().hex}",
        context_hash="c",
        rule_set_id=rs,
        bundle_id=bid,
        plan={},
        routing_status="review",
        created_by="test",
        provenance={"run_id": "R1", "bundle_code": "most-wi-motion-parse-poc003", "attempts": 1},
        upstream_run_id="R1",
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    assert run.provenance == {"run_id": "R1", "bundle_code": "most-wi-motion-parse-poc003", "attempts": 1}
    assert run.upstream_run_id == "R1"


async def test_upstream_run_id_is_indexed(db_session):
    idx = await db_session.execute(
        text("SELECT indexdef FROM pg_indexes WHERE tablename = 'ai_parse_runs' AND indexname = 'ix_ai_parse_runs_upstream_run_id'")
    )
    assert "upstream_run_id" in idx.scalar_one()


# ═════════ 4. downgrade 前的檢查 SQL ═════════
# 一律斷言「增量」：不假設庫裡原本沒有 external 的 run／bundle（後續切片會 seed）。

async def _counts(session) -> tuple[int, int, int]:
    runs = (await session.execute(text(MIG.SQL_COUNT_EXTERNAL_RUNS))).scalar_one()
    jobs = (await session.execute(text(MIG.SQL_COUNT_EXTERNAL_JOBS))).scalar_one()
    others = (await session.execute(text(MIG.SQL_COUNT_OTHER_EXTERNAL_BUNDLES))).scalar_one()
    return runs, jobs, others


async def _placeholder_id(session) -> uuid.UUID:
    return (
        await session.execute(
            text("SELECT id FROM ai_deployment_bundles WHERE code = :c"), {"c": MIG.PLACEHOLDER_BUNDLE_CODE}
        )
    ).scalar_one()


async def test_placeholder_alone_does_not_count_as_external_data(db_session):
    # 佔位 bundle 本身不算「external 資料」：否則 downgrade 永遠被自己擋住
    runs, jobs, others = await _counts(db_session)
    assert others == 0 and runs == 0 and jobs == 0


async def test_a_run_on_an_external_bundle_is_counted(db_session):
    before = await _counts(db_session)
    rs = await _rule_set_id(db_session)
    await _insert_run(db_session, await _placeholder_id(db_session), rs, upstream_run_id="R1")
    after = await _counts(db_session)
    assert after == (before[0] + 1, before[1], before[2])


async def test_runs_on_llm_or_rule_based_bundles_are_not_counted(db_session):
    before = await _counts(db_session)
    rs = await _rule_set_id(db_session)
    for kind in ("llm", "rule_based"):
        await _insert_run(db_session, await _insert_bundle(db_session, kind), rs)
    assert await _counts(db_session) == before


async def test_another_external_bundle_is_counted(db_session):
    before = await _counts(db_session)
    await _insert_bundle(db_session, "external")
    after = await _counts(db_session)
    assert after == (before[0], before[1], before[2] + 1)


async def test_a_parse_job_on_an_external_bundle_is_counted(db_session):
    """ai_parse_jobs.deployment_bundle_id 也是 RESTRICT FK：有 job 指向 external bundle 時要被計到。"""
    before = await _counts(db_session)
    rs = await _rule_set_id(db_session)
    imp = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO excel_imports (id, source_name, status, raw_payload, imported_by) "
            "VALUES (:id, 'mig50.xlsx', 'mapped', '{}'::jsonb, 'test')"
        ),
        {"id": imp},
    )
    await db_session.execute(
        text(
            "INSERT INTO ai_parse_jobs (id, idempotency_key, import_id, deployment_bundle_id, rule_set_id, requested_by) "
            "VALUES (gen_random_uuid(), :k, :imp, :b, :rs, 'test')"
        ),
        {"k": f"mig50-{uuid.uuid4().hex}", "imp": imp, "b": await _placeholder_id(db_session), "rs": rs},
    )
    after = await _counts(db_session)
    assert after == (before[0], before[1] + 1, before[2])


async def test_delete_placeholder_sql_only_removes_the_placeholder(db_session):
    other = await _insert_bundle(db_session, "external")
    await db_session.execute(text(MIG.SQL_DELETE_PLACEHOLDER_BUNDLE))
    left = (await db_session.execute(text("SELECT code FROM ai_deployment_bundles WHERE kind = 'external'"))).scalars().all()
    assert MIG.PLACEHOLDER_BUNDLE_CODE not in left
    got = await db_session.execute(text("SELECT COUNT(*) FROM ai_deployment_bundles WHERE id = :id"), {"id": other})
    assert got.scalar_one() == 1


async def test_placeholder_check_sql_sees_the_seeded_external_bundle(db_session):
    assert (await db_session.execute(text(MIG.SQL_PLACEHOLDER_IS_EXTERNAL))).scalar_one() == 1
    await db_session.execute(text(MIG.SQL_DELETE_PLACEHOLDER_BUNDLE))
    assert (await db_session.execute(text(MIG.SQL_PLACEHOLDER_IS_EXTERNAL))).scalar_one() == 0


# ═════════ 5. 佔位 bundle 不可被 rule_based／llm 路徑選為 parse bundle ═════════

async def test_wi_ai_service_refuses_to_select_the_external_placeholder_bundle(db_session):
    from ddm_v2.services.v2 import wi_ai_service

    with pytest.raises(RuntimeError, match="missing or inactive"):
        await wi_ai_service._get_active_bundle(db_session, code=MIG.PLACEHOLDER_BUNDLE_CODE)
    # 既有的 rule_based bundle 照常可選
    ok = await wi_ai_service._get_active_bundle(db_session, code=wi_ai_service.DEFAULT_BUNDLE_CODE)
    assert ok.kind != "external"


async def test_create_parse_job_refuses_the_external_placeholder_bundle(db_session):
    from ddm_v2.models.v2.import_staging import ExcelImport
    from ddm_v2.services.v2 import parse_job_service

    code = f"MIG50-{uuid.uuid4().hex[:8]}"
    await db_session.execute(
        text(
            "INSERT INTO rule_sets (id, code, name_zh, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :code, 'mig50', 'draft', NOW(), NOW())"
        ),
        {"code": code},
    )
    rec = ExcelImport(
        id=uuid.uuid4(),
        source_name="mig50.xlsx",
        status="mapped",
        raw_payload={"sheets": []},
        sheet="Sheet1",
        header_row=0,
        column_map={"description": 0},
        time_unit="sec",
        staged_rows=[{"_row": 1, "description": "拿起零件"}],
        imported_by="TEST",
    )
    db_session.add(rec)
    await db_session.flush()
    with pytest.raises(RuntimeError, match="missing or inactive"):
        await parse_job_service.create_parse_job(
            db_session,
            import_id=rec.id,
            rule_set_code=code,
            requested_by="TEST",
            bundle_code=MIG.PLACEHOLDER_BUNDLE_CODE,
        )
