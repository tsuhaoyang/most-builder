import { useMutation, useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../shared/api/client'
import type { LevelPayloadRow } from './logic'

export interface LevelIssue { code: string; row_index: number; message: string }
export interface LevelValidateResult { valid: boolean; issues: LevelIssue[] }

// R1–R9 驗證（後端權威）
export const useValidateLevel = () =>
  useMutation({ mutationFn: (rows: LevelPayloadRow[]) =>
    apiPost<LevelValidateResult>('/api/v2/level/validate', rows) })

// ── WP12（ADR-035）LB 投影預覽（後端才是投影權威；前端不另建投影路徑）───────────────
// lb-report 讀的是**已存檔**的 worksheet；報告無 per-task rows，只有彙總與 E/W 診斷。
export interface LbReportDiag { code: string; wi_row_id: string | null; message: string; params?: Record<string, unknown> | null }
export interface LbReportRow {
  wi_row_id: string
  task_ids: number[]
  tool_id: string | null
  parts: string[]
  repeat_n: number | null
  frequency: number
  quantity: number
  qty_scope: string | null
  x_seconds: number
  is_general: boolean
  general_role: string | null
  duration_ms_total: number
}
export interface LbHint { kind: string; key: string; wi_row_ids: string[]; params: Record<string, unknown> }
export interface LbReport {
  contract_version: string
  tasks_out: number
  groups: Record<string, number[]>
  atomic_groups: Record<string, number[]>
  errors: LbReportDiag[]
  warnings: LbReportDiag[]
  rows: LbReportRow[]
  hints: LbHint[]
}

// v1：只有存檔後才啟用預覽（enabled 由呼叫端在存檔後開啟）。
export const useLbReport = (worksheetId: string, enabled: boolean) =>
  useQuery({
    queryKey: ['lb-report', worksheetId],
    queryFn: () => apiGet<LbReport>(`/api/v2/worksheets/${worksheetId}/export/lb-report`),
    enabled: !!worksheetId && enabled,
    refetchOnWindowFocus: false,
  })

// 作業版預覽（dry-run，ADR-035 D10 B3）：POST 未存檔 rows → 同一投影路徑的 report。
// 不寫 DB、不另建前端投影（後端權威）。呼叫端以 debounce + latest-wins 節流（F6）。
export const useLbPreview = (worksheetId: string) =>
  useMutation({
    mutationFn: (body: unknown) =>
      apiPost<LbReport>(`/api/v2/worksheets/${worksheetId}/export/lb-report/preview`, body),
  })
