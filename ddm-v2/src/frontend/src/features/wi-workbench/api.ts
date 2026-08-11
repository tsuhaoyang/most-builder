import { useQuery, useMutation } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut } from '../../shared/api/client'
import type { ABand } from './cycle'
import type { NlDraftResponse, ReviewBatchIn, ReviewBatchOut } from './aiTypes'

export type { NlDraftResponse, ReviewBatchIn, ReviewBatchOut }

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

// code 必填且無預設（ADR-023 §3.5）：預設值會讓 UI 在 active 未載入時靜默用錯版本計算。
// 呼叫端請傳 `useActiveRuleSetCode()`；未載入時為 undefined → query 停用。
export const useRuleSetOptions = (code: string | undefined) =>
  useQuery({
    queryKey: ['ruleopts', code],
    queryFn: () => apiGet<RuleSetOptions>(`/api/v2/rule-sets/${code}/options`),
    enabled: !!code,
  })

export const useVocab = () =>
  useQuery({ queryKey: ['vocab'], queryFn: () => apiGet<Vocab[]>('/api/v2/vocab') })

export const useTemplates = () =>
  useQuery({ queryKey: ['templates'], queryFn: () => apiGet<Template[]>('/api/v2/motion-templates') })

// 後端權威計算：前端不自算 TMU
export const useCalculate = () =>
  useMutation({ mutationFn: (cycle: unknown) => apiPost<CalcResult>('/api/v2/minimost/calculate', cycle) })

export interface SaveResult {
  worksheet_id: string
  status: string
  total_tmu: number
  rows: unknown[]
  revision_no?: number
  content_hash?: string | null
}
export const useSaveWorksheet = (wsId: string) =>
  useMutation({ mutationFn: (body: unknown) => apiPut<SaveResult>(`/api/v2/worksheets/${wsId}`, body) })

// 讀回整份 worksheet（切換版本 / 開啟時載入；後端權威）
export interface WsReadRow {
  wi_row_id: string
  seq_no: number
  hand: string | null
  sub_activity: string | null
  object_vocab_id: string | null
  from_vocab_id: string | null
  to_vocab_id: string | null
  tool_vocab_id: string | null
  frequency: number
  simo_group_id: string | null
  /** F-03b §2 provenance — nullable 軟參考（非 FK） */
  source_module_id: string | null
  source_module_version: number | null
  cycle: {
    seq_kind: string
    total_tmu: number
    total_seconds: number
    narrative: string | null
    /** 原始 CycleIn JSON（後端權威）— apply-back 時整包回傳 */
    slot_inputs: unknown
    /** 計算時使用的 rule-set UUID（apply-back 回傳給後端） */
    rule_set_id: string
  } | null
  level: {
    coefficient: number
    ascription: string | null
    level: string | null
    countersignature: string | null
    parent_countersignature: string | null
    number: string | null
    number_count: number | null
  } | null
}
/**
 * ADR-023 §3.4-4：工序表建立時凍結的 default rule-set 快照的**現況**狀態。
 * 純顯示層——供警示徽章判斷「本工序表是否基於已下架版本」；不進計算路徑
 * （回放仍由各列 cycle.rule_set_id 決定）。default_rule_set_id 為 NULL → 整欄 null。
 */
export interface DefaultRuleSetInfo { code: string; status: 'draft' | 'published' | 'retired'; is_active: boolean }
export interface WsRead {
  worksheet_id: string
  status: string
  total_tmu: number
  rows: WsReadRow[]
  default_rule_set: DefaultRuleSetInfo | null
  revision_no?: number
  content_hash?: string | null
}
export const useWorksheet = (wsId: string) =>
  useQuery({ queryKey: ['worksheet', wsId], queryFn: () => apiGet<WsRead>(`/api/v2/worksheets/${wsId}`), refetchOnWindowFocus: false, enabled: !!wsId })

// ── WI AI（L3）────────────────────────────────────────────────────────────────
export const useNlDraft = () =>
  useMutation({
    mutationFn: (body: {
      text: string
      rule_set_code: string
      worksheet_id?: string | null
      context?: {
        station_hint?: string | null
        available_tools?: string[]
        available_locations?: string[]
      }
    }) => apiPost<NlDraftResponse>('/api/v2/worksheets/nl-draft', body),
  })

export const usePostReviews = () =>
  useMutation({
    mutationFn: ({ runId, body }: { runId: string; body: ReviewBatchIn }) =>
      apiPost<ReviewBatchOut>(`/api/v2/nl-drafts/${runId}/reviews`, body),
  })
