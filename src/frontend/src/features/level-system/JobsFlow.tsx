// ADR-035 D10 F3：作業順序畫布（job-order canvas）。把作業依「排（layer）」由上而下排成水平帶；
// 同一排＝可同時做。純消費 jobsFromStore 反投影 + LbReport（chips/秒數）；動作走 jobsActions（A.*）。
// 顯示字串一律 t('levelSystem.jobs.*')；rowNarr/t 產物**不入 store**。
import { useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useWiStore, type Row } from '../wi-workbench/store'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { useLevelStore } from './store'
import { jobsFromStore } from './jobs'
import * as A from './jobsActions'
import type { Job, JobModel, StepTag } from './jobsModel'
import type { LbReport, LbReportRow } from './api'

interface Props {
  report: LbReport | null
  editable: boolean
  onSelect: (jobId: string) => void
  selectedJobId: string | null
}

/** wi_row_id → LbReportRow 索引（report 存在時）。 */
function reportIndex(report: LbReport | null): Record<string, LbReportRow> {
  const m: Record<string, LbReportRow> = {}
  if (report) for (const r of report.rows) m[r.wi_row_id] = r
  return m
}

export function JobsFlow({ report, editable, onSelect, selectedJobId }: Props) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const levelMap = useLevelStore(s => s.levelMap)
  const groupMeta = useLevelStore(s => s.groupMeta)
  const rowNarr = useRowNarr()
  const model: JobModel = jobsFromStore(rows, levelMap, groupMeta)
  const idxOfRow: Record<string, LbReportRow> = reportIndex(report)
  const rowById = (id: string): Row | undefined => rows.find(r => r.id === id)

  // 名稱去重：同名作業附序號（card.dupSuffix）
  const nameCounts: Record<string, number> = {}
  const jobName = (job: Job): string => {
    const base = job.name ?? (rowNarr(rowById(job.steps[0] ?? job.generalSteps[0]!) ?? ({} as Row)) || t('levelSystem.jobs.unnamed'))
    return base
  }

  // 每個顯示排號（1..k）對應的 job.row 值
  const displayRows = [...new Set(model.jobs.filter(j => !j.discrete).map(j => j.row))].sort((a, b) => a - b)
  const bandOfJob = (job: Job): number => displayRows.indexOf(job.row) + 1

  // 統計重複名稱，發序號
  const seen: Record<string, number> = {}
  const allNames = model.jobs.map(jobName)
  allNames.forEach(n => { nameCounts[n] = (nameCounts[n] || 0) + 1 })
  const displayName = (job: Job): string => {
    const base = jobName(job)
    if ((nameCounts[base] || 0) <= 1) return base
    seen[base] = (seen[base] || 0) + 1
    return t('levelSystem.jobs.card.dupSuffix', { name: base, k: seen[base] })
  }

  const jobsInBand = (band: number): Job[] =>
    model.jobs.filter(j => !j.discrete && bandOfJob(j) === band)
  const discreteJobs = model.jobs.filter(j => j.discrete)

  // DnD state（拖曳中的 jobId）
  const [dragId, setDragId] = useState<string | null>(null)

  const onDropCard = (targetJob: Job) => {
    if (!dragId || dragId === targetJob.id) { setDragId(null); return }
    const dragged = model.jobs.find(j => j.id === dragId)
    if (dragged) A.joinLayerOf(dragged, targetJob)
    setDragId(null)
  }
  const onDropGap = (afterLayerJobRow: number) => {
    if (!dragId) return
    const dragged = model.jobs.find(j => j.id === dragId)
    if (dragged) A.placeBetween(dragged, afterLayerJobRow)
    setDragId(null)
  }

  return (
    <div className="space-y-1">
      <p className="text-xs text-slate-500">
        <Trans i18nKey="levelSystem.jobs.flow.hint" components={{ b: <b /> }} />
      </p>

      {editable && (
        <Gap onDrop={() => onDropGap(displayRows[0] != null ? displayRows[0] - 1 : 0)} label={t('levelSystem.jobs.flow.gapFirst')} />
      )}

      {model.layers.map(band => {
        const bandJobs = jobsInBand(band)
        const parallel = bandJobs.length > 1
        const hint = (parallel
          ? t('levelSystem.jobs.flow.bandParallel', { count: bandJobs.length })
          : t('levelSystem.jobs.flow.bandSingle'))
          + (band > 1 ? t('levelSystem.jobs.flow.bandWait') : '')
        const bandRowVal = displayRows[band - 1]
        return (
          <div key={band}>
            <div data-testid={`layer-band-${band}`} className="rounded-lg border border-slate-200 bg-slate-50/60 p-2 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">{band}</span>
                <span className="text-[11px] text-slate-500">{hint}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {bandJobs.map(job => (
                  <JobCard
                    key={job.id}
                    job={job}
                    name={displayName(job)}
                    band={band}
                    bandHasMultiple={parallel}
                    report={report}
                    reportRows={idxOfRow}
                    levelMap={levelMap}
                    stepTags={model.stepTags}
                    editable={editable}
                    selected={selectedJobId === job.id}
                    onClick={() => onSelect(job.id)}
                    onDragStartCard={() => setDragId(job.id)}
                    onDropCard={() => onDropCard(job)}
                  />
                ))}
              </div>
            </div>
            {editable && <Gap onDrop={() => onDropGap(bandRowVal ?? band)} label={t('levelSystem.jobs.flow.gapAfter')} />}
          </div>
        )
      })}

      {discreteJobs.length > 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 p-2 space-y-2">
          {discreteJobs.map(job => (
            <JobCard
              key={job.id}
              job={job}
              name={displayName(job)}
              band={0}
              bandHasMultiple={false}
              report={report}
              reportRows={idxOfRow}
              levelMap={levelMap}
              stepTags={model.stepTags}
              editable={editable}
              selected={selectedJobId === job.id}
              onClick={() => onSelect(job.id)}
              onDragStartCard={() => setDragId(job.id)}
              onDropCard={() => onDropCard(job)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function Gap({ onDrop, label }: { onDrop: () => void; label: string }) {
  const [over, setOver] = useState(false)
  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); onDrop() }}
      className={`h-4 flex items-center justify-center text-[10px] rounded border border-dashed ${over ? 'ring-2 ring-sky-400 text-sky-600 border-sky-300' : 'text-transparent border-transparent hover:text-slate-400 hover:border-slate-200'}`}>
      {label}
    </div>
  )
}

interface CardProps {
  job: Job
  name: string
  band: number
  bandHasMultiple: boolean
  report: LbReport | null
  reportRows: Record<string, LbReportRow>
  levelMap: Record<string, import('./logic').LevelCell>
  stepTags: Record<string, StepTag>
  editable: boolean
  selected: boolean
  onClick: () => void
  onDragStartCard: () => void
  onDropCard: () => void
}

function JobCard({
  job, name, band, bandHasMultiple, report, reportRows, levelMap, stepTags,
  editable, selected, onClick, onDragStartCard, onDropCard,
}: CardProps) {
  const { t } = useTranslation()
  const [over, setOver] = useState(false)

  const jobRowIds = [...job.steps, ...job.generalSteps]
  const jobReportRows = jobRowIds.map(id => reportRows[id]).filter((r): r is LbReportRow => !!r)

  // 秒數：有 report → duration_ms_total/1000 加總；否則 row.seconds*freq 加總
  const rows = useWiStore.getState().rows
  const rowById = (id: string) => rows.find(r => r.id === id)
  let seconds = 0
  if (report && jobReportRows.length) {
    seconds = jobReportRows.reduce((s, r) => s + r.duration_ms_total / 1000, 0)
  } else {
    seconds = jobRowIds.reduce((s, id) => {
      const r = rowById(id)
      return s + (r ? r.seconds * (r.freq || 1) : 0)
    }, 0)
  }
  const secondsStr = Math.round(seconds).toString()

  const stepCount = job.steps.length + job.generalSteps.length

  // chips
  const chips: { key: string; text: string; cls: string }[] = []
  const push = (key: string, text: string, cls: string) => chips.push({ key, text, cls })

  // 部分同站：有 stepTags.cub 但非整個作業
  const someCub = job.steps.some(id => stepTags[id]?.cub)
  if (job.sameStation) push('station', t('levelSystem.jobs.chip.station'), 'bg-amber-100 text-amber-800')
  else if (someCub) push('stationPart', t('levelSystem.jobs.chip.stationPart'), 'bg-amber-50 text-amber-700')

  const someWcub = job.steps.some(id => stepTags[id]?.wcub)
  if (job.samePerson) push('person', t('levelSystem.jobs.chip.person'), 'bg-violet-100 text-violet-800')
  else if (someWcub) push('personPart', t('levelSystem.jobs.chip.personPart'), 'bg-violet-50 text-violet-700')

  if (job.offline) push('offline', t('levelSystem.jobs.chip.offline'), 'bg-slate-200 text-slate-700')
  if (job.pin != null) push('pin', t('levelSystem.jobs.chip.pin', { n: job.pin }), 'bg-slate-100 text-slate-700')
  if (job.generalSteps.length) push('general', t('levelSystem.jobs.chip.general', { count: job.generalSteps.length }), 'bg-emerald-100 text-emerald-800')

  const anySegment = jobRowIds.some(id => stepTags[id]?.segment)
  if (anySegment) push('batch', t('levelSystem.jobs.chip.batch'), 'bg-sky-100 text-sky-800')

  // 工具：report.rows 的 distinct tool_id
  const tools = [...new Set(jobReportRows.map(r => r.tool_id).filter((v): v is string => !!v))]
  tools.forEach(tool => push(`tool:${tool}`, t('levelSystem.jobs.chip.tool', { tool }), 'bg-slate-100 text-slate-700'))

  // error rows：report.errors 有此 job 的 wi_row_id
  const errIds = new Set((report?.errors ?? []).map(e => e.wi_row_id).filter(Boolean))
  const errCount = jobRowIds.filter(id => errIds.has(id)).length
  if (errCount > 0) push('toFix', t('levelSystem.jobs.chip.toFix', { count: errCount }), 'bg-red-100 text-red-800')

  // per-row report chips
  jobReportRows.forEach(r => {
    if (r.repeat_n != null && r.repeat_n > 1) push(`rep:${r.wi_row_id}`, t('levelSystem.jobs.chip.repeatN', { n: r.repeat_n }), 'bg-slate-100 text-slate-700')
    if (r.parts.length > 1) push(`parts:${r.wi_row_id}`, t('levelSystem.jobs.chip.splitParts', { tool: r.tool_id ?? '', count: r.parts.length }), 'bg-slate-100 text-slate-700')
    if (r.frequency > 1) push(`freq:${r.wi_row_id}`, t('levelSystem.jobs.chip.freq', { n: r.frequency }), 'bg-slate-100 text-slate-700')
    if (r.x_seconds >= 1) {
      const ms = levelMap[r.wi_row_id]?.machineUnattended ?? null
      const sec = Math.round(r.x_seconds)
      if (ms === null) push(`mach:${r.wi_row_id}`, t('levelSystem.jobs.chip.machineUnknown', { seconds: sec }), 'bg-amber-100 text-amber-800')
      else if (ms === false) push(`mach:${r.wi_row_id}`, t('levelSystem.jobs.chip.machineAttended', { seconds: sec }), 'bg-slate-100 text-slate-700')
      else push(`mach:${r.wi_row_id}`, t('levelSystem.jobs.chip.machineUnattended', { seconds: sec }), 'bg-slate-100 text-slate-700')
    }
  })

  if (job.discrete) push('discrete', t('levelSystem.jobs.chip.discrete', { level: job.discrete }), 'bg-amber-50 text-amber-700')

  return (
    <div
      data-testid={`job-card-${job.id}`}
      draggable={editable}
      onDragStart={e => { e.dataTransfer.setData('text/plain', job.id); e.dataTransfer.effectAllowed = 'move'; onDragStartCard() }}
      onDragOver={editable ? (e => { e.preventDefault(); e.stopPropagation(); setOver(true) }) : undefined}
      onDragLeave={() => setOver(false)}
      onDrop={editable ? (e => { e.preventDefault(); e.stopPropagation(); setOver(false); onDropCard() }) : undefined}
      onClick={onClick}
      className={`w-56 rounded-lg border bg-white p-2 space-y-1 cursor-pointer select-none
        ${selected ? 'ring-2 ring-sky-400 border-sky-300' : 'border-slate-200 hover:border-slate-300'}
        ${over ? 'ring-2 ring-amber-400' : ''}`}>
      <div className="flex items-center gap-1">
        {editable && <span className="text-slate-300 cursor-move select-none">⠿</span>}
        <span className="flex-1 text-sm font-medium truncate">{name}</span>
      </div>
      <div className="text-[11px] text-slate-500">{t('levelSystem.jobs.card.meta', { steps: stepCount, seconds: secondsStr })}</div>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {chips.map(c => (
            <span key={c.key} className={`text-[10px] px-1 py-0.5 rounded ${c.cls}`}>{c.text}</span>
          ))}
        </div>
      )}
      {editable && (
        <div className="flex items-center gap-1 pt-0.5">
          {band > 1 && (
            <button
              data-testid="job-merge-up"
              className="text-[10px] text-slate-600 border rounded px-1 py-0.5 hover:bg-slate-50"
              onClick={e => { e.stopPropagation(); A.mergeUp(job) }}>
              {t('levelSystem.jobs.card.mergeUp')}
            </button>
          )}
          {bandHasMultiple && (
            <button
              data-testid="job-own-row"
              className="text-[10px] text-slate-600 border rounded px-1 py-0.5 hover:bg-slate-50"
              onClick={e => { e.stopPropagation(); A.ownRow(job) }}>
              {t('levelSystem.jobs.card.ownRow')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
