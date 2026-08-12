# Legacy 分類清冊與 most_engine 純度稽核

**文件類型：** 稽核報告 + 保留政策（判定依據，非規格）
**稽核日期：** 2026-08-11
**稽核範圍：** `ddm-v2` @ `202606-rc1/alpha/frontend-refactor`（commit `63fd50f`）
**關聯：** [ADR-014](../decisions/ADR-014-v3-dictionary-as-value-authority.md)（值權威與 V1/V2 並存的由來）、
[ADR-021](../decisions/ADR-021-ia-restructure-v3-parity.md)（IA 母版，AI 快速建模列）、
[ADR-023](../decisions/ADR-023-dictionary-governance-unification.md)（§3.4 回放鐵則）、
[ADR-011](../decisions/ADR-011-schema-evolution-and-contract-stability.md)（契約加法演進、刪欄三步）、
[CI Gates](../CI_GATES.md)、[v2 權威模型指南](v2-authoritative-model-guide.md)

---

## 0. 為什麼需要這份文件

「legacy」這個詞在本 repo 指涉**六種性質完全不同的東西**，其中兩種是稽核硬需求（刪掉會毀掉回放能力），
兩種是名字誤導的現役程式碼（刪掉會讓系統直接掛掉），只有一種是真的可以刪的技術債。

過去已發生過一次誤判風險：`nlp/lexicon.py` / `ports.py` / `rule_based.py` 因命名與 docstring
自述而看似 impl-05 遺留物，實際上是新 AI pipeline 的現役依賴與預設路徑。

**本文件的用途是：在任何人提出「清掉 legacy」之前，先查這張表。**

---

## 1. 權威結論摘要

| 問題 | 結論 |
|------|------|
| `most_engine/` 是不是 legacy？ | **不是。** 引擎內零版本分支，V1/V2 差異全由資料承載，單一程式路徑 |
| AI 那批（L0–L4/R1–R3b）有沒有汙染引擎？ | **沒有。** 引擎最後一次改動 2026-07-13，早於 L0（2026-08-07） |
| `MINIMOST_FACTORY_V1` 可以刪嗎？ | **絕對不可。** 它是 ADR-014 選項 C 的稽核代價，ADR-023 §3.4 定為回放鐵則 |
| MOST 工作台的「AI 快速建模」可以刪嗎？ | **不可。** ADR-021 §Tab1 形態第 1 項明文要求；但它目前違反規格（見 §5.1） |
| 真的可以刪的有哪些？ | 三處零引用死碼 + 一個無效環境變數（見 §4.F） |
| 引擎本身有沒有問題？ | **有兩類**：靜默 fallback（§6）與一份已漂移的重複實作（§7） |

---

## 2. 分類總表

| 類別 | 性質 | 可否移除 |
|------|------|----------|
| A. Rule-set 回放快照隔離 | 稽核硬需求 | **絕對不可** |
| B. 引擎的 V1 資料相容分支 | 稽核硬需求（A 的實作面） | **絕對不可** |
| C. nl-draft legacy 七格位契約 | 契約相容層，有退場條件 | 需先遷前端，且受 ADR-011 三步約束 |
| D. `nlp/` 的 lexicon / ports / rule_based | **誤判——是現役 L0 baseline 與預設路徑** | 不可 |
| E. 過渡／雙寫 schema | 遷移中間態 | 需先完成遷移 |
| F. 純技術債／死碼 | 零引用 | **可砍** |
| G. 已退役但刻意封存的文件／資產 | 有明文守則 | 保留 |

---

## 3. 必須保留的（A / B）

### A. `MINIMOST_FACTORY_V1` — 稽核回放的快照隔離，不是舊程式碼

**為什麼存在。** ADR-014 否決了「直接改 V1 數值」（該選項會破壞既有 cycle 快照回放、違反 published
凍結原則），改採「新開 V2 + 黃金重錨」。雙版本並存就是這個決策的直接代價。
ADR-023 §3.4 進一步把它升格為**回放鐵則**：`load_rule_set_from_db` 只依 `code` 查表，
**永不看 `status` / `is_active`**——治理狀態只在「選擇」時生效，不在「載入」時生效。

**回放是資料驅動的，不是程式分支。** `most_cycles.rule_set_id` 為 per-cycle 外鍵，
每筆 cycle 自己釘住當初的規則版本；`most_worksheets.default_rule_set_id` 只是新建時的預設。

**證據位置。**

| 位置 | 內容 |
|------|------|
| `src/ddm_v2/seed/v2/rule_set_seed.py:19` | V1 rule-set 定義（手寫） |
| `src/ddm_v2/most_engine/providers.py:123` | `load_rule_set_from_db()`——只用 `code` 查，零版本感知 |
| `tests/integration/test_rule_set_replay_isolation.py` | 回放鐵則的機械化斷言（inactive/retired 仍須載得到且算出原值） |
| `scripts/core_logic/engine_golden_test.py:148-154` | 「L. V1 回放（快照隔離）」段，5 條 V1 語意斷言 |
| `tests/unit/test_most_engine.py` | `test_v1_replay_goldens` 等 |
| `docs/CI_GATES.md:14` | 回放鐵則的 grep 負向規則 |

**V1 與 V2 的五處行為差異（全部由資料承載，同一份程式碼跑出來）：**

| 行為 | V1 | V2 |
|------|-----|-----|
| CM 黃金 29 的來源 | 推 18cm（階梯 18→16） | 推 45cm |
| 階梯 30cm | 24 | 16 |
| G 接觸未勾 gating | 0 | 3 |
| 對準未勾精度 | 16 | 24 |
| M 腳步帶 | 無獨立表，回退 ladder | 有獨立 `m_foot` 表 |

**移除的後果：** 所有引用 V1 的歷史 cycle 無法回放；`test_rule_set_replay_isolation.py`、
`test_v1_replay_*`、`engine_golden_test.py` L 段全紅；稽核能力歸零。

> **命名陷阱：** `MODELING_FACTORY_V1` / `LEVEL_FACTORY_V1`（`services/v2/policy_service.py`、
> `seed/v2/policy_seed.py`、migration `v2_0030`）**完全不是 legacy**——那是 2026-08-11 才落地的
> ADR-027 R2a policy manifest 第一版，`V1` 是它的版本序號。名字撞了而已。

### B. 引擎裡的 V1 資料相容分支

這些是 A 的實作面，同樣不可動。**注意它們全都是資料形狀驅動，不是 `if version == "V1"`。**

| 位置 | 內容 | 為何必要 |
|------|------|----------|
| `most_engine/rule_set_data.py` `foot_tmu()` | `m_foot` 空表 → 回退 ladder | V1 無獨立腳步帶 |
| `most_engine/calculate.py` G gating | `requires_modifier` 未滿足 → 0 | V1 資料 `requires_modifier=True`，V2 全 `False` |
| `most_engine/calculate.py` P addon | `needs_precision` 未滿足 → 略過 | V1 `a_align` 有精度 gating，V2 無 |
| `most_engine/narrative.py` `_sent()` | `sentence` NULL → 回退 `label` | V1 資料無 `sentence_text_zh` |
| `schemas/v2/most.py` `GSlot.modifiers` | 註解寫「V2 資料下無作用」 | **歷史 `slot_inputs` JSONB 的反序列化入口**——拿掉舊 cycle 直接 422 |
| `schemas/v2/most.py` `PSlot.precision` | 同上 | 同上 |

> `GSlot.modifiers` 與 `PSlot.precision` 是最容易被誤判為死碼的兩個欄位。它們在 V2 資料下確實
> 不影響計算，但它們是舊 cycle 反序列化的必要欄位。**這兩個欄位的存在理由必須寫在程式碼註解裡**
> （目前只寫了「V2 資料下無作用」，沒寫「但反序列化需要」）。

---

## 4. 其餘分類

### C. nl-draft legacy 七格位契約 — 相容層，有退場條件但現在不能動

**是什麼。** `nlp/rule_plan_adapter.py` 的 `legacy_from_parse_run()` / `legacy_from_run_snapshot()`，
把新的 `wi-plan-v1` 結果轉回舊的 GM-shaped 七格位，攤平到 `/nl-draft` 回應的 top-level
（`slots` / `suggested_seq` / `overall_confidence` / `context` / `provenance` / `raw_text` / `normalized_text`）。

**為什麼存在。** 系統規格要求「舊版 `NLDraftResult` 欄位只增不改」；
`legacy_from_run_snapshot` 另有獨立理由（worklog D3-003）：cache hit 時若重算 legacy，
會與當下 synonym 表漂移，導致 `ai.*` 與 legacy 兩塊互相矛盾。

**逐欄位真實消費盤點：**

| 欄位 | 後端 | workbench-v3 | wi-workbench | 判定 |
|------|------|--------------|--------------|------|
| `slots` | 無 | **讀** | **讀** | 現役 |
| `suggested_seq` | 無 | **讀** | **讀** | 現役 |
| `overall_confidence` | 無 | **讀** | 宣告未讀 | 現役（單邊） |
| `context` | 無 | 宣告未讀 | 未宣告 | **零消費**（後端永遠回 `{}`） |
| `provenance`（top-level） | 無 | 未宣告 | 宣告未讀（UI 讀的是 `ai.provenance`） | **零消費** |
| `raw_text` / `normalized_text` | 無 | 無 | 宣告未讀 | 零消費 |

**後端自己零消費**——`parse_job_service` 明確丟棄（`result, _legacy = ...`）。

**退場順序（受 ADR-011「刪欄要三步跨 release」約束）：**

1. 補上規格要求但尚未實作的 `tests/integration/test_nl_draft_compat.py`（golden JSON 逐欄 diff）。
   目前 `legacy_from_parse_run` / `legacy_from_run_snapshot` **零單元測試覆蓋**，沒有安全網。
2. 前端遷移到 `ai.*`。注意 `ai.slot_candidates` 的 `field` 是 CycleIn 風格（`a0` / `b1.b_code` …），
   前端目前沒有這個對映，需要把反向表搬到前端或另開 adapter。
3. 並行一個 release。
4. 才刪後端 `legacy_from_*`。

> 特別注意：新的 `AiDraftPanel` 在「LLM 沒產出完整 draft」時的退路（「填入編輯器（相容）」按鈕）
> **也吃 legacy**。砍了等於連新路徑一起殘廢。

### D. 誤判清單 — 名字像 legacy，實際是現役

| 檔案 | 實際角色 | 砍掉的後果 |
|------|----------|------------|
| `nlp/lexicon.py` | **新 `SlotLinker` 的核心依賴**（`linking.py` L1 層 + `rule_based.py`） | `linking.py` import 失敗 → 整個 AI pipeline 起不來 |
| `nlp/rule_based.py` | `wi_ai_enabled=False`（**這是預設值**）時的**唯一路徑**；LLM 開啟時的 `baseline_disagreement` 對照組；`import_service` 的 seq 推斷 | `/nl-draft` 在預設部署下直接掛掉；失去 shadow 對照能力 |
| `nlp/ports.py` | `rule_based.py` 與 `rule_plan_adapter.py` 的契約來源 | 兩者 import 失敗 |

規格明文要求保留：`ports.py` = 「保留為 legacy 契約；新契約以加法並存」、
`rule_based.py` = 「保留為 baseline 與 fallback adapter」；系統規格另定
「timeout、circuit breaker 與 rule-based fallback 是 contract 的一部分」。

**可做的只有正名**：把它們標成 legacy 的是**實作規格的接縫盤點表**（「保留為 legacy 契約」、
「保留為 baseline 與 fallback adapter」），不是程式碼本身——`ports.py` 的 docstring 其實寫的是
「`DraftParserPort` 是 Protocol；`RuleBasedParser` 是第一個 adapter」。
規格表格那兩個「legacy」標籤是這次誤判的來源，建議改為「L0 現役契約／fallback adapter」。

### E. 過渡／雙寫 schema — 尚未完成的遷移，不是可清的債

| 項目 | 現況 | 退場條件 |
|------|------|----------|
| `excel_imports.staged_rows` → `import_rows` | `staged_rows` **仍是唯一寫入源**；`import_rows` 目前是 `materialize_import_rows()` 產生的衍生資料 | upload/map 直接寫 `import_rows`、submit 改讀 `import_rows` |
| `base_revision` nullable（R1 樂觀鎖） | `None` → 無條件 +1 並記 `logger.warning("legacy last-write path")` | 所有前端寫入路徑都送 `base_revision` 後改必填 |
| worksheet policy FK nullable（R2a） | 「nullable 過渡；新建應立即綁定 factory default」 | consumer 全面切換後收緊 |

`base_revision` 的 nullable 是**現存的 lost-update 風險窗口**，不只是整潔問題。

### F. 可直接移除的（已驗證零引用）—— **本次已全數處置**

| 項目 | 驗證方式 | 處置 |
|------|----------|------|
| `src/frontend/src/features/sop/api.ts` | 該目錄唯一檔案，全 repo 零 import；6 個匯出符號逐一 grep 僅命中自身 | ✅ 已刪（含空目錄） |
| `Sidebar.tsx` 的 `SECONDARY_NAV` + `sidebar.types.ts` 的 `NavItem.secondary` | grep 只命中宣告自身；`NavList` 只收 `PRIMARY_NAV` | ✅ 已刪 |
| `schemas/common.py` 的 `AuditAction` | 只被 `schemas/__init__.py` re-export，無實際消費者；它服務的 legacy JSON-store routes 已於 `0c7a2d2` 刪除 | ✅ 已刪並同步 `__all__` |
| `settings.py` 的 `tmu_factor` / `DDM_TMU_FACTOR` | **引擎完全不讀**（`most_engine/` 內 grep `tmu_factor` 零命中） | ✅ 已刪，並在原處留墓碑註解防止再加回 |

> e2e 影響已逐條確認：`ux-compliance.spec.ts` 兩處提到 `SECONDARY_NAV` 的都是**註解**，
> 實際斷言是「SOP 按鈕不可見」；最嚴格的 A-01-1（`nav` 按鈕 `toHaveCount(8)` 且順序完全相符）
> 因為 `SECONDARY_NAV` 本來就未被渲染，DOM 完全不變。

> **`DDM_TMU_FACTOR` 是會騙人的環境變數。** 它看起來能設定 TMU→秒 換算，實際設了完全沒有作用。
> 這比死碼更危險：有人可能設了它然後以為換算已改變。移除時應同時確認沒有部署文件在教人設定它。

### G. 已退役但刻意封存的（有明文守則，別碰）

| 路徑 | 守則出處 |
|------|----------|
| `docs/html_con/` | DOC_REGISTRY「只封存不作新實作依據」；ADR-021 已廢止其 UI reference 地位；v2 權威模型指南列為禁止清單 |
| `docs/v3/reference/minimost_ai_dictionary_v1.json` | **不是 legacy**（名字有 v1 而已）——ADR-014 值權威、converter 唯一輸入，DOC_REGISTRY 標「禁止刪除」 |
| `docs/sample_excel/` | 1205 Level/敘事來源、1128 WI 範本 |

---

## 5. 稽核中發現的缺陷（不是 legacy，是需要修的）

### 5.1 MOST 工作台靜默丟棄多動作結果（規格違反）

實作規格明文：「legacy 欄位由『第一個 GM draft』透過 adapter 轉出；**結果含多 action 時
`multi_action_warning=true`，舊前端必須顯示警告不得靜默取第一筆**」。

`features/workbench-v3/`（即側邊欄「MOST 工作台」）**完全沒有讀 `multi_action_warning`**
（grep 零命中），也沒有讀 `ai.*`。`features/wi-workbench/AiDraftPanel` 有正確處理。

**這不是可以靠刪除解決的問題。** ADR-021 §Tab1 形態第 1 項明文要求 MOST 工作台要有
「AI 快速建模列：NL 輸入＋『AI 預填』；編輯器有內容時詢問『覆蓋／只填空白』」，
ADR-022 重述，v3 母版的動作編輯器結構第 1 項也是 `NlDraftInput`。
ADR-021 驗收協定第 4 條另有「既有功能不得回歸」。

**正確處置：升級而非移除**——讓 workbench-v3 改用 `wi-workbench/aiTypes.ts` 的契約，
順帶消掉 `workbench-v3/nlDraft.ts` 與 `AiDraftPanel` 的雙份 legacy 消費邏輯
（`nlDraft.ts` 檔頭註解本來就寫了這個收斂計畫）。

### 5.2 rule-set 刪除守衛的引用清單漂移（真迴歸）

`services/v2/rule_set_service.py` 的 `_RESTRICT_REFERRERS` 只列三張表
（`most_cycles` / `most_worksheets` / `motion_module_versions`），
但 migration `v2_0026`（`ai_parse_runs`）與 `v2_0028`（`ai_parse_jobs`）各新增了一個
指向 `rule_sets` 的 `ondelete="RESTRICT"` 外鍵，**沒有同步這個常數**。

後果：`count_references()` 少報引用，原本設計要回的 409 友善錯誤
（「rule-set 已被歷史資料引用，不可刪除」）會變成 DB 層 RESTRICT 拋出的 500。

`tests/integration/test_rule_set_delete_unretire.py::test_count_references_covers_every_restrict_referrer`
就是為了抓這種漂移而寫的（2026-07-21，ADR-023 D3b），**它確實抓到了**。

**處置（本次已修）：** `_RESTRICT_REFERRERS` 補上 `ai_parse_runs` / `ai_parse_jobs`，
並在常數上方寫明「新增任何指向 `rule_sets` 的 RESTRICT FK 時必須同步此清單，
`test_count_references_covers_every_restrict_referrer` 會擋」與這次漏加的實例，
讓下一個加 migration 的人看得到。

> **未被及時發現的原因值得記錄：** worklog 顯示每個 phase 的 checkpoint 只跑相關子集測試
> （「9 passed」「17 passed」「23 passed」），**從未跑過完整 integration 套件**。
> 這個守衛測試不在任何一個 AI phase 的子集裡。

### 5.3 完整測試套件基線（2026-08-11 實測）

| 套件 | 稽核當下 | 本次修正後 |
|------|----------|------------|
| `pytest tests/unit` | 256 passed | 256 passed |
| `pytest tests/integration`（完整） | **396 passed / 3 failed / 1 skipped** | **398 passed / 1 failed / 1 skipped** |
| `scripts/core_logic/run_all.py` | 167 passed（84 + 26 + 57） | 167 passed，全綠 |
| `ruff check src/` | 3 errors（未使用 import） | **All checks passed** |
| `mypy src/` | 62 errors / 12 files（services/v2 佔 37、most_engine 佔 19） | 62 errors，**零新增**（對照 pristine worktree） |
| `npm run typecheck` / `build` | 乾淨 | 乾淨 |

稽核當下的三個 integration 失敗，**歸因必須分清楚**（初稿把兩筆都算在引用清單漂移上，是錯的）：

| 失敗 | 真實成因 | 本次處置 |
|------|----------|----------|
| `test_count_references_covers_every_restrict_referrer` | §5.2 的引用清單漂移 | ✅ 修程式 |
| `test_delete_referenced_draft_returns_409_with_reference_count` | **環境資料問題**——`SELECT id FROM most_cycles LIMIT 1` 直接 `NoResultFound`，因為乾淨 dev DB 的 `most_cycles` 是 0 列。與引用清單無關（`most_cycles` 本來就在舊清單裡） | ⚠️ 靠補跑 seed 轉綠，**測試脆弱性未解** |
| `test_wi_set.py::test_instantiate_runtime_failure_rolls_back_worksheet_and_prior_rows` | **不是測試瑕疵，是線上 P0 的症狀**——見 §11 | ❌ 本次未修，須獨立處理 |

也就是說 396 → 398 這兩筆進帳中，**只有一筆歸功於程式修正**，另一筆歸功於「補跑 seed」。
把兩筆都算成修 bug 會高估此次驗證強度，也會淡化「測試依賴環境既存資料」這個該追的脆弱點。

> **另一個環境脆弱性（修正過程中發現）：**
> `test_delete_referenced_draft_returns_409_with_reference_count` 不是被 409/500 邏輯擋掉的，
> 而是 `SELECT id FROM most_cycles LIMIT 1` 直接 `NoResultFound`——因為乾淨的 dev DB
> `most_cycles` 是 0 列。它**依賴環境既存資料**才能跑，要靠 `scripts/dev_seed_30rows.py` 種資料。
> 依賴環境資料的測試是脆弱的，應改為自建 fixture。
>
> 而 `scripts/dev_seed_30rows.py` 本身當時是**壞的**：它用 `x_scan`，但該碼只存在於 V1 字典，
> V2 認證字典只有 `x_scan_bar` → 一跑就 `X_UNKNOWN` 整份掛掉。也就是說 CLAUDE.md 記載的
> dev 環境建置第三步當時是斷的。**已修**（全腳本 27 個碼已逐一比對 V2 字典，皆有效）。

> **環境陷阱（已絆倒一次）：** dev DB 若停在舊 migration head，AI 相關 integration 會整批紅
> （症狀像大迴歸，實為 `ai_*` 表不存在）。跑測試前先確認 `alembic current` 是 head。

---

## 6. most_engine 純度稽核

### 6.1 「唯一計算權威」成立的部分

- **引擎內零版本分支**：grep `FACTORY_V1|FACTORY_V2|version ==|legacy` 於 `most_engine/` 零命中。
- **slot 級 TMU 計算沒有第二份**：`src/` 內除 `most_engine/`、seed 資料檔與 DB 表外，
  無任何 band/ladder 表或 slot 算術。所有呼叫端都委派 `compute_cycle`。
- **前端不算 TMU**：`SlotBuilder.tsx` 明示「前端不算 TMU（DISC-02）」，
  A 距離選擇器只是把後端回的 `a_bands` 轉成下拉選項。
- **AI 對引擎的依賴方向正確**：`most_compiler/engine_gate.py` 呼叫 `compute_cycle`，
  且 `most_compiler/` 內零 TMU 計算（實作規格列為 invariant I1）。

> ⚠️ **「CI 有 grep gate」是規格要求，不是現況。** 實作規格與 `CI_GATES.md` 都寫著
> 「CI 另以 grep 守」（invariant I1、ADR-023 §3.4 回放鐵則），但 `.github/workflows/ci.yml`
> **全檔沒有任何 grep step**——只有 import 檢查、alembic、seed、`run_all.py`、`pytest`、
> 前端 typecheck/build、Playwright。這兩條純度守則目前**只靠人工遵守**。列入 §9。

### 6.2 不成立的部分

| 項目 | 內容 |
|------|------|
| **秒數換算有三份** | `most_engine/rule_set_data.py` 的 `TMU_TO_SEC`（權威）、前端 `shared/config.ts` 的 `TMU_SEC`（23 個使用點）、`settings.py` 的 `tmu_factor`（引擎不讀，死設定） |
| **表級聚合語意有四份** | `compute_table` 的 ADR-020「SIMO 標記列貢獻 0」規則，在 `cases_service`、`worksheet_service`、前端 store、前端 `wiGroupTmu` 各重新編碼一次，靠約定而非結構維持一致 |
| **V1 seed 有一份完整的重複引擎** | 見 §7 |

`scripts/core_logic/` 的兩個驗證器（sequence / level）是**刻意的獨立 oracle**，
不算純度違反，但同樣是需要人工同步的副本。

---

## 7. 引擎的兩類實際問題

### 7.1 靜默 fallback（違反「No error bypass」hard rule）

以 `build_from_seed_v2()` + `compute_cycle` 實測（2026-08-11）：

| 輸入 | 目前行為 |
|------|----------|
| M 推 `distance_cm = -5` | **TMU = 0.0，不報錯** |
| 旋轉 `revolutions = 99` | **TMU = 42.0**，靜默夾到 3 圈 |
| `compute_cycle({"seq":"GM"})`（無 slots） | **TMU = 0.0，不報錯** |
| GM 的 slot0 塞 `m_components` + `x_code` | **接受，12 TMU**（跨模型檢查只守 slot 3/4/5） |
| `compute_cycle(json.loads(json.dumps(cycle)), rs)` | **28.0 變 0.0，不報錯**（見下方） |
| 對照：A 格位 `reach_cm = -5` | `SequenceError A_NEGATIVE`（**正確擋下**） |

A 格位擋了負值，M 格位沒擋——同一個引擎內兩套標準。

> **最後一列是 ADR-028 審查時才發現的，比其他幾條更危險。** 引擎的 `slots` 用 **int 鍵**
> dispatch，JSON 往返後變成字串鍵 → 七格全部 miss → miss 分支的預設值恰好是合法的 0，
> 於是整條 cycle 靜默算成 `A0 B0 G0 A0 B0 P0 A0`、TMU=0，**不報任何錯**。
> 任何直接讀 `slot_inputs` 的修補腳本或批次 worker 都會踩到。
> 通用偵測特徵：**以非字串鍵做 dispatch、且 miss 分支回傳合法預設值的查表**
> （`dict.get(i)` + `or {}` 是可 grep 的目標）。

其他靜默點：A band 溢位靜默夾到最後一檔、負值視為 0、`m_foot` 空表靜默回退 ladder、
無 `b_default` 靜默計 0、G gating 未滿足回 0、P addon 精度未滿足靜默略過、
M component 無 `verb_code` 靜默略過、缺格位變空 dict。

另有一處錯誤契約不一致：`calculate.py` 的 X 選項 `fixed_seconds` 為 NULL 時拋**裸 `ValueError`**
而非 `SequenceError`，會繞過所有 `except SequenceError` 處理器，變成 500 而非 422。

> **為什麼這件事擋在 AI 前面：** 人工點 UI 幾乎不會產生負距離、99 圈、空 cycle 或跨模型格位；
> **LLM parser 會持續產生這些**。今天每一個都回傳一個看起來合理的數字，而黃金錨點依然全綠——
> 這是「AI 算錯了我們抓到」與「AI 算錯了但沒人發現」的差別。

**加嚴的真實爆炸半徑（ADR-028 §3 修正了本稽核初稿的推測）：**
`read_worksheet()` 回傳 `most_cycles.total_tmu` **快取欄、不重算**，匯出／LB 輸出／Level 同樣
消費已存欄位——所以「已發布工時表再也算不出當初的數字」**不會發生**。會重算的只有
`PUT /worksheets/{id}`（整份取代語意 → 全列重算）、匯入 commit、`POST /minimost/calculate`、
模組實體化與 backfill 腳本。真正的風險是**含有不合規舊列的工序表，下次存檔會整份 422
（一列毒死整表）**——比原先擔憂的窄，但比「只影響新資料」寬，因此 ADR-028 要求先掃描不得推測。

處置決策見 ADR-028。

### 7.2 已漂移的重複引擎實作

`src/ddm_v2/seed/v2/rule_set_seed.py` 內含一份完整的 TMU 演算法副本
（`_band_index` / `_a_tmu` / `_g_tmu` / `_p_tmu` / `_ladder` / `_m_tmu` / `_x_tmu` / `_i_tmu`），
供該檔自我驗證使用。**它與真引擎已經給出不同答案：**

| 檢查項 | V1 seed 自檢 | 真引擎 / V2 seed 自檢 |
|--------|--------------|----------------------|
| X 10 秒 | **278**（`math.ceil`） | **277.778**（ROUND_HALF_UP） |
| `_ladder(0)` / `_ladder(-5)` | **3** | 0 |
| `revolutions=2.6` | **`StopIteration` 裸崩** | 夾到 3 圈（另由 ADR-028 A2 加嚴） |

**兩邊各自綠燈**，而且**沒有任何測試或 CI 會呼叫 V1 seed 的 `_self_check()`**
（只能靠 `python -m ddm_v2.seed.v2.rule_set_seed` 手動觸發）——這正是漂移長期沒被發現的原因。
對照組是 `rule_set_seed_v2.py` 的正確做法——它 `from ddm_v2.most_engine import compute_cycle`，不自己算。

**「X 10S → 278」不是 V1 語意，是已被 ADR-014 取代的舊裁決殘留。** 三個獨立證據（詳見 ADR-028 §6）：
核心邏輯 spec 的舊裁決 Q3（ceil）已由同檔 §E2 標記 superseded；ADR-014 明文
「X 捨入（ceil→half-up）屬引擎行為變更、**全域生效**」；且 `seconds_to_tmu()` 是
`@staticmethod`，捨入不由 rule-set 資料承載——實測 `build_from_seed().seconds_to_tmu(10)`
**今天就已經是 277.778**，V1 seed 那份自檢驗的是一份早已不存在的實作。

> 保留注意：`most_engine/providers.py` 會 import 這個檔的 **DATA 常數**建 V1 fixture。
> 要刪的只有那份重複的計算函式與自檢，**資料表必須留**。

處置決策見 ADR-028 §6。

---

## 8. 可重跑的驗證方法

```bash
cd ddm-v2

# 引擎黃金值（含 V1 回放段）
PYTHONPATH=src .venv/bin/python scripts/core_logic/run_all.py

# 單元（不需 DB）
PYTHONPATH=src .venv/bin/python -m pytest tests/unit -q

# 完整整合（需 DB 在 head）
export DATABASE_URL="postgresql+asyncpg://USER:PASS@localhost:5432/ddm_v2_most"
PYTHONPATH=src .venv/bin/alembic current      # 必須是 head
PYTHONPATH=src .venv/bin/python -m pytest tests/integration -q

# 引擎是否含版本分支（應零命中）
grep -rnE "FACTORY_V1|FACTORY_V2|version ==|legacy" src/ddm_v2/most_engine/

# TMU→秒 常數散落處（應只剩引擎權威 + 前端一份待收斂）
grep -rn "TMU_TO_SEC\|TMU_SEC\|0\.036" src/ddm_v2/ src/frontend/src/
```

---

## 9. 未解決事項

| # | 事項 | 追蹤 |
|---|------|------|
| 1 | 引擎邊界驗證的加嚴範圍與回放安全性 | ADR-028 |
| 2 | V1 seed 自檢期望值（278 vs 277.778）何者為 V1 正確語意 | ADR-028 |
| 3 | MOST 工作台升級到 `ai.*` 契約（§5.1） | 待派工 |
| 4 | `test_nl_draft_compat.py` 缺失（legacy 相容層零覆蓋） | 待派工 |
| 5 | `staged_rows` → `import_rows` 遷移未完成（§4.E） | ADR-027 §6 |
| 6 | `base_revision` nullable 的 lost-update 窗口 | R1 nit |
| 7 | 秒數換算三份、表級聚合四份的收斂 | 未排程 |
| 8 | ~~CI 後端測試步驟整個是 collection error + seed 崩潰~~ | ✅ 本次修（§10） |
| 9 | `count_references` 的守衛只比對「表名集合」不比對欄位；同表兩條 FK 或欄名不符都測不出來 | 未排程 |
| 10 | `CASCADED_CHILD_TABLES` 是同型手維護清單，**完全沒有守衛** | 未排程 |
| 11 | `REFERRER_ZH` 前端對照表無自動守門（建議把標籤搬到後端成單一權威） | 未排程 |
| 12 | `ai_parse_runs` 對 **draft** rule-set 持有 RESTRICT ⇒ 預覽過一次的 draft 字典永遠刪不掉 | 未排程 |
| 13 | 實作規格與 CI_GATES 宣稱的 grep gate（引擎純度、回放鐵則）**實際不存在**（見 §6.1） | 未排程 |
| 14 | 測試依賴環境既存資料（`test_delete_referenced_draft_*` 需 `most_cycles` 有列） | 未排程 |
| 15 | ~~P0：`expire_all()` 讓三個端點回 500~~ | ✅ 已修（§11） |
| 16 | `tests/integration/` 有約 120 處「seed 未種就 skip」——seed 一旦部分失敗，整套會從「紅」退化成「綠但什麼都沒測」 | 未排程 |
| 17 | CI 紅燈無人看：建議 branch protection 或把「貼出綠燈 CI run URL」列為 checkpoint 出口條件 | 未排程（§11 有直接證據） |
| 18 | `require_seed` helper 未做——`tests/integration/` 約 120 處「seed 未種就 skip」，種子一旦部分失敗，整套會從「紅」退化成「綠但什麼都沒測」。**新補的 WI Set P0 迴歸測試自己就用了這個 pattern** | 未排程 |
| 19 | 「主要路徑測試不得列為可後補的 nit」只寫在事後檢討裡，沒進 CLAUDE.md／CI_GATES／checkpoint skill——**教訓沒有寫進任何會被執行的地方** | 未排程 |
| 20 | `worksheet_revision.py` 的裸 `assert ws is not None`（`f19e501` 既有）：`python -O` 下會退化成 `AttributeError`，兩者都是 500 | 未排程 |
| 21 | `wi_set_service` 硬寫 `base_revision=None` → 每筆 WI 噴一行 legacy WARNING 假警報 | 未排程 |
| 22 | coverage.py 對 async 檔案的行覆蓋不可信（`await` 之後系統性漏記）——若日後要拿覆蓋率當關卡需先處理 | 未排程 |
| 23 | **依賴完全沒鎖**（§12）：CI 與 prod image 每次 build 都裝到最新版，同一份 commit 昨天綠今天紅。下界／排除區間已修正並實測（`fastapi>=0.133,!=0.137.0,!=0.137.1`／`starlette>=1.5.1`／`python-multipart>=0.0.18`），但**漂移本身要靠 lock 檔才解得掉** | 下界已修；lock **需決策** |

---

## 12. 依賴沒鎖：本次 CI-only 失敗的系統性根因

CI 修活之後第一次真的跑測試，unit 出現 2 條「CI 紅、本機綠」。追下去發現**變因不是
Python 版本，是套件版本**：

| | 本機 `.venv` | CI（每次重裝） |
|---|---|---|
| fastapi | 0.136.0 | **0.141.1** |
| starlette | 1.0.0 | **1.6.0** |

FastAPI 0.141 改了 `include_router()` 的資料結構——不再把子 router 的 `APIRoute`
攤平進 `app.router.routes`，改成放一個延遲展開的 `_IncludedRouter` 節點。
於是 `{r.path for r in app.routes}` 退化成只剩 FastAPI 預設路由加一個 `None`
（19 個 `_IncludedRouter` 沒有 `.path`，在 set 裡塌成一個）。

**但 app 本身完全正常**：`app.openapi()` 有 84 條 path、TestClient 打得到 handler、
415 條 integration 在 0.141 下全綠。**壞掉的只有「走訪路由表」這件事。**

> 這推翻了初判。看到「`create_app()` 產出的 app 沒有任何 v2 路由」時，
> 自然的結論是「正式環境若命中同樣條件就是全掛」——**那是錯的**。
> 教訓：`app.routes` 走不到 ≠ 路由不存在；判斷 API 面是否存在要問 OpenAPI，不要問路由表。

同源的第二處不相容（修好第一處後才浮現）：0.141 把 `Dependant.computed_scope`
從 cached_property 改成模組私有函式，直接讀會 `AttributeError`。

**第三處，由獨立複審建三組 overlay 環境實測出來的版本空窗：**

| fastapi 版本 | `_IncludedRouter`（延遲展開） | `iter_route_contexts`（官方走訪器） | 走訪結果 |
|---|:---:|:---:|---|
| ≤ 0.136.3 | 無 | 無 | 舊路徑可用 |
| **0.137.0 / 0.137.1** | **有** | **無** | **兩邊都不成立 → 回空** |
| ≥ 0.137.2 | 有 | 有 | 新走訪器可用 |

也就是說「用新 API 是否存在來判斷資料結構是新是舊」本身就有兩個版本的空窗。
教訓：**探測能力（API 在不在）不等於探測結構（資料長什麼樣）**，
跨版本相容要驗的是後者。

**已修（2026-08）**：`iter_mounted_api_routes` 的舊路徑改成驗**結構**——走訪前先掃
`routes`，出現既非 `APIRoute`、也非已知 starlette 節點（`Route`/`WebSocketRoute`/
`Mount`/`Host`）的型別就丟 `RouteTraversalUnsupported`，不再回一個看似正常的空結果。
0.137.0 實測：修前 `pytest tests/unit` 5 failed（訊息長得像「路由沒掛上」），修後五條
一致指名 `fastapi.routing._IncludedRouter`，`create_app()` 照常起得來（OpenAPI 84 條）。
用白名單而非「`!= _IncludedRouter`」黑名單：黑名單只擋得住已經知道名字的那個容器。
（已知邊界：白名單只掃**頂層**節點——保證的是「不是已知葉節點」而非「我看得進去」。
若未來的延遲展開容器改成繼承 `Mount`／`Route`，白名單會放行而內容仍看不到 → 回到靜默
少報。已寫進 `_KNOWN_NON_API_ROUTE_TYPES` 的註解當已知邊界。）

**對帳單位是 `(path, method)` 不是 path**（複審追加）：19 支 router 的 106 條路由只塌成
83 條 path，用 path 對帳等於自願放掉方法級解析度——「掛上了 GET、掉了同路徑的
PUT/DELETE」會讓差集為空 → 記 ERROR 放行 → 那批寫入 API 全 404 而自我檢查一聲不吭。
快樂路徑本來就是逐 path＋method，這次把降級路徑（`_reconcile_with_framework` 問
OpenAPI 的那層）也拉到同一個單位，順帶把原本並存的三種「路由數量」單位收斂成一種。

另外 `pyproject.toml` 的 `fastapi>=0.115` 下界是**錯的**：程式碼用
`Depends(..., scope="function")`，而 `scope=` 參數是 0.121.0 才有的——
裝 0.115～0.120 任一版，`import ddm_v2` 直接 `TypeError`
（實測 0.120.4：`Depends() got an unexpected keyword argument 'scope'`）。
「宣稱支援但實際會 crash」的區間存在，本身就說明沒有人真的驗過下界。

**已修（2026-08）**：下界改成 `fastapi>=0.133,<1.0,!=0.137.0,!=0.137.1` ＋
顯式宣告 `starlette>=1.5.1,<2.0`。0.133 而非 0.121 的理由：0.121～0.132 把 starlette
釘在 `<1.0`，而 `tests/unit/test_cors_security.py` 的威脅前提（wildcard origin ＋
credentials 會鏡射任意 Origin）只有 starlette ≥ 1.0 成立（實測 0.47/0.48/0.49/0.50
都回 `*`）；0.133.0 是第一個放行 starlette 1.x 的 fastapi。實測：0.121.0 → 1 failed、
0.133.0 → 292 passed。

`starlette` 的下界最初訂在 **1.3.1**，決定性理由是資安而非相容性：
**CVE-2026-54283（form limits 在 urlencoded 分支被靜默忽略 → DoS）在本 app 是
pre-auth 可利用的**。`POST /api/v2/imports/upload` 宣告 `UploadFile = File(...)`，
FastAPI `routing.py` 先 `await request.form()`（~406 行）才 `solve_dependencies()`
（~457 行，`require_role("analyst")` 在那裡），而 starlette 依**實際** Content-Type
分派——攻擊者送 `application/x-www-form-urlencoded` 就走進沒有 limit 的 `FormParser`。
實測（未認證，5000 欄，預設上限 1000）：

| starlette | 回應 | 意義 |
|---|---|---|
| 1.0.0 | 401 | parser 全收了 5000 欄，之後才輪到認證＝limits 被忽略 |
| 1.3.0 | 401 | 同上（**1.3.0 還沒修**，所以那一格是 1.3.1 不是 1.3） |
| 1.3.1 | 400 | parser 先擋下＝limits 生效，且發生在認證之前 |

同時涵蓋 CVE-2026-48710（BADHOST 路徑授權繞過，≤1.0.0；本 app 不用
`request.url.path` 做安全判斷，故非直接可利用，但沒有理由停在受影響版本）。

**再抬到 1.5.1（複審追加）**：`FileResponse.max_ranges = 100` 是 **1.5.1 才加入**的
（逐版拆 wheel 比對 `starlette/responses.py`：1.3.1／1.5.0 沒有、1.5.1／1.6.0 有），
所以 `>=1.3.1` 允許解到的 1.3.1～1.5.0 **沒有 Range 數量上限**。本 app 的
`/assets/<bundle>.js`（`StaticFiles`）與 `/`（`FileResponse`）都是未認證可達：
`Range: bytes=0-0,2-2,…`（刻意不相鄰以避開 merge）會讓伺服器對檔案做上千次 seek/read，
再回一份每個 part 都帶 boundary 的 `multipart/byteranges`。實測（1 MB 檔、1500 個
range、~14 KB header）：

| starlette | 回應 | body | 耗時 |
|---|---|---|---|
| 1.5.0 | 206 multipart/byteranges（1500 parts） | 180 KB（13× 放大） | 0.46 s |
| 1.5.1 / 1.6.0 | 200（超過上限就整份送，單次循序讀） | 1 MB | 0.012～0.016 s |

O(n²) 在更早版本已修，所以是放大而非爆炸（Low）；抬下界的理由是
**「宣告的下界＝實際的保護」**——實裝 1.6.0 有這道上限而宣告落後於它，正是本節在講的病。
沒有再抬到 1.6.0：1.6.0 的新東西是 `RequestBodyLimitMiddleware`
（`starlette/middleware/body_limit.py`，1.5.1 沒有），本 app 沒在用；
為沒在用的功能訂下界就把下界變回「保守估計」。真的掛上它時再抬。

與 `fastapi>=0.133` 不衝突：fastapi 0.133／0.136／0.137.2／0.141.1 對 starlette 都只有
下界（`>=0.40.0`／`>=0.46.0`）沒有上界（拆 wheel METADATA 逐版查過）。
**本機 `.venv` 的 starlette 已同步從 1.0.0 升到 1.6.0**——宣告與實際脫節正是本節在講的病，
不能一邊修一邊複製它。

`python-multipart` 的下界同理，而且是**同一條 pre-auth 路徑上的同型缺陷**：
原本寫 `>=0.0.9`，但 CVE-2024-53981（GHSA-59g5-xgcq-4qw3）到 **0.0.18** 才修——
`<0.0.18` 在「最後一個 boundary 之後」的狀態機逐 byte 走，每個非 CR/LF 的 byte 都送一次
log event。攻擊路徑與上面 starlette 那條完全相同（同一個 `POST /api/v2/imports/upload`，
一樣在 `solve_dependencies()` 之前）。實測（200 KB 垃圾 epilogue，計 root logger 收到的
record 數）：

| python-multipart | log events | 耗時 |
|---|---|---|
| 0.0.9（原下界） | 200,000 | 0.93 s |
| 0.0.17 | 200,000 | 0.94 s |
| 0.0.18 | 1 | <0.001 s |
| 0.0.26（本機實裝） | 0 | <0.001 s |

外推：40 MB body ≈ 190 CPU-秒，全部發生在認證之前。改成 `>=0.0.18` 對現況零行為變更
（實裝 0.0.26），純粹是讓宣告與已知事實一致；fastapi 自己的 `standard` extra 也早就是
`python-multipart>=0.0.18`（0.133～0.141.1 逐版確認）。

### 為什麼這是系統性問題

- `pyproject.toml` 的 `requires-python`（`>=3.11`）與 CI（3.11）、Dockerfile
  （`FROM python:3.11-slim`）**是一致的**，沒有落差。
- 版本區間**有**上界，但對 0.x 套件形同虛設：`fastapi>=0.115,<1.0`。
  **FastAPI 還在 0.x，依慣例 minor 版就可以有破壞性變更**——這次 0.136 → 0.141 正是如此。
  `<1.0` 允許的區間橫跨數十個可破壞的 minor 版，等於沒有保護。
  `starlette` 更是連宣告都沒有（由 fastapi 遞移帶入），本機 1.0.0 → CI 1.6.0。
- `Dockerfile` 是 `pip install -e .`（無 lock），所以 **prod image 每次重 build 也會漂移**。
- 綜合起來：CI 與 prod 的行為隨上游發版變動，**同一份 commit 昨天綠今天紅**，
  而本機永遠複現不出來（本機 venv 是幾個月前裝的）。這次剛好只弄壞兩條測試，
  下一次可能弄壞的是行為。

**本次做了（下界）**：`fastapi>=0.133,<1.0,!=0.137.0,!=0.137.1` ＋ `starlette>=1.5.1,<2.0`
＋ `python-multipart>=0.0.18,<1.0`，每個數字都有 overlay／拆 wheel 的實測依據（見上）。
**上界刻意維持 `<1.0`**：0.x 的破壞性變更改由
`route_registry` 的結構偵測（不認得的節點型別就 `RouteTraversalUnsupported`）＋
`tests/unit/test_route_mounting.py` 的 OpenAPI 對照擋。把上界收成 `<0.142` 會讓
`pip install -e .`（CI 與 Dockerfile 都用它）在 fastapi 每次發版時**硬性解不出來**，
那個失敗模式比「大聲記 ERROR、服務照跑」更糟，而且必須有人手動追版才能解除。

**仍待決策（會影響 Docker build，不由本文件裁決）**：真正的 lock（例如 `pip-compile`
產生的 `requirements.lock`，CI 與 Dockerfile 都用它安裝）。下界修好只是把「宣稱支援
但會 crash」的區間消掉，**沒有**消除「同一份 commit 昨天綠今天紅」——那需要 lock。

### 順帶修掉的既有漂移

`scripts/preview_server.py` 自己抄了一份 router 清單，且**已漂移成少掛
`ai_review`／`parse_jobs`／`wi_context` 三支**——而 e2e 打的正是 preview server，
等於**預覽的 API 面與正式 app 不一致**。已改為與 `main.py` 共用同一份清單
（`api/route_registry.py`），兩邊 OpenAPI 的 `(path, method)` 集合完全相同
（107 條 operation／84 條 path，差集雙向皆空）。

這個「差集為空」由 `test_preview_server_exposes_the_same_api_surface` 釘住，不是靠人工
比對：原本只有一條 AST 測試斷言 preview **沒有**自己列 `include_router`，那是單向的——
mutation 實測把 `mount_v2_routers(app)` 整行換成 `pass`，17 條測試全綠，預覽會變成
一個只有前端、零 API 的服務。新測試在同一個 mutation 下紅（少 106 條 operation）。

---

## 10. CI 現況：稽核當下是紅的，本次已修（雙重故障）

> **狀態：兩個故障點都已在本批修復。** 以下保留診斷過程，因為它解釋了 §5.2 的漂移為何能存活，
> 也是「守衛測試存在 ≠ 守衛有在跑」這個教訓的證據。

`gh run list` 顯示 **2026-08-04 起連續 6 次以上全部 failure**（含 `202606-rc1/alpha/frontend-refactor`
與已刪除的 `github/` 前綴分支）。最新一次兩個 job 都掛在同一個步驟「Migrate + seed」。

逐層實測定位（用全新空資料庫 `ci_probe`）：

| 步驟 | 結果 |
|------|------|
| `alembic upgrade head`（空 DB → v2_0034） | ✅ 正常，10 個 migration 全套用 |
| `scripts/dev_seed_v2.py` | ❌ **`AttributeError: 'coroutine' object has no attribute 'name'`** |
| `scripts/dev_seed_templates.py` | ✅ 16 筆（但其中 1 筆帶 V1-only 的 `x_scan`，見下） |
| `scripts/dev_seed_30rows.py` | ✅（修正 `x_scan` 後） |

**根因：`src/ddm_v2/seed/v2/policy_seed.py` 的同步／非同步錯配。**
`seed_modeling_policy_factory_v1` / `seed_level_policy_factory_v1` 宣告為 `def`（同步），
卻對 AsyncSession 呼叫 `session.get(...)`——回傳的是 coroutine，於是：

1. `existing is not None` **恆為真** → 永遠走「已存在」分支 → **從不建立任何列**；
2. 回傳的 coroutine 被呼叫端當成 ORM 物件使用 → `mp.name` 當場 `AttributeError`；
3. `seed_policy_factory_v1` 的型別註記 `tuple[ModelingPolicyVersion, LevelPolicyVersion]` **在說謊**。

進入版本：`474a6f0`（R2a，2026-08-11），與本稽核的 AI 批次同一批。
唯一呼叫端是 `scripts/dev_seed_v2.py`（migration `v2_0030` 另有自己的 SQL 種子，
所以正式資料不受影響——但 CLAUDE.md 記載的 dev 環境建置第二步是斷的）。

**✅ 已修**：三個函式改為 `async def` + `await session.get(...)`，型別註記從 `session: Any`
改成 `AsyncSession`（原本的謊言同時存在於註記與同步／非同步形狀，兩者都已修正）。
實測全新空 DB 四步全過：`alembic upgrade head` → `dev_seed_v2.py`（`policy manifests:
MODELING_FACTORY_V1 LEVEL_FACTORY_V1`）→ `dev_seed_templates.py`（16 筆）→
`dev_seed_30rows.py`（30 列 / 1291.9 TMU）。新增 `tests/integration/test_policy_seed.py`
守住兩條分支——其中「列不存在時真的建立」這條分支**在修好之前根本到不了**。

**另一個獨立問題（CI 後端 job 即使 seed 修好也還是紅）：**
`.github/workflows/ci.yml` 的後端測試步驟是 `pytest -q`（unit + integration 一起跑），
但 `tests/unit/test_search.py` 與 `tests/integration/test_search.py` **同名**且兩目錄皆無 `__init__.py`
→ `612 tests collected, 1 error` → `Interrupted: 1 error during collection`。
CLAUDE.md 早已記載「unit 與 integration 必須分開跑」，CI 卻沒照做。

**這才是 §5.2 的 FK 漂移能存活的真正原因**——不是「checkpoint 只跑子集」，
而是 **CI 的後端測試步驟從 `test_search.py` 出現（2026-07）起就整個沒跑過**。
（初稿把成因診斷為前者，是錯的。）

> 也就是說：修好 seed 之後 CI 仍然一句測試都不會跑，**兩個都要修**。

**✅ 已修**：`ci.yml` 的後端測試步驟改為兩段式 `pytest tests/unit` + `pytest tests/integration`
（與 CLAUDE.md 既有結論一致，且讓 unit／integration 的失敗歸因在 CI log 裡分開）。
選擇兩段式而非補 `__init__.py`，是因為後者會為了修一個檔名衝突而悄悄改動全部 612 個測試的
模組命名與 import 語意。`docs/CI_GATES.md` 的後端 job 描述與「本機快速重現 CI」區塊同步更新
（兩處原本都還寫著 `pytest -q`）。

---

## 11. P0：R1 樂觀鎖的 CAS 路徑讓三個端點回 500（✅ 已修）

這是本次稽核最嚴重的發現，與 legacy/引擎無關。**已修復並補上 7 條迴歸測試**，
`pytest tests/integration` 從 407 passed / 1 failed 變成 **415 passed / 0 failed**。

### 根因

`services/v2/worksheet_revision.py` 的 `bump_worksheet_revision()` 在 flush 之後呼叫
`session.expire_all()`——目的是避免舊 `revision_no` 被 flush 蓋回（R1 checkpoint 記錄的「ORM expire fix」）。
但 `expire_all()` **失效的是 session identity map 裡的每一顆物件**，不只目標 worksheet。
呼叫端手上握著的任何 ORM 物件都變成 expired，下一次屬性存取觸發同步 SELECT →
在 async 情境下就是 `sqlalchemy.exc.MissingGreenlet`。

**因果證明**：把 `Session.expire_all` monkeypatch 成 no-op、其餘不動 → 該測試 `1 passed`。

### 三個已重現的線上影響

| 端點 | 觸發條件 | 結果 |
|------|----------|------|
| WI Set 專案實體化 | 專案含 **≥2 筆 WI** | 500。第 2 圈迴圈存取已 expired 的 `item` |
| `POST /worksheets/{id}/rows/from-module` | **帶** `base_revision`（R1 正式 CAS 路徑） | 500 |
| `POST /imports/{id}/submit` | **帶** `base_revision`——**前端 `ImportModal.tsx` 實際就是這樣送的** | 500 |

不帶 `base_revision` 的 legacy 路徑之所以僥倖能過，是因為它在 `expire_all()` 之後
還多做了一次 `session.get(MostWorksheet, ...)`，順手把呼叫端的物件刷新回來。
**CAS 路徑 `expire_all()` 後直接 return，物件一直是 expired。**

### 為什麼測試沒抓到

- WI Set 的 happy path 斷言 `imported_wi_count == 1`——**迴圈永遠不會進第 2 圈**。
  而「專案可以放多個 WI」正是這個功能存在的全部理由。
- 四個 `bump_worksheet_revision` 呼叫點中，只有 `worksheet_service.save_worksheet` 寫對了
  （bump 後明確重取 `ws`）——**而那正是唯一有 `base_revision` 整合測試的那一個**。
- R1 的 code review 把「import/CAS 測試可後補」列為 **nit** 並 APPROVE_WITH_NITS。
  那個「可後補」的 nit，就是這三個 500 的藏身處。

### 修復方式

改成 `session.refresh(ws, attribute_names=[...])`——**只重讀被 Core UPDATE 改過的那幾個欄位，
且在 `await` 內完成**。四個候選方案的取捨（皆經實測，非紙上推論）：

| 方案 | 防 stale | 不誤傷 | 否決理由 |
|------|:---:|:---:|------|
| `session.expire_all()` | ✅ | ❌ | 原況；誤傷全 session |
| `session.expire(ws)` | ❌ | ✅ | expire 只是「下次再載」，async 下那個「下次」仍是同步 IO——把雷從呼叫端移到自己腳下 |
| 整顆 `refresh()` / `get(populate_existing=True)` | ✅ | 半 | **實測**會連已載入的 relationship（`rows`／`process_version`）一起 expire，換個欄位埋同一顆雷 |
| **`refresh(ws, attribute_names=[...])`** | ✅ | ✅ | **採用**。只碰被 Core UPDATE 改過的欄位，成本是一次 PK SELECT |

欄位清單抽成模組常數放在 UPDATE 的 SET 清單旁邊，讓「改了 SET 卻忘了改 refresh」這個
維護風險是看得見的。

### ⚠️ 對失效機制的更正（實測推翻了 R1 worklog 的描述）

R1 checkpoint 記的是「舊 revision 被 flush **蓋回**」。實測證明**這個形態在 SQLAlchemy 2.0
下不成立**：ORM 的 UPDATE 只包含有 history 差異的欄位，identity map 握著舊 `revision_no`
並不會在 flush 時把它寫回；連明寫 `ws.revision_no = <stale>` 也不會產生 UPDATE
（committed state 就是那個值，net history 為空）。全 repo 也沒有任何一處對 `.revision_no`／
`.content_hash` 做 ORM 賦值。

**真正可觸發的是 stale read**：`read_worksheet()` 的 `revision_no`／`content_hash` 是直接讀
identity map 那顆 ORM 物件的，而 `from-module` 與 `imports/submit` 的回應 revision 就來自
那份 snapshot。不同步 → **回舊 revision 給 client → client 拿它當下次的 `base_revision`
→ 之後永遠 409**。比 lost update 更難發現，嚴重性相當，而同一個修法把兩者一起解掉。

`set_content_hash()` 是同一個失效模式的另一個欄位，而且原本**連 expire 都沒有**——
`wi_set_service.instantiate_project` 迴圈第 2 圈的 `read_worksheet` 就會讀到舊 hash。
今天沒出事只是因為 `content_hash_from_read()` 不吃這個欄位、回應用的是本地變數，
是巧合不是設計；且拿掉 `expire_all()` 後這個 stale 會**更持久**。已一併修。

### 迴歸測試

涵蓋：bump 同時滿足「目標同步」與「不誤傷其他物件」、衝突路徑的 `current_revision` 必須是真值、
`set_content_hash` 同步、`from-module` 帶 `base_revision` 的成功 + 409、
`imports/submit` 帶 `base_revision` 的成功 + 409、WI Set 實體化 **3 筆** WI
（不只 2 筆，讓迴圈確實跑滿）。

**mutation 驗證結果（M0 ＝ 把 `worksheet_revision.py` + `worksheet_service.py` 還原成 `f19e501`
的字面原始碼，也就是真正的 bug）：新增測試中有 5 條會紅，2 條不會。**

初稿寫的「7 條皆通過 mutation 驗證」與「改回 `expire_all()` → 3 紅」都不成立：
前者把「對某種 mutation 會紅」誤述成「對真 bug 會紅」；後者是只把 mutation 施加於
`bump_worksheet_revision` 的數字，還原成 `f19e501` 字面原始碼實際是 **6 紅**（含既有的 rollback 測試）。

> 這一段本身就是「**稽核文件裡的數字必須附上可複現的條件**」的反面教材——
> 初稿在同一節寫下這條規則，卻在下一行違反它。數字要標明 mutation 的**施加範圍**與**基準版本**。

被判定為零獨立覆蓋的那條測試**已刪除**：它的主張句（「bump 後的 revision_no 被 stale 的
ORM 狀態蓋回去了」）在**每一種** mutation 下都通過，因為那個失效形態在 SQLAlchemy 2.0 下
結構上不可能發生；它唯一會紅的斷言是另一條測試的複本。原處留了一段**負向知識註解**
說明「刻意不寫這型測試」與理由，避免下一個人再加回來。

### 補上核心設計約束的守衛，以及過程中發現的一個測試陷阱

`attribute_names=` 窄化原本**零測試覆蓋**——把它換成整顆 `refresh(ws)`，415 條全綠。
已補一條守衛測試，並附 mutation 證據（整顆 refresh → 紅、窄化 → 綠）。

> **陷阱（值得記住的通則）：** 該守衛測試的**第一版在 mutation 下是綠的**，差點又是一條假測試。
> 原因是 SQLAlchemy 2.0 會把載入時的 loader options 記在 `InstanceState.load_options`，
> 並在整顆 `refresh()` 時**重放**——所以用 `selectinload(...)` 直接載入物件的 setup
> 會把 bug 遮掉。正確的 setup 必須比照真實呼叫點：先 `session.get()`
> （此時 `load_options` 是空的），再讓 relationship 被填充。
>
> 通則：**測試的 setup 若與生產路徑取得物件的方式不同，可能無意間關掉待測的失效模式。**
> 這也是為什麼「新測試必須附 mutation 證據」不是形式要求——這條測試就是靠它才沒有假綠。

### ⚠️ 這個 P0 一直有測試在抓，只是紅燈被容忍

`test_instantiate_runtime_failure_rolls_back_worksheet_and_prior_rows` 本來就跑 2 筆 WI 的迴圈，
它從 R1 落地起就是紅的，並且被帶進分支。所以 WI Set 那一路嚴格說**不是「沒測到」，
是「測到了沒人理」**——這是 §9 第 17 項（CI 紅燈無人看）的直接證據，
也讓「補測試」這個結論本身不完整：**沒有人看的紅燈，等於沒有測試。**

該測試現已轉綠且斷言一字未動；既有 happy path 的 `imported_wi_count == 1` 保留（新增而非弱化）。
