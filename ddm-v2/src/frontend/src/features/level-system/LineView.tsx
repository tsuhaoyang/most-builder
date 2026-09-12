// ADR-035 D10 F5：產線視角（line view）。把作業依「排（layer）」由上而下排開，標出通用動作的
// 線頭（take_unit）與每站開頭／結尾（scanner／transport）。純消費 jobsFromStore + LbReport。
// 顯示字串一律 t('levelSystem.jobs.line.*')；rowNarr/t 產物不入 store。
import { Trans, useTranslation } from 'react-i18next'
import { useWiStore, type Row } from '../wi-workbench/store'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { useLevelStore } from './store'
import { jobsFromStore } from './jobs'
import type { Job, JobModel } from './jobsModel'
import type { LbReport } from './api'

interface Props {
  report: LbReport | null
}

export function LineView({ report }: Props) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const levelMap = useLevelStore(s => s.levelMap)
  const groupMeta = useLevelStore(s => s.groupMeta)
  const rowNarr = useRowNarr()

  const model: JobModel = jobsFromStore(rows, levelMap, groupMeta)
  const rowById = (id: string): Row | undefined => rows.find(r => r.id === id)

  const jobName = (job: Job): string =>
    job.name ?? ((rowById(job.steps[0] ?? job.generalSteps[0]!) && rowNarr(rowById(job.steps[0] ?? job.generalSteps[0]!)!)) || t('levelSystem.jobs.unnamed'))

  // 通用動作角色 → 標記文字
  const generalText = (role: string): string | null => {
    for (const j of model.jobs) {
      for (const id of j.generalSteps) {
        const m = levelMap[id]
        if (m?.isGeneral && m.generalRole === role) {
          const r = rowById(id)
          return (r && rowNarr(r)) || jobName(j)
        }
      }
    }
    return null
  }
  const headText = generalText('take_unit')
  const startText = generalText('scanner')
  const endText = generalText('transport')

  const displayRows = [...new Set(model.jobs.filter(j => !j.discrete).map(j => j.row))].sort((a, b) => a - b)
  const bandOfJob = (job: Job): number => displayRows.indexOf(job.row) + 1
  const jobsInBand = (band: number): Job[] => model.jobs.filter(j => !j.discrete && bandOfJob(j) === band)

  // 秒數：有 report → duration_ms_total/1000 加總；否則 row.seconds*freq
  const reportRow = (id: string) => report?.rows.find(r => r.wi_row_id === id)
  const jobSeconds = (job: Job): number => {
    const ids = [...job.steps, ...job.generalSteps]
    if (report) {
      const rr = ids.map(reportRow).filter((r): r is NonNullable<typeof r> => !!r)
      if (rr.length) return rr.reduce((s, r) => s + r.duration_ms_total / 1000, 0)
    }
    return ids.reduce((s, id) => {
      const r = rowById(id)
      return s + (r ? r.seconds * (r.freq || 1) : 0)
    }, 0)
  }

  const totalHumanSeconds = report
    ? report.rows.reduce((s, r) => s + r.duration_ms_total / 1000, 0)
    : model.jobs.reduce((s, j) => s + jobSeconds(j), 0)

  const errCount = report?.errors.length ?? 0
  const tasksOut = report?.tasks_out ?? 0

  const blockCls = (job: Job): string => {
    if (job.offline) return 'bg-slate-100 border-slate-300 text-slate-500'
    if (job.pin != null) return 'bg-indigo-50 border-indigo-200'
    if (job.sameStation) return 'bg-amber-50 border-amber-200'
    return 'bg-white border-slate-200'
  }

  const marker = (text: string, testid: string, i18nKey: string) => (
    <div data-testid={testid} className="text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
      {t(i18nKey, { text })}
    </div>
  )

  return (
    <div className="space-y-1" data-testid="line-view">
      <p className="text-xs text-slate-500">{t('levelSystem.jobs.line.hint')}</p>

      {headText && marker(headText, 'line-head', 'levelSystem.jobs.line.head')}
      {startText && marker(startText, 'line-station-start', 'levelSystem.jobs.line.stationStart')}

      {model.layers.map(band => {
        const bandJobs = jobsInBand(band)
        return (
          <div key={band} className="rounded-lg border border-slate-200 bg-slate-50/60 p-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">{band}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {bandJobs.map(job => (
                <div key={job.id} data-testid={`line-block-${job.id}`} className={`w-52 rounded-lg border p-2 space-y-1 ${blockCls(job)}`}>
                  <div className="text-sm font-medium truncate">
                    {job.offline && '⏸ '}{job.pin != null && '📍 '}{job.sameStation && '🏭 '}{jobName(job)}
                  </div>
                  <div className="text-[11px] text-slate-500">
                    {t('levelSystem.jobs.card.meta', { steps: job.steps.length + job.generalSteps.length, seconds: Math.round(jobSeconds(job)).toString() })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}

      {endText && marker(endText, 'line-station-end', 'levelSystem.jobs.line.stationEnd')}

      <div className="text-xs text-slate-600 pt-1">
        <Trans i18nKey="levelSystem.jobs.line.foot" components={{ b: <b /> }} values={{ tasks: tasksOut, seconds: Math.round(totalHumanSeconds) }} />
        {errCount > 0
          ? <span className="text-red-600">{t('levelSystem.jobs.line.footBlocked', { count: errCount })}</span>
          : <span className="text-emerald-600">{t('levelSystem.jobs.line.footOk')}</span>}
      </div>
    </div>
  )
}
