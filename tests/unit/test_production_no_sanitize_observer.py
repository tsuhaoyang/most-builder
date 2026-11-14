"""生產路徑不得訂閱 `StripDetail` 旁通道（入站防腐層的 sanitize observer）。

## 這在守什麼

`inbound_guard.SanitizeObserver` 的第三個參數是 `list[StripDetail]`——**被剝掉的原文值本身**
（外部可控字串：role 的 `text`／`value`／`unit`、定位不到的 evidence 片語）。它刻意只走
callback，不進 `reasons`／`unresolved`／`routing_reasons`，理由見 `contracts.StripDetail`
的 docstring：那條路會落 DB 並回 API，而它**本來就不乾淨**（S-5 未修），不該再多開一個入口。

合法訂閱者只有評測腳本 `scripts/wi_ai_eval.py`（值只出現在評測報告）。

## ADR-037 之後的形狀

舊版有兩條守衛：(a) 行為——真的走一次 `wi_ai_service._try_llm_plan`，看 adapter 手上有沒有
observer；(b) 靜態——全 `src/` 掃 observer 字面。ADR-037 移除了 MOST 內的 LLM planner，
(a) 失去對象（沒有任何生產路徑會建 adapter）。現在只剩 (b)，並改成掃**兩個字面**：
`SanitizeObserver`（型別名，任何訂閱都得 import 或標註它）、`on_sanitize`（舊參數名，防止
有人照舊寫法重新接回來）與 `StripDetail`（明細型別本身——直接呼叫
`sanitize_planner_output(..., details=...)` 或讀 `parse_sanitize_validate` 第 4 個回傳值的
程式，型別註記或 import 會帶出它；只放行 nlp 內部的定義站與評測模組）。外部 ai_service adapter（實作計畫 S2）落地時，若它要接受 observer，
定義站要加進 `_ALLOWED`，且 `wi_ai_service`／routes／models 仍不得出現。

空跑防護：放行清單過期偵測（放行檔不再含任何 needle＝豁免過期）＋掃描檔數下界＋正向控制
（評測腳本 `scripts/wi_ai_eval.py` 必須仍掃得到 `StripDetail`，needle 拼錯或改名時先在這裡紅）。
⚠️ **已知未保證**：掃描只認字面，`getattr(x, "_on_" + "sanitize")` 這類拼接繞得過。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]

_NEEDLES = ("SanitizeObserver", "on_sanitize", "StripDetail")
# 放行：nlp 內部的定義站與評測模組（不是生產呼叫端）。
#   contracts.py   — `StripDetail` 定義、`sanitize_planner_output(details=...)`
#   inbound_guard.py — `SanitizeObserver` 定義、`parse_sanitize_validate`
#   planner_eval.py — 評測報告的明細序列化
_ALLOWED = {
    "ddm_v2/nlp/contracts.py",
    "ddm_v2/nlp/inbound_guard.py",
    "ddm_v2/nlp/planner_eval.py",
}
# 正向控制：合法訂閱者（評測腳本）必須掃得到
_LEGITIMATE_SUBSCRIBER = Path("scripts") / "wi_ai_eval.py"
# 掃描規模下界——掉到三位數以下代表掃錯目錄
_MIN_SCANNED_FILES = 100


def test_no_production_module_mentions_the_sanitize_observer():
    """全 `src/` 掃：除了定義站，沒有生產模組可以提到 observer。"""
    scanned = sorted(p for p in (ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts)
    assert len(scanned) >= _MIN_SCANNED_FILES, (
        f"只掃到 {len(scanned)} 個 .py（下界 {_MIN_SCANNED_FILES}）——掃描範圍壞了，這條守衛會恆綠"
    )
    offenders = sorted(
        f"{p.relative_to(ROOT / 'src')}:{needle}"
        for p in scanned
        if str(p.relative_to(ROOT / "src")) not in _ALLOWED
        for needle in _NEEDLES
        if needle in p.read_text(encoding="utf-8")
    )
    assert offenders == [], (
        f"這些生產模組的檔案內容**提到**了 sanitize observer：{offenders}。"
        "⚠️ 本檢查是純字面子字串比對，**註解與 docstring 也算命中**。"
        "真的掛上去請拆掉（observer 只給評測，`StripDetail`＝被剝除的外部原文值）；"
        "只是提到的話請把名字拆開寫。"
    )


def test_allowlisted_files_still_need_the_exemption():
    """放行清單只准指向真的需要豁免的檔；檔案搬走／不再提到任何 needle 要在這裡紅。"""
    for rel in sorted(_ALLOWED):
        path = ROOT / "src" / rel
        assert path.exists(), f"放行清單指向不存在的檔：{rel}"
        text = path.read_text(encoding="utf-8")
        assert any(n in text for n in _NEEDLES), f"放行清單裡的 {rel} 已不含任何 needle＝豁免過期，請移除"
    assert "SanitizeObserver" in (ROOT / "src" / "ddm_v2/nlp/inbound_guard.py").read_text(encoding="utf-8"), (
        "`SanitizeObserver` 已不在 inbound_guard.py——定義站搬家了，先更新本檔"
    )


def test_scanner_finds_the_legitimate_subscriber():
    """正向控制：沒有這條，needle 一改名就變成掃不到任何東西的恆綠斷言，而且看起來更綠。"""
    path = ROOT / _LEGITIMATE_SUBSCRIBER
    assert path.exists(), f"{_LEGITIMATE_SUBSCRIBER} 不存在——正向控制失去對象"
    assert "StripDetail" in path.read_text(encoding="utf-8"), (
        f"`StripDetail` 在 {_LEGITIMATE_SUBSCRIBER} 找不到：型別可能改名了。先更新本檔的 needle。"
    )
