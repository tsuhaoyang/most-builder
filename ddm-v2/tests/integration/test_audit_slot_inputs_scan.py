"""`scripts/audit_slot_inputs.py` 的 **DB 掃描層** 端對端證明（ADR-028 §4）。

單元測試（`tests/unit/test_audit_slot_inputs.py`）證明的是「偵測器對合成 payload 會紅」。
它證明不了另一半：**掃描真的走到那張表了嗎？** 兩者是不同的失效模式——

  偵測器對，但 query 打錯表／欄位取錯／早退 → 正式環境掃描恆綠 → 帶著髒資料部署加嚴版本。
  這就是「差集守門的待驗集合是空的」在 DB 層的版本
  （先例 `Always-True-Assertion-Detector-Self-Disable` 型二）。

所以這裡自己種一筆**故意違規**的資料進每一條掃描路徑，斷言 `audit()` 抓得到、
而且歸屬到正確的來源表與規則。資料在 `db_ctx` 的外層 transaction 內，teardown 全部 rollback
（CI_GATES 硬性規則 7：不撈環境既存資料，自己建）。
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import uuid

import pytest

pytestmark = pytest.mark.integration

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "audit_slot_inputs.py"


def _load():
    name = "_audit_slot_inputs_scan_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


AUDIT = _load()


def _dirty_cm_payload(rule_set_code: str) -> dict:
    """一筆同時踩 A1 與 A6 的 CM payload（CycleIn dump 形狀＝真實 slot_inputs 形狀）。"""
    from ddm_v2.schemas.v2.most import CycleIn

    payload = CycleIn.model_validate({
        "seq": "CM",
        "rule_set_code": rule_set_code,
        "a0": {"reach_cm": 25},
        "g2": {"g_code": "g_touch"},
        "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 45}]},
        "x4": {"x_code": "x_none"},
        "i5": {"i_code": "i_none"},
    }).model_dump(mode="json")
    payload["m3"]["m_components"] = [
        {"verb_code": "m_push", "distance_cm": -5, "angle_deg": 0,
         "revolutions": 1, "diameter_cm": 0},   # A1 M_NEGATIVE
        {"distance_cm": 45},                     # A6 M_VERB_REQUIRED
    ]
    return payload


async def _seed_worksheet(db_session):
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    tag = uuid.uuid4().hex[:6]
    site = Site(id=uuid.uuid4(), external_code=f"AUD-{tag}", name_zh="AUDIT")
    db_session.add(site)
    await db_session.flush()
    product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="AUDIT")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(id=uuid.uuid4(), product_id=product.id, sku_code=f"AUD-{tag}", name_zh="AUDIT")
    db_session.add(sku)
    await db_session.flush()
    rs = await get_active_rule_set(db_session)
    pv = ProcessVersion(id=uuid.uuid4(), sku_id=sku.id, version_no="v1", status="draft")
    ws = MostWorksheet(id=uuid.uuid4(), process_version_id=pv.id, status="draft",
                       default_rule_set_id=rs.id)
    db_session.add(pv)
    db_session.add(ws)
    await db_session.flush()
    return ws, rs


def _find(records, source: str, entity_id: str):
    return [r for r in records if r.source == source and entity_id in r.entity_id]


async def test_scan_reaches_most_cycles_slot_inputs(db_session):
    """most_cycles.slot_inputs：種一筆 A1+A6 違規 → audit() 必須抓到並回非零 exit code。"""
    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    ws, rs = await _seed_worksheet(db_session)
    row = WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=1, hand="RH")
    db_session.add(row)
    await db_session.flush()
    cycle_id = uuid.uuid4()
    db_session.add(MostCycle(id=cycle_id, wi_row_id=row.id, seq_kind="CM", rule_set_id=rs.id,
                             slot_inputs=_dirty_cm_payload(rs.code), total_tmu=29, total_seconds=1.044))
    await db_session.commit()

    records, counts, _infos, _drafts = await AUDIT.audit(db_session)

    hit = _find(records, "most_cycles", str(cycle_id))
    assert len(hit) == 1, f"掃描沒走到 most_cycles（counts={counts}）"
    # 報告的【掃描範圍】不得謊報：`counts[...] = 0` 這種突變必須在這裡轉紅。
    # 用 `>= 1` 而不是精確值，才不會因為目標 DB 的既存資料量而假紅。
    assert counts["most_cycles.slot_inputs"] >= 1, f"counts 沒有反映真實掃描量：{counts}"
    assert {f.rule for f in hit[0].blocking} == {"A1", "A6"}
    assert hit[0].rule_set_code == rs.code
    assert hit[0].orig_tmu == 29.0
    assert hit[0].path == "slot_inputs"

    # 只對**本測試種的**紀錄 render：`records` 是掃全庫的結果，對它斷言 exit code
    # 會讓這條測試的成敗取決於目標 DB 裡有沒有別人留下的髒列（與本檔 docstring
    # 「不撈環境既存資料，自己建」直接衝突）。這裡要證的是「這一筆會把 code 推成 1」。
    _report, code = AUDIT.render(hit, counts, [], verbose=False)
    assert code == 1, "有 BLOCK 命中時 exit code 必須非 0"


async def test_scan_reaches_motion_module_versions_rows(db_session):
    """motion_module_versions.rows[].cycle：巢狀在 JSONB 陣列裡，最容易被漏掉的一條路徑。

    髒 cycle 刻意種在 **rows[1]**、前面墊一列沒有 cycle 的：
      - 只種一列時，`path=f"rows[{i}].cycle"` 寫死成 `rows[0]` 仍然全綠（實測突變存活）；
      - 而「沒有 cycle 的列要不要佔索引」也只有這樣才驗得到——用另一個計數器就會回報
        `rows[0].cycle`，指到一個根本沒有 cycle 的列，修補時會改錯資料。
    """
    from datetime import datetime, timezone

    from ddm_v2.models.v2.motion_module import MotionModule, MotionModuleVersion
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    rs = await get_active_rule_set(db_session)
    module = MotionModule(id=uuid.uuid4(), name_zh="AUDIT", category="action",
                          scope="global", status="draft", current_version=1)
    db_session.add(module)
    await db_session.flush()
    ver_id = uuid.uuid4()
    db_session.add(MotionModuleVersion(
        id=ver_id, module_id=module.id, version_no=1, rule_set_id=rs.id,
        rows=[{"hand": "RH", "frequency": 1, "description": "沒有 cycle 的列"},
              {"hand": "LH", "frequency": 1, "cycle": _dirty_cm_payload(rs.code)}],
        total_tmu=0, total_seconds=0, published_by="UT_AUDIT",
        published_at=datetime.now(timezone.utc)))
    await db_session.commit()

    records, counts, _infos, _drafts = await AUDIT.audit(db_session)

    hit = _find(records, "motion_module_versions", str(ver_id))
    assert len(hit) == 1, f"掃描沒走到 motion_module_versions.rows[].cycle（counts={counts}）"
    assert hit[0].path == "rows[1].cycle", "path 要指得出是哪一列（且不因跳過的列而位移）"
    assert {f.rule for f in hit[0].blocking} == {"A1", "A6"}


async def test_scan_reaches_motion_templates_and_uses_active_rule_set(db_session):
    """motion_templates.cycle_template 不帶 rule_set_code → 必須以 **active** 掃（套用時就是現算）。"""
    from ddm_v2.models.v2.motion_template import MotionTemplate
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    rs = await get_active_rule_set(db_session)
    payload = _dirty_cm_payload(rs.code)
    payload.pop("rule_set_code")  # 與真實範本一致（ADR-025 D9 已清）
    tpl_id = uuid.uuid4()
    db_session.add(MotionTemplate(id=tpl_id, name_zh="AUDIT-TPL", seq_kind="CM",
                                  cycle_template=payload, status="draft", keywords=[]))
    await db_session.commit()

    records, counts, _infos, _drafts = await AUDIT.audit(db_session)

    hit = _find(records, "motion_templates", str(tpl_id))
    assert len(hit) == 1, f"掃描沒走到 motion_templates（counts={counts}）"
    assert hit[0].rule_set_code == rs.code
    assert {f.rule for f in hit[0].blocking} == {"A1", "A6"}


async def test_scan_reaches_import_staging_tables(db_session):
    """excel_imports.staged_rows 與 import_rows.normalized_data：靠深走訪找 cycle 形狀子物件。"""
    from ddm_v2.models.v2.import_staging import ExcelImport, ImportRow
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    rs = await get_active_rule_set(db_session)
    imp_id = uuid.uuid4()
    db_session.add(ExcelImport(
        id=imp_id, source_name="audit.xlsx", status="mapped", raw_payload={"sheets": []},
        staged_rows=[{"_row": 2, "description": "乾淨列", "seconds": 1.0},
                     {"_row": 3, "description": "髒列", "cycle": _dirty_cm_payload(rs.code)}]))
    await db_session.flush()
    row_id = uuid.uuid4()
    db_session.add(ImportRow(
        id=row_id, import_id=imp_id, source_row_no=3,
        normalized_data={"description": "髒列", "cycle": _dirty_cm_payload(rs.code)},
        input_hash="audit-test", status="staged"))
    await db_session.commit()

    records, counts, _infos, _drafts = await AUDIT.audit(db_session)

    staged = _find(records, "excel_imports", str(imp_id))
    assert len(staged) == 1, f"掃描沒走到 excel_imports.staged_rows（counts={counts}）"
    assert staged[0].path == "staged_rows[1].cycle", "深走訪的路徑要指得出是哪一列"
    assert {f.rule for f in staged[0].blocking} == {"A1", "A6"}

    norm = _find(records, "import_rows", str(row_id))
    assert len(norm) == 1, f"掃描沒走到 import_rows.normalized_data（counts={counts}）"
    assert norm[0].path == "normalized_data.cycle"


async def test_scan_pins_rule_set_per_row_not_the_active_one(db_session):
    """`most_cycles.rule_set_id` 是逐列釘死的——掃描必須用**該列的**版本，不是一律用 active。

    反例會這樣浮現：twist 的 overflow 帶只存在於某一版時，用錯版本就會誤報／漏報。
    這裡用「V1 有 (None,1,24)/(None,3,42) 旋轉 overflow、V2 沒有 50cm×3 圈」這個真實差異：
    直徑 60cm × 3 圈在 V1 查得到（→42），在 V2 查不到（→ M_ROTATION_RANGE）。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.models.v2.worksheet import MostCycle, WiRow
    from ddm_v2.schemas.v2.most import CycleIn

    v1 = (await db_session.execute(
        select(RuleSet).where(RuleSet.code == "MINIMOST_FACTORY_V1"))).scalar_one_or_none()
    if v1 is None:
        pytest.skip("V1 rule-set 未種（先跑 dev_seed_v2.py）")
    active = (await db_session.execute(
        select(RuleSet).where(RuleSet.is_active.is_(True)))).scalar_one()
    assert active.code != v1.code

    payload = CycleIn.model_validate({
        "seq": "CM", "rule_set_code": v1.code,
        "m3": {"m_components": [{"verb_code": "m_rotate", "diameter_cm": 60, "revolutions": 3}]},
    }).model_dump(mode="json")

    ws, _rs = await _seed_worksheet(db_session)
    row = WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=1, hand="RH")
    db_session.add(row)
    await db_session.flush()
    cycle_id = uuid.uuid4()
    db_session.add(MostCycle(id=cycle_id, wi_row_id=row.id, seq_kind="CM", rule_set_id=v1.id,
                             slot_inputs=payload, total_tmu=42, total_seconds=1.512))
    await db_session.commit()

    records, _counts, _infos, _drafts = await AUDIT.audit(db_session)

    hit = _find(records, "most_cycles", str(cycle_id))
    assert len(hit) == 1
    assert hit[0].rule_set_code == v1.code, "掃描用錯 rule-set：必須是該列釘住的版本"
    assert hit[0].blocking == [], f"在 V1 下 60cm×3 圈合法，不該命中：{hit[0].findings}"
    # 這兩條才是有鑑別力的：若誤用 active（V2）掃，60cm×3 圈查不到值
    # → engine_error='M_ROTATION_RANGE'、engine_tmu=None。
    assert (hit[0].engine_tmu, hit[0].engine_error) == (42.0, None)


async def test_a_row_that_already_fails_cycle_in_today_warns_but_does_not_block(db_session):
    """S2（連現行 `CycleIn` 都驗不過）是 **WARN**：閘門要量的是加嚴造成的**差值**。

    這種列**今天就已經會 422**（下次存檔照樣爆），不是加嚴造成的。若算進 exit code，
    正式環境掃描會非 0，讀報告的人會以為「加嚴不安全」——那是誤導性訊號。
    但它的爆炸半徑與加嚴同型，所以必須**顯眼**地出現在 WARN 區塊裡（修補批次一起帶走）。
    """
    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    ws, rs = await _seed_worksheet(db_session)
    payload = _dirty_cm_payload(rs.code)
    payload["m3"]["m_components"] = [{"verb_code": "m_push", "distance_cm": 45}]  # 清掉 A1/A6
    payload["frequency"] = "not-a-number"   # 現行 CycleIn 就驗不過（float 欄位）
    row = WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=1, hand="RH")
    db_session.add(row)
    await db_session.flush()
    cycle_id = uuid.uuid4()
    db_session.add(MostCycle(id=cycle_id, wi_row_id=row.id, seq_kind="CM", rule_set_id=rs.id,
                             slot_inputs=payload, total_tmu=29, total_seconds=1.044))
    await db_session.commit()

    records, counts, _infos, _drafts = await AUDIT.audit(db_session)

    hit = _find(records, "most_cycles", str(cycle_id))
    assert len(hit) == 1
    assert [f.rule for f in hit[0].warnings] == ["S2"], f"S2 應命中：{hit[0].findings}"
    assert hit[0].blocking == [], "S2 不得進 BLOCK"

    # 同上：只對本測試種的紀錄 render。對全庫 `records` 斷言 exit 0 會在目標 DB 有任何
    # 既存 BLOCK 命中時（跑過 dev_seed_30rows.py 或 migrate_v3_user_data.py）假紅。
    report, code = AUDIT.render(hit, counts, [], verbose=False)
    assert code == 0, "只有 S2 命中時 exit code 必須是 0（本來就壞的列不算加嚴的帳）"
    warn_section = report.split("【WARN：不影響 exit code】")[1]
    assert str(cycle_id) in warn_section and "今天就已經會 422" in warn_section


async def test_keyset_pagination_walks_every_row_across_pages(db_session):
    """分頁改成 keyset（`WHERE id > :last`）之後，要證明它在**真的 PostgreSQL 上**走得完。

    單元測試用假 session 只能驗「送出的 SQL 沒有 OFFSET、第二頁帶 keyset 條件」；
    走不走得完取決於 PG 的 uuid 比較與 ORDER BY 是否一致，那只有真 DB 驗得到。

    `_PAGE = 2`（**不是 1**）：每頁 1 列時 `rows[0] is rows[-1]`，游標取哪一端完全等價，
    於是「游標取本頁第一列」這個會**產生重複列**的突變在這裡存活（實測全綠）。
    每頁 2 列種 3 筆才有鑑別力：游標取 rows[0] 的話第二頁會重吐第 2 列。
    （重複列會灌大【命中率】的分母 `len(records)`，把 ADR-028 的 1% 門檻稀釋到失效。）
    """
    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    ws, rs = await _seed_worksheet(db_session)
    cycle_ids = []
    for seq_no in range(3):
        row = WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=seq_no + 1, hand="RH")
        db_session.add(row)
        await db_session.flush()
        cycle_id = uuid.uuid4()
        cycle_ids.append(cycle_id)
        db_session.add(MostCycle(id=cycle_id, wi_row_id=row.id, seq_kind="CM", rule_set_id=rs.id,
                                 slot_inputs=_dirty_cm_payload(rs.code), total_tmu=29,
                                 total_seconds=1.044))
    await db_session.commit()

    original_page = AUDIT._PAGE
    AUDIT._PAGE = 2
    try:
        records, _counts, _infos, _drafts = await AUDIT.audit(db_session)
    finally:
        AUDIT._PAGE = original_page

    for cycle_id in cycle_ids:
        assert len(_find(records, "most_cycles", str(cycle_id))) == 1, (
            f"keyset 分頁漏掉或重複了 {cycle_id}")


async def test_readonly_snapshot_is_enforced_by_postgres(db_session):
    """`begin_readonly_snapshot()` 的「唯讀」必須由 PostgreSQL 真的擋下來，不是宣稱。

    ⚠️ 這條刻意自建 engine，與 `tests/conftest.py` 的「測試內不得自行 create_async_engine」
    相牴觸——例外理由：本測試要證的**就是**那條連線寫不進去，而探針用的是
    `CREATE TEMP TABLE`（session 生命週期、不進任何 schema）。萬一唯讀失效，
    測試會紅，而那張暫存表也隨連線消失，兩種結果都不可能汙染資料庫。
    """
    import os

    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await AUDIT.begin_readonly_snapshot(session)

            identity = await AUDIT.connection_identity(session, url)
            assert identity["transaction_read_only"] == "on"
            assert identity["transaction_isolation"] == "repeatable read"

            # 密碼遮罩：**不留 `or` 逃生門**。原本這條是
            #   assert "***" in rendered or "@" not in <authority>
            # ——標準 URL 下前半恆真，後半永遠不會被求值，而且從未斷言真正的密碼不在輸出裡。
            rendered = identity["DATABASE_URL（已遮罩密碼與 query 值）"]
            parsed_url = make_url(url)
            secret = parsed_url.password
            assert secret, "測試環境的 DATABASE_URL 沒有密碼，這條斷言就沒有鑑別力（請帶密碼）"
            # 密碼若是 username／database 的子字串，下面的 `secret not in rendered`
            # 會被 userinfo／database 這兩個「本來就該印」的合法欄位打成假陽性——
            # 測試資料本身就沒有鑑別力，不是 redact_url() 有 bug。
            # ⚠️ 只查這個方向：反過來（username／database 是密碼的子字串）不會讓
            # 「完整密碼字串」出現在 rendered 裡，`secret not in rendered` 照樣有鑑別力，
            # 不該被擋。而且反向用 `value in secret` 在 value 是空字串時（例如 URL 不帶
            # database path，asyncpg 合法寫法）恆為 True，會把「URL 缺欄位」誤診斷成
            # 「密碼重疊」，訊息反而導人換錯地方。
            username = parsed_url.username or ""
            database = parsed_url.database or ""
            for label, value in (("username", username), ("database", database)):
                assert secret not in value, (
                    f"測試環境的密碼是{label}（{value!r}）的子字串，這條斷言會有假陽性："
                    f"密碼字串會透過合法顯示的 {label} 欄位出現在遮罩後的輸出裡，"
                    f"不代表密碼真的外洩。請把 CI 的 POSTGRES_PASSWORD 換成"
                    f"不是 POSTGRES_USER／POSTGRES_DB 子字串的值。"
                )
            assert secret not in rendered, f"報告 header 原樣印出了密碼：{rendered}"

            # replica 判定欄位：runbook 第 3 步建議「量大就跑 read replica」，
            # 而落後的 standby 上最近寫入的髒列不在快照裡 → exit 0，報告卻與 primary 無異。
            assert identity["pg_is_in_recovery()"].startswith("False"), "本測試庫應為 primary"
            assert "pg_last_xact_replay_timestamp()" in identity

            with pytest.raises(Exception) as excinfo:
                await session.execute(text("CREATE TEMP TABLE ddm_audit_readonly_probe(x int)"))
            assert "read-only" in str(excinfo.value).lower(), (
                f"寫入沒有被 PostgreSQL 擋下（唯讀只是宣稱）：{excinfo.value}")
    finally:
        await engine.dispose()


async def test_report_header_never_prints_a_password_hidden_in_the_query_string(db_session):
    """密碼搬進 query string 也不得外洩——這條**不依賴**測試環境的 URL 長什麼樣。

    `render_as_string(hide_password=True)` 只遮 `URL.password`，`URL.query` 是逐字 render 的，
    而 asyncpg dialect 會 `opts.update(url.query)` → `?password=` 是合法且會生效的寫法。
    被 runbook 的 percent-encode 警告勸退的操作者最自然的迴避動作就是這一條，
    然後正式庫密碼明文落進一份要附進 ADR 核可、被傳閱的報告。
    """
    from sqlalchemy.engine import make_url

    secret = "q-s3cr3t-in-query"
    url = f"postgresql+asyncpg://ddm_audit_run@dbhost:5432/ddm?password={secret}&sslmode=require"

    assert secret in make_url(url).render_as_string(hide_password=True), "前提：SQLAlchemy 擋不住"
    assert secret not in AUDIT.redact_url(url)
    assert AUDIT.redact_url(url) == (
        "postgresql+asyncpg://ddm_audit_run@dbhost:5432/ddm?password=***&sslmode=***")


async def test_scan_reaches_ai_parse_run_drafts_but_only_as_an_indicator(db_session):
    """`ai_parse_runs.drafts[].cycle`：掃得到、列在【指標】區塊，但**不影響 exit code**。

    種一筆同時踩 A1+A6 的草稿——若它被誤當閘門，下面的 `code == 0` 會紅。
    不是閘門的理由：草稿還沒被採用，不會被原樣重存；採用時會重過 `CycleIn` + `compute_cycle`
    （`most_compiler/engine_gate.py`），屆時被加嚴版本擋下正是預期行為。
    """
    from datetime import datetime, timezone

    from ddm_v2.models.v2.ai_ops import AiDeploymentBundle, AiParseRun
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    rs = await get_active_rule_set(db_session)
    tag = uuid.uuid4().hex[:8]
    bundle = AiDeploymentBundle(id=uuid.uuid4(), code=f"AUDIT-{tag}", kind="rule_based",
                                status="draft", created_by="UT_AUDIT",
                                created_at=datetime.now(timezone.utc))
    db_session.add(bundle)
    await db_session.flush()
    run_id = uuid.uuid4()
    db_session.add(AiParseRun(
        id=run_id, source_kind="interactive", raw_text="推 45cm", normalized_text="推 45cm",
        input_hash=f"audit-{tag}", context_hash=f"ctx-{tag}", rule_set_id=rs.id,
        bundle_id=bundle.id, plan={"actions": []}, slot_candidates=[],
        drafts=[{"action_id": "a1", "complete": False, "cycle": None},          # partial：跳過
                {"action_id": "a2", "complete": True, "cycle": _dirty_cm_payload(rs.code)}],
        routing_status="review", routing_reasons=[], created_by="UT_AUDIT",
        created_at=datetime.now(timezone.utc)))
    await db_session.commit()

    records, counts, _infos, drafts = await AUDIT.audit(db_session)

    hit = _find(drafts, "ai_parse_runs", str(run_id))
    assert len(hit) == 1, f"掃描沒走到 ai_parse_runs.drafts[].cycle（counts={counts}）"
    assert hit[0].path == "drafts[1].cycle", "cycle=None 的 partial draft 要跳過，索引不可錯位"
    assert {f.rule for f in hit[0].blocking} == {"A1", "A6"}
    assert hit[0].rule_set_code == rs.code

    # 結構性保證：草稿**不在** records 裡，所以不可能被算進 exit code
    assert _find(records, "ai_parse_runs", str(run_id)) == []

    # `records=[]`：本測試要證的是「這筆違規草稿自己不會把 exit code 推離 0」。
    # 傳全庫的 `records` 進來的話，目標 DB 只要有任何既存 BLOCK 命中，這條就會假紅。
    report, code = AUDIT.render([], counts, [], verbose=False, draft_records=hit)
    assert code == 0, "AI 草稿命中不得影響 exit code"
    head, indicator = report.split("【指標：AI 草稿（不影響 exit code）】")
    assert str(run_id) in indicator and "M_VERB_REQUIRED" in indicator
    assert str(run_id) not in head, "草稿不得混進 BLOCK／WARN 區塊"
