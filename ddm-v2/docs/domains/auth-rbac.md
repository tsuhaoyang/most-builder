# 領域索引：auth-rbac — 認證與 RBAC（角色階層、稽核、事件、搜尋）

## 一句話
聯邦認證（Traefik ForwardAuth 注入 `X-Username`）＋本地角色授權 viewer<IE<manager<admin；含稽核、outbox 事件、向量搜尋。

## 權威文件
- [`rbac-spec.md`](../architecture/rbac-spec.md)
- [ADR-019](../decisions/ADR-019-worksheet-access-control.md)（worksheet 存取控制）
- ⚠️ RBAC 有 spec；但 **`outbox`（R3b 事件）、`search`（bge-m3）無專屬規格，現況以程式為準**（見 `docs/BACKLOG.md` **BL-DOC-4**）。

## 決策（相關 ADR）
- [ADR-019](../decisions/ADR-019-worksheet-access-control.md) — worksheet 存取控制

## 程式入口
- 路徑：`src/ddm_v2/auth/**`（`deps.py`、`identity.py`、`startup_checks.py`）、`src/ddm_v2/services/v2/{audit_service,outbox_service}.py`、`src/ddm_v2/api/routes/v2/{admin_users,audit_log,search}.py`、`src/ddm_v2/models/v2/{auth,audit,outbox}.py`、`src/ddm_v2/schemas/v2/{auth,audit}.py`、`src/ddm_v2/search/**`、`src/frontend/src/features/{users,layout,dashboard}/**`、`src/frontend/src/shared/**`
- graphify 錨點：`require_role`、`identity`、`audit_service`、`outbox_service`、`search_service`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- 角色階層 viewer<IE<manager<admin；`X-Username`（員工號）；dev＝`AUTH_DEV_USER=IEC141289`；`DDM_AUTH_MODE`＝gateway／verify。
- gateway 模式無條件信任入站 `X-Username` → 只綁 loopback（ADR-023 D7b）。
- outbox：`OutboxEvent`（`EVENT_REVIEW_RECORDED`／`EVENT_WORKSHEET_SAVED`）、`payload_schema_version`、claim/publish（**無 spec，以程式為準**）。
- search：port/adapter（bge-m3 http / null provider）、normalization（**無 spec**）。
- 前端：`shared/api/client.ts` 唯一 API 入口；`shared/types/api.d.ts` 由 OpenAPI 產生、不可手改。

## 不變量
見 `docs/agent-team/domains.yaml` domain `auth-rbac` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/integration/test_admin_users*.py`、`test_audit*.py`、`test_outbox_api.py`、`test_search.py`（integration 版）、`tests/unit/test_search.py`（unit 版，同名須分開跑）。
- **缺口（BL-DOC-4）**：outbox 事件契約與 search provider 邊界無專屬 spec。補 spec 需另行排程核准。
