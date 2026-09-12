// ADR-035 D10 F4：作業內容抽屜（job-content drawer）。右側顯示所選作業的四個是非題、步驟清單、進階設定。
// 動作走 jobsActions（A.*）；字串一律 t('levelSystem.jobs.*')；rowNarr/t 產物**不入 store**。
import { useMemo, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useWiStore, type Row } from '../wi-workbench/store'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { useLevelStore } from './store'
import { jobsFromStore } from './jobs'
import { canAssignWcub } from './logic'
import * as A from './jobsActions'
import type { Job, JobModel } from './jobsModel'
import type { LbReport, LbReportRow } from './api'

const GENERAL_ROLES = ['take_unit', 'scanner', 'transport'] as const

interface Props {
  jobId: string | null
  report: LbReport | null
  editable: boolean
}

export function JobDrawer({ jobId, report, editable }: Props) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const levelMap = useLevelStore(s => s.levelMap)
  const groupMeta = useLevelStore(s => s.groupMeta)
  const setMachineUnattended = useLevelStore(s => s.setMachineUnattended)
  const rowNarr = useRowNarr()

  const model: JobModel = useMemo(() => jobsFromStore(rows, levelMap, groupMeta), [rows, levelMap, groupMeta])
  const job = jobId ? model.jobs.find(j => j.id === jobId) : undefined

  const reportRows: Record<string, LbReportRow> = useMemo(() => {
    const m: Record<string, LbReportRow> = {}
    if (report) for (const r of report.rows) m[r.wi_row_id] = r
    return m
  }, [report])

  // 選取的步驟子集（rowId）
  const [sel, setSel] = useState<string[]>([])
  // 名稱編輯本地值
  const [nameDraft, setNameDraft] = useState<string | null>(null)
  const [nameErr, setNameErr] = useState(false)

  if (!job) {
    return <div className="text-xs text-slate-500 p-4">{t('levelSystem.jobs.drawer.empty')}</div>
  }

  const rowById = (id: string): Row | undefined => rows.find(r => r.id === id)
  const stepIds = [...job.steps, ...job.generalSteps]
  const subset = sel.filter(id => stepIds.includes(id))
  const scopeSel = subset.length > 0
  // 只有通用步驟的作業（無 steps）：四題與固定站不適用（general 不得入群組 → E_GENERAL_IN_GROUP）。
  const generalOnly = job.steps.length === 0

  const displayName = job.name ?? (rowNarr(rowById(stepIds[0]!) ?? ({} as Row)) || t('levelSystem.jobs.unnamed'))
  const nameValue = nameDraft ?? displayName

  const commitName = () => {
    const v = (nameDraft ?? '').trim()
    if (nameDraft == null) return
    if (!v) { setNameErr(true); return }
    setNameErr(false)
    A.rename(job, v)
    setNameDraft(null)
  }

  // q.person block：目標步驟有 !canAssignWcub（freq>1 或 tool）→ disable
  const personTargets = scopeSel ? subset : job.steps
  const personBlockedCount = personTargets.filter(id => {
    const r = rowById(id)
    return r ? !canAssignWcub(r) : false
  }).length
  const personDisabled = personBlockedCount > 0

  const subsetArg = scopeSel ? subset : undefined

  const toggleSel = (id: string) => setSel(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]))

  return (
    <div className="space-y-3">
      {/* 標題（可編輯名稱） */}
      <div>
        <input
          className={`w-full border rounded px-2 py-1 text-sm font-semibold ${nameErr ? 'border-red-400' : 'border-slate-200'}`}
          value={nameValue}
          onChange={e => { setNameDraft(e.target.value); setNameErr(false) }}
          onBlur={commitName}
          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
          disabled={!editable}
          aria-label={t('levelSystem.jobs.drawer.rename')}
        />
        {nameErr && <div className="text-[11px] text-red-600 mt-0.5">{t('levelSystem.jobs.drawer.nameEmpty')}</div>}
      </div>

      {/* Scope line */}
      <p className="text-[11px] text-slate-500">
        {scopeSel
          ? <Trans i18nKey="levelSystem.jobs.drawer.scopeSel" components={{ b: <b /> }} values={{ count: subset.length }} />
          : <Trans i18nKey="levelSystem.jobs.drawer.scopeAll" components={{ b: <b /> }} values={{ count: stepIds.length }} />}
      </p>

      {/* 四個是非題 */}
      <div className="space-y-2">
        {generalOnly && (
          <div className="text-[11px] text-slate-500 bg-slate-100 rounded px-2 py-1" data-testid="drawer-general-only">
            {t('levelSystem.jobs.q.generalOnly')}
          </div>
        )}
        {/* 同一工站 */}
        <Question
          testId="drawer-q-station"
          checked={job.sameStation}
          disabled={!editable || generalOnly || job.sameStation}
          onChange={on => A.setSameStation(job, on, subsetArg)}
          label={<Trans i18nKey="levelSystem.jobs.q.station" components={{ b: <b /> }} />}
          hint={job.sameStation ? t('levelSystem.jobs.q.stationAlready') : t('levelSystem.jobs.q.stationHint')}
        />
        {/* 同一個人 */}
        <Question
          testId="drawer-q-person"
          checked={job.samePerson}
          disabled={!editable || generalOnly || personDisabled}
          onChange={on => A.setSamePerson(job, on, subsetArg)}
          label={<Trans i18nKey="levelSystem.jobs.q.person" components={{ b: <b /> }} />}
          hint={personDisabled ? t('levelSystem.jobs.q.personBlocked', { count: personBlockedCount }) : t('levelSystem.jobs.q.personHint')}
        />
        {/* 離線 */}
        <Question
          testId="drawer-q-offline"
          checked={job.offline}
          disabled={!editable || generalOnly}
          onChange={on => A.setOffline(job, on, subsetArg)}
          label={<Trans i18nKey="levelSystem.jobs.q.offline" components={{ b: <b /> }} />}
          hint={t('levelSystem.jobs.q.offlineHint')}
        />
        {/* 固定站 */}
        <div className="rounded border border-slate-200 p-2">
          <div className="text-xs">
            <Trans i18nKey="levelSystem.jobs.q.pin" components={{ b: <b /> }} />
          </div>
          <div className="text-[11px] text-slate-400">{t('levelSystem.jobs.q.pinHint')}</div>
          <div className="flex items-center gap-2 mt-1">
            <input
              data-testid="drawer-pin-input"
              type="number"
              min={1}
              className="border rounded w-16 px-1 text-xs"
              placeholder={t('levelSystem.jobs.q.pinPlaceholder')}
              title={t('levelSystem.jobs.q.pinPrompt')}
              value={job.pin ?? ''}
              disabled={!editable || generalOnly}
              onChange={e => {
                const v = e.target.value
                A.setPin(job, v === '' ? null : Math.max(1, parseInt(v, 10) || 1))
              }}
            />
            <span className="text-[11px] text-slate-500">
              {job.pin != null ? t('levelSystem.jobs.q.pinAt', { n: job.pin }) : t('levelSystem.jobs.q.pinNone')}
            </span>
          </div>
        </div>
      </div>

      {/* Advanced（作業層） */}
      <Collapsible title={t('levelSystem.jobs.adv.title')}>
        <div className="flex items-center gap-2">
          <label className="text-[11px] text-slate-600">{t('levelSystem.jobs.adv.late', { n: job.rowHi ?? job.row })}</label>
          <input
            type="number"
            min={job.row}
            className="border rounded w-16 px-1 text-xs"
            value={job.rowHi ?? ''}
            disabled={!editable}
            onChange={e => {
              const v = e.target.value
              A.setLate(job, v === '' ? null : Math.max(job.row, parseInt(v, 10) || job.row))
            }}
          />
        </div>
        {job.discrete && (
          <div className="mt-1 text-[11px] text-amber-700">
            {t('levelSystem.jobs.adv.discrete', { level: job.discrete })}
            {editable && (
              <button className="ml-2 underline" onClick={() => A.setLayer(job, Math.floor(job.row) || 1)}>
                {t('levelSystem.jobs.adv.discreteFix', { n: Math.floor(job.row) || 1 })}
              </button>
            )}
          </div>
        )}
      </Collapsible>

      {/* 步驟清單 */}
      <div className="space-y-1">
        <div className="text-xs font-semibold text-slate-700">{t('levelSystem.jobs.steps.title')}</div>
        {stepIds.map((id, i) => {
          const r = rowById(id)
          const rr = reportRows[id]
          const tag = model.stepTags[id]
          return (
            <div key={id} data-testid={`drawer-step-${id}`} className="flex items-start gap-2 rounded border border-slate-100 p-1.5">
              <input
                type="checkbox"
                className="mt-0.5"
                aria-label={t('levelSystem.jobs.steps.select', { n: i + 1 })}
                checked={sel.includes(id)}
                onChange={() => toggleSel(id)}
              />
              <span className="text-slate-400 w-5 text-right text-xs">{i + 1}</span>
              <div className="flex-1 space-y-0.5">
                <div className="text-sm">{(r && rowNarr(r)) || t('levelSystem.jobs.unnamed')}</div>
                <StepChips rr={rr} tag={tag} machineUnattended={levelMap[id]?.machineUnattended ?? null} />
              </div>
              {editable && (
                <div className="flex flex-col gap-0.5">
                  <button className="text-[10px] text-slate-500 hover:text-slate-800" title={t('levelSystem.jobs.steps.up')} onClick={() => A.reorderStep(job, id, -1)}>▲</button>
                  <button className="text-[10px] text-slate-500 hover:text-slate-800" title={t('levelSystem.jobs.steps.down')} onClick={() => A.reorderStep(job, id, 1)}>▼</button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 選取 >=1 步：拆 / 移 */}
      {editable && subset.length >= 1 && (
        <div className="rounded border border-slate-200 p-2 space-y-2">
          <div className="text-[11px] text-slate-600">{t('levelSystem.jobs.sel.count', { count: subset.length })}</div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              data-testid="drawer-split"
              className="text-[11px] border rounded px-2 py-0.5 hover:bg-slate-50"
              onClick={() => {
                const name = window.prompt(t('levelSystem.jobs.sel.splitName')) ?? ''
                A.splitSteps(job, subset, name)
                setSel([])
              }}>
              {t('levelSystem.jobs.sel.split')}
            </button>
            <select
              data-testid="drawer-move-select"
              className="text-[11px] border rounded px-1 py-0.5"
              value=""
              onChange={e => {
                const targetId = e.target.value
                if (!targetId) return
                const target = model.jobs.find(j => j.id === targetId)
                if (target) { A.moveStepsTo(job, target, subset); setSel([]) }
              }}>
              <option value="">{t('levelSystem.jobs.sel.moveTo')}</option>
              {model.jobs.filter(j => j.id !== job.id).map(j => (
                <option key={j.id} value={j.id}>{j.name ?? j.id}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* 選取剛好 1 步：通用角色 + 進階（含機台三態） */}
      {editable && subset.length === 1 && (
        <SingleStepPanel
          id={subset[0]}
          report={report}
          reportRow={reportRows[subset[0]]}
          setMachineUnattended={setMachineUnattended}
        />
      )}
    </div>
  )
}

function Question({ testId, checked, disabled, onChange, label, hint }: {
  testId: string; checked: boolean; disabled: boolean; onChange: (on: boolean) => void
  label: React.ReactNode; hint: string
}) {
  return (
    <label className="flex items-start gap-2 rounded border border-slate-200 p-2 cursor-pointer">
      <input
        data-testid={testId}
        type="checkbox"
        className="mt-0.5"
        checked={checked}
        disabled={disabled}
        onChange={e => onChange(e.target.checked)}
      />
      <div className="flex-1">
        <div className="text-xs">{label}</div>
        <div className="text-[11px] text-slate-400">{hint}</div>
      </div>
    </label>
  )
}

function StepChips({ rr, tag, machineUnattended }: {
  rr: LbReportRow | undefined
  tag: import('./jobsModel').StepTag | undefined
  machineUnattended: boolean | null
}) {
  const { t } = useTranslation()
  const chips: { key: string; text: string; cls: string }[] = []
  const push = (key: string, text: string, cls: string) => chips.push({ key, text, cls })

  if (rr?.is_general) push('gen', t('levelSystem.jobs.chip.general', { count: 1 }), 'bg-emerald-100 text-emerald-800')
  if (tag?.cub) push('station', t('levelSystem.jobs.chip.stationPart'), 'bg-amber-50 text-amber-700')
  if (tag?.wcub) push('person', t('levelSystem.jobs.chip.personPart'), 'bg-violet-50 text-violet-700')
  if (tag?.offline) push('offline', t('levelSystem.jobs.chip.offline'), 'bg-slate-200 text-slate-700')
  if (tag?.segment) push('batch', t('levelSystem.jobs.chip.batch'), 'bg-sky-100 text-sky-800')

  if (rr) {
    if (rr.parts.length > 1) push('parts', t('levelSystem.jobs.chip.splitParts', { tool: rr.tool_id ?? '', count: rr.parts.length }), 'bg-slate-100 text-slate-700')
    if (rr.repeat_n != null && rr.repeat_n > 1) push('rep', t('levelSystem.jobs.chip.repeatN', { n: rr.repeat_n }), 'bg-slate-100 text-slate-700')
    if (rr.frequency > 1) push('freq', t('levelSystem.jobs.chip.freq', { n: rr.frequency }), 'bg-slate-100 text-slate-700')
    if (rr.x_seconds >= 1) {
      const sec = Math.round(rr.x_seconds)
      if (machineUnattended === null) push('mach', t('levelSystem.jobs.chip.machineUnknown', { seconds: sec }), 'bg-amber-100 text-amber-800')
      else if (machineUnattended === false) push('mach', t('levelSystem.jobs.chip.machineAttended', { seconds: sec }), 'bg-slate-100 text-slate-700')
      else push('mach', t('levelSystem.jobs.chip.machineUnattended', { seconds: sec }), 'bg-slate-100 text-slate-700')
    }
  }

  if (chips.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1">
      {chips.map(c => <span key={c.key} className={`text-[10px] px-1 py-0.5 rounded ${c.cls}`}>{c.text}</span>)}
    </div>
  )
}

function SingleStepPanel({ id, report, reportRow, setMachineUnattended }: {
  id: string
  report: LbReport | null
  reportRow: LbReportRow | undefined
  setMachineUnattended: (id: string, val: boolean | null) => void
}) {
  const { t } = useTranslation()
  const levelMap = useLevelStore(s => s.levelMap)
  const toggleMergeLock = useLevelStore(s => s.toggleMergeLock)
  const patchCell = useLevelStore(s => s.patchCell)
  const setActionType = useLevelStore(s => s.setActionType)
  const m = levelMap[id]
  const isCmMachine = (reportRow?.x_seconds ?? 0) >= 1
  const currentRole = m?.isGeneral ? (m?.generalRole || '') : ''

  return (
    <div className="rounded border border-slate-200 p-2 space-y-2">
      {/* 通用角色 */}
      <div>
        <div className="text-xs">
          <Trans i18nKey="levelSystem.jobs.general.q" components={{ b: <b /> }} />
        </div>
        <div className="text-[11px] text-slate-400">{t('levelSystem.jobs.general.hint')}</div>
        <select
          data-testid="drawer-general-select"
          className="mt-1 border rounded px-1 py-0.5 text-xs"
          value={currentRole}
          onChange={e => A.setGeneral(id, e.target.value || null)}>
          <option value="">{t('levelSystem.jobs.general.no')}</option>
          {GENERAL_ROLES.map(role => (
            <option key={role} value={role}>{t(`levelSystem.roles.${role}` as const)}</option>
          ))}
        </select>
      </div>

      <Collapsible title={t('levelSystem.jobs.adv.title')}>
        <label className="flex items-center gap-2 text-[11px] text-slate-600">
          <input type="checkbox" checked={!!m?.mergeLock} onChange={() => toggleMergeLock(id)} />
          {t('levelSystem.jobs.adv.mergeLock')}
        </label>
        <div className="flex items-center gap-2 mt-1">
          <label className="text-[11px] text-slate-600">{t('levelSystem.jobs.adv.coefficient')}</label>
          <input
            type="number"
            step="0.1"
            className="border rounded w-16 px-1 text-xs"
            value={m?.coefficient ?? 1}
            onChange={e => patchCell(id, { coefficient: Number(e.target.value) || 1 })}
          />
        </div>
        <div className="flex items-center gap-2 mt-1">
          <label className="text-[11px] text-slate-600">{t('levelSystem.jobs.adv.actionType')}</label>
          <input
            className="border rounded w-28 px-1 text-xs"
            value={m?.actionType ?? ''}
            onChange={e => setActionType(id, e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))}
          />
        </div>
        {isCmMachine && (
          <div className="mt-1">
            <label className="text-[11px] text-slate-600 block">{t('levelSystem.jobs.adv.machineAttendance')}</label>
            <select
              data-testid="drawer-machine-select"
              className="border rounded px-1 py-0.5 text-xs mt-0.5"
              value={m?.machineUnattended === null || m?.machineUnattended === undefined ? '' : m.machineUnattended ? 'unattended' : 'attended'}
              onChange={e => {
                const v = e.target.value
                setMachineUnattended(id, v === '' ? null : v === 'unattended')
              }}>
              <option value="">{t('levelSystem.jobs.adv.machineUnknown')}</option>
              <option value="attended">{t('levelSystem.jobs.adv.machineAttendedOpt')}</option>
              <option value="unattended">{t('levelSystem.jobs.adv.machineUnattendedOpt')}</option>
            </select>
          </div>
        )}
      </Collapsible>
      {report == null && <span className="hidden" />}
    </div>
  )
}

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded border border-slate-200">
      <button className="w-full text-left px-2 py-1 text-[11px] text-slate-600 flex items-center gap-1" onClick={() => setOpen(o => !o)}>
        <span>{open ? '▾' : '▸'}</span>{title}
      </button>
      {open && <div className="px-2 pb-2">{children}</div>}
    </div>
  )
}
