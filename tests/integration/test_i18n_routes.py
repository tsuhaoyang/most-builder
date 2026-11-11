"""`/api/v2/i18n/review/*` 端點（ADR-032 D6）：摘要 ＋ 待審清單，正常／邊界／RBAC。"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update

from ddm_v2.models.v2.i18n import I18nReviewState
from ddm_v2.models.v2.rule_set import RuleSet

pytestmark = pytest.mark.integration

CERTIFIED = "MINIMOST_FACTORY_V2"

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_i18n_labels.py"


def _load_seed_module():
    name = "_dev_seed_i18n_labels_routes_under_test"
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


async def _seed_labels(db_session) -> None:
    await _reset_human_review_state(db_session)
    await SEED.seed_i18n_labels(db_session)
    await db_session.commit()


@pytest_asyncio.fixture
async def draft_rs(db_session) -> str:
    """clone 出拋棄式 draft（provenance=cloned）——同 `test_i18n_review_state.py`
    的 fixture，供本檔的「有 draft 存在」迴歸測試使用（S1／S2）。刻意在這裡
    重複定義而不是搬進 `conftest.py`：這個 fixture 只有 i18n 兩個測試檔在用，
    放進全域 conftest 會擴大它的可見範圍卻沒有對應的共用需求。
    """
    from ddm_v2.services.v2 import rule_set_service as rsvc

    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    code = f"UT_I18N_ROUTES_{uuid.uuid4().hex[:8]}"
    await rsvc.clone_draft(db_session, CERTIFIED, code, "i18n 路由測試草稿")
    await db_session.commit()
    return code


async def _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session) -> None:
    """M1（2026-08-18 第二輪複審修正）：同 `test_i18n_review_state.py` 的同名函式
    ——刻意在這裡重複定義而不是搬進共用模組（同檔頭「重複定義 `draft_rs`」的理由：
    只有 i18n 兩個測試檔在用）。CI 種子鏈可能已經跑過 `dev_seed_i18n_labels.py`，
    active／`clone_draft` 出的 draft 的 `label_en` 可能一開局就是滿的，
    `_seed_labels()` 在這個 savepoint 裡會變成沒事可做的 no-op，S1 的迴歸測試因此
    不會顯形（不論有沒有修好都是綠燈）。這裡只清 `label_en` 本身，不動側表——
    S1 bug 的觸發條件正是「側表列已存在、`_en` 卻還沒填」。
    """
    rule_set_ids = (await db_session.execute(
        select(RuleSet.id).where((RuleSet.status == "draft") | (RuleSet.is_active.is_(True)))
    )).scalars().all()
    for model, _param, _labels in SEED.RULE_OPTION_TABLES:
        await db_session.execute(update(model).where(model.rule_set_id.in_(rule_set_ids)).values(label_en=None))
    await db_session.flush()


# ══════════════════════════════════════════════════════════════════
# RBAC：viewer 403、analyst+ 200（D6：分析師以上，取字典/主數據入口下界）
# ══════════════════════════════════════════════════════════════════

async def test_summary_requires_analyst_viewer_gets_403(client):
    r = await client.get(
        "/api/v2/i18n/review/summary", headers={"X-Username": "ZZZ_I18N_VIEWER"}
    )
    assert r.status_code == 403, r.text


async def test_pending_requires_analyst_viewer_gets_403(client):
    r = await client.get(
        "/api/v2/i18n/review/pending", headers={"X-Username": "ZZZ_I18N_VIEWER_2"}
    )
    assert r.status_code == 403, r.text


async def test_analyst_can_read_summary_and_pending(client):
    emp = "ZZZ_I18N_ANALYST"
    ur = await client.post(
        "/api/v2/admin/users",
        json={"employee_no": emp, "display_name": "UT i18n analyst", "roles": ["analyst"]},
    )
    assert ur.status_code == 200, ur.text
    h = {"X-Username": emp}

    r = await client.get("/api/v2/i18n/review/summary", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"total", "reviewed", "pending"}

    r = await client.get("/api/v2/i18n/review/pending", headers=h)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


async def test_admin_can_read_too(client):
    """admin(IEC141289，client 預設身分)也是 analyst 以上，理應可讀。"""
    r = await client.get("/api/v2/i18n/review/summary")
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════
# 正常路徑：摘要與清單反映灌值後的狀態
# ══════════════════════════════════════════════════════════════════

# 每一列選項對應**兩個**可譯欄位：`label`（下拉標籤）與 `sentence`（敘事句面）
# ——2026-08-20 起 `i18n_service._candidates_sql()` 兩種 field 都出候選（先前只出
# `label`，句面的覆核狀態寫得進側表卻永遠不會出現在待審清單裡）。分母因此從
# 「相異 scope_key 數」變成「相異 (scope_key, field) 數」。**刻意不寫死 ×2**：
# 逐 field 建鍵，日後再多一種 field 時測試自己會跟著對。
_RULE_OPTION_REVIEW_FIELDS = ("label", "sentence")


async def _in_scope_rule_set_ids(db_session) -> list:
    """`i18n_service.IN_SCOPE_RULE_SET_SQL` 的 Python 版（active ＋ 現存 draft）
    ——與 service 用同一個字面判準（`status='draft' OR is_active`），不是自己
    另外發明一份範圍定義。
    """
    return (await db_session.execute(
        select(RuleSet.id).where((RuleSet.status == "draft") | (RuleSet.is_active.is_(True)))
    )).scalars().all()


async def _rule_option_distinct_review_key_count(db_session) -> int:
    """`summary()` 的分母（DISTINCT `(entity_type, scope_key, field)`）——**刻意
    不硬編 126**：126 是「乾淨 DB、沒有 draft」時的實測數字（63 個 option code
    × label／sentence 兩個 field；2026-08-20 句面進清單之前是 63），DB 上一旦出現任何
    draft（不論是本測試自己建的、還是環境裡殘留的），summary 的分母**依然**
    等於相異 scope_key 數（因為 S2 修正把 summary 改成 DISTINCT 計數），
    但若那個 draft 帶著跟 active 不同的 code 集合（例如自訂了新選項），
    63 這個常數就不成立——直接查 DB 現況才是唯一準確的口徑（同一個粒度：
    `(param, code)` 的相異個數，對應側表 `scope_key` 的業務鍵）。
    """
    rule_set_ids = await _in_scope_rule_set_ids(db_session)
    keys: set[tuple[str, str]] = set()
    for model, param, _labels in SEED.RULE_OPTION_TABLES:
        codes = (await db_session.execute(
            select(model.code).where(model.rule_set_id.in_(rule_set_ids))
        )).scalars().all()
        keys.update((f"{param}:{c}", field) for c in codes for field in _RULE_OPTION_REVIEW_FIELDS)
    return len(keys)


async def _rule_option_row_count(db_session) -> int:
    """`pending_rows()` 的候選列數（**不去重**，每個 in-scope rule-set 版本各
    算一次）——`pending_rows()` 刻意不像 `summary()` 那樣去重（見
    `i18n_service.pending_rows` 檔頭：待審清單要讓使用者看到「哪個版本」卡住），
    所以拿來對照 `/pending` 回應長度的分母必須是「總列數」而不是「相異
    scope_key 數」，兩者在有 draft 時不相等。
    """
    rule_set_ids = await _in_scope_rule_set_ids(db_session)
    total = 0
    for model, _param, _labels in SEED.RULE_OPTION_TABLES:
        total += (await db_session.execute(
            select(func.count()).select_from(model).where(model.rule_set_id.in_(rule_set_ids))
        )).scalar_one()
    return int(total) * len(_RULE_OPTION_REVIEW_FIELDS)


async def test_summary_shape_matches_active_rule_option_count(client, db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await _seed_labels(db_session)
    expected = await _rule_option_distinct_review_key_count(db_session)

    r = await client.get("/api/v2/i18n/review/summary", params={"entity_type": "rule_option"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"total": expected, "reviewed": 0, "pending": expected}


async def test_summary_denominator_does_not_double_count_when_a_draft_shares_scope_keys(
    client, db_session, draft_rs
):
    """S2：一有 draft，`(rule-set × option)` 式計數會把同一條翻譯算兩次——
    這裡明確造出「有 draft」的情境（不靠環境殘留），驗證 summary 的分母
    仍然等於 DISTINCT scope_key 數，不會因為 `draft_rs` 而變成兩倍。
    """
    await _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session)  # M1
    await _seed_labels(db_session)
    expected = await _rule_option_distinct_review_key_count(db_session)
    # draft 與 active 共用完全相同的 code 集合（clone 出來的），所以這裡的
    # DISTINCT 個數應該等於「只看 active」時的個數——先驗證這個前提成立，
    # 才有資格說「summary 沒有把 draft 重複算進去」。
    active_only = (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == CERTIFIED)
    )).scalar_one()
    active_only_keys: set[tuple[str, str]] = set()
    for model, param, _labels in SEED.RULE_OPTION_TABLES:
        codes = (await db_session.execute(
            select(model.code).where(model.rule_set_id == active_only)
        )).scalars().all()
        active_only_keys.update(
            (f"{param}:{c}", field) for c in codes for field in _RULE_OPTION_REVIEW_FIELDS
        )
    assert expected == len(active_only_keys), "draft 不應該改變 DISTINCT (scope_key, field) 的個數"

    r = await client.get("/api/v2/i18n/review/summary", params={"entity_type": "rule_option"})
    assert r.status_code == 200, r.text
    assert r.json() == {"total": expected, "reviewed": 0, "pending": expected}, (
        f"draft_rs={draft_rs!r} 存在時，summary 分母不應該翻倍"
    )


async def _vocab_and_template_counts(db_session) -> tuple[int, int]:
    """`work_vocab_items`／`motion_templates` 的實際列數。

    **刻意不硬編 59／16**：這兩張表的列數依賴哪些 dev seed 腳本跑過——
    `dev_seed_v2.py` 只建 3 筆詞彙，完整的 59 筆需要另外的 `dev_seed_30rows.py`
    （backend CI job 不跑這支，只有 e2e job 跑），而 `motion_templates` 的 16 筆
    穩定來自 `dev_seed_templates.py`（backend job 有跑）。硬編 59 在乾淨 CI DB 上
    會紅——這正是同義詞守門測試踩過的同一種坑（見 CI 種子鏈驗證紀錄）。
    """
    from sqlalchemy import func, select

    from ddm_v2.models.v2.motion_template import MotionTemplate
    from ddm_v2.models.v2.vocab import WorkVocabItem

    vocab = (await db_session.execute(select(func.count()).select_from(WorkVocabItem))).scalar_one()
    templates = (await db_session.execute(select(func.count()).select_from(MotionTemplate))).scalar_one()
    return int(vocab), int(templates)


async def test_summary_aggregates_across_entity_types_when_unfiltered(client, db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await _seed_labels(db_session)
    rule_option_count = await _rule_option_distinct_review_key_count(db_session)
    vocab_count, template_count = await _vocab_and_template_counts(db_session)

    r = await client.get("/api/v2/i18n/review/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == rule_option_count + vocab_count + template_count


async def test_pending_list_items_have_the_documented_shape(client, db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await _seed_labels(db_session)
    expected = await _rule_option_row_count(db_session)

    r = await client.get(
        "/api/v2/i18n/review/pending", params={"entity_type": "rule_option", "status": "unreviewed"}
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == expected
    sample = items[0]
    assert {
        "entity_type", "scope_key", "field", "status", "rule_set_code",
        "source_zh", "target_en", "source_is_fallback", "source_changed", "review_source",
        "translated_by", "translated_at", "reviewed_by", "reviewed_at",
    } <= set(sample)
    assert sample["entity_type"] == "rule_option"
    assert sample["status"] == "unreviewed"
    assert sample["review_source"] in ("machine", "legacy_seed")
    assert isinstance(sample["source_changed"], bool)


async def _blank_zh_sentence_keys(db_session) -> set[tuple[str, str]]:
    """DB 現況：`(scope_key, rule_set_code)` 中**中文句面本身為空**的那些選項列。

    對照組刻意直接查 DB，而不是把 D7.6 的 7 個 code 抄進測試——抄一份就是第二個
    真相來源，字典改了測試也不會知道（下面的 active 版另有一條顯式的 pin，
    那條的用途相反：釘住「這批到底是哪幾條」，改動時要當場看見）。
    """
    rule_set_ids = await _in_scope_rule_set_ids(db_session)
    keys: set[tuple[str, str]] = set()
    for model, param, _labels in SEED.RULE_OPTION_TABLES:
        rows = (await db_session.execute(
            select(model.code, RuleSet.code)
            .join(RuleSet, RuleSet.id == model.rule_set_id)
            .where(
                model.rule_set_id.in_(rule_set_ids),
                (model.sentence_text_zh.is_(None)) | (model.sentence_text_zh == ""),
            )
        )).all()
        keys.update((f"{param}:{code}", rs_code) for code, rs_code in rows)
    return keys


async def test_pending_items_expose_source_is_fallback_matching_blank_zh_sentences(client, db_session):
    """`source_is_fallback` 必須逐列等於「這一列的中文句面是不是空的」。

    前端要靠它事前分辨「英文句面留空」是 D7.6 的刻意不入句（合法）還是把有中文的
    句子標成沒英文（422 `I18N_REVIEW_TARGET_MISSING`）。**不可用「`source_zh` 看起來
    等於 label」反推**——`source_zh` 走 `COALESCE(NULLIF(sentence_text_zh,''), label_zh)`，
    句面剛好等於標籤時那個反推會誤判；這條測試釘的就是「API 回的是服務層算的那個
    布林」。`field='label'` 與主數據（vocab/template）一律 `false`：它們沒有回退鏈。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await _seed_labels(db_session)
    expected_true = await _blank_zh_sentence_keys(db_session)

    r = await client.get("/api/v2/i18n/review/pending")
    assert r.status_code == 200, r.text
    items = r.json()
    assert items, "前提失效：待審清單是空的，這條測試會變成沒斷言到任何事"
    assert all("source_is_fallback" in i for i in items), "API 沒有回 source_is_fallback"

    actual_true = {
        (i["scope_key"], i["rule_set_code"])
        for i in items
        if i["field"] == "sentence" and i["source_is_fallback"]
    }
    returned = {(i["scope_key"], i["rule_set_code"]) for i in items if i["field"] == "sentence"}
    assert actual_true == (expected_true & returned), (
        "source_is_fallback 與 DB 的中文句面空值不一致："
        f"多報 {sorted(actual_true - expected_true)}；少報 {sorted((expected_true & returned) - actual_true)}"
    )
    assert actual_true, "前提失效：清單裡一條中文句面為空的列都沒有（D7.6 那批不在範圍內）"

    assert not [i for i in items if i["field"] != "sentence" and i["source_is_fallback"]], (
        "只有 field='sentence' 才可能是回退來的（label／vocab／template 沒有回退鏈）"
    )


async def test_source_is_fallback_pins_the_d76_codes_on_the_active_rule_set(client, db_session):
    """active 版「刻意不入句」那批＝D7.6 的 7 條——改動時要當場看見（ADR-032 D7.6）。

    上一條測試拿 DB 當對照組，所以字典整批改了它也照樣綠；這條相反，顯式列出目前的
    7 個 code。它紅了不代表壞掉，代表「哪些選項不入敘事句」變了——那是需要有人看一眼
    的核心邏輯改動，不是實作細節。只在 active 版就是認證版（`MINIMOST_FACTORY_V2`）
    時才斷言：其他環境的 active 版可能自訂過選項集合。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    active_code = (await db_session.execute(
        select(RuleSet.code).where(RuleSet.is_active.is_(True))
    )).scalars().first()
    if active_code != CERTIFIED:
        pytest.skip(f"active rule-set 是 {active_code!r}，非認證版——選項集合可能被自訂過")
    await _seed_labels(db_session)

    r = await client.get("/api/v2/i18n/review/pending", params={"entity_type": "rule_option"})
    assert r.status_code == 200, r.text
    active_fallback = {
        i["scope_key"]
        for i in r.json()
        if i["rule_set_code"] == active_code and i["field"] == "sentence" and i["source_is_fallback"]
    }
    assert active_fallback == {
        "b:b_none", "p:a_hard", "p:a_press", "m:m_hand", "m:m_foot", "x:x_none", "i:i_none",
    }, f"active 版「刻意不入句」的選項集合已變動：{sorted(active_fallback)}"


async def test_pending_list_filters_by_entity_type(client, db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await _seed_labels(db_session)
    vocab_count, _template_count = await _vocab_and_template_counts(db_session)

    r = await client.get("/api/v2/i18n/review/pending", params={"entity_type": "vocab_item"})
    assert r.status_code == 200, r.text
    items = r.json()
    assert items and all(i["entity_type"] == "vocab_item" for i in items)
    assert len(items) == vocab_count


async def test_pending_list_filters_by_status(client, db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await _seed_labels(db_session)

    r = await client.get("/api/v2/i18n/review/pending", params={"status": "never_translated"})
    assert r.status_code == 200, r.text
    # 灌值後不應該再有 never_translated（全部至少是 machine/legacy_seed）
    assert r.json() == []


async def test_pending_list_filters_by_status_stays_empty_when_a_draft_exists(client, db_session, draft_rs):
    """S1／S2 迴歸：`never_translated` 空清單這個斷言，在 DB 上有 draft 時也必須
    成立——修好 S1 之前，「側表列存在就跳過填值」的 bug 會讓 active 或 draft
    其中一邊的 `_en` 永遠留 NULL，這裡就會冒出 `never_translated` 項目。

    **M1（2026-08-18 第二輪複審修正）**：先清空 in-scope 的 `label_en`，確保
    `_seed_labels()` 真的有事可做——CI 種子鏈可能已經先跑過灌值腳本，
    `clone_draft` 又會把 `label_en` 一起複製，不清空的話這裡會變成 no-op，
    S1 的 bug 不會顯形。
    """
    await _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session)
    await _seed_labels(db_session)

    r = await client.get("/api/v2/i18n/review/pending", params={"status": "never_translated"})
    assert r.status_code == 200, r.text
    assert r.json() == [], f"draft_rs={draft_rs!r} 存在時，never_translated 清單也必須是空的"


# ══════════════════════════════════════════════════════════════════
# 邊界：非法查詢參數
# ══════════════════════════════════════════════════════════════════

async def test_invalid_entity_type_is_rejected(client):
    r = await client.get("/api/v2/i18n/review/summary", params={"entity_type": "not_a_real_type"})
    assert r.status_code == 422, r.text


async def test_invalid_status_is_rejected(client):
    r = await client.get("/api/v2/i18n/review/pending", params={"status": "not_a_real_status"})
    assert r.status_code == 422, r.text
