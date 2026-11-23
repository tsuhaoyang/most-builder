# RBAC 規格（v2：聯邦認證 + 本地授權）

**文件類型：** 安全 / 權限規格
**版本：** 1.0 — 已確認設計（待動工）
**建立日期：** 2026-06-18
**關聯：** [system-architecture-v2-spec.md](./system-architecture-v2-spec.md)、[data-model-and-storage-spec.md](./data-model-and-storage-spec.md)
**LB 參考（唯讀，勿改）：** `LB/auth_service/`、`LB/traefik/dynamic.yaml`

---

## 1. 背景與約束

- 系統為**微服務**架構，與 Line Balance（LB）共用同一個 **Traefik gateway**。
- LB 已有 **auth_service**：OAuth2 授權碼流程 + **Redis session（cookie `session_id`）** + Bearer token，作為 **Traefik ForwardAuth**。
- 登入後對 MOST 有意義的身分＝**員工編號**。

### LB 機制（自 `LB/` 程式碼確認）

- `LB/traefik/dynamic.yaml`：`auth-verify` middleware = `forwardAuth → http://auth_service:8000/auth/verify`，`authResponseHeaders` 注入下游：**`X-User-Id`、`X-User-Role`、`X-Plant-Code`、`X-Username`**。
- `LB/auth_service/.../auth_routes.py` `/auth/verify`：先驗 session cookie，否則驗 Bearer token；成功回 200 + 上述 header；失敗 401（`X-Auth-Error`）；Redis 故障 503（fail-closed）。
- 身分內容：`X-User-Id`＝auth 服務穩定 user id（UUID）、`X-Username`＝員工編號、`X-Plant-Code`＝廠區、`X-User-Role`＝**LB 自己的角色**（與 MOST 角色語意不同）。
- OAuth / session / Redis 全在 auth_service；**下游服務不碰 token**。

---

## 2. 決策：認證與授權分離

| 面向 | 由誰負責 | 說明 |
|------|----------|------|
| **認證 Authentication（你是誰）** | **委派 Traefik ForwardAuth（auth_service）** | MOST 不做 OAuth / token 驗證、不存密碼。Gateway 已驗證並注入身分 header |
| **授權 Authorization（你能做什麼）** | **MOST 本地** | MOST 自管角色（analyst/approver/admin），不沿用 LB 的 `X-User-Role` |

理由：token 只帶身分、無 MOST 角色；微服務下**每個服務自管授權**（最懂自己的資源）。

```
請求 → Traefik(ForwardAuth → auth_service /auth/verify) → 注入 X-User-Id/X-Username/X-Plant-Code → MOST
                                                                                                    │
MOST：① 讀 header 取身分(員工編號)  ② 查本地 app_users 取 MOST 角色  ③ require_role 守門
```

---

## 3. 身分與鍵

- **穩定鍵＝員工編號（`X-Username`）**：業務身分，跨 IdP/auth 實作穩定（呼應「只有員工編號」）；不綁 auth_service 的內部 UUID。
- `external_user_id`（`X-User-Id`）存著當**輔助**（對帳/將來升級用）。
- `X-Plant-Code` → 預設廠區（site）來源。
- **不採信** `X-User-Role`（LB 角色）作 MOST 授權。

---

## 4. 角色與權限矩陣

角色：**admin > approver > analyst > viewer**（viewer＝已登入但未授予 MOST 角色）。

| 動作 | 需要角色 |
|------|----------|
| 讀（檢視 WI/Level/Rule-set/匯出預覽）；**編輯區除外**，見下表 | viewer+（任何已登入者） |
| 編輯（worksheet save、level 標註、vocab CRUD、rule-set 草稿編輯） | **analyst+** |
| 發布（worksheet publish、rule-set publish）、另存新檔 | **approver+** |
| 使用者角色管理（授予/停用） | **admin** |
| Rule-set 建立草稿(clone) | analyst+（可調） |

**`/api/v2/wi-ai/*`（外部 ai_service 整合；單句與 status 已實作，審核佇列、批量外送、啟用／停用仍規劃中）**——權威在 [ADR-037](../decisions/ADR-037-ai-service-integration.md) D7，下表只列最低角色，不重抄規則；與 D7 不一致時以 D7 為準：

| 動作 | 最低角色 |
|------|----------|
| 觸發 AI 解析：單句（已實作，既有 `POST /worksheets/nl-draft`） | **依角色分流**：analyst 以上走外部 AI（整合可用時）；viewer 仍得 200＋`rule_based`，不外送 |
| 觸發 AI 解析：批量（規劃中） | **拒絕**：analyst 以上（`require_role("analyst")`），viewer 得 403 |
| 看審核佇列與項目（含原文） | analyst（viewer 只看彙總計數；依 `site_ids` 與 owner 過濾） |
| 逐項接受、人工修改 | analyst（落盤另受既有 service 的守衛） |
| 重設他人已決項目 | approver（須填理由） |
| 啟用／停用整合 | admin |
| `GET /wi-ai/status`（已實作） | 登入即可（只回 `enabled`／`available`） |

**工作區編輯區（ADR-038 D2／D3，W1 已實作）**（2026-11-23，W1，Howard 核可）：

| 端點 | 最低角色 |
|------|----------|
| `GET /worksheets/{id}/drafts`（列出） | **analyst**（viewer 得 403） |
| `POST /worksheets/{id}/drafts`（新增） | analyst |
| `PATCH`／`DELETE /worksheet-drafts/{id}` | analyst |
| `POST /worksheets/{id}/drafts/confirm` | analyst |
| `POST /worksheets/{id}/drafts/commit`（寫入工時表） | analyst |
| `POST /worksheets/{id}/drafts/from-sentence`（單句解析，W3） | analyst（viewer 得 403） |

- **讀取例外**：ADR-019「讀取全開 viewer+」只適用工時表正本。編輯區含未確認的 AI 草稿與匯入原文，讀取也需 analyst（與上表「看審核佇列含原文 analyst」一致）。
- **單句解析寫進編輯區**（2026-11-24，W3，依審查建議，Howard 授權）：`POST /worksheets/{id}/drafts/from-sentence` 最低角色 **analyst**（viewer 得 403）。與 `nl-draft` 不同：它不「依角色分流」，viewer 不能用。外部 AI 分流沿用 `wi_ai_service.external_for`（analyst 以上且整合可用才外送）。
- 寫入（`drafts/commit`）與確認（`drafts/confirm`）新增兩個 409：`DRAFT_INCOMPLETE`、`DRAFT_STALE`（ADR-038 D3 W3 追記）；角色不變。
- 編輯區不做 ownership 與站點限制（ADR-038、BL-ENG-19）：任一 analyst 可改、刪、確認、寫入別人建的草稿。已寫入（`committed`）的草稿不可改刪。
- 刪除尚未寫入的草稿不寫稽核表，只留伺服器 log；寫入工時表經 worksheet revision 留 actor。

本專案目前沒有站點層級的存取控制，見 [BL-ENG-19](../BACKLOG.md#bl-eng-19--worksheet-路由沒有站點層級的存取控制延後)。

JIT：第一次出現的員工編號 → 自動建一筆 **viewer**（無 MOST 角色），由 admin 授予。

> ⚠️ **worksheet 讀取為刻意全開設計**：UUID 非機密，可經 `GET /skus/{id}/worksheets` 列舉。
> MOST 工廠環境中，工時標準屬組織共享知識。禁止以 `created_by` 作為讀取授權鍵——
> 那是 audit 欄位，不是 ownership 軸（詳見 ADR-019 Option A）。
> 若需跨廠區隔離，請走 Option C（site_ids 階層），不要補半套 ownership check。

---

**區域、DSX 座標同步與物件歸區（ADR-038 D5，W7a 已實作）**（2026-11-24，W7a，依審查建議，Howard 授權）：

| 端點 | 最低角色 |
|------|----------|
| `GET /zone-categories` | viewer（`current_user`） |
| `POST /zone-categories`（新增類別） | **admin** |
| `GET /skus/{sku_id}/zones`（區域與最近一次同步） | viewer |
| `POST /skus/{sku_id}/zones` | analyst |
| `PATCH`／`DELETE /zones/{zone_id}` | analyst |
| `POST /skus/{sku_id}/zones/sync`（從 DSX 同步，存快照） | analyst |
| `GET /dsx/objects`（代理 DSX 物件清單） | analyst |
| `GET /skus/{sku_id}/object-zones` | viewer |
| `PUT /skus/{sku_id}/object-zones` | analyst |
| `GET /worksheets/{worksheet_id}/objects`（這份 WI 用到的物件與歸區） | viewer |

- 共 11 個端點。讀取沿用 ADR-019 的「讀取全開 viewer+」；寫入 analyst；只有新增類別需要 admin。
- `GET /dsx/objects` 雖是讀取，但會對外呼叫 DSX（DSX 沒有認證），所以要 analyst。整合未開或連不到時回 200＋`available=false`＋原因，不回空清單。
- 同步等寫入端點的 DSX 失敗：`DSX_DISABLED` 503、`DSX_UNREACHABLE` 502、`DSX_NOT_READY` 409。刪除還有歸區的區域：`ZONE_IN_USE` 409。
- 區域不做 ownership 與站點限制：任一 analyst 可改別人建的區域。

## 5. 資料模型：`app_users`（MOST 本地授權）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | UUID PK | 內部主鍵 |
| `employee_no` | text UNIQUE | **穩定鍵**（= X-Username） |
| `external_user_id` | text | 輔助（= X-User-Id），可空 |
| `display_name` | text | 顯示名（= X-Username 或 X-User-Id 衍生） |
| `roles` | text[]（或多列關聯） | `admin`/`approver`/`analyst`（空＝viewer） |
| `site_ids` | uuid[] | 可存取廠區（空＝預設由 X-Plant-Code） |
| `is_active` | bool | 停用 |
| `created_at`/`updated_at` | timestamptz | |

**`*_by` 欄位改存員工編號（text）**：`process_versions.created_by/published_by`、`rule_sets.published_by`、`bom_imports.imported_by`、`audit_log.actor_id` 由 UUID → **text(employee_no)**（migration）。

---

## 6. 後端實作

- **`current_user` 依賴**：讀 `X-Username`(員工編號)/`X-User-Id`/`X-Plant-Code`；查 `app_users`（JIT 建 viewer）；回 `CurrentUser{employee_no, roles, site_ids}`。
  - **Dev override**（設定 `AUTH_DEV_USER=員工編號:role`，僅非 production）：本地無 gateway 也能測。
- **`require_role(min_role)` 守門**：掛上 publish/edit 端點（§4 矩陣）。
- **使用者管理 API**（admin）：`GET/POST/PATCH /api/v2/admin/users`（list / 授予角色 / 停用）。
- **`AuthIdentityProvider` port**：`GatewayHeaderProvider`（prod，讀 header）/ `DevProvider`（本地）→ 換來源＝換 adapter。

---

## 7. 安全模型：閘道信任（gateway-trust）

- 設計信任 gateway 注入的 `X-User-*` header。**前提（必做）**：
  1. **MOST 只在 Traefik 後、不對外直連**（否則可偽造 header 冒充）。
  2. gateway 清掉 client 自帶的 `X-User-*`（Traefik forwardAuth 以 auth 回應覆蓋）。
  3. **建議雙保險**：gateway↔MOST 共享密鑰 header（MOST 驗 `X-Gateway-Secret`）。
- **非零信任**：更嚴格版本是 gateway 下發**簽章 JWT**、MOST 自驗章。LB 目前為 opaque session + 注入 header，故採閘道信任；零信任為日後升級項。
- Dev override 必須 **production 關閉**（config-gated）。

---

## 8. 前端

- SPA 掛在同一 gateway 後：未登入 → gateway 導向 LB 登入頁；登入後請求自帶 session cookie。
- 頂部顯示登入者（員工編號/廠區）。
- 依角色顯示/禁用：viewer 隱藏編輯/發布鈕；admin 才見「使用者管理」tab。
- **前端權限只是 UX**；真正守門在後端 `require_role`。

---

## 9. 微服務符合性（評估）

✅ 符合：bounded context（authn 在 auth_service、authz 在 MOST）、去中心化授權與資料（不共用 DB）、gateway 邊緣認證、鬆耦合（只依賴 header 契約）、runtime 不互打（本地角色表）。
⚠️ 取捨：安全模型為**閘道信任**（非零信任）；受控內網合理，硬化見 §7。

---

## 10. 待確認 / Bootstrap

| # | 項目 | 預設/建議 |
|---|------|----------|
| 1 | 初始 admin 的**員工編號**（bootstrap 第一管理員） | 待 User 提供；seed 一筆 admin |
| 2 | gateway↔MOST **共享密鑰**（雙保險用） | 待定（env） |
| 3 | 員工編號確切來自哪個 header（`X-Username` 確認） | 採 `X-Username` |
| 4 | `roles` 用 text[] 還是關聯表 | 先 text[]（簡單；多角色少） |

---

*本規格為動工依據；先建「本地授權 + GatewayHeaderProvider/DevProvider + 守門」骨架（dev override 可離線測），部署到 Traefik 後即生效。*
