"""ADR-032 D6 後半（覆核 mutation）＋ D4（`_en` 專用寫入閘）的端點測試。

三組：

1. **D4 的 `_en` 寫入閘**（`PATCH /rule-sets/{code}/params/{param}/options/{code}/en`）
   ——正向（**active 的 certified_import 版**改得動英文）、負向（同一條路徑改
   `label_zh`／`base_tmu` 被拒、retired 被拒、viewer 403、I5 衝突被拒），
   以及「沒有連坐放寬 `assert_editable`」的對照斷言：同一個 option 走一般
   PATCH 仍然 409。這一條是本檔最重要的斷言——D4 的閘一旦能寫到 `_zh`／TMU，
   ADR-023 §3.3 規則 1 與規則 3 就整個被繞過了。
2. **覆核 mutation**（`POST /i18n/review/mark-reviewed`／`assign`）——標記已覆核、
   同一交易內順手改譯文、交易原子性、指派／取消指派、RBAC。
3. **`field='sentence'` 的可達性**——Phase C 寫進側表的 63 筆句面覆核狀態先前
   永遠不會出現在待審清單裡（`_candidates_sql` 對 rule_option 硬寫 `'label'`），
   本輪補上；這裡守住它不再退回去。
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from ddm_v2.models.v2.i18n import I18nReviewState
from ddm_v2.models.v2.rule_set import RuleSet

pytestmark = pytest.mark.integration

CERTIFIED = "MINIMOST_FACTORY_V2"

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_i18n_labels.py"


def _load_seed_module():
    name = "_dev_seed_i18n_labels_mutations_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SEED = _load_seed_module()


async def _seeded(db_session) -> bool:
    return (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == CERTIFIED))).first() is not None


async def _reset_human_review_state(db_session) -> None:
    """清掉「已由人覆核」的側表列，讓灌值腳本重建 machine／legacy_seed 的基準線。

    本檔多條測試的前提是「這批翻譯還沒有人覆核過」（`reviewed == 0`、
    `status == 'unreviewed'`、待審清單長度＝全部候選列）。那個前提是**共用開發庫
    當下的可變狀態**：任何人在 D6 英文覆核介面按一次「標記已覆核」，
    `i18n_review_state` 就多一列 `source='human'`，而灌值腳本明文「側表已有列就
    不重覆寫入（尊重既有覆核狀態）」——重跑種子也還原不回來，這些測試從此常紅。
    照 CI_GATES 硬性規則 7，前提由測試自己 arrange。刪除走 savepoint 隔離連線，
    測試結束隨外層 transaction rollback，共用開發庫零殘留。
    """
    await db_session.execute(delete(I18nReviewState).where(I18nReviewState.source == "human"))
    await db_session.flush()


@pytest_asyncio.fixture
async def seeded(db_session):
    """前置：active 版有選項、英文已灌值、且尚無人工覆核（覆核的對象必須先存在且待審）。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    await _reset_human_review_state(db_session)
    await SEED.seed_i18n_labels(db_session)
    await db_session.commit()


@pytest_asyncio.fixture
async def draft_rs(db_session) -> str:
    from ddm_v2.services.v2 import rule_set_service as rsvc

    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    code = f"UT_I18N_MUT_{uuid.uuid4().hex[:8]}"
    await rsvc.clone_draft(db_session, CERTIFIED, code, "i18n mutation 測試草稿")
    await db_session.commit()
    return code


@pytest_asyncio.fixture
async def retired_rs(db_session) -> str:
    """clone → publish → retire，造出一個 retired 版本（D4 唯一的拒絕理由）。

    刻意不動 V1／V2 的狀態：那兩個是全庫共用的資料前置條件，改它們會讓同一條
    connection 上的其他測試看到不該有的狀態。
    """
    from ddm_v2.services.v2 import rule_set_service as rsvc

    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    code = f"UT_I18N_RETIRED_{uuid.uuid4().hex[:8]}"
    await rsvc.clone_draft(db_session, CERTIFIED, code, "i18n retired 測試版本")
    await rsvc.publish(db_session, code, actor="UT")
    await rsvc.retire(db_session, code, actor="UT")
    await db_session.commit()
    return code


async def _label_zh_en(db_session, rule_set_code: str, option_code: str) -> tuple[str, str | None]:
    row = (await db_session.execute(text(
        "SELECT t.label_zh, t.label_en FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :rs AND t.code = :c"
    ), {"rs": rule_set_code, "c": option_code})).one()
    return row[0], row[1]


async def _sentence_zh_en(
    db_session, rule_set_code: str, option_code: str, table: str = "rule_g_actions"
) -> tuple[str | None, str | None]:
    row = (await db_session.execute(text(
        f"SELECT t.sentence_text_zh, t.sentence_text_en FROM {table} t "  # noqa: S608 - 常數表名
        "JOIN rule_sets rs ON rs.id = t.rule_set_id WHERE rs.code = :rs AND t.code = :c"
    ), {"rs": rule_set_code, "c": option_code})).one()
    return row[0], row[1]


async def _viewer_headers(prefix: str) -> dict[str, str]:
    """從未出現過的員編 → `current_user` JIT 建立 `roles=[]`（viewer）。"""
    return {"X-Username": f"{prefix}_{uuid.uuid4().hex[:6]}"}


# ══════════════════════════════════════════════════════════════════
# 1. D4：`_en` 專用寫入閘
# ══════════════════════════════════════════════════════════════════

async def test_en_gate_writes_label_en_on_active_certified_rule_set(client, db_session, seeded):
    """D4 的核心：**active ＋ published ＋ certified_import** 的 V2 也改得動英文標籤。

    這正是 ADR-032 D4 在 ADR-023 §3.3 規則 1 矩陣新增的那一列；先前
    `assert_editable` 對 `provenance='certified_import'` 一律 409，63 列 rule-option
    的英文一個字都改不動。
    """
    new_en = f"Grasp (UT {uuid.uuid4().hex[:6]})"
    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en",
        json={"label_en": new_en},
    )
    assert r.status_code == 200, r.text
    assert r.json()["label_en"] == new_en

    zh, en = await _label_zh_en(db_session, CERTIFIED, "g_grasp")
    assert en == new_en
    assert zh == "抓握", "`_en` 寫入閘不得碰中文標籤"


async def test_ordinary_option_patch_on_certified_rule_set_is_still_409(client, seeded):
    """對照組：**沒有連坐放寬 `assert_editable`**。同一個 option 走一般 PATCH 仍 409
    CERTIFIED_IMMUTABLE——D4 開的是一條並列的新路徑，不是把舊路徑的門檻調低。
    """
    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp",
        json={"label_en": "should not pass"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "CERTIFIED_IMMUTABLE"


@pytest.mark.parametrize(
    "payload",
    [
        {"label_zh": "改中文"},
        {"base_tmu": 3},
        {"label_en": "ok", "label_zh": "夾帶中文"},
        {"code": "g_renamed"},
        {"is_active": False},
    ],
)
async def test_en_gate_rejects_any_field_outside_the_two_en_columns(
    client, db_session, seeded, payload
):
    """**本檔最重要的負向斷言**：這條閘是唯一能寫進 `certified_import` active 版的
    入口，一旦能順帶寫 `label_zh`／`base_tmu`，`_zh` 與 TMU 值就跟著解凍了
    （ADR-032 D4／I3）。夾帶（合法欄位 ＋ 非法欄位）也必須整包拒收，不得只寫合法的那個。
    """
    zh_before, en_before = await _label_zh_en(db_session, CERTIFIED, "g_grasp")
    tmu_before = (await db_session.execute(text(
        "SELECT t.base_tmu FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :rs AND t.code = 'g_grasp'"
    ), {"rs": CERTIFIED})).scalar_one()

    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en", json=payload
    )
    assert r.status_code == 422, r.text

    zh_after, en_after = await _label_zh_en(db_session, CERTIFIED, "g_grasp")
    tmu_after = (await db_session.execute(text(
        "SELECT t.base_tmu FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :rs AND t.code = 'g_grasp'"
    ), {"rs": CERTIFIED})).scalar_one()
    assert (zh_after, en_after, tmu_after) == (zh_before, en_before, tmu_before)


async def test_en_gate_service_layer_also_rejects_non_en_fields(db_session, seeded):
    """schema 的 `extra="forbid"` 之外，service 層另有一道欄位白名單——直接呼叫
    service（繞過 HTTP 驗證層）也必須擋下來，否則白名單只是註解。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    with pytest.raises(opsvc.EnFieldNotWritable) as exc:
        await opsvc.update_option_en_text(
            db_session, CERTIFIED, "G", None, "g_grasp",
            {"label_en": "ok", "base_tmu": 999}, actor="UT",
        )
    assert "base_tmu" in str(exc.value)


async def test_en_gate_rejects_retired_rule_set(client, db_session, retired_rs):
    """retired 是終態，`_en` 也不可寫（D4 矩陣那一列唯一的 ❌）。"""
    r = await client.patch(
        f"/api/v2/rule-sets/{retired_rs}/params/G/options/g_grasp/en",
        json={"label_en": "Should be rejected"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "RULE_SET_RETIRED"


async def test_en_gate_allows_published_non_active_rule_set(client, db_session, seeded):
    """矩陣的 published(非 active) 那一格：V1 是 published 且非 active，仍可寫 `_en`。"""
    v1 = (await db_session.execute(
        select(RuleSet).where(RuleSet.status == "published", RuleSet.is_active.is_(False))
    )).scalars().first()
    if v1 is None:
        pytest.skip("DB 無 published 非 active 版本")
    r = await client.patch(
        f"/api/v2/rule-sets/{v1.code}/params/G/options/g_grasp/en",
        json={"label_en": f"Grasp (UT v1 {uuid.uuid4().hex[:6]})"},
    )
    assert r.status_code == 200, r.text


async def test_en_gate_requires_analyst(client, seeded):
    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en",
        json={"label_en": "viewer should not pass"},
        headers=await _viewer_headers("ZZZ_EN_GATE_VIEWER"),
    )
    assert r.status_code == 403, r.text


async def test_en_gate_enforces_i5_uniqueness(client, db_session, seeded):
    """I5（量化風險：`g_grasp` 6 TMU vs `g_touch` 3 TMU）：同一參數表內英文標籤
    正規化後必須唯一。灌值腳本在灌值當下就守著這件事，D4 開了線上編輯之後，
    這條線上路徑必須守同一件事——否則 I5 只剩「腳本灌的那批」成立。
    """
    _zh, touch_en = await _label_zh_en(db_session, CERTIFIED, "g_touch")
    assert touch_en, "前置條件：g_touch 應已有英文標籤"

    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en",
        json={"label_en": touch_en},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "EN_LABEL_NOT_UNIQUE"

    _zh2, grasp_en = await _label_zh_en(db_session, CERTIFIED, "g_grasp")
    assert grasp_en != touch_en


async def test_en_gate_writes_sentence_text_en_and_audit_log(client, db_session, seeded):
    new_sent = f"grasp it (UT {uuid.uuid4().hex[:6]})"
    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en",
        json={"sentence_text_en": new_sent},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sentence_text_en"] == new_sent

    logged = (await db_session.execute(text(
        "SELECT payload FROM workflow_audit_log WHERE action = 'option_en_update' "
        "ORDER BY created_at DESC LIMIT 1"
    ))).scalar_one()
    assert logged["option_code"] == "g_grasp"
    assert logged["after"]["sentence_text_en"] == new_sent


async def test_en_gate_no_write_no_audit(client, db_session, seeded):
    """值沒變就不寫 audit——留痕要留在「真的改了什麼」上，不是每次按下儲存。"""
    _zh, current_en = await _label_zh_en(db_session, CERTIFIED, "g_grasp")
    before = (await db_session.execute(text(
        "SELECT count(*) FROM workflow_audit_log WHERE action = 'option_en_update'"
    ))).scalar_one()

    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en",
        json={"label_en": current_en},
    )
    assert r.status_code == 200, r.text
    after = (await db_session.execute(text(
        "SELECT count(*) FROM workflow_audit_log WHERE action = 'option_en_update'"
    ))).scalar_one()
    assert after == before


# ══════════════════════════════════════════════════════════════════
# 2. 覆核 mutation
# ══════════════════════════════════════════════════════════════════

async def _pending_item(
    client, *, scope_key: str, field: str, rule_set_code: str = CERTIFIED
) -> dict | None:
    r = await client.get("/api/v2/i18n/review/pending", params={"entity_type": "rule_option"})
    assert r.status_code == 200, r.text
    for item in r.json():
        if (
            item["scope_key"] == scope_key
            and item["field"] == field
            and item["rule_set_code"] == rule_set_code
        ):
            return item
    return None


async def test_mark_reviewed_marks_row_human_and_removes_it_from_pending(client, seeded):
    before = await _pending_item(client, scope_key="g:g_grasp", field="label")
    assert before is not None and before["status"] == "unreviewed"
    summary_before = (await client.get(
        "/api/v2/i18n/review/summary", params={"entity_type": "rule_option"})).json()

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "g:g_grasp", "field": "label"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] is None, "標記完成後不該還在待審三態裡"
    assert body["review_source"] == "human"
    assert body["reviewed_by"] == "IEC141289"
    assert body["reviewed_at"] is not None

    assert await _pending_item(client, scope_key="g:g_grasp", field="label") is None
    summary_after = (await client.get(
        "/api/v2/i18n/review/summary", params={"entity_type": "rule_option"})).json()
    assert summary_after["pending"] == summary_before["pending"] - 1, (
        "D6 的驗收定義是「覆核進度是可見且**可下降**的數字」"
    )
    assert summary_after["reviewed"] == summary_before["reviewed"] + 1
    assert summary_after["total"] == summary_before["total"]


async def test_mark_reviewed_preserves_machine_translation_provenance(client, db_session, seeded):
    """只覆核、沒改譯文時，`translated_by`／`translated_at` 必須保留原值——
    「這批是哪個模型翻的」是還原不回來的事實，覆核並沒有改變它。
    """
    from ddm_v2.services.v2 import i18n_service as svc

    before = await svc.get_review_state(db_session, "rule_option", "g:g_grab", "label")
    # 這一條在不同環境可能是 machine 或 legacy_seed（看 `_en` 是不是先於 seed 就有值），
    # 兩者都是「未經人覆核的既有譯文」，本測試要守的是**覆核不得抹掉它的出處**。
    assert before is not None and before.source in ("machine", "legacy_seed")
    translated_by, translated_at = before.translated_by, before.translated_at

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "g:g_grab", "field": "label"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["translated_by"] == translated_by

    db_session.expire_all()
    after = await svc.get_review_state(db_session, "rule_option", "g:g_grab", "label")
    assert after is not None
    assert after.translated_by == translated_by
    assert after.translated_at == translated_at
    assert after.target_sha256 is not None, "覆核必須記下當下的英文譯文基準"


async def test_mark_reviewed_with_target_en_writes_translation_and_state_together(
    client, db_session, seeded
):
    new_en = f"Regrasp (UT {uuid.uuid4().hex[:6]})"
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_regrasp", "field": "label",
            "target_en": new_en, "note": "UT 覆核順手修正",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_en"] == new_en and body["status"] is None

    _zh, en = await _label_zh_en(db_session, CERTIFIED, "g_regrasp")
    assert en == new_en, "譯文必須真的落盤，不只是側表說覆核了"

    from ddm_v2.services.v2 import i18n_service as svc

    state = await svc.get_review_state(db_session, "rule_option", "g:g_regrasp", "label")
    assert state is not None
    assert state.source == "human" and state.reviewed_by == "IEC141289"
    assert state.translated_by == "IEC141289", "改了譯文，翻譯者就是這位覆核者"
    assert state.target_sha256 == svc.norm_sha256(new_en)
    assert state.note == "UT 覆核順手修正"


async def test_mark_reviewed_is_atomic_translation_rolls_back_when_state_write_fails(
    client, db_session, seeded, monkeypatch
):
    """交易原子性：譯文與側表要嘛都寫、要嘛都不寫。

    這裡把**側表寫入**打成失敗（譯文那一步已經成功），驗證整批 rollback ——
    另一個方向（閘先擋下、側表沒被碰過）由 `test_en_gate_rejects_*` 系列涵蓋。

    **兩個斷言，缺一不可**（第二個是 2026-08-20 覆審補的）：只有
    `en_after == en_before` 時，「譯文那一步根本沒執行」與「執行了又 rollback」在
    斷言下**不可分辨**——把 `_write_target_en` 改成 no-op 或延到側表寫入之後，
    測試照樣綠。所以 `_boom` 在 raise 之前先用**同一個 session**（`upsert_review_state`
    的第一個位置參數，就是 `mark_reviewed` 手上那個）把 `label_en` 讀出來，確認
    譯文確實已經落在這個交易裡；末尾再斷言它等於探針值。
    """
    from ddm_v2.services.v2 import i18n_service as svc

    _zh, en_before = await _label_zh_en(db_session, CERTIFIED, "g_grasp")
    probe = f"Atomicity probe {uuid.uuid4().hex[:6]}"
    seen: dict[str, str | None] = {}

    async def _boom(session, *_a, **_kw):
        seen["en"] = (await _label_zh_en(session, CERTIFIED, "g_grasp"))[1]
        raise RuntimeError("UT: 側表寫入失敗")

    monkeypatch.setattr(svc, "upsert_review_state", _boom)

    with pytest.raises(RuntimeError, match="UT: 側表寫入失敗"):
        await client.post(
            "/api/v2/i18n/review/mark-reviewed",
            json={
                "entity_type": "rule_option", "scope_key": "g:g_grasp", "field": "label",
                "target_en": probe,
            },
        )

    assert seen.get("en") == probe, (
        "側表寫入被呼叫的當下，譯文必須已經落在同一個交易裡——否則這個測試守的只是"
        "「什麼都沒做」，不是原子性"
    )
    db_session.expire_all()
    _zh2, en_after = await _label_zh_en(db_session, CERTIFIED, "g_grasp")
    assert en_after == en_before, "側表寫入失敗時，已落盤的譯文必須一起被 rollback"


async def test_editing_en_after_review_brings_the_row_back_to_pending(client, db_session, seeded):
    """`target_sha256` 的過期偵測（v2_0043，D6 末尾 park 的設計題）：覆核完之後
    有人改英文 → 這一列自己回到待審清單，`status='stale'` ＋ `target_changed=true`，
    而 `source_changed` 維持 false（中文一個字沒動）。
    """
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "g:g_pat", "field": "label"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] is None
    assert await _pending_item(client, scope_key="g:g_pat", field="label") is None

    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_pat/en",
        json={"label_en": f"Pat lightly (UT {uuid.uuid4().hex[:6]})"},
    )
    assert r.status_code == 200, r.text

    item = await _pending_item(client, scope_key="g:g_pat", field="label")
    assert item is not None, "覆核後改了英文，這一列必須重回待審清單"
    assert item["status"] == "stale"
    assert item["target_changed"] is True
    assert item["source_changed"] is False, "中文沒變，不該報成中文來源過期"


async def test_target_changed_is_false_for_rows_that_were_never_reviewed(client, seeded):
    """v2_0043 是純加法：既有列的 `target_sha256` 全是 NULL ＝沒有基準可比較 →
    `target_changed` 一律 false，上線當下不會有任何一列憑空變成 stale。
    """
    r = await client.get("/api/v2/i18n/review/pending", params={"entity_type": "rule_option"})
    assert r.status_code == 200, r.text
    items = r.json()
    assert items, "前置條件：應該有待審項"
    assert all(i["target_changed"] is False for i in items if i["reviewed_by"] is None)


async def test_mark_reviewed_rejects_a_row_without_translation(client, db_session, draft_rs):
    """反橡皮圖章：沒有譯文的列不得被標成已覆核（覆核率會上升，英文卻還是空的）。"""
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": "ut_mark_no_en", "label_zh": "測試未翻譯", "base_tmu": 3},
        actor="UT",
    )
    await db_session.commit()

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:ut_mark_no_en",
            "field": "label", "rule_set_code": draft_rs,
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "I18N_REVIEW_TARGET_MISSING"

    # 但同一個請求帶上譯文就可以——「先有字才能覆核」，不是「不准覆核」。
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:ut_mark_no_en",
            "field": "label", "rule_set_code": draft_rs, "target_en": "UT probe action",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] is None


async def test_mark_reviewed_rejects_blank_label_but_allows_blank_sentence(client, db_session, seeded):
    """空白標籤＝沒有譯文（422）；空字串**句面**是合法值（「這條刻意不入句」，D7.6）。"""
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_tap", "field": "label",
            "target_en": "   ",
        },
    )
    assert r.status_code == 422, r.text

    await db_session.execute(text(
        "UPDATE rule_m_verbs SET sentence_text_en = '' WHERE code = 'm_hand' AND rule_set_id = "
        "(SELECT id FROM rule_sets WHERE code = :rs)"
    ), {"rs": CERTIFIED})
    await db_session.commit()
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "m:m_hand", "field": "sentence"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] is None


async def test_mark_reviewed_unknown_scope_key_is_404(client, seeded):
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "g:does_not_exist", "field": "label"},
    )
    assert r.status_code == 404, r.text
    # NotFoundError 的頂層 code 固定是 NOT_FOUND，細分碼在 detail（main.py 的既有形狀）
    assert r.json()["error"]["detail"]["code"] == "I18N_REVIEW_ROW_NOT_FOUND"


async def test_mark_reviewed_on_a_draft_only_code_requires_explicit_rule_set_code(
    client, db_session, draft_rs
):
    """`scope_key` 不含 rule_set_id（D5），所以「哪一版」必須說清楚：未指定時以
    active 版為準，active 沒有這個 code 就 404，**不靜默改挑一個 draft**。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": "ut_draft_only_code", "label_zh": "測試草稿專屬", "base_tmu": 3, "label_en": "UT draft only"},
        actor="UT",
    )
    await db_session.commit()

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "g:ut_draft_only_code", "field": "label"},
    )
    assert r.status_code == 404, r.text

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:ut_draft_only_code",
            "field": "label", "rule_set_code": draft_rs,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["rule_set_code"] == draft_rs


async def test_mark_reviewed_works_for_master_data(client, db_session, seeded):
    """主數據（ADR-024）：詞彙庫的 `name_en` 也走同一組端點，覆核狀態同一張側表。

    覆核對象由測試自己建（CI_GATES 硬性規則 7：不得撈「第一列」）——原本是
    `select(WorkVocabItem).limit(1)`，那既沒有 ORDER BY（撈到哪一列不確定），
    又會在共用開發庫的既有詞彙上寫 `name_en`，而且庫裡沒詞彙時整條測試靜默 skip。
    """
    from ddm_v2.models.v2.vocab import WorkVocabItem

    item = WorkVocabItem(
        id=uuid.uuid4(), kind="object", name_zh=f"UT 覆核詞彙-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(item)
    await db_session.flush()

    new_en = f"UT vocab {uuid.uuid4().hex[:6]}"
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "vocab_item", "scope_key": str(item.id),
            "field": "name", "target_en": new_en,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] is None

    name_en = (await db_session.execute(text(
        "SELECT name_en FROM work_vocab_items WHERE id = :i"), {"i": item.id})).scalar_one()
    assert name_en == new_en


async def test_mark_reviewed_requires_analyst(client, seeded):
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "g:g_grasp", "field": "label"},
        headers=await _viewer_headers("ZZZ_MARK_VIEWER"),
    )
    assert r.status_code == 403, r.text


# ── 指派 ──────────────────────────────────────────────────────────

async def test_assign_and_unassign_a_pending_row(client, seeded):
    r = await client.post(
        "/api/v2/i18n/review/assign",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_touch",
            "field": "label", "assigned_to": "IEC999999",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_to"] == "IEC999999" and body["assigned_at"] is not None
    assert body["status"] == "unreviewed", "指派記的是「誰在處理」，不該改變 status"

    item = await _pending_item(client, scope_key="g:g_touch", field="label")
    assert item is not None and item["assigned_to"] == "IEC999999"

    r = await client.post(
        "/api/v2/i18n/review/assign",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_touch",
            "field": "label", "assigned_to": None,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["assigned_to"] is None and r.json()["assigned_at"] is None


async def test_assign_creates_a_side_row_for_a_never_translated_item(client, db_session, draft_rs):
    """`never_translated` 的列本來就沒有側表列（D5 預設值表），而那正是最需要有人
    認領的一批——指派必須能就地建列，且不得謊報譯文來源（`source='untranslated'`）。
    """
    from ddm_v2.services.v2 import i18n_service as svc
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": "ut_assign_untranslated", "label_zh": "測試指派未翻譯", "base_tmu": 3},
        actor="UT",
    )
    await db_session.commit()

    r = await client.post(
        "/api/v2/i18n/review/assign",
        json={
            "entity_type": "rule_option", "scope_key": "g:ut_assign_untranslated",
            "field": "label", "rule_set_code": draft_rs, "assigned_to": "IEC888888",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_to"] == "IEC888888"
    assert body["status"] == "never_translated", "指派不改變 status"

    state = await svc.get_review_state(db_session, "rule_option", "g:ut_assign_untranslated", "label")
    assert state is not None
    assert state.source == "untranslated", "尚無譯文的列不得被記成 machine/human/legacy_seed"
    assert state.reviewed_by is None and state.translated_by is None


async def test_assign_requires_analyst(client, seeded):
    r = await client.post(
        "/api/v2/i18n/review/assign",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_grasp",
            "field": "label", "assigned_to": "IEC999999",
        },
        headers=await _viewer_headers("ZZZ_ASSIGN_VIEWER"),
    )
    assert r.status_code == 403, r.text


async def test_mutation_payload_rejects_unknown_fields(client, seeded):
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_grasp", "field": "label",
            "reviewed_by": "IEC000000",  # 覆核者由伺服器決定，不收 client 宣告
        },
    )
    assert r.status_code == 422, r.text


# ══════════════════════════════════════════════════════════════════
# 3. `field='sentence'` 的可達性（本輪補的既有缺口）
# ══════════════════════════════════════════════════════════════════

async def test_sentence_rows_appear_in_the_pending_list(client, seeded):
    """Phase C 已經把 63 筆 `field='sentence'` 的覆核狀態寫進側表，但
    `_candidates_sql()` 對 rule_option 硬寫 `'label' AS field`，那批**永遠不會**
    出現在待審清單裡——使用者在英文介面實際讀到的敘事句面覆核追蹤是 0% 且不可達。
    """
    r = await client.get("/api/v2/i18n/review/pending", params={"entity_type": "rule_option"})
    assert r.status_code == 200, r.text
    fields = {i["field"] for i in r.json()}
    assert fields == {"label", "sentence"}, f"句面必須進得了待審清單，實際：{fields}"


async def test_sentence_rows_can_be_reviewed_and_count_toward_progress(client, db_session, seeded):
    item = await _pending_item(client, scope_key="g:g_grasp", field="sentence")
    assert item is not None and item["target_en"], "前置條件：句面應已灌值"

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={"entity_type": "rule_option", "scope_key": "g:g_grasp", "field": "sentence"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] is None

    assert await _pending_item(client, scope_key="g:g_grasp", field="sentence") is None
    # 同一個 scope_key 的 label 是**另一條**覆核項，不受句面覆核影響。
    label_item = await _pending_item(client, scope_key="g:g_grasp", field="label")
    assert label_item is not None and label_item["status"] == "unreviewed"


async def test_sentence_source_zh_follows_the_engine_fallback_chain(client, db_session, seeded):
    """句面的來源中文必須與引擎的回退鏈一致（`sentence_text_zh` 為 NULL／空字串時
    回退 `label_zh`）——否則句面留空的那幾條會拿一個引擎根本沒讀的字串去算 sha256，
    整批句面永遠顯示過期。
    """
    row = (await db_session.execute(text(
        "SELECT t.code, t.label_zh FROM rule_m_verbs t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :rs AND (t.sentence_text_zh IS NULL OR t.sentence_text_zh = '') LIMIT 1"
    ), {"rs": CERTIFIED})).first()
    if row is None:
        pytest.skip("active 版沒有句面留空的 M 動詞")
    code, label_zh = row

    r = await client.get("/api/v2/i18n/review/pending", params={"entity_type": "rule_option"})
    item = next(
        (i for i in r.json()
         if i["scope_key"] == f"m:{code}" and i["field"] == "sentence" and i["rule_set_code"] == CERTIFIED),
        None,
    )
    assert item is not None
    assert item["source_zh"] == label_zh, "句面留空時，來源中文應回退到 label_zh"


# ══════════════════════════════════════════════════════════════════
# 4. 覆審修正（2026-08-20 checkpoint：cr ＋ sec 兩席）
#
# 每一條都對應一個實測過的缺陷，不是補充覆蓋率。
# ══════════════════════════════════════════════════════════════════


async def test_assign_does_not_change_status_of_a_translated_row_without_side_table(
    client, db_session, draft_rs
):
    """「指派不會改變 status」——三處明文承諾（`assign_review` 檔頭、路由 docstring、
    ADR-032 D6 補記）唯一沒被測到、也正好會出事的那一支：**有譯文、無側表列**。

    修正前：`_classify` 讓這種列報 `stale`（`review_sha256=None != sha(zh)`），指派
    就地補一筆 `legacy_seed` 側表列之後變成 `unreviewed`——指派改變了 status，而且
    修正前的 `stale` 本身就是謊（這列從來沒有人覆核過，不可能「過期」）。
    日常可達：`POST /api/v2/vocab` 帶 `name_en` 建新詞彙就不寫側表列。
    """
    from ddm_v2.services.v2 import i18n_service as svc
    from ddm_v2.services.v2 import rule_option_service as opsvc

    tag = uuid.uuid4().hex[:6]
    code = f"ut_assign_translated_{tag}"
    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": code, "label_zh": f"測試指派已翻譯{tag}", "label_en": f"Assign probe {tag}",
         "base_tmu": 3},
        actor="UT",
    )
    await db_session.commit()

    assert await svc.get_review_state(db_session, "rule_option", f"g:{code}", "label") is None, (
        "前置條件：這一列刻意沒有側表列"
    )
    before = await _pending_item(client, scope_key=f"g:{code}", field="label", rule_set_code=draft_rs)
    assert before is not None
    assert before["status"] == "unreviewed", "有譯文、從未覆核過＝未覆核，不是過期"

    r = await client.post(
        "/api/v2/i18n/review/assign",
        json={
            "entity_type": "rule_option", "scope_key": f"g:{code}", "field": "label",
            "rule_set_code": draft_rs, "assigned_to": "IEC777777",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["assigned_to"] == "IEC777777"
    assert r.json()["status"] == before["status"], "指派記的是誰在處理，不是處理到哪"


async def test_mark_reviewed_rejects_blank_sentence_when_the_zh_sentence_is_not_empty(
    client, db_session, seeded
):
    """`field='sentence'` 的空字串例外**有前提**：中文句面本身為空（D7.6 刻意不入句）。

    修正前這個例外是無條件的：中文句面「抓握」的 `g_grasp` 也吃得下 `target_en=""`，
    回 200、`sentence_text_en` 被清成空、離開待審清單——63 條句面用 63 個空字串請求
    就能把 `n/126` 推到 126/126 而英文全空（ADR-032 R2 寫明的最可能失敗模式）。
    """
    sent_zh, sent_en_before = await _sentence_zh_en(db_session, CERTIFIED, "g_grasp")
    assert sent_zh, "前置條件：g_grasp 的中文句面非空"

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_grasp", "field": "sentence",
            "target_en": "",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "I18N_REVIEW_TARGET_MISSING"

    db_session.expire_all()
    _zh, sent_en_after = await _sentence_zh_en(db_session, CERTIFIED, "g_grasp")
    assert sent_en_after == sent_en_before, "被拒的請求不得動到譯文"
    item = await _pending_item(client, scope_key="g:g_grasp", field="sentence")
    assert item is not None, "被拒的請求不得讓這一列離開待審清單"


async def test_mark_reviewed_still_allows_blank_sentence_when_the_zh_sentence_is_empty(
    client, db_session, seeded
):
    """對照組：中文句面本身為空的那 7 條（`b_none`／`m_hand`／`x_none`…）維持可覆核
    ——空字串在那裡是有意義的值（「這條刻意不入句」），不是缺譯文。
    """
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "x:x_none", "field": "sentence",
            "target_en": "",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] is None
    _zh, en = await _sentence_zh_en(db_session, CERTIFIED, "x_none", table="rule_x_options")
    assert en == ""


async def test_mark_reviewed_rejects_a_never_translated_sentence_marked_with_blank(
    client, db_session, seeded
):
    """更直接的橡皮圖章：`sentence_text_en` 為 NULL、無側表列（`never_translated`）
    的列，用 `target_en=""` 就能標成已覆核——**完全沒有英文，卻算已覆核**。
    這裡把 `g_regrasp`（中文句面非空）打回 `never_translated` 再試。
    """
    await db_session.execute(text(
        "UPDATE rule_g_actions t SET sentence_text_en = NULL FROM rule_sets rs "
        "WHERE rs.id = t.rule_set_id AND rs.code = :rs AND t.code = 'g_regrasp'"
    ), {"rs": CERTIFIED})
    await db_session.execute(text(
        "DELETE FROM i18n_review_state WHERE scope_key = 'g:g_regrasp' AND field = 'sentence'"
    ))
    await db_session.commit()
    item = await _pending_item(client, scope_key="g:g_regrasp", field="sentence")
    assert item is not None and item["status"] == "never_translated"

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_regrasp", "field": "sentence",
            "target_en": "",
        },
    )
    assert r.status_code == 422, r.text
    still = await _pending_item(client, scope_key="g:g_regrasp", field="sentence")
    assert still is not None and still["status"] == "never_translated"


async def test_mark_reviewed_strips_target_en_like_the_dedicated_entry_points(
    client, db_session, seeded
):
    """`target_en` 的正規化必須與 `PATCH /api/v2/vocab/{id}` 一致（`schemas/v2/vocab.py`
    檔頭：「字串一律 strip……在入口擋掉」）。

    修正前實測同一個字串：覆核路徑存成 `'   Padded   '`、vocab PATCH 存成 `'Padded'`
    ——同一份資料兩個入口兩種結果，而覆核路徑是新開的那一個。
    """
    tag = uuid.uuid4().hex[:6]
    vid = (await db_session.execute(text(
        "SELECT id FROM work_vocab_items ORDER BY created_at LIMIT 1"
    ))).scalar_one()

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "vocab_item", "scope_key": str(vid), "field": "name",
            "target_en": f"   Padded {tag}   ",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["target_en"] == f"Padded {tag}"

    db_session.expire_all()
    name_en = (await db_session.execute(text(
        "SELECT name_en FROM work_vocab_items WHERE id = :i"), {"i": vid})).scalar_one()
    assert name_en == f"Padded {tag}", "覆核路徑寫進主數據的字串必須已 strip"


async def test_master_data_translation_change_is_audited_with_before_and_after(
    client, db_session, seeded
):
    """主數據（`vocab_item`／`motion_template`，約 75 條）的譯文改動要留前後值。

    `rule_option` 靠 `option_en_update` 記了完整的 `changed_fields: {before, after}`，
    主數據先前是裸 `setattr`、`i18n_review_mark` 的 payload 只有 `previous_source`／
    `previous_reviewed_by`——看得到「某人覆核過這條」，還原不了英文被改成什麼。
    """
    tag = uuid.uuid4().hex[:6]
    row = (await db_session.execute(text(
        "SELECT id, name_en FROM work_vocab_items ORDER BY created_at LIMIT 1"))).one()
    vid, name_en_before = row

    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "vocab_item", "scope_key": str(vid), "field": "name",
            "target_en": f"Audited {tag}",
        },
    )
    assert r.status_code == 200, r.text

    payload = (await db_session.execute(text(
        "SELECT payload FROM workflow_audit_log WHERE entity_type = 'vocab_item' "
        "AND entity_id = :i AND action = 'i18n_review_mark' ORDER BY created_at DESC LIMIT 1"
    ), {"i": vid})).scalar_one()
    assert payload["changed_fields"] == {
        "name_en": {"before": name_en_before, "after": f"Audited {tag}"}
    }


async def test_en_gate_strips_whitespace_only_sentence_text(client, db_session, seeded):
    """純空白的 `sentence_text_en` 不得落盤（`OptionEnTextIn` strip）。

    `most_engine/narrative_en._sent()` 的回退鏈是 `sentence_en or label_en`——`"   "`
    是 truthy，**不會**回退，會把一段空白當動詞組進英文敘事句（與幾小時前在 `_noun()`
    修掉的是同一類缺陷）。擋在入口，不動引擎。strip 後的 `""` 仍是合法的「刻意不入句」。
    """
    r = await client.patch(
        f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en",
        json={"sentence_text_en": "   "},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sentence_text_en"] == ""
    db_session.expire_all()
    _zh, en = await _sentence_zh_en(db_session, CERTIFIED, "g_grasp")
    assert en == "", "純空白必須在入口被 strip 成空字串，不得原樣落盤"


async def test_mark_reviewed_rejects_whitespace_only_sentence(client, db_session, seeded):
    """同一件事的另一個入口：`mark-reviewed` 的 `target_en="   "` 對**中文句面非空**
    的列 → 422（strip 後是空字串，而那條列的中文句面有字）。
    """
    _zh, before = await _sentence_zh_en(db_session, CERTIFIED, "g_pat")
    r = await client.post(
        "/api/v2/i18n/review/mark-reviewed",
        json={
            "entity_type": "rule_option", "scope_key": "g:g_pat", "field": "sentence",
            "target_en": "   ",
        },
    )
    assert r.status_code == 422, r.text
    db_session.expire_all()
    _zh2, after = await _sentence_zh_en(db_session, CERTIFIED, "g_pat")
    assert after == before


async def test_ordinary_option_create_and_update_enforce_i5(client, db_session, draft_rs):
    """I5 不只守 `_en` 專用閘：`label_en` 是 `_OptionIn` 的可寫欄位，一般 CRUD 先前
    完全沒有唯一性檢查——在任何 draft 上仍可把 `g_grasp`(6 TMU) 的英文改成與
    `g_touch`(3 TMU) 相同，等於 I5 只有「腳本灌的那批」與「`_en` 端點那條路」成立。
    """
    _zh, touch_en = await _label_zh_en(db_session, draft_rs, "g_touch")
    assert touch_en, "前置條件：draft 繼承了 active 的英文標籤"
    tag = uuid.uuid4().hex[:6]

    r = await client.post(
        f"/api/v2/rule-sets/{draft_rs}/params/G/options",
        json={"code": f"ut_i5_create_{tag}", "label_zh": f"測試建立{tag}",
              "label_en": touch_en, "base_tmu": 3},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "EN_LABEL_NOT_UNIQUE"

    r = await client.patch(
        f"/api/v2/rule-sets/{draft_rs}/params/G/options/g_grasp",
        json={"label_en": touch_en},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "EN_LABEL_NOT_UNIQUE"

    db_session.expire_all()
    _zh2, grasp_en = await _label_zh_en(db_session, draft_rs, "g_grasp")
    assert grasp_en != touch_en, "被拒的請求不得留下痕跡"


async def test_ordinary_option_update_without_label_en_is_unaffected_by_i5(client, draft_rs):
    """對照組：不動 `label_en` 的一般編輯不受 I5 影響——檢查以 `payload` 的鍵為準，
    不是拿 `validate_payload` 鋪底後的 `data`（那會讓改 `sort_order` 也被別人造成的
    既有衝突擋下）。
    """
    r = await client.patch(
        f"/api/v2/rule-sets/{draft_rs}/params/G/options/g_grasp", json={"sort_order": 7},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sort_order"] == 7


@pytest.mark.parametrize(
    ("payload", "endpoint"),
    [
        ({"label_en": "A" * 201}, "en_gate"),
        ({"sentence_text_en": "A" * 501}, "en_gate"),
        ({"field": "label", "target_en": "A" * 201}, "mark_reviewed"),
        ({"field": "sentence", "target_en": "A" * 501}, "mark_reviewed"),
    ],
)
async def test_en_text_has_a_length_cap(client, seeded, payload, endpoint):
    """`_en` 自由文字要有上限：這條路徑碰得到**生產字典的 active 認證版**，而任何
    analyst 都走得到——修正前實測 200,001 字元寫得進去。
    """
    if endpoint == "en_gate":
        r = await client.patch(
            f"/api/v2/rule-sets/{CERTIFIED}/params/G/options/g_grasp/en", json=payload
        )
    else:
        r = await client.post(
            "/api/v2/i18n/review/mark-reviewed",
            json={"entity_type": "rule_option", "scope_key": "g:g_grasp", **payload},
        )
    assert r.status_code == 422, r.text
