"""I3 CI 守衛（ADR-032）：`_en` 欄位不得滲入任何決定 TMU 的路徑。

ADR-032 I3：「`_en` 不得進入任何決定 TMU 的路徑（引擎、lexicon、同義詞、範本比對）」，
且明文授權「CI 守衛擋 `nlp/`、`template_matching.py`、`synonym_service.py` 讀取任何
`_en` 欄位」。近因（ADR §3 I3 引用）：`motion_templates.keywords` 已經含英文關鍵字
且會決定套用哪個範本、進而決定 TMU，距離「順手把 `name_en` 也加進 keywords」
只差一個提交。

**grep 型測試**：直接掃原始碼字面，不試圖理解語意（同 `docs/CI_GATES.md` 既有的
grep 型守衛慣例，如「`load_rule_set_from_db` 不得出現 `status`/`is_active`
過濾」）。命中即紅，不論是讀取、指派、註解或字串——寧可偶爾誤殺一個無害的字面提及，
也不要漏放一個真正的讀取（I3 的代價是 TMU 錯，不是誤報一次要人工複查）。
"""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[2]

# I3 明文點名的三個守衛對象：nlp/ 整個目錄（含子目錄 prompts/）、
# template_matching.py（範本關鍵字比對，決定套用哪個範本 → 決定 TMU）、
# synonym_service.py（同義詞登記，決定 parser 選哪個 option code → 決定 TMU）。
_NLP_DIR = _REPO / "src" / "ddm_v2" / "nlp"
_TEMPLATE_MATCHING = _REPO / "src" / "ddm_v2" / "services" / "v2" / "template_matching.py"
_SYNONYM_SERVICE = _REPO / "src" / "ddm_v2" / "services" / "v2" / "synonym_service.py"

# 4 個 `_en` 欄位（7 張選項表的 label_en、詞彙/範本的 name_en、Phase C 的
# sentence_text_en、narrative_en）——即使後三者這輪還沒有資料，欄位名一旦出現
# 在守衛對象的原始碼裡就代表有人在讀它，一律視為違規。
FORBIDDEN_FIELD_NAMES: tuple[str, ...] = (
    "label_en",
    "name_en",
    "sentence_text_en",
    "narrative_en",
)


def _guarded_py_files() -> list[pathlib.Path]:
    files = sorted(_NLP_DIR.rglob("*.py"))
    assert files, f"{_NLP_DIR} 找不到任何 .py 檔——路徑本身可能已經漂移，守衛形同虛設"
    for f in (_TEMPLATE_MATCHING, _SYNONYM_SERVICE):
        assert f.is_file(), f"{f} 不存在——守衛對象的路徑已經漂移，請更新本測試"
        files.append(f)
    return files


def _scan(files: list[pathlib.Path]) -> list[tuple[pathlib.Path, str]]:
    """回傳 (檔案, 命中的欄位名) 的清單；空清單＝乾淨。"""
    hits: list[tuple[pathlib.Path, str]] = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for field in FORBIDDEN_FIELD_NAMES:
            if field in text:
                hits.append((f, field))
    return hits


def test_i3_no_en_field_reads_in_tmu_determining_paths():
    """主守衛：`nlp/` ＋ `template_matching.py` ＋ `synonym_service.py` 現況必須乾淨。"""
    hits = _scan(_guarded_py_files())
    assert hits == [], (
        "I3 違反——以下檔案讀到了 `_en` 欄位名（決定 TMU 的路徑不得依賴未經覆核的機器"
        f"翻譯）：{[(str(f.relative_to(_REPO)), field) for f, field in hits]}"
    )


def test_guarded_file_list_is_not_accidentally_empty():
    """後設守衛：確保 `_guarded_py_files()` 真的掃得到東西（斷言不會恆真地綠）。"""
    files = _guarded_py_files()
    assert len(files) >= 10, f"只掃到 {len(files)} 個檔案，`nlp/` 的路徑疑似漂移"
    names = {f.name for f in files}
    assert {"lexicon.py", "template_matching.py", "synonym_service.py"} <= names


# ══════════════════════════════════════════════════════════════════
# mutation：證明掃描器真的會抓到違規，不是恆真的空清單
# ══════════════════════════════════════════════════════════════════
def test_scanner_detects_a_synthetic_violation(tmp_path):
    """在守衛掃描的**同一支函式**上，餵一個帶 `label_en` 的合成檔案 → 必須命中。

    不改動真實原始碼（那件事在驗收時另外手動做一次 mutation，見任務回報）；
    這裡用 `tmp_path` 造一個結構相同的假違規檔案，證明 `_scan()` 本身不是
    恆真的空清單斷言。
    """
    fake = tmp_path / "fake_template_matching.py"
    fake.write_text("def score(t):\n    return t.label_en\n", encoding="utf-8")
    hits = _scan([fake])
    assert hits == [(fake, "label_en")]


def test_scanner_does_not_flag_zh_field_names(tmp_path):
    """反向對照：`label_zh`／`name_zh`／`sentence_text_zh` 是決定 TMU 的正當欄位，
    不得被誤殺（否則守衛加嚴到連引擎自己都會紅）。"""
    clean = tmp_path / "clean.py"
    clean.write_text(
        "def score(t):\n    return t.label_zh + t.name_zh + (t.sentence_text_zh or '')\n",
        encoding="utf-8",
    )
    assert _scan([clean]) == []
