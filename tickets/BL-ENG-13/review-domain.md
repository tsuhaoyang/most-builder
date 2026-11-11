# BL-ENG-13 auth-rbac domain review
審查對象：MOST commit `ec51a1910762579638bf4e1caef704dd9b0e4981` 的 G6 diff；`domain_id: auth-rbac`。
代存說明：以下 reviewer 回覆原文，由 scribe 原樣代存，未改動。

## 領域
`auth-rbac` — 認證與 RBAC（角色階層、稽核、搜尋）

## 相關性
相關。G6 改了領域路徑、allowlist、outbox 測試與文件的守衛歸屬，但沒有改動產品程式或兩條 invariant。依 G7 標準，本次僅審 `auth-rbac`；未指派 i18n（ACC-1-14，`ACC-1.md:477-482`）。

## Invariant 核對

| # | Invariant（節錄） | 判定 | 證據 |
|---|---|---|---|
| 1 | 角色階層與 gateway header 信任／loopback 限制 | **維持**；G6 未改 invariant，亦未改認證行為。另有既存文件落差，見下方。 | `domains.yaml:397`；本次變更集中於 `domains.yaml:382-394`。權威 RBAC 規格列出 `viewer/analyst/approver/admin`（`rbac-spec.md:52-64`）。 |
| 2 | `shared/api/client.ts` 是唯一 API 入口；`shared/types/api.d.ts` 由 OpenAPI 產生 | **維持**；新 paths 仍涵蓋 `shared/api/**`、`shared/types/**`。 | `domains.yaml:382-384,398` |

## 違反（阻擋級）
- **無。** 本次沒有可證實的 invariant 違反或產品語意變更。

## 變更提案（需使用者裁決）
- **文件同步**：`docs/domains/auth-rbac.md:15` 仍把 `src/frontend/src/shared/**` 列為程式入口，現在與新 paths 不符；該索引也未列 ADR-027（`auth-rbac.md:6-12`）。若要同步，需另行明確授權；G6 設計明載此檔不在本票範圍（`design.md:14-24`）。建議更新入口路徑並加入 ADR-027 的相關決策連結。
- **TMU 顯示常數的未來守衛範圍**：七個 allowlist 項目的描述大致符合檔案內容；但 `shared/config.ts` 含 `TMU_SEC = 0.036`，是顯示換算常數（`domains.yaml:71-84`）。目前沒有程式行為變更，且七項 allowlist 已由 ACC 簽核（`ACC-1.md:7`），所以不構成阻擋；但日後修改此值不會命中領域 reviewer。若希望該換算也受領域守衛，應另行決定其領域歸屬。

## 文件落差
- `domains.yaml:397` 使用 `viewer < IE < manager < admin`；RBAC 規格則是 `viewer < analyst < approver < admin`（`rbac-spec.md:52-64`）。此差異在 G6 前已存在，G6 依 ACC 要求未改 invariant，故不是本次引入的語意漂移。
- `auth-rbac.md:20-21` 也沿用舊角色名稱，並引用「ADR-023 D7b」；已讀的 ADR-023 並無該段，gateway 不可直連的權威說明可見 `v2-authoritative-model-guide.md:96-104`。建議另行裁決角色用語及引用修正，不應在本次 G7 審查中改動 `domains.yaml`。
- outbox 登記合理：測試路徑與 outbox 服務／模型相符（`domains.yaml:368-375,388-394`）；ADR-027 明定 worksheet save 與 outbox 同交易，以及 consumer 去重（`ADR-027:64-69`）。該 ADR 未涵蓋完整事件 payload 契約，因此索引所述「無專屬事件規格」仍可成立。

`decisions.log:20` 所記錄的 paths、allowlist、測試與 ADR 登記，以及 `state.yaml:58-60` 的 G6 完成與交接紀錄，與提交內容一致；沒有發現因此造成的語意漂移。

## 測試
未執行測試；本次是唯讀領域審查，提交只修改登記、決策紀錄與票據狀態。
