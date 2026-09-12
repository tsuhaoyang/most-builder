// ADR-035 D10 F3/F4/F5/F6：作業版外殼。掛 LbPreview（dry-run debounce+latest-wins）取得 report；
// 子檢視切換（作業順序／產線視角）、頂部 pills、儲存／儲存並交出、開發者網格、通知面板（含去看/回答）。
// 顯示字串一律 t('levelSystem.*')；rowNarr/t 產物與 buildNotices 結果**不入 store**。
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { ApiError } from '../../shared/api/client'
import { useWiStore } from '../wi-workbench/store'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { buildSaveBody } from '../wi-workbench/savePayload'
import { useSaveWorkspace } from '../wi-workbench/useSaveWorkspace'
import { useLevelStore } from './store'
import { useLbPreview, useValidateLevel, type LbReport, type LevelIssue } from './api'
import { derive } from './logic'
import { applyBaseline } from './jobsActions'
import { jobsFromStore } from './jobs'
import { buildNotices } from './notices'
import { JobsFlow } from './JobsFlow'
import { JobDrawer } from './JobDrawer'
import { LineView } from './LineView'
import { Notices } from './Notices'
import { DevGrid } from './DevGrid'

type SubView = 'flow' | 'line'

interface PreviewError { n: number; message: string }

export function JobsShell({ activeWs }: { activeWs: string }) {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const editable = canEdit(me)
  const rows = useWiStore(s => s.rows)
  const levelMap = useLevelStore(s => s.levelMap)
  const groupMeta = useLevelStore(s => s.groupMeta)
  const rowNarr = useRowNarr()

  const [dev, setDev] = useState(false)
  const preview = useLbPreview(activeWs, dev)
  const save = useSaveWorkspace(activeWs)
  const validate = useValidateLevel()

  const [report, setReport] = useState<LbReport | null>(null)
  const [levelIssues, setLevelIssues] = useState<LevelIssue[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [subView, setSubView] = useState<SubView>('flow')
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [previewError, setPreviewError] = useState<PreviewError | null>(null)
  const [updating, setUpdating] = useState(false)
  const [baseline, setBaseline] = useState<{ jobCount: number } | null>(null)
  const [baselineWs, setBaselineWs] = useState<string>('')

  // 節流：debounce + latest-wins。seq 遞增，onSuccess/onError 只認最新 seq。
  const seqRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // worksheet 切換 → 清 dismissed（session 級，附錄 A）
  useEffect(() => { setDismissed(new Set()); setReport(null); setPreviewError(null) }, [activeWs])

  // baseline（附錄 A.4）：每個 worksheet 載入後套用一次
  useEffect(() => {
    if (!editable || !rows.length || baselineWs === activeWs) return
    setBaselineWs(activeWs)
    const res = applyBaseline()
    if (res.applied) setBaseline({ jobCount: res.jobCount })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWs, rows.length, editable])

  function undoBaseline() {
    setBaseline(null)
    setBaselineWs('')
    useWiStore.getState().setRows([...useWiStore.getState().rows])
  }

  // rows/levelMap/groupMeta/dev 變動 → debounce 400ms 後 dry-run 預覽（latest-wins）。
  useEffect(() => {
    if (!rows.length) { setReport(null); return }
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      const payload = derive(rows, levelMap, groupMeta, rowNarr)
      const baseRevision = useWiStore.getState().revisionNo
      const body = buildSaveBody(rows, payload, baseRevision)
      const mySeq = ++seqRef.current
      setUpdating(true)
      preview.mutate(body, {
        onSuccess: r => {
          if (mySeq !== seqRef.current) return  // stale
          setReport(r)
          setPreviewError(null)
          setUpdating(false)
        },
        onError: err => {
          if (mySeq !== seqRef.current) return  // stale
          setUpdating(false)
          // 422：後端指出某列 MOST 內容有問題 → 顯示錯誤條（n = 該列 index+1）。
          if (err instanceof ApiError && err.status === 422) {
            const detail = err.detail as Record<string, unknown> | null
            let n = 1
            const idx = detail && typeof detail === 'object' ? (detail.row_index ?? detail.index) : undefined
            if (typeof idx === 'number') n = idx + 1
            setPreviewError({ n, message: err.humanMessage })
          }
        },
      })
    }, 400)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, levelMap, groupMeta, dev])

  // R1–R9 驗證（作業流程正常時應為空）；levelMap/rows 變動時重跑。
  useEffect(() => {
    if (!rows.length) { setLevelIssues([]); return }
    const payload = derive(rows, levelMap, groupMeta, rowNarr)
    let cancelled = false
    validate.mutate(payload, {
      onSuccess: res => { if (!cancelled) setLevelIssues(res.issues ?? []) },
      onError: () => { if (!cancelled) setLevelIssues([]) },
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, levelMap, groupMeta])

  // pills：從 buildNotices 算 ask/err 數。stepOf 只為文字，這裡不需精準（用簡短標籤）。
  const stepOf = (wiRowId: string): string => {
    const i = rows.findIndex(r => r.id === wiRowId)
    return i < 0 ? '' : t('levelSystem.jobs.stepShort', { n: i + 1 })
  }
  const notices = useMemo(
    () => buildNotices(report, levelIssues, { t, stepOf }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report, levelIssues],
  )
  const askCount = notices.filter(n => n.type === 'ask' && !(n.kind !== 'H_MACHINE_TIME' && dismissed.has(n.key))).length
  const errCount = notices.filter(n => n.type === 'err').length

  const onDismiss = (key: string) => setDismissed(s => new Set(s).add(key))

  // 去看：找到含此列的 job → 選取並切回作業順序（JobDrawer 依 selectedJobId 顯示步驟）。
  const onGoto = (wiRowId: string) => {
    const model = jobsFromStore(rows, levelMap, groupMeta)
    const job = model.jobs.find(j => [...j.steps, ...j.generalSteps].includes(wiRowId))
    if (job) {
      setSelectedJobId(job.id)
      setSubView('flow')
    }
  }

  async function doSave(): Promise<boolean> {
    const payload = derive(rows, levelMap, groupMeta, rowNarr)
    const baseRevision = useWiStore.getState().revisionNo
    try {
      await save.saveBody(buildSaveBody(rows, payload, baseRevision))
      return true
    } catch {
      return false
    }
  }

  async function doSaveAndExport() {
    const ok = await doSave()
    if (ok && errCount === 0) {
      window.location.href = `/api/v2/worksheets/${activeWs}/export/lb-csv`
    }
  }

  return (
    <div className="space-y-3">
      {/* 頂部工具列：子檢視切換 + pills + 動作按鈕 + dev */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <button
            data-testid="subview-flow"
            className={`px-2 py-1 rounded text-xs border ${subView === 'flow' ? 'bg-slate-700 text-white border-slate-700' : 'bg-white text-slate-600'}`}
            onClick={() => setSubView('flow')}>
            {t('levelSystem.jobs.view.flow')}
          </button>
          <button
            data-testid="subview-line"
            className={`px-2 py-1 rounded text-xs border ${subView === 'line' ? 'bg-slate-700 text-white border-slate-700' : 'bg-white text-slate-600'}`}
            onClick={() => setSubView('line')}>
            {t('levelSystem.jobs.view.line')}
          </button>
        </div>

        <div className="flex items-center gap-1 text-[11px]">
          {askCount > 0 && (
            <span data-testid="pill-ask" className="px-1.5 py-0.5 rounded bg-sky-100 text-sky-800">{t('levelSystem.jobs.pill.ask', { count: askCount })}</span>
          )}
          {errCount > 0 && (
            <span data-testid="pill-err" className="px-1.5 py-0.5 rounded bg-red-100 text-red-800">{t('levelSystem.jobs.pill.err', { count: errCount })}</span>
          )}
          {errCount === 0 && (
            <span data-testid="pill-ok" className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800">{t('levelSystem.jobs.pill.ok')}</span>
          )}
          {updating && <span data-testid="preview-updating" className="text-slate-400">{t('levelSystem.jobs.preview.updating')}</span>}
        </div>

        <div className="flex-1" />

        {editable && (
          <div className="flex items-center gap-2">
            <button
              data-testid="jobs-save"
              className="px-2 py-1 rounded text-xs border bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              disabled={save.isPending}
              onClick={doSave}>
              {t('levelSystem.jobs.save')}
            </button>
            <button
              data-testid="jobs-save-export"
              className="px-2 py-1 rounded text-xs border bg-sky-600 text-white border-sky-600 hover:bg-sky-700 disabled:opacity-50"
              disabled={save.isPending || errCount > 0}
              onClick={doSaveAndExport}>
              {t('levelSystem.jobs.saveAndExport')}
            </button>
            <label className="flex items-center gap-1 text-[11px] text-slate-500">
              <input data-testid="jobs-dev" type="checkbox" checked={dev} onChange={e => setDev(e.target.checked)} />
              {t('levelSystem.jobs.dev')}
            </label>
          </div>
        )}
      </div>

      {previewError && (
        <div data-testid="preview-error" className="text-xs bg-red-50 border border-red-200 text-red-800 rounded px-2 py-1">
          {t('levelSystem.jobs.preview.rowError', { n: previewError.n, message: previewError.message })}
        </div>
      )}

      {baseline && (
        <div className="flex items-center gap-2 text-xs bg-sky-50 border border-sky-200 rounded px-2 py-1" data-testid="baseline-notice">
          <span className="text-sky-800">{t('levelSystem.jobs.baseline.applied', { count: baseline.jobCount })}</span>
          <button className="text-sky-700 underline" onClick={undoBaseline}>{t('levelSystem.jobs.baseline.undo')}</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-3">
        <div>
          <h3 className="font-semibold text-sm mb-1">{t('levelSystem.jobs.title')}</h3>
          <p className="text-xs text-slate-500 mb-2">{t('levelSystem.jobs.subtitle')}</p>
          {subView === 'flow' ? (
            <JobsFlow report={report} editable={editable} onSelect={setSelectedJobId} selectedJobId={selectedJobId} />
          ) : (
            <LineView report={report} />
          )}
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-2">
          <JobDrawer jobId={selectedJobId} report={report} editable={editable} />
        </div>
      </div>

      <Notices
        report={report}
        levelIssues={levelIssues}
        editable={editable}
        dismissed={dismissed}
        onDismiss={onDismiss}
        onGoto={onGoto}
      />

      {dev && <DevGrid report={report} />}
    </div>
  )
}
