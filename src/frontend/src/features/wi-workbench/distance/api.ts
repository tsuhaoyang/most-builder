// 區域、DSX 同步、物件歸區、距離建議與設定（ADR-038 D5；後端 W7a／W7b）。型別取自 api.d.ts。
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '../../../shared/api/client'
import type { components } from '../../../shared/types/api'

type S = components['schemas']
export type ZoneCategory = S['ZoneCategoryOut']
export type Zone = S['ZoneOut']
export type ZoneList = S['ZoneListOut']
export type DsxObjects = S['DsxObjectListOut']
export type SyncResult = S['SyncOut']
export type ObjectZones = S['ObjectZoneListOut']
export type WorksheetObjects = S['WorksheetObjectsOut']
export type Suggestions = S['DistanceSuggestionListOut']
export type Suggestion = S['DistanceSuggestionOut']
export type DistanceSettings = S['DistanceSettingsOut']

export const keys = {
  categories: ['zone-categories'] as const,
  zones: (sku: string) => ['sku-zones', sku] as const,
  dsxObjects: ['dsx-objects'] as const,
  objectZones: (sku: string) => ['object-zones', sku] as const,
  wsObjects: (ws: string) => ['worksheet-objects', ws] as const,
  suggestions: (ws: string) => ['distance-suggestions', ws] as const,
  settings: ['distance-settings'] as const,
}

export const useCategories = () =>
  useQuery({ queryKey: keys.categories, queryFn: () => apiGet<ZoneCategory[]>('/api/v2/zone-categories') })

export const useWorksheetObjects = (ws: string) =>
  useQuery({ queryKey: keys.wsObjects(ws), queryFn: () => apiGet<WorksheetObjects>(`/api/v2/worksheets/${ws}/objects`), enabled: !!ws })

export const useZones = (sku: string | undefined) =>
  useQuery({ queryKey: keys.zones(sku ?? ''), queryFn: () => apiGet<ZoneList>(`/api/v2/skus/${sku}/zones`), enabled: !!sku })

/** 只在使用者打開區域設定時才查 DSX（DSX 在內網，查一次就好）。 */
export const useDsxObjects = (enabled: boolean) =>
  useQuery({ queryKey: keys.dsxObjects, queryFn: () => apiGet<DsxObjects>('/api/v2/dsx/objects'), enabled, staleTime: 60_000 })

export const useSuggestions = (ws: string) =>
  useQuery({ queryKey: keys.suggestions(ws), queryFn: () => apiGet<Suggestions>(`/api/v2/worksheets/${ws}/distance-suggestions`), enabled: !!ws })

export const useDistanceSettings = () =>
  useQuery({ queryKey: keys.settings, queryFn: () => apiGet<DistanceSettings>('/api/v2/modeling-policy/distance-settings') })

function useInvalidating<TIn, TOut>(fn: (i: TIn) => Promise<TOut>, invalidate: (qc: ReturnType<typeof useQueryClient>) => void) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSettled: () => invalidate(qc) })
}

export function useZoneMutations(sku: string, ws: string) {
  const refresh = (qc: ReturnType<typeof useQueryClient>) => {
    void qc.invalidateQueries({ queryKey: keys.zones(sku) })
    void qc.invalidateQueries({ queryKey: keys.objectZones(sku) })
    void qc.invalidateQueries({ queryKey: keys.wsObjects(ws) })
  }
  return {
    create: useInvalidating((b: { category_id: string; name: string; dsx_object_id?: string | null }) =>
      apiPost<Zone>(`/api/v2/skus/${sku}/zones`, b), refresh),
    patch: useInvalidating(({ id, body }: { id: string; body: Record<string, unknown> }) =>
      apiPatch<Zone>(`/api/v2/zones/${id}`, body), refresh),
    remove: useInvalidating((id: string) => apiDelete(`/api/v2/zones/${id}`), refresh),
    sync: useInvalidating(() => apiPost<SyncResult>(`/api/v2/skus/${sku}/zones/sync`), refresh),
    assign: useInvalidating((items: Array<{ vocab_item_id: string; zone_id: string | null }>) =>
      apiPut<ObjectZones>(`/api/v2/skus/${sku}/object-zones`, { items }), refresh),
  }
}

export function useDistanceMutations(ws: string) {
  const qc = useQueryClient()
  return {
    compute: useMutation({
      mutationFn: () => apiPost<Suggestions>(`/api/v2/worksheets/${ws}/distance-suggestions/compute`),
      onSuccess: (data) => qc.setQueryData(keys.suggestions(ws), data),
    }),
    apply: useMutation({
      mutationFn: (b: { base_revision: number; computed_at: string; wi_row_ids: string[] }) =>
        apiPost<{ revision_no?: number; rows: Array<{ wi_row_id: string }> }>(
          `/api/v2/worksheets/${ws}/distance-suggestions/apply`, b),
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: keys.suggestions(ws) })
        void qc.invalidateQueries({ queryKey: ['worksheet', ws] })
      },
    }),
    publishSettings: useMutation({
      mutationFn: (b: { reach_foot_threshold_cm: number; person_offset_cm: number[] }) =>
        apiPost<DistanceSettings>('/api/v2/modeling-policy/distance-settings', b),
      onSuccess: (data) => qc.setQueryData(keys.settings, data),
    }),
  }
}
