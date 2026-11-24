// 工作區編輯區 API（ADR-038 D2／D3；後端 W1／W3）。型別一律取自 OpenAPI 產生的 api.d.ts。
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPatch, apiPost } from '../../../shared/api/client'
import type { components } from '../../../shared/types/api'

export type WiDraft = components['schemas']['WiDraftOut']
export type WiDraftContent = components['schemas']['WiDraftContent']
export type WiDraftList = components['schemas']['WiDraftListOut']
export type WiDraftCommitOut = components['schemas']['WiDraftCommitOut']
export type FromSentenceOut = components['schemas']['WiDraftFromSentenceOut']
export type WiAiStatus = components['schemas']['WiAiStatusOut']

export const draftsKey = (wsId: string) => ['worksheet-drafts', wsId] as const

export const useDrafts = (wsId: string, enabled = true) =>
  useQuery({
    queryKey: draftsKey(wsId),
    queryFn: () => apiGet<WiDraftList>(`/api/v2/worksheets/${wsId}/drafts`),
    enabled: !!wsId && enabled,
    refetchOnWindowFocus: false,
  })

/** 寫入類動作成功後一律重新讀編輯區（後端是權威）。 */
function useDraftMutation<TIn, TOut>(wsId: string, fn: (input: TIn) => Promise<TOut>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => qc.invalidateQueries({ queryKey: draftsKey(wsId) }),
  })
}

export const useCreateDrafts = (wsId: string) =>
  useDraftMutation(wsId, (items: Array<{ content: WiDraftContent; group_key?: string; order_in_group?: number }>) =>
    apiPost<WiDraftList>(`/api/v2/worksheets/${wsId}/drafts`, { items }))

export const usePatchDraft = (wsId: string) =>
  useDraftMutation(wsId, ({ id, content }: { id: string; content: WiDraftContent }) =>
    apiPatch<WiDraft>(`/api/v2/worksheet-drafts/${id}`, { content }))

export const useDeleteDraft = (wsId: string) =>
  useDraftMutation(wsId, (id: string) => apiDelete(`/api/v2/worksheet-drafts/${id}`))

export const useConfirmDrafts = (wsId: string) =>
  useDraftMutation(wsId, (body: { draft_ids: string[] } | { group_key: string }) =>
    apiPost<WiDraftList>(`/api/v2/worksheets/${wsId}/drafts/confirm`, body))

export const useCommitDrafts = (wsId: string) =>
  useDraftMutation(wsId, (baseRevision: number) =>
    apiPost<WiDraftCommitOut>(`/api/v2/worksheets/${wsId}/drafts/commit`, { base_revision: baseRevision }))

export const useBlankFromImport = (wsId: string) =>
  useDraftMutation(wsId, (importRowIds: string[]) =>
    apiPost<WiDraftList>(`/api/v2/worksheets/${wsId}/drafts/blank-from-import`, { import_row_ids: importRowIds }))

export const useFromSentence = (wsId: string) =>
  useDraftMutation(wsId, (body: { text: string; hand?: string | null; wi_group?: string | null }) =>
    apiPost<FromSentenceOut>(`/api/v2/worksheets/${wsId}/drafts/from-sentence`, body))

export const useWiAiStatus = () =>
  useQuery({
    queryKey: ['wi-ai-status'],
    queryFn: () => apiGet<WiAiStatus>('/api/v2/wi-ai/status'),
    staleTime: 60_000,
  })
