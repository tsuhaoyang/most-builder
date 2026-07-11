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
import { defaultCycle, buildPayload, aBandOpts, shortNarr, type CycleState, type ASlot } from './cycle'
import { useLevelStore } from '../level-system/store'
import { derive, type LevelCell, type GroupMeta } from '../level-system/logic'

const HANDS = [{ v: 'RH', l: '右手' }, { v: 'LH', l: '左手' }, { v: 'BH', l: '雙手' }]

// 小型原生 select（技術格用；琥珀底表示「可調整的數值格」）
function Sel({ value, onChange, opts, cls }: { value: string; onChange: (v: string) => void; opts: { v: string; l: string }[]; cls?: string }) {
  return (
    <select className={cls ?? 'border-2 border-dashed border-slate-300 rounded px-1 py-0.5 text-sm bg-amber-50'}
      value={value} onChange={e => onChange(e.target.value)}>
      {opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
}

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

  const [cur, setCur] = useState<CycleState>(defaultCycle())
  const [tmu, setTmu] = useState<number | null>(null)
  const [tech, setTech] = useState('')
  const [saveMsg, setSaveMsg] = useState('')
  const editable = canEdit(me)

  // 載入/切換版本：以後端 worksheet 還原 WI 列 + Level
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

  // 後端權威計算（debounce）：cur → buildPayload
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

  // ── helpers ──
  const set = (patch: Partial<CycleState>) => setCur(c => ({ ...c, ...patch }))
  const gm = cur.seq === 'GM'
  const vopts = (kind: string) => vocab.filter(v => v.kind === kind).map(v => ({ v: v.id, l: v.name_zh }))
  const vname = (_kind: string, id: string) => vocab.find(v => v.id === id)?.name_zh ?? ''
  const label = (kind: string, code: string) => {
    const m: Record<string, { code: string; label: string }[]> = { g: opts.g, p_base: opts.p_bases, m_verb: opts.m_verbs }
    return m[kind]?.find(o => o.code === code)?.label ?? ''
  }
  // 詞彙填空（可搜尋 + ＋新增→寫回主數據→即時連動）
  const mkVocab = (kind: string, nvKey: 'obj' | 'from' | 'to', ph: string) => (
    <ComboBox options={vopts(kind)} value={cur.nv[nvKey]} placeholder={ph}
      onPick={id => set({ nv: { ...cur.nv, [nvKey]: id } })}
      onCreate={editable ? (name) => createVocab.mutate({ kind, name_zh: name } as VocabIn,
        { onSuccess: v => setCur(c => ({ ...c, nv: { ...c.nv, [nvKey]: v.id } })) }) : undefined} />
  )

  // 技術格（藏在句子裡，配 ⓘ 說明）
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
  const mBlock = () => {
    const mv = opts.m_verbs.find(x => x.code === cur.m.verb)
    const k = mv?.pricing_kind
    const xo = opts.x.find(o => o.code === cur.x)
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
        <Hint tip="X 製程時間：機器/製程造成的等待（熱壓、測試、掃描）；連續式需輸入秒數。" />
        <Sel value={cur.x} onChange={v => set({ x: v })} opts={opts.x.map(o => ({ v: o.code, l: o.label }))} />
        {xo?.mode === 'seconds' && (
          <input type="number" min={0} step={0.1} className="border-2 border-dashed border-slate-300 rounded w-20 px-1 text-sm bg-amber-50"
            value={cur.x_sec} onChange={e => set({ x_sec: parseFloat(e.target.value) || 0 })} placeholder="秒" />)}
        <Hint tip="I 對準/檢查：定位對準或檢查確認動作的分級。" />
        <Sel value={cur.i} onChange={v => set({ i: v })} opts={opts.i.map(o => ({ v: o.code, l: o.label }))} />
      </span>
    )
  }

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
  const line = 'sentence-line p-2 rounded-lg bg-slate-50 border border-slate-100 leading-9 text-sm'
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">編輯一條工序</h2>
          <label className="text-sm flex items-center gap-1"><input type="radio" checked={gm} onChange={() => set({ seq: 'GM' })} /> 一般移動(取放)</label>
          <label className="text-sm flex items-center gap-1"><input type="radio" checked={!gm} onChange={() => set({ seq: 'CM' })} /> 控制移動(推拉鎖)</label>
        </div>

        <div className="space-y-2">
          <p className={line}>
            {<Sel value={cur.handCode} onChange={v => set({ handCode: v })} opts={HANDS} cls="border rounded px-1 py-0.5 text-sm" />}
            {' 從 '}{mkVocab('from', 'from', '—來源—')}{' ，'}{aBlock(cur.a0, s => set({ a0: s }))}{' '}{bBlock('b1')}
            {' 以 '}{gBlock()}{' 取得「'}{mkVocab('object', 'obj', '—物件—')}{'」。'}
          </p>
          {gm ? (
            <p className={line}>
              {'隨後 '}{aBlock(cur.a3, s => set({ a3: s }))}{' '}{bBlock('b4')}
              {' 到 '}{mkVocab('to', 'to', '—目的地—')}{' ，以 '}{pBlock()}{' 放置。'}
            </p>
          ) : (
            <p className={line}>{'在 '}{mkVocab('to', 'to', '—地點—')}{' ，'}{mBlock()}{' 實施控制移動。'}</p>
          )}
          <p className={line}>{'最後 '}{aBlock(cur.a6, s => set({ a6: s }))}{' 返回。'}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-3 border-t text-sm">
          <span className="text-slate-500">次數</span>
          <input type="number" min={1} className="border rounded w-16 px-1 py-0.5" value={cur.freq} onChange={e => set({ freq: parseInt(e.target.value) || 1 })} />
          <span className="text-slate-500">SIMO(同動群)</span>
          <input className="border rounded w-20 px-1 py-0.5" value={cur.simoGroup} onChange={e => set({ simoGroup: e.target.value })} placeholder="可空" />
          <span className="font-mono text-slate-500 text-xs">{tech || '—'}</span>
          <span className="ml-auto">本列 <b className="text-sky-700 text-lg">{tmu ?? '—'}</b> TMU ≈ {tmu != null ? (tmu * TMU_SEC).toFixed(2) : '—'} 秒</span>
          {editable && <button onClick={saveAsTemplate} className="px-2 py-1.5 border rounded">＋存為範本</button>}
          <button disabled={!editable || tmu == null} onClick={add} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg disabled:opacity-40">＋ 加入工時表</button>
        </div>
        {!editable && <p className="text-xs text-amber-600">目前身分無編輯權限（需 IE 以上）。</p>}
      </div>

      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold">工時表</h2>
          <div className="text-sm">合計 <b className="text-emerald-600 text-lg">{total}</b> TMU ≈ <b className="text-emerald-600">{(total * TMU_SEC).toFixed(2)}</b> 秒</div>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-100 text-left"><th className="p-1">#</th><th className="p-1">手</th><th className="p-1">敘述</th><th className="p-1">Base TMU</th><th className="p-1">頻率</th><th className="p-1">Eff TMU</th><th className="p-1">CT(秒)</th><th className="p-1">SIMO</th><th className="p-1"></th></tr></thead>
          <tbody>
            {rows.map((r, i) => {
              const effTmu = r.tmu != null ? r.tmu * r.freq : null
              const ctSec = effTmu != null ? (effTmu * TMU_SEC).toFixed(2) : '—'
              return (
              <tr key={r.id} className="border-t">
                <td className="p-1">{i + 1}</td><td className="p-1">{r.handCode}</td><td className="p-1">{r.narr}</td>
                <td className="p-1"><b>{r.tmu}</b></td><td className="p-1">{r.freq}</td>
                <td className="p-1"><b>{effTmu ?? '—'}</b></td><td className="p-1">{ctSec}</td>
                <td className="p-1">{r.simoGroup}</td>
                <td className="p-1">{editable && <button className="text-red-600 underline" onClick={() => delRow(r.id)}>刪</button>}</td>
              </tr>
            )})}
            {rows.length === 0 && <tr><td colSpan={9} className="p-3 text-slate-400">尚無列。</td></tr>}
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
