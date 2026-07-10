import { useMutation } from '@tanstack/react-query'
import { apiPost, apiUpload } from '../../shared/api/client'

export interface SheetPreview { name: string; grid: unknown[][]; n_rows: number; n_cols: number }
export interface ProfileOut {
  id: string; name: string; sheet_hint: string | null; header_row: number | null
  column_map: Record<string, number>; time_unit: string | null; owner: string | null
}
export interface UploadOut {
  import_id: string; source_name: string | null
  target_fields: string[]; required_fields: string[]
  sheets: SheetPreview[]; suggested_sheet: string | null; suggested_header_row: number | null
  profiles: ProfileOut[]
}
export interface MapIn { sheet: string; header_row: number; column_map: Record<string, number>; time_unit: string }
export interface PreviewOut { import_id: string; fields: string[]; rows: Record<string, unknown>[]; n: number; warnings: string[] }
export interface ProfileIn { name: string; sheet_hint?: string | null; header_row?: number | null; column_map: Record<string, number>; time_unit: string }

export const useUploadImport = () =>
  useMutation({ mutationFn: (file: File) => { const f = new FormData(); f.append('file', file); return apiUpload<UploadOut>('/api/v2/imports/upload', f) } })

export const useMapColumns = () =>
  useMutation({ mutationFn: ({ importId, body }: { importId: string; body: MapIn }) => apiPost<PreviewOut>(`/api/v2/imports/${importId}/map`, body) })

export const useCreateProfile = () =>
  useMutation({ mutationFn: (body: ProfileIn) => apiPost<ProfileOut>('/api/v2/imports/profiles', body) })

export interface SubmitIn {
  worksheet_id: string
  rule_set_code?: string | null
}
export interface SubmitOut {
  worksheet_id: string
  n_rows: number
  n_with_analysis: number
  n_need_review: number
  warnings: string[]
}

export const useSubmitImport = () =>
  useMutation({
    mutationFn: ({ importId, body }: { importId: string; body: SubmitIn }) =>
      apiPost<SubmitOut>(`/api/v2/imports/${importId}/submit`, body),
  })
