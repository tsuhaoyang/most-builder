# docs/v3 — v3（IE 認證版）→ v2 整合文件庫

> **本資料夾是「ddm-v3 核心邏輯與功能整合進 ddm-v2」的完整文件集**。
> 裁決基準（2026-07-04，User/IE）：**v3 的資料與使用邏輯經 IE 認證為權威**；引擎與架構以 v2 為骨幹。
> 治理：本資料夾登錄於 [docs/DOC_REGISTRY.md](../DOC_REGISTRY.md)；決策落 [docs/decisions/](../decisions/) ADR-014~018。

## 閱讀順序

| # | 文件 | 分類 | 內容 | 狀態 |
|---|------|------|------|------|
| 0 | [migration-delivery-checklist.md](migration-delivery-checklist.md) | **驗收** | **v3→v2 移植交付驗收清單**（合約級）：A~K 共 25 項、每項含可驗證標準與拒絕條件、功能退役清單、簽核欄 | ✅ 2026-07-08 |
| 1 | [v2-v3-core-logic-diff-and-integration.md](v2-v3-core-logic-diff-and-integration.md) | 分析 | 兩版核心邏輯逐格差異盤點、裁決清單 C1–C10（已定案） | ✅ 定稿 |
| 2 | [v3-to-v2-refactor-blueprint.md](v3-to-v2-refactor-blueprint.md) | 設計 | 總體整合策略、ADR 清單、六 Phase 實施順序 | ✅ 定稿 |
| 3 | [impl/](impl/) | 實作規格 | 各 Phase 的實作細節（schema/引擎/API/測試），見下表 | 🔄 P0 產出 |
| 4 | [verification-code-audit.md](verification-code-audit.md) | 查證 | **程式碼查證報告**：本庫所有宣稱 vs ddm-v3 實碼逐條對照、更正 C-1~C-12、三層系統補充 | ✅ 2026-07-05 |
| 5 | [analysis/](analysis/README.md) | **可執行規格庫** | v3 全功能萃取：core-logic/（CL-01~04）＋ features/（F-01~08，AI 可直接實作）＋ UX-design-spec ＋ 00 方法論與 DISC-01~15 討論清單 ＋ reference/ 萃取證據 | ✅ 2026-07-05 |
| 6 | [reference/](reference/) | 權威參考 | 自 ddm-v3 複製的認證來源（唯讀，見下） | 📌 參考 |

## impl/ — 實作細節規格

| 文件 | 對應 Phase | 對應 ADR | 內容 |
|------|-----------|----------|------|
| [impl-01-rule-set-factory-v2.md](impl/impl-01-rule-set-factory-v2.md) | P1 | ADR-014 | `MINIMOST_FACTORY_V2` 完整值表、schema 變更、converter、migration v2_0008/0009 |
| [impl-02-engine-changes.md](impl/impl-02-engine-changes.md) | P1 | ADR-014 | 引擎修改 E1–E8（函式級）、錯誤碼、黃金測試重錨清單 |
| [impl-03-search-infrastructure.md](impl/impl-03-search-infrastructure.md) | P2 | ADR-016 | pg_trgm+pgvector、`search_documents` 投影、EmbeddingProvider port、部署 |
| [impl-04-motion-modules.md](impl/impl-04-motion-modules.md) | P3 | ADR-017 | 組件庫 schema、實體化 API、motion_templates 轉移 |
| [impl-05-nlp-and-synonyms.md](impl/impl-05-nlp-and-synonyms.md) | P4 | ADR-015 | `nlp/` 套件、DraftParserPort、同義詞表 S3、v3 五缺陷修正 |
| [impl-06-workflow-rbac.md](impl/impl-06-workflow-rbac.md) | P5 | ADR-018 | 審核狀態機、audit log、角色收斂（待 ADR-018 accepted） |

## reference/ — v3 權威來源（唯讀，勿改）

| 檔案 | 角色 |
|------|------|
| [minimost_ai_dictionary_v1.json](reference/minimost_ai_dictionary_v1.json) | **值的唯一權威**（IE 認證）。`MINIMOST_FACTORY_V2` seed 由此程式化轉換，不手抄 |
| [MiniMOST_system_data_spec.md](reference/MiniMOST_system_data_spec.md) | v3 系統資料結構規格（⚠️ 其 §8 範例與字典 JSON 有出入，衝突時以 JSON 為準——見差異盤點 §1.3） |
| [minimost_ai_dictionary_v1.md](reference/minimost_ai_dictionary_v1.md) | 字典的人類可讀版 |
| [wi-parser-upgrade/](reference/wi-parser-upgrade/) | v3 的 NL 解析升級計畫 01–09（P4 的設計輸入） |

## 執行分派協議（2026-07-05 起，硬性）

1. **主窗口＝協調者**：只做分診、撰寫/更新執行文件（工單）、派工、驗收回報、升級 User 決策；**不直接實作**。
2. **先文件、後派工**：任何要動程式的任務必須先有執行文件（impl-xx／impl-xxA 工單／F 規格），派工 prompt 只引用文件、不得夾帶文件外的規格。
3. **分工**：ddm-backend（後端/migration/引擎——引擎需工單明文授權）、ddm-frontend（React+TS）、ddm-testing（測試/CI_GATES）、ddm-validator（opus，唯讀守門，任何核心邏輯變更後必跑）、unified-arch（跨 LB 事務）。
4. **完成定義**：agent 回報 → validator 過 → 協調者在工單勾執行結果 → 才向 User 回報關閉。

## 不變的鐵則（引自 [[architecture-v2]] / [[ie-most-engineer]]）

1. 引擎只有一套（`src/ddm_v2/most_engine/`）；v3 程式碼本體不搬。
2. 規則是版本化資料；改值＝新 rule-set 版本，不改引擎。
3. 每項變更先寫黃金測試再實作；`validate-core-logic` 必須綠。
4. 合約加法優先（ADR-011）；破壞性變更走 ADR。
