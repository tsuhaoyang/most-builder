# F-08：認證、角色與使用者管理（可執行功能規格）

> 分類：功能 ｜ 相依：[impl-06 §3](../../impl/impl-06-workflow-rbac.md)、ADR-018、[[rbac-hard-requirement]]、[[lb-most-auth-integration]] ｜ 證據：api-inventory-dictionary-workflow §AUTH/USERS
> ⚠️ 邊界註記：v3 是**獨立 JWT 認證**（無 LB 整合）；v2 的身份來源是 **LB 共享登入／閘道 ForwardAuth（gateway-trust）**，本功能移植的是**角色模型與使用者管理**，不是 v3 的登入機制。

## 1. 角色模型（v3 驗證、保真移植）

五角色：`admin / analyst / reviewer / approver / viewer`（多對多，User.role_names）。guard 模式：`require_roles(*names)` 依賴工廠（403）。角色×功能矩陣：

| 功能 | analyst | reviewer | approver | admin | viewer |
|---|---|---|---|---|---|
| 建/編自己的 draft（worksheet/模組） | ✓ | | | ✓ | |
| submit | ✓ | | | ✓ | |
| review / request-changes | | ✓ | | ✓ | |
| approve / retire、rule-set publish、模組 promote | | | ✓ | ✓ | |
| 使用者/角色管理 | | | | ✓ | |
| 唯讀 | ✓ | ✓ | ✓ | ✓ | ✓ |

## 2. 使用者管理（保真）

admin 建使用者（email 唯一、初始密碼＋`must_change_password=true`）、停用（is_active=false 即全 API 拒絕）、整組替換角色；使用者可自改密碼。前端路由守衛僅為 UX，**後端 guard 為權威**。

## 3. v2 落地差異

1. 身份：閘道 ForwardAuth 提供（verify 模式過渡／gateway 模式目標，`DDM_AUTH_MODE`）；v2 不實作 v3 的 /auth/login JWT（保留 LB 端）。角色存 v2 `app_users`，以員工編號對應。
2. 個資源擁有權：workbench 資源 `owner` 欄＋scope（personal/site/global，ADR-017）；analyst 僅能改自己的 personal 資源（DISC-12 治理層）。
3. 稽核：登入事件屬 LB；v2 記角色變更與工作流動作（impl-06 §2）。

## 4. 驗收條件

- Given viewer token，When PUT worksheet，Then 403。
- Given analyst A，When 編輯 analyst B 的 personal 模組，Then 403（admin 可）。
- Given 使用者被停用，Then 既有 token 下一請求即 401/403。
- Given 角色替換 analyst→reviewer，Then 立即生效（無需重登，以 DB 為準）。
- Given 未經閘道直連 API（gateway 模式），Then 拒絕（gateway-trust 前提）。
