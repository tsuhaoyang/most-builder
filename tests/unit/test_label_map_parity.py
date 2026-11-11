"""兩份 label map builder 的**刻意重複**必須維持同構（ADR-032 I3 的配套測試）。

系統裡有兩支把 rule-set 選項清單轉成敘事層 labels 的函式：

| 函式 | 用途 | 為什麼不能合併 |
|---|---|---|
| `most_engine.providers.build_label_map` | worksheet／motion module 的**讀寫路徑**（中英雙語敘事） | — |
| `services.v2.wi_ai_service._option_labels` | AI parser 的落地路徑 → `most_compiler/engine_gate.py` → `compute_cycle` | 那是**決定 TMU 的路徑**，不得帶入 `_en`（ADR-032 I3，違反即否決） |

重複是刻意的，但重複的代價是**漂移**：加一個中文側的敘事鍵（例如 D7.6 的 `pricing_kind`）
只改一邊，AI 路徑的敘事就會靜默落後，而 TMU 完全正確、沒有任何測試會紅。
本檔把「兩邊在**中文側**必須同構、且 AI 側**不得**有英文鍵」釘成可機械驗證的斷言。

（誰不准呼叫誰，由 `tests/unit/test_i18n_en_field_isolation.py` 的載體守衛擋；
本檔管的是分家之後兩邊的形狀。）
"""
from __future__ import annotations

import pytest

from ddm_v2.most_engine.providers import build_label_map
from ddm_v2.services.v2.wi_ai_service import _option_labels

pytestmark = pytest.mark.unit

# 中文側鍵集合＝兩套敘事樣板真正會讀的鍵（`narrative.py` / `narrative_en.py` 檔頭的契約）。
ZH_SIDE_KEYS = {"label", "sentence", "display_rule", "pricing_kind"}
EN_SIDE_KEYS = {"label_en", "sentence_en"}

# `load_options_from_db()` 回傳形狀的最小合成品：每個參數一列，欄位齊全。
OPTS = {
    "g": [{"code": "g_grasp", "label": "抓握", "sentence": "抓握",
           "label_en": "Grasp", "sentence_en": "grasp"}],
    "p_bases": [{"code": "p_hold", "label": "保持住", "sentence": "保持住",
                 "label_en": "Hold in place", "sentence_en": "hold it in place"}],
    "p_addons": [{"code": "a_hard", "label": "較難處理", "sentence": "",
                  "label_en": "Difficult to handle", "sentence_en": "",
                  "display_rule": "hidden"}],
    "m_verbs": [{"code": "m_push", "label": "推", "sentence": "推", "pricing_kind": "ladder",
                 "label_en": "Push", "sentence_en": "push it"},
                {"code": "m_hand", "label": "手度", "sentence": None, "pricing_kind": "hand",
                 "label_en": "Hand turn", "sentence_en": ""}],
    "x": [{"code": "x_none", "label": "無機台等待", "sentence": None,
           "label_en": "No machine wait", "sentence_en": ""}],
    "i": [{"code": "i_none", "label": "不額外對齊", "sentence": None,
           "label_en": "No additional alignment", "sentence_en": ""}],
}
PARAMS = ("g", "p_base", "p_addon", "m_verb", "x", "i")


def test_both_builders_cover_the_same_parameters():
    """參數層級同構：少一個參數＝該格的敘事整段消失（AI 草稿最容易靜默落後的形狀）。"""
    assert set(build_label_map(OPTS)) == set(_option_labels(OPTS)) == set(PARAMS)


@pytest.mark.parametrize("param", PARAMS)
def test_zh_side_keys_are_identical(param):
    """中文側鍵完全一致——`build_label_map` 加一個中文敘事鍵就必須同步加到 AI 側。"""
    a = build_label_map(OPTS)[param]
    b = _option_labels(OPTS)[param]
    assert set(a) == set(b), f"{param}: 兩邊的 code 集合不同"
    for code in a:
        zh_a = {k: v for k, v in a[code].items() if k in ZH_SIDE_KEYS}
        assert zh_a == b[code], (
            f"{param}/{code}: 中文側形狀漂移。`_option_labels` 是刻意的重複"
            "（ADR-032 I3：AI 落地路徑不得帶 `_en`），但中文側必須跟著 "
            "`build_label_map` 走，否則 AI 草稿的敘事會靜默落後"
        )


def test_zh_side_key_set_matches_what_the_templates_read():
    """`ZH_SIDE_KEYS` 不是憑印象列的：它必須正好是 `build_label_map` 扣掉英文欄的那組。

    少了這條，上面的比對會退化成「拿 A 的子集跟 B 比」——`build_label_map` 新增一個
    中文鍵時，`ZH_SIDE_KEYS` 沒跟著加就會讓那個鍵**不被比對**，漂移照樣溜過去。
    """
    keys = set(build_label_map(OPTS)["m_verb"]["m_push"])
    assert keys - EN_SIDE_KEYS == ZH_SIDE_KEYS, (
        f"`build_label_map` 的非英文鍵是 {sorted(keys - EN_SIDE_KEYS)}，"
        f"但本檔比對的是 {sorted(ZH_SIDE_KEYS)}——請同步更新 ZH_SIDE_KEYS 與 `_option_labels`"
    )


@pytest.mark.parametrize("param", PARAMS)
def test_ai_path_carries_no_english_keys(param):
    """I3 的形狀面：AI 落地路徑的 labels **不得**出現任何英文鍵。

    載體守衛擋的是「呼叫了誰」，這條擋的是「產出長什麼樣」——就算有人手抄一份
    帶 `_en` 的 map 進 `_option_labels`（不呼叫任何載體），這條照樣會紅。
    """
    for code, entry in _option_labels(OPTS)[param].items():
        assert not (set(entry) & EN_SIDE_KEYS), f"{param}/{code} 帶了英文鍵：{sorted(entry)}"
