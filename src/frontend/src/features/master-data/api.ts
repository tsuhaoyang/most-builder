import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiDelete } from '../../shared/api/client'

export type VocabKind = 'object' | 'component' | 'tool' | 'from' | 'to' | 'hand'
export interface VocabItem { id: string; kind: string; name_zh: string; name_en: string | null; external_code: string | null; source_system: string; is_active: boolean }
export interface VocabIn { kind: VocabKind; name_zh: string; name_en?: string | null; external_code?: string | null }

// 共用 queryKey ['vocab']：建立/刪除後 invalidate → WI/Level 的下拉也即時更新（單一快取真相）
export const useVocabList = () =>
  useQuery({ queryKey: ['vocab'], queryFn: () => apiGet<VocabItem[]>('/api/v2/vocab') })

export function useCreateVocab() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: VocabIn) => apiPost<VocabItem>('/api/v2/vocab', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vocab'] }),
  })
}

export function useDeleteVocab() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/v2/vocab/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vocab'] }),
  })
}
