// 案件狀態顯示（CasesPage 與 CaseContextBar 共用，ADR-021 Phase 3 抽出）

export const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  retired: 'bg-slate-200 text-slate-600',
}

export const STATUS_ZH: Record<string, string> = {
  draft: '草稿',
  approved: '已核准',
  retired: '已退役',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {STATUS_ZH[status] ?? status}
    </span>
  )
}
