import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev：把 /api/v2 代理到後端（preview_server 預設 8099，含 AUTH_DEV_USER）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8099', changeOrigin: true } },
  },
})
