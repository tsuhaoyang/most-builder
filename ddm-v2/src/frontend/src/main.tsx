import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './shared/i18n/i18n' // 必須在 App 渲染前初始化（ADR-032 D3.2：首屏讀 localStorage 快取）
import './index.css'

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
