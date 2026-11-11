import { useQuery, useMutation } from '@tanstack/react-query'
import { apiGet, apiPost, apiPatch } from '../../shared/api/client'

export interface AppUser {
  employee_no: string
  external_user_id: string | null
  display_name: string | null
  roles: string[]            // admin/manager/IE（空=viewer）
  site_ids: string[]
  is_active: boolean
}
export interface UpsertIn { employee_no: string; display_name?: string; roles: string[] }
export interface PatchIn { roles?: string[]; is_active?: boolean; display_name?: string }

export const useUsers = () =>
  useQuery({ queryKey: ['admin-users'], queryFn: () => apiGet<AppUser[]>('/api/v2/admin/users') })

export const useUpsertUser = () =>
  useMutation({ mutationFn: (body: UpsertIn) => apiPost<AppUser>('/api/v2/admin/users', body) })

export const usePatchUser = () =>
  useMutation({ mutationFn: ({ employee_no, body }: { employee_no: string; body: PatchIn }) =>
    apiPatch<AppUser>(`/api/v2/admin/users/${employee_no}`, body) })
