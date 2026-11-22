# LB ↔ MOST 共用登入（認證整合）

MOST 不自建登入；身分一律來自 LB 的 auth_service（OAuth2 + session）。兩種模式:

| 模式 | 何時用 | 身分來源 | MOST 可否直接開 port |
|------|--------|----------|----------------------|
| `gateway`（預設、最終型態） | LB/MOST 都在同一個 Traefik 後面 | 信任 ForwardAuth 注入的 `X-Username` 等 header | ❌ 只能經 gateway 進（否則 header 可偽造） |
| `verify`（過渡型態） | 還沒網域、MOST 先單獨開 port | MOST 自己拿 session cookie 打 LB `/auth/verify` 驗證 | ✅ 可直接對外（驗 cookie，不信任 client header） |

由 `DDM_AUTH_MODE` 切換。本檔聚焦**過渡的 verify 模式**（IP:port 階段）。

## 為什麼 verify 模式直接開 port 也安全

`verify` 模式**不讀** client 端的 `X-Username`（那可偽造），而是用瀏覽器帶來的 `session_id`
cookie 去打 LB 的 `/auth/verify`，身分以 LB 回應的 header 為準。等於 MOST 自己做了一次
ForwardAuth。cookie 為 host-only（不分 port），所以使用者在 `http://<ip>/` 登入後，
開 `http://<ip>:<MOST_PORT>/` 時瀏覽器會自動帶上同一個 cookie。

## 環境變數

| 變數 | 說明 | 過渡部署值 |
|------|------|-----------|
| `DDM_AUTH_MODE` | `gateway`｜`verify` | `verify` |
| `DDM_LB_VERIFY_URL` | LB verify 端點（MOST 容器可達） | `http://<server-ip>/auth/verify` |
| `DDM_SESSION_COOKIE_NAME` | 與 LB 一致 | `session_id` |
| `DDM_ADMIN_EMPLOYEE_NO` | 開機自動建為 admin 的員編（設成**你真實員編**） | 你的員編 |
| `DDM_PORT` | MOST 對外 port | 例 `8877` |
| `AUTH_DEV_USER` | 本地 dev 用；**部署時不要設** | （留空） |

## 過渡部署（verify 模式、自己的 port）

```bash
cd most-builder   # repo 根
# .env 或直接 export
export DDM_AUTH_MODE=verify
export DDM_LB_VERIFY_URL=http://<server-ip>/auth/verify
export DDM_SESSION_COOKIE_NAME=session_id      # 須與 LB 的 SESSION_COOKIE_NAME 相同
export DDM_ADMIN_EMPLOYEE_NO=<你的真實員編>
export DDM_PORT=8877                            # MOST 對外 port
docker compose up -d --build                    # 起 db + ddm-v2（前端已 build 進 image）
```

MOST 服務於 `http://<server-ip>:8877/`（前端 + `/api/v2` 同一容器同源）。

## 上線前檢查清單

- [ ] `ENV=production`：`AUTH_DEV_USER` 會被忽略；`DDM_SECRET_KEY` 不得是預設值且至少 32 字，否則啟動報錯。
- [ ] 移除 `AUTH_DEV_USER`。
- [ ] `DDM_AUTH_MODE=verify`，並設 `DDM_LB_VERIFY_URL`。
- [ ] `DDM_SESSION_COOKIE_NAME` 與 LB 一致。
- [ ] `DDM_ADMIN_EMPLOYEE_NO` 設為真實員編。
- [ ] `DDM_SECRET_KEY` 設為隨機字串。
- [ ] `DDM_CORS_ALLOW_ORIGINS` 設為對外網址。
- [ ] port 綁定：`docker-compose.yml` 預設 `127.0.0.1:${DDM_PORT}:8000`。**只有 verify 模式下才可以改成對外**；gateway 模式下改了，等於任何人不帶憑證就是 admin。
- [ ] AI 設定：預設關。開啟前提見實作計畫的「12 月開 AI 前的清單」（[ai-service-integration-plan](../roadmap/ai-service-integration-plan.md)）。金鑰用 docker secrets 檔案（`DDM_AI_SERVICE_KEY_FILE`），檔案權限 0400；`secrets/` 已在 `.gitignore`。

verify 模式的成本：每個請求都多打一次 LB `/auth/verify`（最多等 5 秒）；LB 連不到時 fail-closed，請求被視為未認證。

## 上線 .env 範本

`<…>` 由部署者填；正式環境的 LB 主機位址由 Howard 提供。

```bash
ENV=production
# AUTH_DEV_USER 不要設
DDM_AUTH_MODE=verify
DDM_LB_VERIFY_URL=http://<LB 主機位址>/auth/verify
DDM_SESSION_COOKIE_NAME=<與 LB 的 SESSION_COOKIE_NAME 相同>
DDM_ADMIN_EMPLOYEE_NO=<真實員編>
DDM_SECRET_KEY=<32 字以上的隨機字串>
DDM_CORS_ALLOW_ORIGINS=<MOST 對外網址，例 http://<LB 主機位址>:8877>
DDM_PORT=8877
# AI：預設關，條件滿足前不要開
DDM_AI_SERVICE_ENABLED=false
```

## 使用流程（給使用者）

1. 先到 LB 入口 `http://<server-ip>/` 用公司帳號登入（取得 session cookie）。
2. 開 `http://<server-ip>:8877/` → 直接進 MOST，身分即你的員編。
3. 角色:第一次進來的人自動建為 **viewer**（唯讀）。由 admin 到「⑦ 使用者」分頁授予 analyst（IE）/approver（manager）/admin。
   - 第一個 admin = `DDM_ADMIN_EMPLOYEE_NO`（開機種入），所以那一定要是真實、會登入的員編。
4. session 1 小時到期 → 回 LB 重新登入即可。

> 小瑕疵（可接受）:沒先在 LB 登入就裸開 MOST → 會是未認證（401/viewer）。請先登入 LB。

## 安全須知

- `verify` 模式 MOST 可直接開 port;`gateway` 模式則 MOST **只能經 Traefik 進**，不可直接曝露。
- LB 不可達時 verify **fail-closed**（視為未認證），不會放行。
- 登出走 LB `/auth/logout`（清掉共用 cookie = 兩邊一起登出）。

## 之後拿到網域 → 切到最終型態

把 MOST 併進 LB 的 Traefik（同一 gateway + `auth-verify@file`），`DDM_AUTH_MODE=gateway`，
不再需要 `DDM_LB_VERIFY_URL`。

已知兩個衝突（依據：LB repo 的 `docker-compose.yml` 與 `traefik/dynamic.yaml`；這是改 LB repo 的事，需 LB 團隊同意）：

- LB 的 `PathPrefix(/api)` 路由（`algo-api-docs`，priority 50）會搶走 MOST 的 `/api/v2`。
- LB 的 `/` 是登入頁（`auth-root`）。

所以 MOST 需要獨立網域，或 Traefik 的專用 port。屆時建議用子網域（`most.corp`）取得 origin 隔離;
cookie 設 `Domain=.corp` 即跨子網域共用、仍是 cookie 不發 token。認證那套不用重做。
