"""版控同義詞詞典（`scripts/dev_seed_synonyms.py`）的表格形狀守門（D3-030 B1）。

這 22 條決定 parser 會把哪個詞面掛到哪個 option code、option code 決定 TMU——
所以「表格本身」要有守門：**每條都指得出 IE 裁決輪次**（沒有裁決引用的相似性
判斷不得混進來，ADR-023 §3.3 規則 1 補節二），**鍵不得重複**（重複＝seed 第二
條必撞 UNIQUE），**同一詞面掛多個 code 時 priority 必須不同**（撞 priority 會被
`create_synonym` 以 409 擋下，seed 會整支炸；語意上則是 parser 靜默擇一，D3-018 H1）。

免 DB：直接讀腳本裡的真實定義，不另抄一份樣本。
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_synonyms.py"


def _load():
    spec = importlib.util.spec_from_file_location("_dev_seed_synonyms", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SEED = _load()
_D3_RE = re.compile(r"D3-\d{3}")


def test_seed_dictionary_is_pinned_at_22():
    """筆數釘值：增減都要有意識更新（每一條都是一次 IE 裁決）。"""
    assert len(SEED.SYNONYMS) == 22


def test_every_row_cites_an_ie_ruling():
    """逐條必須指得出輪次（D3-NNN）與答案內容——空字串/佔位符不算。"""
    for parameter, option_code, raw, _priority, ruling in SEED.SYNONYMS:
        assert isinstance(ruling, str) and len(ruling.strip()) >= 10, (
            f"{parameter} {raw} → {option_code}：缺可追溯的裁決引用"
        )
        assert _D3_RE.search(ruling), f"{parameter} {raw} → {option_code}：裁決引用要指得出輪次"


def test_rows_are_unique_by_the_db_unique_key():
    """(parameter, synonym_norm, option_code) 不得重複——UNIQUE 鍵（rule_set 固定一個）。"""
    from ddm_v2.nlp.normalization import normalize

    keys = [
        (p, normalize(raw), code) for p, code, raw, _prio, _r in SEED.SYNONYMS
    ]
    assert len(set(keys)) == len(keys), "詞典有重複鍵"


def test_multi_code_faces_declare_distinct_priority():
    """同一 (parameter, synonym_norm) 掛多個 code 時，priority 必須互異。

    撞 priority ＝ `create_synonym` 的 SynonymPriorityCollision（D3-018 H1）：
    seed 會直接爆；語意上則是 parser tie-break 按 option_code 字母序靜默擇一、
    不標 review——TMU 錯了也沒人知道。現況唯一的多 code 面是「放至/放置」→
    p_place_single(0)／p_place_none(1)（D3-017 情境變體）。
    """
    from ddm_v2.nlp.normalization import normalize

    by_face: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for parameter, code, raw, priority, _r in SEED.SYNONYMS:
        by_face.setdefault((parameter, normalize(raw)), []).append((code, priority))
    multi = {face: v for face, v in by_face.items() if len(v) > 1}
    assert multi, "多 code 面消失了？D3-017 的方向變體是刻意設計，請確認是否為預期"
    for face, variants in multi.items():
        prios = [p for _c, p in variants]
        assert len(set(prios)) == len(prios), (
            f"{face}：多個 code 撞同一 priority {prios}——偏好序必須顯式宣告"
        )


def test_synonym_raw_is_already_normalized():
    """登記的原文正規化後不得為空，且與正規化結果一致（詞典是中文動詞面，
    不該夾帶全形/空白差異——否則 DB 的 synonym_raw 與 norm 會不同步）。"""
    from ddm_v2.nlp.normalization import normalize

    for parameter, code, raw, _prio, _r in SEED.SYNONYMS:
        norm = normalize(raw)
        assert norm, f"{parameter} {raw} → {code}：正規化後為空"
        assert norm == raw, f"{parameter} {raw} → {code}：原文與正規化結果不一致（{norm}）"
