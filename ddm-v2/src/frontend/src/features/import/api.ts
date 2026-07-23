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

// ── ADR-025 D10：匯入預覽的逐行範本建議 ────────────────────────────────────────
// 每個「命中選項」（最佳命中與其候選共用同結構）。TMU 一律後端以 active 重算：
// computed_tmu === null 表後端取不到 active／範本算不出，error 帶原因——前端只渲染、絕不自算。
export interface MatchOption {
  template_id: string
  template_name_zh: string
  seq_kind: string
  score: number
  matched_keywords: string[]
  computed_tmu: number | null
  computed_seconds: number | null
  error: string | null
}
export interface RowMatch extends MatchOption {
  candidates: MatchOption[]   // 其餘命中範本，供 IE 換選
}
// 正規化列＝任意欄位 ＋ match（完全無命中為 null）
export type PreviewRow = Record<string, unknown> & { match?: RowMatch | null }
export interface PreviewOut { import_id: string; fields: string[]; rows: PreviewRow[]; n: number; warnings: string[] }
export interface ProfileIn { name: string; sheet_hint?: string | null; header_row?: number | null; column_map: Record<string, number>; time_unit: string }

export const useUploadImport = () =>
  useMutation({ mutationFn: (file: File) => { const f = new FormData(); f.append('file', file); return apiUpload<UploadOut>('/api/v2/imports/upload', f) } })

export const useMapColumns = () =>
  useMutation({ mutationFn: ({ importId, body }: { importId: string; body: MapIn }) => apiPost<PreviewOut>(`/api/v2/imports/${importId}/map`, body) })

export const useCreateProfile = () =>
  useMutation({ mutationFn: (body: ProfileIn) => apiPost<ProfileOut>('/api/v2/imports/profiles', body) })

// ADR-025 D10：採用某暫存列的範本建議。**只送 template_id**（TMU 一律後端以 active 重算，
// 前端傳 TMU 會被忽略）。row_index ＝暫存列在預覽中的順序索引。
export interface RowAdoption { row_index: number; template_id: string }
export interface SubmitIn {
  worksheet_id: string
  rule_set_code?: string | null
  row_adoptions?: RowAdoption[]
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
