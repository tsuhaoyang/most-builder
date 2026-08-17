"""同義詞登記準則守門（ADR-023 §3.3 規則 1 補節二；D3-028）。

**準則**：同義詞登記的合法來源只有二——

  (a) 該詞出現在對應選項自己的**標籤/句面文字**裡（正規化後子串比對，任一
      方向：詞含標籤或標籤含詞）；或
  (b) 有明確的 **IE 裁決紀錄**（repo 側 allowlist，鍵＝(parameter, norm,
      option_code)，值＝裁決引用）。

**工程端不得以相似性自行判定。** 動機（D3-028 Q4）：IE 反問「動詞應該要按照
most 字典庫去查吧？」——查證 22 條現況，21 條屬 (a)、唯一例外「插入→
p_asm_single」屬 (b)（D3-021 多費力＝base+addon 的 IE 裁決）。工程端曾提的
「下壓≈按壓」「按下≈按動按鈕」字典查無，純屬相似性判斷——同義詞決定
option code、option code 決定 TMU，等於讓工程判斷改工時，繞過 ADR-014 的
值權威。v3 認證字典**無 alias 欄位**可匯入（欄位名已逐一查證），所以 (a)
只能靠標籤/句面文字。

**為什麼是 integration**：判定對象是 DB 現存資料（`rule_option_synonyms` ⇄
各參數選項子表），不是程式碼常數；無 DATABASE_URL 時照既有慣例 skip。
**不新增 DB 欄位**（無 migration）：例外走 repo 側 allowlist，比照
`SEED_GOLD_IDS` 白名單模式——例外要進版控、被 review、可 grep。
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text as sql

from ddm_v2.nlp.normalization import normalize

pytestmark = pytest.mark.integration

# 各參數的選項子表（帶 `code` 可定址者）。A 是帶型（無 code，見 ADR-023 §2）、
# `vocab` 不是 rule-set 選項——兩者查不到文字，會 fail-closed 落進「未授權」，
# 這是刻意的：無法定址的選項沒有標籤可衍生，只能走 IE 裁決。
_PARAM_OPTION_TABLES: dict[str, tuple[str, ...]] = {
    "B": ("rule_b_options",),
    "G": ("rule_g_actions",),
    "P": ("rule_p_bases", "rule_p_addons"),
    "M": ("rule_m_verbs",),
    "X": ("rule_x_options",),
    "I": ("rule_i_options",),
}

# (b) 例外＝有明確 IE 裁決的登記。值＝裁決引用（哪一輪、哪份記錄）。
# **新增一條就要附得出裁決**——沒有裁決引用的相似性判斷不得寫進這裡。
IE_RULING_ALLOWLIST: dict[tuple[str, str, str], str] = {
    ("P", "插入", "p_asm_single"): (
        "D3-021（IE 第四輪答案，2026-08-17）：「插入」照放置邏輯掛 p_asm_single、"
        "多費力＝base+addon 雙段計時；字面「插入」不在 p_asm_single 的標籤"
        "「組(一種方向)」/句面「組」裡，故以裁決為據登記。"
        "見 docs/llm/gold-review/README.md「IE 第四輪答案」與 synonym-candidates.md"
    ),
}


def label_derived(synonym_norm: str, option_texts: list[str]) -> bool:
    """(a) 標籤衍生：正規化後與選項自己的文字有子串關係（任一方向）。

    雙向的理由（實測 22 條）：
    - 詞 ⊆ 標籤：`拿取` ⊆ `拿取(選取)`、`確認` ⊆ `並確認(正常視線範圍)`；
    - 標籤 ⊆ 詞：`放` ⊆ `放至`、`組` ⊆ `組至`、`推` ⊆ `推至`——字典的句面
      用的是單字動詞，工單寫的是帶方向補語的複合詞。

    **這是 provenance 測試，不是語意正確性測試**——邊界要講最誠實的版本：
    同一參數下多個 code 共用同一詞素時，本守門**判斷不出選了哪個 code**，
    而那正是決定 TMU 的那一步。實例：P 的 `p_place_none`（標籤「放(無方向)」／
    句面「放」）、`p_place_single`（「放(一種方向)」／「放」）、`p_asm_single`
    （「組(一種方向)」／「組」）——「放至」對前兩者都成立（現況也真的兩條都
    登記了，靠 priority 0/1 表達 IE 的情境裁決），守門對「放至→單方向 還是
    無方向」一句話都說不出口，但兩者的 P 值不同、TMU 就不同。

    它真正擋掉的只有一件事：「字典裡完全沒有這個詞素」的相似性判斷
    （`下壓` vs `按壓`、`按下` vs `按動按鈕` 互不含）。選哪個 code 由 IE 覆核、
    priority 偏好序與黃金測試承擔。ADR-023 補節有寫明同一條邊界。
    """
    norm = normalize(synonym_norm)
    if not norm:
        return False
    for raw in option_texts:
        text = normalize(raw or "")
        if not text:
            continue
        if norm in text or text in norm:
            return True
    return False


def unauthorized_synonyms(
    rows: list[dict[str, Any]],
    option_texts: dict[tuple[str, str], list[str]],
    allowlist: dict[tuple[str, str, str], str],
) -> list[str]:
    """回傳每一條不符合 (a)/(b) 的同義詞的說明（空 list＝全部合法）。

    純函式（不碰 DB）——mutation 測試才能塞假資料/清空 allowlist 直接驗守門。
    """
    problems: list[str] = []
    for r in rows:
        param, norm, code = r["parameter"], r["synonym_norm"], r["option_code"]
        if (param, norm, code) in allowlist:
            continue  # (b) 有 IE 裁決
        texts = option_texts.get((param, code), [])
        if label_derived(norm, texts):
            continue  # (a) 標籤衍生
        problems.append(
            f"{param} {norm!r} → {code}：既不出現在選項標籤/句面 {texts!r} 裡，"
            "也無 IE 裁決 allowlist 條目——工程端不得以相似性自行判定"
            "（ADR-023 §3.3 規則 1 補節二）"
        )
    return sorted(problems)


async def _fetch_synonyms(db_session) -> list[dict[str, Any]]:
    rows = (
        await db_session.execute(
            sql(
                "select rs.code as rule_set_code, s.parameter, s.synonym_norm,"
                " s.option_code, s.priority"
                " from rule_option_synonyms s"
                " join rule_sets rs on rs.id = s.rule_set_id"
                " order by rs.code, s.parameter, s.synonym_norm, s.option_code"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _fetch_option_texts(db_session) -> dict[tuple[str, str], list[str]]:
    """(parameter, option_code) → 該選項自己的文字（label_zh ＋ sentence_text_zh）。

    跨 rule-set 合併：同一 code 在不同版本可能有不同標籤，任一版本的標籤都算
    合法出處（同義詞的 UNIQUE 鍵含 rule_set，但「詞出自字典」這件事不隨版本
    改變）。合併讓守門對 clone 出來的草稿版本同樣成立。
    """
    out: dict[tuple[str, str], list[str]] = {}
    for param, tables in _PARAM_OPTION_TABLES.items():
        for table in tables:
            rows = (
                await db_session.execute(
                    sql(
                        f"select r.code, r.label_zh, coalesce(r.sentence_text_zh, '')"  # noqa: S608 - table 名來自本檔常數，非外部輸入
                        f" as sentence from {table} r"
                    )
                )
            ).all()
            for code, label, sentence in rows:
                out.setdefault((param, code), []).extend([label, sentence])
    return out


# ── 主守門 ──────────────────────────────────────────────────────────────────


async def test_every_registered_synonym_has_legal_provenance(db_session):
    """DB 現存每一條同義詞都必須是 (a) 標籤衍生或 (b) IE 裁決。"""
    rows = await _fetch_synonyms(db_session)
    assert rows, "DB 無任何同義詞——守門對象不存在，先跑 seed/登記再驗"
    texts = await _fetch_option_texts(db_session)
    assert unauthorized_synonyms(rows, texts, IE_RULING_ALLOWLIST) == []


async def test_allowlist_has_no_stale_entries(db_session):
    """allowlist 只放**現存**登記的例外——條目被撤銷登記後要一併刪，
    否則 allowlist 會累積成「以後也可以這樣登」的暗示。"""
    rows = await _fetch_synonyms(db_session)
    live = {(r["parameter"], r["synonym_norm"], r["option_code"]) for r in rows}
    stale = sorted(k for k in IE_RULING_ALLOWLIST if k not in live)
    assert stale == [], f"allowlist 有已不存在於 DB 的條目：{stale}"


async def test_allowlist_entries_cite_a_ruling(db_session):
    """(b) 的每一條都要附裁決引用——空字串/佔位符不算裁決紀錄。"""
    for key, ruling in IE_RULING_ALLOWLIST.items():
        assert isinstance(ruling, str) and len(ruling.strip()) >= 10, (
            f"{key}：allowlist 值必須是可追溯的裁決引用（哪一輪／哪份記錄）"
        )
        assert "D3-" in ruling, f"{key}：裁決引用要指得出輪次（D3-NNN）"


# ── mutation：守門真的會紅 ──────────────────────────────────────────────────


async def test_similarity_judgement_synonym_is_flagged(db_session):
    """mutation①：塞一條「相似性判斷」的假同義詞（D3-028 Q4 的兩個實例：
    下壓≈按壓、按下≈按動按鈕）→ 守門必須點名它。

    不寫 DB（唯讀語意）：直接把假 row 併進純函式的輸入。
    """
    rows = await _fetch_synonyms(db_session)
    texts = await _fetch_option_texts(db_session)
    fakes = [
        {"parameter": "M", "synonym_norm": "下壓", "option_code": "m_press"},
        {"parameter": "M", "synonym_norm": "按下", "option_code": "m_btn"},
    ]
    problems = unauthorized_synonyms(rows + fakes, texts, IE_RULING_ALLOWLIST)
    assert len(problems) == 2, problems
    assert any("'下壓'" in p and "m_press" in p for p in problems)
    assert any("'按下'" in p and "m_btn" in p for p in problems)


async def test_gate_catches_a_similarity_synonym_written_to_db(db_session):
    """mutation①b：把同一條假同義詞**真的寫進 DB**（走 conftest 的 savepoint
    隔離，teardown rollback）→ 主守門的查詢必須抓到。

    上一條證明純函式會判；這條證明「守門讀的是 DB 現況」——把查詢改成讀死
    名單、或漏掉某個 rule-set，本測試紅。
    """
    rs_id = (
        await db_session.execute(
            sql("select id from rule_sets where code = 'MINIMOST_FACTORY_V2'")
        )
    ).scalar_one()
    await db_session.execute(
        sql(
            "insert into rule_option_synonyms"
            " (rule_set_id, parameter, option_code, synonym_raw, synonym_norm,"
            "  priority, created_by)"
            " values (:rs, 'M', 'm_press', '下壓', '下壓', 5, 'UT_MUTATION')"
        ),
        {"rs": rs_id},
    )
    await db_session.flush()

    rows = await _fetch_synonyms(db_session)
    texts = await _fetch_option_texts(db_session)
    problems = unauthorized_synonyms(rows, texts, IE_RULING_ALLOWLIST)
    assert len(problems) == 1, problems
    assert "'下壓'" in problems[0] and "m_press" in problems[0]


async def test_allowlist_emptied_flags_the_ie_ruled_exception(db_session):
    """mutation②：allowlist 清空 → 唯一靠 (b) 成立的「插入→p_asm_single」
    必須轉紅（證明它真的不是 (a) 標籤衍生，allowlist 不是裝飾）。"""
    rows = await _fetch_synonyms(db_session)
    texts = await _fetch_option_texts(db_session)
    problems = unauthorized_synonyms(rows, texts, {})
    assert len(problems) == len(IE_RULING_ALLOWLIST), problems
    assert all("插入" in p and "p_asm_single" in p for p in problems)


async def test_unaddressable_parameter_fails_closed(db_session):
    """帶型參數（A）與 vocab 沒有可定址的選項標籤 → fail-closed 未授權。

    `create_synonym` 對 parameter='A' 刻意跳過 option_code FK 驗證
    （見 test_synonym_retired_gate），所以這條路徑真的寫得進 DB；守門不能
    因為「查不到選項」就靜默放行。
    """
    texts = await _fetch_option_texts(db_session)
    rows = [
        {"parameter": "A", "synonym_norm": "伸手", "option_code": "A6"},
        {"parameter": "vocab", "synonym_norm": "主機板", "option_code": "board"},
    ]
    problems = unauthorized_synonyms(rows, texts, IE_RULING_ALLOWLIST)
    assert len(problems) == 2, problems


def test_label_derivation_both_directions_and_negative():
    """(a) 的判定本身：兩個方向都算衍生，字典查無的相似性判斷不算。"""
    # 詞 ⊆ 標籤
    assert label_derived("拿取", ["拿取(選取)", "拿取"])
    assert label_derived("確認", ["並確認(正常視線範圍)", "並確認"])
    # 標籤 ⊆ 詞
    assert label_derived("放至", ["放(一種方向)", "放"])
    assert label_derived("組至", ["組(一種方向)", "組"])
    # 相似性判斷（D3-028 Q4）：兩個方向都不成立
    assert not label_derived("下壓", ["按壓", "按壓"])
    assert not label_derived("按下", ["按動按鈕", "按動按鈕"])
    # 空標籤/空詞不算衍生（fail-closed）
    assert not label_derived("按下", ["", ""])
    assert not label_derived("", ["按下"])
