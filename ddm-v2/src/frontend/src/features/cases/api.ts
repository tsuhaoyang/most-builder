// Cases feature — API hooks (G-01/02)
// All data sourced from backend; frontend renders only.
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../shared/api/client'

// ─── Domain types ─────────────────────────────────────────────────────────────

export interface CaseOut {
  process_version_id: string
  worksheet_id: string
  version_no: string
  status: 'draft' | 'approved' | 'retired'
  site_name: string
  product_name: string
  sku_name: string
  process_name: string
  total_tmu: number | null
  created_at: string
  approved_at: string | null
}

export interface CasesListResponse {
  total: number
  items: CaseOut[]
}

export type CaseStatus = 'draft' | 'approved' | 'retired' | ''

export interface AuditLogEntry {
  id: string
  entity_type: string
  entity_id: string
  action: string
  from_status: string | null
  to_status: string | null
  actor: string
  comment: string | null
  created_at: string
}

export interface AuditLogResponse {
  total: number
  items: AuditLogEntry[]
}

// ─── Query hooks ──────────────────────────────────────────────────────────────

export function useCases(params: { status?: CaseStatus; site_id?: string; limit?: number; offset?: number } = {}) {
  const searchParams = new URLSearchParams()
  if (params.status) searchParams.set('status', params.status)
  if (params.site_id) searchParams.set('site_id', params.site_id)
  if (params.limit != null) searchParams.set('limit', String(params.limit))
  if (params.offset != null) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString()
  const path = `/api/v2/cases${qs ? `?${qs}` : ''}`
  return useQuery({
    queryKey: ['cases', params],
    queryFn: () => apiGet<CasesListResponse>(path),
  })
}

export function useCaseAuditLog(processVersionId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['audit-log', 'process_version', processVersionId],
    queryFn: () =>
      apiGet<AuditLogResponse>(
        `/api/v2/audit-log?entity_type=process_version&entity_id=${processVersionId}`
      ),
    enabled: enabled && !!processVersionId,
  })
}

// ─── Mutation hooks ───────────────────────────────────────────────────────────

export function useApproveWorksheet(worksheetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<unknown>(`/api/v2/worksheets/${worksheetId}/publish`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cases'] })
      qc.invalidateQueries({ queryKey: ['audit-log', 'process_version'] })
    },
  })
}

export function useRetireWorksheet(worksheetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<unknown>(`/api/v2/worksheets/${worksheetId}/retire`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cases'] })
      qc.invalidateQueries({ queryKey: ['audit-log', 'process_version'] })
    },
  })
}
