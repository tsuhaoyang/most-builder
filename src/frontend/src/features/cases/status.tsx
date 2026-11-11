// 案件狀態顯示（CasesPage 與 CaseContextBar 共用，ADR-021 Phase 3 抽出）
//
// 狀態**標籤**（文字）與**徽章配色**在此分家：文字進 i18n 的 `status.*`（ADR-032
// Phase A 第 4 批），配色留在各自的元件——儀表板的 rule-set 卡多一個 `published`
// 且用與 approved 相同的綠，案件則沒有這個狀態。標籤本身三處共用一份，避免出現
// 「同一個狀態在案件頁叫 A、在儀表板叫 B」。
import { useTranslation } from 'react-i18next'

export const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  retired: 'bg-slate-200 text-slate-600',
}

/** 有翻譯的狀態值；其餘（後端若新增列舉值）原樣顯示代碼，不假造中文。 */
const TRANSLATED = ['draft', 'approved', 'retired', 'published']

export function useStatusLabel(): (status: string) => string {
  const { t } = useTranslation()
  return (status: string) => (TRANSLATED.includes(status) ? t(`status.${status}`) : status)
}

export function StatusBadge({ status }: { status: string }) {
  const statusLabel = useStatusLabel()
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {statusLabel(status)}
    </span>
  )
}
