import { defineConfig } from '@playwright/test'

// e2e：對 dev server 跑。需先啟動後端(preview_server)與 `npm run dev`。
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:5173' },
})
