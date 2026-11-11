import { useEffect, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useWiStore } from '../wi-workbench/store'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { useWorkspace } from '../../shared/workspace'
import { WorksheetRequiredNotice } from '../../shared/ui/WorksheetRequiredNotice'
import { useWorksheetWorkspace } from '../wi-workbench/useWorksheetWorkspace'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { useLevelStore } from './store'
import { useValidateLevel, useLbReport, type LevelIssue, type LbReportDiag } from './api'
import { cs, rowsIn, rowsInWcub, subGroupsOf, firstIdx, nbList, derive, wcub } from './logic'

const GENERAL_ROLES = ['take_unit', 'scanner', 'transport'] as const
// 匯出阻擋錯誤碼（ADR-035 Spec §8.1）——每碼一個 fix-hint i18n key：levelSystem.exportErr.<CODE>
const EXPORT_ERR_CODES = [
  'E_NARRATIVE_EN_MISSING', 'E_LEVEL_DISCRETE_UNSUPPORTED', 'E_GENERAL_ROLE_MISSING',
  'E_GENERAL_ROLE_ACTION_MISMATCH', 'E_SEGMENT_CROSS_GROUP', 'E_OFFLINE_INCONSISTENT',
  'E_ATOMIC_ON_TOOL_MOTION', 'E_ATOMIC_QUANTITY', 'E_ATOMIC_CROSS_GROUP',
  'E_SPLITTABLE_CONFLICT', 'E_TOOL_NOT_RELEASED', 'E_TOOL_CROSS_CHAIN',
] as const

export function AdvancedView() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const activeWs = useWorkspace(s => s.activeWs)
  const worksheet = useWorksheetWorkspace(activeWs)
  const rows = useWiStore(s => s.rows)
  const revisionNo = useWiStore(s => s.revisionNo)
  const st = useLevelStore()
  const validate = useValidateLevel()
  const rowNarr = useRowNarr()
  const [issues, setIssues] = useState<LevelIssue[]>([])
  const [status, setStatus] = useState('')
  const editable = canEdit(me)

  useEffect(() => { st.sync() }, [rows]) // eslint-disable-line react-hooks/exhaustive-deps

  // 進入/改動即自動檢查（後端權威 R1–R9）
  useEffect(() => {
    if (!rows.length) { setIssues([]); setStatus(''); return }
    const payload = derive(rows, st.levelMap, st.groupMeta, rowNarr)
    validate.mutate(payload, {
      onSuccess: j => { setIssues(j.issues); setStatus(j.valid ? t('levelSystem.valid') : t('levelSystem.invalid', { count: j.issues.length })) },
      onError: e => setStatus(t('levelSystem.checkFailed', { message: (e as Error).message })),
    })
  }, [rows, st.levelMap, st.groupMeta]) // eslint-disable-line react-hooks/exhaustive-deps

  // ADR-021 Phase 3：worksheet 情境只能從分析案件進入（原全域 WorksheetBar 已去全域化並刪除）
  if (!activeWs) return <WorksheetRequiredNotice />

  if (worksheet.isLoading)
    return <div className="bg-white rounded-xl border p-6 text-slate-500">{t('levelSystem.loadingWorksheet')}</div>

  if (worksheet.error)
    return <div className="bg-white rounded-xl border p-6 text-red-600">{t('levelSystem.worksheetLoadFailed', { message: (worksheet.error as Error).message })}</div>

  if (!rows.length)
    return <div className="bg-white rounded-xl border p-6 text-slate-500">{t('levelSystem.noRows')}</div>

  const rowIssue = (i: number) => issues.find(x => x.row_index === i)

  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold mr-1">{t('levelSystem.title')}</h2>
        {editable && <>
          <button className="px-2 py-1 border rounded text-xs bg-sky-50" onClick={() => st.createGroup('sub', '')}>{t('levelSystem.createSub')}</button>
          <button className="px-2 py-1 border rounded text-xs bg-amber-50" onClick={() => st.createGroup('cub', '')}>{t('levelSystem.createCub')}</button>
          <button className="px-2 py-1 border rounded text-xs bg-violet-50" onClick={() => st.createWcub()}>{t('levelSystem.createWcub')}</button>
        </>}
        <span className={`text-xs ${status.startsWith('✓') ? 'text-emerald-600' : status.startsWith('✗') ? 'text-red-600' : 'text-slate-400'}`}>{status}</span>
      </div>
      <p className="text-xs text-slate-500">
        <Trans
          i18nKey="levelSystem.hint"
          components={{ blue: <span className="text-sky-700" />, amber: <span className="text-amber-700" /> }}
        />
      </p>

      <Container label="" depth={0} editable={editable} rowIssue={rowIssue} />

      <NbArea editable={editable} />

      <WcubArea editable={editable} />

      <ExportPanel worksheetId={activeWs} saved={revisionNo != null} />

      {issues.length > 0 &&
        <pre className="font-mono text-xs bg-slate-50 p-2 rounded max-h-40 overflow-auto">
          {issues.map(i => `${i.row_index < 0 ? t('levelSystem.issueWholeSheet') : t('levelSystem.issueRow', { n: i.row_index + 1 })}: ${i.message}`).join('\n')}
        </pre>}
    </div>
  )
}

function Container({ label, depth, editable, rowIssue }:
  { label: string; depth: number; editable: boolean; rowIssue: (i: number) => LevelIssue | undefined }) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const { levelMap, groupMeta, moveTo } = useLevelStore()
  const [over, setOver] = useState(false)

  const items: ({ k: 'row'; id: string; idx: number } | { k: 'grp'; label: string; idx: number })[] = []
  rowsIn(rows, levelMap, label).forEach(r => items.push({ k: 'row', id: r.id, idx: rows.findIndex(x => x.id === r.id) }))
  subGroupsOf(groupMeta, label).forEach(g => items.push({ k: 'grp', label: g, idx: firstIdx(rows, levelMap, groupMeta, g) }))
  items.sort((a, b) => a.idx - b.idx)

  return (
    <div
      onDragOver={editable ? (e => { e.preventDefault(); e.stopPropagation(); setOver(true) }) : undefined}
      onDragLeave={() => setOver(false)}
      onDrop={editable ? (e => { e.preventDefault(); e.stopPropagation(); setOver(false); const id = e.dataTransfer.getData('text/plain'); if (id) moveTo(id, label) }) : undefined}
      className={`space-y-1 ${depth > 0 ? 'px-2 pb-2' : 'bg-slate-50/60 rounded-lg p-2 min-h-[60px]'} ${over ? 'ring-2 ring-violet-400' : ''}`}>
      {items.length === 0 &&
        <div className="text-xs text-slate-400 px-2 py-2 text-center border border-dashed rounded">
          {label === '' ? t('levelSystem.dropRoot') : t('levelSystem.dropEmptyGroup')}
        </div>}
      {items.map(it => it.k === 'row'
        ? <Card key={it.id} id={it.id} editable={editable} rowIssue={rowIssue} />
        : <Box key={it.label} label={it.label} depth={depth + 1} editable={editable} rowIssue={rowIssue} />)}
    </div>
  )
}

function Box({ label, depth, editable, rowIssue }:
  { label: string; depth: number; editable: boolean; rowIssue: (i: number) => LevelIssue | undefined }) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const { levelMap, groupMeta, createGroup, dissolveGroup } = useLevelStore()
  const g = groupMeta[label]; const isCub = g.type === 'cub'
  const n = rowsIn(rows, levelMap, label).length + subGroupsOf(groupMeta, label).length
  return (
    <div className={`rounded-lg border-2 ${isCub ? 'border-amber-300 bg-amber-50/50' : 'border-sky-300 bg-sky-50/50'}`}>
      <div className="flex items-center gap-2 px-2 py-1">
        <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${isCub ? 'bg-amber-200 text-amber-900' : 'bg-sky-200 text-sky-900'}`}>
          {(isCub ? '🔒 ' : '↕ ') + label + t(isCub ? 'levelSystem.box.cubSuffix' : 'levelSystem.box.subSuffix')}
          {g.parent ? t('levelSystem.box.insideParent', { parent: g.parent }) : ''}
        </span>
        <span className="text-[10px] text-slate-400">{n ? t('levelSystem.box.itemCount', { count: n }) : t('levelSystem.box.empty')}</span>
        <span className="flex-1" />
        {editable && !isCub && <button className="text-[11px] text-amber-700 underline" onClick={() => createGroup('cub', label)}>{t('levelSystem.box.createCubChild')}</button>}
        {editable && <button className="text-[11px] text-slate-500 underline" onClick={() => dissolveGroup(label)}>{t('levelSystem.box.dissolve')}</button>}
      </div>
      <Container label={label} depth={depth} editable={editable} rowIssue={rowIssue} />
    </div>
  )
}

function Card({ id, editable, rowIssue }:
  { id: string; editable: boolean; rowIssue: (i: number) => LevelIssue | undefined }) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const rowNarr = useRowNarr()
  const {
    levelMap, patchCell, nbMode, nbPick, toggleNbPick,
    toggleOffline, setStationPin, toggleGeneral, setGeneralRole, toggleMergeLock, setActionType,
    workerCubMeta, assignWcub, wcubError, clearWcubError,
  } = useLevelStore()
  const i = rows.findIndex(r => r.id === id); const row = rows[i]; const m = levelMap[id]
  const c = cs(levelMap, id)
  const isHead = !c || rowsIn(rows, levelMap, c)[0]?.id === id
  const bad = rowIssue(i)
  const wc = wcub(levelMap, id)
  const wcubLabels = Object.keys(workerCubMeta)
  const blocked = wcubError === id
  return (
    <div id={`lvrow-${i}`} draggable={editable && !nbMode}
      onDragStart={e => { e.dataTransfer.setData('text/plain', id); e.dataTransfer.effectAllowed = 'move' }}
      className={`flex flex-col gap-1 px-2 py-1 bg-white rounded border ${bad ? 'bg-red-50 border-red-300' : ''} ${m?.offline ? 'opacity-70' : ''}`}>
      <div className="flex items-center gap-2">
        {nbMode && <input type="checkbox" checked={nbPick.includes(id)} onChange={() => toggleNbPick(id)} />}
        {editable && !nbMode && <span className="text-slate-300 cursor-move select-none">⠿</span>}
        <span className="text-slate-400 w-6 text-right text-xs">{i + 1}</span>
        {isHead && <span className="text-[10px] px-1 rounded bg-violet-100 text-violet-700">main</span>}
        <span className="flex-1 truncate text-sm">{(row && rowNarr(row)) || t('levelSystem.card.unnamed')}</span>
        <span className="font-mono text-xs text-slate-500">{row?.seconds != null ? row.seconds + 's' : ''}</span>
        {isHead && editable &&
          <label className="text-[10px] text-slate-400 flex items-center gap-0.5">{t('levelSystem.card.mainOrder')}
            <input className="border rounded px-1 text-xs w-14" value={m?.level ?? ''} onChange={e => patchCell(id, { level: e.target.value })} />
          </label>}
        {(m?.number || '').trim() && <span className="text-[10px] px-1 rounded bg-rose-100 text-rose-700">🚫{m.number}</span>}
      </div>

      {/* WP12 row-level toolbar：offline / pin / general(+role) / merge_lock / action_type / wcub */}
      <div className="flex items-center gap-1.5 flex-wrap pl-8 text-[10px]">
        {wc && <span data-testid="wcub-chip" className="inline-flex items-center gap-0.5 px-1 rounded bg-violet-100 text-violet-700 font-semibold">👤{wc}</span>}
        {editable && <>
          <button data-testid="offline-toggle" title={t('levelSystem.tags.offline')}
            className={`px-1 rounded border ${m?.offline ? 'bg-slate-700 text-white' : 'bg-white text-slate-500'}`}
            onClick={() => toggleOffline(id)}>⏸</button>
          <label className="inline-flex items-center gap-0.5 text-slate-500" title={t('levelSystem.tags.pin')}>📍
            <input type="number" min={1} className="border rounded w-12 px-1" value={m?.stationPin ?? ''}
              onChange={e => setStationPin(id, e.target.value === '' ? '' : Math.max(1, parseInt(e.target.value) || 1))} />
          </label>
          <button title={t('levelSystem.tags.general')}
            className={`px-1 rounded border ${m?.isGeneral ? 'bg-emerald-600 text-white' : 'bg-white text-slate-500'}`}
            onClick={() => toggleGeneral(id)}>G</button>
          {m?.isGeneral &&
            <select className="border rounded px-1 text-slate-600" value={m?.generalRole ?? ''} onChange={e => setGeneralRole(id, e.target.value)}>
              <option value="">{t('levelSystem.tags.rolePlaceholder')}</option>
              {GENERAL_ROLES.map(r => <option key={r} value={r}>{t(`levelSystem.tags.role.${r}`)}</option>)}
            </select>}
          <button title={t('levelSystem.tags.mergeLock')}
            className={`px-1 rounded border ${m?.mergeLock ? 'bg-amber-600 text-white' : 'bg-white text-slate-500'}`}
            onClick={() => toggleMergeLock(id)}>🔧🔒</button>
          <input className="border rounded px-1 w-28 text-slate-600" placeholder={t('levelSystem.tags.actionType')}
            value={m?.actionType ?? ''} onChange={e => setActionType(id, e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))} />
          <select data-testid="wcub-assign" className="border rounded px-1 text-violet-700" value={wc}
            onChange={e => assignWcub(id, e.target.value)} onFocus={() => { if (blocked) clearWcubError() }}>
            <option value="">{t('levelSystem.wcub.assignNone')}</option>
            {wcubLabels.map(l => <option key={l} value={l}>👤{l}</option>)}
          </select>
          {blocked && <span className="text-red-600" title={t('levelSystem.wcub.blockHint')}>{t('levelSystem.wcub.blocked')}</span>}
        </>}
      </div>
    </div>
  )
}

function WcubArea({ editable }: { editable: boolean }) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const { levelMap, workerCubMeta, removeWcub } = useLevelStore()
  const idx = (id: string) => rows.findIndex(r => r.id === id) + 1
  const labels = Object.keys(workerCubMeta)
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/40 p-2">
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <span className="text-xs font-semibold text-violet-800">{t('levelSystem.wcub.title')}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {labels.length === 0 && <span className="text-[11px] text-slate-400">{t('levelSystem.wcub.empty')}</span>}
        {labels.map(label => {
          const members = rowsInWcub(rows, levelMap, label)
          return (
            <span key={label} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-white border border-violet-300 text-violet-700">
              {t('levelSystem.wcub.chip', {
                label,
                rows: members.length
                  ? members.map(r => t('levelSystem.wcub.chipRow', { n: idx(r.id) })).join(t('levelSystem.listSeparator'))
                  : t('levelSystem.wcub.chipEmpty'),
              })}
              {editable && <button className="text-violet-400 hover:text-violet-700 ml-0.5" onClick={() => removeWcub(label)}>✕</button>}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function ExportPanel({ worksheetId, saved }: { worksheetId: string; saved: boolean }) {
  const { t } = useTranslation()
  const [preview, setPreview] = useState(false)
  const report = useLbReport(worksheetId, preview && saved)
  const data = report.data
  const errors = data?.errors ?? []
  const warnings = data?.warnings ?? []
  const blockExport = errors.length > 0
  const groupCount = data ? Object.keys(data.groups).length : 0

  const hintKey = (code: string) =>
    (EXPORT_ERR_CODES as readonly string[]).includes(code) ? `levelSystem.exportErr.${code}` : ''

  const doExport = () => { window.location.href = `/api/v2/worksheets/${worksheetId}/export/lb-csv` }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-2 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold text-slate-700">{t('levelSystem.export.title')}</span>
        <button data-testid="preview-button" className="px-2 py-1 border rounded text-xs bg-white disabled:opacity-40"
          disabled={!saved || report.isFetching} onClick={() => setPreview(true)}>
          {report.isFetching ? t('levelSystem.export.previewing') : t('levelSystem.export.preview')}
        </button>
        {!saved && <span className="text-[11px] text-amber-700">{t('levelSystem.export.saveToPreview')}</span>}
        <button data-testid="export-button" className="px-2 py-1 border rounded text-xs bg-emerald-50 disabled:opacity-40"
          disabled={!saved || !data || blockExport} onClick={doExport}>
          {t('levelSystem.export.download')}
        </button>
      </div>

      {report.error && <div className="text-[11px] text-red-600">{t('levelSystem.export.reportFailed', { message: (report.error as Error).message })}</div>}

      {data && <div className="text-[11px] text-slate-500">
        {t('levelSystem.export.summary', { tasks: data.tasks_out, groups: groupCount, version: data.contract_version })}
      </div>}

      {blockExport &&
        <ul data-testid="export-error-list" className="text-[11px] text-red-700 space-y-0.5">
          {errors.map((e: LbReportDiag, k: number) =>
            <li key={k}>✗ <span className="font-mono">{e.code}</span>{e.wi_row_id ? ` (${e.wi_row_id})` : ''} — {hintKey(e.code) ? t(hintKey(e.code)) : e.message}</li>)}
        </ul>}

      {!blockExport && warnings.length > 0 &&
        <ul className="text-[11px] text-amber-700 space-y-0.5">
          {warnings.map((w: LbReportDiag, k: number) =>
            <li key={k}>⚠ <span className="font-mono">{w.code}</span>{w.wi_row_id ? ` (${w.wi_row_id})` : ''} — {w.message}</li>)}
        </ul>}
    </div>
  )
}

function NbArea({ editable }: { editable: boolean }) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const { levelMap, nbMode, nbPick, setNbMode, confirmNb, removeNb } = useLevelStore()
  const [count, setCount] = useState(1)
  const nbs = nbList(rows, levelMap)
  const idx = (id: string) => rows.findIndex(r => r.id === id) + 1
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50/40 p-2">
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <span className="text-xs font-semibold text-rose-800">{t('levelSystem.nb.title')}</span>
        <span className="flex-1" />
        {editable && !nbMode && <button className="text-[11px] text-rose-700 underline" onClick={() => setNbMode(true)}>{t('levelSystem.nb.add')}</button>}
        {editable && nbMode && <>
          <span className="text-[11px] text-slate-500">{t('levelSystem.nb.pickHint')}</span>
          <input type="number" className="border rounded w-12 px-1 text-xs" value={count} onChange={e => setCount(parseInt(e.target.value) || 1)} />
          <button className="text-[11px] text-white bg-rose-600 rounded px-2 py-0.5" disabled={!nbPick.length} onClick={() => confirmNb(count)}>{t('levelSystem.nb.confirm')}</button>
          <button className="text-[11px] text-slate-500 underline" onClick={() => setNbMode(false)}>{t('levelSystem.nb.cancel')}</button>
        </>}
      </div>
      <div className="flex flex-wrap gap-1">
        {Object.keys(nbs).length === 0 && !nbMode && <span className="text-[11px] text-slate-400">{t('levelSystem.nb.empty')}</span>}
        {Object.entries(nbs).map(([label, g]) => (
          <span key={label} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-white border border-rose-300 text-rose-700">
            {t('levelSystem.nb.chip', {
              label,
              n: g.count,
              rows: g.ids.map(idx).map(n => t('levelSystem.nb.chipRow', { n })).join(t('levelSystem.listSeparator')),
            })}
            {editable && <button className="text-rose-400 hover:text-rose-700 ml-0.5" onClick={() => removeNb(label)}>✕</button>}
          </span>
        ))}
      </div>
    </div>
  )
}
