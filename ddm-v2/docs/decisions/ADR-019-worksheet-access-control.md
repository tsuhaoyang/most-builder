# ADR-019: Worksheet 讀取端點的存取控制（ownership vs site scoping vs 維持 spec）

**狀態：** Proposed（待人工決策）
**日期：** 2026-07-09
**關聯：** [../architecture/rbac-spec.md](../architecture/rbac-spec.md) §4/§7、ADR-018（workflow/role convergence）、ADR-017
**參考先例（Vault）：** `02-Memory/MultiTenant-Ownership-Check-Blind-Spot.md`、`02-Memory/API-IDOR-Scope-Filter-Blind-Spot.md`、`01-Canonical/FullStack/Backend-Architecture.md`（爆炸半徑測試）、`01-Canonical/FullStack/Python-Code-Quality.md` P-03

---

## 脈絡（約束與問題）

### 問題

一整群「讀取 worksheet」的端點目前只掛 `Depends(current_user)`，代表**任何已登入者（viewer+）只要拿到工序表 UUID 就能讀取任何一份工序表及其衍生輸出**。要不要為這群端點加上 ownership 或 site scoping 的存取控制？

受影響端點（實際盤點自 `api/routes/v2/`）：

| 端點 | 目前守門 | 性質 |
|---|---|---|
| `GET /worksheets/{id}` | `current_user`（viewer+） | 讀整份 WI |
| `GET /worksheets/{id}/versions` | `current_user` | 讀版本歷史 |
| `GET /worksheets/{id}/export/wi-preview` | `current_user` | 匯出預覽 |
| `GET /worksheets/{id}/export/excel` | `current_user` | 匯出 Excel |
| `GET /worksheets/{id}/export/lb-csv` | `current_user` | 匯出 LB CSV |
| `POST /worksheets/{id}/export/lb-api` | `current_user` | 推送到 LB |
| `GET /skus/{sku_id}/worksheets` | `current_user` | **列舉**（回 UUID 清單） |
| `PUT /worksheets/{id}`（save） | `require_role(IE)` | 寫 |
| `POST /worksheets/{id}/clone` | `require_role(IE)` | 寫 |
| `POST /worksheets/{id}/publish` | `require_role(manager)` | 發布 |

### 觸發本 ADR 的事件

上一輪實作在 `worksheet_service.check_read_access()` 加了 ownership 檢查（`ProcessVersion.created_by == employee_no` 才能讀，manager+ 無限制，失敗一律回 404 不洩漏存在性），並掛到 `GET /worksheets/{id}`。**security reviewer 否決，路由掛接已撤回，函數保留但未啟用**（`worksheet_service.py:167`，帶「等 ADR-019 定案」註解）。否決四點：

1. **假安全**：只掛 1 個端點，其餘 5+ 個（versions、4 個 export、list）全繞過。
2. **與 RBAC spec §4 矛盾**：spec 明訂「讀＝viewer+（任何已登入者）」為已確認設計。
3. **legacy data 誤拒**：dev seed 的 `ProcessVersion.created_by` 為 null，合法使用者會被判成非 owner 而 404。
4. **寫入側語意矛盾**：`save`/`clone` 用 `require_role(IE)` 只驗角色、不驗 ownership，讀比寫還嚴，語意不一致。

### 相關約束

- **RBAC spec §4**：讀＝viewer+ 全公開給已登入者；編輯＝IE+；發布/另存＝manager+。此為「已確認設計（待動工）」。
- **UUID 可列舉**：`GET /skus/{sku_id}/worksheets` 無任何 owner/site filter，直接回該 SKU 下所有 worksheet 的 UUID。→ **「UUID 不可猜」不成立為安全邊界**（[[Backend-Architecture]] 爆炸半徑測試、`MultiTenant-Ownership-Check-Blind-Spot` 都明講不能靠這個）。
- **Provenance 洩漏**：worksheet/row 帶 `source_module_id` / `source_module_version`（ADR-017 實體化快照留痕），讀取權過寬時，這些「這份工序表引用了誰的哪個模組版本」的來源資訊跟著外洩。
- **`created_by` 語意**：`ProcessVersion.created_by` 是 **provenance/audit 欄位**（RBAC spec §5 定義為 text employee_no），不是為存取控制設計的；dev seed 為 null；把它當授權鍵正是上一輪 legacy 誤拒的根因。
- **`site_ids` 已解析、從未使用**：auth 層 `CurrentUser.site_ids`（來源 X-Plant-Code / admin 授予）已存在但沒有任何存取 check 用到它。
- **安全模型（spec §7）**：gateway-trust、MOST 只在 Traefik 後、內網、非零信任。
- **租戶性質**：MOST 是**單一公司內部工具**，site＝廠區（plant），非多客戶。跨 site 讀取洩漏屬「同公司跨廠區」，嚴重度遠低於典型多租戶 IDOR。

### 與 Vault 先例的關係（先例非規則）

`MultiTenant-Ownership-Check-Blind-Spot` 與 `API-IDOR-Scope-Filter-Blind-Spot` 兩則先例都來自本 repo 的 **motion_modules**，情境是 `scope=personal` 的**私人資源**——ownership（`owner` 欄位）是資料模型裡明確建模的概念。

**本次偏離該先例，理由**：worksheet **不是私人資源**，它是 Site→Product→SKU 階層下的**組織級工時標準文件**，模型裡沒有 owner/scope 軸。因此把 motion_modules 的「personal ownership 隔離」直接套到 worksheet 是**錯的軸**——這正是上一輪 `created_by` 檢查失敗的本質原因。**先例可沿用的部分**只有方法論：(a) UUID 不是安全邊界；(b) 若要做隔離，所有讀+列舉+寫端點必須用同一個 guard 統一掛接，不能只掛一個（避免「假安全」）。**不沿用**的部分是隔離軸的選擇——worksheet 的正確軸是 site，不是個人 ownership。

---

## 決策（Proposed，二選一交人工拍板）

本 ADR **不自行定案**，因為決策樞紐是一個架構師無法代答的商業問題（見下）。收斂為兩個可行候選 + 一個否決項，並推薦「回頭成本最低」的起點。

### 樞紐問題（人工必須回答）

> **同一公司的不同廠區（site）之間，工時標準文件需不需要互相保密？**
>
> - 「不需要／全公司共享標準庫」 → **Option A**。
> - 「需要，A 廠不該看 B 廠的工序表」 → **Option C**。

### 推薦起點：Option A（對齊 spec）+ 預留 Option C 的 site 軸

推薦**現在**採 Option A（乾淨對齊 RBAC spec §4，把撤回的 patch 收尾），並在設計上**預先把 `site_id` 釘為未來 scoping 的唯一軸**，使 A→C 是「加一個 filter」而非「重新設計」。理由見下節。

---

## 考慮過的選項

### Option A — 維持現行 spec（read = viewer+ 全開）〔推薦為起點〕

已登入者皆可讀任何 worksheet；不加 ownership、不加 site check。

- **賭注**：賭「同公司內工時標準可全員共享」為真（單一公司內部工具，多為真）。
- **優點**：與 RBAC spec §4 一致（零矛盾）；讀/寫語意一致（都只驗角色）；無 legacy null 誤拒；實作成本＝0（撤回已完成）。
- **代價/誠實面**：`GET /skus/{id}/worksheets` 讓 worksheet **可列舉**，所以 Option A 的防線**不是**「UUID 不可猜」（那已被列舉端點證偽），而是「讀本來就對已登入者全開，故無需保密」這個**明示假設**。此假設若不成立（跨廠需保密），Option A 直接漏。provenance 欄位（`source_module_*`）也隨之全員可見。
- **回頭成本**：低——只要 scoping 軸預留為 site，日後升級 C 是加 filter。

### Option C — Site scoping（同 site 可讀，跨 site 需 admin）〔升級路徑〕

worksheet → SKU → Product → Site 解析出 `site_id`，檢查 `site_id ∈ user.site_ids`（admin bypass）；**同一個 guard 統一掛所有讀 + 列舉 + 寫端點**。

- **賭注**：賭「跨廠保密有價值且 site_ids 能被正確填充」。
- **優點**：軸正確（site 是階層頂層、是真正的組織邊界）；啟用已解析但閒置的 `site_ids`；列舉端點也能一併加 site filter，堵住列舉洩漏；讀/寫用同一 guard，語意對稱。
- **代價**：要正確填充 `site_ids`（X-Plant-Code / admin 授予）；要定義「site 無法解析的 worksheet」的行為；要為 6+ 端點掛統一 guard + 補整合測試（同 site 可讀 / 跨 site 404 / admin bypass）；與 spec §4 現行文字需同步修訂。
- **回頭成本**：中——一旦掛上，撤除要改多處，但因是單一 guard，集中可控。

### Option B — Ownership 模型（owner-IE 讀自己的、manager 讀同 site、admin 無限）〔否決〕

即上一輪被否決的 `created_by` 方案的完整版。

- **否決理由**：
  1. **軸錯誤**——worksheet 是組織文件，非私人資源；ownership 不是它的存取邊界（偏離 motion_modules 先例的理由見上）。
  2. `created_by` 是 provenance 欄位、dev seed 為 null → 系統性 legacy 誤拒（reviewer 第 3 點）。
  3. 讀比寫嚴（寫只驗角色）造成語意倒置（reviewer 第 4 點）。
  4. 若只掛部分端點即「假安全」（reviewer 第 1 點）；若掛全部又比 Option C 複雜且軸更可疑。
- 結論：**不採用**。若日後真需個人層級隔離，應在模型層引入明確的 scope/owner 概念（如 motion_modules 那樣），而非挪用 audit 欄位。

---

## 後果（代價與風險）

### 若採 Option A（推薦起點）

- **好處**：零實作、零矛盾、立即收尾。
- **殘留風險（已知並接受）**：worksheet 對全體已登入者可讀含 provenance；此為 spec §4 的**明示**選擇，非疏漏。必須在 RBAC spec 與程式碼註解裡**寫明**「worksheet UUID 非機密、讀取刻意全開」，杜絕未來有人再誤加半套 ownership check（假安全復發）。
- **必要收尾**：**刪除**（而非續留）`check_read_access()`——它編碼了錯誤的 `created_by` 軸，留著就是誘餌，日後容易被人「順手掛上」重蹈上一輪覆轍。若未來採 C，另寫一個 site-scoped guard。

### 若採 Option C（升級路徑）

- **好處**：真正的組織邊界隔離；列舉端點一併收斂；讀寫語意對稱。
- **代價**：site_ids 填充與治理成為新的正確性依賴；「site 無法解析」需明確 fail 策略（建議 fail-closed：admin 才可讀，並記 audit，而非默默放行）；6+ 端點 + 測試工程量。
- **風險**：site_ids 未正確填充會把合法使用者鎖在外（與 legacy null 同類風險，但 site 比 created_by 可控）。

### 共同

- **爆炸半徑**（[[Backend-Architecture]]）：目前答案＝「任一已登入者可讀全部 worksheet」。Option A 明示接受此半徑（賭單公司共享）；Option C 收斂到「自己的 site」。人工需在知情下選擇，不可用「先讓功能動、之後再隔離」心態拖延——這是拓樸決策。

---

## 決定後的工作項目

### 若人工選 Option A

1. `services/v2/worksheet_service.py`：**刪除** `check_read_access()`（167–183 行）及其「等 ADR-019」註解。
2. 確認 7 個讀/列舉端點維持 `Depends(current_user)`（read、versions、export×4、`GET /skus/{id}/worksheets`）——現況即符合，無改動。
3. `docs/architecture/rbac-spec.md` §4：補一句「worksheet UUID 非機密、可經 `GET /skus/{id}/worksheets` 列舉；讀取對 viewer+ 全開為刻意設計」，並在 read 端點加對應註解，防止未來半套 ownership 復發。
4. 本 ADR 狀態改 accepted，記錄「賭：單公司共享工時標準」。

### 若人工選 Option C

1. 新增單一共用 guard，例如 `auth/deps.py: require_worksheet_read(worksheet_id)` 或 service 層 `assert_worksheet_site_access(session, worksheet_id, user)`：解析 worksheet→SKU→Product→Site 取 `site_id`，檢查 `site_id ∈ user.site_ids`（admin bypass）；site 無法解析→fail-closed（admin only + audit）。
2. **統一掛接全部端點**（避免假安全）：read、versions、export×4、以及寫側 save/clone/publish 也走同一 site check（讀寫對稱）；`GET /skus/{id}/worksheets` 加 site filter（堵列舉洩漏）。
3. `services/v2/worksheet_service.py`：刪除舊 `check_read_access()`（錯誤的 created_by 軸），改用新的 site-scoped guard。
4. 落實 `site_ids` 填充：確認 auth 層從 X-Plant-Code / admin 授予正確寫入 `app_users.site_ids`；定義 backfill。
5. `docs/architecture/rbac-spec.md` §4 修訂為 site-scoped read；ADR 狀態改 accepted。
6. 整合測試（CI Gate 2）：同 site 可讀、跨 site 404（不洩漏存在性）、admin bypass、site 無法解析 fail-closed，涵蓋全部 6+ 端點。

---

## Revisit-when（provisional 觸發訊號）

出現以下任一訊號，本決策（尤其若停在 Option A）必須重新評估：

1. **多客戶/多公司**：MOST 從「單公司多廠」變成服務多個外部客戶（真多租戶）——此時 Option A 的共享假設立即失效，須升級到 site（或 tenant）scoping，且爆炸半徑要求答案＝1。
2. **跨廠保密需求浮現**：業務端明確要求 A 廠不得見 B 廠工序表 → 直接執行 Option C 工作項目。
3. **provenance 敏感度升級**：`source_module_*` 或客戶專屬製程被認定為機密資訊 → 至少對非同 site 者做欄位級遮蔽或升級 C。
4. **有人再度提交半套 ownership check**：出現「只掛部分端點的 owner/created_by 檢查」PR → 這是本 ADR 明令避免的假安全，退回並引用本 ADR。
5. **site_ids 開始被其它功能使用**：一旦 site_ids 進入任何存取決策，讀取側應同步納入同一 scoping 模型，避免半套隔離。
