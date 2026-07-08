# impl-06：審核工作流與角色收斂（提案；實作凍結至 ADR-018 accepted）

> **Phase**：P5 ｜ **ADR**：ADR-018（proposed）｜ **依賴**：LB 共享登入時程（[[lb-most-auth-integration]]）、[[rbac-hard-requirement]]。
> 本文件是**提案級**實作規格：ADR-018 未 accepted 前不得動工（涉及 LB 端與組織權責，非純技術決策）。

## 1. 狀態機（ProcessVersion 擴充）

```
draft ──submit──▶ submitted ──review_ok──▶ reviewed ──approve──▶ approved(=published) ──retire──▶ retired
  ▲                   │
  └──changes_requested┘
```

- **`approved` 即現行 `published` 的語意**（凍結、可回放、可 clone）；migration 以 CHECK 擴充 status 集合，既有 `published` 資料值映射為 `approved`（`postgresql_using` 轉型，ADR-011 程序）。
- 查證 C-10：v3 程式碼的末態命名為 **`archived`**（`routes/analysis.py:85-91`），v2 沿用既有 `retired` 語意——兩者等價，對外文件與 UI 用詞統一為「退役」；遷移驗證與 400 擋非法遷移的機制 v3 已證實可行（`analysis.py:429-434`），照此模式實作。
- 遷移動作各對應 service 方法與權限（見 §3）；非法遷移（如 draft→approved 跳關）→ 409 `WORKFLOW_TRANSITION_INVALID`。
- 快速通道：組織可配置 `WORKFLOW_MODE=full|simple`；simple = draft→approved 兩態（現行為，預設），full = 五態。**預設不改變現行行為**。

## 2. Audit log（migration `v2_0014_workflow_audit`）

```sql
CREATE TABLE workflow_audit_log (
  id uuid PRIMARY KEY,
  entity_type text NOT NULL CHECK (entity_type IN ('process_version','motion_module','rule_set')),
  entity_id uuid NOT NULL,
  action text NOT NULL,                -- submit/review_ok/changes_requested/approve/retire/publish/override
  from_status text NULL, to_status text NULL,
  actor text NOT NULL,                 -- 員工編號
  comment text NULL,
  payload jsonb NULL,                  -- 例：E7 人工覆寫 {auto_tmu, override_tmu, reason}
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_entity ON workflow_audit_log (entity_type, entity_id, created_at);
```

僅追加（service 無 update/delete 路徑）；E7 人工覆寫與 rule-set publish 一併投錄。

## 3. 角色收斂提案（v3 五角色 × v2 RBAC × LB 登入）

| 收斂角色 | v3 對應 | 權限（MOST 端） |
|---|---|---|
| `analyst`（=IE） | analyst | 建/編自己 draft、submit、personal 組件庫 |
| `reviewer`（=IE-lead） | reviewer | review_ok / changes_requested、看全部 |
| `approver`（=manager） | approver | approve/retire、promote 組件庫 standard、rule-set publish |
| `admin` | admin | 全部＋使用者/角色管理 |
| `viewer` | viewer | 唯讀 |

- 身份來源：閘道 ForwardAuth（gateway-trust 前提不變）；角色存 MOST `app_users`。
- 開放問題（ADR-018 內裁決）：LB 端角色是否共用同一組代碼；simple 模式下 reviewer/approver 是否合併。

## 4. 測試（ADR-018 accepted 後）

1. 狀態機矩陣：每合法遷移 × 每非法遷移（409）× 每角色（403）。
2. audit：每遷移一筆、僅追加、payload 完整。
3. 相容：simple 模式行為與現行 publish 流程逐 endpoint 等價（回歸防線）。
4. migration：status 值映射對帳、可逆。
