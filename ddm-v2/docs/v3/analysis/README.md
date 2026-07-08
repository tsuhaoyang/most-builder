# analysis/ — v3 全功能分析與可執行規格庫

> **目的**：把 v3（IE 開發、IE 認證）的**全部功能與核心邏輯**萃取成「其他 AI 讀了就能實作」的可執行文件。萃取自程式碼（非 v3 文件）；正文為裁決後的「應然」規格，v3 原始行為以「（v3 實況）」註記，**bug 不入規格**。
> **先讀**：[00-methodology-and-issues.md](00-methodology-and-issues.md)——萃取方法論＋不合理設計討論清單（DISC-01~15；**DISC-01 已定案＝二代三層為 canonical**，餘 DISC-12/15 待裁決）。

## 分類一：core-logic/（核心邏輯——實作任何功能前必讀）

| 文件 | 內容 |
| --- | --- |
| [CL-01](core-logic/CL-01-sequence-model-and-tmu.md) | 序列模型七格、各參數 TMU 演算法、repeat、精度、黃金值 |
| [CL-02](core-logic/CL-02-sentence-generation.md) | 口語句生成：slot 片段、P display_rule 三態、整句模板、系統句/人工句雙欄 |
| [CL-03](core-logic/CL-03-dictionary-data-model.md) | 字典資料關聯：版本→模型→slot→選項→語彙、生命週期、v2 rule-set 對映 |
| [CL-04](core-logic/CL-04-aggregation-and-time.md) | 列合計、frequency、SIMO（配對 UX＋group-max）、normal/standard 時間鏈 |

## 分類二：features/（功能規格——可獨立分派給 AI 實作）

| 文件 | 功能 | 收斂狀態 |
| --- | --- | --- |
| [F-01](features/F-01-workbench-sequence-editor.md) | 工作台序列編輯器（試算迴圈、SlotModal、模型切換） | canonical |
| [F-02](features/F-02-mi-statement-composition.md) | MI 語句組合（快照子項、微調、重聚合） | 一代→併入 F-03/組件庫 |
| [F-03](features/F-03-three-tier-assembly.md) | **三層組裝**：模組→WI 範本→製程途程＋apply-back | **canonical（DISC-01 ✅ 定案）** |
| [F-03b](features/F-03b-snapshot-design-and-apply-back-spec.md) | **快照設計與 Apply-Back 規格**（F-03 補件）：Snapshot vs Live Reference 決策、apply-back 影響範圍確認、版本不可變、AddWI bug 修正、WILibraryItem 死欄位清理 | 2026-07-08 新增 |
| [F-04](features/F-04-wi-set-projects.md) | WI Set 專案（搜庫收集、度量）——⚠️ WI 庫只含 MiStatement（C-13） | 一代→併入 L3/worksheet |
| [F-05](features/F-05-nl-draft.md) | NL 快速預填（badge、覆蓋/補空、治具防護） | canonical |
| [F-06](features/F-06-dictionary-management.md) | 字典管理（匯入/clone/選項 CRUD/同義詞/publish） | canonical |
| [F-07](features/F-07-approval-workflow-and-report.md) | 審核工作流＋xlsx 報表（掛 ProcessVersion——DISC-04 修正） | canonical |
| [F-08](features/F-08-auth-rbac-users.md) | 五角色 RBAC 與使用者管理（身份改走 LB 閘道） | canonical |

## 分類三：UX 設計規格

| 文件 | 內容 |
| --- | --- |
| [UX-design-spec.md](UX-design-spec.md) | **v3 UX 設計規格**（使用者親自設計）：全域殼層、工作台佈局、SlotModal、WI Pool、v2 vs v3 差異對照、移植優先順序、10 條不可改動 UX 規則 |

## reference/（萃取證據底稿，唯讀）

[api-inventory-workbench.md](reference/api-inventory-workbench.md)（50+ endpoints 全合約）｜[api-inventory-dictionary-workflow.md](reference/api-inventory-dictionary-workflow.md)｜[frontend-usage-flows.md](reference/frontend-usage-flows.md)（IE 操作流）

## 給實作 AI 的執行守則

1. 讀你的 F 文件＋其引用的 CL 文件即可動工；endpoint 細節查 reference/。
2. 值表只認 [impl-01](../impl/impl-01-rule-set-factory-v2.md)；計算只准呼叫 `most_engine`（禁止重複實作 CL-01/04——DISC-03）。
3. API 拒收 client 端 TMU（DISC-02）；所有寫入走 [[backend-v2]]/[[database-v2]] 紀律；改核心邏輯先讀 [[ie-most-engineer]] 並跑黃金測試。
4. 每個 F 文件的驗收條件（Given/When/Then）＝最低測試集，實作未附測試不得視為完成（[[testing-ci-hard-rules]]）。
