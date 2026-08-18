"""`scripts/dev_seed_i18n_labels.py` 的翻譯表形狀守門（ADR-032 Phase B）。

**I5（同一參數表內英文標籤正規化後必須唯一）在這裡先做一次快速的、免 DB 的檢查**
——用腳本裡的真實翻譯表常數，不另抄一份樣本；對真實 active rule-set 資料的
唯一性驗證另見 `tests/integration/test_i18n_review_state.py`
（`test_english_labels_are_unique_within_each_rule_set_table`）。
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from ddm_v2.nlp.normalization import normalize

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_i18n_labels.py"


def _load():
    """按路徑載入腳本（`scripts/` 不是 package）——與 `test_audit_slot_inputs.py` 同慣例。

    必須先塞進 `sys.modules`：腳本內的 `@dataclass` 在處理欄位時會查
    `sys.modules[cls.__module__]`，沒登記就 `AttributeError`。
    """
    name = "_dev_seed_i18n_labels_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SEED = _load()

pytestmark = pytest.mark.unit


def test_rule_option_tables_cover_exactly_seven_tables():
    """D5／D6：7 張選項表，不多不少（P 的 base/addon 各自一張物理表）。"""
    tables = {model.__tablename__ for model, _param, _labels in SEED.RULE_OPTION_TABLES}
    assert tables == {
        "rule_b_options", "rule_g_actions", "rule_p_bases", "rule_p_addons",
        "rule_m_verbs", "rule_x_options", "rule_i_options",
    }


def test_rule_option_translations_total_sixty_three():
    """實測 active（`MINIMOST_FACTORY_V2`）63 列選項——翻譯表筆數釘住這個數字。"""
    total = sum(len(labels) for _model, _param, labels in SEED.RULE_OPTION_TABLES)
    assert total == 63


def test_vocab_translations_cover_fifty_three_distinct_names():
    """實測 `work_vocab_items` 59 列、53 個相異中文名（同名跨 kind 共用一條翻譯）。"""
    assert len(SEED.VOCAB_LABELS) == 53


@pytest.mark.parametrize("model_name", ["B", "G", "P_BASE", "P_ADDON", "M", "X", "I"])
def test_no_empty_translation_strings(model_name):
    """每一條翻譯都不得是空字串／純空白（否則等於白灌）。"""
    labels = {
        "B": SEED.B_LABELS, "G": SEED.G_LABELS, "P_BASE": SEED.P_BASE_LABELS,
        "P_ADDON": SEED.P_ADDON_LABELS, "M": SEED.M_LABELS, "X": SEED.X_LABELS,
        "I": SEED.I_LABELS,
    }[model_name]
    for code, en in labels.items():
        assert isinstance(en, str) and en.strip(), f"{model_name}.{code} 翻譯為空"


def test_i18n_labels_are_unique_per_table():
    """I5：同一張表內，正規化後的英文標籤不得重複。

    衝突就是腳本本身的 bug——本測試若紅，修法是**換一個更能區分語意的英文詞**，
    不是加後綴矇混（ADR-032 I5 明文禁止）。
    """
    for model, _param, labels in SEED.RULE_OPTION_TABLES:
        normed = [normalize(v) for v in labels.values()]
        dupes = {n for n in normed if normed.count(n) > 1}
        assert not dupes, f"{model.__tablename__} 有重複的正規化英文標籤：{dupes}"


def test_the_two_flagged_risk_pairs_are_genuinely_distinct():
    """R1／I5 明文點名的兩組高風險字面（不是恰好躲過 normalize，是真的不同詞）。"""
    assert normalize(SEED.G_LABELS["g_grasp"]) != normalize(SEED.G_LABELS["g_touch"])
    assert normalize(SEED.G_LABELS["g_pat"]) != normalize(SEED.G_LABELS["g_tap"])
    assert normalize(SEED.M_LABELS["m_tearopen"]) != normalize(SEED.M_LABELS["m_teartape"])
    # 且不共用詞根（比字面不同更進一步——語意差異也要在英文裡看得出來）
    assert "tear" not in normalize(SEED.M_LABELS["m_teartape"])


def test_no_literal_slide_out_screw_translation():
    """ADR-032 P3 明文點名「滑出螺絲」逐字翻成 'slide out screw' 是業界看不懂的反例——
    翻譯表不得原樣沿用這個被否決的譯法。"""
    assert normalize(SEED.M_LABELS["m_screw"]) != normalize("slide out screw")


def test_translation_missing_is_a_system_exit_subclass():
    """fail-loud：缺翻譯必須中止腳本（非 0 exit），不是印個警告就略過。"""
    assert issubclass(SEED.TranslationMissing, SystemExit)


def test_legacy_seed_note_cites_the_adr_section():
    """legacy_seed 的側表記錄必須留得住「為什麼不覆核」的線索。"""
    assert "1.2c" in SEED.LEGACY_SEED_NOTE


# ══════════════════════════════════════════════════════════════════
# S3：缺漏收集與延後報告（`raise_if_missing`），免 DB 純函式測試
# ══════════════════════════════════════════════════════════════════

def test_raise_if_missing_is_a_noop_when_nothing_missing():
    """S3：沒有缺漏就不該拋——這條若紅，代表 `main()` 就算灌值全部成功也會
    以非 0 結束，CI 會把「一切正常」誤報成失敗。"""
    stats = SEED.SeedStats()
    SEED.raise_if_missing(stats)  # 不拋例外即通過


def test_raise_if_missing_raises_with_every_missing_entry_listed():
    """S3：缺翻譯不再讓整條 seed 在第一筆就中止——`raise_if_missing` 必須把
    `stats.missing` 的每一條都列進例外訊息，讓人一次看到全部缺漏，不用重跑
    N 次才把 N 個缺漏一個個挖出來。"""
    stats = SEED.SeedStats(missing=["g/ut_a（中文來源 'A'）不在翻譯表中", "x/ut_b（中文來源 'B'）不在翻譯表中"])
    with pytest.raises(SEED.TranslationMissing) as exc_info:
        SEED.raise_if_missing(stats)
    message = str(exc_info.value)
    assert "ut_a" in message
    assert "ut_b" in message
