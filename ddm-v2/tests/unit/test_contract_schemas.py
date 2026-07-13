"""P0 合約 schema 單元測試（免 DB）。

涵蓋：
- F-01：PublishRequest rule_set_id / rule_set_code 恰好擇一。
- F-02a：WiSetItemCreate 快照欄 optional 化 + 手動條目名稱必填。

（TMU→秒換算已改讀引擎權威值 version.total_seconds，route 內不再重算，
 原 _tmu_to_seconds 單元測試隨函式刪除。）
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from ddm_v2.schemas.v2.motion_module import PublishRequest
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
