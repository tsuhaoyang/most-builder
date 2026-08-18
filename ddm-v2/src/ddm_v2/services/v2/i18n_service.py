"""i18n 覆核狀態服務（ADR-032 D5／D6）。

三件事：
1. `i18n_review_state` 的讀寫原語（`get_review_state` / `upsert_review_state`）
   ——供灌值腳本與（未來的）人工覆核端點共用，是覆核狀態的唯一寫入路徑。
2. 待審清單的三態聯集查詢（D6）——「目標欄位 IS NULL」／「有側表列且
   source ∈ {machine,legacy_seed}」／「有側表列且來源已過期（sha256 不符）」。
3. 覆核正確性的保護機制（D5 原始設計；2026-08-18 第四輪簡化定案，拆除寫入前
   逐字比對防線）——完全依賴上面第 2 點「讀取時的 sha256 過期偵測」：
   `upsert_review_state` 如實記錄呼叫端聲明的 `source_text`，不對它的內容做
   任何版本相關的驗證；`scope_key` 不含 `rule_set_id`（D5）代表哪個版本的候選
   列被覆核，是留給 `_classify` 用自己的 sha 比對去判斷，不是留給寫入端猜。
   寫入端唯一保留的檢查是「`scope_key` 指涉的 entity 是否存在」（fail-closed，
   見 `UnknownReviewScopeKey`／`upsert_review_state` 檔頭）——這與「內容是否與
   某版本一致」是不同的檢查：前者問「這個覆核對象存在嗎」，後者曾經是這裡的
   第二道防線（`_authoritative_zh_text`／`SourceTextStale`，已拆除）。拆除理由：
   它想擋的「draft 改過的中文被拿去覆核，污染 active 的顯示狀態」，讀取端的
   sha 比對本來就正確處理了（見
   `test_stale_status_when_zh_label_changes_after_human_review`）；寫入前比對是
   同一個問題的第二個、版本無關、精度更低的答案，而且是過去兩輪每一個阻擋級
   複審問題（B1、L1，以及第三輪複審再抓到的問題）的唯一來源，故直接拆除，
   不是再修一次。

**`_en` 的編輯權＝analyst 以上（D4）：本模組所有函式都不呼叫
`rule_set_service.assert_editable`**——`_en` 標籤／名稱的可變性不受
ADR-023 §3.3 規則 1「draft-only」限制（D4 已修訂該矩陣新增一列：
`_en` 在 draft／published／published+active 皆可寫，僅 retired 終態不可寫）。
這與 `synonym_service._assert_not_retired` 是同一種「繞道」，同一個理由。

**單一查詢，不是三次查詢拼接**：待審清單的候選列（7 張選項表 ＋ 詞彙 ＋ 範本，
UNION ALL）與側表的 LEFT JOIN 在**一次** SQL 往返內完成；三態的分類
（never_translated / unreviewed / stale）留到 Python 端一次 pass 內完成——
理由是 stale 判定需要 `nlp.normalization.normalize()`（含 OpenCC 簡轉繁），
這是 C 擴充套件，SQL 端算不出來，故分類本來就不可能整段下推成 SQL。
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.exceptions import NotFoundError
from ddm_v2.models.v2 import rule_set_tables as rt
from ddm_v2.models.v2.i18n import ENTITY_TYPES, FIELDS, SOURCES, I18nReviewState
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.nlp.normalization import normalize

__all__ = [
    "ENTITY_TYPES",
    "FIELDS",
    "PENDING_STATUSES",
    "SOURCES",
    "TranslatableRow",
    "UnknownReviewScopeKey",
    "get_review_state",
    "list_translatable_rows",
    "norm_sha256",
    "pending_rows",
    "summary",
    "upsert_review_state",
]

PENDING_STATUSES = ("never_translated", "unreviewed", "stale")

# rule_option 的 scope_key 前綴（"{param}:{code}"）→ 可能承載該 code 的 ORM 表。
# 'p' 前綴同時被 rule_p_bases（p_ 開頭 code）與 rule_p_addons（a_ 開頭 code）共用
# （scope_key 設計見 D5／`dev_seed_i18n_labels.py` 檔頭：兩表 code 命名空間不重疊，
# 逐一嘗試即可，不需要另外解析 code 前綴）。
_RULE_OPTION_MODELS_BY_PARAM: dict[str, tuple[type, ...]] = {
    "b": (rt.RuleBOption,),
    "g": (rt.RuleGAction,),
    "p": (rt.RulePBase, rt.RulePAddon),
    "m": (rt.RuleMVerb,),
    "x": (rt.RuleXOption,),
    "i": (rt.RuleIOption,),
}

# `rule_option` 的合法 `field` 值——同時充當「這個 field 對 rule_option 有沒有意義」
# 的判準（`_scope_key_exists` 用它排除例如 field='name' 打在 rule_option 上這種
# 組合本身就不成立的呼叫；不做這件事以外的用途——本輪拆除寫入前內容比對後，
# 不再需要知道對應的中文欄位「名稱」是什麼，只需要知道這個 field 合不合法）。
_RULE_OPTION_FIELDS = frozenset({"label", "sentence"})


class UnknownReviewScopeKey(NotFoundError):
    """`upsert_review_state` 的 `scope_key` 查無對應的 entity（HTTP 404）。

    **`upsert_review_state` 唯一保留的寫入前檢查（2026-08-18 第四輪簡化）**：
    這不是「內容跟某個版本的文字比不比對得起來」——那道比對防線
    （`_authoritative_zh_text`／`SourceTextStale`）已經在本輪拆除，理由見模組
    檔頭。這裡擋的是完全不同的情境：`scope_key` 根本不指向任何存在的 entity
    （例如打錯 code、或引用一個從未建立過的 rule_option／vocab_item／
    motion_template）——覆核一個不存在的對象沒有意義，fail-closed 拒絕。

    **檢查範圍刻意跨所有 rule-set 版本，不限 active**：`rule_option` 的
    `scope_key` 只要在**任一** rule-set 版本（active 或 draft）能找到對應 code
    即視為存在——D4 允許 IE 在 draft 新增 active 沒有的選項，這種列覆核起來
    完全合法，不該因為「active 沒有」就被拒絕。這正是拆掉的那道防線在第二輪
    複審暴露出的 B1 洞的根本原因：把「內容比對」與「存在性檢查」混在同一個
    判斷式裡，前者需要限定 active（因為要跟 active 的現行文字逐字比對），
    後者不需要（只是確認 code 存在過），混在一起就必然顧此失彼；拆開之後，
    存在性檢查天然就不需要「active」這個概念，也就不需要 `rule_set_id` 這個
    參數來局部繞過它。
    """

    def __init__(self, *, entity_type: str, scope_key: str, field: str) -> None:
        super().__init__(
            f"覆核寫入被拒：查無 {entity_type}/{scope_key}/{field} 對應的資料——"
            "這個覆核對象在目前的資料庫裡不存在（不限 active 版，任一 rule-set "
            "版本皆可），請確認 scope_key／field 是否正確。",
            detail={
                "code": "I18N_UNKNOWN_SCOPE_KEY",
                "entity_type": entity_type,
                "scope_key": scope_key,
                "field": field,
            },
        )


async def _scope_key_exists(session: AsyncSession, entity_type: str, scope_key: str, field: str) -> bool:
    """`scope_key` 是否指向一個真的存在的 entity——`upsert_review_state` 唯一保留的
    寫入前檢查（見 `UnknownReviewScopeKey` 檔頭）。**不比對任何版本的中文內容**，
    只確認「這個覆核對象存在」。

    - `rule_option`：`code` 存在於**任一** rule-set 版本（不限 active）。
    - `vocab_item`／`motion_template`：`scope_key`（id）存在於對應主數據表。
    """
    if entity_type == "rule_option":
        param, sep, code = scope_key.partition(":")
        if not sep or field not in _RULE_OPTION_FIELDS:
            return False
        for model in _RULE_OPTION_MODELS_BY_PARAM.get(param, ()):
            # `model` 是 `_RULE_OPTION_MODELS_BY_PARAM`（`tuple[type, ...]`）裡的
            # 元素——七張表沒有共同的 mixin/Protocol 宣告 `id`／`code`，mypy 看不到
            # 這個裸 `type` 上有這兩個屬性。用 `getattr` 取（回傳 `Any`）是既有慣例
            # （`_candidates_sql` 之外，本檔原本的 `_authoritative_zh_text` 對動態
            # 欄位也是同一招），不是繞過型別檢查，是型別檢查本來就到不了這裡。
            id_col = getattr(model, "id")  # noqa: B009
            code_col = getattr(model, "code")  # noqa: B009
            found = (
                await session.execute(select(id_col).where(code_col == code).limit(1))
            ).first()
            if found is not None:
                return True
        return False
    if entity_type in ("vocab_item", "motion_template"):
        try:
            row_id = uuid.UUID(scope_key)
        except ValueError:
            return False
        model = WorkVocabItem if entity_type == "vocab_item" else MotionTemplate
        found = (await session.execute(select(model.id).where(model.id == row_id))).first()
        return found is not None
    return False


def norm_sha256(raw: str) -> str:
    """正規化（`nlp.normalization.normalize`）後取 sha256（十六進位）。

    與 gold review 的 `norm_sha256` 手法同構（`scripts/gold_harvest.py`）——
    沿用同一個正規化函式，不是另外自己發明一套「差不多」的正規化。
    """
    return hashlib.sha256(normalize(raw).encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════
# 覆核狀態的讀寫原語
# ══════════════════════════════════════════════════════════════════


async def get_review_state(
    session: AsyncSession, entity_type: str, scope_key: str, field: str, locale: str = "en"
) -> I18nReviewState | None:
    return (
        await session.execute(
            select(I18nReviewState).where(
                I18nReviewState.entity_type == entity_type,
                I18nReviewState.scope_key == scope_key,
                I18nReviewState.field == field,
                I18nReviewState.locale == locale,
            )
        )
    ).scalar_one_or_none()


async def upsert_review_state(
    session: AsyncSession,
    *,
    entity_type: str,
    scope_key: str,
    field: str,
    source: str,
    source_text: str,
    translated_by: str | None,
    locale: str = "en",
    note: str | None = None,
    reviewed_by: str | None = None,
    reviewed_at: datetime | None = None,
) -> I18nReviewState:
    """建立或覆寫 `(entity_type, scope_key, field, locale)` 的覆核狀態列。

    覆寫語意＝整列以本次呼叫的值為準（last-write-wins）——本表只存「關於譯文
    的事實」，不像 gold set 的 `ruling_history` 需要留完整軌跡（D5：「翻譯的
    更正史價值遠低於 IE 裁決的更正史」）；覆蓋寫入由既有 `workflow_audit_log`
    承接即可（若呼叫端需要稽核，自行在外層加 `log_audit`，本函式不重複做）。

    **`source_text` 如實記錄，不做內容驗證（2026-08-18 第四輪簡化，拆除三輪複審
    問題的唯一來源）**：本函式**不**比對 `source_text` 是否等於某個版本的
    「現行權威中文」——`source_text` 本來就只是「呼叫端這次覆核當下看到的
    中文」，原樣記錄即可，不需要、也不應該由這裡去判斷它「對不對」。正確性
    保護完全交給讀取端（`_classify`）：`scope_key` 不含 `rule_set_id`（D5），
    一個 scope_key 可能被 active 版與所有 draft 版共用，若某一版的現行中文跟
    這次覆核記錄的 `source_sha256` 對不上，`_classify` 會把那一版標成
    `stale`，不會顯示「已覆核」——這條讀取端機制本來就正確處理了「draft 改過
    的中文被拿去覆核，會不會污染 active 的顯示狀態」這個問題（見
    `test_stale_status_when_zh_label_changes_after_human_review`，以及本輪新增
    的端對端測試，證明拆掉寫入前比對之後這個安全屬性依然成立）。舊版在這裡
    另外疊了一層寫入前逐字比對（`_authoritative_zh_text`／`SourceTextStale`），
    是對同一個問題的第二個、版本無關、精度更低的答案——那道防線與它的
    `rule_set_id` 放行參數，是過去兩輪每一個阻擋級複審問題（B1、L1，以及第三
    輪複審再抓到的問題）的唯一來源，第三輪複審後拆除，不再保留。

    **唯一保留的寫入前檢查：`scope_key` 必須指向存在的 entity（fail-closed）**
    ——這不是「內容跟某個版本比對」，是「這個覆核對象根本不存在」，兩者是
    不同的檢查，見 `UnknownReviewScopeKey`。查無時拒絕（404），不靜默建立一筆
    指向虛構對象的覆核狀態。
    """
    if not await _scope_key_exists(session, entity_type, scope_key, field):
        raise UnknownReviewScopeKey(entity_type=entity_type, scope_key=scope_key, field=field)
    existing = await get_review_state(session, entity_type, scope_key, field, locale)
    sha = norm_sha256(source_text)
    now = datetime.now(timezone.utc)
    if existing is None:
        row = I18nReviewState(
            id=uuid.uuid4(),
            entity_type=entity_type,
            scope_key=scope_key,
            field=field,
            locale=locale,
            source=source,
            source_sha256=sha,
            translated_by=translated_by,
            translated_at=now,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            note=note,
        )
        session.add(row)
    else:
        existing.source = source
        existing.source_sha256 = sha
        existing.translated_by = translated_by
        existing.translated_at = now
        existing.reviewed_by = reviewed_by
        existing.reviewed_at = reviewed_at
        existing.note = note
        row = existing
    await session.flush()
    return row


# ══════════════════════════════════════════════════════════════════
# 待審清單（D6）
# ══════════════════════════════════════════════════════════════════

# 7 張選項表 → (表名, scope_key 的參數前綴)。前綴刻意小寫，對齊 ADR-032 D5 的
# 字面範例 `g:g_grasp`（option code 自己也是小寫前綴，兩者一致）。
# P 的 base／addon 兩張物理表共用參數字母 'p'——code 命名空間不重疊
# （p_base 一律 `p_` 開頭、p_addon 一律 `a_` 開頭，實測見 dev_seed_i18n_labels.py
# 檔頭），故不會撞 scope_key。
_RULE_OPTION_SOURCES: tuple[tuple[str, str], ...] = (
    ("rule_b_options", "b"),
    ("rule_g_actions", "g"),
    ("rule_p_bases", "p"),
    ("rule_p_addons", "p"),
    ("rule_m_verbs", "m"),
    ("rule_x_options", "x"),
    ("rule_i_options", "i"),
)

# D6 範圍：active rule-set ＋ 現存 draft。published(非 active)／retired 是凍結
# 的歷史版本，不進待審清單（也不是灌值腳本的灌值範圍——同一個判準，兩處共用
# 這個字面條件，避免「灌了什麼」與「清單顯示什麼」兩處各自維護一份定義而漂移）。
IN_SCOPE_RULE_SET_SQL = "(rs.status = 'draft' OR rs.is_active)"


def _candidates_sql() -> str:
    """組出**單一** SQL 陳述式：9 個來源 UNION ALL，再 LEFT JOIN 覆核側表。

    表／欄名皆為本模組常數（非外部輸入），故用 f-string 組 SQL 是安全的
    （與 `rule_set_service.count_references` 同慣例，noqa: S608）。

    每一列額外帶一欄 `rule_set_is_active`（rule_option 來自 `rs.is_active`；
    vocab/template 無版本概念，一律 `NULL`），**只用來排序，不進最終 SELECT**——
    `summary()` 用「同一個 scope_key 有多列（active ＋ draft 共用）時，優先取
    active 那一列」做 DISTINCT 去重（見 `summary()` 檔頭），排序把 active 排在
    同一 scope_key 的最前面，讓 Python 端「取第一筆」天然等於「取 active」。
    """
    parts = [
        f"""
        SELECT 'rule_option' AS entity_type, '{param}:' || t.code AS scope_key,
               'label' AS field, rs.code AS rule_set_code,
               t.label_zh AS source_zh, t.label_en AS target_en,
               rs.is_active AS rule_set_is_active
        FROM {table} t JOIN rule_sets rs ON rs.id = t.rule_set_id
        WHERE {IN_SCOPE_RULE_SET_SQL}
        """
        for table, param in _RULE_OPTION_SOURCES
    ]
    # 主數據（ADR-024）：詞彙庫／範本庫不分版本，D6 明文「全部」——不因
    # rule-set 的 draft/published/retired 狀態而過濾（它們本來就不掛 rule_set_id）。
    parts.append(
        """
        SELECT 'vocab_item', v.id::text, 'name', NULL,
               v.name_zh, v.name_en, NULL::boolean
        FROM work_vocab_items v
        """
    )
    parts.append(
        """
        SELECT 'motion_template', m.id::text, 'name', NULL,
               m.name_zh, m.name_en, NULL::boolean
        FROM motion_templates m
        """
    )
    candidates = " UNION ALL ".join(parts)
    return f"""
    WITH candidates AS ({candidates})
    SELECT c.entity_type, c.scope_key, c.field, c.rule_set_code, c.source_zh, c.target_en,
           r.source AS review_source, r.source_sha256 AS review_sha256,
           r.translated_by, r.translated_at, r.reviewed_by, r.reviewed_at
    FROM candidates c
    LEFT JOIN i18n_review_state r
      ON r.entity_type = c.entity_type AND r.scope_key = c.scope_key
     AND r.field = c.field AND r.locale = 'en'
    ORDER BY c.entity_type, c.scope_key, c.field,
             c.rule_set_is_active DESC NULLS LAST, c.rule_set_code NULLS LAST
    """  # noqa: S608 - 表/欄名為模組常數，非外部輸入


@dataclass(frozen=True)
class TranslatableRow:
    """一個可譯欄位的現況（候選列 ＋ 分類後的狀態）。

    `status is None` ＝已覆核且未過期（不進待審清單）；否則是
    `PENDING_STATUSES` 三者之一。

    `source_changed`（S6，2026-08-18 覆審修正）：這一列**現行**中文來源的
    sha256 是否與側表記錄的 `review_sha256` 不同——不論 `status` 為何都算得出來
    （沒有側表列時視為 `False`，因為沒有可比較的基準）。存在的理由是
    `status='unreviewed'` 這個值本身**無法區分**兩種情況：(a) 剛翻好、中文
    來源沒變過；(b) 曾經翻過，但中文來源後來又改了，而它本來就還沒被人看過
    （所以優先序上仍歸 `unreviewed` 不是 `stale`，見 `_classify` 檔頭）——兩者
    對覆核者的意義不同（(b) 代表「這批機器翻譯可能已經對不上現在的中文」），
    但 `status` 這個欄位本身看不出差異。`source_changed=True` 把這個區別
    顯式標出來，而不是讓它悄悄消失在 `unreviewed` 這一個值裡。
    """

    entity_type: str
    scope_key: str
    field: str
    rule_set_code: str | None
    source_zh: str
    target_en: str | None
    status: str | None
    source_changed: bool
    review_source: str | None
    translated_by: str | None
    translated_at: datetime | None
    reviewed_by: str | None
    reviewed_at: datetime | None


def _classify(source_zh: str, target_en: str | None, review_source: str | None, review_sha256: str | None) -> str | None:
    """D6 的三態聯集判準（單一函式，避免三處各自寫一次判斷式而漂移）。

    **優先序（`unreviewed` 先於 `stale` 判定）是刻意的，不是巧合**：`stale`
    描述的是「曾經被 IE 覆核（`source='human'`），中文來源之後又變了」——
    D5 原文「中文來源變了，譯文就是過期，**重回**待審清單」的「重回」二字
    意味著它曾經離開過待審清單（＝曾經被覆核）。一列還停在 `machine`／
    `legacy_seed` 時本來就從未離開待審清單，不存在「重回」，所以即使
    `source_sha256` 剛好對不上現行中文（例如灌值後又手動改了中文標籤），
    仍報 `unreviewed`——對使用者更有意義的訊息是「這條還沒人看過」，
    不是「這條過期了」（過期意味著曾經有人確認過、現在需要重新確認）。

    第三支（`target_en` 非 NULL 但查無側表列）理論上不該發生——本模組的寫入
    路徑（`upsert_review_state`）與灌值腳本（`dev_seed_i18n_labels.py`）保證
    「灌值同時寫 `_en` 欄與側表列，兩者同交易」（ADR-032 D6）。若真的出現
    （例如未來有其他路徑繞過本模組直寫 `_en`），不靜默放過——`review_sha256`
    為 None 必然 `!=` 任何 sha256，會落進 `stale` 分支而不是被吃掉。
    """
    if target_en is None:
        return "never_translated"
    if review_source in ("machine", "legacy_seed"):
        return "unreviewed"
    if review_sha256 != norm_sha256(source_zh):
        return "stale"
    return None


def _source_changed(source_zh: str, review_sha256: str | None) -> bool:
    """S6：現行中文來源是否與側表記錄的來源 sha 不同——`status` 分不出這個區別
    （見 `TranslatableRow.source_changed` 檔頭），故獨立算一次。`review_sha256`
    為 `None`（從未翻譯過，沒有側表列）視為 `False`：沒有基準可比較，不能算「變了」。
    """
    if review_sha256 is None:
        return False
    return review_sha256 != norm_sha256(source_zh)


async def list_translatable_rows(
    session: AsyncSession, *, entity_type: str | None = None
) -> list[TranslatableRow]:
    """全部可譯欄位（含已覆核者），已分類。`entity_type` 篩選在 Python 端做

    ——資料量小（現況 63＋59＋16＝138 列），不值得為篩選條件重組 SQL；
    且無論篩不篩，底層都是同一次查詢（見模組檔頭）。
    """
    rows = (await session.execute(text(_candidates_sql()))).mappings().all()
    out: list[TranslatableRow] = []
    for r in rows:
        if entity_type is not None and r["entity_type"] != entity_type:
            continue
        status = _classify(r["source_zh"], r["target_en"], r["review_source"], r["review_sha256"])
        out.append(
            TranslatableRow(
                entity_type=r["entity_type"],
                scope_key=r["scope_key"],
                field=r["field"],
                rule_set_code=r["rule_set_code"],
                source_zh=r["source_zh"],
                target_en=r["target_en"],
                status=status,
                source_changed=_source_changed(r["source_zh"], r["review_sha256"]),
                review_source=r["review_source"],
                translated_by=r["translated_by"],
                translated_at=r["translated_at"],
                reviewed_by=r["reviewed_by"],
                reviewed_at=r["reviewed_at"],
            )
        )
    return out


async def pending_rows(
    session: AsyncSession, *, entity_type: str | None = None, status: str | None = None
) -> list[TranslatableRow]:
    """D6 待審清單：三態聯集（`status is not None`），可選再篩單一狀態。

    **刻意不對 scope_key 去重**（與 `summary()` 不同，見該函式檔頭）：清單要讓
    使用者看到「哪個 rule-set 版本」卡在待審——`test_stale_status_when_zh_label_
    changes_after_human_review` 這類情境需要同一個 scope_key 在 active 與 draft
    兩列分別顯示不同狀態，去重會讓其中一列消失、使用者以為它已經沒問題了。
    """
    rows = await list_translatable_rows(session, entity_type=entity_type)
    pending = [r for r in rows if r.status is not None]
    if status is not None:
        pending = [r for r in pending if r.status == status]
    return pending


async def summary(session: AsyncSession, *, entity_type: str | None = None) -> dict[str, int]:
    """`{total, reviewed, pending}`——供頁首顯示「英文覆核 n/總數」。

    **DISTINCT `(entity_type, scope_key, field)`（S2 覆審修正，2026-08-18）**：
    `list_translatable_rows()` 對 rule_option 是「每個 rule-set 版本各一列」——
    一有 draft，同一個 scope_key 就出現兩列（active ＋ draft），若直接
    `len(rows)` 當分母，63 會在有 draft 時變成 126，同一條翻譯被算兩次，
    「n/63」這個 D6 明文要求的驗收語意就破了。這裡改成以
    `(entity_type, scope_key, field)` 為鍵去重，與側表 `i18n_review_state` 的
    UNIQUE 鍵同一個粒度——每個業務鍵只算一次，不論背後有幾個 rule-set 版本
    共用它。

    去重時「同一鍵留哪一列的 status」：取**第一筆**——`_candidates_sql()` 的
    `ORDER BY ... rule_set_is_active DESC` 已經保證同一 scope_key 內 active 版
    排最前面，所以這裡天然等於「以 active 版的狀態為準」，與 D6「`n/63` 描述
    的是 active 版覆核進度」的語意一致。`pending_rows()`／`list_translatable_rows()`
    刻意不做這個去重（見 `pending_rows` 檔頭）——去重只在「算總數」這個場合
    是對的，在「列出待辦」這個場合會讓 draft 專屬的 stale 項目消失。
    """
    rows = await list_translatable_rows(session, entity_type=entity_type)
    by_key: dict[tuple[str, str, str], TranslatableRow] = {}
    for r in rows:
        key = (r.entity_type, r.scope_key, r.field)
        by_key.setdefault(key, r)  # 第一筆留下（SQL 已排 active 優先）
    distinct_rows = by_key.values()
    total = len(distinct_rows)
    pending = sum(1 for r in distinct_rows if r.status is not None)
    return {"total": total, "reviewed": total - pending, "pending": pending}
