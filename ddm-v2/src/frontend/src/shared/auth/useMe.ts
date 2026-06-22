import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../api/client'

export interface Me { employee_no: string; roles: string[]; plant_code?: string | null; level: number }

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: () => apiGet<Me>('/api/v2/me') })
}

// RBAC gating（UI 層；安全仍由後端 require_role 保證）
export const canEdit = (m?: Me) => (m?.level ?? 0) >= 1
export const canPublish = (m?: Me) => (m?.level ?? 0) >= 2
export const isAdmin = (m?: Me) => (m?.level ?? 0) >= 3
