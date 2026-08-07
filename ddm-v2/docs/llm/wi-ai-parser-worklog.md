# WI AI Parser 交付追蹤（Worklog）

**文件類型：** 交付追蹤紀錄（單一追蹤入口；不定義規格）
**規格：** [wi-ai-parser-implementation-spec.md](wi-ai-parser-implementation-spec.md)（§20 定義本文件的填寫規則）
**建立日期：** 2026-08-07

> 填寫規則摘要（完整版見 spec §20）：
> - Phase 狀態、checklist 勾選、checkpoint 結果 → 本文件。
> - 卡點（規格沒寫／規格與現實衝突）→ Blocker Log，**先記再解**；不刪列、不改寫歷史。
> - 決策分級：D1 架構級 → 開 ADR；D2 規格級 → 修 spec＋升版本；D3 實作級 → 本文件 Decision Log。
> - 不確定分級時從嚴（往上一級記）。

---

## 1. Phase 狀態總覽

| Phase | 內容 | 狀態 | 開工 | 完成 | Checkpoint |
|-------|------|------|------|------|------------|
| L0 | 契約 + AI 表 migration + rule parser 包進新契約 + run 落庫 | `completed` | 2026-08-07 | 2026-08-07 | code-review APPROVE_WITH_NITS |
| L1 | LLM planner adapter（structured output、cache、fallback） | `completed` | 2026-08-07 | 2026-08-07 | code-review APPROVE |
| L2 | Slot linking + deterministic compiler + engine gate | `not_started` | — | — | — |
| L3 | 審核 UI + review events + feedback candidates | `not_started` | — | — | — |
| L4 | 批次 parse job（**需 ADR-026/027 accepted**） | `blocked_on_adr` | — | — | — |

狀態值：`not_started / in_progress / blocked / completed / blocked_on_adr`

## 2. Checklist 進度（對照 spec §18）

### L0
- [x] L0-1 `contracts.py` + 單元測試
- [x] L0-2 `normalize_with_map` + `quantities.py` + 測試
- [x] L0-3 `models/v2/ai_ops.py` + Alembic migration（AI-1 / v2_0026）+ bundle seed；`alembic upgrade head` 已套用
- [x] L0-4 `rule_plan_adapter.py` + `wi_ai_service.parse()`（rule 路徑）+ run 落庫 + 冪等
- [x] L0-5 `nl_draft.py` 加法擴充 + integration 相容／冪等測試（9 passed）
- [x] L0 checkpoint（code review；資安依 user 指示延後）
  - 驗證：unit + `test_nlp_api` 綠；migration v2_0026/v2_0027；review [L0 WI AI code review](b4377189-48be-4e40-9f68-42988e7b3bb4) → REQUEST_CHANGES 後修畢 → APPROVE_WITH_NITS。
  - 資安完整席位：延後（功能優先）。

### L1
- [x] L1-1 `llm_client.py` + settings 欄位 + `prompts/plan_v1.py`
- [x] L1-2 `llm_planner.py` + `validate_planner_output` + fallback 接線（`wi_ai_enabled`）
- [x] L1-3 injection / dimm / fallback 測試 + FakeLLMClient（minimal：無真模型）
- [x] L1 checkpoint
  - 驗證：unit + L1 FakeLLM/unreachable integration 綠；review → REQUEST_CHANGES 後修 P0/P1 → **APPROVE**（[L1 re-check](38db58c0-df15-4693-8e3d-5105d37d3618)）。
  - 備註：minimal 骨架；prompt few-shot 可後調；drafts 仍空（L2）；security 延後。

### L2
- [ ] L2-0 端到端 fixture 5 筆（spec 附錄 A5）
- [ ] L2-1 `linking.py`（L0/L1/L2 層；embedding 可後補）
- [ ] L2-2 `most_compiler/` + 決策表矩陣測試
- [ ] L2-3 engine gate + routing + multi_action 整合測試 + golden 全跑
- [ ] L2 checkpoint

### L3
- [ ] L3-1 `ai_review.py` + `ai_review_service`（events + candidates）+ 測試
- [ ] L3-2 前端 `AiDraftPanel` 等 + typecheck/build + Playwright e2e
- [ ] L3-3 gold plans 目錄與 eval script 骨架
- [ ] L3 checkpoint + 使用者驗收（spec §0.1 五條逐條演示）

## 3. Blocker Log（卡點紀錄）

> 格式：現象寫「發生了什麼」，處置寫「為什麼這樣解」。重開同一問題＝新編號＋引用舊編號。

| 編號 | 日期 | Phase | 現象 | 影響範圍 | 分級 | 處置與理由 | 狀態 |
|------|------|-------|------|----------|------|------------|------|
| BLK-001 | 2026-08-07 | L0 | 本機 Docker daemon 未啟動，無法跑 `alembic upgrade`／integration（需 DATABASE_URL） | L0 退出條件中的 migration/integration 驗收 | D3 | 啟動 docker compose db 後：`alembic upgrade head`（v2_0025→v2_0026）成功；`pytest tests/integration/test_nlp_api.py` → 9 passed。 | resolved |

## 4. Decision Log（D3 實作級決策）

> D1 → `docs/decisions/ADR-*`；D2 → 修 spec＋§20.5 修訂紀錄。本表只收 D3。

| 編號 | 日期 | Phase | 背景 | 選項 | 選擇與理由 |
|------|------|-------|------|------|------------|
| D3-001 | 2026-08-07 | 規劃 | spec v1.0 七個軟點 | 邊做邊猜 vs 先查證定案 | 先查證定案，寫入附錄 A（升 v1.1） |
| D3-002 | 2026-08-07 | L0 | input_hash 用 bundle.code 或 bundle.id | code（穩定字串） vs UUID | 採用 code，與 settings/bundle seed 對齊；記於 wi_ai_service 註解 |
| D3-003 | 2026-08-07 | L0 | cache hit 時 legacy slots 重算或還原 | 重算（會與 synonym 漂移） vs 自 run 還原 | 自 run 的 slot_candidates 還原（legacy_from_run_snapshot），保證 ai.* 與 legacy 一致 |

## 5. Checkpoint 紀錄

| 日期 | Phase | 席位/審查者 | 發現 | 處置 |
|------|-------|-------------|------|------|
| 2026-08-07 | L0 | code-reviewer agent | P1：`error` 欄誤用；P2：缺 UNIQUE／abstain／active bundle／legacy 漂移／§7.5 | 全部必修項已修；**APPROVE_WITH_NITS**（optional 測試檔可後補）。資安延後。 |
| 2026-08-07 | L1 | code-reviewer agent | P1：malformed envelope／sanitize 硬失敗／cache provenance／缺 unreachable test | 全修；**APPROVE**。資安延後。 |

## 6. 驗收紀錄（spec §0.1）

| # | 判準 | 演示日期 | 結果 | 備註 |
|---|------|----------|------|------|
| 1 | 多 action 拆解＋top-K＋TMU 來自引擎 | — | — | — |
| 2 | 「拿起 DIMM」不補步驟、missing、review | — | — | — |
| 3 | replace_candidate review event 可查 | — | — | — |
| 4 | LLM 關機 fallback 無損核心 | — | — | — |
| 5 | 黃金錨點全綠（GM=28、CM=29） | — | — | — |

## 7. 待決事項狀態（鏡射 spec §19，裁決後更新）

| # | 事項 | 分級 | 狀態 |
|---|------|------|------|
| 1 | quantity 展開 policy | D2（IE 裁決） | open |
| 2 | inspect 併入前 cycle | D2（modeling policy） | open |
| 3 | 手別/SIMO 自動分配 | D2（IE 裁決） | open |
| 4 | 雲端 LLM | **D1（需 ADR）** | open |
| 5 | auto-accept 開啟 | **D1（需 ADR）** | open |
| 6 | `ai_*` 獨立 PostgreSQL schema | **D1（需 ADR）** | open |
| 7 | worksheet revision 綁定 | D2（R1 後加法） | open |
