"""範本比對的**關鍵字來源**只有一個：`template_matching.template_keywords()`。

比對命中決定套用哪個範本 → 決定 `computed_tmu`，所以「關鍵字從哪來」與「怎麼比對」
同樣是決定 TMU 的一環（ADR-032 I3）。三個呼叫端（`nlp/linking`、`import_service`、
`/motion-templates/match`）一律傳範本物件，不自組清單——CI 側的守衛在
`test_i18n_en_field_isolation.py`，這裡守的是 helper 自己的行為。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ddm_v2.services.v2.template_matching import score_keywords, score_template, template_keywords

pytestmark = pytest.mark.unit


def test_template_keywords_reads_only_the_keywords_column_orm():
    t = SimpleNamespace(keywords=["鎖螺絲", "screw"], name_zh="鎖附", name_en="Fasten screw")
    assert template_keywords(t) == ["鎖螺絲", "screw"]


def test_template_keywords_reads_only_the_keywords_column_dict():
    """`nlp/linking` 拿到的是投影過的 dict，不是 ORM 列——兩種形狀共用同一支 helper。"""
    t = {"id": "x", "keywords": ["鎖螺絲"], "name_zh": "鎖附", "name_en": "Fasten screw"}
    assert template_keywords(t) == ["鎖螺絲"]


@pytest.mark.parametrize("t", [
    pytest.param(SimpleNamespace(keywords=None), id="orm-none"),
    pytest.param(SimpleNamespace(), id="orm-missing"),
    pytest.param({}, id="dict-missing"),
    pytest.param({"keywords": []}, id="dict-empty"),
])
def test_template_keywords_tolerates_missing_keywords(t):
    assert template_keywords(t) == []


def test_score_template_equals_scoring_the_keywords_column():
    """行為與舊寫法逐字相同——收斂關鍵字來源不改變任何既有命中。"""
    t = SimpleNamespace(keywords=["鎖螺絲", "screw"], name_en="Fasten screw")
    assert score_template("用電動起子鎖螺絲", t) == score_keywords("用電動起子鎖螺絲", ["鎖螺絲", "screw"])


def test_score_template_does_not_match_on_the_english_name():
    """`name_en` 是機器翻譯、未經 IE 覆核：出現在描述裡也不得構成命中（ADR-032 I3）。"""
    t = SimpleNamespace(keywords=["鎖螺絲"], name_zh="鎖附", name_en="fasten")
    score, hits = score_template("fasten the bracket", t)
    assert (score, hits) == (0.0, [])
