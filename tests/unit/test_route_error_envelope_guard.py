"""ADR-034 §D6 CI 守衛（階段 A5）：擋新的裸 `HTTPException` 進 route 層。

ADR-034 D5 階段 A 完成判準之一：「grep 無裸 `HTTPException(detail=...)` 於 route 層」，
D6 明文要求「CI 守衛：擋新的裸 `HTTPException(detail=...)` 進 route 層（回歸到多信封）」。
A1–A4 已把 route 層 145 處裸 `HTTPException` 收斂進 `DomainError` 信封
（`api/error_handlers.py` 產出統一的 `{error:{code,message,detail}}`），只剩**一處**合理保留。

**為什麼用 AST 而不是純字面 grep**：route 層仍有兩種「HTTPException 字樣」不是違規——
`motion_module.py` 的 `from fastapi import ..., HTTPException` import 行，以及 `rule_set.py`
的 docstring 裡「取代裸 `HTTPException`」這句說明。純 grep 會誤報這兩者；AST 只認**真正的
`raise HTTPException(...)` 語句節點**（`ast.Raise` 且 exc 是 `HTTPException(...)` 呼叫），
天然略過 import、docstring、註解與字串字面值。

**白名單為什麼綁「檔案 + 狀態碼 501」而不是行號**：行號會隨上下游編輯漂移，寫死行號的
白名單遲早指向錯的一行（要嘛誤放真違規、要嘛誤殺）。狀態碼 501（Not Implemented）是
`motion_module.py::promote_module` 這個**端點尚未實作**的路由級佔位——不是 domain 錯誤
契約的一環（無對應 `DomainError` 家族），所以是唯一合理保留的裸 `HTTPException`。用
「檔名 + status_code==501」當白名單條件，語意穩定且不隨行號漂移。

**後設守衛（`test_...whitelisted_raise_is_still_a_501_placeholder`）**：比照
`test_i18n_en_field_isolation.py::test_carrier_list_really_carries_en_fields` 的精神——
白名單不是一串沒有根據的魔法字串，必須有一條測試回頭斷言「被白名單那處確實仍是 501」。
哪天那個 promote placeholder 被真正實作（改回 DomainError 或換狀態碼），白名單就該隨之
移除；沒有這條後設測試，白名單會變成一個永遠放行、卻不再對應任何真實情況的盲區。

**mutation 防恆綠（`test_scanner_detects_a_synthetic_bare_raise` 等）**：用 `tmp_path`
合成違規 / 乾淨 / docstring-only 檔案跑 `_bare_http_raises()`，證明掃描器本身不是恆真的
空清單斷言，且不會被 docstring/註解裡的 `HTTPException` 字樣騙。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[2]
_ROUTES_DIR = _REPO / "src" / "ddm_v2" / "api" / "routes"

# 白名單：唯一合理保留的裸 `HTTPException`——`motion_module.py::promote_module` 的
# 501 Not Implemented 路由級佔位（端點尚未實作、非 domain 錯誤契約，無對應 DomainError 家族）。
# 條件刻意綁「檔名 + 狀態碼」而非行號（行號會漂移）。
_WHITELIST_FILENAME = "motion_module.py"
_WHITELIST_STATUS = 501


def _status_code_of(call: ast.Call) -> int | None:
    """從 `HTTPException(...)` 呼叫節點取出 `status_code`（取不到常數→None）。

    支援關鍵字 `status_code=<int常數>` 與第一個位置引數（FastAPI 的
    `HTTPException(status_code, detail=...)` 簽名）。非整數常數（變數、表達式）回 None，
    因為白名單只認得穩定的整數狀態碼。
    """
    for kw in call.keywords:
        if kw.arg == "status_code" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
            return kw.value.value
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, int):
            return first.value
    return None


def _is_http_exception_call(node: ast.expr) -> bool:
    """節點是否為 `HTTPException(...)` 呼叫（含 `fastapi.HTTPException(...)` 屬性寫法）。"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "HTTPException"
    if isinstance(func, ast.Attribute):
        return func.attr == "HTTPException"
    return False


def _bare_http_raises_in_source(source: str) -> list[tuple[int, int | None]]:
    """回傳單檔內所有 `raise HTTPException(...)` 的 (行號, status_code) 清單。

    只認 `ast.Raise` 且 exc 是 `HTTPException(...)` 呼叫的節點——import 行、docstring、
    註解、字串字面值裡的 `HTTPException` 字樣一律不算（AST 天然略過）。
    """
    tree = ast.parse(source)
    hits: list[tuple[int, int | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None and _is_http_exception_call(node.exc):
            assert isinstance(node.exc, ast.Call)  # narrow for type-checkers
            hits.append((node.lineno, _status_code_of(node.exc)))
    return hits


def _route_py_files() -> list[pathlib.Path]:
    files = sorted(_ROUTES_DIR.rglob("*.py"))
    assert files, f"{_ROUTES_DIR} 找不到任何 .py 檔——route 層路徑可能已漂移，守衛形同虛設"
    return files


def _is_whitelisted(path: pathlib.Path, status_code: int | None) -> bool:
    """白名單判定：`motion_module.py` 的 501 promote placeholder。"""
    return path.name == _WHITELIST_FILENAME and status_code == _WHITELIST_STATUS


# ══════════════════════════════════════════════════════════════════
# 主守衛
# ══════════════════════════════════════════════════════════════════
def test_no_new_bare_http_exception_in_route_layer():
    """route 層不得新增裸 `raise HTTPException(...)`——一律走 DomainError 信封（ADR-034 A/D6）。

    唯一放行：`motion_module.py` 的 501 promote placeholder（見檔頭與白名單常數）。
    """
    offenders: list[tuple[str, int, int | None]] = []
    for path in _route_py_files():
        for lineno, status in _bare_http_raises_in_source(path.read_text(encoding="utf-8")):
            if _is_whitelisted(path, status):
                continue
            offenders.append((str(path.relative_to(_REPO)), lineno, status))
    assert offenders == [], (
        "ADR-034 違反——route 層出現新的裸 `raise HTTPException(...)`（會繞過 DomainError "
        "統一信封 `{error:{code,message,detail}}`，回歸多信封並存）。請改 `raise` 對應的 "
        "DomainError 家族（NotFoundError/ValidationError/ConflictError/ForbiddenError/…）："
        f"{offenders}"
    )


# ══════════════════════════════════════════════════════════════════
# 後設守衛：白名單不腐爛（比照 test_carrier_list_really_carries_en_fields 精神）
# ══════════════════════════════════════════════════════════════════
def test_whitelisted_raise_is_still_a_501_placeholder():
    """斷言被白名單的那處**確實仍是** `motion_module.py` 的 501 裸 `HTTPException`。

    沒有這條，白名單就是一串沒有根據的放行條件：哪天 promote placeholder 被真正實作
    （收斂進 DomainError 或改狀態碼），主守衛會靜默地少放行一處該紅的違規（若又冒出別的
    501）、或這個白名單永遠對應不到任何真實情況卻沒人知道。判準比照
    `test_i18n_en_field_isolation.py::test_carrier_list_really_carries_en_fields`：
    白名單指向的前提必須被回頭驗證仍然成立。
    """
    target = _ROUTES_DIR / "v2" / _WHITELIST_FILENAME
    assert target.is_file(), f"{target} 不存在——白名單目標檔已搬家/改名，請更新本測試與白名單常數"
    raises = _bare_http_raises_in_source(target.read_text(encoding="utf-8"))
    whitelisted = [(ln, st) for ln, st in raises if st == _WHITELIST_STATUS]
    assert len(whitelisted) == 1, (
        f"{_WHITELIST_FILENAME} 裡 status_code==501 的裸 `HTTPException` 應恰為 1 處"
        f"（promote placeholder），實際找到 {len(whitelisted)} 處：{whitelisted}。"
        "若 promote 端點已被實作，請一併移除白名單常數與本測試。"
    )


def test_route_file_list_is_not_accidentally_empty():
    """後設守衛：確保 `_route_py_files()` 真的掃得到東西（斷言不會恆真地綠）。"""
    files = _route_py_files()
    names = {f.name for f in files}
    assert len(files) >= 10, f"只掃到 {len(files)} 個 route 檔案，路徑疑似漂移"
    # 已知一定存在的幾支 route（含白名單目標檔），漂移即紅。
    assert {"motion_module.py", "rule_set.py", "vocab.py"} <= names


# ══════════════════════════════════════════════════════════════════
# mutation：證明掃描器真的會抓到違規，不是恆真的空清單，也不被 docstring 騙
# ══════════════════════════════════════════════════════════════════
def test_scanner_detects_a_synthetic_bare_raise():
    """合成一段真正的 `raise HTTPException(...)` → 掃描器必須命中並取出狀態碼。"""
    src = (
        "from fastapi import HTTPException\n"
        "def h():\n"
        "    raise HTTPException(status_code=400, detail='x')\n"
    )
    hits = _bare_http_raises_in_source(src)
    assert hits == [(3, 400)]


def test_scanner_reads_positional_status_code():
    """FastAPI `HTTPException(status_code, detail=...)` 位置引數也要讀得到狀態碼。"""
    src = "def h():\n    raise HTTPException(501, detail='y')\n"
    assert _bare_http_raises_in_source(src) == [(2, 501)]


def test_scanner_not_fooled_by_docstring_or_comment_or_import():
    """反向對照：import 行、docstring、註解、字串字面值裡的 `HTTPException` 字樣**不算違規**。

    這正是 `rule_set.py:337` 那句 docstring「取代裸 `HTTPException`」不得被誤報的原因，
    也是本守衛用 AST 而非純 grep 的理由。
    """
    src = (
        "from fastapi import HTTPException\n"
        "def h():\n"
        "    \"\"\"取代裸 HTTPException，改走 raise HTTPException(...) 的 DomainError。\"\"\"\n"
        "    x = 'raise HTTPException(status_code=400)'  # raise HTTPException 只是字串\n"
        "    return x\n"
    )
    assert _bare_http_raises_in_source(src) == []


def test_whitelist_predicate_only_matches_motion_module_501(tmp_path):
    """白名單斷言：只有 `motion_module.py` 的 501 被放行；同狀態碼在別檔、或同檔別狀態碼都不放行。"""
    mm = _ROUTES_DIR / "v2" / _WHITELIST_FILENAME
    other = _ROUTES_DIR / "v2" / "vocab.py"
    assert _is_whitelisted(mm, 501) is True
    assert _is_whitelisted(mm, 400) is False           # 同檔、非 501 → 不放行
    assert _is_whitelisted(other, 501) is False         # 別檔、501 → 不放行
    assert _is_whitelisted(other, 400) is False
    assert _is_whitelisted(mm, None) is False           # 取不到狀態碼 → 不放行（保守）
