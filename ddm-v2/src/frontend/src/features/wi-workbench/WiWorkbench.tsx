import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRuleSetOptions, useVocab, useCalculate, useSaveWorksheet, useWorksheet } from './api'
import { useWiStore, type Row } from './store'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { useWorkspace } from '../../shared/workspace'
import { TMU_SEC } from '../../shared/config'
import { apiPost } from '../../shared/api/client'
import { ComboBox } from '../../shared/ui/ComboBox'
import { Hint } from '../../shared/ui/Hint'
import { useCreateVocab, type VocabIn } from '../master-data/api'
import {
  defaultCycle, buildPayload, aBandOpts, shortNarr, payloadToState,
  type CycleState, type ASlot, type ABand,
} from './cycle'
import { useLevelStore } from '../level-system/store'
import { derive, type LevelCell, type GroupMeta } from '../level-system/logic'

// ─── Local types ───────────────────────────────────────────────────────────────
interface WiGroup { id: string; name: string; rowIds: string[] }
type SlotKey = 'a0' | 'b1' | 'g' | 'a3' | 'b4' | 'p' | 'm' | 'x' | 'i' | 'a6'

interface NlDraftSlot {
  slot_index: number
  field: string
  chosen: { option_code: string; score: number; source: string } | null
}
interface NlDraftRes {
  suggested_seq?: string | null
  slots?: NlDraftSlot[]
  overall_confidence?: number
}

const HANDS = [{ v: 'RH', l: '右手' }, { v: 'LH', l: '左手' }, { v: 'BH', l: '雙手' }]

const SLOT_COLORS: Record<string, { filled: string; empty: string }> = {
  A: { filled: 'bg-blue-600 text-white border-blue-600', empty: 'bg-blue-50 text-blue-400 border-blue-200 border-dashed' },
  B: { filled: 'bg-slate-500 text-white border-slate-500', empty: 'bg-slate-50 text-slate-400 border-slate-200 border-dashed' },
  G: { filled: 'bg-green-600 text-white border-green-600', empty: 'bg-green-50 text-green-400 border-green-200 border-dashed' },
  P: { filled: 'bg-amber-500 text-white border-amber-500', empty: 'bg-amber-50 text-amber-400 border-amber-200 border-dashed' },
  M: { filled: 'bg-amber-500 text-white border-amber-500', empty: 'bg-amber-50 text-amber-400 border-amber-200 border-dashed' },
  X: { filled: 'bg-purple-600 text-white border-purple-600', empty: 'bg-purple-50 text-purple-400 border-purple-200 border-dashed' },
  I: { filled: 'bg-teal-600 text-white border-teal-600', empty: 'bg-teal-50 text-teal-400 border-teal-200 border-dashed' },
}

// ─── Sel: small native select (amber-bg) ───────────────────────────────────────
function Sel({ value, onChange, opts, cls }: {
  value: string; onChange: (v: string) => void
  opts: { v: string; l: string }[]; cls?: string
}) {
  return (
    <select
      className={cls ?? 'border-2 border-dashed border-slate-300 rounded px-1 py-0.5 text-sm bg-amber-50'}
      value={value} onChange={e => onChange(e.target.value)}
    >
      {opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
}

// ─── A-slot helpers ────────────────────────────────────────────────────────────
function aIdx(val: number, bands: ABand[]): number {
  if (val === 0) return 0
  for (const b of bands) {
    const bv = b.max_value == null ? 999 : b.max_value
    if (val === bv) return b.index
  }
  return 0
}

function aAbbrev(slot: ASlot, aBands: { reach: ABand[]; twist: ABand[]; foot: ABand[] }): string {
  const m = Math.max(
    aIdx(slot.reach, aBands.reach),
    aIdx(slot.twist, aBands.twist),
    aIdx(slot.foot, aBands.foot),
  )
  return m > 0 ? `A${m}` : '—'
}

function aIsFilled(slot: ASlot): boolean {
  return slot.reach > 0 || slot.twist > 0 || slot.foot > 0
}

// ─── NL draft → CycleState patch ──────────────────────────────────────────────
function nlDraftPatch(res: NlDraftRes): Partial<CycleState> {
  const patch: Partial<CycleState> = {}
  if (res.suggested_seq === 'GM' || res.suggested_seq === 'CM') {
    patch.seq = res.suggested_seq as 'GM' | 'CM'
  }
  for (const slot of (res.slots ?? [])) {
    if (!slot.chosen) continue
    const code = slot.chosen.option_code
    switch (slot.field) {
      case 'g_code': patch.g = code; break
      case 'b_code': patch.b1 = code; break
      case 'b_code2': patch.b4 = code; break
      case 'p_base_code': patch.p_base = code; break
      // A-slot reverse-mapping skipped (distance→ASlot requires lexicon lookup)
    }
  }
  return patch
}

// ─── Main component ────────────────────────────────────────────────────────────
export function WiWorkbench() {
  const { data: me } = useMe()
  const { data: opts } = useRuleSetOptions()
  const { data: vocab = [] } = useVocab()
  const calc = useCalculate()
  const createVocab = useCreateVocab()
  const activeWs = useWorkspace(s => s.activeWs)
  const save = useSaveWorksheet(activeWs)
  const qc = useQueryClient()
  const { data: wsData } = useWorksheet(activeWs)
  const { rows, addRow, delRow, setRows, totalTmu } = useWiStore()

  // ── existing editor state ──────────────────────────────────────────────────
  const [cur, setCur] = useState<CycleState>(defaultCycle())
  const [tmu, setTmu] = useState<number | null>(null)
  const [tech, setTech] = useState('')
  const [saveMsg, setSaveMsg] = useState('')
  const editable = canEdit(me)

  // ── [F] NL draft state ─────────────────────────────────────────────────────
  const [nlText, setNlText] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlError, setNlError] = useState('')

  // ── [D] drag state ──────────────────────────────────────────────────────────
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null)

  // ── [D] multi-select ────────────────────────────────────────────────────────
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set())

  // ── [E] WI groups state ────────────────────────────────────────────────────
  const [wiGroups, setWiGroups] = useState<WiGroup[]>([])
  const [wiNameInput, setWiNameInput] = useState('')
  const [expandedWiIds, setExpandedWiIds] = useState<Set<string>>(new Set())
  const [highlightedRowIds, setHighlightedRowIds] = useState<Set<string>>(new Set())

  // ── [C] slot modal ─────────────────────────────────────────────────────────
  const [activeSlot, setActiveSlot] = useState<SlotKey | null>(null)

  // ── load/switch worksheet ─────────────────────────────────────────────────
  useEffect(() => {
    if (!wsData) return
    setRows(wsData.rows.map(r => ({
      id: r.wi_row_id, seq: (r.cycle?.seq_kind === 'CM' ? 'CM' : 'GM') as 'GM' | 'CM',
      handCode: r.hand ?? 'RH', freq: r.frequency, simoGroup: r.simo_group_id ?? '',
      nv: { obj: r.object_vocab_id ?? '', from: r.from_vocab_id ?? '', to: r.to_vocab_id ?? '' },
      narr: r.cycle?.narrative ?? '', tmu: r.cycle?.total_tmu ?? 0, seconds: r.cycle?.total_seconds ?? 0,
      payload: r.cycle?.slot_inputs ?? null,
    })))
    const lm: Record<string, LevelCell> = {}; const gm: Record<string, GroupMeta> = {}
    wsData.rows.forEach((r, i) => {
      const L = r.level
      lm[r.wi_row_id] = {
        coefficient: L?.coefficient ?? 1, number: L?.number ?? '', number_count: L?.number_count ?? '',
        level: L?.level ?? String(i + 1), countersignature: L?.countersignature ?? '', machine_count: 1, manpower: 1,
      }
      const csl = (L?.countersignature ?? '').trim()
      if (csl && !gm[csl]) gm[csl] = { type: csl.startsWith('cub') ? 'cub' : 'sub', parent: L?.parent_countersignature ?? '', seq: i }
    })
    useLevelStore.getState().hydrate(lm, gm, wsData.rows.length)
  }, [wsData, setRows])

  // ── debounced backend calculate ───────────────────────────────────────────
  const payload = useMemo(() => (opts ? buildPayload(cur, opts.code) : null), [cur, opts])
  useEffect(() => {
    if (!payload) { setTmu(null); setTech(''); return }
    const id = setTimeout(() => calc.mutate(payload, {
      onSuccess: r => { setTmu(r.total_tmu); setTech(r.tech_line) },
      onError: () => { setTmu(null); setTech('') },
    }), 250)
    return () => clearTimeout(id)
  }, [JSON.stringify(payload)]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!opts) return <div className="bg-white rounded-xl border p-6 text-slate-500">載入 rule-set…</div>

  // ── helpers ───────────────────────────────────────────────────────────────
  const set = (patch: Partial<CycleState>) => setCur(c => ({ ...c, ...patch }))
  const gm = cur.seq === 'GM'
  const vopts = (kind: string) => vocab.filter(v => v.kind === kind).map(v => ({ v: v.id, l: v.name_zh }))
  const vname = (_kind: string, id: string) => vocab.find(v => v.id === id)?.name_zh ?? ''
  const label = (kind: string, code: string) => {
    const m: Record<string, { code: string; label: string }[]> = { g: opts.g, p_base: opts.p_bases, m_verb: opts.m_verbs }
    return m[kind]?.find(o => o.code === code)?.label ?? ''
  }
  const mkVocab = (kind: string, nvKey: 'obj' | 'from' | 'to', ph: string) => (
    <ComboBox options={vopts(kind)} value={cur.nv[nvKey]} placeholder={ph}
      onPick={id => set({ nv: { ...cur.nv, [nvKey]: id } })}
      onCreate={editable ? (name) => createVocab.mutate({ kind, name_zh: name } as VocabIn,
        { onSuccess: v => setCur(c => ({ ...c, nv: { ...c.nv, [nvKey]: v.id } })) }) : undefined} />
  )

  // ── slot builder helpers (used in modal) ───────────────────────────────────
  const aBlock = (slot: ASlot, onSlot: (s: ASlot) => void) => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle px-1 bg-blue-50 border border-blue-200 rounded">
      <Hint tip="A 移動/伸手：取 伸手、手度(扭轉)、腳步 三者分級的最大值；距離越大分數越高。" />
      {(['reach', 'twist', 'foot'] as const).map(comp => (
        <Sel key={comp} value={String(slot[comp] || 0)}
          opts={aBandOpts(opts.a_bands[comp], comp).map(o => ({ v: String(o.v), l: o.l }))}
          onChange={v => onSlot({ ...slot, [comp]: parseFloat(v) || 0 })} />
      ))}
    </span>
  )
  const bBlock = (key: 'b1' | 'b4') => (
    <span className="inline-flex items-center align-middle">
      <Hint tip="B 身體動作：彎腰/起身/站坐等輔助動作（無=0）。" />
      <Sel value={cur[key] ?? ''} onChange={v => set({ [key]: v || null } as Partial<CycleState>)}
        opts={[{ v: '', l: '身體:無' }, ...opts.b.filter(b => b.code !== 'b_none').map(b => ({ v: b.code, l: b.label }))]} />
    </span>
  )
  const gBlock = () => {
    const g = opts.g.find(x => x.code === cur.g)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="G 取得：抓握/接觸/拿取等方式；部分方式需勾修飾子，否則計 0。" />
        <Sel value={cur.g} onChange={v => set({ g: v, gMod: {} })}
          opts={[{ v: '', l: '—取得方式—' }, ...opts.g.map(o => ({ v: o.code, l: o.label }))]} />
        {g?.requires_modifier && g.modifier_key && (
          <Sel value={cur.gMod[g.modifier_key] ? '1' : '0'}
            onChange={v => set({ gMod: { ...cur.gMod, [g.modifier_key!]: v === '1' } })}
            opts={[{ v: '0', l: `—${g.modifier_key} 未勾—` }, { v: '1', l: `✓ ${g.modifier_key}` }]} />
        )}
      </span>
    )
  }
  const pBlock = () => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle">
      <Hint tip="P 放置：放/組/保持等 + 最多 2 個附加（對準、插入、壓合…）。選「對準」須再勾精度(<4mm)。" />
      <Sel value={cur.p_base} onChange={v => set({ p_base: v })}
        opts={[{ v: '', l: '—放置—' }, ...opts.p_bases.map(o => ({ v: o.code, l: o.label }))]} />
      {[0, 1].map(i => (
        <Sel key={i} value={cur.p_addons[i] ?? ''}
          onChange={v => { const a = cur.p_addons.filter((_, j) => j !== i); if (v) a.splice(i, 0, v); set({ p_addons: a.slice(0, 2) }) }}
          opts={[{ v: '', l: '—附加—' }, ...opts.p_addons.map(o => ({ v: o.code, l: o.label }))]} />
      ))}
      {cur.p_addons.some(c => opts.p_addons.find(a => a.code === c)?.needs_precision) && (
        <Sel value={cur.precision ? '1' : '0'} onChange={v => set({ precision: v === '1' })}
          opts={[{ v: '0', l: '精度未勾' }, { v: '1', l: '精度<4mm' }]} />
      )}
    </span>
  )
  // CM sub-blocks (used in modal for M/X/I separately)
  const mVerbBlock = () => {
    const mv = opts.m_verbs.find(x => x.code === cur.m.verb)
    const k = mv?.pricing_kind
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="M 控制移動：推/拉/旋轉/鎖附等受控動作；依動詞種類自動要距離、角度或圈數。" />
        <Sel value={cur.m.verb} onChange={v => set({ m: { ...cur.m, verb: v } })}
          opts={[{ v: '', l: '—控制動詞—' }, ...opts.m_verbs.map(o => ({ v: o.code, l: o.label }))]} />
        {(k === 'ladder' || k === 'foot' || k === 'distance_ladder') && (
          <Sel value={String(cur.m.distance)} onChange={v => set({ m: { ...cur.m, distance: parseFloat(v) } })}
            opts={[4, 12, 18, 30, 45].map(d => ({ v: String(d), l: '距離 ' + d + 'cm' }))} />)}
        {(k === 'hand' || k === 'hand_twist') && (
          <Sel value={String(cur.m.angle)} onChange={v => set({ m: { ...cur.m, angle: parseFloat(v) } })}
            opts={[{ v: '90', l: '≤90度' }, { v: '180', l: '≤180度' }]} />)}
        {(k === 'rotate' || k === 'rotation_by_diameter') && (
          <Sel value={String(cur.m.rev)} onChange={v => set({ m: { ...cur.m, rev: parseInt(v) } })}
            opts={[1, 2, 3].map(r => ({ v: String(r), l: r + '圈' }))} />)}
      </span>
    )
  }
  const xBlock = () => {
    const xo = opts.x.find(o => o.code === cur.x)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="X 製程時間：機器/製程造成的等待（熱壓、測試、掃描）；連續式需輸入秒數。" />
        <Sel value={cur.x} onChange={v => set({ x: v })} opts={opts.x.map(o => ({ v: o.code, l: o.label }))} />
        {xo?.mode === 'seconds' && (
          <input type="number" min={0} step={0.1}
            className="border-2 border-dashed border-slate-300 rounded w-20 px-1 text-sm bg-amber-50"
            value={cur.x_sec} onChange={e => set({ x_sec: parseFloat(e.target.value) || 0 })} placeholder="秒" />
        )}
      </span>
    )
  }
  const iBlock = () => (
    <span className="inline-flex items-center align-middle">
      <Hint tip="I 對準/檢查：定位對準或檢查確認動作的分級。" />
      <Sel value={cur.i} onChange={v => set({ i: v })} opts={opts.i.map(o => ({ v: o.code, l: o.label }))} />
    </span>
  )

  // ── [C] slot block definitions ─────────────────────────────────────────────
  const gmSlots: Array<{ key: SlotKey; label: string; param: string; isFilled: boolean; abbrev: string }> = [
    {
      key: 'a0', label: 'A (取得)', param: 'A',
      isFilled: aIsFilled(cur.a0),
      abbrev: aAbbrev(cur.a0, opts.a_bands),
    },
    {
      key: 'b1', label: 'B1', param: 'B',
      isFilled: !!cur.b1,
      abbrev: cur.b1 ? (opts.b.find(b => b.code === cur.b1)?.label.slice(0, 4) ?? 'B?') : '—',
    },
    {
      key: 'g', label: 'G (取得)', param: 'G',
      isFilled: !!cur.g,
      abbrev: cur.g ? (opts.g.find(g => g.code === cur.g)?.label.slice(0, 4) ?? 'G?') : '—',
    },
    {
      key: 'a3', label: 'A (放置)', param: 'A',
      isFilled: aIsFilled(cur.a3),
      abbrev: aAbbrev(cur.a3, opts.a_bands),
    },
    {
      key: 'b4', label: 'B4', param: 'B',
      isFilled: !!cur.b4,
      abbrev: cur.b4 ? (opts.b.find(b => b.code === cur.b4)?.label.slice(0, 4) ?? 'B?') : '—',
    },
    {
      key: 'p', label: 'P (放置)', param: 'P',
      isFilled: !!cur.p_base,
      abbrev: cur.p_base ? (opts.p_bases.find(p => p.code === cur.p_base)?.label.slice(0, 4) ?? 'P?') : '—',
    },
    {
      key: 'a6', label: 'A (返回)', param: 'A',
      isFilled: aIsFilled(cur.a6),
      abbrev: aAbbrev(cur.a6, opts.a_bands),
    },
  ]
  const cmSlots: Array<{ key: SlotKey; label: string; param: string; isFilled: boolean; abbrev: string }> = [
    {
      key: 'a0', label: 'A (取得)', param: 'A',
      isFilled: aIsFilled(cur.a0),
      abbrev: aAbbrev(cur.a0, opts.a_bands),
    },
    {
      key: 'b1', label: 'B1', param: 'B',
      isFilled: !!cur.b1,
      abbrev: cur.b1 ? (opts.b.find(b => b.code === cur.b1)?.label.slice(0, 4) ?? 'B?') : '—',
    },
    {
      key: 'g', label: 'G (取得)', param: 'G',
      isFilled: !!cur.g,
      abbrev: cur.g ? (opts.g.find(g => g.code === cur.g)?.label.slice(0, 4) ?? 'G?') : '—',
    },
    {
      key: 'm', label: 'M (動作)', param: 'M',
      isFilled: !!cur.m.verb,
      abbrev: cur.m.verb ? (opts.m_verbs.find(m => m.code === cur.m.verb)?.label.slice(0, 4) ?? 'M?') : '—',
    },
    {
      key: 'x', label: 'X (製程)', param: 'X',
      isFilled: cur.x !== 'x_none',
      abbrev: cur.x !== 'x_none' ? (opts.x.find(x => x.code === cur.x)?.label.slice(0, 4) ?? 'X?') : '—',
    },
    {
      key: 'i', label: 'I (對準)', param: 'I',
      isFilled: cur.i !== 'i_none',
      abbrev: cur.i !== 'i_none' ? (opts.i.find(i => i.code === cur.i)?.label.slice(0, 4) ?? 'I?') : '—',
    },
    {
      key: 'a6', label: 'A (返回)', param: 'A',
      isFilled: aIsFilled(cur.a6),
      abbrev: aAbbrev(cur.a6, opts.a_bands),
    },
  ]
  const currentSlots = gm ? gmSlots : cmSlots

  // Modal label per slot
  const slotModalLabels: Record<SlotKey, string> = {
    a0: 'A 移動 — 取得段',
    b1: 'B 身體動作 — 取得段',
    g: 'G 取得',
    a3: 'A 移動 — 放置段',
    b4: 'B 身體動作 — 放置段',
    p: 'P 放置',
    m: 'M 控制移動',
    x: 'X 製程時間',
    i: 'I 對準/檢查',
    a6: 'A 移動 — 返回段',
  }

  // ── [D] DnD handlers ───────────────────────────────────────────────────────
  function onDragStart(idx: number, e: React.DragEvent) {
    setDragIdx(idx)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(idx))
  }
  function onDragOver(idx: number, e: React.DragEvent) {
    e.preventDefault()
    setDragOverIdx(idx)
  }
  function onDrop(idx: number, e: React.DragEvent) {
    e.preventDefault()
    if (dragIdx !== null && dragIdx !== idx) {
      const arr = [...rows]
      const [item] = arr.splice(dragIdx, 1)
      arr.splice(idx, 0, item)
      setRows(arr)
    }
    setDragIdx(null)
    setDragOverIdx(null)
  }
  function onDragEnd() { setDragIdx(null); setDragOverIdx(null) }

  // ── helper: update individual row ──────────────────────────────────────────
  function updateRow(id: string, patch: Partial<Row>) {
    setRows(rows.map(r => r.id === id ? { ...r, ...patch } : r))
  }

  // ── [D-2] toggle row selection ─────────────────────────────────────────────
  function toggleSelect(id: string) {
    const next = new Set(selectedRowIds)
    if (next.has(id)) next.delete(id); else next.add(id)
    setSelectedRowIds(next)
  }

  // ── [E] WI group handlers ──────────────────────────────────────────────────
  function addToWi() {
    if (selectedRowIds.size === 0 || !wiNameInput.trim()) return
    setWiGroups(g => [...g, { id: crypto.randomUUID(), name: wiNameInput.trim(), rowIds: [...selectedRowIds] }])
    setSelectedRowIds(new Set())
    setWiNameInput('')
  }
  function toggleWiExpand(id: string) {
    const n = new Set(expandedWiIds)
    if (n.has(id)) n.delete(id); else n.add(id)
    setExpandedWiIds(n)
  }
  function selectWiGroup(group: WiGroup) {
    setHighlightedRowIds(new Set(group.rowIds))
  }
  function deleteWiGroup(id: string) {
    setWiGroups(g => g.filter(w => w.id !== id))
    setHighlightedRowIds(new Set())
  }
  function wiGroupTmu(group: WiGroup): number {
    // ADR-020：SIMO 標記列（simoGroup 非空）貢獻 0，其餘 Σ(tmu × freq)
    return rows.filter(r => group.rowIds.includes(r.id) && !(r.simoGroup || '').trim())
      .reduce((sum, r) => sum + (r.tmu * (r.freq || 1)), 0)
  }

  // ── [F] NL draft ───────────────────────────────────────────────────────────
  async function runNlDraft() {
    const text = nlText.trim()
    if (!text) return
    setNlLoading(true)
    setNlError('')
    try {
      const res = await apiPost<NlDraftRes>('/api/v2/worksheets/nl-draft', {
        text,
        rule_set_code: opts?.code,
      })
      const patch = nlDraftPatch(res)
      if (Object.keys(patch).length > 0) {
        setCur(c => ({ ...c, ...patch }))
      }
    } catch (e) {
      const msg = (e as Error).message
      if (msg.includes('501') || msg.includes('Not Implemented') || msg.includes('404')) {
        setNlError('NL Draft 功能需要後端支援')
      } else {
        setNlError('預填失敗：' + msg)
      }
    } finally {
      setNlLoading(false)
    }
  }

  // ── existing add/save functions ────────────────────────────────────────────
  function add() {
    if (tmu == null) return
    addRow({
      id: crypto.randomUUID(), seq: cur.seq, handCode: cur.handCode, freq: cur.freq, simoGroup: cur.simoGroup,
      nv: { ...cur.nv }, narr: shortNarr(cur, label, vname), tmu, seconds: tmu * TMU_SEC, payload,
    } as Row)
  }

  async function saveAsTemplate() {
    if (!opts) return
    const name = window.prompt('範本名稱（中文）？'); if (!name) return
    const kw = window.prompt('關鍵字（逗號分隔，供匯入比對；可留空）：', '') || ''
    try {
      await apiPost('/api/v2/motion-templates', {
        name_zh: name, seq_kind: cur.seq,
        keywords: kw.split(/[,，]/).map(s => s.trim()).filter(Boolean), cycle_template: buildPayload(cur, opts.code),
      })
      qc.invalidateQueries({ queryKey: ['templates'] })
      setSaveMsg('✓ 已存為草稿範本：' + name)
    } catch (e) { setSaveMsg('存範本失敗：' + (e as Error).message) }
  }

  async function doSave() {
    setSaveMsg('儲存中…')
    const lv = useLevelStore.getState()
    const d = derive(rows, lv.levelMap, lv.groupMeta)
    const fallbackObj = vocab.find(v => v.kind === 'object')?.id
    const body = {
      rows: rows.map((r, i) => {
        const e = d[i] || {}
        return {
          id: r.id, seq_no: i + 1, hand: r.handCode,
          object_vocab_id: r.nv.obj || fallbackObj,
          from_vocab_id: r.nv.from || null, to_vocab_id: r.nv.to || null,
          frequency: r.freq, simo_group_id: r.simoGroup || null, narrative: r.narr, cycle: r.payload,
          level: {
            coefficient: e.coefficient ?? 1, ascription: e.ascription ?? 'main', level: e.level ?? String(i + 1),
            countersignature: e.countersignature ?? null, parent_countersignature: e.parent_countersignature ?? null,
            order: e.order ?? null, number: e.number ?? null, number_count: e.number_count ?? null,
            machine_count: 1, manpower: 1,
          },
        }
      }),
    }
    try {
      const res = await save.mutateAsync(body)
      qc.invalidateQueries({ queryKey: ['wi-preview'] })
      qc.invalidateQueries({ queryKey: ['versions'] })
      setSaveMsg(`✓ 已儲存：${res.rows.length} 列，合計 ${res.total_tmu} TMU（≈ ${(res.total_tmu * TMU_SEC).toFixed(2)} 秒）`)
    } catch (e) { setSaveMsg('⚠️ 儲存失敗：' + (e as Error).message) }
  }

  const total = totalTmu()

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">

      {/* ═══ Editor section ═══ */}
      <div className="bg-white rounded-xl border p-4 space-y-3">

        {/* [F] NL Draft bar */}
        <div className="flex flex-wrap items-start gap-2 pb-2 border-b border-slate-100">
          <span className="text-xs font-semibold text-slate-500 mt-2 shrink-0">AI 預填</span>
          <textarea
            rows={1}
            className="flex-1 min-w-0 border rounded px-2 py-1.5 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
            placeholder="輸入口語描述，AI 自動填入動作參數…"
            value={nlText}
            onChange={e => setNlText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!nlLoading) runNlDraft() } }}
            disabled={nlLoading}
          />
          <button
            onClick={runNlDraft}
            disabled={nlLoading || !nlText.trim()}
            className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded disabled:opacity-40 shrink-0"
          >
            {nlLoading ? '分析中…' : '填入'}
          </button>
          {nlError && <span className="text-xs text-red-500 w-full mt-0.5">{nlError}</span>}
        </div>

        {/* Sequence type + hand */}
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">編輯一條工序</h2>
          <label className="text-sm flex items-center gap-1">
            <input type="radio" checked={gm} onChange={() => set({ seq: 'GM' })} /> 一般移動(取放)
          </label>
          <label className="text-sm flex items-center gap-1">
            <input type="radio" checked={!gm} onChange={() => set({ seq: 'CM' })} /> 控制移動(推拉鎖)
          </label>
          <div className="flex items-center gap-1 ml-2">
            <span className="text-sm text-slate-500">手</span>
            <Sel value={cur.handCode} onChange={v => set({ handCode: v })} opts={HANDS}
              cls="border rounded px-1 py-0.5 text-sm" />
          </div>
        </div>

        {/* Context fields (vocabulary) */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">從</span>{mkVocab('from', 'from', '—來源—')}
          <span className="text-slate-500">取得</span>{mkVocab('object', 'obj', '—物件—')}
          {gm && <><span className="text-slate-500">放至</span>{mkVocab('to', 'to', '—目的地—')}</>}
          {!gm && <><span className="text-slate-500">在</span>{mkVocab('to', 'to', '—地點—')}</>}
        </div>

        {/* [C] Visual slot blocks */}
        <div className="flex flex-wrap gap-2 py-1">
          {currentSlots.map(slot => {
            const clr = SLOT_COLORS[slot.param] ?? SLOT_COLORS['A']
            const cls = `flex flex-col items-center justify-center min-w-[72px] px-2 py-2 rounded-lg border-2
              cursor-pointer transition-all select-none hover:opacity-80 active:scale-95
              ${slot.isFilled ? clr.filled : clr.empty}`
            return (
              <button key={slot.key} className={cls} onClick={() => setActiveSlot(slot.key)}
                title={slotModalLabels[slot.key]}>
                <span className="text-[10px] font-medium opacity-70 leading-none mb-1">{slot.label}</span>
                <span className="font-bold text-sm leading-none">{slot.abbrev}</span>
                <span className={`w-2 h-2 rounded-full mt-1.5 ${slot.isFilled ? 'bg-green-400' : 'bg-gray-300'}`} />
              </button>
            )
          })}
        </div>

        {/* Tech line + TMU + controls */}
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t text-sm">
          <span className="text-slate-500">次數</span>
          <input type="number" min={1} className="border rounded w-16 px-1 py-0.5"
            value={cur.freq} onChange={e => set({ freq: parseInt(e.target.value) || 1 })} />
          <span className="text-slate-500">SIMO(同動群)</span>
          <input className="border rounded w-20 px-1 py-0.5" value={cur.simoGroup}
            onChange={e => set({ simoGroup: e.target.value })} placeholder="可空" />
          <span className="font-mono text-slate-500 text-xs">{tech || '—'}</span>
          <span className="ml-auto">本列 <b className="text-sky-700 text-lg">{tmu ?? '—'}</b> TMU ≈ {tmu != null ? (tmu * TMU_SEC).toFixed(2) : '—'} 秒</span>
          {editable && <button onClick={saveAsTemplate} className="px-2 py-1.5 border rounded">＋存為範本</button>}
          <button disabled={!editable || tmu == null} onClick={add}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg disabled:opacity-40">＋ 加入工時表</button>
        </div>
        {!editable && <p className="text-xs text-amber-600">目前身分無編輯權限（需 IE 以上）。</p>}
      </div>

      {/* ═══ Table section ═══ */}
      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold">工時表</h2>
          <div className="text-sm">合計 <b className="text-emerald-600 text-lg">{total}</b> TMU ≈ <b className="text-emerald-600">{(total * TMU_SEC).toFixed(2)}</b> 秒</div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-100 text-left">
                {/* D-1 drag handle */}
                <th className="p-1 w-6 text-center"></th>
                {/* D-2 checkbox */}
                <th className="p-1 w-7 text-center">
                  <input type="checkbox"
                    checked={rows.length > 0 && rows.every(r => selectedRowIds.has(r.id))}
                    onChange={e => {
                      if (e.target.checked) setSelectedRowIds(new Set(rows.map(r => r.id)))
                      else setSelectedRowIds(new Set())
                    }} />
                </th>
                <th className="p-1">#</th>
                <th className="p-1">手</th>
                <th className="p-1">敘述</th>
                <th className="p-1">Base TMU</th>
                {/* D-3 freq input */}
                <th className="p-1">頻率</th>
                <th className="p-1">Eff TMU</th>
                <th className="p-1">CT(秒)</th>
                {/* D-4 simo checkbox */}
                <th className="p-1">SIMO</th>
                {/* D-5 納入TMU */}
                <th className="p-1">納入 TMU</th>
                <th className="p-1"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const effTmu = r.tmu != null ? r.tmu * (r.freq || 1) : null
                const ctSec = effTmu != null ? (effTmu * TMU_SEC).toFixed(2) : '—'
                const isSimo = (r.simoGroup || '').trim() !== ''
                const isDragging = dragIdx === i
                const isOver = dragOverIdx === i
                const isSelected = selectedRowIds.has(r.id)
                const isHighlighted = highlightedRowIds.has(r.id)
                const rowCls = [
                  'border-t',
                  isDragging ? 'opacity-40' : '',
                  isOver ? 'border-t-2 border-t-sky-400' : '',
                  isSelected ? 'bg-blue-50' : '',
                  isHighlighted ? 'bg-amber-50' : '',
                ].filter(Boolean).join(' ')
                return (
                  <tr key={r.id} className={rowCls}
                    onDragOver={e => onDragOver(i, e)}
                    onDrop={e => onDrop(i, e)}>
                    {/* D-1 drag handle */}
                    <td className="p-1 text-center">
                      <span
                        className="cursor-grab text-slate-400 hover:text-slate-600 select-none text-base leading-none"
                        draggable
                        onDragStart={e => onDragStart(i, e)}
                        onDragEnd={onDragEnd}
                        title="拖拉排序"
                      >⠿</span>
                    </td>
                    {/* D-2 checkbox */}
                    <td className="p-1 text-center">
                      <input type="checkbox" checked={isSelected}
                        onChange={() => toggleSelect(r.id)} />
                    </td>
                    <td className="p-1">{i + 1}</td>
                    <td className="p-1">{r.handCode}</td>
                    <td className="p-1 max-w-xs truncate">{r.narr}</td>
                    <td className="p-1"><b>{r.tmu}</b></td>
                    {/* D-3 freq input */}
                    <td className="p-1">
                      <input type="number" min={1}
                        className="border rounded w-14 px-1 py-0.5 text-center"
                        value={r.freq}
                        onChange={e => {
                          const v = parseInt(e.target.value) || 1
                          updateRow(r.id, { freq: v, seconds: r.tmu * v * TMU_SEC })
                        }}
                        disabled={!editable} />
                    </td>
                    <td className="p-1"><b className="text-blue-700">{effTmu ?? '—'}</b></td>
                    <td className="p-1">{ctSec}</td>
                    {/* D-4 simo checkbox */}
                    <td className="p-1 text-center">
                      <input type="checkbox" checked={isSimo}
                        disabled={!editable}
                        onChange={e => updateRow(r.id, { simoGroup: e.target.checked ? 'simo-1' : '' })}
                        title={r.simoGroup || undefined} />
                    </td>
                    {/* D-5 納入TMU */}
                    <td className="p-1 text-right">
                      {isSimo
                        ? <span className="line-through text-slate-400">0</span>
                        : <span>{effTmu ?? '—'}</span>
                      }
                    </td>
                    <td className="p-1">
                      {editable && (
                        <button className="text-red-600 underline" onClick={() => {
                          delRow(r.id)
                          const n = new Set(selectedRowIds); n.delete(r.id); setSelectedRowIds(n)
                          const h = new Set(highlightedRowIds); h.delete(r.id); setHighlightedRowIds(h)
                        }}>刪</button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 && (
                <tr><td colSpan={12} className="p-3 text-slate-400">尚無列。</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* [E-1] Floating action bar */}
        {selectedRowIds.size > 0 && (
          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg flex flex-wrap items-center gap-3">
            <span className="text-sm text-blue-700 font-medium">已選 {selectedRowIds.size} 個動作</span>
            <span className="text-sm text-slate-500">WI 名稱：</span>
            <input
              className="border rounded px-2 py-1 text-sm flex-1 min-w-0"
              placeholder="輸入 WI 名稱…"
              value={wiNameInput}
              onChange={e => setWiNameInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addToWi() }}
            />
            <button
              onClick={addToWi}
              disabled={!wiNameInput.trim()}
              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded disabled:opacity-40 shrink-0"
            >加入 WI</button>
            <button onClick={() => setSelectedRowIds(new Set())}
              className="text-xs text-slate-500 underline shrink-0">取消選擇</button>
          </div>
        )}

        <div className="flex gap-2 mt-3 items-center">
          <button disabled={!editable || !rows.length || save.isPending} onClick={doSave}
            className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg disabled:opacity-40">儲存</button>
          <span className="text-xs text-slate-500">{saveMsg}</span>
        </div>
      </div>

      {/* ═══ [E-2] WI Outline ═══ */}
      {wiGroups.length > 0 && (
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">WI 大綱 · {wiGroups.length} 筆 WI</h2>
          </div>
          <div className="space-y-2">
            {wiGroups.map(group => {
              const grpTmu = wiGroupTmu(group)
              const isExpanded = expandedWiIds.has(group.id)
              const groupRows = rows.filter(r => group.rowIds.includes(r.id))
              return (
                <div key={group.id}
                  className="border rounded-lg overflow-hidden hover:shadow-sm transition-shadow">
                  {/* WI group header */}
                  <div
                    className="flex items-center gap-3 px-3 py-2 bg-slate-50 cursor-pointer select-none"
                    onClick={() => { selectWiGroup(group); toggleWiExpand(group.id) }}
                  >
                    <span className="text-slate-400 text-lg leading-none">{isExpanded ? '▾' : '▸'}</span>
                    <span className="font-medium text-sm flex-1 truncate">{group.name}</span>
                    <span className="text-xs text-slate-500 shrink-0">{group.rowIds.length} 個動作</span>
                    <span className="text-sm shrink-0">
                      <b className="text-blue-700">{grpTmu.toFixed(1)}</b>
                      <span className="text-slate-400"> TMU ≈ </span>
                      <b className="text-emerald-600">{(grpTmu * TMU_SEC).toFixed(3)}</b>
                      <span className="text-slate-400"> 秒</span>
                    </span>
                    <button
                      onClick={e => { e.stopPropagation(); deleteWiGroup(group.id) }}
                      className="text-red-400 hover:text-red-600 text-xs ml-2 shrink-0"
                    >刪除</button>
                  </div>
                  {/* Expanded: list action rows */}
                  {isExpanded && (
                    <div className="divide-y">
                      {groupRows.length === 0 && (
                        <div className="px-3 py-2 text-xs text-slate-400">（所有動作已被刪除）</div>
                      )}
                      {groupRows.map((r, idx) => (
                        <div key={r.id} className="flex items-center gap-3 px-4 py-1.5 text-sm hover:bg-slate-50">
                          <span className="text-xs text-slate-400 w-5 shrink-0">{idx + 1}.</span>
                          <span className="text-xs text-slate-500 shrink-0">{r.handCode}</span>
                          <span className="flex-1 truncate text-xs">{r.narr}</span>
                          <span className="text-xs text-blue-600 shrink-0">{r.tmu} TMU</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ═══ [C] Slot Modal ═══ */}
      {activeSlot && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setActiveSlot(null)}
        >
          <div
            className="bg-white rounded-xl border shadow-2xl p-5 max-w-lg w-full mx-4 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-base">{slotModalLabels[activeSlot]}</h3>
              <button onClick={() => setActiveSlot(null)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none">✕</button>
            </div>
            <div className="py-1">
              {activeSlot === 'a0' && aBlock(cur.a0, s => set({ a0: s }))}
              {activeSlot === 'b1' && bBlock('b1')}
              {activeSlot === 'g' && gBlock()}
              {activeSlot === 'a3' && aBlock(cur.a3, s => set({ a3: s }))}
              {activeSlot === 'b4' && bBlock('b4')}
              {activeSlot === 'p' && pBlock()}
              {activeSlot === 'm' && mVerbBlock()}
              {activeSlot === 'x' && xBlock()}
              {activeSlot === 'i' && iBlock()}
              {activeSlot === 'a6' && aBlock(cur.a6, s => set({ a6: s }))}
            </div>
            {/* Live TMU preview in modal */}
            <div className="text-xs text-slate-500 border-t pt-2">
              預覽 TMU: <b className="text-sky-700">{tmu ?? '計算中…'}</b>
              {tech && <span className="ml-2 font-mono text-slate-400">{tech}</span>}
            </div>
            <div className="flex justify-end">
              <button onClick={() => setActiveSlot(null)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">確認</button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
