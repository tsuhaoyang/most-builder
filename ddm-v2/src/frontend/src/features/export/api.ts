import { useMutation } from '@tanstack/react-query'
import { apiPost } from '../../shared/api/client'

export interface WiPreviewRow {
  seq_no?: number
  sub_activity?: string
  method?: string
  hand?: string
  freq?: number
  tmu?: number | null
}
export interface WiPreview {
  worksheet_id: string
  status: string
  total_tmu: number
  rows: WiPreviewRow[]
}
export interface LbApiResult { status: string; note: string; worksheet_id: string; payload: unknown }

// 匯出面板本體已收進 features/cases/CasesPage.tsx（ADR-021 Phase 3）；
// 這裡只留該頁實際用到的東西。原有的 `useWiPreview` hook 隨舊 ExportPanel 一併移除——
// CasesPage 是在 onClick 裡直接 `apiGet<WiPreview>` 取預覽（按下才抓，不是掛載即抓）。
export const useLbApi = (wsId: string) =>
  useMutation({ mutationFn: () => apiPost<LbApiResult>(`/api/v2/worksheets/${wsId}/export/lb-api`) })

// 下載走瀏覽器（dev：vite proxy→8099，AUTH_DEV_USER 生效）
export const downloadExcel = (wsId: string) => window.open(`/api/v2/worksheets/${wsId}/export/excel`, '_blank')
export const downloadCsv = (wsId: string) => window.open(`/api/v2/worksheets/${wsId}/export/lb-csv`, '_blank')
