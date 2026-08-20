/**
 * i18n 覆核狀態 API hooks（ADR-032 D6）。
 *
 * | 端點 | 用途 |
 * |---|---|
 * | `GET  /api/v2/i18n/review/summary` | `{total, reviewed, pending}`（可選 entity_type 篩單一類別） |
 * | `GET  /api/v2/i18n/review/pending` | 待審清單（可篩 entity_type / status） |
 * | `POST /api/v2/i18n/review/mark-reviewed` | 標記已覆核；可帶 `target_en` 在同交易內修正譯文 |
 * | `POST /api/v2/i18n/review/assign` | 指派／取消指派（`assigned_to: null` ＝取消） |
 *
 * **本模組是這一頁唯一的寫入面，而且只准打上表這幾支端點**（e2e §I18N-07 掃原始碼
 * 守著：這一頁可達的每個模組，呼叫寫入 helper／裸 `fetch(` 的 URL 都必須落在白名單
 * 內；`I18nReviewTab.tsx` 一個寫入 helper 都不准提到，UI 只能透過這裡的 hooks 寫。
 * §I18N-06 是覆核操作本身，不是這道守衛）。理由是 ADR-032 D4／D6 把 `_en` 的可寫
 * 範圍收得很窄（欄位白名單 ＋ retired 擋 ＋ I5 唯一性 ＋ 反橡皮圖章的 422），這些
 * 保護全部長在那三支端點上；繞去別的寫入 API（例如 `PATCH /api/v2/vocab/{id}` 也寫
 * 得到 `name_en`）就整組繞過了。
 *
 * **沒有批次核准 hook，是刻意的**（ADR-032 R1／I5）：`g_grasp`(6 TMU)／`g_touch`(3 TMU)
 * 這類「英文看起來一樣」的誤譯只有逐條人看才擋得住。後端本來就沒有批次端點，前端
 * 也不得用迴圈自己拼一個出來。
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../shared/api/client'

export type I18nEntityType = 'rule_option' | 'vocab_item' | 'motion_template'
export type I18nPendingStatus = 'never_translated' | 'unreviewed' | 'stale'
/** `untranslated`：側表列只為記指派而存在、尚無譯文（v2_0043，見 ADR-032 D6）。 */
export type I18nReviewSource = 'machine' | 'human' | 'legacy_seed' | 'untranslated'
export type I18nField = 'label' | 'sentence' | 'name'

/**
 * `target_en` 的長度上限，依 `field` 而定——與後端 `schemas/v2/i18n.py` 的
 * `_MAX_TARGET_EN_BY_FIELD`（＝`rule_set_options.MAX_EN_LABEL_LEN`／
 * `MAX_EN_SENTENCE_LEN`）同一組數字。前端只拿來做 `maxLength` 與字數提示，
 * **權威仍在後端**（超長一律 422，不靠前端擋）。
 */
export const MAX_EN_LEN_BY_FIELD: Record<I18nField, number> = {
  label: 200,
  sentence: 500,
  name: 200,
}

export interface I18nReviewSummary {
  total: number
  reviewed: number
  pending: number
}

/** 一個可譯欄位的現況。`status === null` ＝已覆核且未過期（已離開待審清單）。 */
export interface I18nReviewItem {
  entity_type: I18nEntityType
  scope_key: string
  field: string
  status: I18nPendingStatus | null
  rule_set_code: string | null
  source_zh: string
  /**
   * `source_zh` 是回退來的、不是這一列自己的中文——只有 `field='sentence'` 且該列
   * 中文句面本身為空時為真（那時 `source_zh` 顯示的是標籤）。**英文句面能不能留空
   * 就看這個布林**（D7.6「刻意不入句」；後端 `_is_reviewable_target` 用同一個值），
   * 前端不得改用「`source_zh` 等於標籤」反推——句面剛好等於標籤時那會誤判。
   */
  source_is_fallback: boolean
  target_en: string | null
  /** S6：現行中文來源是否已與這筆翻譯依據的來源不同（見 ADR-032 D6 補記）。 */
  source_changed: boolean
  /** v2_0043：英文譯文在覆核之後被改過。與 `source_changed` 正交，兩者都會讓 status 變 stale。 */
  target_changed: boolean
  review_source: I18nReviewSource | null
  translated_by: string | null
  translated_at: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  assigned_to: string | null
  assigned_at: string | null
}

/** 待審清單的一列——`status` 必為三態之一（清單依定義只回 `status` 非空的列）。 */
export interface I18nPendingItem extends I18nReviewItem {
  status: I18nPendingStatus
}

export interface I18nPendingFilters {
  entity_type?: I18nEntityType
  status?: I18nPendingStatus
}

/**
 * 「指哪一列」。`rule_set_code` 只對 `rule_option` 有意義：同一個 `scope_key` 可能
 * 同時存在於 active 與多個 draft（D5 刻意讓 scope_key 不含 rule_set_id），後端未指定
 * 時以 active 版為準——所以清單回來的 `rule_set_code` 要原樣帶回去，不能省略，
 * 否則「畫面上看到的是 draft 那一列、覆核卻寫到 active」。
 */
export interface I18nReviewTargetRef {
  entity_type: I18nEntityType
  scope_key: string
  field: I18nField
  rule_set_code?: string | null
}

export interface I18nMarkReviewedInput extends I18nReviewTargetRef {
  /** `null` ＝不改譯文（沿用現有的 `_en`）。 */
  target_en?: string | null
  note?: string | null
}

export interface I18nAssignInput extends I18nReviewTargetRef {
  /** `null`／空白 ＝取消指派。 */
  assigned_to: string | null
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

/**
 * 覆核成功後，摘要（分子分母）與清單（這一列會消失）兩邊都變了——一律整組
 * invalidate。分母大（現況 201 列）但回應小，重抓一次的成本遠低於「畫面數字
 * 與 DB 不同步」的代價，D6 的驗收定義正是「數字可見且可下降」。
 */
function useInvalidateReviewQueries() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: [SUMMARY_QK] })
    void qc.invalidateQueries({ queryKey: [PENDING_QK] })
  }
}

/**
 * 標記已覆核（可同時修正譯文）。**逐條，沒有批次版本**（見檔頭）。
 *
 * `target_en` 的取值規則交給呼叫端（見 `I18nReviewTab.buildTargetEn`），這裡不做
 * 任何「猜使用者想不想改」的加工——後端對「沒有譯文的列不得標記已覆核」有 422
 * 守門（`I18N_REVIEW_TARGET_MISSING`），前端多猜一層只會讓兩邊的判準漂移。
 */
export function useMarkI18nReviewed() {
  const invalidate = useInvalidateReviewQueries()
  return useMutation({
    mutationFn: (input: I18nMarkReviewedInput) =>
      apiPost<I18nReviewItem>('/api/v2/i18n/review/mark-reviewed', input),
    onSuccess: invalidate,
  })
}

/** 指派／取消指派（`assigned_to: null` ＝取消）。指派不改變 `status`（ADR-032 D6）。 */
export function useAssignI18nReview() {
  const invalidate = useInvalidateReviewQueries()
  return useMutation({
    mutationFn: (input: I18nAssignInput) =>
      apiPost<I18nReviewItem>('/api/v2/i18n/review/assign', input),
    onSuccess: invalidate,
  })
}
