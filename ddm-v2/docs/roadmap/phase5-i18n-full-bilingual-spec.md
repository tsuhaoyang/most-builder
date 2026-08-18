# Phase 5：全面多語系（中文 / 英文）

**狀態：** ⛔ **已被取代（superseded）**——2026-08-18 起請改看
[ADR-032：雙語 UI 與資料標籤層](../decisions/ADR-032-bilingual-ui-and-data-label-layer.md)。
本文件保留供追溯，**不得再被當作實作依據**：ADR-032 §1.1 逐表實測證明本文件
〈現況（已有的一半基礎）〉一節與事實不符（欄位存在但值全空，不是「已有基礎」），
且 ADR-032 對語言來源、翻譯權威、儲存位置、覆核治理等本文件列為「待決」的問題
都已有明確裁決（見該 ADR 全文，尤其 D1–D9）。

**狀態（原）：** 🔄 roadmap 草案（尚未實作）
**日期：** 2026-06-21
**關聯：** [../architecture/frontend-data-flow-spec.md](../architecture/frontend-data-flow-spec.md)、[../architecture/data-model-and-storage-spec.md](../architecture/data-model-and-storage-spec.md)

## 目標

整套系統**全面支援中文 / 英文**：UI、資料標籤、敘事、匯出、錯誤訊息皆可雙語，使用者可切換語言。

## 現況（已有的一半基礎）

- 詞彙 `work_vocab_items.name_zh` / `name_en`（已有欄）。
- rule-set 選項表（B/G/P/M/X/I…）有 `label_zh` / `label_en`（已有欄）。
- 敘事(`narrative`) 目前**只中文**（`most_engine/narrative.py`）。
- 前端 React 元件仍有中文硬編字串，尚未導入統一 i18n catalog。
- 錯誤訊息：domain 例外 message 中英混。

## 範圍（要做的）

### 1. 前端 UI 字串外部化 + 語言切換
- 把硬編中文抽成 **i18n 資源**（zh/en key→value）；元件以 key 取字串。
- 頂部加**語言切換**；偏好存 localStorage / 使用者設定。
- vanilla 階段：簡單 `t(key)` + 字典；React 遷移用 i18n 框架（react-i18next）。

### 2. 後端敘事雙語
- `build_narrative` 產 **zh + en** 兩版（或依請求語言）；用 rule-set `label_en` + vocab `name_en` + 英文 HAND_NAMES/句型模板。
- 儲存：`most_cycles.narrative_zh` + 新增 `narrative_en`（加法 migration）。

### 3. 資料標籤 _en 補齊
- 確保 vocab、rule-set 選項、動作範本（`motion_templates` 加 `name_en`？）的 `_en` 有值；主數據/範本 UI 可編雙語。

### 4. 匯出雙語
- Excel/CSV 表頭、METHOD 欄依語言；或同時出雙語欄。

### 5. 錯誤訊息 / API i18n
- domain 例外與驗證訊息走 message catalog（zh/en）；API 依 `Accept-Language` 或 `?lang=` 回對應語言。

## 設計原則

- **語言是呈現層的事，不是邏輯**：TMU/Level/規則不因語言而異；i18n 只影響字串與標籤。
- **加法演進**（ADR-011）：新增 `_en` 欄與 catalog，不破壞既有 `_zh`。
- **單一真相**：每個可譯字串只有一個 key；不散落重複翻譯。
- **fallback**：缺 en 時回 zh（反之亦然），不顯示空白。

## 待決

- 語言來源：使用者偏好(app_users 加 `locale`?) vs 瀏覽器 `Accept-Language` vs 兩者。
- 敘事英文句型模板的語序（與中文不同）。
- 是否需要更多語系（目前只 zh/en；架構預留可擴）。

## 影響的 skill / 檔

[[frontend-workbench]]（字串外部化、切換）、[[backend-v2]]（敘事/錯誤 i18n）、[[database-v2]]（`narrative_en`、`locale` 加法 migration）、[[integration-lb-import]]（匯出雙語）。
