/**
 * WI AI 回應型別（對齊後端 ParseRunResult / nl-draft 加法欄位）。
 *
 * D3：OpenAPI 目前將 nl-draft 200 標成任意物件；正式 gen:api 補 schema 前
 * 以此檔為前端契約，欄位與 `nlp/contracts.py` 對齊。
 */
export type RoutingStatus = 'auto' | 'review' | 'abstain' | 'invalid'

export interface AiCycleDraft {
  action_id: string
  cycle: Record<string, unknown> | null
  complete: boolean
  engine_result: {
    total_tmu: number
    total_seconds: number
    tech_line: string
    breakdown?: { letter: string; tmu: number }[]
  } | null
  narrative: string | null
  issues: string[]
}

export interface AiPlannedAction {
  action_id: string
  action_type: string
  sequence_order: number
  roles: Record<string, { text?: string | null; value?: number | null; status?: string }>
  notes?: string | null
}

export interface AiParseBlock {
  run_id: string
  plan: {
    schema_version: string
    source_text: string
    normalized_text: string
    actions: AiPlannedAction[]
    unresolved: string[]
  }
  slot_candidates: unknown[]
  drafts: AiCycleDraft[]
  routing_status: RoutingStatus
  routing_reasons: string[]
  provenance: {
    planner?: string
    fallback?: boolean
    cached?: boolean
    model?: string | null
    [k: string]: unknown
  }
}

export interface NlDraftLegacySlot {
  slot_index: number
  field: string
  chosen: { option_code: string; score: number; source: string } | null
  needs_review?: boolean
}

/** POST /api/v2/worksheets/nl-draft 完整回應（legacy + ai） */
export interface NlDraftResponse {
  raw_text?: string
  normalized_text?: string
  suggested_seq?: string | null
  slots?: NlDraftLegacySlot[]
  overall_confidence?: number
  provenance?: Record<string, unknown>
  ai?: AiParseBlock
  multi_action_warning?: boolean
}

export interface ReviewEventIn {
  event_type:
    | 'accept_plan'
    | 'split_action'
    | 'merge_actions'
    | 'reorder_action'
    | 'add_action'
    | 'delete_action'
    | 'replace_role'
    | 'replace_candidate'
    | 'change_sequence_model'
    | 'change_quantity_policy'
    | 'mark_missing'
    | 'accept_all'
  target?: Record<string, unknown> | null
  before?: Record<string, unknown> | null
  after?: Record<string, unknown> | null
  reason?: string | null
}

export interface ReviewBatchIn {
  events: ReviewEventIn[]
  ui_version?: string | null
}

export interface ReviewBatchOut {
  run_id: string
  event_ids: string[]
  candidate_ids: string[]
}
