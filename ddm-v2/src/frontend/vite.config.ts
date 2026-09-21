import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev：把 /api/v2 代理到後端（preview_server 預設 8099，含 AUTH_DEV_USER）。
// DDM_API_TARGET 可覆寫——同時跑兩個 preview_server（例如驗證改動時另起一個新建置）時，
// 不必改這個檔就能把 dev 前端指過去：`DDM_API_TARGET=http://127.0.0.1:8097 npm run dev`。
// 兩個覆寫都 Fail-Fast：連錯了最糟的結果是「看起來有跑、其實打到別的東西」（空字串會讓
// Number('') === 0＝隨機埠、target 空字串會靜默失效），而 proxy target 決定 dev 前端把工序表與
// 身分 header 送去哪裡——只允許 loopback，要指到別處必須顯式開關。
function devPort(): number {
  const raw = process.env.DDM_DEV_PORT
  if (raw === undefined || raw === '') return 5173
  const n = Number(raw)
  if (!Number.isInteger(n) || n <= 0 || n > 65535) throw new Error(`DDM_DEV_PORT 不是合法埠號：${raw}`)
  return n
}

function apiTarget(): string {
  const raw = process.env.DDM_API_TARGET
  if (raw === undefined || raw === '') return 'http://127.0.0.1:8099'
  const u = new URL(raw)  // 解不動就讓它炸
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error(`DDM_API_TARGET 只能是 http(s)：${raw}`)
  const loopback = ['127.0.0.1', 'localhost', '[::1]', '::1'].includes(u.hostname)
  if (!loopback && process.env.DDM_ALLOW_REMOTE_API_TARGET !== '1') {
    throw new Error(`DDM_API_TARGET 非 loopback（${u.hostname}）；確定要的話設 DDM_ALLOW_REMOTE_API_TARGET=1`)
  }
  return raw
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: devPort(),
    strictPort: true,  // 埠被佔用時直接失敗，不要靜默跳號讓測試打到別的建置
    proxy: { '/api': { target: apiTarget(), changeOrigin: true } },
  },
})
