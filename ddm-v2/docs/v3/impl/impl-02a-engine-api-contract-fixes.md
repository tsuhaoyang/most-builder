# impl-02a：引擎/API 合約缺口修復（P1 收尾工單）

> **Phase**：P1 收尾 ｜ **來源**：ddm-testing-p1 驗收 gap 盤點（2026-07-05）發現三缺口 ｜ **執行**：ddm-backend-fix agent ｜ **驗收**：ddm-validator
> 本文件是已派工任務的正式規格（工單），validator 以此驗收。三項皆有既定規格依據，無新決策。

## Fix-1：錯誤碼契約統一——REPEAT_INVALID 在 API 層可達

- **問題**：`schemas/v2/most.py` 各 slot `repeat_count` 的 Pydantic `ge=1, le=99` 先於引擎攔截，回 FastAPI 標準 422（detail 為 list），前端拿不到 `{detail:{code:"REPEAT_INVALID"}}`——違反 impl-02 §2 錯誤碼契約。
- **修法**：schema 卸下範圍約束（保留 `int | None` 型別）；**驗證權威唯一＝引擎**（`calculate.py::_repeat`）。單一驗證來源原則（同 DISC-03 精神）。
- **測試**：`tests/integration/test_calculate_v2.py` 原被放寬的斷言改回檢查 `detail.code == "REPEAT_INVALID"`（0／100／1.5 三案）。

## Fix-2：E4 契約——A/B 格 repeat「出現即 422」在 API 層可達

- **問題**：`ASlot`/`BSlot` 無 `repeat_count` 欄＋Pydantic 預設 ignore extra → payload 帶 `a0.repeat_count` 被靜默丟棄、回 200——違反 impl-02 E4「A、B 不支援（出現即 422）」。
- **修法**：`ASlot`/`BSlot` 加 `repeat_count: int | None = None` passthrough 欄（無範圍約束），讓引擎 `_no_repeat` 防線經 API 可達。引擎不改（防線已存在）。
- **測試**：新增整合測試 `a0.repeat_count=2` → 422 `REPEAT_INVALID`。

## Fix-3：CL-01 遺漏移植——X user 秒數 ≤0 → 422（核心邏輯，已授權）

- **問題**：CL-01 §2 X 節（v3 認證驗證「X 動態秒數項目必須輸入正數」）規定 `mode=seconds 且 user_seconds ≤ 0 → 422`；現行引擎對 0／未填回 0 TMU——規格遺漏移植。
- **修法**（協調者授權觸碰 most_engine）：
  1. `most_engine/calculate.py::_x_tmu`：mode=seconds 且 `seconds <= 0` → `SequenceError("X_SECONDS_REQUIRED", ...)`（負值與零的錯誤碼取捨由實作 agent 擇一並在本檔補記）。
  2. 同步獨立規格 `scripts/core_logic/minimost_sequence_validator.py`（同語意；「X 0 秒→0」測試改為 expect_error）。
  3. 同步 `tests/unit/test_most_engine.py` 反例（不動其他斷言）。
  4. 文件連動：impl-02 §2 錯誤碼清單加 `X_SECONDS_REQUIRED`；catalog「V2 重錨過帳表」補一列（新增類）。
  5. V1 回放注意：屬引擎行為全域生效（同 E2 half-up 前例）；歷史 `computed` 快取不重算。

## 完成門檻（validator 驗收基準）

1. `PYTHONPATH=src pytest -q` 全綠（含既有 102＋本工單新增）。
2. `scripts/core_logic/run_all.py` 全綠；`rule_set_seed_v2.py` 自檢全過。
3. 三個錯誤碼（REPEAT_INVALID×API、REPEAT_INVALID×A/B、X_SECONDS_REQUIRED）各有 API 或 unit 層反例測試。
4. 不碰 rule_set_seed*、不 git commit。

## 追蹤殘項（不在本工單）

- F-01「人工句雙欄」「模型切換遷移」＝前端功能未開工（屬 F-01 實作 phase，ddm-frontend）。
- E9 其餘 M 範圍錯誤碼的 API 層測試＝已由代表性 4 碼覆蓋，unit 層全鎖（ddm-testing-p1 判定，接受）。

## 執行結果（agent 回報後由協調者補記）

- [ ] Fix-1 ／ [ ] Fix-2 ／ [ ] Fix-3 ／ [ ] validator PASS
