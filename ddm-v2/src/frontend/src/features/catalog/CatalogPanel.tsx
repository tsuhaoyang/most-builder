/**
 * 產品／SKU 主數據 CRUD 面板。**目前零引用、使用者到不了**——`App.tsx` 的 7 個 tab
 * （ADR-021 IA）沒有 catalog 入口，本檔不被任何地方 import。
 *
 * **為什麼仍刻意保留**（2026-08-21 User 裁決，Phase A 孤兒清理時逐檔覆核）：
 * 後端 `POST /api/v2/products`／`PATCH /api/v2/products/{id}`／`POST /api/v2/skus`／
 * `PATCH /api/v2/skus/{id}` 都還活著，而 `useCreateProduct`／`useUpdateProduct`／
 * `useCreateSku`／`useUpdateSku`／`useSites`（`./api`）**全 repo 只有本檔在用**。
 * 刪掉本檔＝把「產品／SKU 沒有任何可達的管理 UI」這個 IA 缺口從*暫時*變成*永久*
 * （同批一起刪掉的 `Export.tsx`／`WorksheetBar.tsx` 則相反：它們的功能已分別被
 * `features/cases/CasesPage.tsx` 與 `features/cases/NewCaseModal.tsx` 完整吸收）。
 *
 * **但它現在也不能直接接回去**，產品化前必須先修這三個實作缺陷：
 *   1. `const site0 = sites[0]?.id`（見下）——「撈第一列」。目前只有單廠區才碰巧正確；
 *      多廠區時新產品會**靜默**落到任意 site（不報錯、事後才發現歸屬錯）。要真的接進
 *      IA 必須先有明確的 site 選擇。（`docs/CI_GATES.md` 硬性規則 7 第一則禁的是*測試*
 *      撈第一列，本檔是產品碼不在其字面範圍內；但那條規則要防的失效模式與這裡同源。）
 *   2. `SkuRow` 每一列各自呼叫 `useWorksheetsBySku(skuId)` —— N+1 查詢，代價只換到
 *      一行「· N 張工序表」的顯示。
 *   3. `無 site，請先種子。` 是開發期文案；更根本的是**整個 Site 層級沒有任何選擇或
 *      管理介面**——歸屬鏈（Site → 產品 → SKU → 版本 → 工序表）最上層是空的。
 *
 * **歸屬未定**：ADR-024 的主數據定義表只涵蓋詞彙庫（`work_vocab_items`）與範本庫
 * （`motion_templates`），**不含產品／SKU**。要把本檔接進「主數據管理」得先修訂
 * ADR-024，那是架構決策、不是實作決定。
 *
 * i18n-exempt-file[72]: 零引用且待重寫的產品／SKU CRUD，UI 字串維持中文——見本檔頭
 *   四段說明：它接回 IA 前必須先修三個實作缺陷並修訂 ADR-024 決定歸屬，屆時整個版面
 *   會重寫，現在外部化這 72 個字等於同一份工付兩次。
 *   `[72]` 是**漢字預算**（守衛斷言本檔剝離註解後的漢字數不得超過它）：豁免不是垃圾
 *   桶，這裡的中文只准隨著重寫變少，新的字請走 i18n。
 */
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
