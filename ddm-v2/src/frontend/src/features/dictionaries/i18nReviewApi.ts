/**
 * i18n 覆核狀態 API hooks（ADR-032 D6）。
 * - GET /api/v2/i18n/review/summary → `{total, reviewed, pending}`（可選 entity_type 篩單一類別）
 * - GET /api/v2/i18n/review/pending → 待審清單（可篩 entity_type / status）
 *
 * 本輪唯讀（ADR-032 D6 附記：後端只交付了 GET 兩支端點，沒有標記完成的 mutation
 * 端點）——這裡刻意不提供任何 usePatch/useMutation，避免前端做出一個按了沒反應
 * 或呼叫不存在端點的 UI。
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiGet } from '../../shared/api/client'

export type I18nEntityType = 'rule_option' | 'vocab_item' | 'motion_template'
export type I18nPendingStatus = 'never_translated' | 'unreviewed' | 'stale'
export type I18nReviewSource = 'machine' | 'human' | 'legacy_seed'

export interface I18nReviewSummary {
  total: number
  reviewed: number
  pending: number
}

export interface I18nPendingItem {
  entity_type: I18nEntityType
  scope_key: string
  field: string
  status: I18nPendingStatus
  rule_set_code: string | null
  source_zh: string
  target_en: string | null
  /** S6：現行中文來源是否已與這筆翻譯依據的來源不同（見 ADR-032 D6 補記）。 */
  source_changed: boolean
  review_source: I18nReviewSource | null
  translated_by: string | null
  translated_at: string | null
  reviewed_by: string | null
  reviewed_at: string | null
}

export interface I18nPendingFilters {
  entity_type?: I18nEntityType
  status?: I18nPendingStatus
}

const SUMMARY_QK = 'i18n-review-summary' as const
const PENDING_QK = 'i18n-review-pending' as const

export function useI18nReviewSummary(entityType?: I18nEntityType) {
  const qs = entityType ? `?entity_type=${entityType}` : ''
  return useQuery({
    queryKey: [SUMMARY_QK, entityType ?? 'all'],
    queryFn: () => apiGet<I18nReviewSummary>(`/api/v2/i18n/review/summary${qs}`),
  })
}

export function useI18nReviewPending(filters?: I18nPendingFilters) {
  const params = new URLSearchParams()
  if (filters?.entity_type) params.append('entity_type', filters.entity_type)
  if (filters?.status) params.append('status', filters.status)
  const qs = params.toString()
  return useQuery({
    queryKey: [PENDING_QK, filters ?? {}],
    queryFn: () => apiGet<I18nPendingItem[]>(`/api/v2/i18n/review/pending${qs ? '?' + qs : ''}`),
    // S3：切換 entity_type／status 篩選時保留舊資料，避免整個表格區被 loading 取代
    // （工具列／篩選器／摘要卡片本來就恆存，不受這裡影響——見 I18nReviewTab）。
    placeholderData: keepPreviousData,
  })
}
