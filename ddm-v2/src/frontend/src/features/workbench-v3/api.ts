import { useQuery, useQueries, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete, apiDeleteJson } from '../../shared/api/client'

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

/** ADR-022 A-1：publish 時引擎算好、持久化在 rows JSON 的每列計算結果（前端永不自算） */
export interface ModuleRowComputed {
  total_tmu: number
  total_seconds: number
  eff_tmu: number
  contribution_tmu: number
}

export interface MotionModuleRow {
  hand: string
  frequency: number
  cycle: Record<string, unknown>
  sub_activity: string | null
  simo_pair_index?: number | null
  vocab_refs?: Record<string, unknown>
  /** ADR-022 A-1 批次 A 後端寫入；批次 A 之前發布的版本可能缺 → UI 顯示 '—' */
  computed?: ModuleRowComputed | null
  narrative_zh?: string | null
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
const WI_QK = 'wi-templates' as const

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

/**
 * 批次撈多個模組 detail（動作清單每列需 rows[0] 的 frequency / computed）。
 * queryKey 與 useMotionModuleDetail 相同 → 快取共用；invalidate [QK] 前綴一併重整。
 */
export const useModuleDetails = (ids: string[]) =>
  useQueries({
    queries: ids.map(id => ({
      queryKey: [QK, 'detail', id],
      queryFn: () => apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${id}`),
      staleTime: 300_000,
    })),
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

// ── Row 級操作（ADR-022 A-2：WiItemInspector / WI 大綱子列）─────────────────────
// 每個操作都由後端引擎重算並發新版本，回應＝新版本 detail（rows 含 computed）。
// 錯誤（422）：EMPTY_ROWS（刪到 0 列）、SIMO_PAIR_INVALID（刪被 SIMO 指向的主列等）。
//
// 快取策略：回應即權威新版本 → 直接寫入 detail / WI 列表快取（setQueriesData），
// 不走 invalidate 重抓——後端目前有「回應先於 commit 可見」的 race（已回報），
// 立即 refetch 會撈到舊版並被 staleTime 快取住。

function applyVersionToCaches(qc: QueryClient, id: string, ver: MotionModuleVersionDetail) {
  // detail 快取（[QK,'detail',id]）：換上新版本內容與摘要欄
  qc.setQueryData<MotionModuleSummary | undefined>([QK, 'detail', id], old =>
    old
      ? {
          ...old,
          current_version: ver.version_no,
          current_version_detail: ver,
          total_tmu: ver.total_tmu,
          action_count: ver.rows.length,
        }
      : old)
  // WI 列表快取（[WI_QK]）：更新該筆摘要（total_tmu / action_count / current_version）
  qc.setQueriesData<MotionModuleSummary[] | undefined>({ queryKey: [WI_QK] }, old =>
    Array.isArray(old)
      ? old.map(m =>
          m.id === id
            ? { ...m, current_version: ver.version_no, total_tmu: ver.total_tmu, action_count: ver.rows.length }
            : m)
      : old)
}

export const useUpdateModuleRow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, rowIndex, row }: { id: string; rowIndex: number; row: MotionModuleRow }) =>
      apiPut<MotionModuleVersionDetail>(`/api/v2/motion-modules/${id}/rows/${rowIndex}`, row),
    onSuccess: (ver, { id }) => applyVersionToCaches(qc, id, ver),
  })
}

export const useReorderModuleRows = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, orderedIndexes }: { id: string; orderedIndexes: number[] }) =>
      apiPost<MotionModuleVersionDetail>(`/api/v2/motion-modules/${id}/rows/reorder`, {
        ordered_indexes: orderedIndexes,
      }),
    onSuccess: (ver, { id }) => applyVersionToCaches(qc, id, ver),
  })
}

export const useDeleteModuleRow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, rowIndex }: { id: string; rowIndex: number }) =>
      apiDeleteJson<MotionModuleVersionDetail>(`/api/v2/motion-modules/${id}/rows/${rowIndex}`),
    onSuccess: (ver, { id }) => applyVersionToCaches(qc, id, ver),
  })
}

// ── WI Template hooks (L2: category='wi-template') ────────────────────────────

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
