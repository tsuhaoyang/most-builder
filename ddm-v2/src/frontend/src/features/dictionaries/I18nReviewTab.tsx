/**
 * I18nReviewTab — ADR-032 D6 待審清單（Phase B 前端半部）。
 *
 * 唯讀：後端本輪只交付 GET /api/v2/i18n/review/summary 與 /pending 兩支端點，
 * 沒有標記完成的 mutation 端點——本元件刻意不做「標記已覆核」按鈕，
 * 也不做英文譯文編輯（那是 rule_set 既有 `label_en` 編輯欄／paramSchema.ts 的事）。
 * 「複製」只是方便貼去 Excel 給人工翻譯的小工具，不代表任何覆核狀態變更。
 *
 * 驗收核心（D6）：摘要區要讓「覆核進度是可見且可下降的數字」。
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useI18nReviewPending,
  useI18nReviewSummary,
  type I18nEntityType,
  type I18nPendingItem,
  type I18nPendingStatus,
  type I18nReviewSummary,
} from './i18nReviewApi'

const ENTITY_TYPES: I18nEntityType[] = ['rule_option', 'vocab_item', 'motion_template']
const STATUSES: I18nPendingStatus[] = ['never_translated', 'unreviewed', 'stale']

const STATUS_BADGE_CLASS: Record<I18nPendingStatus, string> = {
  never_translated: 'bg-slate-200 text-slate-700',
  unreviewed: 'bg-amber-100 text-amber-800',
  stale: 'bg-red-100 text-red-800',
}

/**
 * `navigator.clipboard` 可能因權限／非安全情境（非 HTTPS，MDN 明文：Clipboard API
 * 僅限 secure context）整個不存在——先探測，不存在或寫入失敗都落到隱藏
 * textarea + `execCommand('copy')` 的舊式 fallback，兩者都失敗才回 false。
 * S5：呼叫端必須把 false 顯示給使用者看，不能悄悄吞掉。
 */
async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 掉到下面的 fallback 再試一次，不直接放棄
    }
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.top = '-1000px'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

function SummaryCard({
  label, summary, error, testId,
}: { label: string; summary?: I18nReviewSummary; error?: unknown; testId: string }) {
  const { t } = useTranslation()
  return (
    <div className="bg-white rounded-lg border px-3 py-2" data-testid={testId}>
      <div className="text-xs text-slate-500">{label}</div>
      {error ? (
        <div className="text-xs font-medium text-red-600" data-testid={`${testId}-error`}>
          {t('i18nReview.loadError', { message: (error as Error).message })}
        </div>
      ) : (
        <div className="text-lg font-semibold text-slate-800">
          {summary ? t('i18nReview.summary.progress', { reviewed: summary.reviewed, total: summary.total }) : '—'}
        </div>
      )}
    </div>
  )
}

export function I18nReviewTab() {
  const { t } = useTranslation()

  const [entityFilter, setEntityFilter] = useState<I18nEntityType | ''>('')
  const [statusFilter, setStatusFilter] = useState<I18nPendingStatus | ''>('')
  const [rawQ, setRawQ] = useState('')

  // 整體 + 依 entity_type 分開顯示（D6：「覆核進度是可見且可下降的數字」）。
  // S4：每一個 query 的 error 都要接住，不能讓「失敗」跟「載入中」一樣顯示 '—'。
  const { data: overall, error: overallError } = useI18nReviewSummary()
  const { data: byRuleOption, error: byRuleOptionError } = useI18nReviewSummary('rule_option')
  const { data: byVocab, error: byVocabError } = useI18nReviewSummary('vocab_item')
  const { data: byTemplate, error: byTemplateError } = useI18nReviewSummary('motion_template')

  // S3：`placeholderData: keepPreviousData`（見 i18nReviewApi.ts）讓切換篩選時
  // `isLoading` 只在真正的初次載入為 true；`isFetching` 用來給表格區一個輕量的
  // 「更新中」提示，不影響工具列／摘要卡片（下面 render 時兩者都恆存）。
  const { data: items = [], isLoading, isFetching, error } = useI18nReviewPending({
    entity_type: entityFilter || undefined,
    status: statusFilter || undefined,
  })

  const filteredItems = useMemo(() => {
    if (!rawQ.trim()) return items
    const q = rawQ.trim().toLowerCase()
    return items.filter(i =>
      i.source_zh.toLowerCase().includes(q) || (i.target_en ?? '').toLowerCase().includes(q),
    )
  }, [items, rawQ])

  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [copiedAll, setCopiedAll] = useState(false)
  // S5：複製失敗（非 HTTPS context、`execCommand` fallback 也失敗）要有明確回饋，
  // 不能靜默無反應——不論失敗的是單列還是整批複製，都用同一顆訊息位。
  const [copyError, setCopyError] = useState(false)

  const handleCopyRow = async (item: I18nPendingItem) => {
    const key = `${item.entity_type}:${item.scope_key}:${item.field}`
    const ok = await copyText(`${item.source_zh}\t${item.target_en ?? ''}`)
    if (ok) {
      setCopiedKey(key)
      setCopyError(false)
      setTimeout(() => setCopiedKey(k => (k === key ? null : k)), 1500)
    } else {
      setCopyError(true)
      setTimeout(() => setCopyError(false), 3000)
    }
  }

  const handleCopyAll = async () => {
    const tsv = filteredItems.map(i => `${i.source_zh}\t${i.target_en ?? ''}`).join('\n')
    const ok = await copyText(tsv)
    if (ok) {
      setCopiedAll(true)
      setCopyError(false)
      setTimeout(() => setCopiedAll(false), 1500)
    } else {
      setCopyError(true)
      setTimeout(() => setCopyError(false), 3000)
    }
  }

  return (
    <div className="space-y-3" data-testid="i18n-review-tab">
      <div className="text-xs text-slate-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
        {t('i18nReview.note')}
      </div>

      {/* Summary — D6 驗收核心：覆核進度是可見且可下降的數字。
          S3：這一區與下面的工具列恆存，不隨表格區的載入／錯誤狀態被卸載。 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="i18n-review-summary">
        <SummaryCard label={t('i18nReview.summary.overall')} summary={overall} error={overallError} testId="i18n-summary-overall" />
        <SummaryCard label={t('i18nReview.entityType.rule_option')} summary={byRuleOption} error={byRuleOptionError} testId="i18n-summary-rule_option" />
        <SummaryCard label={t('i18nReview.entityType.vocab_item')} summary={byVocab} error={byVocabError} testId="i18n-summary-vocab_item" />
        <SummaryCard label={t('i18nReview.entityType.motion_template')} summary={byTemplate} error={byTemplateError} testId="i18n-summary-motion_template" />
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="border rounded px-2 py-1 text-sm w-56"
          placeholder={t('i18nReview.filters.searchPlaceholder')}
          value={rawQ}
          onChange={e => setRawQ(e.target.value)}
        />
        <select
          className="border rounded px-2 py-1 text-sm"
          value={entityFilter}
          onChange={e => setEntityFilter(e.target.value as I18nEntityType | '')}
          aria-label={t('i18nReview.filters.entityTypeLabel')}
        >
          <option value="">{t('i18nReview.filters.allEntityTypes')}</option>
          {ENTITY_TYPES.map(et => (
            <option key={et} value={et}>{t(`i18nReview.entityType.${et}`)}</option>
          ))}
        </select>
        <select
          className="border rounded px-2 py-1 text-sm"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as I18nPendingStatus | '')}
          aria-label={t('i18nReview.filters.statusLabel')}
        >
          <option value="">{t('i18nReview.filters.allStatuses')}</option>
          {STATUSES.map(s => (
            <option key={s} value={s}>{t(`i18nReview.status.${s}`)}</option>
          ))}
        </select>
        <button
          className="ml-auto px-3 py-1.5 border rounded text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          disabled={filteredItems.length === 0}
          onClick={handleCopyAll}
        >
          {copiedAll ? t('i18nReview.table.copyAllDone', { n: filteredItems.length }) : t('i18nReview.table.copyAll')}
        </button>
        {copyError && (
          <span className="text-xs text-red-600" data-testid="i18n-copy-error">{t('i18nReview.table.copyFailed')}</span>
        )}
      </div>

      {/* Table — S3：只有這一區受載入／錯誤狀態影響，工具列／摘要卡片在它上面恆存。 */}
      {isLoading ? (
        <div className="p-4 text-slate-500 text-sm" data-testid="i18n-review-table-loading">{t('i18nReview.loading')}</div>
      ) : error ? (
        <div className="p-4 text-red-600 text-sm" data-testid="i18n-review-table-error">
          {t('i18nReview.loadError', { message: (error as Error).message })}
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto" style={{ opacity: isFetching ? 0.6 : 1 }}>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2">{t('i18nReview.table.entityType')}</th>
              <th className="px-3 py-2">{t('i18nReview.table.sourceZh')}</th>
              <th className="px-3 py-2">{t('i18nReview.table.targetEn')}</th>
              <th className="px-3 py-2">{t('i18nReview.table.status')}</th>
              <th className="px-3 py-2">{t('i18nReview.table.source')}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {filteredItems.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-400">
                  {t('i18nReview.table.empty')}
                </td>
              </tr>
            )}
            {filteredItems.map(item => {
              const key = `${item.entity_type}:${item.scope_key}:${item.field}`
              return (
                <tr key={key} className="border-t align-top" data-testid={`i18n-row-${key}`}>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-700">
                      {t(`i18nReview.entityType.${item.entity_type}`)}
                    </span>
                    {item.rule_set_code && (
                      <div className="text-[11px] text-slate-400 mt-0.5">{item.rule_set_code}</div>
                    )}
                  </td>
                  <td className="px-3 py-2">{item.source_zh}</td>
                  <td className="px-3 py-2">
                    {item.target_en ?? <span className="text-slate-400">{t('i18nReview.table.untranslated')}</span>}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-1 items-start">
                      <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${STATUS_BADGE_CLASS[item.status]}`}>
                        {t(`i18nReview.status.${item.status}`)}
                      </span>
                      {/* source_changed：獨立正交維度，不併進 status（D6 補記）——
                          單獨一個醒目徽章，語意上比單純 unreviewed 更急。 */}
                      {item.source_changed && (
                        <span
                          className="px-1.5 py-0.5 rounded text-xs font-medium bg-red-600 text-white"
                          data-testid="i18n-source-changed-badge"
                          title={t('i18nReview.table.sourceChangedHint')}
                        >
                          {t('i18nReview.table.sourceChangedBadge')}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-slate-500">
                    {item.review_source ? t(`i18nReview.reviewSource.${item.review_source}`) : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      className="px-2 py-0.5 rounded text-xs border text-slate-600 hover:bg-slate-50"
                      onClick={() => handleCopyRow(item)}
                    >
                      {copiedKey === key ? t('i18nReview.table.copyRowDone') : t('i18nReview.table.copyRow')}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}
