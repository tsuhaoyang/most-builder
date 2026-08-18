import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { SupportedLocale } from '../i18n/i18n'
import { apiGet, apiPatch } from '../api/client'

// `locale` 已由後端解析（NULL→系統預設），前端不需要自己做 fallback（ADR-032 D3.1）。
export interface Me { employee_no: string; roles: string[]; plant_code?: string | null; level: number; locale: SupportedLocale }

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: () => apiGet<Me>('/api/v2/me') })
}

/** 本人自助改語言偏好（ADR-032 D3.1：PATCH /me/locale，無需 admin）。 */
export function useUpdateMyLocale() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (locale: SupportedLocale) => apiPatch<Me>('/api/v2/me/locale', { locale }),
    onSuccess: (me) => qc.setQueryData(['me'], me),
  })
}

// RBAC gating（UI 層；安全仍由後端 require_role 保證）
export const canEdit = (m?: Me) => (m?.level ?? 0) >= 1
export const canPublish = (m?: Me) => (m?.level ?? 0) >= 2
export const isAdmin = (m?: Me) => (m?.level ?? 0) >= 3
