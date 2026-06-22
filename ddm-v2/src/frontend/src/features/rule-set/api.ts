import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../shared/api/client'

export interface RuleSetSummary { code: string; name_zh: string; status: string; multiplier: number }

// 各規則表為 record 陣列；以泛型表格渲染（唯讀檢視）
export interface RuleSetFull {
  code: string; name_zh: string; status: string; multiplier: number
  a_bands: Record<string, unknown>[]
  b: Record<string, unknown>[]
  g: Record<string, unknown>[]
  p_bases: Record<string, unknown>[]
  p_addons: Record<string, unknown>[]
  m_ladder: Record<string, unknown>[]
  m_verbs: Record<string, unknown>[]
  m_rotation: Record<string, unknown>[]
  m_hand: Record<string, unknown>[]
  x: Record<string, unknown>[]
  i: Record<string, unknown>[]
}

export const useRuleSetList = () =>
  useQuery({ queryKey: ['rule-sets'], queryFn: () => apiGet<RuleSetSummary[]>('/api/v2/rule-sets') })

export const useRuleSetFull = (code: string) =>
  useQuery({ queryKey: ['rule-set-full', code], queryFn: () => apiGet<RuleSetFull>(`/api/v2/rule-sets/${code}/full`), enabled: !!code })
