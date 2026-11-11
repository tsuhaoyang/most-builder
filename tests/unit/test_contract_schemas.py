"""P0 合約 schema 單元測試（免 DB）。

涵蓋：
- F-01：PublishRequest rule_set_id / rule_set_code 恰好擇一。
- F-02a：WiSetItemCreate 快照欄 optional 化 + 手動條目名稱必填。
- ADR-032：詞彙名 strip／空白名不得入庫（英文敘事讀取時組句的毒源，見 vocab.py 檔頭）。

（TMU→秒換算已改讀引擎權威值 version.total_seconds，route 內不再重算，
 原 _tmu_to_seconds 單元測試隨函式刪除。）
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from ddm_v2.schemas.v2.motion_module import PublishRequest
from ddm_v2.schemas.v2.vocab import VocabItemIn, VocabPatchIn
from ddm_v2.schemas.v2.wi_set import WiSetItemCreate

_ROW = {
    "hand": "RH",
    "frequency": 1,
    "vocab_refs": {},
    "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V2"},
}


# ── F-01：PublishRequest ─────────────────────────────────────────────

def test_publish_request_accepts_rule_set_id():
    req = PublishRequest(rows=[_ROW], rule_set_id=uuid.uuid4())
    assert req.rule_set_code is None


def test_publish_request_accepts_rule_set_code():
    req = PublishRequest(rows=[_ROW], rule_set_code="MINIMOST_FACTORY_V2")
    assert req.rule_set_id is None


def test_publish_request_rejects_both():
    with pytest.raises(ValidationError):
        PublishRequest(
            rows=[_ROW],
            rule_set_id=uuid.uuid4(),
            rule_set_code="MINIMOST_FACTORY_V2",
        )


def test_publish_request_rejects_neither():
    with pytest.raises(ValidationError):
        PublishRequest(rows=[_ROW])


# ── F-02a：WiSetItemCreate ───────────────────────────────────────────

def test_wi_set_item_template_only_ok():
    """只給 wi_template_id：快照欄全省略也合法（伺服器回填）。"""
    item = WiSetItemCreate(wi_template_id=uuid.uuid4())
    assert item.wi_name_snapshot is None
    assert item.total_tmu_snapshot is None


def test_wi_set_item_manual_requires_name():
    """無 wi_template_id 的手動條目必須有 wi_name_snapshot。"""
    with pytest.raises(ValidationError):
        WiSetItemCreate()


def test_wi_set_item_manual_with_name_ok():
    item = WiSetItemCreate(wi_name_snapshot="手動條目", total_tmu_snapshot=28.0)
    assert item.wi_template_id is None
    assert item.total_tmu_snapshot == 28.0


# ── ADR-032：詞彙名輸入驗證（H-1 根因）───────────────────────────────

# 含全形空白（U+3000）與 nbsp（U+00A0）：`str.strip()` 是 Unicode-aware 的，現行實作
# 擋得住；fixture 只放 ASCII 的話，日後把它收窄成 `.strip(" \t\n")` 這類寫法
# 不會有任何測試變紅，而全形空白正是中文輸入法最容易打出的那一種。
BLANKS = ["   ", "\t", "\n", " \t ", "", "\u3000", "\xa0", "\u3000 \xa0"]


@pytest.mark.parametrize("blank", BLANKS)
def test_vocab_create_rejects_blank_name_zh(blank):
    """純空白的中文名不得入庫——它會讓英文敘事在讀取時組句爆掉（narrative_en._noun）。"""
    with pytest.raises(ValidationError):
        VocabItemIn(kind="object", name_zh=blank)


@pytest.mark.parametrize("blank", BLANKS)
def test_vocab_patch_rejects_blank_name_zh(blank):
    with pytest.raises(ValidationError):
        VocabPatchIn(name_zh=blank)


@pytest.mark.parametrize("blank", BLANKS)
def test_vocab_blank_name_en_normalises_to_none(blank):
    """英文名相反：清掉英文名是合法操作，正規化成 None 讓 `name_en or name_zh` 回退。"""
    assert VocabItemIn(kind="object", name_zh="主板", name_en=blank).name_en is None
    assert VocabPatchIn(name_en=blank).name_en is None


def test_vocab_patch_distinguishes_omitted_from_cleared_name_en():
    """route 靠 model_fields_set 分辨「沒送」與「送了要清空」——正規化後兩者的值都是 None。"""
    assert "name_en" not in VocabPatchIn().model_fields_set
    assert "name_en" in VocabPatchIn(name_en="  ").model_fields_set


def test_vocab_names_are_stripped():
    v = VocabItemIn(kind="object", name_zh=" 主板 ", name_en="  Main board  ", external_code=" X1 ")
    assert (v.name_zh, v.name_en, v.external_code) == ("主板", "Main board", "X1")
    assert VocabPatchIn(name_zh=" 主板 ").name_zh == "主板"


def test_vocab_patch_none_still_means_unchanged():
    """明確給 null 的 name_zh 仍是「不改」（route 照 `is not None` 判），不是驗證錯誤。"""
    assert VocabPatchIn(name_zh=None).name_zh is None
