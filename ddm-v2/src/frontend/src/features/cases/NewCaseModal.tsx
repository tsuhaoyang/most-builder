// 新建案件 modal（ADR-021 Phase 3）：選產品 → SKU → 輸入機種/線別名稱 → 建立工序表。
// 建立邏輯照原 WorksheetBar「＋新建工序表」流程搬移；階層下拉重用 catalog/api.ts 既有 hooks。
// 建立成功後由呼叫端（CasesPage）setActiveCase 直接進入編輯情境。
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useProducts, useSkus, useWorksheetsBySku, useCreateWorksheet } from '../catalog/api'
import { useMe } from '../../shared/auth/useMe'
import type { ActiveCaseMeta } from '../../shared/workspace'

interface NewCaseModalProps {
  onClose: () => void
  onCreated: (worksheetId: string, meta: ActiveCaseMeta) => void
}

export function NewCaseModal({ onClose, onCreated }: NewCaseModalProps) {
  const { data: me } = useMe()
  const qc = useQueryClient()
  const { data: products = [] } = useProducts()
  const [pid, setPid] = useState('')
  const { data: skus = [] } = useSkus(pid || undefined)
  const [sid, setSid] = useState('')
  const { data: wss = [] } = useWorksheetsBySku(sid || undefined)
  const createWs = useCreateWorksheet()
  const [label, setLabel] = useState('')
  const [analyst, setAnalyst] = useState('')

  // 預設選第一個產品／SKU（同原 WorksheetBar 行為）
  useEffect(() => { if (!pid && products.length) setPid(products[0].id) }, [products, pid])
  useEffect(() => { if (skus.length && !skus.some(s => s.id === sid)) setSid(skus[0].id) }, [skus, sid])

  const product = products.find(p => p.id === pid)
  const sku = skus.find(s => s.id === sid)

  function doCreate() {
    if (!sid || !sku || !product) return
    createWs.mutate(
      { skuId: sid, body: { model_label: label.trim() || undefined, analyst: analyst.trim() || undefined } },
      {
        onSuccess: (r) => {
          qc.invalidateQueries({ queryKey: ['cases'] })
          onCreated(r.worksheet_id, {
            processName: label.trim() || `${sku.sku_code} 工序表`,
            productName: product.name_zh,
            skuName: sku.name_zh ? `${sku.sku_code}（${sku.name_zh}）` : sku.sku_code,
            versionNo: r.version_no,
            status: r.status,
          })
        },
      },
    )
  }

  const selCls = 'border rounded px-2 py-1.5 text-sm bg-white w-full'
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h2 className="font-semibold text-slate-800">新建案件</h2>
        <p className="text-xs text-slate-500">選擇產品與 SKU，建立新工序表後直接進入編輯情境。</p>

        <label className="block text-sm">
          <span className="text-slate-600">產品</span>
          <select className={selCls} value={pid} onChange={(e) => setPid(e.target.value)}>
            {products.length === 0 && <option value="">（尚無產品）</option>}
            {products.map((p) => (
              <option key={p.id} value={p.id}>{p.name_zh}{p.is_active ? '' : '（停用）'}</option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="text-slate-600">SKU / 機種</span>
          <select className={selCls} value={sid} onChange={(e) => setSid(e.target.value)}>
            {skus.length === 0 && <option value="">（此產品尚無 SKU）</option>}
            {skus.map((s) => (
              <option key={s.id} value={s.id}>{s.sku_code}{s.name_zh ? `（${s.name_zh}）` : ''}</option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="text-slate-600">機種/線別名稱</span>
          <input
            className="border rounded px-2 py-1.5 text-sm w-full"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="可空"
          />
        </label>

        <label className="block text-sm">
          <span className="text-slate-600">負責人（員編）</span>
          <input
            className="border rounded px-2 py-1.5 text-sm w-full"
            value={analyst}
            onChange={(e) => setAnalyst(e.target.value)}
            placeholder={me?.employee_no}
          />
        </label>

        {createWs.isError && (
          <p className="text-sm text-red-600">建立失敗：{(createWs.error as Error).message}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-3 py-1.5 border rounded text-sm">取消</button>
          <button
            disabled={!sid || createWs.isPending}
            onClick={doCreate}
            className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm disabled:opacity-40 hover:bg-blue-700 transition-colors"
          >
            {createWs.isPending ? '建立中…' : `建立（v${(wss.length || 0) + 1}）`}
          </button>
        </div>
      </div>
    </div>
  )
}
