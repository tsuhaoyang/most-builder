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
| `DDM_PORT` | MOST 對外 port | 例 `8100` |
| `AUTH_DEV_USER` | 本地 dev 用；**部署時不要設** | （留空） |

## 過渡部署（verify 模式、自己的 port）

```bash
cd ddm-v2
# .env 或直接 export
export DDM_AUTH_MODE=verify
export DDM_LB_VERIFY_URL=http://<server-ip>/auth/verify
export DDM_SESSION_COOKIE_NAME=session_id      # 須與 LB 的 SESSION_COOKIE_NAME 相同
export DDM_ADMIN_EMPLOYEE_NO=<你的真實員編>
export DDM_PORT=8100                            # MOST 對外 port
docker compose up -d --build                    # 起 db + ddm-v2（前端已 build 進 image）
```

MOST 服務於 `http://<server-ip>:8100/`（前端 + `/api/v2` 同一容器同源）。

## 使用流程（給使用者）

1. 先到 LB 入口 `http://<server-ip>/` 用公司帳號登入（取得 session cookie）。
2. 開 `http://<server-ip>:8100/` → 直接進 MOST，身分即你的員編。
3. 角色:第一次進來的人自動建為 **viewer**（唯讀）。由 admin 到「⑦ 使用者」分頁授予 IE/manager/admin。
   - 第一個 admin = `DDM_ADMIN_EMPLOYEE_NO`（開機種入），所以那一定要是真實、會登入的員編。
4. session 1 小時到期 → 回 LB 重新登入即可。

> 小瑕疵（可接受）:沒先在 LB 登入就裸開 MOST → 會是未認證（401/viewer）。請先登入 LB。

## 安全須知

- `verify` 模式 MOST 可直接開 port;`gateway` 模式則 MOST **只能經 Traefik 進**，不可直接曝露。
- LB 不可達時 verify **fail-closed**（視為未認證），不會放行。
- 登出走 LB `/auth/logout`（清掉共用 cookie = 兩邊一起登出）。

## 之後拿到網域 → 切到最終型態

把 MOST 併進 LB 的 Traefik（同一 gateway + `auth-verify@file`），`DDM_AUTH_MODE=gateway`，
不再需要 `DDM_LB_VERIFY_URL`。屆時建議用子網域（`most.corp`）取得 origin 隔離;
cookie 設 `Domain=.corp` 即跨子網域共用、仍是 cookie 不發 token。認證那套不用重做。
