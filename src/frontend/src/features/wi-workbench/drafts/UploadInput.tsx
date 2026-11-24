// 整份上傳（ADR-038 D2 情境 3，W5）：在工作區內上傳 Excel → 欄位對應 → 建 parse job → 顯示進度。
// 每列解析完就出現在編輯區；沒有產生草稿的列（超長、解析失敗、寫不進去）列在下面，可一鍵「建空白草稿」。
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { resolveErrorMessage } from '../../../shared/i18n/errorMessage'
import { ImportModal } from '../../import/ImportModal'
import { TERMINAL_JOB, useParseJob, useParseJobItems, type ParseJobItem } from '../../import/api'
import { ApiError } from '../../../shared/api/client'
import { draftsKey, useBlankFromImport } from './api'

interface ActiveJob { importId: string; jobId: string; total: number }

const FINISHED_ITEM = new Set(['ready', 'review', 'failed'])

const storageKey = (wsId: string) => `ddm.workspace.upload.${wsId}`

/** 進行中的上傳記在 sessionStorage：切 tab 或重新整理後還看得到進度。 */
function loadJob(wsId: string): ActiveJob | null {
  try {
    const raw = sessionStorage.getItem(storageKey(wsId))
    return raw ? (JSON.parse(raw) as ActiveJob) : null
  } catch {
    return null
  }
}

export function UploadInput({ worksheetId, ruleSetCode }: { worksheetId: string; ruleSetCode: string | undefined }) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState<ActiveJob | null>(() => loadJob(worksheetId))
  const job = useParseJob(active?.importId ?? null, active?.jobId ?? null)
  const processed = job.data?.processed ?? 0
  const done = !!job.data && TERMINAL_JOB.has(job.data.status)
  const items = useParseJobItems(active?.importId ?? null, active?.jobId ?? null, done ? -1 : processed)
  const create = useBlankFromImport(worksheetId)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => { setActive(loadJob(worksheetId)) }, [worksheetId])
  // 每處理完一列，編輯區重新讀取（新草稿出現）
  useEffect(() => { void qc.invalidateQueries({ queryKey: draftsKey(worksheetId) }) }, [processed, worksheetId, qc])
  // 記住的 job 在後端已不存在（DB 重置、換環境）：清掉，不讓上傳按鈕永久停用
  useEffect(() => {
    if (job.error instanceof ApiError && job.error.status === 404) clear()
  }, [job.error]) // eslint-disable-line react-hooks/exhaustive-deps

  function started(j: ActiveJob) {
    sessionStorage.setItem(storageKey(worksheetId), JSON.stringify(j))
    setActive(j)
    setMsg(null)
  }
  function clear() {
    sessionStorage.removeItem(storageKey(worksheetId))
    setActive(null)
  }

  // 已處理完（ready／review／failed）卻沒有草稿的列；還在排隊或處理中的不算
  const missing = (items.data?.items ?? []).filter(i => !i.has_drafts && FINISHED_ITEM.has(i.status))

  async function blankDrafts(rows: ParseJobItem[]) {
    setMsg(null)
    try {
      // 後端建：帶 Excel 出處、佔位 cycle（補齊格位前不能確認）；已有草稿的列會跳過，重按不重複
      await create.mutateAsync(rows.map(r => r.import_row_id))
      await qc.invalidateQueries({ queryKey: ['parse-job-items', active?.importId, active?.jobId] })
      setMsg(t('workbench.drafts.upload.blankCreated', { count: rows.length }))
    } catch (e) {
      setMsg(resolveErrorMessage(e, i18n))
    }
  }

  const pct = job.data && job.data.total ? Math.round((job.data.processed / job.data.total) * 100) : 0

  return (
    <div className="text-sm space-y-2" data-testid="upload-entry">
      <p className="text-slate-600">{t('workbench.drafts.upload.hint')}</p>
      <button type="button" className="px-3 py-1.5 border rounded" data-testid="upload-open"
        disabled={!!active && !done} onClick={() => setOpen(true)}>
        {t('workbench.drafts.upload.open')}
      </button>
      {!ruleSetCode && <p className="text-amber-700">{t('workbench.drafts.upload.noRuleSet')}</p>}

      {active && job.data && (
        <div className="border rounded p-2 bg-white space-y-1" data-testid="upload-progress">
          <div className="flex items-center gap-2">
            <span className="font-medium">
              {done ? t(`workbench.drafts.upload.status.${job.data.status}`) : t('workbench.drafts.upload.running')}
            </span>
            <span className="text-slate-500" data-testid="upload-counts">
              {t('workbench.drafts.upload.counts', {
                processed: job.data.processed, total: job.data.total,
                review: job.data.review, failed: job.data.failed,
              })}
            </span>
            {done && (
              <button type="button" className="ml-auto text-xs underline" onClick={clear}>{t('workbench.drafts.upload.dismiss')}</button>
            )}
          </div>
          <div className="h-1.5 bg-slate-100 rounded">
            <div className="h-1.5 bg-sky-500 rounded" style={{ width: `${pct}%` }} />
          </div>
          {missing.length > 0 && (
            <div className="pt-1 space-y-1" data-testid="upload-missing">
              <div className="flex items-center gap-2">
                <span className="text-amber-800">{t('workbench.drafts.upload.missing', { count: missing.length })}</span>
                <button type="button" className="text-xs px-2 py-0.5 border rounded" data-testid="upload-blank-all"
                  disabled={create.isPending} onClick={() => void blankDrafts(missing)}>
                  {t('workbench.drafts.upload.blankAll')}
                </button>
              </div>
              <ul className="text-xs divide-y border rounded max-h-48 overflow-auto">
                {missing.map(r => (
                  <li key={r.item_id} className="px-2 py-1 flex items-center gap-2" data-testid="upload-missing-row">
                    <span className="text-slate-400 w-10">#{r.source_row_no}</span>
                    <span className="flex-1 truncate">{r.description}</span>
                    <span className="text-amber-700">
                      {r.reason && /^[A-Za-z_]+$/.test(r.reason) && i18n.exists(`workbench.drafts.upload.reason.${r.reason}`)
                        ? t(`workbench.drafts.upload.reason.${r.reason}`) : t('workbench.drafts.upload.reason.other')}
                    </span>
                    <button type="button" className="px-1.5 border rounded" disabled={create.isPending}
                      onClick={() => void blankDrafts([r])}>{t('workbench.drafts.upload.blankOne')}</button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {msg && <p role="status" className="text-xs text-slate-600" data-testid="upload-msg">{msg}</p>}

      {open && (
        <ImportModal mode="drafts" worksheetId={worksheetId} ruleSetCode={ruleSetCode}
          onClose={() => setOpen(false)} onJobCreated={started} />
      )}
    </div>
  )
}
