"""i18n 覆核狀態服務（ADR-032 D5／D6）。

四件事：
1. `i18n_review_state` 的讀寫原語（`get_review_state` / `upsert_review_state`）
   ——供灌值腳本與人工覆核端點共用，是覆核狀態的唯一寫入路徑。
2. 待審清單的三態聯集查詢（D6）——「目標欄位 IS NULL」／「有側表列且
   source ∈ {machine,legacy_seed,untranslated}」／「有側表列且來源已過期
   （中文 sha256 不符）**或譯文在覆核後被改過**（英文 sha256 不符，v2_0043）」。
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
4. 覆核 mutation（`mark_reviewed` / `assign_review`，2026-08-20 D6 後半）——
   「標記已覆核」與「指派」，譯文修正與側表寫入同交易，見檔案末節的檔頭。

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

from ddm_v2.exceptions import NotFoundError, ValidationError
from ddm_v2.models.v2.i18n import ENTITY_TYPES, FIELDS, SOURCES, I18nReviewState
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.nlp.normalization import normalize
from ddm_v2.schemas.v2.rule_set_options import OptionSpec, resolve
from ddm_v2.services.v2.audit_service import log_audit

__all__ = [
    "ENTITY_TYPES",
    "FIELDS",
    "PENDING_STATUSES",
    "SOURCES",
    "ReviewRowNotFound",
    "ReviewTargetMissing",
    "TranslatableRow",
    "UnknownReviewScopeKey",
    "assign_review",
    "find_translatable_row",
    "get_review_state",
    "list_translatable_rows",
    "mark_reviewed",
    "norm_sha256",
    "pending_rows",
    "summary",
    "upsert_review_state",
]

PENDING_STATUSES = ("never_translated", "unreviewed", "stale")

# rule_option 的 scope_key 前綴（"{param}:{code}"）→ 可能承載該 code 的 `OptionSpec`。
# 'p' 前綴同時被 rule_p_bases（p_ 開頭 code）與 rule_p_addons（a_ 開頭 code）共用
# （scope_key 設計見 D5／`dev_seed_i18n_labels.py` 檔頭：兩表 code 命名空間不重疊，
# 逐一嘗試即可，不需要另外解析 code 前綴）。
#
# **值是 `OptionSpec` 而不是裸 model**（ADR-032 D6 mutation 輪次改）：覆核端點要能
# 「順手改譯文」就得回頭呼叫 `rule_option_service.update_option_en_text(code, param,
# section, ...)`，而 section 只有 P 才分岔——與其在這裡另外維護一份「哪個表對哪個
# section」的對照（第二份真相，必然漂移），不如直接持有 ADR-023 D2 分派表
# （`schemas/v2/rule_set_options.resolve`）解出來的 spec，model 與 section 都從它取。
_RULE_OPTION_SPECS_BY_PARAM: dict[str, tuple[OptionSpec, ...]] = {
    "b": (resolve("B", "default"),),
    "g": (resolve("G", "default"),),
    "p": (resolve("P", "base"), resolve("P", "addon")),
    "m": (resolve("M", "verb"),),
    "x": (resolve("X", "default"),),
    "i": (resolve("I", "default"),),
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
        for spec in _RULE_OPTION_SPECS_BY_PARAM.get(param, ()):
            model = spec.model
            # `model` 是 `OptionSpec.model`（宣告型別 `Any`）——七張表沒有共同的
            # mixin/Protocol 宣告 `id`／`code`，mypy 看不到
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
    target_text: str | None = None,
    translated_at: datetime | None = None,
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

    **`target_text`（v2_0043）**：覆核當下的**英文譯文**，落成 `target_sha256`
    （與 `source_text`→`source_sha256` 對稱，同一支 `norm_sha256`）。`None` ＝
    這次寫入沒有記錄譯文基準 → `target_sha256` 一併清成 NULL，維持本函式
    last-write-wins 的整列語意（`source`／`reviewed_by` 本來就是這個規則）。

    **`translated_at`：`None` ＝取 now()（原行為）**；顯式帶值是給「只覆核、
    沒改譯文」的路徑保存原本的翻譯時間用的——譯文一個字沒動卻把翻譯時間往前推，
    是憑空捏造的事實。

    **`assigned_to`／`assigned_at` 刻意不在 last-write-wins 的範圍內**：指派是與
    「譯文的來源／覆核狀態」正交的第三種事實（誰在處理它），不該因為某人重跑一次
    灌值腳本或標了一次覆核就被清掉。改指派只走 `assign_review()`。
    """
    if not await _scope_key_exists(session, entity_type, scope_key, field):
        raise UnknownReviewScopeKey(entity_type=entity_type, scope_key=scope_key, field=field)
    existing = await get_review_state(session, entity_type, scope_key, field, locale)
    sha = norm_sha256(source_text)
    target_sha = norm_sha256(target_text) if target_text is not None else None
    now = datetime.now(timezone.utc)
    translated = translated_at or now
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
            translated_at=translated,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            target_sha256=target_sha,
            note=note,
        )
        session.add(row)
    else:
        existing.source = source
        existing.source_sha256 = sha
        existing.translated_by = translated_by
        existing.translated_at = translated
        existing.reviewed_by = reviewed_by
        existing.reviewed_at = reviewed_at
        existing.target_sha256 = target_sha
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
    """組出**單一** SQL 陳述式：16 個來源 UNION ALL，再 LEFT JOIN 覆核側表。

    表／欄名皆為本模組常數（非外部輸入），故用 f-string 組 SQL 是安全的
    （與 `rule_set_service.count_references` 同慣例，noqa: S608）。

    **7 張選項表各出兩列候選：`field='label'` 與 `field='sentence'`**
    （2026-08-20，D6 mutation 輪次補；先前只出 `'label'`）。Phase C 已經把 63 筆
    `field='sentence'` 的覆核狀態寫進側表，但它們**永遠不會出現在待審清單裡**——
    也就是使用者在英文介面實際讀到的那些句子（METHOD 敘事）覆核追蹤是 0% 且不可達，
    風險低得多的下拉標籤反而 100% 可見。清單一旦要能操作（可指派、可標記完成），
    這個缺口就必須補。代價是 `summary()` 的分母從 63 變成 126（ADR-032 D10 Phase B
    的「n/63」已隨本輪補記更新為「n/126」）。

    **句面的來源中文取 `COALESCE(NULLIF(sentence_text_zh,''), label_zh)`**：這不是
    「順手加個 fallback」，而是必須與引擎的回退鏈逐字一致——`narrative._sent()` 是
    `entry.get("sentence") or entry.get("label")`（空字串也會回退），
    `dev_seed_i18n_labels` 算 `source_sha256` 時用的是同一條鏈
    （`row.sentence_text_zh or row.label_zh`）。若這裡改用裸 `sentence_text_zh`，
    句面留空的那幾條會拿一個引擎根本沒讀、seed 也沒記過的字串去算 sha256，
    整批句面會永遠顯示 `stale`。**代價是 `source_zh` 看不出中文句面本身是不是空的**
    ——所以每一列另外帶一欄 `source_is_fallback`（句面列＝`sentence_text_zh` 為
    NULL／空字串；label 與主數據列一律 `false`）。它不是給使用者看的：
    `_is_reviewable_target()` 用它判斷「把英文句面標成空字串」是不是 D7.6 的
    「刻意不入句」（合法）還是把有中文的句子標成沒英文（橡皮圖章，422）。

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
               false AS source_is_fallback,
               rs.is_active AS rule_set_is_active
        FROM {table} t JOIN rule_sets rs ON rs.id = t.rule_set_id
        WHERE {IN_SCOPE_RULE_SET_SQL}
        """
        for table, param in _RULE_OPTION_SOURCES
    ]
    parts += [
        f"""
        SELECT 'rule_option', '{param}:' || t.code,
               'sentence', rs.code,
               COALESCE(NULLIF(t.sentence_text_zh, ''), t.label_zh), t.sentence_text_en,
               (t.sentence_text_zh IS NULL OR t.sentence_text_zh = ''),
               rs.is_active
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
               v.name_zh, v.name_en, false, NULL::boolean
        FROM work_vocab_items v
        """
    )
    parts.append(
        """
        SELECT 'motion_template', m.id::text, 'name', NULL,
               m.name_zh, m.name_en, false, NULL::boolean
        FROM motion_templates m
        """
    )
    candidates = " UNION ALL ".join(parts)
    return f"""
    WITH candidates AS ({candidates})
    SELECT c.entity_type, c.scope_key, c.field, c.rule_set_code, c.source_zh, c.target_en,
           c.source_is_fallback,
           r.source AS review_source, r.source_sha256 AS review_sha256,
           r.target_sha256 AS review_target_sha256,
           r.translated_by, r.translated_at, r.reviewed_by, r.reviewed_at,
           r.assigned_to, r.assigned_at
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

    `target_changed`（v2_0043，D6 末尾 park 的設計題定案）：與 `source_changed`
    正交的第二個維度——**英文譯文**在覆核之後被改過（`target_sha256` 比對）。
    兩者都會讓 `status` 變成 `stale`（都是「曾經被覆核，之後內容變了」），但
    「中文改了、譯文要跟上」與「有人動了譯文、要重新確認」對覆核者是兩件事，
    所以照 `source_changed` 的先例再加一個獨立布林欄位，**不引入第四個 status 值**
    （`status` 的三態聯集維持 D6 定義的形狀不變）。`target_sha256 is None`
    （從未覆核過）時一律 `False`：沒有基準可比較，不能算「變了」。

    `source_is_fallback`（2026-08-20 覆核修正）：`source_zh` 是**回退**來的，不是這一
    列自己的中文——只有 `field='sentence'` 且 `sentence_text_zh` 為 NULL／空字串時為
    真（那時 `source_zh` 取的是 `label_zh`，見 `_candidates_sql`）。存在的唯一理由是
    `_is_reviewable_target()` 要分辨「中文句面本身就是空的」（D7.6 刻意不入句 → 英文
    句面可以是空字串）與「中文句面有字」（英文空字串＝沒翻譯，不得標成已覆核）。
    """

    entity_type: str
    scope_key: str
    field: str
    rule_set_code: str | None
    source_zh: str
    target_en: str | None
    source_is_fallback: bool
    status: str | None
    source_changed: bool
    target_changed: bool
    review_source: str | None
    translated_by: str | None
    translated_at: datetime | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    assigned_to: str | None
    assigned_at: datetime | None


def _classify(
    source_zh: str,
    target_en: str | None,
    review_source: str | None,
    review_sha256: str | None,
    review_target_sha256: str | None = None,
) -> str | None:
    """D6 的三態聯集判準（單一函式，避免三處各自寫一次判斷式而漂移）。

    **優先序（`unreviewed` 先於 `stale` 判定）是刻意的，不是巧合**：`stale`
    描述的是「曾經被 IE 覆核（`source='human'`），中文來源之後又變了」——
    D5 原文「中文來源變了，譯文就是過期，**重回**待審清單」的「重回」二字
    意味著它曾經離開過待審清單（＝曾經被覆核）。一列還停在 `machine`／
    `legacy_seed` 時本來就從未離開待審清單，不存在「重回」，所以即使
    `source_sha256` 剛好對不上現行中文（例如灌值後又手動改了中文標籤），
    仍報 `unreviewed`——對使用者更有意義的訊息是「這條還沒人看過」，
    不是「這條過期了」（過期意味著曾經有人確認過、現在需要重新確認）。

    **第四支（`target_changed`，v2_0043）**：中文沒變、但**英文譯文**在覆核之後
    被改過（`target_sha256` 對不上現行 `_en`）——同樣是「曾經被覆核，之後內容
    變了」，所以歸同一個 `stale`，不另立第四個 status 值（見
    `TranslatableRow.target_changed`）。這一支的存在讓 D4 開出來的線上編輯路徑
    （`rule_option_service.update_option_en_text`）不會把已覆核狀態帶著走：改了
    英文卻不重新覆核，這一列會自己回到待審清單。

    **有譯文但查無側表列（`review_source is None`）→ `unreviewed`，不是 `stale`**
    （2026-08-20 覆核修正）：沒有側表列代表**從來沒有人覆核過這一列**，而 `stale`
    的定義是「曾經被覆核，之後內容變了」——一條沒有覆核基準的列不可能「過期」，
    報 `stale` 傳達的訊息與事實相反。這一支**日常可達，不是理論邊角**：
    `POST /api/v2/vocab` 帶 `name_en` 建新詞彙時完全不寫側表列，每一筆新詞彙一
    出生就會落進來；D4 開的 `_en` 線上編輯閘也只寫欄位、不碰側表（那是刻意的：
    文字一個真相、覆核狀態一個真相）。修正前這一支靠「`review_sha256` 為 None
    必然 `!=` 任何 sha256」掉進 `stale`，並且讓 `assign_review()` 就地補一筆
    `legacy_seed` 側表列的動作**把 status 從 `stale` 改成 `unreviewed`**——那與
    「指派記的是誰在處理，不改變處理到哪」這句三處明文承諾（`assign_review`
    檔頭、`api/routes/v2/i18n.py`、ADR-032 D6 補記）直接矛盾。改成在這裡顯式
    回 `unreviewed` 之後，指派前後的 status 一致，那三處承諾才是真的。
    `unreviewed` 與 `stale` 同屬 `PENDING_STATUSES`，`summary()` 的分子分母不變。
    """
    if target_en is None:
        return "never_translated"
    if review_source is None:
        return "unreviewed"  # 沒有側表列＝從未被覆核，不可能「過期」
    if review_source in _UNREVIEWED_SOURCES:
        return "unreviewed"
    if review_sha256 != norm_sha256(source_zh):
        return "stale"
    if _target_changed(target_en, review_target_sha256):
        return "stale"
    return None


# 「有側表列但尚未經人覆核」的 source 值域。`untranslated`（v2_0043）＝側表列只為
# 記指派而存在、尚無譯文——若這樣的列日後被別的路徑填了 `_en`（例如 D4 的線上
# 編輯閘只寫欄位、不碰側表），它必須報 `unreviewed` 而不是掉進「已覆核」那一支。
_UNREVIEWED_SOURCES = frozenset({"machine", "legacy_seed", "untranslated"})


def _target_changed(target_en: str | None, review_target_sha256: str | None) -> bool:
    """覆核當下記下的英文譯文是否已被改過（v2_0043；D6 末尾 park 的設計題）。

    `review_target_sha256 is None` → `False`：從未被覆核過的列沒有基準可比較，
    不能算「變了」（與 `_source_changed` 對 `review_sha256 is None` 的處理對稱，
    ADR-032 D6 L3 已有這條先例）。**既有列一律是這種情形**（v2_0043 純加法，
    既有列的 `target_sha256` 全為 NULL），所以本欄位上線當下不會讓任何一列
    憑空變成 `stale`。

    `target_en is None`（覆核過的譯文被清空）→ `True`：那也是「內容變了」。
    這一列的 `status` 本來就會因為 `target_en is None` 而報 `never_translated`，
    但布林欄位仍如實回報「這條曾經有覆核基準，現在對不上了」。
    """
    if review_target_sha256 is None:
        return False
    if target_en is None:
        return True
    return review_target_sha256 != norm_sha256(target_en)


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
        status = _classify(
            r["source_zh"], r["target_en"], r["review_source"],
            r["review_sha256"], r["review_target_sha256"],
        )
        out.append(
            TranslatableRow(
                entity_type=r["entity_type"],
                scope_key=r["scope_key"],
                field=r["field"],
                rule_set_code=r["rule_set_code"],
                source_zh=r["source_zh"],
                target_en=r["target_en"],
                source_is_fallback=r["source_is_fallback"],
                status=status,
                source_changed=_source_changed(r["source_zh"], r["review_sha256"]),
                target_changed=_target_changed(r["target_en"], r["review_target_sha256"]),
                review_source=r["review_source"],
                translated_by=r["translated_by"],
                translated_at=r["translated_at"],
                reviewed_by=r["reviewed_by"],
                reviewed_at=r["reviewed_at"],
                assigned_to=r["assigned_to"],
                assigned_at=r["assigned_at"],
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


# ══════════════════════════════════════════════════════════════════
# 覆核 mutation（ADR-032 D6 的後半：標記已覆核／指派）
#
# D6 的驗收定義是「覆核進度是**可見且可下降**的數字」——Phase B 只交付了「可見」
# （唯讀清單），這一節是「可下降」。三個設計約束，每一個都對應 ADR 的一句話：
#
# 1. **改譯文與寫側表必須同一個交易**（譯文寫了、側表沒寫，或反之，就是資料不
#    一致：清單會顯示「已覆核」但字沒改，或字改了卻永遠停在未覆核）。本節的函式
#    全程只用呼叫端傳進來的同一個 `session`，自己**不 commit**——交易邊界由路由層
#    的 `get_db_session` 統一負責（成功 commit／例外 rollback）。
# 2. **譯文一律經 D4 的 `_en` 寫入閘**（`rule_option_service.update_option_en_text`），
#    不在這裡直接 `setattr` 到 rule-set 子表——否則 D4 的欄位白名單與 I5 唯一性
#    檢查就被繞過了，而繞過它的正是「覆核」這個最常走的路徑。
# 3. **不做批次核准**（ADR-032 R1／I5）：`g_grasp`(6 TMU)／`g_touch`(3 TMU) 這種
#    「英文看起來一樣」的風險只有逐條人看才擋得住，一次核准 126 列會把覆核變成
#    橡皮圖章，等於把 D2 賴以成立的第三個前提（每條譯文都有人負責）作廢。
# ══════════════════════════════════════════════════════════════════


class ReviewRowNotFound(NotFoundError):
    """指定的 `(entity_type, scope_key, field[, rule_set_code])` 不在候選集合裡（404）。

    與 `UnknownReviewScopeKey` 的差別：那支問「這個 entity 存在嗎」（跨所有版本），
    這支問「它在**待審清單的來源集合**裡嗎」——D6 的來源集合是 active rule-set ＋
    現存 draft ＋ 全部主數據，`published(非 active)`／`retired` 的凍結歷史不在內。
    對一個清單上根本看不到的列做覆核沒有意義，fail-closed 拒絕。
    """

    def __init__(self, *, entity_type: str, scope_key: str, field: str, rule_set_code: str | None) -> None:
        where = f"（rule_set_code={rule_set_code}）" if rule_set_code else "（未指定 rule_set_code → 以 active 版為準）"
        super().__init__(
            f"覆核對象不在待審清單的來源集合裡：{entity_type}/{scope_key}/{field}{where}。"
            "來源集合＝active rule-set ＋ 現存 draft ＋ 全部主數據（ADR-032 D6）；"
            "若這個 code 只存在於某個 draft，請顯式帶上該 draft 的 rule_set_code。",
            detail={
                "code": "I18N_REVIEW_ROW_NOT_FOUND",
                "entity_type": entity_type,
                "scope_key": scope_key,
                "field": field,
                "rule_set_code": rule_set_code or "",
            },
        )


class ReviewTargetMissing(ValidationError):
    """要標記已覆核，但這一列沒有可覆核的英文（422）。

    **這是反橡皮圖章的那道檢查，不是型別驗證**：把一條還沒有譯文（或譯文是空白）
    的列標成「已覆核」，等於用覆核狀態掩蓋一個空欄位——覆核率會上升，英文介面
    卻還是空的。要覆核就得先有字：請在同一個請求帶 `target_en`。

    `field='sentence'` 是**刻意的例外，但有前提**：句面空字串是合法且有意義的值
    （「這條刻意不入句」，ADR-032 D7.6／`dev_seed_i18n_labels.py` 句面表註解），
    對它可以覆核——**前提是這一列的中文句面本身就是空的**（`source_is_fallback`）。
    2026-08-20 覆核修正前這個例外是無條件的，等於一張橡皮圖章：中文句面「抓握」
    的那一列也吃得下 `target_en=""`，回 200、`status` 變 null、離開待審清單，而
    英文是空的——63 條句面用 63 個空字串請求就能把 `n/126` 推到 126/126 而英文全空，
    正是 ADR-032 R2 寫明的「本 ADR 最可能的失敗模式」。標籤／名稱沒有「刻意不入句」
    這種語意，空白一律拒絕。
    """

    def __init__(self, *, entity_type: str, scope_key: str, field: str) -> None:
        super().__init__(
            f"{entity_type}/{scope_key}/{field} 目前沒有可覆核的英文譯文——"
            "要標記已覆核請在同一個請求帶入 `target_en`（不得把空白標成已覆核）。",
            detail={
                "code": "I18N_REVIEW_TARGET_MISSING",
                "entity_type": entity_type,
                "scope_key": scope_key,
                "field": field,
            },
        )


# `field` → 主數據／選項表上承載英文的欄位。`rule_option` 兩個 field 對到 D4 白名單
# 的兩欄（`EN_WRITABLE_FIELDS`）；主數據只有一個 `name_en`。
_EN_COLUMN_BY_FIELD = {"label": "label_en", "sentence": "sentence_text_en", "name": "name_en"}

# 允許空字串當作合法譯文的 field。只有句面，且**還要中文句面本身為空**才放行
# （`_is_reviewable_target`）——見 `ReviewTargetMissing` 檔頭。
_BLANK_OK_FIELDS = frozenset({"sentence"})


def _is_reviewable_target(field: str, target_en: str | None, *, source_is_fallback: bool) -> bool:
    """這段英文算不算「可覆核的譯文」（見 `ReviewTargetMissing` 檔頭）。

    空字串的放行條件是**恰好是空字串**（不是「strip 後為空」）**且**這一列的中文
    句面本身為空——前者讓 `"   "` 這種純空白落到下面的 `strip()` 判斷去（純空白不是
    「刻意不入句」，是沒翻譯；而且 `narrative_en._sent()` 的回退鏈
    `sentence_en or label_en` 吃不掉 truthy 的空白字串，會把空白當動詞組進句子）；
    後者見上面的檔頭。
    """
    if target_en is None:
        return False
    if target_en == "":
        return field in _BLANK_OK_FIELDS and source_is_fallback
    return bool(target_en.strip())


async def find_translatable_row(
    session: AsyncSession,
    *,
    entity_type: str,
    scope_key: str,
    field: str,
    rule_set_code: str | None = None,
) -> TranslatableRow:
    """在待審清單的候選集合裡定位一列（找不到 → `ReviewRowNotFound`）。

    **刻意重用 `list_translatable_rows()` 而不是另寫一支查詢**：mutation 端點記錄的
    `source_sha256`／`target_sha256` 必須是「覆核者在清單上**看到的那個** 中文／英文」，
    兩邊只要有一處對來源欄位的解讀不同（例如句面的 `sentence_text_zh` 回退鏈），
    覆核完的列就會立刻被讀取端判成 `stale`。同一份 SQL ＝不可能漂移。
    資料量小（現況 rule_option 126 ＋ 主數據 ~75 列），一次全掃可接受。

    **也刻意不接受呼叫端傳來的中文／英文字串**：那等於讓 client 宣告「我覆核的是
    這段文字」，與 ADR-023 D2「API 不收 client 端算好的值」同一個理由。

    `rule_set_code` 的語意：`rule_option` 的同一個 `scope_key` 可能同時存在於 active
    與多個 draft（D5 刻意讓 scope_key 不含 rule_set_id）。未指定時**以 active 版為準**
    （與 `summary()` 的 active-first 去重同一個口徑），active 版沒有這個 code 時
    **不靜默改挑一個 draft**，直接 404 並在訊息裡指出要顯式帶 rule_set_code。
    """
    rows = [
        r for r in await list_translatable_rows(session, entity_type=entity_type)
        if r.scope_key == scope_key and r.field == field
    ]
    if entity_type == "rule_option":
        wanted = rule_set_code
        if wanted is None:
            from ddm_v2.services.v2.rule_set_service import get_active_rule_set_code

            wanted = await get_active_rule_set_code(session)
        rows = [r for r in rows if r.rule_set_code == wanted]
    if not rows:
        raise ReviewRowNotFound(
            entity_type=entity_type, scope_key=scope_key, field=field, rule_set_code=rule_set_code
        )
    return rows[0]


async def _resolve_option_spec(
    session: AsyncSession, *, rule_set_code: str, param: str, code: str
) -> OptionSpec:
    """`scope_key` 的參數前綴 ＋ option code → `OptionSpec`（決定要打哪張表／哪個 section）。

    只有 P 需要分辨（base／addon），但**用查表而不是解析 code 前綴**：命名慣例
    （`p_` vs `a_`）是資料現況，不是 schema 約束，draft 裡新增一個不照慣例命名的
    code 完全合法。查表則對任何命名都正確。
    """
    rs_id = (
        await session.execute(select(RuleSet.id).where(RuleSet.code == rule_set_code))
    ).scalar_one_or_none()
    if rs_id is not None:
        for spec in _RULE_OPTION_SPECS_BY_PARAM.get(param, ()):
            model = spec.model
            found = (
                await session.execute(
                    select(getattr(model, "id")).where(  # noqa: B009 - 見 `_scope_key_exists`
                        getattr(model, "rule_set_id") == rs_id,  # noqa: B009
                        getattr(model, "code") == code,  # noqa: B009
                    )
                )
            ).first()
            if found is not None:
                return spec
    raise ReviewRowNotFound(
        entity_type="rule_option", scope_key=f"{param}:{code}", field="label", rule_set_code=rule_set_code
    )


async def _write_target_en(
    session: AsyncSession, row: TranslatableRow, target_en: str, *, actor: str
) -> None:
    """把新譯文落盤。`rule_option` **一律經 D4 的 `_en` 寫入閘**（見本節檔頭第 2 點）。"""
    column = _EN_COLUMN_BY_FIELD[row.field]
    if row.entity_type == "rule_option":
        from ddm_v2.services.v2 import rule_option_service

        param, _sep, code = row.scope_key.partition(":")
        spec = await _resolve_option_spec(
            session, rule_set_code=row.rule_set_code or "", param=param, code=code
        )
        await rule_option_service.update_option_en_text(
            session, row.rule_set_code or "", spec.param, spec.section, code,
            {column: target_en}, actor=actor,
        )
        return
    # 主數據（ADR-024）：詞彙／範本無版本、無凍結狀態，`name_en` 本來就有 analyst
    # 級的 PATCH 路徑（`vocab.py`／`motion_template.py`），這裡只是同交易內就地寫。
    # **前後值的留痕由呼叫端負責**（`mark_reviewed` 把 `changed_fields` 放進
    # `i18n_review_mark` 的 payload）：`rule_option` 走上面的 `_en` 閘、有自己的
    # `option_en_update` 稽核記前後值，主數據這條沒有對應的稽核路徑，
    # 若不補就只剩「某人覆核過這條」而還原不了被改成什麼（sec 覆審 2026-08-20）。
    model = WorkVocabItem if row.entity_type == "vocab_item" else MotionTemplate
    obj = await session.get(model, uuid.UUID(row.scope_key))
    if obj is None:  # pragma: no cover - find_translatable_row 已保證存在
        raise ReviewRowNotFound(
            entity_type=row.entity_type, scope_key=row.scope_key, field=row.field,
            rule_set_code=None,
        )
    setattr(obj, column, target_en)
    await session.flush()


async def _log_review_audit(
    session: AsyncSession, row: TranslatableRow, *, action: str, actor: str, **payload: object
) -> None:
    """覆核／指派的留痕（D5：「覆蓋寫入由既有 `workflow_audit_log` 承接即可」）。

    側表本身是 last-write-wins，**覆蓋掉的前一次覆核不留痕**——所以誰在什麼時候
    把某條標成已覆核（尤其是覆蓋別人的覆核）只有 audit log 說得清。
    `entity_id` 對 `rule_option` 取該 rule-set 的 id（scope_key 不是 UUID，而
    `workflow_audit_log.entity_id` 是 UUID NOT NULL），對主數據取該列 id。
    """
    if row.entity_type == "rule_option":
        entity_type, entity_id = "rule_set", (
            await session.execute(select(RuleSet.id).where(RuleSet.code == row.rule_set_code))
        ).scalar_one()
    else:
        entity_type, entity_id = row.entity_type, uuid.UUID(row.scope_key)
    await log_audit(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        from_status=None,
        to_status=None,
        actor=actor,
        payload={
            "scope_key": row.scope_key, "field": row.field, "locale": "en",
            "rule_set_code": row.rule_set_code, **payload,
        },
    )
    await session.flush()


async def mark_reviewed(
    session: AsyncSession,
    *,
    entity_type: str,
    scope_key: str,
    field: str,
    reviewed_by: str,
    target_en: str | None = None,
    rule_set_code: str | None = None,
    note: str | None = None,
    locale: str = "en",
) -> TranslatableRow:
    """標記一列英文為「已由人覆核」，可選在同一個請求裡順手修正譯文。

    落盤內容：`source='human'` ＋ `reviewed_by`／`reviewed_at` ＋ `target_sha256`
    （＝覆核當下的英文譯文；之後有人改英文，讀取端就會把它判回 `stale`）。
    `source='human'` 時 `reviewed_by` 必填由 **DB CHECK** 保證（v2_0040）。

    **`target_en` 帶了就先落盤、再寫側表，全程同一個交易**（本節檔頭第 1 點）：
    順序是刻意的——先過 D4 的 `_en` 寫入閘（retired／欄位白名單／I5 唯一性都在
    那裡擋），閘擋下來時側表一個字都還沒寫；閘過了之後側表寫入若失敗，
    路由層的 rollback 會把譯文一起收回。兩邊不可能只成功一半。

    **不改譯文時，`translated_by`／`translated_at`／`note` 沿用既有值**：`upsert_
    review_state` 是整列 last-write-wins，不顯式沿用就會把「這批是哪個模型翻的、
    什麼時候翻的」抹成 `None`——那是還原不回來的事實，而覆核並沒有改變它。

    **稽核 payload 帶 `changed_fields`（形狀比照 `option_en_update`）**：改了譯文時
    記 `{欄位: {before, after}}`，沒改時為 `None`。`rule_option` 的前後值另有
    `option_en_update` 一筆（走 `_en` 閘），主數據（`vocab_item`／`motion_template`，
    約 75 條）先前**完全沒有前後值留痕**——只看得到「某人覆核過這條」，還原不了
    英文被改成什麼。兩類物件的稽核形狀在這裡統一（sec 覆審 2026-08-20）。
    """
    row = await find_translatable_row(
        session, entity_type=entity_type, scope_key=scope_key, field=field, rule_set_code=rule_set_code
    )
    existing = await get_review_state(session, entity_type, scope_key, field, locale)

    changed_fields: dict[str, dict[str, str | None]] | None = None
    if target_en is not None:
        if not _is_reviewable_target(field, target_en, source_is_fallback=row.source_is_fallback):
            raise ReviewTargetMissing(entity_type=entity_type, scope_key=scope_key, field=field)
        await _write_target_en(session, row, target_en, actor=reviewed_by)
        # `row.target_en` 是寫入前的值（`find_translatable_row` 在上面就取好了，
        # 與待審清單同一份 SQL），故此處的 before/after 是如實的前後值。
        changed_fields = {_EN_COLUMN_BY_FIELD[field]: {"before": row.target_en, "after": target_en}}
        effective_target = target_en
    else:
        if not _is_reviewable_target(field, row.target_en, source_is_fallback=row.source_is_fallback):
            raise ReviewTargetMissing(entity_type=entity_type, scope_key=scope_key, field=field)
        effective_target = row.target_en  # type: ignore[assignment]  # _is_reviewable_target 已排除 None

    await upsert_review_state(
        session,
        entity_type=entity_type,
        scope_key=scope_key,
        field=field,
        locale=locale,
        source="human",
        source_text=row.source_zh,
        target_text=effective_target,
        translated_by=reviewed_by if target_en is not None else (existing.translated_by if existing else reviewed_by),
        translated_at=None if target_en is not None else (existing.translated_at if existing else None),
        reviewed_by=reviewed_by,
        reviewed_at=datetime.now(timezone.utc),
        note=note if note is not None else (existing.note if existing else None),
    )
    await _log_review_audit(
        session, row, action="i18n_review_mark", actor=reviewed_by,
        previous_source=existing.source if existing else None,
        previous_reviewed_by=existing.reviewed_by if existing else None,
        target_changed=target_en is not None,
        changed_fields=changed_fields,
    )
    return await find_translatable_row(
        session, entity_type=entity_type, scope_key=scope_key, field=field, rule_set_code=rule_set_code
    )


async def assign_review(
    session: AsyncSession,
    *,
    entity_type: str,
    scope_key: str,
    field: str,
    assigned_to: str | None,
    actor: str,
    rule_set_code: str | None = None,
    locale: str = "en",
) -> TranslatableRow:
    """指派／取消指派一條待審項（D6 驗收定義「每條**可指派**」）。

    `assigned_to=None`（或全空白）＝取消指派，兩個欄位一起回 NULL。

    **側表列不存在時就地建立一筆**——指派最需要用到的正是 `never_translated`
    那些列（還沒有譯文、最需要有人認領），而它們依 D5 的預設值表本來就「無列」。
    新建列的 `source` 取值：
    - 沒有譯文 → `'untranslated'`（v2_0043 新增的值域；舊三個值每一個都是在描述
      「譯文從哪來」，對一條還沒有譯文的列填任何一個都是謊，見 migration 檔頭）；
    - 有譯文卻沒有側表列 → `'legacy_seed'`，那正是這個值的既有語意
      （ADR-032 1.2c：「有值但出處不明，等同未覆核」）。可能的來路：D4 的 `_en`
      線上編輯閘只寫欄位、不碰側表（那是刻意的——文字一個真相、覆核狀態一個真相）。

    兩種取值都落在 `_UNREVIEWED_SOURCES` 裡，所以**指派不會改變一列的 `status`**
    （指派是「誰在處理」，不是「處理到哪」）。
    """
    row = await find_translatable_row(
        session, entity_type=entity_type, scope_key=scope_key, field=field, rule_set_code=rule_set_code
    )
    assignee = (assigned_to or "").strip() or None
    state = await get_review_state(session, entity_type, scope_key, field, locale)
    now = datetime.now(timezone.utc)
    if state is None:
        state = I18nReviewState(
            id=uuid.uuid4(),
            entity_type=entity_type,
            scope_key=scope_key,
            field=field,
            locale=locale,
            source="untranslated" if row.target_en is None else "legacy_seed",
            source_sha256=norm_sha256(row.source_zh),
            translated_by=None,
            translated_at=now,
        )
        session.add(state)
    state.assigned_to = assignee
    state.assigned_at = now if assignee else None
    await session.flush()
    await _log_review_audit(
        session, row, action="i18n_review_assign", actor=actor, assigned_to=assignee,
    )
    return await find_translatable_row(
        session, entity_type=entity_type, scope_key=scope_key, field=field, rule_set_code=rule_set_code
    )
