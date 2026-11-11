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

## 2026-08-19 的近失（near-miss）：本守衛漏放了一次真實違規，故擴大兩個維度

實作 `M_COMPANION_WITHOUT_VERB` 時，有人（DRY 清理）把 `wi_ai_service._option_labels()`
——一份**刻意重複的純中文** label map——換成 `providers.build_label_map()`。那條路徑是
`wi_ai_service` → `most_compiler/engine_gate.py` → `compute_cycle`，**決定 TMU**。
改動當下 unit 1159 ＋ integration 533 ＋ 黃金 174 **全綠**，本守衛也全綠。兩個原因疊加：

1. **覆蓋面**：`_guarded_py_files()` 只掃 `nlp/`＋2 個檔，`most_compiler/` 與
   `wi_ai_service.py` 都不在內。
2. **穿透性**：即使掃了 `wi_ai_service.py` 也抓不到——違規的字面是
   `build_label_map(opts)`，`label_en` 三個字**在 `providers.py` 裡**，不在被掃的檔案裡。
   純欄位名 grep 看不穿函式邊界。

因此本檔守四件事：

1. **欄位名**（`FORBIDDEN_FIELD_NAMES`）——整檔字面 grep。
2. **載體符號**（`FORBIDDEN_EN_CARRIERS`：回傳值可原樣當 labels map、且帶 `_en` 的 helper）。
   載體清單不是憑印象列的——`test_carrier_list_really_carries_en_fields` 會用 `ast` 取出
   **該函式自己**的原始碼回頭檢查它確實還帶 `_en`（避免清單腐爛）。
3. **範本比對的引數供應端**——守住計分器沒有用，關鍵字是呼叫端挑的
   （`score_keywords(desc, keywords + [t.name_en])` 一個字都沒動計分器，卻改變範本命中
   → 改變 `computed_tmu`）。收斂成 `template_matching.score_template(desc, 範本物件)`，
   呼叫端不得自組關鍵字清單。
4. **執行期不變式**（`most_compiler/engine_gate._assert_no_en_fields`）——字面 grep 守不住
   間接取用（`getattr(providers, "build_label" + "_map")(opts)` 穿透以上全部），
   所以引擎入口另外檢查**實際傳進來的資料形狀**。

1–3 是字面/AST 掃描（可能誤殺，寧可人工複查）；4 是承重防線（`raise`，不是 `assert`，
因為 `python -O` 會拿掉 `assert`）。
"""
from __future__ import annotations

import ast
import copy
import pathlib

import pytest

from ddm_v2.most_compiler.engine_gate import EnFieldInTmuPath, apply_engine_gate

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[2]

# I3 明文點名的三個守衛對象：nlp/ 整個目錄（含子目錄 prompts/）、
# template_matching.py（範本關鍵字比對，決定套用哪個範本 → 決定 TMU）、
# synonym_service.py（同義詞登記，決定 parser 選哪個 option code → 決定 TMU）。
_NLP_DIR = _REPO / "src" / "ddm_v2" / "nlp"
_TEMPLATE_MATCHING = _REPO / "src" / "ddm_v2" / "services" / "v2" / "template_matching.py"
_SYNONYM_SERVICE = _REPO / "src" / "ddm_v2" / "services" / "v2" / "synonym_service.py"
# 2026-08-19 擴大（見檔頭近失）：AI parser 的落地路徑同樣決定 TMU——
# `wi_ai_service` 組 labels → `most_compiler/engine_gate.py` → `compute_cycle`。
_MOST_COMPILER_DIR = _REPO / "src" / "ddm_v2" / "most_compiler"
_WI_AI_SERVICE = _REPO / "src" / "ddm_v2" / "services" / "v2" / "wi_ai_service.py"
_PROVIDERS = _REPO / "src" / "ddm_v2" / "most_engine" / "providers.py"
# 範本比對的**引數供應端**（2026-08-19 補）：守住計分器不夠，關鍵字是呼叫端挑的。
# `import_service` 現況零 `_en` 命中 → 可整檔納入；`motion_template.py` 自身有合法的
# `name_en`（CRUD 欄位），整檔掃會誤殺，改用下面的函式層級 AST 守衛。
_IMPORT_SERVICE = _REPO / "src" / "ddm_v2" / "services" / "v2" / "import_service.py"
_MOTION_TEMPLATE_ROUTE = _REPO / "src" / "ddm_v2" / "api" / "routes" / "v2" / "motion_template.py"
# 比對路徑上、但不整檔掃的檔案：它們只准呼叫 `score_template(description, 範本物件)`，
# 不准自己組關鍵字清單（關鍵字來源收斂在 `template_matching.template_keywords()`）。
_SCORER_CALLERS: tuple[pathlib.Path, ...] = (
    _REPO / "src" / "ddm_v2" / "nlp" / "linking.py",
    _IMPORT_SERVICE,
    _MOTION_TEMPLATE_ROUTE,
)

# 4 個 `_en` 欄位（7 張選項表的 label_en、詞彙/範本的 name_en、Phase C 的
# sentence_text_en、narrative_en）——即使後三者這輪還沒有資料，欄位名一旦出現
# 在守衛對象的原始碼裡就代表有人在讀它，一律視為違規。
FORBIDDEN_FIELD_NAMES: tuple[str, ...] = (
    "label_en",
    "name_en",
    "sentence_text_en",
    "narrative_en",
)


# `_en` 的**載體**：回傳值**能原樣當 labels map 用**、且該 map 裡帶 `_en` 的 helper。
# 守衛對象呼叫它們＝間接把 `_en` 餵進敘事/引擎路徑，純欄位名 grep 看不見（近失的第 2 個原因）。
#
# 加新載體的判準（兩條都成立才收）：
#   (a) 回傳值裡會出現 `_en` 鍵/屬性；且
#   (b) 回傳值**可以直接當 labels map 傳給下游**，中間沒有必經的投影層。
# 為什麼要 (b)：`providers.load_options_from_db()` 完全符合 (a)（選項清單本來就含 `_en`），
# 但它**不是**載體——它回的是選項清單，還要再過一層轉換才能當 labels 用，而
# `wi_ai_service._option_labels()` 就是那層轉換：**逐鍵白名單**投影，只挑
# `label`/`sentence`/`display_rule`/`pricing_kind`，把 `_en` 投影掉。這才是那條路徑安全的
# 唯一理由（不是因為 `load_options_from_db` 乾淨）。把它收進清單只會誤殺正當呼叫端。
FORBIDDEN_EN_CARRIERS: tuple[tuple[str, pathlib.Path], ...] = (
    ("build_label_map", _PROVIDERS),
)


def _guarded_py_files() -> list[pathlib.Path]:
    files = sorted(_NLP_DIR.rglob("*.py"))
    assert files, f"{_NLP_DIR} 找不到任何 .py 檔——路徑本身可能已經漂移，守衛形同虛設"
    compiler = sorted(_MOST_COMPILER_DIR.rglob("*.py"))
    assert compiler, f"{_MOST_COMPILER_DIR} 找不到任何 .py 檔——守衛對象的路徑已經漂移"
    files += compiler
    for f in (_TEMPLATE_MATCHING, _SYNONYM_SERVICE, _WI_AI_SERVICE, _IMPORT_SERVICE):
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


def _scan_carriers(files: list[pathlib.Path]) -> list[tuple[pathlib.Path, str]]:
    """回傳 (檔案, 命中的載體符號) 的清單；空清單＝乾淨。"""
    hits: list[tuple[pathlib.Path, str]] = []
    for f in files:
        if f in {src for _name, src in FORBIDDEN_EN_CARRIERS}:
            continue  # 載體的定義檔本身不算違規
        text = f.read_text(encoding="utf-8")
        for name, _src in FORBIDDEN_EN_CARRIERS:
            if name in text:
                hits.append((f, name))
    return hits


def _function_code(path: pathlib.Path, func_name: str) -> str | None:
    """`def {func_name}` 的**可執行碼**（找不到 → None）：不含註解、不含 docstring。

    兩層都是必要的：

    - **切到函式**：整檔 `read_text()` 對「某個函式是否還帶 `_en`」是**恆真**的斷言——
      同檔別的函式（`providers.load_options_from_db`）合法地帶 `_en`。
    - **去掉 docstring／註解**：只切函式仍然不夠。實測把 `build_label_map` 裡的
      `"label_en"`／`"sentence_en"` 兩個鍵整行刪掉，該函式的 docstring 還寫著
      「共用同一份 entry（`label`/`sentence` ＋ `label_en`/`sentence_en`）」——
      光看原始碼片段仍然命中，斷言照樣恆真。`ast.unparse` 天然丟掉註解，
      docstring 則明確剝掉（含巢狀函式的）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            target = copy.deepcopy(node)
            for sub in ast.walk(target):
                if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                first = sub.body[0] if sub.body else None
                if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    sub.body = sub.body[1:] or [ast.Pass()]
            return ast.unparse(target)
    return None


def test_i3_no_en_field_reads_in_tmu_determining_paths():
    """主守衛：`nlp/` ＋ `most_compiler/` ＋ `template_matching.py` ＋ `synonym_service.py`
    ＋ `wi_ai_service.py` ＋ `import_service.py` 現況必須乾淨。"""
    hits = _scan(_guarded_py_files())
    assert hits == [], (
        "I3 違反——以下檔案讀到了 `_en` 欄位名（決定 TMU 的路徑不得依賴未經覆核的機器"
        f"翻譯）：{[(str(f.relative_to(_REPO)), field) for f, field in hits]}"
    )


def test_i3_no_en_carrier_calls_in_tmu_determining_paths():
    """同一批檔案不得呼叫**會帶入 `_en` 的 helper**——欄位名 grep 看不穿函式邊界。

    這條就是 2026-08-19 近失漏掉的那一維：`wi_ai_service.py` 改用
    `providers.build_label_map()` 時，`label_en` 三個字仍然只出現在 `providers.py`，
    上一版守衛（純欄位名 grep）不可能命中。
    """
    hits = _scan_carriers(_guarded_py_files())
    assert hits == [], (
        "I3 違反——以下檔案呼叫了會把 `_en` 帶進 labels 的 helper（決定 TMU 的路徑必須"
        "自組純中文 label map，例如 `wi_ai_service._option_labels()`）："
        f"{[(str(f.relative_to(_REPO)), name) for f, name in hits]}"
    )


def test_carrier_list_really_carries_en_fields():
    """後設守衛：`FORBIDDEN_EN_CARRIERS` 的每個載體，**該函式自己的**原始碼含 `_en` 欄位。

    沒有這條，載體清單就是一串沒有根據的魔法字串：哪天 `build_label_map()` 不再帶
    `_en`（或被改名／搬家），上一條測試會繼續無償地紅（或無償地綠），而沒有人知道
    它守的前提已經不成立。

    **必須切到函式粒度**（2026-08-19 修）：上一版掃的是整個 `providers.py`，而同檔的
    `load_options_from_db()` 永遠含 `_en` → 斷言恆真。實測把 `build_label_map` 裡的
    `label_en`／`sentence_en` 兩行整段刪掉，這條仍然綠——它宣稱要防的「清單腐爛」
    正好是它偵測不到的那一種。
    """
    for name, src in FORBIDDEN_EN_CARRIERS:
        assert src.is_file(), f"載體 {name} 的定義檔 {src} 不存在——路徑已漂移"
        code = _function_code(src, name)
        assert code is not None, f"{src} 裡找不到 `def {name}`——載體已改名或搬家"
        assert any(field in code for field in FORBIDDEN_FIELD_NAMES), (
            f"{name} 的**可執行碼**裡已經沒有任何 `_en` 欄位（docstring 提到不算）——它不再是載體，"
            "請把它移出 FORBIDDEN_EN_CARRIERS（否則守的是一個不存在的前提）"
        )


def test_guarded_file_list_is_not_accidentally_empty():
    """後設守衛：確保 `_guarded_py_files()` 真的掃得到東西（斷言不會恆真地綠）。"""
    files = _guarded_py_files()
    assert len(files) >= 10, f"只掃到 {len(files)} 個檔案，`nlp/` 的路徑疑似漂移"
    names = {f.name for f in files}
    assert {"lexicon.py", "template_matching.py", "synonym_service.py",
            "engine_gate.py", "wi_ai_service.py", "import_service.py"} <= names


# ══════════════════════════════════════════════════════════════════
# 範本比對：守「引數供應端」，不只守計分器
# ══════════════════════════════════════════════════════════════════
def test_scorer_callers_do_not_build_their_own_keyword_lists():
    """比對路徑的呼叫端只准傳範本物件，不准自組關鍵字清單。

    守住 `score_keywords` 沒有用——關鍵字是**呼叫端挑的**，
    `score_keywords(desc, list(t.keywords or []) + [t.name_en or ""])` 會改變範本命中
    → 改變 `computed_tmu`，而計分器本身一個字都沒動。所以關鍵字來源收斂進
    `template_matching.template_keywords()`，呼叫端一律走 `score_template(desc, 範本)`。
    """
    offenders = []
    for f in _SCORER_CALLERS:
        assert f.is_file(), f"{f} 不存在——比對路徑的呼叫端已漂移，請更新本測試"
        text = f.read_text(encoding="utf-8")
        if "score_keywords" in text:
            offenders.append(str(f.relative_to(_REPO)))
    assert offenders == [], (
        "以下檔案直接呼叫（或提及）低階計分器 `score_keywords`——比對路徑的呼叫端只准用 "
        f"`score_template(description, 範本物件)`，關鍵字來源不得由呼叫端決定：{offenders}"
    )


def test_match_endpoint_function_does_not_touch_en_fields():
    """`motion_template.py` 的比對端點**函式本體**不得出現 `_en` 欄位。

    這檔不能整檔掃：`_out()` 等 CRUD serializer 合法地讀 `name_en`（純顯示）。
    但比對端點是決定 TMU 的路徑，函式層級零容忍。
    """
    code = _function_code(_MOTION_TEMPLATE_ROUTE, "match_templates")
    assert code is not None, "找不到 `match_templates`——比對端點已改名或搬家，請更新本測試"
    bad = [field for field in FORBIDDEN_FIELD_NAMES if field in code]
    assert bad == [], (
        f"I3 違反——`match_templates()` 裡出現 {bad}：範本比對決定套用哪個範本、"
        "進而決定 computed_tmu，不得依賴未經覆核的機器翻譯"
    )


def test_function_scoped_scan_is_not_fooled_by_the_rest_of_the_file(tmp_path):
    """反向對照：函式層級掃描不得被同檔**其他**函式的合法 `_en`、或被 docstring／註解騙。

    後兩者不是假想：`build_label_map` 的 docstring 本來就寫著 `label_en`，
    所以「取函式原始碼片段」這個做法仍然是恆真的斷言——必須連 docstring 一起剝掉。
    """
    fake = tmp_path / "fake_route.py"
    fake.write_text(
        "def _out(t):\n    return {'name_en': t.name_en}\n\n"
        "def match_templates(p, t):\n    return score(p, t)\n\n"
        "def only_mentions_it(o):\n"
        "    \"\"\"回傳 label_en 用的 entry。\"\"\"\n"
        "    return {'label': o.get('label')}   # 不含 label_en\n",
        encoding="utf-8",
    )
    assert "name_en" in _function_code(fake, "_out")
    assert "name_en" not in _function_code(fake, "match_templates")
    assert "label_en" not in _function_code(fake, "only_mentions_it"), "docstring／註解不算"
    assert _function_code(fake, "no_such_function") is None


# ══════════════════════════════════════════════════════════════════
# 執行期不變式：呼叫端寫法再怎麼繞，帶 `_en` 的 labels 就是進不了引擎路徑
# ══════════════════════════════════════════════════════════════════
def test_engine_gate_rejects_labels_carrying_en_fields():
    """`apply_engine_gate(labels=...)` 收到帶 `_en` 的 entry 必須當場炸。

    字面 grep 守不住間接取用：
    `getattr(providers, "build_label" + "_map")(opts)` 讓上面所有掃描器全綠，
    英文欄照樣進到 `apply_engine_gate`。這條改守**資料形狀**，與呼叫端怎麼寫無關。
    """
    with pytest.raises(EnFieldInTmuPath) as exc:
        apply_engine_gate([], object(), labels={"g": {"g_grasp": {"label": "抓握", "label_en": "grasp"}}})
    assert "label_en" in str(exc.value) and "g/g_grasp" in str(exc.value)


def test_engine_gate_accepts_the_legitimate_zh_only_label_map():
    """反向對照：`wi_ai_service._option_labels()` 形狀（逐鍵白名單投影）照常通過。"""
    lab = {"g": {"g_grasp": {"label": "抓握", "sentence": "抓握", "display_rule": None, "pricing_kind": None}},
           "m": {"m_hand": {"label": "手度", "sentence": None, "display_rule": None, "pricing_kind": "hand"}}}
    assert apply_engine_gate([], object(), labels=lab) == []
    assert apply_engine_gate([], object(), labels=None) == []


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
