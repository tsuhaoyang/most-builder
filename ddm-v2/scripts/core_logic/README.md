# 核心邏輯驗證器（Core Logic Validators）

MOST 系統兩個核心概念的**可執行規格 + 自帶測試**。是「核心邏輯驗證 script/skill」的基礎。

| 檔案 | 對應規格 | 內容 |
|------|----------|------|
| [minimost_sequence_validator.py](minimost_sequence_validator.py) | [MiniMOST 核心規格](../../docs/core-logic/minimost-sequence-model-core-logic-spec.md) | MiniMOST GM/CM 七格 TMU 計算（A/B/G/P/M/X/I）+ SIMO/頻率 |
| [level_system_validator.py](level_system_validator.py) | [Level 核心規格](../../docs/core-logic/level-system-core-logic-spec.md) | Level System 填寫合法性 R1–R9（main/sub/cub/nb、深度、變動層級） |

## 跑法

```bash
cd ddm-v2
python3 scripts/core_logic/minimost_sequence_validator.py   # exit 0 = 全綠
python3 scripts/core_logic/level_system_validator.py
```

兩者皆無第三方相依，純 stdlib。exit code 0 = 全部通過，非 0 = 有失敗。

## 設計原則

- **權威來源＝`docs/core-logic/`＋accepted ADR＋IE 認證字典**；`html_con/` 僅為封存 UI 原型。
- 把 **edge case 封死**：非法選項、未勾修飾、超過 2 附加、GM↔CM 結構混用、距離/秒負值、
  歸屬不明、重複定義歸屬、nb 與 cub 矛盾、level 格式/反向範圍、order 跳號/重複… 一律明確報錯（帶錯誤碼）。
- **黃金測試集**：Sequence＝GM 28 TMU / CM 29 TMU；Level＝教學檔案 7 個範例 + image5 三個反例。

## 已知待 IE 確認項（不可硬編，見規格 §14）

C1 機台/人力分攤倍數、C2 深度巢狀>2 編碼、C3 節拍不可行回饋、C4 B 完整選項與選用規則、C5 SIMO 配對 UX。

## 已由驗證器發現的來源筆誤

理解文件把 CM 黃金例的 `M16` 標為「推 30cm」，但 M 階梯 30cm→24（≤18cm 才→16）。驗證器以 18cm 還原 29 TMU 並另測 30cm→24。
