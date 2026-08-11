import { useQuery, useMutation } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../shared/api/client'

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

export const useWiPreview = (wsId: string) =>
  useQuery({ queryKey: ['wi-preview', wsId], queryFn: () => apiGet<WiPreview>(`/api/v2/worksheets/${wsId}/export/wi-preview`) })

export const useLbApi = (wsId: string) =>
  useMutation({ mutationFn: () => apiPost<LbApiResult>(`/api/v2/worksheets/${wsId}/export/lb-api`) })

// 下載走瀏覽器（dev：vite proxy→8099，AUTH_DEV_USER 生效）
export const downloadExcel = (wsId: string) => window.open(`/api/v2/worksheets/${wsId}/export/excel`, '_blank')
export const downloadCsv = (wsId: string) => window.open(`/api/v2/worksheets/${wsId}/export/lb-csv`, '_blank')
