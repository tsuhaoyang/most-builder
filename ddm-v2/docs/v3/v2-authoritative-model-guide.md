# v2 權威模型與反 Legacy 開發守則（2026-07-19）

> **目的**：彙整 v3↔v2 深度對照（Playwright 實操＋DB 實測＋版本模型審查）的結論，
> 定義 v2 的**權威模型**與**禁止的 legacy 模式**。任何 agent/工程師動 v2 前必讀。
> 關聯：ADR-014（值權威）、ADR-020（SIMO）、ADR-021（IA）、ADR-022（兩層工作台）、
> `v3-to-v2-migration-audit-202607.md`（缺口總帳）。

## 1. 版本語意（本次審查的核心裁定）

**v3 心智模型（權威）：「版本」只留給規則值權威（字典），全系統單一 active；
業務產出（案件/模組/WI）是「文件＋狀態機＋快照留痕」，不是版本鏈。**

| 物件 | 權威語意 | v2 現況 | 禁止的 legacy 模式 |
|---|---|---|---|
| 規則值（rule_sets） | 單一 active、clone-draft→發布前驗證→原子切換 | **無 is_active 欄**；V1/V2 同時 published；`catalog_service.py:127`、`worksheet_service.py:58` **寫死 V1** 與 `schemas/v2/most.py` 的 DEFAULT V2 矛盾 | ❌ 在程式碼寫死 rule-set code 當預設——一律讀 active（待 P2 批次補旗標） |
| 分析案件（process_versions） | 案件=平面清單＋狀態機（draft→approved→retired）；重分析=退回改或顯式另存 | 案件≡版本鏈（每 SKU v1,v2,…遞增），**案件清單直接 SELECT 每一版** | ❌ 把版本當案件展示；❌「新建案件」默默在既有 SKU 上 +1 版（NewCaseModal 曾自動預選第一個 SKU） |
| 動作/WI（motion_modules） | ADR-022：不可變版本＋current_version 指針＝正確設計，**保留** | ✅ 已對齊 | ❌ 回頭在 rows 上做可變 UPDATE |
| 消費端快照 | case/cycle 記錄使用的版本 id | ✅ 兩邊等價 | — |

**版本爆量事後剖析**（2026-07-19 已清理）：demo SKU 曾累積 279 版，其中 268 筆
（draft 226/approved 36/retired 6）具精確測試簽名（`source_version_id IS NOT NULL
AND created_by='IEC141289' AND created_at∈[07-07,07-14)`）＝測試隔離改造
（17661cc）前 integration clone 直接落盤的殘留，爆量恰停在隔離落地日。已刪，
餘 11 筆真實 demo。**教訓：integration 測試永不落真實 DB（CI_GATES 3b）。**

## 2. 工作台兩層模型（ADR-022，摘要）

- 動作（category='action'，單列素材）→ 勾選建 WI（category='wi-template'，
  rows=快照複本 copy-on-write）→ WI 大綱管理/Inspector 微調 → WI 專案建立組專案
  → 分析案件工時表「從 WI 庫插入」實體化
- ❌ 禁止：新增頂層 tab、恢復三層實驗頁（WI 組成/製程途程已刪）、前端計算或
  捏造 TMU/快照（一律後端 computed 持久值）

## 3. 使用者/身分模型

- v2 身分=員編（gateway header JIT），v3=email+密碼——**架構差異，非缺口**
- app_users 測試殘留治理：cleanup 腳本 pattern 已含
  `ZZZ%/SMTEST_%/GAPTEST_%/GAP_APPROVER_RETIRE_%/UT_TESTUSER_%/UT_AUDIT_%/TESTIE%/EMP_FROM_LB`
- dev_seed 示範帳號（IE0001/IE0002/MGR001）保留供 RBAC 測試；要移除須同步改 seed
- ❌ 禁止：測試以真實 DB JIT 建 user（走 rollback 隔離 fixture）

## 4. 工作台互動級差距（2026-07-19 Playwright 實操 v3 確認，待補批次）

| 互動 | v3 實測行為 | v2 現況 | 優先 |
|---|---|---|---|
| 清單行內頻率 | input-number，改值**即時後端重算持久化**（154.333→Eff 308.666 實測） | 唯讀文字（要開 Inspector） | P1 |
| SIMO 配對 | 動作清單行內 checkbox（v3 動作清單是平面 row 列表，列與列可配對） | **語意不同，非缺口**：v2 兩層模型下 action=單列素材，清單內無配對對象；SIMO 屬 WI 內部（rows 之間）→ 正確歸屬是 **WI 大綱子列/Inspector**（目前唯讀，P1 補可編輯） | P1（改於 WI 層） |
| 清單語意 | **我的動作**（owner 過濾，個人工作素材） | 所有可見（共享池） | P1：加「全部/我的」篩選。**預設「全部」**——搬遷的 29 條認證庫為 global scope，預設「我的」會是空清單；待各使用者累積個人素材後再議預設值 |
| 清單拖曳排序 | drag handle（個人清單有序） | 無（池無序） | P2（隨「我的」語意一起） |
| 已選浮動列 | 已選 N 筆 · TMU/秒合計 | 只有筆數 | P2 |
| 每列 WI 語句覆寫 | user_edited per row | 單一覆寫欄 | P2 |

## 5. rule-set 治理缺口（P2 實施規格）

1. `rule_sets` 加 `is_active`（partial unique index `WHERE is_active`）；
   `publish` 改 v3 語意：發布前完整性驗證（每參數至少一啟用選項）＋
   原子「deactivate 其他＋activate 自己」
2. `catalog_service`/`worksheet_service` 寫死 V1 → 改讀 active（同時解決
   「案件編輯器 V1/工作台 V2 分裂」的懸案）
3. 選項級編輯端點（教學型格位介面若要編值會需要）；archive 端點
4. `version_no` 產號 `COUNT+1` → `MAX+1` 帶鎖或 sequence（併發撞 unique 500）

## 6. 案件清單收斂（P1 實施規格）

- `cases_service.list_cases` 以 SKU（×model_label）聚合：每案件呈現最新版＋
  可展開歷史折疊（`worksheet_service._version_info` sibling 查詢可直接餵）
- 版本鏈資料保留（v2 相對 v3 的稽核優勢），只是 UI 不再一版一列
- NewCaseModal：同 SKU 已有版本時引導「另存新版/繼續編輯 draft」，
  不自動預選第一個 SKU
- CI 守衛：integration 跑完 `process_versions` 計數不變（隔離迴歸保險絲）

## 7. 禁止清單（速查）

1. ❌ 寫死 rule-set code 當預設（讀 active）
2. ❌ 案件清單一版一列；「新建案件」默默 +1 版
3. ❌ 前端計算/捏造 TMU、快照、句子（後端 computed/narrative 權威）
4. ❌ 新增頂層 tab 或恢復三層實驗頁
5. ❌ 測試落真實 DB（rollback 隔離；跑兩遍計數不變）
6. ❌ **無法變紅的測試**（本 session 已重複出現四次，每次都由 code-review 攔下）：
   - ❌ `[SPEC GAP]` 型：斷言「缺口存在」而綠燈
   - ❌ **skip 條件是被測程式的回應**（例：`if r.status_code == 500: skip("資料未種")`
     ——而 500 正是該端點壞掉的表現，真回歸會變 skip 不會變紅）。
     **skip 條件必須是資料前置條件**（例：`if not await _seeded(db): skip(...)`）
   - ❌ 只做讀取卻宣稱防寫入回歸（例：只 GET 然後斷言計數不變）
   - ❌ 斷言太寬而失去鑑別力（例：`assert rows == []`、`assert tmu > 0`
     ——把被測邏輯改回錯誤版本仍會綠）
   - ❌ **多重條件下的空洞通過**：斷言 409 但目標同時滿足兩個 409 條件時，
     須斷言 `detail.code` 才能證明是預期那道 gate 攔的
   - ✅ **規則：每個宣稱防回歸的測試，交付時須附「非空洞性證明」**——把對應
     修正/gate 還原後貼出該測試的失敗訊息。**無法變紅的測試等於沒有測試。**
7. ❌ UI reference 用 html_con（母版=ddm-v3 畫面＋ADR-021/022）
8. ❌ 靜默 fallback/夾檔/吞錯（no-error-bypass；不確定就 422）
9. ❌ **agent 執行 repo-wide `git stash`**（並行席位常在寫檔，會吞掉他人在途工作）。
   要比對基線請用 `git stash push -- <限定路徑>`、`git show HEAD:<file>` 或
   `git diff HEAD -- <file>`。2026-07-19 曾發生（無損失，主動揭露）。
