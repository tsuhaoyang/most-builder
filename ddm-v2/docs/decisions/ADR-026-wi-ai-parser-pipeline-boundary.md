# ADR-026: WI AI Parser 獨立管線與 MOST 權威邊界

**狀態：** proposed（待 User/架構核可）
**日期：** 2026-07-30
**關聯：** [ADR-013](ADR-013-excel-import-architecture.md)（批次 staging）、
[ADR-014](ADR-014-v3-dictionary-as-value-authority.md)（值權威）、
[ADR-015](ADR-015-nl-parsing-in-scope.md)（DraftParserPort 與建議層）、
[ADR-016](ADR-016-search-infrastructure.md)（語意檢索）、
[ADR-023](ADR-023-dictionary-governance-unification.md)（rule-set 回放與 active）、
[ADR-024](ADR-024-master-data-vs-dictionary-boundary.md)（字典/主數據分界）、
[ADR-025](ADR-025-import-template-matching-p2.md)（匯入 template 建議與 IE 信任邊界）、
[ADR-027](ADR-027-domain-evolution-versioning-and-ai-readiness.md)（後續版本軸與資料地基提案）、
[WI AI Parser 系統規格](../architecture/wi-ai-parser-system-spec.md)

## 脈絡

ddm-v2 已有 rule-based `DraftParserPort`、`/worksheets/nl-draft`、DB synonym 與搜尋基礎設施，
但目前只能將一段文字映射到固定 GM-shaped slots，尚未處理：

- 一句拆成多個原子動作；
- 工具取得/持有/使用與數量展開；
- LLM、embedding、reranker 的模型依賴與版本；
- 數十至數百列匯入的背景工作；
- 人工修正、評測、校準與版本 promotion。

這些能力的執行特性與 DDM 核心 API 不同：模型服務可能需要 GPU、較長 timeout、獨立 scaling
及資料落地政策；批次解析需要 queue、retry、cancel 與 row-level progress。同時，MOST 工時標準
屬可稽核資料，不能讓 AI pipeline 形成第二套 TMU 或 sequence 規則權威。

## 決策提案

### 1. WI AI Parser 建立為獨立 bounded context

- 初期可在同一 monorepo 以獨立 package 與 in-process adapter 開發。
- 從第一版起使用版本化 request/response contract，不依賴 DDM ORM。
- 模型依賴、推論、檢索、信心、評測與 feedback dataset 歸 AI bounded context。
- 當 LLM/GPU 或批次需求成熟後，可抽成 `wi-ai-api` 與 `wi-ai-worker` 容器，不改 DDM domain contract。

### 2. DDM 保留 deterministic compiler 與最終權威

- AI 輸出 MOST-neutral `WorkInstructionPlan`、合法 slot candidates、confidence 與 provenance。
- Action plan → GM/CM `CycleIn` 的 deterministic compiler 留在 DDM。
- Compiler 只將正規化後的原始 cm/deg/revolutions 等值寫入 cycle；A/M band/ladder selection
  仍由 `most_engine` 依指定 rule-set 負責，不得在 compiler 複製規則表。
- AI 不計算 TMU、不寫 worksheet、不發布 motion module、不修改 active rule-set。
- 任何採用結果都必須通過 DDM schema、指定 rule-set 與 `most_engine.compute_cycle()`。

### 3. 互動與批次共用解析核心

- 互動式入口使用同步 parse contract。
- CSV/Excel 使用相同 row parser/compiler，由背景 job orchestration 管理。
- 不建立「快速但較弱」的批次 parser；一個 source row 可展開成多個 actions/cycles。
- ADR-025 的 standard template matching 保留為同一候選管線的 L0 完整 cycle candidate；既有
  `map` 預覽、逐列 IE 採用與 active rule-set 重算邊界不變。
- 在 ADR-025 被明確 accepted replacement 取代前，**每一個 template 命中列仍須由 IE 在 preview
  逐列核對/採用**；L0 表示候選完整度，不表示可跳過人工信任閘門或自動落地。
- Template/AI 輸出始終只是 candidate；任何 batching、confidence threshold 或 deployment bundle
  都無權繞過 ADR-025 的逐列人工採用 gate。
- 新 parse job 先以加法 enrich 接入；任何要取消未採用列 stub 或改變既有 `/submit` 語義的
  變更，必須另經 accepted 決策，不由本 proposed ADR 靜默取代 ADR-025。

### 4. 回饋採事件與版本 promotion，不做無治理線上自學

- 接受、替換、拆分、合併、調序與 quantity policy 修正都存 append-only review event。
- 回饋先成為 synonym/few-shot/gold/calibration candidate。
- 新 synonym、prompt、模型、校準器與門檻須經離線評測、IE 核准、shadow/canary 後形成
  immutable deployment bundle。
- 單筆回饋不得立即修改 production threshold 或 active synonym。

### 5. Romantic-Rush 只作方法與程式骨架輸入

採用 contextual gate、多引擎不一致、IQR 取樣、高信心抽查與 EMA/rolling median 的治理思路；
不引入其完整 service topology，也不以 RAGAS/LLM-as-a-judge 判定 MOST 正確性。

## 考慮過的選項

### A. 全部直接放進現有 FastAPI process

初期最省部署，但模型依賴、GPU、長任務與 Web API release lifecycle 互相綁定；批次可能耗盡
request worker。否決作為長期形態，允許作為 bounded context 尚未抽離時的過渡 adapter。

### B. 一開始拆成獨立 repository 與完整微服務群

隔離最徹底，但 contract、action policy 與 gold set 尚在演進，會過早承擔跨 repo 版本、部署、
queue 與觀測成本。否決作為第一步。

### C. 同 monorepo 的獨立 bounded context，契約先行、按負載抽離（提案）

兼顧初期迭代速度與長期隔離；能在不複製 MOST engine 的前提下，獨立演進模型與批次 worker。

## 後果

### 好處

- AI 失效不影響手動建模、正式資料與 MOST 計算。
- 互動/批次共用同一解析品質與評測結果。
- 模型、prompt、索引、校準器可獨立版本化與回退。
- 人工修正能長期累積，而不犧牲製造業稽核與可重現性。

### 代價

- 需要新增跨程序 contract、outbox/feedback ingestion 與 deployment bundle 治理。
- 批次上線時需選擇 job queue/worker 技術並增加可觀測性。
- DDM 與 AI 間需要 rule-set read-only projection 與 index 同步機制。
- action/quantity/tool-state policy 必須先由 IE 定義，不能只靠模型補齊。

## 待核可與後續 ADR

本 ADR 核可的是 bounded context、權威與資料流方向。下列選型在對應 Phase 前另行定案：

1. 雲端或地端 LLM、資料落地與 retention。
2. Queue/worker 技術與 GPU 排程。
3. Review/inference storage 的實體位置與跨 site 隔離。
4. 初始 auto-accept precision/coverage 工作點。
5. Synonym、model、prompt、calibrator bundle 的核准角色。
