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
export interface LbReportDiag { code: string; wi_row_id: string | null; message: string }
export interface LbReport {
  contract_version: string
  tasks_out: number
  groups: Record<string, number[]>
  atomic_groups: Record<string, number[]>
  errors: LbReportDiag[]
  warnings: LbReportDiag[]
}

// v1：只有存檔後才啟用預覽（enabled 由呼叫端在存檔後開啟）。
export const useLbReport = (worksheetId: string, enabled: boolean) =>
  useQuery({
    queryKey: ['lb-report', worksheetId],
    queryFn: () => apiGet<LbReport>(`/api/v2/worksheets/${worksheetId}/export/lb-report`),
    enabled: !!worksheetId && enabled,
    refetchOnWindowFocus: false,
  })
