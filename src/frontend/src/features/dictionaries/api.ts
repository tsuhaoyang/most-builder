/**
 * Dictionaries feature API hooks.
 * - WorkVocabItem  → GET/POST/PATCH /api/v2/vocab
 * - MotionTemplate → GET /api/v2/motion-templates, POST /api/v2/motion-templates/{id}/promote
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPatch, apiDelete } from '../../shared/api/client'

// ── WorkVocabItem ─────────────────────────────────────────────────────────────

export interface VocabItem {
  id: string
  kind: string
  name_zh: string
  name_en: string | null
  external_code: string | null
  source_system: string
  is_active: boolean
}

export interface VocabFilters {
  kind?: string
  q?: string
  limit?: number
  offset?: number
  include_inactive?: boolean
}

export interface VocabItemCreate {
  kind: string
  name_zh: string
  name_en?: string
  source_system?: string
}

export interface VocabItemPatch {
  name_zh?: string
  name_en?: string
  external_code?: string
  is_active?: boolean
}

const VOCAB_QK = 'vocab-items' as const

export function useVocabItems(filters?: VocabFilters) {
  const params = new URLSearchParams()
  if (filters?.kind) params.append('kind', filters.kind)
  if (filters?.q) params.append('q', filters.q)
  if (filters?.limit != null) params.append('limit', String(filters.limit))
  if (filters?.offset != null) params.append('offset', String(filters.offset))
  if (filters?.include_inactive) params.append('include_inactive', 'true')
  const qs = params.toString()
  return useQuery({
    queryKey: [VOCAB_QK, filters ?? {}],
    queryFn: () => apiGet<VocabItem[]>(`/api/v2/vocab${qs ? '?' + qs : ''}`),
  })
}

export function useCreateVocabItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: VocabItemCreate) => apiPost<VocabItem>('/api/v2/vocab', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [VOCAB_QK] }),
  })
}

export function usePatchVocabItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: VocabItemPatch }) =>
      apiPatch<VocabItem>(`/api/v2/vocab/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [VOCAB_QK] }),
  })
}

export function useDeleteVocabItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/v2/vocab/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [VOCAB_QK] }),
  })
}

// ── MotionTemplate ────────────────────────────────────────────────────────────

export interface MotionTemplateSummary {
  id: string
  name_zh: string
  name_en: string | null
  category: string | null
  keywords: string[]
  seq_kind: string
  cycle_template: Record<string, unknown>
  status: string     // 'draft' | 'standard'
  owner: string | null
  is_active: boolean
}

export interface TemplateFilters {
  q?: string
  status?: string
}

const TEMPLATE_QK = 'dict-motion-templates' as const

export function useMotionTemplates(filters?: TemplateFilters) {
  return useQuery({
    queryKey: [TEMPLATE_QK, filters ?? {}],
    queryFn: () => apiGet<MotionTemplateSummary[]>('/api/v2/motion-templates'),
    select: (data) => {
      let result = data
      if (filters?.status) result = result.filter(t => t.status === filters.status)
      if (filters?.q) {
        const lower = filters.q.toLowerCase()
        result = result.filter(t =>
          t.name_zh.toLowerCase().includes(lower) ||
          (t.name_en ?? '').toLowerCase().includes(lower) ||
          t.keywords.some(k => k.toLowerCase().includes(lower)),
        )
      }
      return result
    },
  })
}

export function usePromoteTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<MotionTemplateSummary>(`/api/v2/motion-templates/${id}/promote`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [TEMPLATE_QK] }),
  })
}
