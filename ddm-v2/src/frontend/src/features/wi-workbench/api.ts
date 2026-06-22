import { useQuery, useMutation } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../shared/api/client'

export interface RuleOption { code: string; label: string }
export interface Vocab { id: string; kind: string; name_zh: string }
export interface Template { id: string; name_zh: string; seq_kind: string; cycle_template: unknown; status: string }
export interface CalcResult { seq: string; total_tmu: number; total_seconds: number; tech_line: string }

export const useVocab = () =>
  useQuery({ queryKey: ['vocab'], queryFn: () => apiGet<Vocab[]>('/api/v2/vocab') })

export const useTemplates = () =>
  useQuery({ queryKey: ['templates'], queryFn: () => apiGet<Template[]>('/api/v2/motion-templates') })

// 後端權威計算：前端不自算 TMU
export const useCalculate = () =>
  useMutation({ mutationFn: (cycle: unknown) => apiPost<CalcResult>('/api/v2/minimost/calculate', cycle) })
