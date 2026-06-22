import { useQuery, useMutation } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../shared/api/client'

export interface VersionRow {
  version_no: string
  status: string
  worksheet_id: string | null
  is_current: boolean
}
export interface VersionInfo {
  worksheet_id: string
  version_no: string
  status: string
  sku_id: string
  versions: VersionRow[]
}
export interface CloneResult { new_worksheet_id: string; version_no: string; status: string; source_version_no: string }

export const useVersions = (wsId: string) =>
  useQuery({ queryKey: ['versions', wsId], queryFn: () => apiGet<VersionInfo>(`/api/v2/worksheets/${wsId}/versions`) })

export const usePublish = (wsId: string) =>
  useMutation({ mutationFn: () => apiPost<VersionInfo>(`/api/v2/worksheets/${wsId}/publish`) })

export const useClone = (wsId: string) =>
  useMutation({ mutationFn: () => apiPost<CloneResult>(`/api/v2/worksheets/${wsId}/clone`) })
