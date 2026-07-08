import { useState } from 'react'
import {
  useSites, useProducts, useSkus, useWorksheetsBySku,
  useCreateProduct, useUpdateProduct, useCreateSku, useUpdateSku,
} from './api'
import { useMe, canEdit } from '../../shared/auth/useMe'

export function CatalogPanel() {
  const { data: me } = useMe()
  const editable = canEdit(me)
  const { data: sites = [] } = useSites()
  const { data: products = [] } = useProducts()
  const createProduct = useCreateProduct(); const updateProduct = useUpdateProduct()
  const [pName, setPName] = useState(''); const [pCode, setPCode] = useState('')
  const [sel, setSel] = useState('')   // 選中的 product id

  const { data: skus = [] } = useSkus(sel || undefined)
  const createSku = useCreateSku(); const updateSku = useUpdateSku()
  const [skName, setSkName] = useState(''); const [skCode, setSkCode] = useState('')

  const site0 = sites[0]?.id

  return (
    <div className="grid md:grid-cols-2 gap-4">
      {/* 產品 */}
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold mb-1">產品</h2>
        <p className="text-xs text-slate-500 mb-2">歸屬鏈：產品 → SKU → 版本 → 工序表。停用＝軟刪（保留歷史）。</p>
        <table className="w-full text-sm mb-2">
          <tbody>
            {products.map(p => (
              <tr key={p.id} className={`border-t ${p.is_active ? '' : 'opacity-50'} ${sel === p.id ? 'bg-sky-50' : ''}`}>
                <td className="p-1 cursor-pointer" onClick={() => setSel(p.id)}>
                  {sel === p.id ? '▸ ' : ''}{p.name_zh} <span className="text-slate-400 text-xs">{p.external_code}</span>
                </td>
                <td className="p-1 text-right">
                  {editable && (
                    <button className="text-xs underline" onClick={() => updateProduct.mutate({ id: p.id, patch: { is_active: !p.is_active } })}>
                      {p.is_active ? '停用' : '啟用'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {products.length === 0 && <tr><td className="p-2 text-slate-400">尚無產品。</td></tr>}
          </tbody>
        </table>
        {editable && (
          <div className="flex flex-wrap items-end gap-2 text-sm border-t pt-2">
            <label>名稱 <input className="border rounded px-2 py-1" value={pName} onChange={e => setPName(e.target.value)} /></label>
            <label>業務碼 <input className="border rounded px-2 py-1 w-28" value={pCode} onChange={e => setPCode(e.target.value)} placeholder="可空" /></label>
            <button disabled={!pName.trim() || !site0 || createProduct.isPending}
              onClick={() => createProduct.mutate({ site_id: site0!, name_zh: pName.trim(), external_code: pCode.trim() || undefined },
                { onSuccess: () => { setPName(''); setPCode('') } })}
              className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-40">＋新增產品</button>
            {!site0 && <span className="text-xs text-amber-600">無 site，請先種子。</span>}
          </div>
        )}
      </div>

      {/* SKU（選中產品） */}
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold mb-1">SKU / 機種{sel ? '' : '（先選左側產品）'}</h2>
        {sel && <>
          <div className="space-y-1 mb-2">
            {skus.map(s => <SkuRow key={s.id} skuId={s.id} code={s.sku_code} name={s.name_zh} active={s.is_active} editable={editable}
              onToggle={() => updateSku.mutate({ id: s.id, patch: { is_active: !s.is_active } })} />)}
            {skus.length === 0 && <p className="text-slate-400 text-sm">此產品尚無 SKU。</p>}
          </div>
          {editable && (
            <div className="flex flex-wrap items-end gap-2 text-sm border-t pt-2">
              <label>SKU 碼 <input className="border rounded px-2 py-1 w-32" value={skCode} onChange={e => setSkCode(e.target.value)} /></label>
              <label>名稱 <input className="border rounded px-2 py-1" value={skName} onChange={e => setSkName(e.target.value)} placeholder="可空" /></label>
              <button disabled={!skCode.trim() || createSku.isPending}
                onClick={() => createSku.mutate({ product_id: sel, sku_code: skCode.trim(), name_zh: skName.trim() || undefined },
                  { onSuccess: () => { setSkCode(''); setSkName('') } })}
                className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-40">＋新增 SKU</button>
            </div>
          )}
        </>}
      </div>
    </div>
  )
}

function SkuRow({ skuId, code, name, active, editable, onToggle }: {
  skuId: string; code: string; name: string | null; active: boolean; editable: boolean; onToggle: () => void
}) {
  const { data: wss = [] } = useWorksheetsBySku(skuId)
  return (
    <div className={`flex items-center gap-2 text-sm border-t py-1 ${active ? '' : 'opacity-50'}`}>
      <span className="font-medium">{code}</span>
      {name && <span className="text-slate-500">{name}</span>}
      <span className="text-xs text-slate-400">· {wss.length} 張工序表</span>
      {editable && <button className="ml-auto text-xs underline" onClick={onToggle}>{active ? '停用' : '啟用'}</button>}
    </div>
  )
}
