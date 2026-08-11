# WI AI Eval Reports

`scripts/wi_ai_eval.py` 輸出目錄（spec §14.3 / §20.1）。

- 檔名：`wi-gold-<UTC timestamp>.json`
- 內容：每筆 gold case 的 pass/fail、routing、TMU 對照與錯誤列表
- 最新一次亦寫 `wi-gold-latest.json`（方便 diff；可入版控）

本目錄以 `.gitkeep` 與 `wi-gold-latest.json` 為起點；歷史報告可選擇性 commit。
