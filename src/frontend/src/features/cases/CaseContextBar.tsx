// 案件情境列（ADR-021 Phase 3）：wi tab（工時表編輯器）頂部常駐。
// 資料來源：workspace store 的 activeCaseMeta（由 CasesPage / NewCaseModal 進入時寫入）。
// 返回動線：dispatch ddm:switch-tab → 'case'（App.tsx 監聽切 tab）。
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '../../shared/workspace'
import { StatusBadge } from './status'

export function CaseContextBar() {
  const { t } = useTranslation()
  const meta = useWorkspace((s) => s.activeCaseMeta)

  const goBack = () =>
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'case' }))

  return (
    <div
      data-testid="case-context-bar"
      className="bg-white rounded-xl border px-4 py-2 mb-3 flex flex-wrap items-center gap-3 text-sm"
    >
      <button
        onClick={goBack}
        className="px-2 py-1 border rounded text-slate-600 hover:bg-slate-50 transition-colors"
      >
        {t('cases.contextBar.back')}
      </button>
      {meta ? (
        <>
          <span className="font-medium text-slate-800">{meta.processName}</span>
          <span className="text-xs text-slate-500">
            {t('cases.contextBar.meta', {
              product: meta.productName,
              sku: meta.skuName,
              version: meta.versionNo,
            })}
          </span>
          <StatusBadge status={meta.status} />
        </>
      ) : (
        <span className="text-xs text-slate-400">{t('cases.contextBar.editingContext')}</span>
      )}
    </div>
  )
}
