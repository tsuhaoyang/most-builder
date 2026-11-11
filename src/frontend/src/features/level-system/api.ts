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
  // 件數比對基準：ok＝已用 MOST 投影 Q 比對；unavailable＝MOST 目前投影不出來（reasons＝E 碼），件數沒比；
  // not_needed＝LB 沒帶件數
  units_baseline: { status: 'ok' | 'unavailable' | 'not_needed'; reasons: string[] }
}
export interface WbMotion {
  task_ids: number[]
  stations: number[]
  workers: string[]
  units_total: number | null
  // 件數來源：cyclic＝LB 回寫帶 qty_scope、取 cyclic 列；inferred_max＝缺 qty_scope 時各列取最大值的推算值
  units_source: 'cyclic' | 'inferred_max' | null
  offline: boolean
  cross_station: boolean
  offline_conflict: boolean
  // LB 對這一步的件數沒有把握、主動降級（LB §8 export_warnings.units_degraded）；沒有就是空清單。
  // 舊後端回應沒有這個欄 → undefined。
  units_degraded?: WbUnitsDegraded[]
}
// reason：conservation＝cyclic 列 Σunits 對不上數量（兩數可比）；setup_not_one＝取放列的經手人次異常
// （units_sum 是 Σused，與 quantity 本來就不該相等——**不得**並排成「應為 X、實為 Y」）；unknown＝LB 新加的原因
export interface WbUnitsDegraded {
  task_id: number          // LB 端的 id，只供人回 LB 找列
  units_sum: number | null // 已知 reason 必有；unknown 時可能為 null（LB 新 reason 不一定帶）
  quantity: number | null
  reason: 'conservation' | 'setup_not_one' | 'unknown'
  reason_raw?: string
}
// present=false＝payload 沒有這個欄（舊 LB／舊快照＝不知道），三欄為 null；不是「LB 明說沒事」
export interface WbExportWarnings {
  present: boolean
  units_degraded: Array<WbUnitsDegraded & { source_wi_row_id: string }> | null
  dropped_rows: Array<{ task_id: number; reason: 'source_wi_row_id_not_uuid' | 'unknown'; reason_raw?: string }> | null
  truncated: boolean | null
  limit: number                        // 清單上限（MOST 端自己的）；「只列前 N 筆」用這個，不寫死
  unattached_units_degraded?: number   // 對不上本工序表任何步驟的降級筆數（present 時才有）
}
export interface WbDiff {
  matched: string[]
  unmatched: string[]
  // lb_dropped_possible：LB 這次丟了對應鍵損壞的列、對應不回是哪一步，這一步**可能**是其中之一。
  // reason 不變（原本的歸因與下一步仍然有效），旗標只是補一句
  missing: Array<{ wi_row_id: string; reason: string; lb_dropped_possible?: boolean }>
  offline_diffs: Array<{ wi_row_id: string; most_offline: boolean; lb_offline: boolean }>
  unit_mismatches: Array<{ wi_row_id: string; expected_n: number; units_total: number; units_source: WbMotion['units_source'] }>
  units_uncomparable: Array<{ wi_row_id: string; expected_n: number; reason: string }>
  motions: Record<string, WbMotion>
  export_warnings?: WbExportWarnings
}
export interface WbLatest {
  snapshot_id: string
  fetched_at: string | null
  applied_at: string | null
  // 套用當下投影那一關的狀態（存進 applied_rows，重整後仍在）；舊快照沒有這兩欄 → undefined
  applied_report_status?: 'ok' | 'unavailable' | null
  applied_report_reasons?: string[]
  // 完整診斷（code/wi_row_id/message/params）——日後要把 E 碼翻成「第 n 步：…」需要它
  applied_report_errors?: WbReportError[]
  summary: WbSummary
  diff: WbDiff
}
export interface WbReportError {
  code: string
  wi_row_id: string | null
  message: string
  params?: Record<string, unknown> | null
}
export interface WbApplyResult {
  applied: string[]
  propagated: string[]
  // status：ok＝投影報告算得出來（E 碼照常擋並整批取消）；unavailable＝投影此刻拋例外（reasons 附 E 碼），
  // E 碼那一關無從判定——離線設定仍已套用（R1–R9 照常擋），但不可讀成「投影沒問題」
  // errors／warnings 在 unavailable 時是 null（＝沒算出來），不是 []（＝算過、沒問題）
  report: {
    status: 'ok' | 'unavailable'
    reasons: string[]
    reason_details: WbReportError[]
    errors: unknown[] | null
    warnings: unknown[] | null
  }
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
