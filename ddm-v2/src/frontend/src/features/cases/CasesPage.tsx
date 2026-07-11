// Cases page — G-01 案件清單 + G-02 詳情面板 (L-04 SOP tab 取代)
import { useState } from 'react'
import { useMe, canPublish, isAdmin } from '../../shared/auth/useMe'
import { useWorkspace } from '../../shared/workspace'
import {
  useCases,
  useCaseAuditLog,
  useApproveWorksheet,
  useRetireWorksheet,
  type CaseOut,
  type CaseStatus,
} from './api'

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUS_TABS: { value: CaseStatus; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'approved', label: '已核准' },
  { value: 'retired', label: '已退役' },
]

const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  retired: 'bg-slate-200 text-slate-600',
}

const STATUS_ZH: Record<string, string> = {
  draft: '草稿',
  approved: '已核准',
  retired: '已退役',
}

const ACTION_ZH: Record<string, string> = {
  publish: '核准',
  approve: '核准',
  retire: '退役',
  create: '建立',
  update: '更新',
  clone: '另存新版',
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {STATUS_ZH[status] ?? status}
    </span>
  )
}

interface CaseItemProps {
  item: CaseOut
  selected: boolean
  onSelect: () => void
}

function CaseItem({ item, selected, onSelect }: CaseItemProps) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-3 py-2.5 border-b hover:bg-slate-50 transition-colors ${
        selected ? 'bg-sky-50 border-l-2 border-l-sky-500' : 'border-l-2 border-l-transparent'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium text-sm text-slate-800 leading-tight truncate flex-1">
          {item.process_name}
        </span>
        <StatusBadge status={item.status} />
      </div>
      <div className="mt-0.5 text-xs text-slate-500 truncate">
        {item.product_name} / {item.sku_name}
      </div>
      <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
        <span>版本 {item.version_no}</span>
        {item.total_tmu != null && (
          <span className="text-emerald-600 font-medium">{item.total_tmu} TMU</span>
        )}
      </div>
    </button>
  )
}

interface DetailPanelProps {
  item: CaseOut
  onOpenWorkbench: (worksheetId: string) => void
}

function DetailPanel({ item, onOpenWorkbench }: DetailPanelProps) {
  const { data: me } = useMe()
  const approve = useApproveWorksheet(item.worksheet_id)
  const retire = useRetireWorksheet(item.worksheet_id)
  const userCanPublish = canPublish(me)
  const { data: auditData, isLoading: auditLoading } = useCaseAuditLog(
    item.process_version_id,
    userCanPublish,
  )

  const canApprove = item.status === 'draft' && userCanPublish
  const canRetire = item.status === 'approved' && isAdmin(me)

  const handleDownloadReport = () => {
    window.open(`/api/v2/worksheets/${item.worksheet_id}/export/report.xlsx`, '_blank')
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-2">
        <h2 className="text-lg font-semibold text-slate-800 flex-1">{item.process_name}</h2>
        <StatusBadge status={item.status} />
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm bg-slate-50 rounded-lg p-3">
        <span className="text-slate-500">廠區</span>
        <span className="font-medium">{item.site_name}</span>
        <span className="text-slate-500">產品</span>
        <span className="font-medium">{item.product_name}</span>
        <span className="text-slate-500">機種</span>
        <span className="font-medium">{item.sku_name}</span>
        <span className="text-slate-500">版本</span>
        <span className="font-medium">{item.version_no}</span>
        <span className="text-slate-500">總 TMU</span>
        <span className="font-medium text-emerald-600">
          {item.total_tmu != null ? `${item.total_tmu} TMU` : '—'}
        </span>
        {item.approved_at && (
          <>
            <span className="text-slate-500">核准時間</span>
            <span className="font-medium">{new Date(item.approved_at).toLocaleString('zh-TW')}</span>
          </>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        {canApprove && (
          <button
            disabled={approve.isPending}
            onClick={() => approve.mutate()}
            className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm disabled:opacity-40 hover:bg-emerald-700 transition-colors"
          >
            {approve.isPending ? '處理中…' : '核准'}
          </button>
        )}
        {canRetire && (
          <button
            disabled={retire.isPending}
            onClick={() => retire.mutate()}
            className="px-3 py-1.5 bg-slate-600 text-white rounded text-sm disabled:opacity-40 hover:bg-slate-700 transition-colors"
          >
            {retire.isPending ? '處理中…' : '退役'}
          </button>
        )}
        <button
          onClick={handleDownloadReport}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
        >
          下載報表
        </button>
        <button
          onClick={() => onOpenWorkbench(item.worksheet_id)}
          className="px-3 py-1.5 bg-violet-600 text-white rounded text-sm hover:bg-violet-700 transition-colors"
        >
          開啟工作台
        </button>
      </div>

      {/* Mutation error feedback */}
      {approve.isError && (
        <p className="text-sm text-red-600">核准失敗：{(approve.error as Error).message}</p>
      )}
      {retire.isError && (
        <p className="text-sm text-red-600">退役失敗：{(retire.error as Error).message}</p>
      )}

      {/* Audit log timeline */}
      <div>
        <h3 className="font-semibold text-sm text-slate-700 mb-2">簽核歷程</h3>
        {!userCanPublish ? (
          <p className="text-xs text-slate-400">需 approver 以上角色才可查看歷程</p>
        ) : auditLoading ? (
          <p className="text-sm text-slate-400">載入中…</p>
        ) : !auditData?.items.length ? (
          <p className="text-sm text-slate-400">尚無歷程記錄</p>
        ) : (
          <ol className="relative border-l border-slate-200 space-y-3 ml-1">
            {auditData.items.map((entry) => (
              <li key={entry.id} className="pl-4 relative">
                <span className="absolute -left-1.5 top-1 w-3 h-3 rounded-full bg-slate-300 border-2 border-white" />
                <p className="text-xs text-slate-400">
                  {new Date(entry.created_at).toLocaleString('zh-TW')}
                  <span className="ml-2 font-medium text-slate-600">{entry.actor}</span>
                </p>
                <p className="text-sm font-medium text-slate-700">
                  {ACTION_ZH[entry.action] ?? entry.action}
                  {entry.from_status && entry.to_status && (
                    <span className="ml-1 text-xs text-slate-400 font-normal">
                      {STATUS_ZH[entry.from_status] ?? entry.from_status}
                      {' → '}
                      {STATUS_ZH[entry.to_status] ?? entry.to_status}
                    </span>
                  )}
                </p>
                {entry.comment && (
                  <p className="text-xs text-slate-500 mt-0.5">{entry.comment}</p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function CasesPage() {
  const [statusFilter, setStatusFilter] = useState<CaseStatus>('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const setActiveWs = useWorkspace((s) => s.setActiveWs)

  const { data, isLoading, error } = useCases({ status: statusFilter })

  const selectedItem = data?.items.find((i) => i.worksheet_id === selectedId) ?? null

  // When user clicks "開啟工作台": set activeWs and signal parent to switch tab
  // We use a custom event so App.tsx can intercept without prop drilling
  const handleOpenWorkbench = (worksheetId: string) => {
    setActiveWs(worksheetId)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'workbench-v3' }))
  }

  return (
    <div className="bg-white rounded-xl border flex h-full overflow-hidden" style={{ minHeight: 0 }}>
      {/* ── Left list panel ── */}
      <div
        className="flex flex-col flex-shrink-0 border-r"
        style={{ flexBasis: '360px', minWidth: 0 }}
      >
        {/* Status filter tabs */}
        <div className="flex border-b bg-slate-50">
          {STATUS_TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => { setStatusFilter(t.value); setSelectedId(null) }}
              className={`flex-1 py-2 text-xs font-medium transition-colors ${
                statusFilter === t.value
                  ? 'bg-white text-sky-600 border-b-2 border-sky-500'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* List content */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <p className="p-4 text-sm text-slate-400">載入中…</p>
          )}
          {error && (
            <p className="p-4 text-sm text-red-600">載入失敗：{(error as Error).message}</p>
          )}
          {!isLoading && !error && data?.items.length === 0 && (
            <p className="p-4 text-sm text-slate-400">目前沒有案件</p>
          )}
          {data?.items.map((item) => (
            <CaseItem
              key={item.worksheet_id}
              item={item}
              selected={selectedId === item.worksheet_id}
              onSelect={() => setSelectedId(item.worksheet_id)}
            />
          ))}
        </div>

        {/* Footer count */}
        {data != null && (
          <div className="border-t px-3 py-1.5 text-xs text-slate-400">
            共 {data.total} 筆
          </div>
        )}
      </div>

      {/* ── Right detail panel ── */}
      <div className="flex-1 overflow-hidden" style={{ minWidth: 0 }}>
        {selectedItem ? (
          <DetailPanel item={selectedItem} onOpenWorkbench={handleOpenWorkbench} />
        ) : (
          <div className="h-full flex items-center justify-center text-slate-400 text-sm">
            ← 從左側選擇一個案件
          </div>
        )}
      </div>
    </div>
  )
}
