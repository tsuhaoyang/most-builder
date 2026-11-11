import { defineConfig } from '@playwright/test'

// e2e baseURL：
//   單一伺服器預覽（含 DB）：E2E_BASE_URL=http://127.0.0.1:8099（preview_server）
//   熱重載 dev：預設 http://127.0.0.1:5173（需另跑後端 + npm run dev）
//
// ADR-032 Phase A：locale 鎖定（風險段——11 個既有 spec 以中文文字定位）。
// 兩層鎖，理由不同：
//   1. `globalSetup`：把共用開發 DB 裡 e2e 身分（IEC141289）的 `locale` 重置為
//      zh-TW（真正的權威來源，App 的 useLocaleSync 一律以 /me 為準）。
//   2. `use.locale`：Playwright 瀏覽器層的 `navigator.language`/`Intl`。目前
//      App 不讀這個（ADR-032 已明文否決 Accept-Language 偵測），設定它本身
//      不影響行為，是防禦性收斂——若未來不慎加回瀏覽器偵測，這裡先鎖住，
//      不會讓 CI 環境的系統語系悄悄滲入。
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    locale: 'zh-TW',
  },
})
