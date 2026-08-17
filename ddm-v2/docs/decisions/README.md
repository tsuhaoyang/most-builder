# 決策紀錄索引

此目錄保存目前適用於 DDM v2 的架構決策。早期 OQ 討論稿與已被取代的 ADR 已自工作文件移除；其歷史仍可由 Git 查閱。

## 目的

- 保存「為什麼這樣做」而不只是「做了什麼」
- 記錄曾評估過的方案、取捨理由與否決原因
- 為後續開發者與 AI agent 提供可追溯的上下文

## 文件索引

| 文件 | 主題 | 狀態 |
|------|------|------|
| [ADR-011-schema-evolution-and-contract-stability.md](ADR-011-schema-evolution-and-contract-stability.md) | v2 實作期變更政策：契約穩定 + schema 加法演進（避免整合問題） | 🟢 已定案 |
| [ADR-012-3d-rendering-architecture.md](ADR-012-3d-rendering-architecture.md) | 3D 模擬渲染架構：Web 3D 資產管線(A) 為基礎 + Pixel Streaming(B) 未來可選；workbench 新分頁 | 🟢 已定案 |
| [ADR-013-excel-import-architecture.md](ADR-013-excel-import-architecture.md) | Excel 匯入：資料驅動(profile)+staging 暫存+預覽；增量 2a(ingest)→2b(enrich/commit) | 🟢 已定案 |
| [ADR-014-v3-dictionary-as-value-authority.md](ADR-014-v3-dictionary-as-value-authority.md) | v3 IE 認證字典為值權威；rule-set `MINIMOST_FACTORY_V2`＋黃金重錨 | 🟢 accepted |
| [ADR-015-nl-parsing-in-scope.md](ADR-015-nl-parsing-in-scope.md) | NL 解析納入 scope（DraftParserPort、建議層隔離） | 🟢 accepted |
| [ADR-016-search-infrastructure.md](ADR-016-search-infrastructure.md) | 檢索架構：pg_trgm＋pgvector 混合、search_documents 投影、EmbeddingProvider port | 🟡 proposed |
| [ADR-017-motion-modules-library.md](ADR-017-motion-modules-library.md) | 組件庫 motion_modules：合併範本與 v3 MI 語句概念（registry＋實體化快照） | 🟡 proposed |
| [ADR-018-workflow-and-role-convergence.md](ADR-018-workflow-and-role-convergence.md) | 審核工作流與角色收斂（viewer/analyst/approver/admin） | 🟢 accepted |
| [ADR-019-worksheet-access-control.md](ADR-019-worksheet-access-control.md) | Worksheet 讀取端點存取控制：維持已登入 viewer+ | 🟢 accepted |
| [ADR-020-simo-contribution-semantics.md](ADR-020-simo-contribution-semantics.md) | SIMO 標記列貢獻 0，時間由未標記主列吸收 | 🟢 accepted |
| [ADR-021-ia-restructure-v3-parity.md](ADR-021-ia-restructure-v3-parity.md) | 前端資訊架構以 v3 驗證畫面為母版 | 🟢 accepted |
| [ADR-022-workbench-two-layer-correction.md](ADR-022-workbench-two-layer-correction.md) | 工作台動作/WI 兩層模型、WI 大綱與 row inspector | 🟢 accepted |
| [ADR-023-dictionary-governance-unification.md](ADR-023-dictionary-governance-unification.md) | MOST 字典 active、clone-on-write、認證血緣與回放 | 🟢 accepted |
| [ADR-024-master-data-vs-dictionary-boundary.md](ADR-024-master-data-vs-dictionary-boundary.md) | 主數據、MOST 字典與業務產出的責任分界 | 🟢 accepted |
| [ADR-025-import-template-matching-p2.md](ADR-025-import-template-matching-p2.md) | 匯入預覽接 template match，IE 核對後以 active rule-set 重算 | 🟢 accepted |
| [ADR-026-wi-ai-parser-pipeline-boundary.md](ADR-026-wi-ai-parser-pipeline-boundary.md) | WI AI Parser 獨立 bounded context、DDM deterministic compiler 與 MOST 權威邊界 | 🟢 accepted |
| [ADR-027-domain-evolution-versioning-and-ai-readiness.md](ADR-027-domain-evolution-versioning-and-ai-readiness.md) | Worksheet revision、Modeling/Level policy、outbox、row-level batch 與 AI readiness | 🟢 accepted |
| [ADR-028-most-engine-boundary-validation-and-single-authority.md](ADR-028-most-engine-boundary-validation-and-single-authority.md) | most_engine 邊界驗證加嚴（三層權威、無 strict 旗標）與刪除重複計算實作 | 🟡 proposed |
| [ADR-029-python-dependency-locking-and-audit-gate.md](ADR-029-python-dependency-locking-and-audit-gate.md) | Python 依賴鎖版（hash-pinned 雙鎖檔、pip 格式）＋阻斷式 pip-audit＋nightly 上游漂移偵測 | 🟡 proposed |
| [ADR-030-in-process-parse-worker-topology.md](ADR-030-in-process-parse-worker-topology.md) | ai_parse_jobs 背景 worker 部署拓撲：in-process 預設開啟＝過渡；per-process 迴圈語意與 dedicated worker 觸發條件 | 🟡 proposed |
| [ADR-031-spatial-layout-and-distance-acquisition.md](ADR-031-spatial-layout-and-distance-acquisition.md) | 空間佈局與距離取得（2026-08-17 修訂：空間單位＝**工位（站）**，原「佈局跟產線走」作廢）：`stations` 主數據＋站內局部座標擺放表（與詞彙身分分離）＋列級工位綁定 `wi_rows.station_id` → 產生帶出處的 `reach_cm`／`foot_cm`／`distance_cm` 建議；引擎仍是唯一換算權威 | 🟡 proposed |

## 狀態說明

| 符號 | 意義 |
|------|------|
| 🔴 尚未定案 | 問題已提出，但尚未形成可執行決策 |
| 🟡 討論中 | 已有初步方向，仍需補充規則或確認邊界 |
| 🟢 已定案 | 已形成可落地的決策，可據此實作 |
| ⚫ 已取消 | 議題不再適用或已被其他方案取代 |

## 已產出規格文件

以下規格文件已從決策討論中衍生，可直接作為實作依據：

| 文件 | 說明 | 依賴決策 |
|------|------|----------|
| [`docs/architecture/system-architecture-v2-spec.md`](../architecture/system-architecture-v2-spec.md) | 目標系統架構 v2（定點重建） | — |
| [`docs/architecture/wi-ai-parser-system-spec.md`](../architecture/wi-ai-parser-system-spec.md) | v2 WI AI Parser：互動/批次、action planning、MOST compiler 邊界、feedback learning | ADR-015、ADR-026 |
| [`docs/architecture/domain-evolution-and-ai-readiness-spec.md`](../architecture/domain-evolution-and-ai-readiness-spec.md) | 核心持續演進下的 revision、policy version、method context、AI/batch 資料地基 | ADR-011、ADR-027 |
| [`docs/core-logic/minimost-sequence-model-core-logic-spec.md`](../core-logic/minimost-sequence-model-core-logic-spec.md) | MiniMOST Sequence Model 核心邏輯 | ADR-014、ADR-020 |
| [`docs/core-logic/level-system-core-logic-spec.md`](../core-logic/level-system-core-logic-spec.md) | Level System 核心邏輯（含對 LB 輸出合約） | — |
| [`docs/CI_GATES.md`](../CI_GATES.md)〈依賴鎖版與安全稽核〉 | 鎖檔形狀、更新時機、pip-audit 豁免政策與 nightly | ADR-029 |

---

## 使用方式

當某個議題有新結論時，請在對應文件中更新：

1. `Status`
2. `Discussion Notes`
3. `Open Questions`
4. `Resolution`

若某項結論已可直接影響實作，請在 commit message、PR 描述或程式註解中引用對應編號。

示例：`implements ADR-020: SIMO 標記列不計入總工時`
