# ADR-027: Domain Evolution 版本軸與 AI Readiness 資料地基

**狀態：** accepted（2026-08-10，User 核可）
**日期：** 2026-07-31
**關聯：** [ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（加法演進）、
[ADR-013](ADR-013-excel-import-architecture.md)（staging）、
[ADR-023](ADR-023-dictionary-governance-unification.md)（rule-set 回放）、
[ADR-025](ADR-025-import-template-matching-p2.md)（匯入信任邊界）、
[ADR-026](ADR-026-wi-ai-parser-pipeline-boundary.md)（AI bounded context）、
[Domain Evolution 與 AI Readiness 規格](../architecture/domain-evolution-and-ai-readiness-spec.md)

## 脈絡

ddm-v2 第一版 MOST 工作台與 Level System 仍在演進，後續可能增加正式工序資訊、建模 policy、
Level 限制與批次 AI。現行資料模型已能以 `most_cycles.slot_inputs + rule_set_id` 回放 MOST，
但仍有五個缺口：

1. 同一 draft worksheet 沒有內容 revision，並行存檔與非同步 AI 採用可能覆蓋較新內容。
2. Level R1–R9 與 LB output 沒有 policy/validator/contract version，規則改版後缺歷史驗證證據。
3. Quantity、工具持有、SIMO、inspect/default 等 modeling policy 可能藏在 prompt 或 service code。
4. 正式 method context、MOST 計算輸入與 AI metadata 尚未有明確儲存分界。
5. `excel_imports.staged_rows` 整批 JSONB 不適合 row-level retry/cancel/progress/multi-action lineage。

若先做完整 LLM/批次服務再補這些地基，將無法證明結果使用哪版 domain 規則，也無法安全處理
stale result。若等待所有業務邏輯永遠固定才開始，又會錯過建立 gold baseline 與真實回饋資料。

## 決策提案

### 1. 版本拆成正交軸

下列版本不得互相冒充：

- `process_version`：業務發布與 clone 生命週期；
- `worksheet_revision`：同一 draft 每次成功存檔；
- `rule_set_id`：MOST option/band/TMU 回放；
- `modeling_policy_version`：quantity/tool/SIMO/default 如何 compile；
- `level_policy_version`：Level validator 與 LB output contract；
- `schema_version`：跨邊界 payload shape；
- `deployment_bundle_id`：模型/prompt/index/calibrator/threshold。

正式 parse/compile/validation evidence 必須保存所使用的版本 reference。

### 2. Worksheet 使用 revision optimistic locking

- `most_worksheets` 加單調遞增 `revision_no`。
- Save request 帶 `base_revision`，server 原子 compare-and-increment。
- Stale write 回 409，且不得先刪 rows。
- AI run 保存 source revision；revision 不一致時不得自動套用。

### 3. 建模與 Level policy 使用 immutable manifest

- 新增 versioned modeling policy manifest，管理非 TMU 的 compile 決策。
- 新增 versioned Level policy manifest，識別 validator revision、config 與 output contract。
- 現行行為 seed 為 V1 manifest，不在本 ADR 中把 R1–R9 重寫成規則 DSL。
- Worksheet snapshot policy；歷史 replay 不依今天 active/default。
- Level validation 以 append-only run 保存 revision、policy、issues 與 output evidence。

### 4. 三類資料分離

- `slot_inputs` 只保存 MOST 計算原始輸入。
- 正式 method context 使用版本化 schema 的獨立 context storage；需要 FK/查詢/約束時升為正式欄表。
- AI inference/candidate/score/prompt/latency 使用 AI operational store，不寫入正式 method/cycle/Level。

### 5. DDM 採用事實以 review event + transactional outbox 發布

- 正式 worksheet save 與 review/outbox 在同一 DDM transaction。
- AI consumer at-least-once，以 event id 去重。
- AI service 不參與 distributed transaction，不直接寫 DDM 正式表。
- `workflow_audit_log` 保持低頻 workflow transition，不承載高頻 AI feedback。

### 6. Batch staging 以加法正規化

- 保留 ADR-013/025 的 upload/map/template preview/IE adoption。
- 批次 AI 上線前新增 stable `import_rows` 與 durable parse job/item。
- 過渡期雙寫/相容組裝，不直接刪 `staged_rows`。
- Dedicated worker 承載 durable work；FastAPI `BackgroundTasks` 不作數百列 job queue。

### 7. AI 先邏輯隔離，達條件再物理拆分

- 初期同 monorepo/in-process adapter，contract 與 ownership 先固定。
- GPU/大型依賴、SLO、release cadence、scaling 或資料落地需要時，再抽 `wi-ai-api/worker`。
- 初期共用 PostgreSQL cluster 但以 schema/role 邏輯隔離；獨立 database 是後續部署決策。

## 考慮過的選項

### A. 先凍結全部 schema，再開始 AI

Domain 不可能一次完整預測，會阻塞真實資料與 gold baseline。否決。

### B. 所有未定資訊放 JSONB，AI 直接寫 worksheet

短期快速，但 ownership、FK、查詢、回放與稽核失控；`slot_inputs` 會變成不相容資料集合。否決。

### C. 立即拆獨立 repository/database/microservices

模型與 domain contract 都尚在演進，過早增加跨 repo/deploy 協調與 distributed consistency。否決作為
第一步，保留為負載與治理成熟後的目標形。

### D. 契約穩定、schema 加法演進、版本軸分離、邏輯先隔離（提案）

能在核心繼續演進的同時建立可回放地基，並將物理拆分延後到有實際需求時。

## 後果

### 好處

- Stale save/AI apply 可機械拒絕。
- MOST、建模 policy、Level policy 與模型版本可獨立演進及回放。
- 同一 WorkInstructionPlan 可換 policy recompile，不必重呼叫 LLM。
- 批次有 row-level lineage、retry/cancel/partial submit。
- AI failure 不影響手動 MOST/Level 核心。

### 代價

- 增加多個 manifest/reference 與 migration batches。
- Save API/前端需處理 409 conflict。
- Level publish 增加 latest valid run gate。
- AI operational/event/outbox 需要 retention、權限與清理治理。
- 過渡期會有 `staged_rows` 與 `import_rows` 雙寫/相容成本。

## 不由本 ADR 決定

1. Modeling policy 的實際 IE 規則內容。
2. Level v2 新增哪些限制。
3. 外部/地端 LLM 與模型選型。
4. PostgreSQL queue 或企業 broker 的最終選型。
5. AI raw data retention 與跨 site 可見性。
6. ADR-025 stub submit 的退役時間。
7. AI bundle/policy 的最終核准角色。

上述項目在實作對應 phase 前另行核可。本 ADR 已於 2026-08-10 accepted；實作仍須依 phase
切片（L4 先 jobs／import_rows；worksheet revision／policy manifests／outbox 依 roadmap 分批）。
