import { useEffect, useState } from 'react'
import { useProducts, useSkus, useWorksheetsBySku, useCreateWorksheet } from './api'
import { useWorkspace } from '../../shared/workspace'
import { useMe, canEdit } from '../../shared/auth/useMe'

// 頂部「產品 / SKU / 工序表(版本)」選擇器：決定作用中的 worksheet（取代寫死 ACTIVE_WS）。
export function WorksheetBar() {
  const { data: me } = useMe()
  const activeWs = useWorkspace(s => s.activeWs)
  const setActiveWs = useWorkspace(s => s.setActiveWs)
  const { data: products = [] } = useProducts()
  const [pid, setPid] = useState('')
  const { data: skus = [] } = useSkus(pid)
  const [sid, setSid] = useState('')
  const { data: wss = [] } = useWorksheetsBySku(sid)
  const createWs = useCreateWorksheet()
  const [showNew, setShowNew] = useState(false)
  const [label, setLabel] = useState(''); const [analyst, setAnalyst] = useState('')

  useEffect(() => { if (!pid && products.length) setPid(products[0].id) }, [products, pid])
  useEffect(() => { if (skus.length && !skus.some(s => s.id === sid)) setSid(skus[0].id) }, [skus, sid])
  useEffect(() => { if (wss.length && !wss.some(w => w.worksheet_id === activeWs)) setActiveWs(wss[0].worksheet_id) }, [wss]) // eslint-disable-line react-hooks/exhaustive-deps

  const cur = wss.find(w => w.worksheet_id === activeWs)
  const editable = canEdit(me)

  function doCreate() {
    if (!sid) return
    createWs.mutate({ skuId: sid, body: { model_label: label.trim() || undefined, analyst: analyst.trim() || undefined } },
      { onSuccess: r => { setActiveWs(r.worksheet_id); setShowNew(false); setLabel(''); setAnalyst('') } })
  }

  const selCls = 'border rounded px-2 py-1 text-sm bg-white max-w-[14rem]'
  return (
    <div className="bg-slate-50 border-b">
      <div className="max-w-6xl mx-auto px-4 py-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">產品</span>
        <select className={selCls} value={pid} onChange={e => setPid(e.target.value)}>
          {products.length === 0 && <option value="">（無產品，請到「⑧ 目錄」建立）</option>}
          {products.map(p => <option key={p.id} value={p.id}>{p.name_zh}{p.is_active ? '' : '（停用）'}</option>)}
        </select>
        <span className="text-slate-500">SKU</span>
        <select className={selCls} value={sid} onChange={e => setSid(e.target.value)}>
          {skus.length === 0 && <option value="">—</option>}
          {skus.map(s => <option key={s.id} value={s.id}>{s.sku_code}{s.name_zh ? `（${s.name_zh}）` : ''}</option>)}
        </select>
        <span className="text-slate-500">工序表</span>
        <select className={selCls} value={activeWs} onChange={e => setActiveWs(e.target.value)}>
          {wss.length === 0 && <option value={activeWs}>（此 SKU 尚無工序表）</option>}
          {wss.map(w => <option key={w.worksheet_id} value={w.worksheet_id}>
            {w.version_no}·{w.status}{w.model_label ? `·${w.model_label}` : ''}
          </option>)}
        </select>
        {cur?.analyst && <span className="text-xs text-slate-400">負責：{cur.analyst}</span>}
        {editable && sid && (
          <button onClick={() => setShowNew(v => !v)} className="ml-auto px-2 py-1 border rounded text-blue-700">＋新建工序表</button>
        )}
      </div>
      {showNew && (
        <div className="max-w-6xl mx-auto px-4 pb-2 flex flex-wrap items-end gap-2 text-sm">
          <label>機種/線別 <input className="border rounded px-2 py-1" value={label} onChange={e => setLabel(e.target.value)} placeholder="可空" /></label>
          <label>負責人(員編) <input className="border rounded px-2 py-1" value={analyst} onChange={e => setAnalyst(e.target.value)} placeholder={me?.employee_no} /></label>
          <button disabled={createWs.isPending} onClick={doCreate} className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-40">建立（v{(wss.length || 0) + 1}）</button>
          <button onClick={() => setShowNew(false)} className="px-2 py-1 border rounded">取消</button>
        </div>
      )}
    </div>
  )
}
