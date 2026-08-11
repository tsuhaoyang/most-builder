"""每一筆 seed 範本都必須能用 **V2 認證字典** 算得出來（ADR-014 值權威 / ADR-024 §3-2）。

範本的 `cycle_template` 不帶 `rule_set_code`——套用時一律解析 active rule-set，
現行 active＝`MINIMOST_FACTORY_V2`。所以「範本裡出現只存在於 V1 的 option code」
不是相容性問題，是**這筆範本恆定算不出來**：

- 匯入預覽（`import_service.preview` 對每個範本試算）→ `computed_tmu: null` + error，
  前端判定不可採用；
- 繞過 UI 直接採用（落地路徑的 `compute_cycle` 不在 try 內）→ 整份匯入 500。

實際發生過：「掃描/檢查」用 V1 的 `x_scan`（V2 已改名分家為 x_scan_bar/ppid/wo）
→ `SequenceError [X_UNKNOWN]`。既有資料由 migration v2_0035 修補，產生源由本測試守住。
直接跑腳本裡的真實定義，不另抄一份樣本。
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from ddm_v2.most_engine import SequenceError, build_from_seed_v2, compute_cycle
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_templates.py"


def _load():
    spec = importlib.util.spec_from_file_location("_dev_seed_templates_v2", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SEED = _load()
RS_V2 = build_from_seed_v2()


def _compute(payload: dict) -> float:
    """走與 import_service 完全相同的路徑：dict → CycleIn → engine。"""
    return compute_cycle(cycle_in_to_engine(CycleIn.model_validate(payload)), RS_V2).total_tmu


@pytest.mark.parametrize("name_zh", [t[0] for t in SEED.TEMPLATES])
def test_seed_template_computes_under_v2_dictionary(name_zh):
    """逐筆：V2 字典下算得出 TMU，且不為 None。"""
    cyc = next(t[5] for t in SEED.TEMPLATES if t[0] == name_zh)
    tmu = _compute(SEED.dump_cycle_template(cyc))
    assert tmu is not None, f"{name_zh} 算不出 TMU"


def test_scan_template_uses_v2_scan_code():
    """釘住修正本身：掃描範本的 X 碼在 V2 字典裡（不是 V1 的 x_scan）。"""
    cyc = next(t[5] for t in SEED.TEMPLATES if t[0] == "掃描/檢查")
    x_code = SEED.dump_cycle_template(cyc)["x4"]["x_code"]
    assert x_code in RS_V2.x_options, f"{x_code} 不在 V2 認證字典的 X 選項裡"
    assert x_code == "x_scan_bar", "通用「掃描」取條碼版（PPID／工單二維碼語意較窄）"


def test_guard_has_teeth_v1_only_code_is_rejected():
    """具鑑別力：把 X 碼換回 V1 的 x_scan 就必須爆——否則上面的測試只是同義反覆。"""
    cyc = next(t[5] for t in SEED.TEMPLATES if t[0] == "掃描/檢查")
    payload = SEED.dump_cycle_template(cyc)
    payload["x4"] = {**payload["x4"], "x_code": "x_scan"}
    with pytest.raises(SequenceError) as e:
        _compute(payload)
    assert e.value.code == "X_UNKNOWN"
