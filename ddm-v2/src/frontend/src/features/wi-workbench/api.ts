import { useQuery, useMutation } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut } from '../../shared/api/client'
import type { ABand } from './cycle'

export interface RuleOption { code: string; label: string; label_en?: string }
export interface GOption extends RuleOption { modifier_key: string | null; requires_modifier: boolean }
export interface PAddon extends RuleOption { needs_precision: boolean }
export interface MVerb extends RuleOption { pricing_kind: string }
export interface XOption extends RuleOption { mode: string }
export interface RuleSetOptions {
  code: string; multiplier: number
  a_bands: { reach: ABand[]; twist: ABand[]; foot: ABand[] }
  b: RuleOption[]; g: GOption[]; p_bases: RuleOption[]; p_addons: PAddon[]
  m_verbs: MVerb[]; x: XOption[]; i: RuleOption[]
}
export interface Vocab { id: string; kind: string; name_zh: string }
export interface Template { id: string; name_zh: string; seq_kind: string; cycle_template: unknown; status: string }
export interface CalcResult { seq: string; total_tmu: number; total_seconds: number; tech_line: string }

export const useRuleSetOptions = (code = 'MINIMOST_FACTORY_V1') =>
  useQuery({ queryKey: ['ruleopts', code], queryFn: () => apiGet<RuleSetOptions>(`/api/v2/rule-sets/${code}/options`) })

export const useVocab = () =>
  useQuery({ queryKey: ['vocab'], queryFn: () => apiGet<Vocab[]>('/api/v2/vocab') })

export const useTemplates = () =>
  useQuery({ queryKey: ['templates'], queryFn: () => apiGet<Template[]>('/api/v2/motion-templates') })

// 後端權威計算：前端不自算 TMU
export const useCalculate = () =>
  useMutation({ mutationFn: (cycle: unknown) => apiPost<CalcResult>('/api/v2/minimost/calculate', cycle) })

export interface SaveResult { worksheet_id: string; status: string; total_tmu: number; rows: unknown[] }
export const useSaveWorksheet = (wsId: string) =>
  useMutation({ mutationFn: (body: unknown) => apiPut<SaveResult>(`/api/v2/worksheets/${wsId}`, body) })
