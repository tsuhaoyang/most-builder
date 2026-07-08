import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPatch } from '../../shared/api/client'

export interface Site { id: string; external_code: string | null; name_zh: string; name_en: string | null; is_active: boolean }
export interface Product { id: string; site_id: string; external_code: string | null; name_zh: string; name_en: string | null; description: string | null; is_active: boolean }
export interface Sku { id: string; product_id: string; sku_code: string; name_zh: string | null; name_en: string | null; is_active: boolean }
export interface WorksheetSummary { worksheet_id: string; version_no: string; status: string; analyst: string | null; model_label: string | null }

export const useSites = () => useQuery({ queryKey: ['sites'], queryFn: () => apiGet<Site[]>('/api/v2/sites') })

export const useProducts = (siteId?: string) =>
  useQuery({ queryKey: ['products', siteId ?? 'all'], queryFn: () => apiGet<Product[]>(`/api/v2/products${siteId ? `?site_id=${siteId}` : ''}`) })

export const useSkus = (productId?: string) =>
  useQuery({ queryKey: ['skus', productId], queryFn: () => apiGet<Sku[]>(`/api/v2/skus?product_id=${productId}`), enabled: !!productId })

export const useWorksheetsBySku = (skuId?: string) =>
  useQuery({ queryKey: ['sku-worksheets', skuId], queryFn: () => apiGet<WorksheetSummary[]>(`/api/v2/skus/${skuId}/worksheets`), enabled: !!skuId })

export function useCreateProduct() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (b: { site_id: string; name_zh: string; external_code?: string }) => apiPost<Product>('/api/v2/products', b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['products'] }) })
}
export function useUpdateProduct() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: ({ id, patch }: { id: string; patch: Record<string, unknown> }) => apiPatch<Product>(`/api/v2/products/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['products'] }) })
}
export function useCreateSku() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (b: { product_id: string; sku_code: string; name_zh?: string }) => apiPost<Sku>('/api/v2/skus', b),
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ['skus', v.product_id] }) })
}
export function useUpdateSku() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: ({ id, patch }: { id: string; patch: Record<string, unknown> }) => apiPatch<Sku>(`/api/v2/skus/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skus'] }) })
}
export function useCreateWorksheet() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ skuId, body }: { skuId: string; body: { model_label?: string; analyst?: string } }) =>
      apiPost<{ worksheet_id: string; version_no: string; status: string }>(`/api/v2/skus/${skuId}/worksheets`, body),
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ['sku-worksheets', v.skuId] }),
  })
}
