"""v2_0022 migration 驗證（ADR-024 §3-2 / §4）。

分三組：
1. CHECK 生效：'action'/'wi-template' 放行、中文領域分類（'取放'）被擋。
   ⚠️ 並明確釘住「NULL 目前仍放行」這個已知落差——它不是疏忽，是待裁決項，
   若日後收緊 schema 使 NULL 被擋，這條測試會變紅，強迫同時更新 ADR-024 §4 的落差註記。
2. migration 冪等 / 有效：直接執行 migration 模組匯出的**同一份 SQL 常數**（不是抄一份），
   在 rollback transaction 內驗證「有隱形列 → 刪掉且無孤兒版本列」與「無隱形列 → no-op」。
3. 範本 V1 清除：DB 內 cycle_template 全數不含 rule_set_code key，
   且 API 寫入路徑（POST/PATCH /motion-templates）不會把該 key 寫回去。

測試全程走 conftest 的 rollback fixture，不落真實 DB。
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


# ── 載入 migration 模組（migrations/versions_v2 不是 package，走 spec 載入）──
def _load_migration():
    p = (
        pathlib.Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions_v2"
        / "v2_0022_motion_module_category_and_template_ruleset.py"
    )
    spec = importlib.util.spec_from_file_location("_v2_0022", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()


async def _insert_module(session, category, *, name=None):
    """繞過 ORM/service 直接 INSERT，確保測到的是 DB 約束而非應用層驗證。"""
    mid = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO motion_modules
                (id, name_zh, category, keywords, scope, status, current_version,
                 created_at, updated_at)
            VALUES (:id, :name, :cat, '{}'::text[], 'global', 'draft', 0, NOW(), NOW())
            """
        ),
        {"id": mid, "name": name or f"mig22-{uuid.uuid4().hex[:8]}", "cat": category},
    )
    return mid


# ═════════ 1. CHECK 約束 ═════════

@pytest.mark.parametrize("category", ["action", "wi-template"])
async def test_check_allows_two_layer_values(db_session, category):
    """ADR-022 的兩層判別值必須放行。"""
    mid = await _insert_module(db_session, category)
    got = await db_session.execute(
        text("SELECT category FROM motion_modules WHERE id = :id"), {"id": mid}
    )
    assert got.scalar_one() == category


@pytest.mark.parametrize("category", ["取放", "組裝", "鎖附", "搬運", "arbitrary-third-value"])
async def test_check_rejects_domain_categories(db_session, category):
    """領域分類（v2_0012 抄進來的舊語意）必須被 DB 擋下——這正是 16 筆隱形模組的成因。"""
    with pytest.raises(IntegrityError) as exc:
        await _insert_module(db_session, category)
    assert "ck_motion_modules_ck_motion_modules_category_valid" in str(exc.value)
    await db_session.rollback()


async def _drop_not_null(session):
    await session.execute(
        text("ALTER TABLE motion_modules ALTER COLUMN category DROP NOT NULL")
    )


async def test_check_rejects_null_category(db_session):
    """NULL 必須被擋（v2_0023 補上的 NOT NULL）。

    ⚠️ 這條測試守的是一個反直覺的陷阱：**單靠 CHECK 擋不住 NULL**。
    SQL 的 CHECK 只在謂詞求值為 FALSE 時拒絕，而 `NULL IN ('action','wi-template')`
    求值為 NULL（`select (null in ('action','wi-template')) is null` → t），不是 FALSE。
    所以 v2_0022 那條「看起來明顯正確」的 CHECK 會讓 NULL 整批溜過去——
    而 NULL category 的模組兩層皆不屬，正是 ADR-024 那 16 筆隱形模組的原始形狀。
    NOT NULL（v2_0023）才是真正堵住它的那一半。

    若有人日後把 NOT NULL 拿掉、以為 CHECK 就夠，本測試會變紅。
    """
    with pytest.raises(IntegrityError) as exc:
        await _insert_module(db_session, None)
    msg = str(exc.value)
    assert "category" in msg and ("null value" in msg.lower() or "not-null" in msg.lower()), msg
    await db_session.rollback()


# ═════════ 2. migration 資料清理：有效性 + 冪等 ═════════

async def _invisible_count(session) -> int:
    r = await session.execute(
        text(
            "SELECT count(*) FROM motion_modules "
            "WHERE category IS NULL OR category NOT IN ('action','wi-template')"
        )
    )
    return r.scalar_one()


async def test_delete_sql_removes_invisible_rows_and_leaves_no_orphans(db_session):
    """先造隱形列（含其版本列）→ 跑 migration 的 DELETE → 該列消失、版本列 CASCADE 一併消失。"""
    # CHECK 已存在，故必須暫時停用才能造出 migration 當年要清的髒資料。
    await db_session.execute(
        text(f"ALTER TABLE motion_modules DROP CONSTRAINT {MIG._CK_NAME}")
    )
    mid = await _insert_module(db_session, "取放", name="mig22-invisible")
    rs_id = (
        await db_session.execute(text("SELECT id FROM rule_sets ORDER BY created_at LIMIT 1"))
    ).scalar_one()
    vid = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO motion_module_versions
                (id, module_id, version_no, rule_set_id, rows, total_tmu, total_seconds,
                 published_by, published_at)
            VALUES (:vid, :mid, 1, :rs, '[]'::jsonb, 0, 0, 'SYSTEM', NOW())
            """
        ),
        {"vid": vid, "mid": mid, "rs": rs_id},
    )
    assert await _invisible_count(db_session) == 1

    await db_session.execute(text(MIG.SQL_DELETE_INVISIBLE_MODULES))

    # 具體斷言：該模組與其版本列都不在，且不是「順手刪光整張表」。
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM motion_modules WHERE id = :id"), {"id": mid}
        )
    ).scalar_one() == 0
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM motion_module_versions WHERE id = :id"), {"id": vid}
        )
    ).scalar_one() == 0
    # 無孤兒版本列
    assert (
        await db_session.execute(
            text(
                "SELECT count(*) FROM motion_module_versions v "
                "WHERE NOT EXISTS (SELECT 1 FROM motion_modules m WHERE m.id = v.module_id)"
            )
        )
    ).scalar_one() == 0
    # 具鑑別力：剩下的 category 值集合恰為兩層判別值（不是只斷言「筆數變了」）
    cats = {
        r[0]
        for r in (
            await db_session.execute(text("SELECT DISTINCT category FROM motion_modules"))
        ).all()
    }
    assert cats <= {"action", "wi-template"}, f"仍有非兩層判別值殘留：{cats}"


async def test_delete_sql_also_removes_null_category_rows(db_session):
    """NULL category 同樣是「兩層皆不屬」→ 必須一併刪除（NOT IN 對 NULL 求值為 NULL，
    所以 migration 顯式寫了 OR IS NULL；若那半句被拿掉，本測試變紅）。

    v2_0023 之後 NULL 已寫不進去，故須先卸下 NOT NULL 才能重現 migration 當年要清的髒資料。
    """
    await _drop_not_null(db_session)
    mid = await _insert_module(db_session, None, name="mig22-null-cat")
    await db_session.execute(text(MIG.SQL_DELETE_INVISIBLE_MODULES))
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM motion_modules WHERE id = :id"), {"id": mid}
        )
    ).scalar_one() == 0


async def test_delete_sql_is_idempotent_noop_when_clean(db_session):
    """對「已無隱形列」的 DB 重跑 → 不報錯，且不動到合法列。"""
    keep = await _insert_module(db_session, "action", name="mig22-keep")
    before = (
        await db_session.execute(text("SELECT count(*) FROM motion_modules"))
    ).scalar_one()
    assert await _invisible_count(db_session) == 0

    for _ in range(2):  # 重跑兩次，證明 no-op 可重複執行
        await db_session.execute(text(MIG.SQL_DELETE_INVISIBLE_MODULES))

    after = (
        await db_session.execute(text("SELECT count(*) FROM motion_modules"))
    ).scalar_one()
    assert after == before
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM motion_modules WHERE id = :id"), {"id": keep}
        )
    ).scalar_one() == 1


# ═════════ 2b. schema 端：category 必填且限定值域（D9b）═════════
# DB 約束是兜底；第一道防線是 schema，讓呼叫端拿到 422 而不是 500。

async def test_create_module_without_category_is_422(client):
    """省略 category → 422。

    刻意**不**預設成 'action'：那是靜默猜測呼叫端意圖（守則 §7 第 8 條），
    WI 範本被預設成 action 會直接錯層。沒有 category 的模組兩層皆不屬＝隱形模組，
    是這批要消滅的狀態，所以省略它就是呼叫端錯誤。
    """
    r = await client.post(
        "/api/v2/motion-modules",
        json={"name_zh": f"mig22-nocat-{uuid.uuid4().hex[:8]}", "scope": "global"},
    )
    assert r.status_code == 422, r.text
    # 具鑑別力：確認 422 真的是 category 缺漏造成，而不是碰巧別的欄位不合法
    assert any(
        "category" in str(e.get("loc", "")) for e in r.json()["error"]["detail"]["errors"]
    ), r.text


@pytest.mark.parametrize("bad", ["取放", "組裝", "ACTION", "wi_template", ""])
async def test_create_module_with_illegal_category_is_422(client, bad):
    """非兩層判別值 → 422（含大小寫與底線變體等易犯錯法）。"""
    r = await client.post(
        "/api/v2/motion-modules",
        json={
            "name_zh": f"mig22-badcat-{uuid.uuid4().hex[:8]}",
            "category": bad,
            "scope": "global",
        },
    )
    assert r.status_code == 422, r.text
    assert any("category" in str(e.get("loc", "")) for e in r.json()["error"]["detail"]["errors"]), r.text


async def test_create_module_with_null_category_is_422(client):
    """顯式送 null 也要 422（不是被當成「沒送」而放行）。"""
    r = await client.post(
        "/api/v2/motion-modules",
        json={
            "name_zh": f"mig22-nullcat-{uuid.uuid4().hex[:8]}",
            "category": None,
            "scope": "global",
        },
    )
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("category", ["action", "wi-template"])
async def test_create_module_with_valid_category_succeeds(client, category):
    """正常路徑不受影響：兩個合法值都能建，且回傳值就是送進去的那個。"""
    r = await client.post(
        "/api/v2/motion-modules",
        json={
            "name_zh": f"mig22-ok-{uuid.uuid4().hex[:8]}",
            "category": category,
            "scope": "global",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["category"] == category


async def test_update_module_with_illegal_category_is_422(client):
    """PUT 也要守：不能用更新把既有模組改成隱形。"""
    mid = (
        await client.post(
            "/api/v2/motion-modules",
            json={
                "name_zh": f"mig22-upd-{uuid.uuid4().hex[:8]}",
                "category": "action",
                "scope": "global",
            },
        )
    ).json()["id"]

    r = await client.put(f"/api/v2/motion-modules/{mid}", json={"category": "取放"})
    assert r.status_code == 422, r.text

    # 具鑑別力：被擋下後原值不變（不是擋了卻已寫進去）
    got = await client.get(f"/api/v2/motion-modules/{mid}")
    assert got.json()["category"] == "action"


async def test_update_module_category_to_valid_value_succeeds(client):
    """選填語意保留：送合法值可改層（action → wi-template）。"""
    mid = (
        await client.post(
            "/api/v2/motion-modules",
            json={
                "name_zh": f"mig22-updok-{uuid.uuid4().hex[:8]}",
                "category": "action",
                "scope": "global",
            },
        )
    ).json()["id"]

    r = await client.put(f"/api/v2/motion-modules/{mid}", json={"category": "wi-template"})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "wi-template"


# ═════════ 3. 範本內寫死的 V1 清除 ═════════

async def test_no_template_carries_rule_set_code(db_session):
    """ADR-024 §3-2：現有 16 筆範本的 cycle_template 不得再含 rule_set_code key。"""
    r = await db_session.execute(
        text("SELECT count(*) FROM motion_templates WHERE cycle_template ? 'rule_set_code'")
    )
    assert r.scalar_one() == 0


async def test_no_template_mentions_legacy_v1(db_session):
    """更強的網：整個 cycle_template 內不得出現任何 MINIMOST_* 字樣（含巢狀位置）。"""
    r = await db_session.execute(
        text("SELECT count(*) FROM motion_templates WHERE cycle_template::text LIKE '%MINIMOST%'")
    )
    assert r.scalar_one() == 0


async def test_strip_sql_is_idempotent(db_session):
    """重跑 UPDATE 不報錯（key 已不存在時 WHERE 濾掉，影響 0 列）。"""
    for _ in range(2):
        await db_session.execute(text(MIG.SQL_STRIP_TEMPLATE_RULE_SET_CODE))
    r = await db_session.execute(
        text("SELECT count(*) FROM motion_templates WHERE cycle_template ? 'rule_set_code'")
    )
    assert r.scalar_one() == 0


async def test_strip_sql_removes_only_that_key(db_session):
    """造一筆帶 V1 的範本 → 跑 strip → 只有該 key 消失，其餘 slot 原封不動。"""
    tid = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO motion_templates
                (id, name_zh, keywords, seq_kind, cycle_template, status, created_by)
            VALUES (:id, :name, '{}'::text[], 'GM',
                    CAST(:ct AS jsonb), 'draft', 'IEC141289')
            """
        ),
        {
            "id": tid,
            "name": f"mig22-tmpl-{uuid.uuid4().hex[:8]}",
            "ct": '{"seq":"GM","rule_set_code":"MINIMOST_FACTORY_V1",'
                  '"g2":{"g_code":"g_grasp"},"a0":{"reach_cm":20}}',
        },
    )
    await db_session.execute(text(MIG.SQL_STRIP_TEMPLATE_RULE_SET_CODE))

    ct = (
        await db_session.execute(
            text("SELECT cycle_template FROM motion_templates WHERE id = :id"), {"id": tid}
        )
    ).scalar_one()
    assert "rule_set_code" not in ct, "rule_set_code 未被移除"
    # 具鑑別力：其他 key 完整保留（不是把整個 JSONB 清空）
    assert ct["seq"] == "GM"
    assert ct["g2"] == {"g_code": "g_grasp"}
    assert ct["a0"] == {"reach_cm": 20}


async def test_api_create_template_does_not_write_rule_set_code(client):
    """寫入路徑同步堵住：POST /motion-templates 不得把 rule_set_code 存進 cycle_template，
    否則新環境會與 migration 過的舊環境不一致（客戶端明給 V1 也一樣要被丟掉）。"""
    body = {
        "name_zh": f"mig22-api-{uuid.uuid4().hex[:8]}",
        "seq_kind": "GM",
        "cycle_template": {
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V1",  # 客戶端硬塞
            "g2": {"g_code": "g_grasp"},
        },
    }
    r = await client.post("/api/v2/motion-templates", json=body)
    assert r.status_code == 201, r.text
    ct = r.json()["cycle_template"]
    assert "rule_set_code" not in ct, f"API 把 rule_set_code 寫回去了：{ct.get('rule_set_code')}"
    assert ct["seq"] == "GM"           # 其餘內容照常保存
    assert ct["g2"]["g_code"] == "g_grasp"


async def test_api_patch_template_does_not_write_rule_set_code(client):
    """PATCH 路徑同上。"""
    body = {
        "name_zh": f"mig22-patch-{uuid.uuid4().hex[:8]}",
        "seq_kind": "GM",
        "cycle_template": {"seq": "GM", "g2": {"g_code": "g_grasp"}},
    }
    tid = (await client.post("/api/v2/motion-templates", json=body)).json()["id"]

    r = await client.patch(
        f"/api/v2/motion-templates/{tid}",
        json={"cycle_template": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                                 "g2": {"g_code": "g_pick_sel"}}},
    )
    assert r.status_code == 200, r.text
    ct = r.json()["cycle_template"]
    assert "rule_set_code" not in ct
    assert ct["g2"]["g_code"] == "g_pick_sel"
