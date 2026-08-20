/**
 * I18nReviewTab — ADR-032 D6 待審清單 ＋ 覆核操作。
 *
 * D6 的驗收定義是「**覆核進度是可見且可下降的數字**」——本輪把「可下降」接上：
 * 逐條標記已覆核（可在同一個請求裡修正譯文）、指派／取消指派。
 *
 * 三個刻意的形狀（每一個都對應 ADR 的一句話，不是 UI 偏好）：
 *
 * 1. **沒有批次核准**（R1／I5）：沒有全選 checkbox、沒有「全部標記已覆核」。
 *    `g_grasp`(6 TMU)／`g_touch`(3 TMU) 這種「英文看起來一樣」的誤譯只有逐條人看
 *    才擋得住；一次核准 126 列會把覆核變成橡皮圖章，而「每條譯文都有人負責」正是
 *    D2（機器翻譯先全灌）賴以成立的第三個前提。
 * 2. **寫入入口只給 analyst+**（D4／D6：`_en` 編輯權＝analyst 以上）。本頁本身已由
 *    側欄 `minRole:'analyst'` gating，但寫入入口另外用 `canEdit(me)` 再擋一層——
 *    側欄 gating 擋的是「進得來嗎」，這裡擋的是「看得到寫入嗎」，兩者失效模式不同
 *    （e2e §I18N-05-2 直接把 viewer 送進這一頁驗證）。
 * 3. **`source_changed`／`target_changed` 分開顯示**：兩者都會讓 `status` 變 `stale`，
 *    但「中文改了、譯文要跟上」與「有人動了譯文、要重新確認」對覆核者是兩件事
 *    （D6：不引入第四個 status 值，改用兩個正交布林）。
 *
 * **英文譯文留空的判準跟著資料走，不靠前端猜**：`field='sentence'` 且**該列中文句面
 * 本身為空**時，空字串是合法的（D7.6「刻意不入句」，active 版共 7 條）；中文句面有字
 * 時空字串＝沒翻譯，後端 422。分辨兩者的布林是 `source_is_fallback`，`/pending` 會回
 * （2026-08-20 補上；後端 `_is_reviewable_target` 判的是同一個值）——所以本頁直接用它
 * 決定「這一列的空字串是刻意不入句還是漏翻」，**不硬刻 7 條 code 清單、也不用
 * 『`source_zh` 等於標籤』反推**（句面剛好等於標籤時那會誤判）。被 422 擋下時仍原樣
 * 顯示後端訊息：權威在後端，這裡只是把它前移到按鈕上，讓人不必撞了才知道。
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../../shared/api/client'
import { canEdit, useMe } from '../../shared/auth/useMe'
import {
  MAX_EN_LEN_BY_FIELD,
  useAssignI18nReview,
  useI18nReviewPending,
  useI18nReviewSummary,
  useMarkI18nReviewed,
  type I18nEntityType,
  type I18nField,
  type I18nPendingItem,
  type I18nPendingStatus,
  type I18nReviewSummary,
} from './i18nReviewApi'

/** 表頭欄數——編輯器那一列的 `colSpan` 與空清單那一列的 `colSpan` 都讀這裡（同一個數字只寫一份）。 */
const COL_COUNT = 7

const ENTITY_TYPES: I18nEntityType[] = ['rule_option', 'vocab_item', 'motion_template']
const STATUSES: I18nPendingStatus[] = ['never_translated', 'unreviewed', 'stale']

const STATUS_BADGE_CLASS: Record<I18nPendingStatus, string> = {
  never_translated: 'bg-slate-200 text-slate-700',
  unreviewed: 'bg-amber-100 text-amber-800',
  stale: 'bg-red-100 text-red-800',
}

/** 一列的穩定鍵——與後端的 UNIQUE (entity_type, scope_key, field) 同一組欄位。 */
function rowKey(item: Pick<I18nPendingItem, 'entity_type' | 'scope_key' | 'field'>): string {
  return `${item.entity_type}:${item.scope_key}:${item.field}`
}

/**
 * 送去 `mark-reviewed` 的 `target_en`。
 *
 * **一律先 `.trim()` 再比對、再送出**：後端 `I18nMarkReviewedIn.target_en` 是
 * `StringConstraints(strip_whitespace=True)`，`"grasp "` 到了那邊就是 `"grasp"`。
 * 不 trim 就比對，會把「使用者多打一個尾空白」判成「有改」送出去，稽核紀錄留下
 * `{before:"grasp", after:"grasp"}`——正是下面「沒改送 null」要避免的那種噪音，
 * 只是被空白繞過。停用判斷（`blank`）也用 `.trim()`，兩處判準一致。
 *
 * - 有改 → 送新字串（已 trim）。
 * - 沒改 → 送 `null`（＝沿用現有 `_en`；後端會拿現有值去過反橡皮圖章那道檢查）。
 * - **例外：句面且使用者把欄位清空 → 一律顯式送 `''`**。因為 `null` 對一列
 *   `sentence_text_en IS NULL` 的句面代表「沿用那個 null」→ 必然 422，
 *   D7.6「刻意不入句」就永遠表達不出來。空字串才是那個有意義的值。
 */
export function buildTargetEn(item: I18nPendingItem, edited: string): string | null {
  // 比對用的原值刻意**不** trim：DB 裡若還留著舊入口寫進去的空白（那條路徑當時是裸
  // setattr），使用者不動它也應該被順手修正成 trim 後的值，而不是永遠比不相等。
  const original = item.target_en ?? ''
  const next = edited.trim()
  if (next !== original) return next
  if (item.field === 'sentence' && next === '') return ''
  return null
}

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const code = e.code
    return code ? `[${code}] ${e.humanMessage}` : e.humanMessage
  }
  return (e as Error)?.message ?? String(e)
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

// ── 覆核編輯器（逐條，展開在該列下方） ────────────────────────────────────────

function ReviewEditor({ item, me, onClose }: { item: I18nPendingItem; me: string; onClose: () => void }) {
  const { t } = useTranslation()
  const key = rowKey(item)
  const field = item.field as I18nField
  const maxLen = MAX_EN_LEN_BY_FIELD[field] ?? MAX_EN_LEN_BY_FIELD.label

  const [draft, setDraft] = useState(item.target_en ?? '')
  const [assignee, setAssignee] = useState(item.assigned_to ?? '')

  const mark = useMarkI18nReviewed()
  const assign = useAssignI18nReview()

  const ref = {
    entity_type: item.entity_type,
    scope_key: item.scope_key,
    field,
    rule_set_code: item.rule_set_code,
  }

  const blank = draft.trim() === ''
  // 句面留空 ＝ D7.6「刻意不入句」：只有**中文句面本身為空**的那幾列才合法，
  // 判準用後端回的 `source_is_fallback`（與 `_is_reviewable_target` 同一個值），
  // 不是「只要是句面就放行」——後者會讓有中文的句子一路送到 422 才被擋下。
  const blankIsCandidate = field === 'sentence' && blank && item.source_is_fallback
  const blockedByBlank = blank && !blankIsCandidate

  const handleMark = () => {
    mark.mutate({ ...ref, target_en: buildTargetEn(item, blankIsCandidate ? '' : draft) }, { onSuccess: onClose })
  }

  const handleAssign = (to: string | null) => {
    assign.mutate({ ...ref, assigned_to: to })
  }

  return (
    <tr className="bg-slate-50 border-t" data-testid={`i18n-editor-${key}`}>
      <td colSpan={COL_COUNT} className="px-3 py-3">
        <div className="space-y-2 text-sm">
          <div className="text-xs text-slate-500">
            {t('i18nReview.editor.scope', { scope: item.scope_key, field: item.field })}
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">{t('i18nReview.editor.targetEn')}</span>
            <textarea
              className="border rounded px-2 py-1 w-full font-mono"
              rows={field === 'sentence' ? 2 : 1}
              maxLength={maxLen}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              placeholder={t('i18nReview.editor.targetEnPlaceholder')}
              data-testid={`i18n-en-input-${key}`}
            />
            <span className="text-[11px] text-slate-400">
              {t('i18nReview.editor.charCount', { n: draft.length, max: maxLen })}
            </span>
          </label>

          {blockedByBlank && (
            <div className="text-xs text-red-600" data-testid={`i18n-blank-blocked-${key}`}>
              {t('i18nReview.editor.needTranslation')}
            </div>
          )}
          {blankIsCandidate && (
            <div className="text-xs text-amber-700" data-testid={`i18n-blank-sentence-hint-${key}`}>
              {t('i18nReview.editor.blankSentenceHint')}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-40"
              disabled={blockedByBlank || mark.isPending || draft.length > maxLen}
              onClick={handleMark}
              data-testid={`i18n-mark-reviewed-${key}`}
            >
              {mark.isPending ? t('i18nReview.editor.marking') : t('i18nReview.editor.markReviewed')}
            </button>
            <button
              className="px-3 py-1.5 border rounded text-sm text-slate-600 hover:bg-slate-100"
              onClick={onClose}
            >
              {t('i18nReview.editor.cancel')}
            </button>
          </div>

          {/* 指派：與覆核並列，但不改變 status（ADR-032 D6：記的是「誰在處理」） */}
          <div className="flex flex-wrap items-center gap-2 pt-1 border-t">
            <span className="text-xs text-slate-500">{t('i18nReview.editor.assignLabel')}</span>
            <input
              className="border rounded px-2 py-1 text-sm w-36"
              value={assignee}
              onChange={e => setAssignee(e.target.value)}
              placeholder={t('i18nReview.editor.assignPlaceholder')}
              data-testid={`i18n-assign-input-${key}`}
            />
            <button
              className="px-2 py-1 border rounded text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-40"
              disabled={assign.isPending || assignee.trim() === ''}
              onClick={() => handleAssign(assignee.trim())}
              data-testid={`i18n-assign-${key}`}
            >
              {t('i18nReview.editor.assign')}
            </button>
            <button
              className="px-2 py-1 border rounded text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-40"
              disabled={assign.isPending}
              onClick={() => { setAssignee(me); handleAssign(me) }}
              data-testid={`i18n-assign-me-${key}`}
            >
              {t('i18nReview.editor.assignToMe')}
            </button>
            <button
              className="px-2 py-1 border rounded text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-40"
              disabled={assign.isPending || !item.assigned_to}
              onClick={() => { setAssignee(''); handleAssign(null) }}
              data-testid={`i18n-unassign-${key}`}
            >
              {t('i18nReview.editor.unassign')}
            </button>
          </div>

          {(mark.error || assign.error) && (
            <div className="text-xs text-red-600" data-testid={`i18n-editor-error-${key}`}>
              {errorText(mark.error ?? assign.error)}
            </div>
          )}
        </div>
      </td>
    </tr>
  )
}

// ── 主元件 ────────────────────────────────────────────────────────────────────

export function I18nReviewTab() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const canModify = canEdit(me)

  const [entityFilter, setEntityFilter] = useState<I18nEntityType | ''>('')
  const [statusFilter, setStatusFilter] = useState<I18nPendingStatus | ''>('')
  const [rawQ, setRawQ] = useState('')
  const [mineOnly, setMineOnly] = useState(false)
  const [editingKey, setEditingKey] = useState<string | null>(null)

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

  // 關鍵字與「只看指派給我」都是**前端**篩選（後端 `/pending` 沒有這兩個參數）——
  // 資料量小（現況 201 列全量），不值得為它們加端點參數。
  const filteredItems = useMemo(() => {
    const q = rawQ.trim().toLowerCase()
    return items.filter(i => {
      if (mineOnly && i.assigned_to !== me?.employee_no) return false
      if (!q) return true
      return i.source_zh.toLowerCase().includes(q) || (i.target_en ?? '').toLowerCase().includes(q)
    })
  }, [items, rawQ, mineOnly, me?.employee_no])

  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [copiedAll, setCopiedAll] = useState(false)
  // S5：複製失敗（非 HTTPS context、`execCommand` fallback 也失敗）要有明確回饋，
  // 不能靜默無反應——不論失敗的是單列還是整批複製，都用同一顆訊息位。
  const [copyError, setCopyError] = useState(false)

  const handleCopyRow = async (item: I18nPendingItem) => {
    const key = rowKey(item)
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
        {canModify ? t('i18nReview.note') : t('i18nReview.noteViewer')}
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
        {canModify && (
          <label className="flex items-center gap-1 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={mineOnly}
              onChange={e => setMineOnly(e.target.checked)}
              data-testid="i18n-mine-only"
            />
            {t('i18nReview.filters.assignedToMe')}
          </label>
        )}
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
              <th className="px-3 py-2">{t('i18nReview.table.assignedTo')}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {filteredItems.length === 0 && (
              <tr>
                <td colSpan={COL_COUNT} className="px-3 py-6 text-center text-slate-400">
                  {t('i18nReview.table.empty')}
                </td>
              </tr>
            )}
            {filteredItems.map(item => {
              const key = rowKey(item)
              const editing = editingKey === key
              return [
                (
                  <tr key={key} className="border-t align-top" data-testid={`i18n-row-${key}`}>
                    <td className="px-3 py-2">
                      <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-700">
                        {t(`i18nReview.entityType.${item.entity_type}`)}
                      </span>
                      {/* field 對 rule_option 有兩個值（label 下拉標籤／sentence 敘事句面），
                          兩者風險不同（句面是英文使用者在 METHOD 欄實際讀到的整句），
                          必須看得出來是哪一個——分母 63→126 的理由就是這個（D6 分母修正）。 */}
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        {t(`i18nReview.field.${item.field}`, { defaultValue: item.field })}
                        {item.rule_set_code ? ` · ${item.rule_set_code}` : ''}
                      </div>
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
                        {/* source_changed／target_changed：兩個獨立正交維度，不併進 status
                            （D6 補記）——分開顯示，因為對覆核者的意義不同。 */}
                        {item.source_changed && (
                          <span
                            className="px-1.5 py-0.5 rounded text-xs font-medium bg-red-600 text-white"
                            data-testid="i18n-source-changed-badge"
                            title={t('i18nReview.table.sourceChangedHint')}
                          >
                            {t('i18nReview.table.sourceChangedBadge')}
                          </span>
                        )}
                        {item.target_changed && (
                          <span
                            className="px-1.5 py-0.5 rounded text-xs font-medium bg-purple-600 text-white"
                            data-testid="i18n-target-changed-badge"
                            title={t('i18nReview.table.targetChangedHint')}
                          >
                            {t('i18nReview.table.targetChangedBadge')}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-slate-500">
                      {item.review_source ? t(`i18nReview.reviewSource.${item.review_source}`) : '—'}
                    </td>
                    <td className="px-3 py-2 text-slate-500" data-testid={`i18n-assigned-${key}`}>
                      {item.assigned_to ?? <span className="text-slate-400">{t('i18nReview.table.unassigned')}</span>}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        {canModify && (
                          <button
                            className="px-2 py-0.5 rounded text-xs border border-blue-300 text-blue-700 hover:bg-blue-50"
                            onClick={() => setEditingKey(k => (k === key ? null : key))}
                            data-testid={`i18n-open-editor-${key}`}
                          >
                            {editing ? t('i18nReview.table.closeEditor') : t('i18nReview.table.openEditor')}
                          </button>
                        )}
                        <button
                          className="px-2 py-0.5 rounded text-xs border text-slate-600 hover:bg-slate-50"
                          onClick={() => handleCopyRow(item)}
                        >
                          {copiedKey === key ? t('i18nReview.table.copyRowDone') : t('i18nReview.table.copyRow')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ),
                editing && canModify ? (
                  <ReviewEditor
                    key={`${key}:editor`}
                    item={item}
                    me={me?.employee_no ?? ''}
                    onClose={() => setEditingKey(null)}
                  />
                ) : null,
              ]
            })}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}
