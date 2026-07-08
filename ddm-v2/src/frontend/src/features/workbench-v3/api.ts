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
  sub_activity: string
}

export interface MotionModuleSummary {
  id: string
  name_zh: string
  category?: string
  keywords: string[]
  scope: string
  owner?: string
  status: string
  source?: string
  rows: MotionModuleRow[]
  total_tmu?: number
}

export interface CreateModuleBody {
  name_zh: string
  category?: string
  keywords: string[]
  scope: string
  owner?: string
  rows: MotionModuleRow[]
  status?: string
  source?: string
}

export interface PublishModuleBody {
  rows: MotionModuleRow[]
  rule_set_id?: string
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
