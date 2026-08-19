"""`i18n_review_state` 側表 ＋ 灌值腳本 ＋ 待審清單服務（ADR-032 Phase B）。

⚠️ 測試紀律（沿 `test_rule_set_options.py`）：任何寫入一律打 `draft_rs` fixture
clone 出來的拋棄式版本；對 V1/V2 只讀不寫。灌值腳本本身對 active(V2)／draft
兩者都會寫，但這是它的設計行為（D6），透過 `db_session` 的 savepoint 隔離
測試結束即 rollback，不會弄髒真實資料庫。
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from ddm_v2.models.v2.i18n import I18nReviewState
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.nlp.normalization import normalize
from ddm_v2.services.v2 import i18n_service as svc

pytestmark = pytest.mark.integration

CERTIFIED = "MINIMOST_FACTORY_V2"
LEGACY = "MINIMOST_FACTORY_V1"

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_i18n_labels.py"


def _load_seed_module():
    name = "_dev_seed_i18n_labels_integration_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SEED = _load_seed_module()


async def _seeded(db_session, code: str = CERTIFIED) -> bool:
    return (await db_session.execute(
        select(RuleSet.id).where(RuleSet.code == code))).first() is not None


@pytest_asyncio.fixture
async def draft_rs(db_session) -> str:
    """clone 出拋棄式 draft（provenance=cloned）——與 V2 同 code 集合但不同 rule_set_id。"""
    from ddm_v2.services.v2 import rule_set_service as rsvc

    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（DB 資料前置條件不足）")
    code = f"UT_I18N_{uuid.uuid4().hex[:8]}"
    await rsvc.clone_draft(db_session, CERTIFIED, code, "i18n 灌值測試草稿")
    await db_session.commit()
    return code


async def _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session) -> None:
    """M1（2026-08-18 第二輪複審修正）：讓 S1 迴歸測試不受 CI 種子鏈狀態影響。

    複審實測：CI 的種子鏈在 pytest 之前就已經對真實 active 版跑過
    `dev_seed_i18n_labels.py`（`label_en` 已經全部有值）；`draft_rs` fixture
    clone 出的草稿又因為 `_insert_children` 連 `label_en` 一起複製，天生也是滿的。
    在這個前提下呼叫 `seed_i18n_labels()` 對 `_en` 欄位完全無事可做——不管
    S1 的修復存不存在，測試都是綠的，S1 的 bug 不會顯形。

    這裡刻意**只清 `label_en` 本身，不動側表** `i18n_review_state`——S1 bug 的
    觸發條件正是「側表列已經存在、`_en` 卻還沒填」（不論側表列是這個 savepoint
    裡新建的，還是 CI 種子鏈早就建好的殘留），把側表也清空反而測不到這個條件。
    """
    rule_set_ids = (await db_session.execute(
        select(RuleSet.id).where((RuleSet.status == "draft") | (RuleSet.is_active.is_(True)))
    )).scalars().all()
    for model, _param, _labels in SEED.RULE_OPTION_TABLES:
        await db_session.execute(update(model).where(model.rule_set_id.in_(rule_set_ids)).values(label_en=None))
    await db_session.flush()


# ══════════════════════════════════════════════════════════════════
# DB CHECK 不變式
# ══════════════════════════════════════════════════════════════════

async def test_reviewed_by_required_for_human_source_is_enforced(db_session):
    """D5：`source='human'` 時 `reviewed_by` 必填，由 DB CHECK 守（不是 application 層）。"""
    with pytest.raises(IntegrityError):
        db_session.add(I18nReviewState(
            id=uuid.uuid4(), entity_type="rule_option", scope_key="g:ut_probe",
            field="label", locale="en", source="human",
            source_sha256="0" * 64, translated_by=None, reviewed_by=None,
        ))
        await db_session.flush()
    await db_session.rollback()


async def test_human_source_with_reviewed_by_is_accepted(db_session):
    db_session.add(I18nReviewState(
        id=uuid.uuid4(), entity_type="rule_option", scope_key="g:ut_probe_ok",
        field="label", locale="en", source="human",
        source_sha256="0" * 64, translated_by="IEC141289", reviewed_by="IEC141289",
    ))
    await db_session.flush()  # 不拋例外即通過


async def test_entity_type_field_locale_source_check_constraints(db_session):
    """四個列舉 CHECK 各自獨立擋非法值。"""
    bad_rows = [
        dict(entity_type="not_a_type", scope_key="x", field="label", locale="en", source="machine"),
        dict(entity_type="rule_option", scope_key="x", field="not_a_field", locale="en", source="machine"),
        dict(entity_type="rule_option", scope_key="x", field="label", locale="fr", source="machine"),
        dict(entity_type="rule_option", scope_key="x", field="label", locale="en", source="not_a_source"),
    ]
    for kwargs in bad_rows:
        with pytest.raises(IntegrityError):
            db_session.add(I18nReviewState(
                id=uuid.uuid4(), source_sha256="0" * 64, translated_by="t", **kwargs,
            ))
            await db_session.flush()
        await db_session.rollback()


async def test_unique_constraint_on_entity_scope_field_locale(db_session):
    key = dict(entity_type="rule_option", scope_key=f"g:ut_dup_{uuid.uuid4().hex[:6]}", field="label", locale="en")
    db_session.add(I18nReviewState(id=uuid.uuid4(), source="machine", source_sha256="0" * 64, translated_by="t", **key))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(I18nReviewState(id=uuid.uuid4(), source="machine", source_sha256="1" * 64, translated_by="t2", **key))
        await db_session.flush()
    await db_session.rollback()


# ══════════════════════════════════════════════════════════════════
# 讀寫原語
# ══════════════════════════════════════════════════════════════════

async def test_get_review_state_returns_none_when_absent(db_session):
    assert await svc.get_review_state(db_session, "rule_option", "g:does_not_exist", "label") is None


async def test_upsert_review_state_is_get_or_create(db_session):
    """`scope_key` 必須是一個真的 rule_option（`upsert_review_state` 唯一保留的
    寫入前檢查是「entity 是否存在」——合成的、查無此 code 的 scope_key 一律被
    `UnknownReviewScopeKey` 擋下，見 `test_upsert_review_state_rejects_unknown_
    scope_key`）。這裡不做內容驗證，`source_text` 只是如實記錄。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    scope_key = "g:g_grasp"
    label_zh = (await db_session.execute(text(
        "SELECT t.label_zh FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :code AND t.code = 'g_grasp'"
    ), {"code": CERTIFIED})).scalar_one()

    row1 = await svc.upsert_review_state(
        db_session, entity_type="rule_option", scope_key=scope_key, field="label",
        source="machine", source_text=label_zh, translated_by="machine:v1",
    )
    assert row1.source == "machine"
    row2 = await svc.upsert_review_state(
        db_session, entity_type="rule_option", scope_key=scope_key, field="label",
        source="human", source_text=label_zh, translated_by="IEC141289",
        reviewed_by="IEC141289",
    )
    assert row2.id == row1.id, "同鍵覆寫必須是同一列（UNIQUE get-or-create），不是新增第二列"
    assert row2.source == "human" and row2.reviewed_by == "IEC141289"

    count = (await db_session.execute(
        select(I18nReviewState).where(
            I18nReviewState.entity_type == "rule_option",
            I18nReviewState.scope_key == scope_key,
            I18nReviewState.field == "label",
        )
    )).scalars().all()
    assert len(count) == 1


async def test_norm_sha256_matches_gold_review_convention(db_session):
    """`norm_sha256` 必須就是 `normalize()` 後取 sha256——不是另一套正規化。"""
    import hashlib

    raw = "並對準(正常視線範圍到點)"
    assert svc.norm_sha256(raw) == hashlib.sha256(normalize(raw).encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════
# 第四輪（2026-08-18）：拆除寫入前比對防線後的正確性驗證
# ══════════════════════════════════════════════════════════════════
#
# 三輪複審後拆除了 `_authoritative_zh_text`／`SourceTextStale` 這道寫入前逐字
# 比對防線（見 `i18n_service.upsert_review_state` 檔頭）——它是過去兩輪每一個
# 阻擋級複審問題的唯一來源。以下不再測「寫入時因為文字不符而被拒」（那個行為
# 已經不存在），改成一條端對端測試，直接證明拆掉比對防線後，它原本想擋的問題
# 依然被擋住，只是換成讀取端 `_classify` 的 sha256 過期偵測來擋。


async def test_write_side_no_longer_checks_content_but_read_side_still_catches_stale_review(
    db_session, draft_rs
):
    """核心驗收（第四輪）：拆掉 `upsert_review_state` 的寫入前內容比對後，
    「拿 draft 改過的中文去登記覆核，污染 active 顯示狀態」這個問題依然被擋
    住——只是擋的位置從寫入端搬到讀取端。取代第一輪 security review 加的
    「寫入時拒絕」測試，驗證同一個安全屬性，但用讀取端機制達成。

    步驟：
    1. `draft_rs`（fixture）clone 出一個與 active 共用 `g_grasp` code 的草稿。
    2. 把 draft 的 `g_grasp` 中文改掉（模擬「IE 正在編輯草稿」）。
    3. 對這個 scope_key（`g:g_grasp`，D5：scope_key 不含 rule_set_id，
       active／draft 共用同一筆覆核狀態）呼叫 `upsert_review_state`，
       `source_text` 帶 draft 剛改過的中文、`source='human'`——**這次呼叫必須
       成功**（不再有內容比對，如實記錄呼叫端聲明的文字）。
    4. 查 active 版該 code 的候選列狀態（`list_translatable_rows`）——
       **必須不是「已覆核」（`status is not None`）**：active 的現行中文從未
       變過，跟剛才記錄的 `source_sha256`（draft 改過的中文的 sha）對不上，
       `_classify` 判成 `stale`。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session)  # M1：不受 CI 種子鏈狀態影響
    await SEED.seed_i18n_labels(db_session)  # 先讓 active／draft 的 g_grasp 都有 _en，才顯得出 stale
    await db_session.flush()

    active_label_zh_before = (await db_session.execute(text(
        "SELECT t.label_zh FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :code AND t.code = 'g_grasp'"
    ), {"code": CERTIFIED})).scalar_one()

    # 步驟 1：改掉 draft 的中文（active 完全不受影響——底下會驗證這件事）。
    await opsvc.update_option(db_session, draft_rs, "G", None, "g_grasp", {"label_zh": "改握测试-第四輪"})
    await db_session.flush()

    draft_label_zh_after = (await db_session.execute(text(
        "SELECT t.label_zh FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :code AND t.code = 'g_grasp'"
    ), {"code": draft_rs})).scalar_one()
    assert draft_label_zh_after == "改握测试-第四輪"

    # 步驟 2／3：拿 draft 改過的中文登記「human 已覆核」——這次呼叫必須成功
    # （拆掉比對防線前，這裡會是 `SourceTextStale`；現在如實記錄）。
    row = await svc.upsert_review_state(
        db_session, entity_type="rule_option", scope_key="g:g_grasp", field="label",
        source="human", source_text=draft_label_zh_after,
        translated_by="IEC141289", reviewed_by="IEC141289",
    )
    assert row.source == "human"
    assert row.source_sha256 == svc.norm_sha256(draft_label_zh_after)

    # active 的中文本身完全沒被動過——`upsert_review_state` 只寫側表，不寫回
    # 任何一張選項表——重新查一次確認前置假設沒有被意外破壞。
    active_label_zh_after = (await db_session.execute(text(
        "SELECT t.label_zh FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :code AND t.code = 'g_grasp'"
    ), {"code": CERTIFIED})).scalar_one()
    assert active_label_zh_after == active_label_zh_before

    # 步驟 4：核心斷言——active 版該 code 的狀態絕對不是「已覆核」。
    rows = await svc.list_translatable_rows(db_session, entity_type="rule_option")
    active_row = next(r for r in rows if r.rule_set_code == CERTIFIED and r.scope_key == "g:g_grasp")
    draft_row = next(r for r in rows if r.rule_set_code == draft_rs and r.scope_key == "g:g_grasp")

    assert active_row.status is not None, (
        "active 版 g_grasp 不應該被剛才那次覆核標成「已覆核」——覆核記錄的中文是 "
        "draft 改過的字，跟 active 現行的中文對不上"
    )
    assert active_row.status in svc.PENDING_STATUSES
    assert active_row.status == "stale", (
        "active 現行中文從未變過，卻跟剛記錄的 source_sha256（draft 改過的中文）對不上，"
        "_classify 應判為 stale——這正是拆掉寫入前比對後，讀取端接手擋住問題的機制"
    )

    # 對照：draft 自己這次確實是被正確覆核（覆核記錄的中文＝draft 現行的中文）。
    assert draft_row.status is None, "draft 自己的覆核是名符其實的——記錄的中文就是 draft 現行的中文"


async def test_upsert_review_state_rejects_unknown_scope_key(db_session):
    """唯一保留的寫入前檢查（見 `i18n_service.UnknownReviewScopeKey` 檔頭）：
    `scope_key` 完全不指向任何存在的 entity（不限 active，任一 rule-set 版本
    皆可）時，fail-closed 拒絕——不是「反正查不到就放行」。這與拆除的內容比對
    防線是不同的檢查：前者問「這個覆核對象存在嗎」，後者問「內容跟某個版本
    比不比對得起來」（已拆除，見模組頂端小節說明）。
    """
    with pytest.raises(svc.UnknownReviewScopeKey) as exc_info:
        await svc.upsert_review_state(
            db_session, entity_type="rule_option", scope_key="g:ut_does_not_exist_anywhere",
            field="label", source="machine", source_text="隨便", translated_by="t",
        )
    assert exc_info.value.detail.get("code") == "I18N_UNKNOWN_SCOPE_KEY"


async def test_upsert_review_state_accepts_code_that_exists_only_in_a_draft(db_session, draft_rs):
    """存在性檢查跨所有 rule-set 版本，不限 active（見
    `i18n_service.UnknownReviewScopeKey` 檔頭）：D4 允許 IE 在 draft 新增
    active 沒有的選項，這種列覆核起來完全合法——拆除前需要呼叫端額外聲明
    `rule_set_id` 才放行（B1，第二輪複審修正）；拆除後這是預設行為，
    不再是需要特別參數才能觸發的特例。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    code = f"ut_new_code_only_in_draft_{uuid.uuid4().hex[:6]}"
    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": code, "label_zh": "測試僅存在於草稿的新選項", "base_tmu": 3}, actor="UT",
    )
    await db_session.flush()

    row = await svc.upsert_review_state(
        db_session, entity_type="rule_option", scope_key=f"g:{code}", field="label",
        source="machine", source_text="測試僅存在於草稿的新選項", translated_by="t",
    )
    assert row.source == "machine"
    assert row.source_sha256 == svc.norm_sha256("測試僅存在於草稿的新選項")


async def test_upsert_review_state_no_longer_requires_an_active_rule_set(db_session):
    """第四輪簡化的副作用（值得留一條回歸測試）：存在性檢查不再呼叫
    `rule_set_service.get_active_rule_set()`，所以系統沒有 active rule-set 時
    `upsert_review_state` 不再連帶失敗——拆除前這種情況會拋 `NoActiveRuleSet`
    （500），即使呼叫端只是想覆核一個仍然存在（只是不在 active 版）的 code。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")

    await db_session.execute(update(RuleSet).where(RuleSet.is_active.is_(True)).values(is_active=False))
    await db_session.flush()

    row = await svc.upsert_review_state(
        db_session, entity_type="rule_option", scope_key="g:g_grasp", field="label",
        source="machine", source_text="抓握", translated_by="t",
    )
    assert row.source == "machine"


async def test_seed_succeeds_when_draft_adds_a_code_absent_from_active(db_session, draft_rs, monkeypatch):
    """B1／S1 複現流程：draft 新增一個 active 沒有的選項（D4 允許），跑灌值腳本
    **不得整批炸掉**。第二輪複審時這裡曾經是 `try/except SourceTextStale` 才能
    通過的路徑；第四輪拆除寫入前比對防線後，這個情境天生就不會撞到任何寫入
    例外（`_scope_key_exists` 不限定 active），這條測試現在單純確認這條路徑
    確實更順暢——不再有 `SourceTextStale` 這個中止點。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    code = f"ut_b1_seed_new_code_{uuid.uuid4().hex[:6]}"
    monkeypatch.setitem(SEED.G_LABELS, code, "Probe grab (B1 new code)")
    # Phase C 起，一個 option code 有**兩個**可譯欄（label_en／sentence_text_en），
    # 兩張翻譯表都要有它才不會被記進 `missing`——本測試守的是「不得整批炸掉」，
    # 不是「只有標籤需要翻譯」。
    monkeypatch.setitem(SEED.G_SENTENCES, code, "probe-grab")

    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": code, "label_zh": "測試 B1 灌值新選項", "base_tmu": 3}, actor="UT",
    )
    await db_session.flush()

    stats = await SEED.seed_i18n_labels(db_session)  # 不得炸掉——這是 B1/S1 複現流程的核心斷言
    await db_session.flush()

    assert not any(code in m for m in stats.missing), stats.missing

    draft_label_en = (await db_session.execute(text(
        "SELECT t.label_en FROM rule_g_actions t JOIN rule_sets rs ON rs.id=t.rule_set_id "
        "WHERE rs.code=:code AND t.code=:opt_code"
    ), {"code": draft_rs, "opt_code": code})).scalar_one()
    assert draft_label_en == "Probe grab (B1 new code)"

    review = await svc.get_review_state(db_session, "rule_option", f"g:{code}", "label")
    assert review is not None and review.source == "machine"

    # active 63 條選項照常全部填值，不因為 draft 多一個新 code 而整批牽連留
    # NULL（S1 修復前的失敗畫面；重演見 §6 worklog）。
    active_rows = (await db_session.execute(text(
        "SELECT t.code, t.label_en FROM rule_g_actions t JOIN rule_sets rs ON rs.id=t.rule_set_id "
        "WHERE rs.code=:code"
    ), {"code": CERTIFIED})).all()
    assert active_rows, "V2 的 rule_g_actions 應該有列"
    for c, en in active_rows:
        assert en is not None, f"active {c} 因為 draft 新增選項而被牽連留 NULL（B1/S1 回歸）"


# ══════════════════════════════════════════════════════════════════
# 灌值腳本：範圍、冪等、legacy_seed、fail-loud
# ══════════════════════════════════════════════════════════════════

async def test_seed_fills_active_rule_set_labels_and_side_table_atomically(db_session):
    """D6：`label_en` 與 `sentence_text_en` **兩條**寫入路徑都填值，且與側表同交易寫入。

    **先清空再灌**（arrange）：真實 DB 早就被灌過並 commit 了，不清空的話「灌值有沒有
    成功」這件事根本沒被執行到——把腳本的句面寫入路徑整段停掉（`if False and ...`），
    這條測試在清空之前照樣全綠（2026-08-19 突變實測 24 passed）。清空範圍限 V2 的
    `rule_g_actions` 兩個 `_en` 欄位＋它對應的側表列，全都在 `db_session` 的 savepoint
    內，測試結束即 rollback（同本檔既有的「灌值腳本會寫 active，但被隔離」紀律）。

    句面（`field='sentence'`）是 Phase C 新增的第二條寫入路徑，必須**無條件**斷言：
    它一旦靜默 no-op，`sentence_text_en` 全 NULL →
    `test_narrative_en_endpoints.py` 那條「英文敘事不得殘留中文」的 skip 條件成立 →
    唯一能發現「素材沒灌成功」的測試把自己關掉，整批綠。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")

    await db_session.execute(text(
        "UPDATE rule_g_actions t SET label_en = NULL, sentence_text_en = NULL "
        "FROM rule_sets rs WHERE rs.id = t.rule_set_id AND rs.code = :code"
    ), {"code": CERTIFIED})
    await db_session.execute(text(
        "DELETE FROM i18n_review_state WHERE entity_type = 'rule_option' "
        "AND scope_key LIKE 'g:%' AND field IN ('label', 'sentence')"
    ))
    await db_session.flush()

    stats = await SEED.seed_i18n_labels(db_session)
    await db_session.flush()
    assert not [m for m in stats.missing if "rule_g_actions" in m], stats.missing

    rows = (await db_session.execute(text(
        "SELECT t.code, t.label_en, t.sentence_text_en FROM rule_g_actions t "
        "JOIN rule_sets rs ON rs.id=t.rule_set_id WHERE rs.code = :code"
    ), {"code": CERTIFIED})).all()
    assert rows, "V2 的 rule_g_actions 應該有列"
    for code, label_en, sentence_en in rows:
        assert label_en is not None, f"{code} 灌值後 label_en 仍是 NULL"
        assert sentence_en is not None, (
            f"{code} 灌值後 sentence_text_en 仍是 NULL——Phase C 的句面寫入路徑沒跑")
        for field_name in ("label", "sentence"):
            review = await svc.get_review_state(db_session, "rule_option", f"g:{code}", field_name)
            assert review is not None, (
                f"{code} 的 {field_name} 有 _en 值但查無側表列——違反同交易原子性")
            assert review.source == "machine", (
                f"{code}/{field_name} 由本次灌值新建，來源應為 machine：{review.source}")


async def test_seed_is_idempotent(db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    stats1 = await SEED.seed_i18n_labels(db_session)
    await db_session.flush()
    stats2 = await SEED.seed_i18n_labels(db_session)
    assert stats2.filled == 0
    assert stats2.legacy_seed == 0
    assert stats2.skipped == stats1.filled + stats1.legacy_seed + stats1.skipped


async def test_seed_does_not_touch_published_non_active_rule_set(db_session):
    """D6 範圍排除 published(非 active)：V1 的 `label_en` **與** `sentence_text_en` 都維持 NULL。

    兩欄都要查：`sentence_text_en` 是 Phase C 新增的第二條寫入路徑，只查 `label_en`
    的話「句面灌值誤把 published 非 active 也掃進去」這種越界完全沒人看守。
    """
    if not await _seeded(db_session, LEGACY):
        pytest.skip("V1 未種")
    rs = (await db_session.execute(select(RuleSet).where(RuleSet.code == LEGACY))).scalar_one()
    assert rs.status == "published" and not rs.is_active, "前置條件：V1 必須是 published 非 active"

    await SEED.seed_i18n_labels(db_session)
    await db_session.flush()

    count_filled = (await db_session.execute(text(
        "SELECT count(*) FROM rule_g_actions t JOIN rule_sets rs ON rs.id=t.rule_set_id "
        "WHERE rs.code = :code AND (t.label_en IS NOT NULL OR t.sentence_text_en IS NOT NULL)"
    ), {"code": LEGACY})).scalar_one()
    assert count_filled == 0, "V1（published 非 active）不應被灌值——超出 D6 範圍"


async def test_seed_registers_legacy_seed_without_overwriting_existing_value(db_session):
    """motion_templates 既有 16 筆：`name_en` 原樣保留，只補一筆 legacy_seed 側表列。"""
    from ddm_v2.models.v2.motion_template import MotionTemplate

    rows = (await db_session.execute(
        select(MotionTemplate).where(MotionTemplate.name_en.is_not(None))
    )).scalars().all()
    if not rows:
        pytest.skip("motion_templates 未種（缺 dev_seed_templates.py 的資料）")
    before = {str(r.id): r.name_en for r in rows}

    await SEED.seed_i18n_labels(db_session)
    await db_session.flush()

    for row_id, name_en_before in before.items():
        row = await db_session.get(MotionTemplate, uuid.UUID(row_id))
        assert row.name_en == name_en_before, f"{row_id} 的既有 name_en 被覆寫了"
        review = await svc.get_review_state(db_session, "motion_template", row_id, "name")
        assert review is not None and review.source == "legacy_seed"


async def test_scope_key_is_shared_across_rule_set_versions(db_session, draft_rs):
    """D5 的設計重點：scope_key 不含 rule_set_id——同一 code 在 V2 與 draft 共用
    同一筆覆核狀態，不會因為 clone 出新版本而重複灌值或撞 UNIQUE。

    **S1 覆審修正後的重點**：`draft_rs` fixture 在本測試呼叫第一次
    `seed_i18n_labels` **之前**就已經 clone 完成——換句話說，clone 當下 V2
    尚未被本測試灌值過（`draft_rs` 只讀不寫 V2，見檔頭紀律），draft 的
    `label_en` 在 clone 那一刻很可能仍是 NULL。這正是覆審 S1 抓到的紅燈情境：
    修法前，若掃描順序先碰到 draft、後碰到 active，active 反而會被誤判「已有
    側表列」而永遠留白。本測試因此是 S1 的迴歸測試之一——不論 CI 這台 DB
    先前有沒有跑過 baseline 種子（label_en 可能已經有值、也可能沒有），
    第一次 `seed_i18n_labels()` 呼叫都必須讓 V2 與 draft **兩邊**的
    `g:g_grasp` 都拿到值，第二次呼叫則兩邊都不再有新動作
    （`stats.filled == 0`、`stats.legacy_seed == 0`）。
    """
    # M1（2026-08-18 第二輪複審修正）：不管 CI 種子鏈有沒有先跑過（active／draft
    # 的 label_en 可能早就是滿的），這裡先清空，確保下面第一次
    # seed_i18n_labels() 真的有事可做——否則 S1 的 bug（側表列存在就跳過 `_en`
    # 填值）不會顯形，「乾淨形狀」與「CI 形狀」兩種 DB 都必須靠這行才能可靠地
    # 抓到迴歸。
    await _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session)

    await SEED.seed_i18n_labels(db_session)  # 第一次：不論掃描順序，V2 與 draft 都應該被灌好
    await db_session.flush()

    stats = await SEED.seed_i18n_labels(db_session)  # 第二次：兩邊都已有值 + 側表列，應該全部 skip
    await db_session.flush()

    assert stats.filled == 0
    assert stats.legacy_seed == 0

    draft_grasp = (await db_session.execute(text(
        "SELECT t.label_en FROM rule_g_actions t JOIN rule_sets rs ON rs.id=t.rule_set_id "
        "WHERE rs.code = :code AND t.code = 'g_grasp'"
    ), {"code": draft_rs})).scalar_one()
    assert draft_grasp == SEED.G_LABELS["g_grasp"]

    # S1 的核心斷言：active（V2）自己的 g_grasp 也必須有值，不能因為 draft 先佔走
    # 了側表列就被跳過（這是覆審抓到的紅燈本體——沒有這條斷言，前面的
    # stats.filled==0 單獨看不出 active 到底有沒有值，只看得出「沒有新動作」）。
    v2_grasp = (await db_session.execute(text(
        "SELECT t.label_en FROM rule_g_actions t JOIN rule_sets rs ON rs.id=t.rule_set_id "
        "WHERE rs.code = :code AND t.code = 'g_grasp'"
    ), {"code": CERTIFIED})).scalar_one()
    assert v2_grasp == SEED.G_LABELS["g_grasp"], "active 版 g_grasp 的 label_en 不能是 NULL（S1）"


async def test_stale_status_when_zh_label_changes_after_human_review(db_session, draft_rs):
    """過期偵測（D5/D6）：`stale` 描述的是「曾經被 IE 覆核，之後中文來源又變了」，
    不是「還沒覆核、剛好 sha 對不上」——後者本來就已經是 `unreviewed`（見同檔
    `test_seed_fills_active_rule_set_labels_and_side_table_atomically` 起手的
    machine 狀態，改字面不會把它從 unreviewed 變成 stale，因為它從未脫離待審）。

    情境：先把 `g:g_grasp`（V2 與 draft 目前共用同一份中文「抓握」）標成
    `source='human'` 已覆核 → 兩邊都應該落在「已覆核且未過期」（status is None）；
    接著只改 draft 的 `label_zh` → **只有 draft** 那一列的 sha 對不上而變 stale，
    V2 本身（zh 未變）仍是已覆核狀態，不受波及——這正是 scope_key 不含
    rule_set_id 的設計取捨要付的代價（D5 明文承認）。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session)  # M1
    await SEED.seed_i18n_labels(db_session)
    await db_session.flush()

    active_label_zh = (await db_session.execute(text(
        "SELECT t.label_zh FROM rule_g_actions t JOIN rule_sets rs ON rs.id = t.rule_set_id "
        "WHERE rs.code = :code AND t.code = 'g_grasp'"
    ), {"code": CERTIFIED})).scalar_one()
    await svc.upsert_review_state(
        db_session, entity_type="rule_option", scope_key="g:g_grasp", field="label",
        source="human", source_text=active_label_zh, translated_by="IEC141289", reviewed_by="IEC141289",
    )
    await db_session.flush()

    rows = await svc.list_translatable_rows(db_session, entity_type="rule_option")
    draft_row = next(r for r in rows if r.rule_set_code == draft_rs and r.scope_key == "g:g_grasp")
    v2_row = next(r for r in rows if r.rule_set_code == CERTIFIED and r.scope_key == "g:g_grasp")
    assert draft_row.status is None, "覆核後、zh 未變，尚不應在待審清單裡"
    assert v2_row.status is None

    await opsvc.update_option(db_session, draft_rs, "G", None, "g_grasp", {"label_zh": "改握测试"})
    await db_session.flush()

    rows = await svc.list_translatable_rows(db_session, entity_type="rule_option")
    draft_row = next(r for r in rows if r.rule_set_code == draft_rs and r.scope_key == "g:g_grasp")
    v2_row = next(r for r in rows if r.rule_set_code == CERTIFIED and r.scope_key == "g:g_grasp")

    assert draft_row.status == "stale", draft_row
    assert v2_row.status is None, v2_row  # V2 的 zh 未變，未被波及


async def test_source_changed_distinguishes_fresh_machine_translation_from_stale_one(db_session, draft_rs):
    """S6：`status='unreviewed'` 本身分不出「剛翻好、zh 沒變過」跟「翻過，但 zh
    後來又改了、它還沒被人看過」——兩者都回報 `unreviewed`（`_classify` 的優先序，
    見該函式檔頭），但對覆核者的意義不同。`source_changed` 把這個差異獨立標出來，
    不靠改 `status` 本身。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session)  # M1
    await SEED.seed_i18n_labels(db_session)  # g:g_grasp 現在兩邊都是 machine／unreviewed
    await db_session.flush()

    rows = await svc.list_translatable_rows(db_session, entity_type="rule_option")
    draft_row = next(r for r in rows if r.rule_set_code == draft_rs and r.scope_key == "g:g_grasp")
    v2_row = next(r for r in rows if r.rule_set_code == CERTIFIED and r.scope_key == "g:g_grasp")
    assert draft_row.status == "unreviewed" and draft_row.source_changed is False, (
        "剛灌值、zh 沒變過：unreviewed 但 source_changed 應為 False"
    )
    assert v2_row.status == "unreviewed" and v2_row.source_changed is False

    # 只改 draft 的 zh——這條翻譯從未被人覆核過（source 仍是 machine），
    # 所以照優先序仍歸 unreviewed，不是 stale（那是給「曾經被人覆核過」的）。
    await opsvc.update_option(db_session, draft_rs, "G", None, "g_grasp", {"label_zh": "改握测试二"})
    await db_session.flush()

    rows = await svc.list_translatable_rows(db_session, entity_type="rule_option")
    draft_row = next(r for r in rows if r.rule_set_code == draft_rs and r.scope_key == "g:g_grasp")
    v2_row = next(r for r in rows if r.rule_set_code == CERTIFIED and r.scope_key == "g:g_grasp")

    assert draft_row.status == "unreviewed", draft_row  # 分類不變……
    assert draft_row.source_changed is True, "……但 source_changed 必須標出來源已經變了（S6）"
    assert v2_row.status == "unreviewed" and v2_row.source_changed is False, "V2 的 zh 未變，不受影響"


async def test_translation_missing_fails_loud_for_unknown_option_code(db_session, draft_rs):
    """fail-loud（ADR-032：不得靜默略過缺翻譯的選項）——但「fail-loud」不等於
    「當場中止整條 seed」（S3 覆審修正）：缺漏被收集進 `stats.missing`，讓其餘
    表／rule-set 版本照常掃完；`raise_if_missing()` 才是真正拋例外、以非 0
    結束的那一步（`main()` 在那之前已經 `commit()` 過，見腳本檔頭）。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": "ut_unknown_g_probe", "label_zh": "測試未知動作", "base_tmu": 3},
        actor="UT",
    )
    await db_session.flush()

    stats = SEED.SeedStats()
    await SEED.seed_rule_options(db_session, stats)  # 不再中途炸

    assert any("ut_unknown_g_probe" in m for m in stats.missing)
    # 其餘正常的選項（active 全部 63 條）仍然照常被填值，不受這一條缺漏拖累。
    assert stats.filled > 0 or stats.skipped > 0 or stats.legacy_seed > 0

    with pytest.raises(SEED.TranslationMissing) as exc_info:
        SEED.raise_if_missing(stats)
    assert "ut_unknown_g_probe" in str(exc_info.value)


# ══════════════════════════════════════════════════════════════════
# I5：正式資料的唯一性驗證（互補 unit 測試的靜態字典檢查）
# ══════════════════════════════════════════════════════════════════

async def test_english_labels_are_unique_within_each_rule_set_table(db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await SEED.seed_i18n_labels(db_session)
    await db_session.flush()

    tables = [m.__tablename__ for m, _p, _l in SEED.RULE_OPTION_TABLES]
    for table in set(tables):
        rows = (await db_session.execute(text(
            f"SELECT rule_set_id, code, label_en FROM {table} WHERE label_en IS NOT NULL"  # noqa: S608
        ))).all()
        by_rs: dict[uuid.UUID, list[tuple[str, str]]] = {}
        for rs_id, code, label_en in rows:
            by_rs.setdefault(rs_id, []).append((code, label_en))
        for rs_id, items in by_rs.items():
            normed: dict[str, list[str]] = {}
            for code, label_en in items:
                normed.setdefault(normalize(label_en), []).append(code)
            dupes = {k: v for k, v in normed.items() if len(v) > 1}
            assert not dupes, f"{table} rule_set={rs_id} 有英文標籤衝突：{dupes}"


# ══════════════════════════════════════════════════════════════════
# 待審清單服務（供 API 層覆用）
# ══════════════════════════════════════════════════════════════════

async def _in_scope_rule_set_ids(db_session) -> list[uuid.UUID]:
    """`i18n_service.IN_SCOPE_RULE_SET_SQL` 的 Python 版（active ＋ 現存 draft）。"""
    return (await db_session.execute(
        select(RuleSet.id).where((RuleSet.status == "draft") | (RuleSet.is_active.is_(True)))
    )).scalars().all()


async def _rule_option_distinct_scope_key_count(db_session) -> int:
    """`summary()` 的分母：DISTINCT `(param, code)`——**不硬編 63**（S2）：
    有 draft 時 63 這個常數不再保證成立，只有直接查 DB 現況才準。
    """
    rule_set_ids = await _in_scope_rule_set_ids(db_session)
    scope_keys: set[str] = set()
    for model, param, _labels in SEED.RULE_OPTION_TABLES:
        codes = (await db_session.execute(
            select(model.code).where(model.rule_set_id.in_(rule_set_ids))
        )).scalars().all()
        scope_keys.update(f"{param}:{c}" for c in codes)
    return len(scope_keys)


async def _rule_option_row_count(db_session) -> int:
    """`pending_rows()` 的候選列數（不去重，見 `pending_rows` 檔頭）。"""
    rule_set_ids = await _in_scope_rule_set_ids(db_session)
    total = 0
    for model, _param, _labels in SEED.RULE_OPTION_TABLES:
        total += (await db_session.execute(
            select(func.count()).select_from(model).where(model.rule_set_id.in_(rule_set_ids))
        )).scalar_one()
    return int(total)


async def test_summary_and_pending_rows_reflect_seeded_state(db_session):
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    await SEED.seed_i18n_labels(db_session)
    await db_session.flush()

    expected_distinct = await _rule_option_distinct_scope_key_count(db_session)
    expected_rows = await _rule_option_row_count(db_session)

    summary = await svc.summary(db_session, entity_type="rule_option")
    assert summary["total"] == expected_distinct
    assert summary["reviewed"] == 0
    assert summary["pending"] == expected_distinct

    pending = await svc.pending_rows(db_session, entity_type="rule_option", status="unreviewed")
    assert len(pending) == expected_rows
    assert {r.review_source for r in pending} <= {"machine", "legacy_seed"}


async def test_summary_and_pending_rows_reflect_seeded_state_with_draft_present(db_session, draft_rs):
    """S2 迴歸：上一條測試在「沒有 draft」時就已經動態查詢，這裡明確造出
    「有 draft」的情境，證明 `summary()`（DISTINCT，總數不變）與
    `pending_rows()`（不去重，總數隨版本數增加）在有 draft 時的行為都符合設計，
    不是巧合地綠。
    """
    await _reset_rule_option_en_labels_for_in_scope_rule_sets(db_session)  # M1
    await SEED.seed_i18n_labels(db_session)
    await db_session.flush()

    expected_distinct = await _rule_option_distinct_scope_key_count(db_session)
    expected_rows = await _rule_option_row_count(db_session)
    assert expected_rows == 2 * expected_distinct, (
        f"draft_rs={draft_rs!r} 與 active 共用完全相同的 code 集合，"
        "候選列數理應剛好是相異 scope_key 數的兩倍"
    )

    summary = await svc.summary(db_session, entity_type="rule_option")
    assert summary["total"] == expected_distinct, "summary 不應該因為多了一個 draft 而把分母翻倍（S2）"
    assert summary["pending"] == expected_distinct

    pending = await svc.pending_rows(db_session, entity_type="rule_option", status="unreviewed")
    assert len(pending) == expected_rows == 2 * expected_distinct


async def test_pending_rows_never_translated_when_en_is_null(db_session, draft_rs):
    """不灌值的情況下，draft 的選項（clone 前 V2 尚未灌值時的假想狀態）——
    這裡改用「clone 一個尚未灌值的 rule-set」不可行（V2 現況已灌），故直接
    構造一列 label_en=NULL 的自訂選項，驗證 never_translated 分支。
    """
    from ddm_v2.services.v2 import rule_option_service as opsvc

    await opsvc.create_option(
        db_session, draft_rs, "G", None,
        {"code": "ut_never_translated_probe", "label_zh": "測試從未翻譯", "base_tmu": 3},
        actor="UT",
    )
    await db_session.flush()

    rows = await svc.list_translatable_rows(db_session, entity_type="rule_option")
    probe = next(r for r in rows if r.rule_set_code == draft_rs and r.scope_key == "g:ut_never_translated_probe")
    assert probe.status == "never_translated"
    assert probe.target_en is None
