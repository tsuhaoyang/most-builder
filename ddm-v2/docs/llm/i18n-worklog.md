# i18n（雙語 UI）交付追蹤（Worklog）

**文件類型：** 交付追蹤紀錄（單一追蹤入口；不定義規格）
**規格：** [ADR-032：雙語（中／英）支援 — UI 外殼與資料標籤層](../decisions/ADR-032-bilingual-ui-and-data-label-layer.md)
**建立日期：** 2026-08-18
**範圍對照 ADR-032 §D10**：本文件目前只追蹤 **Phase A**（前端 i18n 框架 ＋ UI 外殼字串外部化 ＋
標頭語言切換 ＋ `app_users.locale` ＋ `/me` 帶 locale ＋ `PATCH /me/locale`）。Phase B（資料標籤層）
與 Phase C（敘事英文化）尚未開工，不在本文件範圍。

> 填寫規則（比照 [wi-ai-parser-worklog.md](wi-ai-parser-worklog.md) §20 的精神，本檔案簡化版）：
> - 每一批交付一個 D 編號；狀態、驗證結果、待辦都記在對應的 D 底下。
> - 卡點／複審發現但本批不修 → 記進「待辦清單」，不刪、不改寫歷史。
> - 決策分級：D1 架構級（已有 ADR-032，不重複開）；規格級／實作級差異記本文件。

---

## 1. 批次狀態總覽

| 批次 | 內容 | 狀態 | 完成日 | Checkpoint |
|---|---|---|---|---|
| **D1** | Phase A 第一刀：i18n 框架導入（i18next＋react-i18next）、`zh-TW.ts`／`en.ts` 資源、`LocaleSwitcher`、`useLocaleSync`、`app_users.locale` migration（`v2_0039`）、`/me` 帶 locale、`PATCH /me/locale`、側欄／標頭／`App.tsx` tab-in-progress 文案、共用元件（`ErrorBoundary`／`RuleSetUnavailable`／`WorksheetRequiredNotice`／`ComboBox`）外部化 | `completed`（未 commit，等本批一起走） | 2026-08-18 | 內部複審（非正式 code-review agent，人工/協調者複驗）→ 抓到 3 個必修＋若干待辦 |
| **D2**（本文件記錄的這一批） | **D1 複審修復**：PATCH 失敗無聲＋`<html lang>` 不跟隨語言＋中英 key 對稱無型別保證，三項必修 ＋ 對應 e2e | `completed` | 2026-08-18 | 見 §2、§3 |

**重要標注（commit message 必須帶）**：D1＋D2 合計＝ADR-032 **D10-A 的第一批**（側欄／標頭／共用元件），
**不是 D10-A 的完整交付**。D10-A 的完成判準（ADR-032 表格）是「外殼（側欄 7 項＋admin 2 項、標頭、
按鈕、表頭）無中文殘留」——目前只做了側欄／標頭／共用元件，其餘分頁（見 §4 待辦）仍是中文字面值，
**尚未達成 D10-A 的完成判準**。R4（CI 守衛「新增 `.tsx` 不得含中文字面值」）依 ADR-032 §5 的原文
**順延到 D10-A 收尾時同批交付**，不在 D1／D2 這兩批。

---

## 2. D2 修復清單（本批，2026-08-18）

範圍：`src/frontend/`。不動 `most_engine/`、不動 ADR-032 Phase B／C。

### D2-1 `PATCH /me/locale` 失敗無聲（必修）

- **問題**：`LocaleSwitcher.handlePick` 對 `updateLocale.mutate(locale)` 是 fire-and-forget，
  無 `onError`。PATCH 500 時：畫面已切語言、`localStorage` 已寫入新語言、**零錯誤提示**；
  下次開頁 `/me` 回舊值，`useLocaleSync` 會把畫面與 `localStorage` 都無聲改回去——
  使用者的設定就這樣消失，沒有任何線索。
- **修法**：`updateLocale.mutate(locale, { onError })`——`onError` 回滾 `i18n.changeLanguage(previous)`
  ＋還原 `localStorage` ＋顯示可見錯誤（沿用既有 `ActionModuleWorkspace.tsx`／`WiWorkbench.tsx`
  的 local toast pattern：元件內 state + fixed 定位 + 定時消失，**未新增共用 toast 機制**）。
  錯誤文案走 i18n（`locale.updateFailed`，兩語系同步新增）。
- **檔案**：
  - `src/frontend/src/features/layout/LocaleSwitcher.tsx`（rollback + toast）
  - `src/frontend/src/shared/i18n/resources/zh-TW.ts`／`en.ts`（新增 `locale.updateFailed`）
- **測試**：`e2e/locale-switcher.spec.ts` 新增
  `'failed PATCH /me/locale rolls back the UI and shows a visible error'`——mock PATCH 500，
  斷言畫面回滾中文、`aria-pressed` 回滾、`localStorage`／`<html lang>` 回滾、
  `data-testid="locale-switcher-error"` 可見且文字含「語言偏好更新失敗」。
- **Mutation 證據**：拆掉 `onError` 區塊（改回 `updateLocale.mutate(locale)`）→ build → 該 e2e
  在「畫面回滾回中文」那一斷言 timeout 紅（`getByRole('button',{name:'儀表板'})` 找不到，因為畫面
  停在英文）。還原後重新 build → 綠。未保留在 repo（依驗收要求「不用留在 repo 裡」的同精神處理，
  這裡口頭記錄過程供覆核）。

### D2-2 `<html lang>` 永遠是 `zh-TW`（必修）

- **問題**：`index.html:2` 寫死 `<html lang="zh-TW">`，全 repo 沒有任何地方寫入
  `document.documentElement.lang`，切到英文後 a11y／SEO／瀏覽器拼字檢查等仍讀到 zh-TW。
- **修法**：`i18n.ts` 加 `i18next.on('languageChanged', l => { document.documentElement.lang = l })`
  （在 `init()` 之前掛），並在 `init()` 之後**立即**用 `initialLocale`（而非讀 `i18next.language`，
  避免依賴 init 內部狀態何時就緒）顯式設一次，不等第一次事件觸發。
- **檔案**：`src/frontend/src/shared/i18n/i18n.ts`
- **測試**：`e2e/locale-switcher.spec.ts` 既有測試補三個 `expect.poll(() =>
  document.documentElement.lang)`（首屏 zh-TW／切 en 後 en／切回 zh-TW 後 zh-TW）。
- **Mutation 證據**：拆掉監聽器＋立即設定兩行 → build → e2e 在「切 en 後 `<html lang>` 應為
  en」斷言 timeout 紅（實測 `Expected: "en" / Received: "zh-TW"`）。還原後重新 build → 綠。

### D2-3 中英 key 對稱無型別保證（必修）

- **問題**：`en.ts` 與 `zh-TW.ts` 複審人工複驗過 35/35 對稱，但無型別綁定；漏一個 key 會被
  i18next `fallbackLng` 靜默補中文，CI 全綠但英文介面殘留中文。
- **修法**：`en.ts` 改成 `const en: Widen<typeof zhTW> = {...}`。**不能直接寫
  `const en: typeof zhTW`**——`zh-TW.ts` 用 `as const`，`typeof zhTW` 的每個 leaf 是該中文字串
  本身的字面型別（如 `'切換語言'`），逐字要求英文譯文等於中文字面值不可能通過。`Widen<T>`
  是本批新增的遞迴 mapped type，只保留鍵的形狀、把每個字串 leaf 放寬成 `string`，藏在
  `en.ts` 檔內（未匯出，只有這一個消費點）。
- **檔案**：`src/frontend/src/shared/i18n/resources/en.ts`
- **驗證**：故意刪除 `en.ts` 的 `locale.updateFailed` 一個 key → `npm run typecheck` 報
  `TS2741: Property 'updateFailed' is missing in type '{...}' but required in type '{...}'`
  → 紅。補回 → 綠。未留在 repo（依驗收要求「截圖或貼錯誤訊息即可，不用留在 repo 裡」）。

---

## 3. 驗證結果（D2 完成時，2026-08-18）

```
cd src/frontend
npm run typecheck && npm run typecheck:e2e && npm run build   # 三者皆綠
E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test        # 125 passed（基線 124 + 本批新增 1）
```

```
PYTHONPATH=src .venv/bin/python -m pytest tests/unit -q                          # 884 passed
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m pytest tests/integration -q  # 462 passed, 1 skipped
.venv/bin/python scripts/core_logic/run_all.py                                    # 全綠（GM=28／CM=29 不變）
```

後端數字與本批修復前的基線完全一致——本批只動 `src/frontend/`，符合預期（I1：
`most_engine/` 零改動）。

---

## 4. 待辦清單（複審已發現但本批不處理，下一批處理前不得遺失）

以下項目來自 2026-08-18 對 D1（Phase A 第一刀）的複審，**編號沿用複審原始編號**，
本批（D2）刻意只處理其中的 1/3/4（對照本文件 §2 的 D2-1／D2-2／D2-3）與 8（本文件本身）。
其餘複審發現的內容細節未在本批的任務指示中展開，這裡先占位保留編號，避免下一批交接時遺失：

- **複審第 2 條**：未展開，待下一批處理時由複審記錄補齊內容。
- **複審第 5 條**：未展開，待下一批處理時由複審記錄補齊內容。
- **複審第 6 條**：未展開，待下一批處理時由複審記錄補齊內容。
- **複審第 7 條**：未展開，待下一批處理時由複審記錄補齊內容。
- **複審第 9 條**：未展開，待下一批處理時由複審記錄補齊內容。
- **複審第 11 條**：未展開，待下一批處理時由複審記錄補齊內容。
- **複審第 12 條**：未展開，待下一批處理時由複審記錄補齊內容。
- **`api.d.ts` 拆 commit**：`git status` 顯示 `src/frontend/src/shared/types/api.d.ts` 在本輪工作樹
  有變動（OpenAPI 產物，`npm run gen:api` 產生，**不可手改**）。複審要求這個檔案的變動應與
  D1／D2 的手寫程式碼改動分開一個 commit（避免生成檔案的 diff 淹沒審查）。本批未處理——
  commit 策略由協調者決定。

### 外殼字串外部化剩餘範圍（D10-A 完成判準尚未達成）

- ADR-032 §5 估計全 repo **62 個檔案、約 553 處**中文字面值。D1（第一刀）只做了側欄／標頭／
  共用元件（`AppLayout`／`Sidebar`／`LocaleSwitcher`／`ComboBox`／`ErrorBoundary`／
  `RuleSetUnavailable`／`WorksheetRequiredNotice`／`App.tsx` 的 tab-in-progress 文案）。
  依複審口徑，**外殼仍有 36 檔待抽**（口徑：僅計外殼／共用元件範圍，不含 Phase B 才要動的
  業務資料頁）。
- 本機粗量（`grep -rlP '[\x{4e00}-\x{9fff}]' src --include='*.tsx' --include='*.ts'`，
  排除 `i18n/resources/`）目前仍有 **65 個檔案**含中文字元——這個數字**不能直接當 36 的反證**：
  grep 抓的是任何中文字元（含程式碼註解，中文註解是本專案慣例、不在外部化範圍），
  口徑比複審的「中文字面值」寬。下一批動手前應先對齊口徑再訂清單，不要直接拿這個粗量當任務清單。
- **R4（CI 守衛：新增 `.tsx` 不得含中文字面值）依 ADR-032 §5 明文，順延到 D10-A 收尾時同批交付**，
  不在 D1／D2。理由（ADR-032 §5 原文）：Phase A 期間必然有「一半 key、一半硬編」的中間態，
  太早加守衛會擋到還沒被排進本輪的合法中文（Phase B／C 範圍或尚未輪到的分頁）；
  但也不能拖到外部化全部做完才加，否則新功能會持續硬編中文、外部化永遠追不完——
  所以是「與外部化收尾同批」，不是「無限期延後」。
