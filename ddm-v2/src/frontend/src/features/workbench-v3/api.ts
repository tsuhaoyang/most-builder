import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete } from '../../shared/api/client'

// ── Instantiate response (from-module endpoint) ────────────────────────────

export interface InstantiatedRowOut {
  wi_row_id: string
  seq_no: number
  sub_activity: string | null
  hand: string | null
  frequency: number
  simo_group_id: string | null
  source_module_id: string
  source_module_version: number
  total_tmu: number
  total_seconds: number
}

export interface InstantiateResponse {
  new_rows: InstantiatedRowOut[]
  tmu_drift: Array<{ row_index: number; module_tmu: number; actual_tmu: number; delta: number }>
}

// ── Domain types ───────────────────────────────────────────────────────────────

export interface MotionModuleRow {
  hand: string
  frequency: number
  cycle: Record<string, unknown>
  sub_activity: string | null
  simo_pair_index?: number | null
  vocab_refs?: Record<string, unknown>
}

/** MotionModuleVersionResponse — GET /motion-modules/{id} 的 current_version_detail */
export interface MotionModuleVersionDetail {
  id: string
  module_id: string
  version_no: number
  rule_set_id: string
  rows: MotionModuleRow[]
  narrative_zh: string | null
  total_tmu: number
  total_seconds: number
  published_by: string
  published_at: string
}

/**
 * MotionModuleResponse 合約（audit §0.1 更正版）：
 * rows 巢狀於 current_version_detail —— list 端點該欄=null，detail (GET /{id})
 * 才有；top-level total_tmu / action_count 為後端摘要欄（list + detail 皆有，
 * 模組尚無已發布版本時為 null）。後端從不回傳 top-level rows。
 */
export interface MotionModuleSummary {
  id: string
  name_zh: string
  category?: string | null
  keywords: string[]
  scope: string
  owner?: string | null
  status: string
  /** 後端 response 無此欄；僅作前端防禦保留（badge 不渲染即可） */
  source?: string
  current_version?: number
  /** 後端摘要欄：無已發布版本時為 null → UI 顯示 '—'，不得假裝是 0 */
  total_tmu?: number | null
  action_count?: number | null
  /** 後端摘要欄（取 current version 第一列）：'GM' | 'CM'；無版本時 null */
  seq_kind?: string | null
  /** 後端摘要欄（取 current version 第一列）：hand code；無版本時 null */
  hand?: string | null
  current_version_detail?: MotionModuleVersionDetail | null
  /** @deprecated 後端從不回傳 top-level rows；顯示邏輯請走 total_tmu / action_count / current_version_detail */
  rows?: MotionModuleRow[]
}

export interface CreateModuleBody {
  // 對齊後端 MotionModuleCreate：無 rows/status/source 欄位（rows 走 publish）
  name_zh: string
  category?: string
  keywords: string[]
  scope: string
  owner?: string
  site_id?: string | null
}

export interface PublishModuleBody {
  rows: MotionModuleRow[]
  /** rule_set_id（UUID）與 rule_set_code 二擇一 */
  rule_set_id?: string
  rule_set_code?: string
}

export interface ModuleFilters {
  scope?: string
  category?: string
  q?: string
}

// ── Query key ─────────────────────────────────────────────────────────────────

const QK = 'motion-modules' as const

// ── Queries ───────────────────────────────────────────────────────────────────

export const useMotionModules = (filters?: ModuleFilters) => {
  const params = new URLSearchParams()
  if (filters?.scope) params.append('scope', filters.scope)
  if (filters?.category) params.append('category', filters.category)
  if (filters?.q) params.append('q', filters.q)
  const qs = params.toString()
  return useQuery({
    queryKey: [QK, filters ?? {}],
    queryFn: () =>
      apiGet<MotionModuleSummary[]>(`/api/v2/motion-modules${qs ? '?' + qs : ''}`),
  })
}

/** 單一模組 detail（含 current_version_detail.rows）；list 不含 rows 時用此撈明細 */
export const useMotionModuleDetail = (id: string | null, enabled = true) =>
  useQuery({
    queryKey: [QK, 'detail', id],
    queryFn: () => apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${id}`),
    enabled: !!id && enabled,
    staleTime: 300_000,
  })

// ── Mutations ─────────────────────────────────────────────────────────────────

export const useCreateModule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateModuleBody) =>
      apiPost<MotionModuleSummary>('/api/v2/motion-modules', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK] }),
  })
}

export const useUpdateModule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<CreateModuleBody> }) =>
      apiPut<MotionModuleSummary>(`/api/v2/motion-modules/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK] }),
  })
}

export const useDeleteModule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/v2/motion-modules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK] }),
  })
}

export const useCloneModule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<MotionModuleSummary>(`/api/v2/motion-modules/${id}/clone`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK] }),
  })
}

export const usePublishModule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PublishModuleBody }) =>
      apiPost<MotionModuleSummary>(`/api/v2/motion-modules/${id}/publish`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK] }),
  })
}

// ── WI Template hooks (L2: category='wi-template') ────────────────────────────

const WI_QK = 'wi-templates' as const

export const useWiTemplates = () =>
  useQuery({
    queryKey: [WI_QK],
    queryFn: () =>
      apiGet<MotionModuleSummary[]>('/api/v2/motion-modules?category=wi-template'),
  })

export const useCreateWiTemplate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateModuleBody) =>
      apiPost<MotionModuleSummary>('/api/v2/motion-modules', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [QK] })
      qc.invalidateQueries({ queryKey: [WI_QK] })
    },
  })
}

export const useCloneWiTemplate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<MotionModuleSummary>(`/api/v2/motion-modules/${id}/clone`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [WI_QK] }),
  })
}

export const useDeleteWiTemplate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/v2/motion-modules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [WI_QK] }),
  })
}

// ── Instantiate WI template into worksheet (Tab 2 → Tab 3 add-to-process) ─

export const useInstantiateToWorksheet = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ worksheetId, moduleId }: { worksheetId: string; moduleId: string }) =>
      apiPost<InstantiateResponse>(
        `/api/v2/worksheets/${worksheetId}/rows/from-module`,
        { module_id: moduleId },
      ),
    onSuccess: (_data, { worksheetId }) => {
      qc.invalidateQueries({ queryKey: ['worksheet', worksheetId] })
    },
  })
}

// ── Apply-back（F-03b §3）：從工序表列發布模組新版本 ─────────────────────

/** POST /motion-modules/{id}/versions/from-rows 的回應（同版本 detail 形狀） */
export type VersionFromRowsResult = MotionModuleVersionDetail

/** 送給 from-rows 的單列資料（slot_inputs 即 CycleIn JSON，直接回傳後端） */
export interface ApplyBackRowIn {
  sub_activity: string | null
  hand: string
  frequency: number
  simo_pair_index: number | null
  vocab_refs: Record<string, unknown>
  cycle: unknown   // WsReadRow.cycle.slot_inputs — 原始 CycleIn JSON
}

export const useVersionFromRows = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      moduleId,
      rows,
      ruleSetId,
    }: {
      moduleId: string
      rows: ApplyBackRowIn[]
      ruleSetId: string
    }) =>
      apiPost<VersionFromRowsResult>(
        `/api/v2/motion-modules/${moduleId}/versions/from-rows`,
        { rows, rule_set_id: ruleSetId },
      ),
    onSuccess: () => {
      // 重整模組列表（新版本已發布）
      qc.invalidateQueries({ queryKey: [QK] })
      qc.invalidateQueries({ queryKey: [WI_QK] })
    },
  })
}
