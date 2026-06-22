import { defineConfig } from '@playwright/test'

// e2e baseURL：
//   單一伺服器預覽（含 DB）：E2E_BASE_URL=http://127.0.0.1:8099（preview_server）
//   熱重載 dev：預設 http://127.0.0.1:5173（需另跑後端 + npm run dev）
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173' },
})
