# F-01：MOST 工作台——序列編輯器（可執行功能規格）

> 分類：功能 ｜ 相依：[CL-01](../core-logic/CL-01-sequence-model-and-tmu.md)、[CL-02](../core-logic/CL-02-sentence-generation.md) ｜ 證據：[api-inventory-workbench](../reference/api-inventory-workbench.md) §routes/most.py、[frontend-usage-flows](../reference/frontend-usage-flows.md) §B1
> 使用者故事：IE 以「選模型→填語境→逐格選項→即時看 TMU 與句子→儲存」的迴圈，把一個動作標準化成一條可重用的序列。

## 1. 行為規則

1. **編輯迴圈**：任何 slot/context/hand/frequency 變更 → debounce（400ms）呼叫試算 API → 顯示每格 TMU、合計、系統句。試算**無副作用**。
2. **Slot 編輯器（modal）**按參數呈現：A＝三分量（reach/twist/foot 物理量輸入→顯示分級與 max 公式）；B/G/I＝單選；P＝base＋modifiers（UI 即時強制 ≤2 與 insert⊥snap，後端仍重驗）；M＝verb＋hand＋foot；X＝選項＋條件式秒數輸入（seconds_source=user_input_seconds 時必填 >0）；G/P/M/X/I 支援 repeat_count（1–99）。
3. **模型切換遷移**：保留 A1/B1/G/A3＋context，清空對方獨有格。預設值/推斷（如 B2 預設眼部動作）**由後端 options 的 is_default／建議規則提供**，前端只渲染並標 badge（DISC-06：不得前端寫死值）。
4. **句子**：顯示系統句（後端組，CL-02）；IE 可改為人工句（雙欄，系統不覆寫人工句）。前端不自組句（DISC-07）。
5. **儲存**：一條序列＝模型＋hand＋context＋slot_inputs＋frequency＋句子雙欄；儲存時後端重算並落快照與值版本參照。清單支援搜尋、拖拉排序、頻率直編、SIMO 配對標記（CL-04 §2）、編輯/複製/刪除。

## 2. API 合約（v2 落地路徑；請求只含 code＋物理量——DISC-02）

| Method | Path | 目的 |
|---|---|---|
| GET | /api/v2/rule-sets/{code}/options | 工作台選項（含 is_default、vision_scope、sentence_text_zh） |
| POST | /api/v2/minimost/calculate | 試算單列（無副作用；回每格 TMU＋合計＋tech_line＋系統句） |
| PUT/GET | /api/v2/worksheets/{id} | 儲存/讀取（列集合含 cycle+level_entry，既有合約） |

（v3 實況對照：POST /most/calculate-row、POST/PATCH /most/sequences——其 selections 夾帶 tmu_value，v2 不沿用。）

## 3. 驗證與錯誤

CL-01 全套錯誤碼（422）＋ frequency>0＋repeat 1–99＋X 條件秒數。前端驗證僅為 UX，後端為權威。

## 4. 驗收條件

- Given GM 黃金輸入（CL-01 §5），When 試算，Then 28 TMU 且句子含「抓握…放」。
- Given 只改 reach 20→25，Then 僅 A 格 TMU 變（6→10），其餘格不重選。
- Given 模型 GM→CM，Then P/A2/B2 清空、G/A1/B1/A3/context 保留。
- Given user_edited 句存在，When 重算，Then 顯示人工句、系統句於折疊處更新。
- Given X 選壓合機台未填秒數，When 儲存，Then 422 且指明欄位。
