"""生產路徑不得訂閱 `StripDetail` 旁通道（`LLMPlannerAdapter(on_sanitize=…)`）。

## 這在守什麼

`on_sanitize` 的第三個參數是 `list[StripDetail]`——**被剝掉的原文值本身**（模型可控
字串：role 的 `text`／`value`／`unit`、定位不到的 evidence 片語）。它刻意只走 callback，
不進 `reasons`／`unresolved`／`routing_reasons`，理由見 `contracts.StripDetail` 的
docstring：那條路會落 DB 並回 API，而它**本來就不乾淨**（S-5 未修），不該再多開一個入口。

唯一合法的訂閱者是評測腳本 `scripts/wi_ai_eval.py`（值只出現在評測報告）。生產路徑
（`services/v2/wi_ai_service.py`）掛上去，等於把被剝除的原文值送進非預期路徑。

## 措辭要準

被擋的是**發送**不是**收集**：`_parse_sanitize_validate` 一律建 `details` 並傳進
sanitize，`_observe` 只在 `_on_sanitize is None` 時 no-op，值隨區域變數丟棄。
（`LLMPlannerAdapter.__init__` 的 docstring 對這點有更正過的說明。）

## 兩條互補的守衛

1. **行為**（`test_production_planner_is_built_without_observer`）：真的走一次
   `_try_llm_plan`，看那顆 adapter 手上有沒有 observer。守的是**現在這個呼叫點**。
2. **靜態**（`test_no_production_module_mentions_on_sanitize`）：全 `src/` 掃 `on_sanitize`
   字面，只放行定義它的 `nlp/llm_planner.py`。守的是**任何新開的呼叫點**，包含
   `planner._on_sanitize = f` 這種繞過建構子的寫法（`_on_sanitize` 含同一子字串）。

靜態掃描的空跑防護：正向控制釘住 `scripts/wi_ai_eval.py` **必須**掃得到（needle 拼錯或
參數改名時先在這裡紅），外加掃描檔數下界。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ddm_v2.nlp.contracts import ParseContext
from ddm_v2.nlp.llm_planner import LLMPlannerAdapter
from ddm_v2.services.v2 import wi_ai_service

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]

_NEEDLE = "on_sanitize"
# 定義站：型別別名 `SanitizeObserver`、建構子參數、`_observe` 的閘門都在這一檔。
_ALLOWED = {"ddm_v2/nlp/llm_planner.py"}
# 合法訂閱者（正向控制：掃描器抓不到它＝needle 已失效，涵蓋率是假的）
_LEGITIMATE_SUBSCRIBER = Path("scripts") / "wi_ai_eval.py"
# 掃描規模下界——`find src -name '*.py'` 當下 138 檔；掉到三位數以下代表掃錯目錄
_MIN_SCANNED_FILES = 100


async def test_production_planner_is_built_without_observer(monkeypatch):
    """`_try_llm_plan` 造出來的 adapter 手上不得有 observer。

    連 `on_sanitize=None` 顯式傳入也一併擋掉：那會讓「生產不訂閱」看起來像是可調的
    參數，而它是不變式。
    """
    seen: dict[str, Any] = {}
    real_init = LLMPlannerAdapter.__init__

    def spy_init(self, client, **kwargs):  # type: ignore[no-untyped-def]
        real_init(self, client, **kwargs)
        seen["kwargs"] = dict(kwargs)
        seen["observer"] = self._on_sanitize

    async def fake_plan(self, normalized_text, context):  # type: ignore[no-untyped-def]
        # 只驗建構參數；真的打 LLM 不是本測試的事（也不該有 HTTP）
        return "PLAN_SENTINEL", "RAW_SENTINEL"

    monkeypatch.setattr(LLMPlannerAdapter, "__init__", spy_init)
    monkeypatch.setattr(LLMPlannerAdapter, "plan", fake_plan)

    out = await wi_ai_service._try_llm_plan(
        normalized_text="取螺絲起子鎖螺絲",
        context=ParseContext(rule_set_code="MINIMOST_FACTORY_V2"),
        timeout_s=1.0,
    )

    assert out == ("PLAN_SENTINEL", "RAW_SENTINEL"), "spy 沒被走到＝下面的斷言是空跑"
    assert "kwargs" in seen, "`_try_llm_plan` 沒有建 LLMPlannerAdapter＝這條守衛失去對象"
    assert _NEEDLE not in seen["kwargs"], (
        f"生產路徑把評測旁通道掛上去了：{sorted(seen['kwargs'])}。"
        "`StripDetail` 帶的是被剝除的原文值（模型可控字串），只給評測腳本訂閱——"
        "見 nlp/contracts.py 的 StripDetail docstring。"
    )
    assert seen["observer"] is None, (
        f"adapter 的 `_on_sanitize` 不是 None（實際 {seen['observer']!r}）"
    )


def test_default_planner_has_no_observer():
    """不傳就是不訂閱——把預設值改成任何非 None 的東西，這條紅。"""
    planner = LLMPlannerAdapter(client=object())  # type: ignore[arg-type]
    assert planner._on_sanitize is None


def test_no_production_module_mentions_on_sanitize():
    """全 `src/` 掃：除了定義站，沒有生產模組可以提到 `on_sanitize`。"""
    scanned: list[Path] = sorted(p for p in (ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts)
    assert len(scanned) >= _MIN_SCANNED_FILES, (
        f"只掃到 {len(scanned)} 個 .py（下界 {_MIN_SCANNED_FILES}）——掃描範圍壞了，"
        "這條守衛會恆綠"
    )
    offenders = sorted(
        str(p.relative_to(ROOT / "src"))
        for p in scanned
        if _NEEDLE in p.read_text(encoding="utf-8")
        and str(p.relative_to(ROOT / "src")) not in _ALLOWED
    )
    assert offenders == [], (
        f"這些生產模組的檔案內容**提到**了 `{_NEEDLE}`：{offenders}。"
        "⚠️ 本檢查是純字面子字串比對，**註解與 docstring 也算命中**——所以這不一定"
        "代表真的訂閱了，也可能只是有人寫了一句「這裡刻意不掛它」。"
        "兩種情形的處置不同：真的掛上去請拆掉（sanitize observer 是**只給評測**的"
        "旁通道，`StripDetail` ＝被剝除的原文值，模型可控字串，生產路徑訂閱等於把它們"
        "送進非預期路徑）；只是提到的話請把那個名字拆開寫"
        "（先例：`wi_ai_service.py` 模組 docstring 的 `on_` ＋ `sanitize`）。"
    )


def test_scanner_finds_the_legitimate_subscriber():
    """正向控制：唯一合法訂閱者必須掃得到。

    沒有這條，`on_sanitize` 一改名（或 needle 拼錯）上面那條就變成掃不到任何東西的
    恆綠斷言，而且**看起來還更綠**。
    """
    path = ROOT / _LEGITIMATE_SUBSCRIBER
    assert path.exists(), f"{_LEGITIMATE_SUBSCRIBER} 不存在——正向控制失去對象"
    assert _NEEDLE in path.read_text(encoding="utf-8"), (
        f"`{_NEEDLE}` 在 {_LEGITIMATE_SUBSCRIBER} 找不到：參數可能改名了。"
        "先更新本檔的 needle，再確認生產掃描仍然有效。"
    )


def test_allowlisted_definition_site_still_defines_it():
    """放行清單只准指向真的定義它的檔；檔案搬走／改名要在這裡紅，不是靜默放行。"""
    for rel in sorted(_ALLOWED):
        path = ROOT / "src" / rel
        assert path.exists(), f"放行清單指向不存在的檔：{rel}"
        assert _NEEDLE in path.read_text(encoding="utf-8"), (
            f"放行清單裡的 {rel} 已不含 `{_NEEDLE}`＝這筆豁免過期，請移除"
        )
