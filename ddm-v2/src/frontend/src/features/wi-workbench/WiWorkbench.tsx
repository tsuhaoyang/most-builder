import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRuleSetOptions, useVocab, useTemplates, useCalculate, useSaveWorksheet, useWorksheet, type RuleSetOptions } from './api'
import { useWiStore, type Row } from './store'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { useWorkspace } from '../../shared/workspace'
import { TMU_SEC } from '../../shared/config'
import { defaultCycle, buildPayload, aBandOpts, shortNarr, type CycleState, type ASlot } from './cycle'
import { useLevelStore } from '../level-system/store'
import { derive, type LevelCell, type GroupMeta } from '../level-system/logic'

const HANDS = [{ id: 'RH', name: '右手' }, { id: 'LH', name: '左手' }, { id: 'BH', name: '雙手' }]

export function WiWorkbench() {
  const { data: me } = useMe()
  const { data: opts } = useRuleSetOptions()
  const { data: vocab = [] } = useVocab()
  const { data: templates = [] } = useTemplates()
  const calc = useCalculate()
  const activeWs = useWorkspace(s => s.activeWs)
  const save = useSaveWorksheet(activeWs)
  const qc = useQueryClient()
  const { data: wsData } = useWorksheet(activeWs)
  const { rows, addRow, delRow, setRows, totalTmu } = useWiStore()

  // 載入/切換版本：以後端 worksheet 還原 WI 列 + Level（取代本地）
  useEffect(() => {
    if (!wsData) return
    setRows(wsData.rows.map(r => ({
      id: r.wi_row_id,
      seq: (r.cycle?.seq_kind === 'CM' ? 'CM' : 'GM') as 'GM' | 'CM',
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

  const [mode, setMode] = useState<'quick' | 'precise'>('quick')
  const [cur, setCur] = useState<CycleState>(defaultCycle())
  const [qHand, setQHand] = useState('RH'); const [qTpl, setQTpl] = useState(''); const [qObj, setQObj] = useState(''); const [qFreq, setQFreq] = useState(1)
  const [tmu, setTmu] = useState<number | null>(null); const [tech, setTech] = useState(''); const [saveMsg, setSaveMsg] = useState('')

  const editable = canEdit(me)
  const objs = vocab.filter(v => v.kind === 'object' || v.kind === 'component')
  const froms = vocab.filter(v => v.kind === 'from'); const tos = vocab.filter(v => v.kind === 'to')
  const std = templates.filter(t => t.status === 'standard')
  const tpl = std.find(t => t.id === qTpl)

  // 目前要送計算的 payload（精確：buildPayload；快速：範本 cycle_template）
  const payload = useMemo(() => {
    if (!opts) return null
    return mode === 'precise' ? buildPayload(cur, opts.code) : (tpl?.cycle_template ?? null)
  }, [mode, cur, tpl, opts])

  useEffect(() => {
    if (!payload) { setTmu(null); setTech(''); return }
    const id = setTimeout(() => calc.mutate(payload, { onSuccess: r => { setTmu(r.total_tmu); setTech(r.tech_line) }, onError: () => { setTmu(null); setTech('') } }), 250)
    return () => clearTimeout(id)
  }, [JSON.stringify(payload)]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!opts) return <div className="bg-white rounded-xl border p-6 text-slate-500">載入 rule-set…</div>
  const label = (kind: string, code: string) => {
    const m: Record<string, { code: string; label: string }[]> = { g: opts.g, p_base: opts.p_bases, m_verb: opts.m_verbs }
    return m[kind]?.find(o => o.code === code)?.label ?? ''
  }
  const vname = (kind: string, id: string) => vocab.find(v => v.id === id)?.name_zh ?? ''

  function add() {
    if (tmu == null) return
    if (mode === 'precise') {
      addRow(mkRow(cur.seq, cur.handCode, cur.freq, cur.simoGroup, cur.nv, shortNarr(cur, label, vname), tmu, payload))
    } else {
      if (!tpl) return
      const nv = { obj: qObj, from: '', to: '' }
      const narr = `${HANDS.find(h => h.id === qHand)?.name} ${tpl.name_zh}「${vname('object', qObj)}」`
      addRow(mkRow(tpl.seq_kind as 'GM' | 'CM', qHand, qFreq, '', nv, narr, tmu, payload))
    }
  }
  function mkRow(seq: 'GM' | 'CM', hand: string, freq: number, simo: string, nv: Row['nv'], narr: string, t: number, pl: unknown): Row {
    return { id: crypto.randomUUID(), seq, handCode: hand, freq, simoGroup: simo, nv, narr, tmu: t, seconds: t * TMU_SEC, payload: pl }
  }

  async function doSave() {
    setSaveMsg('儲存中…')
    const lv = useLevelStore.getState()
    const d = derive(rows, lv.levelMap, lv.groupMeta)
    const fallbackObj = objs[0]?.id
    const body = {
      rows: rows.map((r, i) => {
        const e = d[i] || {}
        return {
          id: r.id, seq_no: i + 1, hand: r.handCode,
          object_vocab_id: r.nv.obj || fallbackObj,
          from_vocab_id: r.nv.from || null, to_vocab_id: r.nv.to || null,
          frequency: r.freq, simo_group_id: r.simoGroup || null, narrative: r.narr,
          cycle: r.payload,
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
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center gap-3 mb-2">
          <h2 className="font-semibold">編輯一條工序</h2>
          <div className="ml-auto flex gap-1 text-sm">
            <button className={`px-2 py-1 rounded border ${mode === 'quick' ? 'bg-slate-900 text-white' : ''}`} onClick={() => setMode('quick')}>⚡ 快速範本</button>
            <button className={`px-2 py-1 rounded border ${mode === 'precise' ? 'bg-slate-900 text-white' : ''}`} onClick={() => setMode('precise')}>🔧 精確調整</button>
          </div>
        </div>

        {mode === 'quick'
          ? <div className="flex flex-wrap items-end gap-2 text-sm">
              <label>手 <Sel value={qHand} onChange={setQHand} opts={HANDS.map(h => ({ v: h.id, l: h.name }))} /></label>
              <label>動作 <Sel value={qTpl} onChange={setQTpl} opts={[{ v: '', l: '— 選動作 —' }, ...std.map(t => ({ v: t.id, l: `[${t.seq_kind}] ${t.name_zh}` }))]} /></label>
              <label>物件 <Sel value={qObj} onChange={setQObj} opts={[{ v: '', l: '—' }, ...objs.map(o => ({ v: o.id, l: o.name_zh }))]} /></label>
              <label>次數 <input type="number" min={1} className="border rounded w-16 px-1 py-0.5" value={qFreq} onChange={e => setQFreq(parseInt(e.target.value) || 1)} /></label>
            </div>
          : <PreciseEditor cur={cur} setCur={setCur} opts={opts} objs={objs} froms={froms} tos={tos} />}

        <div className="flex flex-wrap items-center gap-3 mt-3 pt-3 border-t text-sm">
          <span className="font-mono text-slate-600">{tech || '—'}</span>
          <span className="ml-auto">本列 <b className="text-sky-700 text-lg">{tmu ?? '—'}</b> TMU</span>
          <button disabled={!editable || tmu == null} onClick={add} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg disabled:opacity-40">＋ 加入工時表</button>
        </div>
        {!editable && <p className="text-xs text-amber-600 mt-2">目前身分無編輯權限（需 IE 以上）。</p>}
      </div>

      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold">工時表</h2>
          <div className="text-sm">合計 <b className="text-emerald-600 text-lg">{total}</b> TMU ≈ <b className="text-emerald-600">{(total * TMU_SEC).toFixed(2)}</b> 秒</div>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-100 text-left"><th className="p-1">#</th><th className="p-1">手</th><th className="p-1">敘述</th><th className="p-1">TMU</th><th className="p-1">次數</th><th className="p-1">SIMO</th><th className="p-1"></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id} className="border-t">
                <td className="p-1">{i + 1}</td><td className="p-1">{r.handCode}</td><td className="p-1">{r.narr}</td>
                <td className="p-1"><b>{r.tmu}</b></td><td className="p-1">{r.freq}</td><td className="p-1">{r.simoGroup}</td>
                <td className="p-1">{editable && <button className="text-red-600 underline" onClick={() => delRow(r.id)}>刪</button>}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={7} className="p-3 text-slate-400">尚無列。</td></tr>}
          </tbody>
        </table>
        <div className="flex gap-2 mt-3 items-center">
          <button disabled={!editable || !rows.length || save.isPending} onClick={doSave} className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg disabled:opacity-40">儲存</button>
          <span className="text-xs text-slate-500">{saveMsg}</span>
        </div>
      </div>
    </div>
  )
}

function Sel({ value, onChange, opts }: { value: string; onChange: (v: string) => void; opts: { v: string; l: string }[] }) {
  return <select className="border rounded px-1 py-0.5" value={value} onChange={e => onChange(e.target.value)}>
    {opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
  </select>
}

function ASlotEditor({ slot, set, opts }: { slot: ASlot; set: (s: ASlot) => void; opts: RuleSetOptions }) {
  const comp = (c: 'reach' | 'twist' | 'foot') => (
    <select className="border rounded px-1 text-xs bg-amber-50" value={slot[c]} onChange={e => set({ ...slot, [c]: parseFloat(e.target.value) || 0 })}>
      {aBandOpts(opts.a_bands[c], c).map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
  return <span className="inline-flex gap-1 items-center px-1 bg-blue-50 border border-blue-200 rounded">{comp('reach')}{comp('twist')}{comp('foot')}</span>
}

function PreciseEditor({ cur, setCur, opts, objs, froms, tos }: {
  cur: CycleState; setCur: (c: CycleState) => void; opts: RuleSetOptions
  objs: { id: string; name_zh: string }[]; froms: { id: string; name_zh: string }[]; tos: { id: string; name_zh: string }[]
}) {
  const gm = cur.seq === 'GM'
  const set = (patch: Partial<CycleState>) => setCur({ ...cur, ...patch })
  const g = opts.g.find(x => x.code === cur.g)
  const mv = opts.m_verbs.find(x => x.code === cur.m.verb)
  const voc = (arr: { id: string; name_zh: string }[]) => [{ v: '', l: '—' }, ...arr.map(o => ({ v: o.id, l: o.name_zh }))]
  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1"><input type="radio" checked={gm} onChange={() => set({ seq: 'GM' })} /> GM 一般移動</label>
        <label className="flex items-center gap-1"><input type="radio" checked={!gm} onChange={() => set({ seq: 'CM' })} /> CM 控制移動</label>
        <label>手 <Sel value={cur.handCode} onChange={v => set({ handCode: v })} opts={HANDS.map(h => ({ v: h.id, l: h.name }))} /></label>
        <label>物件 <Sel value={cur.nv.obj} onChange={v => set({ nv: { ...cur.nv, obj: v } })} opts={voc(objs)} /></label>
        <label>從 <Sel value={cur.nv.from} onChange={v => set({ nv: { ...cur.nv, from: v } })} opts={voc(froms)} /></label>
        <label>到 <Sel value={cur.nv.to} onChange={v => set({ nv: { ...cur.nv, to: v } })} opts={voc(tos)} /></label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">A0</span><ASlotEditor slot={cur.a0} set={s => set({ a0: s })} opts={opts} />
        <span className="text-xs text-slate-500">B</span>
        <Sel value={cur.b1 ?? ''} onChange={v => set({ b1: v || null })} opts={[{ v: '', l: '身體:無' }, ...opts.b.filter(b => b.code !== 'b_none').map(b => ({ v: b.code, l: b.label }))]} />
        <span className="text-xs text-slate-500">G</span>
        <Sel value={cur.g} onChange={v => set({ g: v, gMod: {} })} opts={[{ v: '', l: '—取得—' }, ...opts.g.map(o => ({ v: o.code, l: o.label }))]} />
        {g?.requires_modifier && g.modifier_key &&
          <label className="text-xs"><input type="checkbox" checked={!!cur.gMod[g.modifier_key]} onChange={e => set({ gMod: { ...cur.gMod, [g.modifier_key!]: e.target.checked } })} /> {g.modifier_key}</label>}
      </div>
      {gm
        ? <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">A3</span><ASlotEditor slot={cur.a3} set={s => set({ a3: s })} opts={opts} />
            <span className="text-xs text-slate-500">B</span>
            <Sel value={cur.b4 ?? ''} onChange={v => set({ b4: v || null })} opts={[{ v: '', l: '身體:無' }, ...opts.b.filter(b => b.code !== 'b_none').map(b => ({ v: b.code, l: b.label }))]} />
            <span className="text-xs text-slate-500">P</span>
            <Sel value={cur.p_base} onChange={v => set({ p_base: v })} opts={[{ v: '', l: '—放置—' }, ...opts.p_bases.map(o => ({ v: o.code, l: o.label }))]} />
            {[0, 1].map(i => (
              <Sel key={i} value={cur.p_addons[i] ?? ''} onChange={v => { const a = cur.p_addons.filter((_, j) => j !== i); if (v) a.splice(i, 0, v); set({ p_addons: a.slice(0, 2) }) }}
                opts={[{ v: '', l: '—附加—' }, ...opts.p_addons.map(o => ({ v: o.code, l: o.label }))]} />
            ))}
            {cur.p_addons.some(c => opts.p_addons.find(a => a.code === c)?.needs_precision) &&
              <label className="text-xs"><input type="checkbox" checked={cur.precision} onChange={e => set({ precision: e.target.checked })} /> 精度&lt;4mm</label>}
          </div>
        : <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">M</span>
            <Sel value={cur.m.verb} onChange={v => set({ m: { ...cur.m, verb: v } })} opts={[{ v: '', l: '—動詞—' }, ...opts.m_verbs.map(o => ({ v: o.code, l: o.label }))]} />
            {mv && (mv.pricing_kind === 'distance_ladder' || mv.pricing_kind === 'ladder' || mv.pricing_kind === 'foot') &&
              <Sel value={String(cur.m.distance)} onChange={v => set({ m: { ...cur.m, distance: parseFloat(v) } })} opts={[4, 12, 18, 30, 45].map(d => ({ v: String(d), l: d + 'cm' }))} />}
            {mv && (mv.pricing_kind === 'hand_twist' || mv.pricing_kind === 'hand') &&
              <Sel value={String(cur.m.angle)} onChange={v => set({ m: { ...cur.m, angle: parseFloat(v) } })} opts={[{ v: '90', l: '≤90度' }, { v: '180', l: '≤180度' }]} />}
            {mv && (mv.pricing_kind === 'rotation_by_diameter' || mv.pricing_kind === 'rotate') &&
              <Sel value={String(cur.m.rev)} onChange={v => set({ m: { ...cur.m, rev: parseInt(v) } })} opts={[1, 2, 3].map(r => ({ v: String(r), l: r + '圈' }))} />}
            <span className="text-xs text-slate-500">X</span>
            <Sel value={cur.x} onChange={v => set({ x: v })} opts={opts.x.map(o => ({ v: o.code, l: o.label }))} />
            {opts.x.find(o => o.code === cur.x)?.mode === 'seconds' &&
              <input type="number" min={0} step={0.1} className="border rounded w-20 px-1 text-xs" value={cur.x_sec} onChange={e => set({ x_sec: parseFloat(e.target.value) || 0 })} placeholder="秒" />}
            <span className="text-xs text-slate-500">I</span>
            <Sel value={cur.i} onChange={v => set({ i: v })} opts={opts.i.map(o => ({ v: o.code, l: o.label }))} />
          </div>}
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">A6(返回)</span><ASlotEditor slot={cur.a6} set={s => set({ a6: s })} opts={opts} />
      </div>
    </div>
  )
}
