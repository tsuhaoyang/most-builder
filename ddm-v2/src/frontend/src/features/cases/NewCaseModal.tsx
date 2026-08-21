// 新建案件 modal（ADR-021 Phase 3；P1-C 語意修正，守則 §6/§7-2）。
//
// 修正重點：
// 1. **不自動預選第一個產品/SKU** —— 舊行為會讓每次「新建案件」默默在同一個 SKU 上 +1 版
//    （demo SKU 版本爆量的成因之一）。產品/SKU 預設空、必選。
// 2. 引導以 **P1-A 聚合鍵 `(sku_id, model_label)` 精確比對**（review #2）：
//    - 同 SKU ＋同 model_label ⇒ 命中既有案件 → 「繼續編輯該案件的草稿」／「建立新版本」
//    - 同 SKU 但 model_label 不同 ⇒ 這是**該 SKU 底下的另一個案件** → 只給資訊性提示，
//      不列別的案件的草稿（點下去會跳到別的案件），主按鈕維持「建立新案件」
//    故 model_label 輸入欄必須排在 SKU 之後、引導區塊之前。
//    版本資料來源＝既有 catalog hook `useWorksheetsBySku`（GET /api/v2/skus/{id}/worksheets）：
//    它本來就是 SKU 範圍且直接給 worksheet_id/version_no/status/model_label，
//    比從 /api/v2/cases 聚合結果反查同 sku_id 案件更直接（cases 需先分頁命中該案件）。
// 3. SKU 尚無版本＝真正的新案件。
//
// ⚠️ 版號來源：後端 catalog_service.create_worksheet 以 **SKU 範圍**的 process_versions
//    COUNT+1 產號（非 per model_label），故按鈕上的版號一律用 `wss.length + 1`
//    ——即使是該 SKU 的新案件也可能是 v12。不在此處假造 v1。
import { useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { useProducts, useSkus, useWorksheetsBySku, useCreateWorksheet, type WorksheetSummary } from '../catalog/api'
import { useMe } from '../../shared/auth/useMe'
import { StatusBadge } from './status'
import type { ActiveCaseMeta } from '../../shared/workspace'

interface NewCaseModalProps {
  onClose: () => void
  /** 開啟某個工序表的編輯情境（新建成功 或 選擇繼續編輯現有草稿） */
  onOpenWorksheet: (worksheetId: string, meta: ActiveCaseMeta) => void
}

export function NewCaseModal({ onClose, onOpenWorksheet }: NewCaseModalProps) {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const qc = useQueryClient()
  const { data: products = [] } = useProducts()
  const [pid, setPid] = useState('')
  const { data: skus = [] } = useSkus(pid || undefined)
  const [sid, setSid] = useState('')
  const { data: wss = [], isLoading: wssLoading } = useWorksheetsBySku(sid || undefined)
  const createWs = useCreateWorksheet()
  const [label, setLabel] = useState('')
  const [analyst, setAnalyst] = useState('')

  const product = products.find((p) => p.id === pid)
  const sku = skus.find((s) => s.id === sid)
  const skuLabel = sku ? (sku.name_zh ? `${sku.sku_code}（${sku.name_zh}）` : sku.sku_code) : ''

  // 聚合鍵比對：後端 model_label 為 NULL 時等同空字串（cases_service 以 coalesce 併入 case_key）
  const normLabel = (v: string | null | undefined) => (v ?? '').trim()
  const caseLabel = normLabel(label)
  const ready = !!sid && !wssLoading
  /** 同 SKU ＋同 model_label ＝同一個案件的版本鏈 */
  const sameCase = wss.filter((w) => normLabel(w.model_label) === caseLabel)
  /** 同 SKU 但不同 model_label ＝該 SKU 底下的其他案件（僅資訊，不可點選） */
  const otherCaseLabels = [...new Set(
    wss.filter((w) => normLabel(w.model_label) !== caseLabel).map((w) => normLabel(w.model_label)),
  )]

  const isExistingCase = ready && sameCase.length > 0
  const hasOtherCases = ready && otherCaseLabels.length > 0
  const drafts = sameCase.filter((w) => w.status === 'draft')
  // 後端產號＝該 SKU 的 process_versions COUNT+1（見檔頭註記），不是 per-case 計數
  const nextVersion = wss.length + 1

  function doCreate() {
    if (!sid || !sku || !product) return
    createWs.mutate(
      { skuId: sid, body: { model_label: label.trim() || undefined, analyst: analyst.trim() || undefined } },
      {
        onSuccess: (r) => {
          qc.invalidateQueries({ queryKey: ['cases'] })
          onOpenWorksheet(r.worksheet_id, {
            processName: label.trim() || t('cases.newCase.worksheetFallbackName', { sku: sku.sku_code }),
            productName: product.name_zh,
            skuName: skuLabel,
            versionNo: r.version_no,
            status: r.status,
          })
        },
      },
    )
  }

  function doContinue(ws: WorksheetSummary) {
    if (!sku || !product) return
    onOpenWorksheet(ws.worksheet_id, {
      processName: ws.model_label || t('cases.newCase.worksheetFallbackName', { sku: sku.sku_code }),
      productName: product.name_zh,
      skuName: skuLabel,
      versionNo: ws.version_no,
      status: ws.status,
    })
  }

  const selCls = 'border rounded px-2 py-1.5 text-sm bg-white w-full'
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h2 className="font-semibold text-slate-800">{t('cases.newCase.title')}</h2>
        <p className="text-xs text-slate-500">
          {t('cases.newCase.subtitle')}
        </p>

        <label className="block text-sm">
          <span className="text-slate-600">{t('cases.newCase.product')}</span>
          <select className={selCls} value={pid} onChange={(e) => { setPid(e.target.value); setSid('') }}>
            <option value="">{products.length === 0 ? t('cases.newCase.noProducts') : t('cases.newCase.selectProduct')}</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>{p.name_zh}{p.is_active ? '' : t('cases.newCase.inactiveSuffix')}</option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="text-slate-600">{t('cases.newCase.sku')}</span>
          <select className={selCls} value={sid} onChange={(e) => setSid(e.target.value)} disabled={!pid}>
            <option value="">
              {!pid ? t('cases.newCase.selectProductFirst') : skus.length === 0 ? t('cases.newCase.noSkus') : t('cases.newCase.selectSku')}
            </option>
            {skus.map((s) => (
              <option key={s.id} value={s.id}>{s.sku_code}{s.name_zh ? `（${s.name_zh}）` : ''}</option>
            ))}
          </select>
        </label>

        {/* 機種/線別名稱＝聚合鍵的一半，必須在引導區塊之前（review #2） */}
        <label className="block text-sm">
          <span className="text-slate-600">{t('cases.newCase.modelLabel')}</span>
          <input
            className="border rounded px-2 py-1.5 text-sm w-full"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={t('cases.newCase.modelLabelPlaceholder')}
          />
        </label>

        {/* A. 命中既有案件（同 SKU ＋同 model_label）：不默默 +1 版（守則 §6） */}
        {isExistingCase && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2" data-testid="existing-versions-guide">
            <p className="text-sm font-medium text-amber-900">
              {t('cases.newCase.existingTitle', {
                label: caseLabel || t('cases.newCase.unnamed'),
                count: sameCase.length,
              })}
            </p>
            <p className="text-xs text-amber-800">
              {t('cases.newCase.existingHint')}
            </p>

            <div>
              <p className="text-xs font-medium text-slate-600 mb-1">{t('cases.newCase.continueDraftTitle')}</p>
              {drafts.length === 0 ? (
                <p className="text-xs text-slate-500">{t('cases.newCase.noDrafts')}</p>
              ) : (
                <ul className="space-y-1">
                  {drafts.map((w) => (
                    <li key={w.worksheet_id}>
                      <button
                        onClick={() => doContinue(w)}
                        className="w-full flex items-center gap-2 px-2 py-1.5 bg-white border rounded text-sm text-left hover:bg-slate-50 transition-colors"
                      >
                        <span className="font-medium text-slate-700">{w.version_no}</span>
                        <StatusBadge status={w.status} />
                        <span className="flex-1 truncate text-xs text-slate-500">{w.model_label ?? '—'}</span>
                        <span className="text-xs text-sky-600 shrink-0">{t('cases.newCase.continueEdit')}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {/* B. 同 SKU 但 model_label 不同＝另一個案件：純資訊，不列別案件的草稿 */}
        {!isExistingCase && hasOtherCases && (
          <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 space-y-1" data-testid="other-cases-info">
            <p className="text-sm font-medium text-sky-900">
              {t('cases.newCase.otherCasesTitle', { count: otherCaseLabels.length })}
            </p>
            <p className="text-xs text-sky-800">
              <Trans i18nKey="cases.newCase.otherCasesHint" components={{ b: <b /> }} />
            </p>
            <ul className="text-xs text-slate-600 list-disc list-inside">
              {otherCaseLabels.map((l) => (
                <li key={l || '(unnamed)'}>{l || t('cases.newCase.unnamedItem')}</li>
              ))}
            </ul>
          </div>
        )}

        <label className="block text-sm">
          <span className="text-slate-600">{t('cases.newCase.analyst')}</span>
          <input
            className="border rounded px-2 py-1.5 text-sm w-full"
            value={analyst}
            onChange={(e) => setAnalyst(e.target.value)}
            placeholder={me?.employee_no}
          />
        </label>

        {createWs.isError && (
          <p className="text-sm text-red-600">{t('cases.newCase.createFailed', { message: (createWs.error as Error).message })}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-3 py-1.5 border rounded text-sm">{t('cases.newCase.cancel')}</button>
          <button
            disabled={!sid || wssLoading || createWs.isPending}
            onClick={doCreate}
            className={`px-3 py-1.5 text-white rounded text-sm disabled:opacity-40 transition-colors ${
              isExistingCase ? 'bg-slate-600 hover:bg-slate-700' : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {createWs.isPending
              ? t('cases.newCase.creating')
              : isExistingCase
                ? t('cases.newCase.createVersion', { n: nextVersion })
                : t('cases.newCase.createCase', { n: nextVersion })}
          </button>
        </div>
      </div>
    </div>
  )
}
