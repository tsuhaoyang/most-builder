# ADR-018: 審核工作流與角色收斂

**狀態：** Accepted（2026-07-10）— impl-06 解凍
**日期：** 2026-07-04
**關聯：** [../v3/impl/impl-06-workflow-rbac.md](../v3/impl/impl-06-workflow-rbac.md)、[[rbac-hard-requirement]]、[[lb-most-auth-integration]]

## 已裁決項目（2026-07-10）

### 裁決 1：角色獨立（選項 B）
微服務各自維護角色。Gateway 只傳 `employee_no`；MOST 查自己的 `app_users`；LB 自管自己的角色體系。兩邊不共用 role code，獨立演進不互相依賴。

### 裁決 2：無 reviewer，manager 直接 approve
- 取消 `reviewer` 角色；simple 模式（預設）= `draft ↔ approved`（兩態，等同現行 draft/published）。
- full 模式（`WORKFLOW_MODE=full`）= `draft → submitted → approved → retired`（四態，跳過 reviewed）。
- 角色收斂為四個：`viewer / analyst / approver / admin`（IE→analyst、manager→approver）。

### 裁決 3：歷史資料回填 + audit log 嚴謹
- 歷史 `published` → `approved` migration 的 actor 一律填 `"system_migration"`，不留空、不用 `created_by`（可能為 null）。
- audit log 是本系統的核心資產（工廠資料正規化的唯一真相來源）；所有狀態遷移、人工覆寫（E7）、rule-set publish **必須投錄**，任何路徑都不可略去。
- 表結構見 §2（workflow_audit_log）；`僅追加`原則不可違反（無 update/delete 路徑）。

### 裁決 4：角色改名
- `IE` → `analyst`（程式碼、DB CHECK、API 全部改名）
- `manager` → `approver`（同上）
- `viewer` / `admin` 名稱不變
- 改名與 workflow migration 合併在 impl-06 一次完成

## 脈絡

v3 具五角色審核流（analyst/reviewer/approver/viewer/admin；draft→submitted→reviewed→approved→archived）並經 IE 使用認證。v2 現行僅 draft/published 加規劃中 RBAC（IE/manager/admin），登入依賴 LB 共享認證（verify/gateway 兩模式）。三套角色體系必須收斂為一套，否則權限語意漂移。

## 決策（提案）

ProcessVersion 狀態機擴充為五態（`approved` 承接現行 `published` 語意），提供 `WORKFLOW_MODE=simple|full` 且預設 simple（＝現行為，零行為變更）；角色收斂為 `analyst/reviewer/approver/admin/viewer` 五角色，身份來自閘道 ForwardAuth、角色存 MOST；新增僅追加的 `workflow_audit_log`。

## 考慮過的選項

- **A. 保持 draft/published、不做審核流** — 與 IE 認證的 v3 工作流退化衝突；否決。
- **B. 直接照搬 v3 五態、無 simple 模式** — 對現行部署是破壞性行為變更；否決。
- **C. 五態＋模式開關、預設不變（選定）** — 加法演進（ADR-011）；審核紀律由組織按需開啟。

## 後果

- 好處：RBAC 硬需求、v3 審核習慣、LB 共享登入一次收斂；人工覆寫（impl-02 E7）與 rule-set publish 獲得統一稽核面。
- 代價：status 值映射 migration；全 endpoint 權限矩陣測試。
- **待裁決（本 ADR accepted 的前提）**：LB 端是否共用同組角色代碼；simple 模式下 reviewer/approver 是否合併；歷史 published 資料的 actor 回填策略。
