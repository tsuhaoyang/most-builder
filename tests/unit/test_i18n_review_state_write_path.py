"""M2（2026-08-18 第二輪複審）：`i18n_review_state` 的「唯一寫入路徑」假設守衛。

`i18n_service.py` 的檔頭與 `upsert_review_state` docstring 都宣稱
`upsert_review_state` 是 `I18nReviewState` 的唯一寫入路徑——但這個假設本身沒有
任何東西在守，`tests/integration/test_i18n_review_state.py` 就已經直接
`I18nReviewState(...)` 建構繞過它（刻意的，為了測 DB CHECK 約束本身，見該檔案的
「DB CHECK 不變式」小節）。

**grep／AST 型測試**：用 `ast` 找 `I18nReviewState(...)` 的建構呼叫（不是
`class I18nReviewState(Base):` 這種類別定義——兩者字面上都含 `I18nReviewState(`，
純文字 grep 會誤判，改用 AST 精準區分 Call 節點與 ClassDef 節點），確認只出現在
`i18n_service.py`（唯一寫入路徑本身）或白名單測試檔（明確標注理由的例外）。

**L-3（2026-08-18 第三輪複審）：掃描範圍加入 `migrations/`**——先前只掃
`src/`／`scripts/`／`tests/`，手寫 migration 若直接 `I18nReviewState(...)`
灌資料（例如 data migration）會完全不在守衛視野內。`v2_0040_i18n_review_state.py`
（建表的那支 migration）本身用純 SQL／`op.execute`，不會被誤判，加進掃描範圍
後仍是乾淨的，見 `test_write_path_file_itself_is_not_accidentally_empty` 同類的
後設守衛精神——這裡沒有另外加一條，因為 `migrations/` 目前沒有任何合法的
建構呼叫，不需要「確認守衛真的掃到東西」的後設測試（`test_scanner_detects_a_
synthetic_violation` 已經用 `tmp_path` 直接證明掃描器本身抓得到違規，不依賴
`migrations/` 目錄現況）。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_SCRIPTS = _REPO / "scripts"
_TESTS = _REPO / "tests"
_MIGRATIONS = _REPO / "migrations"

_TARGET = "I18nReviewState"

# 唯一合法的寫入路徑本身。
_ALLOWED_FILES = {
    _SRC / "ddm_v2" / "services" / "v2" / "i18n_service.py",
}

# 白名單例外（測試檔）：`test_i18n_review_state.py` 的「DB CHECK 不變式」小節
# 刻意直接建構 `I18nReviewState(...)` 繞過 `upsert_review_state`——目的是驗證
# DB 層的 CHECK 約束（entity_type/field/locale/source 列舉、`source='human'` 時
# `reviewed_by` 必填、UNIQUE 鍵）本身就算應用層驗證被繞過也擋得住，這是防禦深度
# 測試，理應繞過唯一寫入路徑，不是誤用它。
_ALLOWED_TEST_FILES = {
    _TESTS / "integration" / "test_i18n_review_state.py",
}


def _constructor_call_lines(path: pathlib.Path) -> list[int]:
    """回傳這個檔案裡 `I18nReviewState(...)` 建構呼叫所在的行號（空清單＝乾淨）。

    用 AST 而非純文字 grep：`class I18nReviewState(Base):` 字面上也含
    `I18nReviewState(`，純文字掃描會把類別定義本身誤判成一次違規呼叫。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == _TARGET:
            lines.append(node.lineno)
    return lines


def _all_py_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for base in (_SRC, _SCRIPTS, _TESTS, _MIGRATIONS):
        files.extend(sorted(base.rglob("*.py")))
    assert files, (
        f"{[_SRC, _SCRIPTS, _TESTS, _MIGRATIONS]} 掃不到任何 .py 檔——路徑疑似漂移，守衛形同虛設"
    )
    return files


def test_i18n_review_state_constructor_is_confined_to_the_single_write_path():
    violations: list[tuple[str, list[int]]] = []
    for f in _all_py_files():
        if f in _ALLOWED_FILES or f in _ALLOWED_TEST_FILES:
            continue
        lines = _constructor_call_lines(f)
        if lines:
            violations.append((str(f.relative_to(_REPO)), lines))
    assert violations == [], (
        "I18nReviewState(...) 建構子呼叫只准出現在 i18n_service.py（唯一寫入路徑）"
        f"或白名單測試檔（DB CHECK 防禦深度測試）：{violations}"
    )


def test_write_path_file_itself_is_not_accidentally_empty():
    """後設守衛：`i18n_service.py` 本身確實有一次建構（不是恆真的空清單斷言）。"""
    for f in _ALLOWED_FILES:
        assert f.is_file(), f"{f} 不存在——唯一寫入路徑的路徑本身已經漂移"
        assert _constructor_call_lines(f), f"{f} 找不到任何 I18nReviewState(...) 建構——掃描器可能失效"


def test_whitelisted_test_file_actually_uses_the_exception():
    """後設守衛：白名單測試檔確實有繞過寫入路徑的建構（否則白名單是多餘的，
    應該收回，讓守衛範圍維持最小）。"""
    for f in _ALLOWED_TEST_FILES:
        assert f.is_file(), f"{f} 不存在——白名單條目已經漂移，應更新或收回"
        assert _constructor_call_lines(f), (
            f"{f} 找不到任何 I18nReviewState(...) 建構——白名單條目已經沒有存在理由，應收回"
        )


# ══════════════════════════════════════════════════════════════════
# mutation：證明掃描器真的會抓到違規，不是恆真的空清單
# ══════════════════════════════════════════════════════════════════

def test_scanner_detects_a_synthetic_violation(tmp_path):
    fake = tmp_path / "fake_rule_option_service.py"
    fake.write_text(
        "from ddm_v2.models.v2.i18n import I18nReviewState\n"
        "def sneaky(session):\n"
        "    row = I18nReviewState(id=1)\n"
        "    session.add(row)\n",
        encoding="utf-8",
    )
    assert _constructor_call_lines(fake) == [3]


def test_scanner_does_not_flag_the_class_definition_itself(tmp_path):
    """反向對照：`class I18nReviewState(Base):` 不是一次建構呼叫，不得被誤殺
    （否則守衛加嚴到連 model 定義檔自己都會紅）。"""
    fake = tmp_path / "fake_models.py"
    fake.write_text(
        "class I18nReviewState(Base):\n    __tablename__ = 'i18n_review_state'\n",
        encoding="utf-8",
    )
    assert _constructor_call_lines(fake) == []
