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
// ADR-035 D10 F5：dev grid 用的原始 task 列（24 欄 dict，順序＝後端 emit.COLUMNS）。
// include_tasks=1 才有；一般預覽為 undefined。
export type LbTaskRow = Record<string, unknown>
export interface LbReport {
  contract_version: string
  tasks_out: number
  groups: Record<string, number[]>
  atomic_groups: Record<string, number[]>
  errors: LbReportDiag[]
  warnings: LbReportDiag[]
  rows: LbReportRow[]
  hints: LbHint[]
  tasks?: LbTaskRow[]
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
// includeTasks=true → 帶 include_tasks=1（F5 dev grid 要 report.tasks[]）。
export const useLbPreview = (worksheetId: string, includeTasks = false) =>
  useMutation({
    mutationFn: (body: unknown) =>
      apiPost<LbReport>(
        `/api/v2/worksheets/${worksheetId}/export/lb-report/preview${includeTasks ? '?include_tasks=1' : ''}`,
        body,
      ),
  })

// ── ADR-036 F1：LB 回寫消費（作業版產線視角「實際結果」）─────────────────────────
// 型別鏡像後端 lb_writeback_service 的回應（summarize / diff_to_dict / latest）。
export interface WbSummary {
  contract_version: string
  project_id: string
  version_id: string
  result_id: string
  unattended_machine_policy: string          // free / busy
  unattended_machine_policy_source: string    // persisted / defaulted
  rows_in: number
  motions: number
  matched: number
  unmatched: number
  missing: number
  cross_station: string[]
  offline_conflicts: string[]
}
export interface WbMotion {
  task_ids: number[]
  stations: number[]
  workers: string[]
  units_total: number | null
  offline: boolean
  cross_station: boolean
  offline_conflict: boolean
}
export interface WbDiff {
  matched: string[]
  unmatched: string[]
  missing: Array<{ wi_row_id: string; reason: string }>
  offline_diffs: Array<{ wi_row_id: string; most_offline: boolean; lb_offline: boolean }>
  unit_mismatches: Array<{ wi_row_id: string; expected_n: number; units_total: number }>
  motions: Record<string, WbMotion>
}
export interface WbLatest {
  snapshot_id: string
  fetched_at: string | null
  applied_at: string | null
  summary: WbSummary
  diff: WbDiff
}
export interface WbApplyResult {
  applied: string[]
  propagated: string[]
  report: { errors: unknown[]; warnings: unknown[] }
}

/** GET latest 快照（含聚合＋diff）；無快照 → 404（呼叫端以 enabled/isError 處理）。 */
export const useLbWriteback = (worksheetId: string, enabled = true) =>
  useQuery({
    queryKey: ['lb-writeback-latest', worksheetId],
    queryFn: () => apiGet<WbLatest>(`/api/v2/worksheets/${worksheetId}/lb-writeback/latest`),
    enabled: !!worksheetId && enabled,
    retry: false,               // 無快照的 404 不重試
    refetchOnWindowFocus: false,
  })

/** POST fetch：以 project/version/result id 呼叫 LB 存快照。 */
export const useFetchWriteback = (worksheetId: string) =>
  useMutation({
    mutationFn: (body: { lb_project_id: string; lb_version_id: string; lb_result_id: string }) =>
      apiPost<WbLatest>(`/api/v2/worksheets/${worksheetId}/lb-writeback/fetch`, body),
  })

/** POST apply-offline：勾選的 wi_row_ids 套用 LB 的 offline（走正門，任一 E 整批 rollback）。 */
export const useApplyOffline = (worksheetId: string) =>
  useMutation({
    mutationFn: (body: { snapshot_id: string; wi_row_ids: string[] }) =>
      apiPost<WbApplyResult>(`/api/v2/worksheets/${worksheetId}/lb-writeback/apply-offline`, body),
  })
