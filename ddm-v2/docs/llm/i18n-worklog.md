# i18n（雙語 UI）交付追蹤（Worklog）

**文件類型：** 交付追蹤紀錄（單一追蹤入口；不定義規格）
**規格：** [ADR-032：雙語（中／英）支援 — UI 外殼與資料標籤層](../decisions/ADR-032-bilingual-ui-and-data-label-layer.md)
**建立日期：** 2026-08-18
**範圍對照 ADR-032 §D10**：本文件追蹤 **Phase A**（前端 i18n 框架 ＋ UI 外殼字串外部化 ＋
標頭語言切換 ＋ `app_users.locale` ＋ `/me` 帶 locale ＋ `PATCH /me/locale`）與 **Phase B**
（7 張選項表／詞彙／範本的 `label_en`／`name_en` 機器灌值 ＋ `i18n_review_state` ＋ 待審清單，
2026-08-18 起開工，見 §5）。Phase C（敘事英文化）尚未開工，不在本文件範圍。

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

---

## 5. Phase B（資料標籤層）— B1 批（2026-08-18）

範圍：`migrations/`、`src/ddm_v2/models/v2/i18n.py`、`src/ddm_v2/services/v2/i18n_service.py`、
`src/ddm_v2/api/routes/v2/i18n.py`、`src/ddm_v2/schemas/v2/i18n.py`、
`scripts/dev_seed_i18n_labels.py`、`tests/`。不動 `most_engine/`、`nlp/`、`src/frontend/`。

**B1 內容**：`i18n_review_state` 側表（`v2_0040`）＋灌值腳本＋待審清單 service／API 的**兩席複審
修復**（code-reviewer＋security-reviewer）。必修項：

- **S1**：灌值腳本把「側表列是否存在」誤當成「`_en` 欄位該不該填」的判準，導致 active 版可能
  整批留 NULL（複現：clone draft 早於 active 灌值 → 側表先被 draft 佔走 → active 永遠跳過）。
  修法：側表寫入與 `_en` 欄位填值分開判斷；`seed_rule_options` 查詢加
  `ORDER BY is_active DESC` 當第二層保險。已在乾淨拋棄式 DB 上重現舊 bug（active 63 列全
  NULL）並驗證修復（active 63 列皆有值）。
- **S2**：4 條測試硬編 `63`，改為動態查詢；`summary()` 改成對
  `(entity_type, scope_key, field)` DISTINCT 計數，避免有 draft 時分母翻倍。
- **security Medium**：`upsert_review_state` 加寫入前防線——`source_text` 必須等於 active 版
  現行 `label_zh`／`sentence_text_zh`（或主數據現行 `name_zh`），不等就 409
  `SourceTextStale`，擋住「拿 draft 改過的中文去覆核，污染到 active 覆核狀態」。
- **S6**：`TranslatableRow`／API 回應加 `source_changed: bool` 欄位，讓「剛翻好」與
  「翻過但來源後來又變了、還沒被人看過」在 `unreviewed` 這同一個 status 值底下仍可辨識。
- **S3**：缺翻譯不再讓整條 seed 在第一筆就中止——`_seed_one` 把缺漏記進
  `SeedStats.missing`，`main()` 先 `commit()` 已完成的部分，之後才用 `raise_if_missing()`
  一次列出全部缺漏、非 0 結束。
- **S4**：`ADR-023` §3.3 規則 1 矩陣補回 D4 的交叉引用；
  `docs/roadmap/phase5-i18n-full-bilingual-spec.md` 標記已被 ADR-032 取代。

**驗證**：`pytest tests/unit`（905 passed）、`pytest tests/integration`（497 passed / 1
skipped）、`scripts/core_logic/run_all.py`（全綠，GM=28／CM=29 不變）、
`alembic upgrade head && downgrade -1 && upgrade head`（往返成功）。S1／S2／security
Medium／S6 各自附 mutation 證據（拆掉修復邏輯 → 對應測試紅；還原 → 綠）。

### B1 明確不做（記票，下一批處理前不得遺失）

以下項目經兩席複審提出，本批（B1）刻意不處理，編號沿用複審原始編號：

- **S5**：I3 CI 守衛（`tests/unit/test_i18n_en_field_isolation.py`）目前只掃
  `nlp/`、`template_matching.py`、`synonym_service.py`。複審建議把守衛範圍擴大到
  `most_engine/providers.py`、`most_compiler/`、`motion_template.py` 的寫入點，
  多一層防線防止 `_en` 滲入 TMU 決定路徑。本批未展開。
- **S7**：灌值腳本的翻譯用詞與 v3 認證字典有兩處背離：`m_screw`（滑出螺絲）、
  `g_grab`（抓取）。需要 IE 對照 v3 字典裁定正式英文術語（ADR-032 P3：MOST 標準術語表
  屬 IE 權威，工程端不得自行認定）。
- **S8**：複審建議額外覆核的兩對近義詞（例：`g_grab`／`g_grasp`、
  `m_tearopen`／`m_teartape` 之外的其他近義組）——I5 唯一性檢查只擋「字面完全相同」，
  擋不住「字面不同但仍難以辨義」，這兩對需要 IE 人工覆核而非機械檢查。
- **S9**：`i18n_review_state` 的 CHECK 約束有三個縫：(a) 允許空字串 `source_text`／
  `translated_by`；(b) `source='human'` 未同時要求 `reviewed_at` 非 NULL（只查了
  `reviewed_by`）；(c) `source='machine'`／`legacy_seed'` 沒有擋 `reviewed_by`/`reviewed_at`
  非 NULL（理論上機翻不該有覆核人卻沒有 DB 層防線）。另外 CHECK 約束命名在 ORM
  （`models/v2/i18n.py`）、migration（`v2_0040`）、既有測試斷言字面三方不完全一致，
  下一批修復時應一併對齊。
- **security Low**：待審清單端點 `GET /api/v2/i18n/review/pending` 未分頁（現況資料量小，
  113＋59＋16 可接受，但成長後應補 `limit`/`offset`）；`entity_type` 篩選目前在 Python 端
  做（`list_translatable_rows` 檔頭已註記理由），未下推進 SQL——資料量成長後應重評。

**下一批（B2 或更晚）動手前，應先核對這份清單與 ADR-032 §7／§8 的風險/重評訊號是否有重疊**
（例如 S7／S8 呼應 ADR-032 R1 的「殘留風險：唯一性檢查擋不住『字面不同但仍難以辨義』」——
這條殘留風險 ADR 本身已經寫了，S7／S8 只是把它具體化成兩個待辦，不是新發現）。

---

## 6. Phase B — 第二輪複審修復（2026-08-18）

範圍：`src/ddm_v2/services/v2/i18n_service.py`、`scripts/dev_seed_i18n_labels.py`、`tests/`、
`docs/decisions/ADR-032-*.md`（僅措辭）、`docs/DOC_REGISTRY.md`（僅一致性）。不動
`most_engine/`、`nlp/`、`src/frontend/`、migration。

**編號說明**：以下 B1／M1／M2／L1／L3／L4 是**這一輪複審**自己的發現編號（阻擋級／必修／便宜），
與 §5 用來稱呼整批交付的「B1 批」名稱是兩件事，不要混淆——這裡的 B1 特指複審發現的第一個
阻擋項，不是重新開一個交付批次。

### B1【阻擋，已修復】security 修法的前置檢查在同一個呼叫點開了新洞

`_authoritative_zh_text` 對「active 沒有這個 code」原本一律 fail-closed——但 D4 允許 IE 在
draft 新增 active 沒有的選項，這個合法情境會讓 `upsert_review_state` 丟出未被捕捉的
`SourceTextStale`，穿出 `seed_i18n_labels()`，`main()` 的 `commit()` 從未執行、active 整批
回滾——與 S1 修復前一模一樣的畫面，觸發路徑從「側表判準錯誤」換成「新例外未捕捉」。

修法三處：
1. `_authoritative_zh_text` 改回傳 `(text, constrained)`；只在 active 也有這個 code 時才強制
   比對（`constrained=True`）。active 沒有這個 code 時，只有呼叫端明確聲明 `rule_set_id`
   才放行（`constrained=False`）——不聲明維持舊的 fail-closed，避免「active 沒有就一律放行」
   這種更寬的洞（`test_upsert_review_state_rejects_unknown_scope_key` 守住這條）。
2. active **有**這個 code、文字不符時仍然 409，不受 `rule_set_id` 影響（新增
   `test_upsert_review_state_rejects_modified_active_code_even_with_rule_set_id_declared` 這條
   mutation 導向測試守住）。
3. `_seed_one` 把 `upsert_review_state` 包一層 `try/except SourceTextStale`，撞到時收斂進
   `stats.missing`（S3 已建立的同一個錯誤收集機制），不讓例外穿出整支腳本。

**驗證**：`test_seed_succeeds_when_draft_adds_a_code_absent_from_active` 用 mutation 證據
反向確認——還原成修復前的程式碼（`_authoritative_zh_text` 不放行 ＋ `_seed_one` 不 catch）
會重現一模一樣的 `SourceTextStale` 穿出畫面，該測試變紅；修復後綠。另外在**乾淨拋棄式 DB**
上跑過完整流程（migrate → v2 seed → templates seed → clone 含新 code 的 draft → 跑
`seed_i18n_labels()`）：active 63/63 全部有值、exit code 0、`stats.missing == []`。

### M1【必修，已修復】S1 的迴歸測試在 CI 的 DB 形狀下失效

CI 種子鏈在 pytest 之前已經對真實 active 版跑過 `dev_seed_i18n_labels.py`（`label_en` 全部有
值）；`clone_draft` 的 `_insert_children` 又把 `label_en` 一起複製，新 clone 的 draft 也是滿
的——S1 的迴歸測試在這個前提下呼叫 `seed_i18n_labels()` 對 `_en` 完全無事可做，不管有沒有修
好都是綠燈。

修法：`test_i18n_review_state.py`／`test_i18n_routes.py` 各自加一個
`_reset_rule_option_en_labels_for_in_scope_rule_sets()`（只清 `label_en`，不動側表——S1 bug
的觸發條件正是「側表列已存在、`_en` 卻還沒填」），套用在 5 條會被遮蔽的測試上：
`test_scope_key_is_shared_across_rule_set_versions`、
`test_stale_status_when_zh_label_changes_after_human_review`、
`test_source_changed_distinguishes_fresh_machine_translation_from_stale_one`、
`test_summary_and_pending_rows_reflect_seeded_state_with_draft_present`（以上在
`test_i18n_review_state.py`）、`test_pending_list_filters_by_status_stays_empty_when_a_draft_exists`
（`test_i18n_routes.py`）。

**驗證**：把 `_seed_one` 還原成 S1 修復前的邏輯（側表列存在就整體跳過，不管 `_en` 是否
NULL），在「CI 形狀」（本機長跑 DB，138 列側表已存在）與「乾淨形狀」（新建拋棄式 DB，
migrate＋v2 seed＋templates seed，未跑過 i18n 灌值）兩種 DB 各跑一次——**兩種形狀下都是同一組
5 條測試變紅**，還原修復後兩種形狀都回到全綠。

### M2【便宜，已修復】「唯一寫入路徑」的假設沒有東西在守

新增 `tests/unit/test_i18n_review_state_write_path.py`：AST 掃描（不是純文字 grep，避免把
`class I18nReviewState(Base):` 誤判成建構呼叫）確認 `I18nReviewState(...)` 建構呼叫只出現在
`i18n_service.py`，白名單排除 `test_i18n_review_state.py`（該檔「DB CHECK 不變式」小節刻意繞
過 service 層驗證，測 DB 層 CHECK 約束本身的防禦深度，寫清楚理由）。含 mutation 測試證明掃描
器不是恆真的空清單。

### L1【便宜，已修復】無 active rule-set 時的錯誤訊息誤導

`_authoritative_zh_text` 改呼叫 `rule_set_service.get_active_rule_set()`（既有的
`NoActiveRuleSet` 例外與 500 handler），查無 active 時不再落入 `SourceTextStale` 的「很可能是
拿 draft 已修改過的中文去覆核」這種誤導訊息。新增
`test_upsert_review_state_raises_no_active_rule_set_when_none_is_active` 驗證。

### L3／L4【便宜，已修復】

- **L3**：ADR-032 D6 的 `source_changed` 說明補一句「`review_sha256 is None` 時一律 `False`」
  ——程式碼行為本來就對，這裡只是把散文說明補齊。
- **L4**：`docs/DOC_REGISTRY.md` Roadmap 表格裡「全面中英雙語」那一列改成
  「⛔ 已被 ADR-032 取代」，與檔案本身的狀態欄、與〈架構決策〉小節的既有文字保持一致。

**驗證（本輪）**：`pytest tests/unit`（910 passed）、`pytest tests/integration`（501 passed /
1 skipped）、`scripts/core_logic/run_all.py`（全綠，GM=28／CM=29 不變）、`ruff check src/
scripts/ tests/`（全綠）。B1／M1 皆附 mutation 證據（見上）。

### 本輪記票不做

- **L2**：vocab／template 的欄位型別過寬，目前沒有呼叫端會踩到——留待下一輪有實際呼叫端出現
  時再處理，避免預先加限制卻猜錯需求。
- **L5**：前端型別（`api.d.ts`）尚未因本輪後端改動重新產生——本輪不動 `src/frontend/`，留給
  下一輪前端接手 i18n 覆核 UI 時一併跑 `npm run gen:api`。

---

## 7. Phase B — 第三輪複審與第四輪簡化（2026-08-18）

範圍：`src/ddm_v2/services/v2/i18n_service.py`、`scripts/dev_seed_i18n_labels.py`、`tests/`、
`docs/decisions/ADR-032-*.md`、`.github/workflows/ci.yml`（僅註解）、`docs/CI_GATES.md`
（僅註解）。不動 `most_engine/`、`nlp/`、`src/frontend/`、migration。

**第三輪複審的結論（架構評估，經協調者轉達，未另立文件）**：`_authoritative_zh_text`／
`SourceTextStale` 這道寫入前逐字比對防線，是過去兩輪每一個阻擋級複審問題（第二輪的 B1、
L1，以及第三輪再抓到的問題）的**唯一來源**。分析：這道防線想擋的「draft 改過的中文被拿去
標記覆核，污染 active 的顯示狀態」，讀取端的 `_classify` 早就正確處理——它是拿
`review_sha256` 去比對**每一個候選列自己的** `source_zh`，active 那一列若中文跟被覆核時的
內容不一致，會正確顯示 `stale`，不會顯示「已覆核」
（`test_stale_status_when_zh_label_changes_after_human_review` 已證明這個機制運作正常）。
寫入前的逐字比對是對同一問題的第二個、版本無關、精度更低的答案，而且是脆弱的來源——結論：
拆除，不再修補。

### 第四輪：拆除寫入前比對防線

- **`i18n_service.py`**：移除 `_authoritative_zh_text` 函式與 `SourceTextStale` 例外類別；
  `upsert_review_state` 不再接受 `rule_set_id` 參數，也不再比對 `source_text` 與任何版本的
  「現行權威中文」——如實記錄呼叫端聲明的文字。**唯一保留的寫入前檢查**：新增
  `UnknownReviewScopeKey`（404）＋ `_scope_key_exists()`——`scope_key` 完全查無對應 entity
  時 fail-closed 拒絕；檢查範圍刻意跨所有 rule-set 版本（不限 active），因為這是「entity 存不
  存在」的問題，不是「內容跟哪個版本比對」的問題，兩者不該再混在同一個判斷式裡（這正是第二輪
  B1 洞的根本原因）。
- **`dev_seed_i18n_labels.py`**：`_seed_one` 移除 `rule_set_id` 參數與
  `try/except SourceTextStale`（呼叫端傳入的 `scope_key` 永遠是剛從 DB 查到的既有列，天生滿足
  唯一保留的存在性檢查，不會再撞到寫入例外）；`seed_rule_options` 同步移除
  `rule_set_id=rs.id` 的傳遞。
- **核心驗收：新增端對端測試**
  `test_write_side_no_longer_checks_content_but_read_side_still_catches_stale_review`
  （`tests/integration/test_i18n_review_state.py`）——證明「結果正確」而不只是「防線還在」：
  1. clone 一個 draft（與 active 共用 `g_grasp` code），把 draft 的中文改掉。
  2. 對 `scope_key="g:g_grasp"` 呼叫 `upsert_review_state(source_text=<draft 改過的中文>,
     source='human', ...)`——**這次呼叫成功**（拆除前會是 `SourceTextStale`）。
  3. 查 active 版該 code 的候選列狀態（`list_translatable_rows`）——斷言 `status == "stale"`
     （不是 `None`／已覆核）：active 現行中文從未變過，跟剛記錄的 `source_sha256`（draft 改過
     的中文的 sha）對不上，讀取端 `_classify` 正確判成過期。同時斷言 draft 自己的狀態是
     `None`（名符其實的覆核）、active 的中文本身完全沒被動過。
  這條測試取代第一輪 security review 加的「寫入時拒絕」測試，驗證同一個安全屬性，但用讀取端
  機制達成。
- **移除的測試**（凡測「寫入時因為文字不符而被拒」的，行為已不存在）：
  `test_upsert_review_state_rejects_source_text_taken_from_a_draft`、
  `test_upsert_review_state_accepts_source_text_matching_active_label`、
  `test_upsert_review_state_allows_new_code_absent_from_active_when_rule_set_id_declared`
  （依賴已移除的 `rule_set_id` 參數）、
  `test_upsert_review_state_rejects_modified_active_code_even_with_rule_set_id_declared`、
  `test_upsert_review_state_raises_no_active_rule_set_when_none_is_active`。
- **保留並改寫的測試**：`test_upsert_review_state_rejects_unknown_scope_key`（查無 scope_key
  仍 fail-closed，但斷言的例外換成 `UnknownReviewScopeKey`，不再是內容比對失敗）；
  `test_seed_succeeds_when_draft_adds_a_code_absent_from_active`（B1/S1 複現流程：clone draft
  含新 code → 灌值 → active 63/63，簡化後不再有 `SourceTextStale` 這個中止點，路徑更順暢）。
- **新增的補充測試**：`test_upsert_review_state_accepts_code_that_exists_only_in_a_draft`（存在
  性檢查不限 active 是預設行為，不再是需要 `rule_set_id` 才觸發的特例）；
  `test_upsert_review_state_no_longer_requires_an_active_rule_set`（存在性檢查不再呼叫
  `get_active_rule_set()`，系統無 active rule-set 時不再連帶失敗）。
- **L-2（CI 種子鏈理由重寫）**：`.github/workflows/ci.yml`／`docs/CI_GATES.md` 裡「CI 必須跑
  `dev_seed_i18n_labels.py` 否則整合測試會紅」的理由是假的——複審實測：CI 不跑這支腳本，
  `pytest tests/integration` 仍是全綠（每個需要 i18n 資料的測試都在自己的 session 裡自建）。
  改成誠實理由：這支腳本本身要被當成**部署腳本的煙霧測試**（確保它在乾淨環境下真的能跑到底），
  並讓 CI 環境的資料形狀貼近未來 dev/staging 環境——步驟本身保留，只改註解。
- **L-3（M2 守衛擴大範圍）**：`test_i18n_review_state_write_path.py` 的 `I18nReviewState(...)`
  建構呼叫掃描範圍加入 `migrations/`（先前只掃 `src/`／`scripts/`／`tests/`）。
- **ADR-032 更新**：D6 新增段落「寫入端不比對內容，覆核正確性完全依賴讀取端過期偵測」，記錄
  最終設計——寫入端只做存在性檢查、如實記錄呼叫端聲明的文字；正確性保護只有讀取端 sha256
  過期偵測這一層，不再有第二層內容比對，避免下一個人誤以為系統有兩層防護。

**驗證（本輪）**：`pytest tests/unit`（910 passed，同基線）、`pytest tests/integration`
（499 passed / 1 skipped——較上一輪基線 501 少 2，淨變化＝移除 5 條寫入時拒絕測試、新增 3 條
存在性/讀取端測試）、`scripts/core_logic/run_all.py`（全綠，GM=28／CM=29 不變）、
`ruff check src/ scripts/ tests/`（全綠）、`mypy src/`（**64→62**，`i18n_service.py` 本身歸零：
`_authoritative_zh_text` 移除的兩條 `"type" has no attribute` 錯誤原本會被新的
`_scope_key_exists` 用同樣手法重新引入——改用既有的 `getattr()` 慣例避開後，淨減少 2 條，
不是原地打轉）。

### 記票（本輪不做）

- **`source_rule_set_id` 非鍵欄位**：記錄「這次覆核當下看的是哪個版本的中文」，供稽核用——
  這是加法 migration，超出本輪範圍（本輪不動 migration），留給 Phase C 前的待辦。
