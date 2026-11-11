"""dev_seed_templates 的 cycle_template 產出不得帶 rule_set_code（ADR-024 §3-2）。

migration v2_0022 把既有 16 筆 DB 資料裡寫死的 MINIMOST_FACTORY_V1 拔掉了，
但**產生源**若沒同步改，重跑 seed（或在新環境首次 seed）就會把 key 加回去，
造成新舊環境不一致——那正是這次要根治的問題形態。
本測試直接跑腳本裡的 16 筆真實定義，不另抄一份樣本。
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_templates.py"


def _load():
    spec = importlib.util.spec_from_file_location("_dev_seed_templates", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SEED = _load()


def test_all_seed_templates_omit_rule_set_code():
    """16 筆定義逐筆檢查：dump 後不含 rule_set_code key。"""
    assert len(SEED.TEMPLATES) == 16, "範本筆數變動，請確認是否為預期"
    for name_zh, _en, _cat, _seq, _kws, cyc in SEED.TEMPLATES:
        payload = SEED.dump_cycle_template(cyc)
        assert "rule_set_code" not in payload, f"{name_zh} 的 cycle_template 仍帶 rule_set_code"


def test_seed_templates_keep_everything_else():
    """具鑑別力：排除的只有 rule_set_code，其餘 slot 一個都不能少。"""
    for name_zh, _en, _cat, _seq, _kws, cyc in SEED.TEMPLATES:
        full = cyc.model_dump(mode="json")
        payload = SEED.dump_cycle_template(cyc)
        assert set(full) - set(payload) == {"rule_set_code"}, f"{name_zh} 掉了其他欄位"
        for k, v in payload.items():
            assert full[k] == v, f"{name_zh} 的 {k} 被改動"


def test_no_seed_template_mentions_legacy_v1():
    """整份 payload 不得出現任何 MINIMOST_* 字樣。"""
    for name_zh, _en, _cat, _seq, _kws, cyc in SEED.TEMPLATES:
        assert "MINIMOST" not in str(SEED.dump_cycle_template(cyc)), f"{name_zh} 仍寫死版本代碼"


@pytest.mark.parametrize("seq_kind", ["GM", "CM"])
def test_seed_covers_both_seq_kinds(seq_kind):
    """兩種 seq 都有樣本被上述檢查涵蓋（避免只驗到單一分支）。"""
    assert any(t[3] == seq_kind for t in SEED.TEMPLATES)
