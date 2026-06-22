import { useEffect, useState } from 'react'
import { useTemplates, useVocab, useCalculate } from './api'
import { useWiStore } from './store'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { Hint } from '../../shared/ui/Hint'

const HANDS = [{ id: 'RH', name: '右手' }, { id: 'LH', name: '左手' }, { id: 'BH', name: '雙手' }]
const TMU_SEC = 0.036

// 垂直切片：示範 Query(範本/詞彙) + Zustand(列) + 後端權威計算 + 元件分層。
// 精確逐格編輯（七格）於後續遷移補上（藍本：docs/html_con）。
export function WiWorkbench() {
  const { data: me } = useMe()
  const { data: templates = [] } = useTemplates()
  const { data: vocab = [] } = useVocab()
  const calc = useCalculate()
  const { rows, addRow, delRow, totalTmu } = useWiStore()

  const [hand, setHand] = useState('RH')
  const [tplId, setTplId] = useState('')
  const [obj, setObj] = useState('')
  const [freq, setFreq] = useState(1)
  const [tmu, setTmu] = useState<number | null>(null)
  const [tech, setTech] = useState('')

  const std = templates.filter((t) => t.status === 'standard')
  const objs = vocab.filter((v) => v.kind === 'object' || v.kind === 'component')
  const tpl = std.find((t) => t.id === tplId)
  const editable = canEdit(me)

  useEffect(() => {
    if (!tpl) { setTmu(null); setTech(''); return }
    calc.mutate(tpl.cycle_template, { onSuccess: (r) => { setTmu(r.total_tmu); setTech(r.tech_line) } })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tplId])

  function add() {
    if (!tpl || tmu == null) return
    const objName = objs.find((o) => o.id === obj)?.name_zh ?? ''
    addRow({
      id: crypto.randomUUID(),
      narr: `${HANDS.find((h) => h.id === hand)?.name} ${tpl.name_zh}「${objName}」`,
      tmu, seconds: tmu * TMU_SEC, freq, handCode: hand, payload: tpl.cycle_template,
    })
  }

  const total = totalTmu()

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold mb-2">編輯一條工序（快速）</h2>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label>手 <select className="border rounded px-1 py-0.5" value={hand} onChange={(e) => setHand(e.target.value)}>
            {HANDS.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}</select></label>
          <label>動作範本<Hint tip="標準動作範本，後端權威計算 TMU" /> <select className="border rounded px-1 py-0.5" value={tplId} onChange={(e) => setTplId(e.target.value)}>
            <option value="">— 選動作 —</option>
            {std.map((t) => <option key={t.id} value={t.id}>[{t.seq_kind}] {t.name_zh}</option>)}</select></label>
          <label>物件 <select className="border rounded px-1 py-0.5" value={obj} onChange={(e) => setObj(e.target.value)}>
            <option value="">—</option>
            {objs.map((o) => <option key={o.id} value={o.id}>{o.name_zh}</option>)}</select></label>
          <label>次數 <input type="number" min={1} className="border rounded w-16 px-1 py-0.5" value={freq} onChange={(e) => setFreq(parseInt(e.target.value) || 1)} /></label>
          <span className="mono">{tech || '—'}</span>
          <span className="ml-auto">本列 <b className="text-sky-700 text-lg">{tmu ?? '—'}</b> TMU</span>
          <button disabled={!editable || tmu == null} onClick={add}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg disabled:opacity-40">＋ 加入</button>
        </div>
        {!editable && <p className="text-xs text-amber-600 mt-2">目前身分無編輯權限（需 IE 以上）。</p>}
      </div>

      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold">工時表</h2>
          <div className="text-sm">合計 <b className="text-emerald-600 text-lg">{total}</b> TMU ≈ <b className="text-emerald-600">{(total * TMU_SEC).toFixed(2)}</b> 秒</div>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-100 text-left"><th className="p-1">#</th><th className="p-1">手</th><th className="p-1">敘述</th><th className="p-1">TMU</th><th className="p-1">次數</th><th className="p-1"></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id} className="border-t">
                <td className="p-1">{i + 1}</td><td className="p-1">{r.handCode}</td><td className="p-1">{r.narr}</td>
                <td className="p-1"><b>{r.tmu}</b></td><td className="p-1">{r.freq}</td>
                <td className="p-1">{editable && <button className="text-red-600 underline" onClick={() => delRow(r.id)}>刪</button>}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="p-3 text-slate-400">尚無列。選動作範本＋物件後「加入」。</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
