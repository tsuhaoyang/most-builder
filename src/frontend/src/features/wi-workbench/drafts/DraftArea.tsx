// 工作區編輯區（ADR-038 D2／D3）：三種輸入的產出都在這裡，逐列或整組確認後「寫入工時表」。
// 確認只是標記；寫入才落盤（追加到表尾、TMU 由後端以工時表的規則版本重算）。
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../../../shared/api/client'
import { resolveErrorMessage } from '../../../shared/i18n/errorMessage'
import { useWiStore } from '../store'
import { useRowNarr } from '../useRowNarr'
import {
  useCommitDrafts, useConfirmDrafts, useDeleteDraft, useDrafts, type WiDraft,
} from './api'
import {
  countDrafts, draftAsRow, groupDrafts, parseIssues, parsedIncomplete, quantityNote, wiGroupTruncated,
} from './logic'

/** 409 回應指到的草稿 id（DRAFT_INCOMPLETE 的 draft_ids、DRAFT_STALE 的 drafts[].draft_id）。 */
function flaggedIds(e: unknown): string[] {
  if (!(e instanceof ApiError)) return []
  const detail = ((e.detail as { detail?: Record<string, unknown> } | null)?.detail ?? {}) as {
    draft_ids?: unknown; drafts?: unknown
  }
  const ids = Array.isArray(detail.draft_ids) ? detail.draft_ids : []
  const stale = Array.isArray(detail.drafts) ? detail.drafts.map(x => (x as { draft_id?: unknown }).draft_id) : []
  return [...ids, ...stale].filter((x): x is string => typeof x === 'string')
}

const SOURCE_CLS: Record<string, string> = {
  manual: 'bg-slate-100 text-slate-700',
  ai_service: 'bg-violet-100 text-violet-800',
  rule_based: 'bg-amber-100 text-amber-800',
  imported: 'bg-sky-100 text-sky-800',
}
const STATUS_CLS: Record<string, string> = {
  pending: 'bg-white text-slate-600 border',
  confirmed: 'bg-emerald-100 text-emerald-800',
  committed: 'bg-slate-200 text-slate-500',
}

export function DraftArea({
  worksheetId,
  editable,
  editingId,
  onEdit,
  onCommitted,
}: {
  worksheetId: string
  editable: boolean
  editingId: string | null
  onEdit: (d: WiDraft) => void
  onCommitted: () => void
}) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const rowNarr = useRowNarr()
  const { data, isLoading, error } = useDrafts(worksheetId, editable)
  const confirm = useConfirmDrafts(worksheetId)
  const del = useDeleteDraft(worksheetId)
  const commit = useCommitDrafts(worksheetId)
  const [msg, setMsg] = useState<{ text: string; kind: 'ok' | 'err' | 'warn' } | null>(null)
  const [showCommitted, setShowCommitted] = useState(false)
  // 409 DRAFT_INCOMPLETE／DRAFT_STALE 指到的列：標紅，讓使用者知道是哪幾列
  const [flagged, setFlagged] = useState<Set<string>>(new Set())

  if (!editable) return null
  if (isLoading) return <div className="text-sm text-slate-500">{t('workbench.drafts.loading')}</div>
  if (error) return <div className="text-sm text-red-600">{resolveErrorMessage(error, i18n)}</div>

  const all = data?.items ?? []
  const visible = showCommitted ? all : all.filter(d => d.status !== 'committed')
  const groups = groupDrafts(visible)
  const counts = countDrafts(all)

  function fail(e: unknown) {
    const code = e instanceof ApiError ? e.code : null
    setFlagged(new Set(flaggedIds(e)))
    if (code === 'WORKSHEET_REVISION_CONFLICT') {
      setMsg({ text: t('workbench.drafts.commitConflict'), kind: 'err' })
      qc.invalidateQueries({ queryKey: ['worksheet', worksheetId] })
      return
    }
    setMsg({ text: resolveErrorMessage(e, i18n), kind: 'err' })
  }

  async function run(fn: () => Promise<unknown>) {
    setMsg(null)
    setFlagged(new Set())
    try { await fn() } catch (e) { fail(e) }
  }

  async function doCommit() {
    const { revisionNo: rev, hasUnsaved } = useWiStore.getState()
    // 寫入後會重新讀回工時表；表上（含 level／LB 標記）還沒存檔的修改會被蓋掉，所以先擋
    if (hasUnsaved()) { setMsg({ text: t('workbench.drafts.saveFirst'), kind: 'warn' }); return }
    if (rev == null) { setMsg({ text: t('workbench.drafts.noRevision'), kind: 'err' }); return }
    setMsg(null)
    setFlagged(new Set())
    try {
      const out = await commit.mutateAsync(rev)
      useWiStore.getState().setRevisionMeta({ revisionNo: out.revision_no })
      qc.invalidateQueries({ queryKey: ['worksheet', worksheetId] })
      qc.invalidateQueries({ queryKey: ['versions'] })
      setMsg({ text: t('workbench.drafts.committed', { count: out.committed.length, rev: out.revision_no }), kind: 'ok' })
      onCommitted()
    } catch (e) { fail(e) }
  }

  const busy = confirm.isPending || del.isPending || commit.isPending

  return (
    <section className="border rounded-lg p-3 space-y-2 bg-slate-50" data-testid="draft-area">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{t('workbench.drafts.title')}</h3>
        <span className="text-xs text-slate-500" data-testid="draft-counts">
          {t('workbench.drafts.counts', { pending: counts.pending, confirmed: counts.confirmed })}
        </span>
        <label className="text-xs text-slate-500 flex items-center gap-1 ml-auto">
          <input type="checkbox" checked={showCommitted} onChange={e => setShowCommitted(e.target.checked)} />
          {t('workbench.drafts.showCommitted', { count: counts.committed })}
        </label>
        <button
          type="button"
          data-testid="draft-commit"
          disabled={busy || counts.confirmed === 0}
          onClick={doCommit}
          className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg disabled:opacity-40 text-sm"
        >
          {commit.isPending ? t('workbench.drafts.committing') : t('workbench.drafts.commit', { count: counts.confirmed })}
        </button>
      </div>
      <p className="text-xs text-slate-500">{t('workbench.drafts.hint')}</p>
      {msg && (
        <div role="status" data-testid="draft-msg"
          className={`text-sm rounded px-2 py-1 ${msg.kind === 'ok' ? 'bg-emerald-50 text-emerald-800' : msg.kind === 'warn' ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-700'}`}>
          {msg.text}
        </div>
      )}
      {groups.length === 0 && <div className="text-sm text-slate-400">{t('workbench.drafts.empty')}</div>}
      {groups.map(g => (
        <div key={g.key} className="bg-white border rounded" data-testid="draft-group">
          <div className="flex items-center gap-2 px-2 py-1 border-b bg-slate-100">
            <span className="font-medium text-sm" data-testid="draft-group-name">{g.name ?? t('workbench.drafts.unnamedGroup')}</span>
            <span className="text-xs text-slate-500">{t('workbench.drafts.groupCount', { count: g.drafts.length })}</span>
            {g.pending > 0 && (
              <button type="button" data-testid="draft-confirm-group" disabled={busy}
                className="ml-auto text-xs px-2 py-0.5 border rounded hover:bg-emerald-50 disabled:opacity-40"
                onClick={() => run(() => confirm.mutateAsync({ group_key: g.key }))}>
                {t('workbench.drafts.confirmGroup')}
              </button>
            )}
          </div>
          <ul className="divide-y">
            {g.drafts.map(d => {
              const issues = parseIssues(d)
              const otherIssues = issues.filter(i => i !== 'ai_unknown_code')  // 這個有專屬提示，不再列原始碼
              const qty = quantityNote(d)
              return (
                <li key={d.id} data-testid="draft-row" data-status={d.status} data-source={d.source}
                  data-flagged={flagged.has(d.id) ? 'true' : undefined}
                  className={`px-2 py-1.5 text-sm ${editingId === d.id ? 'bg-blue-50' : ''} ${flagged.has(d.id) ? 'ring-2 ring-red-400' : ''}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`text-[11px] px-1.5 rounded ${SOURCE_CLS[d.source] ?? ''}`}>{t(`workbench.drafts.source.${d.source}`)}</span>
                    <span className={`text-[11px] px-1.5 rounded ${STATUS_CLS[d.status] ?? ''}`}>{t(`workbench.drafts.status.${d.status}`)}</span>
                    <span className="flex-1 min-w-[12rem]" data-testid="draft-narr">{rowNarr(draftAsRow(d)) || t('workbench.drafts.noNarr')}</span>
                    {d.status !== 'committed' && (
                      <>
                        <button type="button" className="text-xs px-2 py-0.5 border rounded" disabled={busy}
                          data-testid="draft-edit" onClick={() => onEdit(d)}>{t('workbench.drafts.edit')}</button>
                        {d.status === 'pending' && (
                          <button type="button" className="text-xs px-2 py-0.5 border rounded hover:bg-emerald-50" disabled={busy}
                            data-testid="draft-confirm" onClick={() => run(() => confirm.mutateAsync({ draft_ids: [d.id] }))}>
                            {t('workbench.drafts.confirm')}
                          </button>
                        )}
                        <button type="button" className="text-xs px-2 py-0.5 border rounded text-red-600" disabled={busy}
                          data-testid="draft-delete"
                          onClick={() => { if (window.confirm(t('workbench.drafts.deleteConfirm'))) void run(() => del.mutateAsync(d.id)) }}>
                          {t('workbench.drafts.delete')}
                        </button>
                      </>
                    )}
                  </div>
                  {(parsedIncomplete(d) || d.stale_reason || wiGroupTruncated(d) || issues.length > 0 || qty) && (
                    <div className="mt-1 space-y-0.5 text-xs">
                      {d.stale_reason && (
                        <div className="text-amber-700" data-testid="draft-stale">
                          {t(`workbench.drafts.stale.${d.stale_reason}`)}
                        </div>
                      )}
                      {parsedIncomplete(d) && <div className="text-red-600" data-testid="draft-incomplete">{t('workbench.drafts.incomplete')}</div>}
                      {issues.includes('ai_unknown_code') && (
                        <div className="text-amber-700" data-testid="draft-unknown-code">{t('workbench.drafts.unknownCode')}</div>
                      )}
                      {wiGroupTruncated(d) && <div className="text-slate-500">{t('workbench.drafts.wiGroupTruncated')}</div>}
                      {qty && (
                        <div className={qty.applied ? 'text-sky-700' : 'text-amber-700'} data-testid="draft-quantity">
                          {qty.applied
                            ? t('workbench.drafts.quantity.applied', { n: String(qty.excel), rule: qty.rule })
                            : t('workbench.drafts.quantity.notApplied', {
                              n: String(qty.excel), rule: qty.rule,
                              reason: i18n.exists(`workbench.drafts.quantity.reason.${qty.reason}`)
                                ? t(`workbench.drafts.quantity.reason.${qty.reason}`) : (qty.reason ?? ''),
                            })}
                        </div>
                      )}
                      {otherIssues.length > 0 && (
                        <div className="text-slate-500" data-testid="draft-issues">
                          {t('workbench.drafts.issues', { list: otherIssues.join(', ') })}
                        </div>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </section>
  )
}
