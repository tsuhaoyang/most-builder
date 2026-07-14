import { useEffect, useState } from 'react'
import { useWiStore } from '../wi-workbench/store'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { useWorkspace } from '../../shared/workspace'
import { WorksheetRequiredNotice } from '../../shared/ui/WorksheetRequiredNotice'
import { useLevelStore } from './store'
import { useValidateLevel, type LevelIssue } from './api'
import { cs, rowsIn, subGroupsOf, firstIdx, nbList, derive } from './logic'

export function LevelSystem() {
  const { data: me } = useMe()
  const activeWs = useWorkspace(s => s.activeWs)
  const rows = useWiStore(s => s.rows)
  const st = useLevelStore()
  const validate = useValidateLevel()
  const [issues, setIssues] = useState<LevelIssue[]>([])
  const [status, setStatus] = useState('')
  const editable = canEdit(me)

  useEffect(() => { st.sync() }, [rows]) // eslint-disable-line react-hooks/exhaustive-deps

  // 進入/改動即自動檢查（後端權威 R1–R9）
  useEffect(() => {
    if (!rows.length) { setIssues([]); setStatus(''); return }
    const payload = derive(rows, st.levelMap, st.groupMeta)
    validate.mutate(payload, {
      onSuccess: j => { setIssues(j.issues); setStatus(j.valid ? '✓ 群組設定正確' : `✗ ${j.issues.length} 項問題待修正`) },
      onError: e => setStatus('檢查失敗：' + (e as Error).message),
    })
  }, [rows, st.levelMap, st.groupMeta]) // eslint-disable-line react-hooks/exhaustive-deps

  // ADR-021 Phase 3：worksheet 情境只能從分析案件進入（WorksheetBar 已去全域化）
  if (!activeWs) return <WorksheetRequiredNotice />

  if (!rows.length)
    return <div className="bg-white rounded-xl border p-6 text-slate-500">工時表還沒有列。請先從「分析案件 → 編輯工時表」加入動作列。</div>

  const rowIssue = (i: number) => issues.find(x => x.row_index === i)

  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold mr-1">Level System</h2>
        {editable && <>
          <button className="px-2 py-1 border rounded text-xs bg-sky-50" onClick={() => st.createGroup('sub', '')}>＋ sub 群組（可移動）</button>
          <button className="px-2 py-1 border rounded text-xs bg-amber-50" onClick={() => st.createGroup('cub', '')}>＋ cub 群組（同站不可拆）</button>
        </>}
        <span className={`text-xs ${status.startsWith('✓') ? 'text-emerald-600' : status.startsWith('✗') ? 'text-red-600' : 'text-slate-400'}`}>{status}</span>
      </div>
      <p className="text-xs text-slate-500">把卡片拖進群組盒即分組；盒中盒＝巢狀（sub 內開 cub）。<span className="text-sky-700">藍＝sub</span>、<span className="text-amber-700">橘＝cub</span>。系統自動管 main/order。</p>

      <Container label="" depth={0} editable={editable} rowIssue={rowIssue} />

      <NbArea editable={editable} />

      {issues.length > 0 &&
        <pre className="font-mono text-xs bg-slate-50 p-2 rounded max-h-40 overflow-auto">
          {issues.map(i => `${i.row_index < 0 ? '整表' : '列' + (i.row_index + 1)}: ${i.message}`).join('\n')}
        </pre>}
    </div>
  )
}

function Container({ label, depth, editable, rowIssue }:
  { label: string; depth: number; editable: boolean; rowIssue: (i: number) => LevelIssue | undefined }) {
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
          {label === '' ? '把卡片拖到這＝獨立 main' : '空群組——把卡片拖進來'}
        </div>}
      {items.map(it => it.k === 'row'
        ? <Card key={it.id} id={it.id} editable={editable} rowIssue={rowIssue} />
        : <Box key={it.label} label={it.label} depth={depth + 1} editable={editable} rowIssue={rowIssue} />)}
    </div>
  )
}

function Box({ label, depth, editable, rowIssue }:
  { label: string; depth: number; editable: boolean; rowIssue: (i: number) => LevelIssue | undefined }) {
  const rows = useWiStore(s => s.rows)
  const { levelMap, groupMeta, createGroup, dissolveGroup } = useLevelStore()
  const g = groupMeta[label]; const isCub = g.type === 'cub'
  const n = rowsIn(rows, levelMap, label).length + subGroupsOf(groupMeta, label).length
  return (
    <div className={`rounded-lg border-2 ${isCub ? 'border-amber-300 bg-amber-50/50' : 'border-sky-300 bg-sky-50/50'}`}>
      <div className="flex items-center gap-2 px-2 py-1">
        <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${isCub ? 'bg-amber-200 text-amber-900' : 'bg-sky-200 text-sky-900'}`}>
          {(isCub ? '🔒 ' : '↕ ') + label + (isCub ? ' 同站不可拆' : ' 可移動組')}
          {g.parent ? ` ↳在${g.parent}內` : ''}
        </span>
        <span className="text-[10px] text-slate-400">{n ? n + ' 項' : '空'}</span>
        <span className="flex-1" />
        {editable && !isCub && <button className="text-[11px] text-amber-700 underline" onClick={() => createGroup('cub', label)}>＋ cub 子群組</button>}
        {editable && <button className="text-[11px] text-slate-500 underline" onClick={() => dissolveGroup(label)}>解散</button>}
      </div>
      <Container label={label} depth={depth} editable={editable} rowIssue={rowIssue} />
    </div>
  )
}

function Card({ id, editable, rowIssue }:
  { id: string; editable: boolean; rowIssue: (i: number) => LevelIssue | undefined }) {
  const rows = useWiStore(s => s.rows)
  const { levelMap, groupMeta, patchCell, nbMode, nbPick, toggleNbPick } = useLevelStore()
  const i = rows.findIndex(r => r.id === id); const row = rows[i]; const m = levelMap[id]
  const c = cs(levelMap, id)
  const isHead = !c || rowsIn(rows, levelMap, c)[0]?.id === id
  const bad = rowIssue(i)
  return (
    <div id={`lvrow-${i}`} draggable={editable && !nbMode}
      onDragStart={e => { e.dataTransfer.setData('text/plain', id); e.dataTransfer.effectAllowed = 'move' }}
      className={`flex items-center gap-2 px-2 py-1 bg-white rounded border ${bad ? 'bg-red-50 border-red-300' : ''}`}>
      {nbMode && <input type="checkbox" checked={nbPick.includes(id)} onChange={() => toggleNbPick(id)} />}
      {editable && !nbMode && <span className="text-slate-300 cursor-move select-none">⠿</span>}
      <span className="text-slate-400 w-6 text-right text-xs">{i + 1}</span>
      {isHead && <span className="text-[10px] px-1 rounded bg-violet-100 text-violet-700">main</span>}
      <span className="flex-1 truncate text-sm">{row?.narr || '(未命名)'}</span>
      <span className="font-mono text-xs text-slate-500">{row?.seconds != null ? row.seconds + 's' : ''}</span>
      {isHead && editable &&
        <label className="text-[10px] text-slate-400 flex items-center gap-0.5">主序
          <input className="border rounded px-1 text-xs w-14" value={m?.level ?? ''} onChange={e => patchCell(id, { level: e.target.value })} />
        </label>}
      {(m?.number || '').trim() && <span className="text-[10px] px-1 rounded bg-rose-100 text-rose-700">🚫{m.number}</span>}
    </div>
  )
}

function NbArea({ editable }: { editable: boolean }) {
  const rows = useWiStore(s => s.rows)
  const { levelMap, nbMode, nbPick, setNbMode, confirmNb, removeNb } = useLevelStore()
  const [count, setCount] = useState(1)
  const nbs = nbList(rows, levelMap)
  const idx = (id: string) => rows.findIndex(r => r.id === id) + 1
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50/40 p-2">
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <span className="text-xs font-semibold text-rose-800">約束：不可同站 (nb)</span>
        <span className="flex-1" />
        {editable && !nbMode && <button className="text-[11px] text-rose-700 underline" onClick={() => setNbMode(true)}>＋ 新增不可同站約束</button>}
        {editable && nbMode && <>
          <span className="text-[11px] text-slate-500">勾選上方卡片 → 每站≤</span>
          <input type="number" className="border rounded w-12 px-1 text-xs" value={count} onChange={e => setCount(parseInt(e.target.value) || 1)} />
          <button className="text-[11px] text-white bg-rose-600 rounded px-2 py-0.5" disabled={!nbPick.length} onClick={() => confirmNb(count)}>確定</button>
          <button className="text-[11px] text-slate-500 underline" onClick={() => setNbMode(false)}>取消</button>
        </>}
      </div>
      <div className="flex flex-wrap gap-1">
        {Object.keys(nbs).length === 0 && !nbMode && <span className="text-[11px] text-slate-400">（無約束）兩組不可同站時在此設定。</span>}
        {Object.entries(nbs).map(([label, g]) => (
          <span key={label} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-white border border-rose-300 text-rose-700">
            🚫 {label} 每站≤{g.count}：{g.ids.map(idx).map(n => '列' + n).join('、')}
            {editable && <button className="text-rose-400 hover:text-rose-700 ml-0.5" onClick={() => removeNb(label)}>✕</button>}
          </span>
        ))}
      </div>
    </div>
  )
}
