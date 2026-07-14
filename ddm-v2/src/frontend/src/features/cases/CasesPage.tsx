// Cases page — G-01 案件清單 + G-02 詳情面板 (L-04 SOP tab 取代)
// ADR-021：匯出動作（wi-preview / excel / lb-csv / report.xlsx）併入案件詳情操作區
import { useState } from 'react'
import { useMe, canPublish, canEdit, isAdmin } from '../../shared/auth/useMe'
import { useWorkspace, type ActiveCaseMeta } from '../../shared/workspace'
import { apiGet } from '../../shared/api/client'
import { TMU_SEC } from '../../shared/config'
import { downloadExcel, downloadCsv, useLbApi, type WiPreview } from '../export/api'
import { StatusBadge } from './status'
import { NewCaseModal } from './NewCaseModal'
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
// StatusBadge 抽至 ./status（CaseContextBar 共用，ADR-021 Phase 3）

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

// ─── 匯出操作區（ADR-021：原頂層「匯出」tab 收進案件詳情）────────────────────
// 依 Export.tsx 既有模式：檔案下載走 window.open（vite proxy / gateway 注入身分），
// wi-preview 走 apiGet 顯示摘要。worksheet id 直接用案件的 worksheet_id，不依賴全域 activeWs。

interface ExportActionsProps {
  worksheetId: string
}

function ExportActions({ worksheetId }: ExportActionsProps) {
  const [preview, setPreview] = useState<WiPreview | null>(null)
  const [previewState, setPreviewState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [previewError, setPreviewError] = useState('')
  const lbApi = useLbApi(worksheetId)
  const [lbResult, setLbResult] = useState('')

  const handlePreview = async () => {
    setPreviewState('loading')
    try {
      const data = await apiGet<WiPreview>(`/api/v2/worksheets/${worksheetId}/export/wi-preview`)
      setPreview(data)
      setPreviewState('idle')
    } catch (e) {
      setPreviewError((e as Error).message)
      setPreviewState('error')
    }
  }

  return (
    <div>
      <h3 className="font-semibold text-sm text-slate-700 mb-2">匯出</h3>
      <div className="flex flex-wrap gap-2">
        <button
          disabled={previewState === 'loading'}
          onClick={handlePreview}
          className="px-3 py-1.5 bg-slate-600 text-white rounded text-sm disabled:opacity-40 hover:bg-slate-700 transition-colors"
        >
          {previewState === 'loading' ? '載入中…' : 'WI 預覽'}
        </button>
        <button
          onClick={() => downloadExcel(worksheetId)}
          className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 transition-colors"
        >
          下載 Excel
        </button>
        <button
          onClick={() => downloadCsv(worksheetId)}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
        >
          下載 LB CSV
        </button>
        <button
          onClick={() => window.open(`/api/v2/worksheets/${worksheetId}/export/report.xlsx`, '_blank')}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
        >
          下載報表
        </button>
        <button
          disabled={lbApi.isPending}
          onClick={() =>
            lbApi.mutate(undefined, {
              onSuccess: (r) => setLbResult(JSON.stringify(r, null, 2)),
              onError: (e) => setLbResult('失敗：' + (e as Error).message),
            })
          }
          className="px-3 py-1.5 bg-violet-600 text-white rounded text-sm disabled:opacity-40 hover:bg-violet-700 transition-colors"
        >
          送 LB API (dry-run)
        </button>
      </div>
      {previewState === 'error' && (
        <p className="mt-2 text-sm text-red-600">WI 預覽失敗：{previewError}</p>
      )}
      {preview && previewState !== 'error' && (
        <p className="mt-2 text-sm text-slate-600">
          共 {preview.rows.length} 列 · 合計{' '}
          <b className="text-emerald-600">{preview.total_tmu}</b> TMU
          （≈ {(preview.total_tmu * TMU_SEC).toFixed(2)} 秒）· 狀態 {preview.status}
        </p>
      )}
      {lbResult && (
        <pre className="mt-2 font-mono text-xs bg-slate-50 p-2 rounded max-h-72 overflow-auto">{lbResult}</pre>
      )}
    </div>
  )
}

interface DetailPanelProps {
  item: CaseOut
  onOpenWorkbench: (item: CaseOut) => void
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
          onClick={() => onOpenWorkbench(item)}
          className="px-3 py-1.5 bg-violet-600 text-white rounded text-sm hover:bg-violet-700 transition-colors"
        >
          編輯工時表
        </button>
      </div>

      {/* Mutation error feedback */}
      {approve.isError && (
        <p className="text-sm text-red-600">核准失敗：{(approve.error as Error).message}</p>
      )}
      {retire.isError && (
        <p className="text-sm text-red-600">退役失敗：{(retire.error as Error).message}</p>
      )}

      {/* Export actions (ADR-021: absorbed from top-level 匯出 tab) */}
      <ExportActions worksheetId={item.worksheet_id} />

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
  const { data: me } = useMe()
  const [statusFilter, setStatusFilter] = useState<CaseStatus>('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showNewCase, setShowNewCase] = useState(false)
  const setActiveCase = useWorkspace((s) => s.setActiveCase)

  const { data, isLoading, error } = useCases({ status: statusFilter })

  const selectedItem = data?.items.find((i) => i.worksheet_id === selectedId) ?? null

  // 「編輯工時表」（ADR-021 Phase 3）：寫入 activeWs＋案件情境 meta（CaseContextBar 用），
  // 再切到 wi tab（WiWorkbench 工時表編輯器）。custom event 讓 App.tsx 切 tab，免 prop drilling。
  const handleOpenWorkbench = (item: CaseOut) => {
    setActiveCase(item.worksheet_id, {
      processName: item.process_name,
      productName: item.product_name,
      skuName: item.sku_name,
      versionNo: item.version_no,
      status: item.status,
    })
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'wi' }))
  }

  // 「新建案件」（ADR-021 Phase 3，原 WorksheetBar ＋新建工序表流程）：建立成功直接進入編輯情境
  const handleCreated = (worksheetId: string, meta: ActiveCaseMeta) => {
    setShowNewCase(false)
    setActiveCase(worksheetId, meta)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'wi' }))
  }

  return (
    <div className="bg-white rounded-xl border flex h-full overflow-hidden" style={{ minHeight: 0 }}>
      {showNewCase && <NewCaseModal onClose={() => setShowNewCase(false)} onCreated={handleCreated} />}
      {/* ── Left list panel ── */}
      <div
        className="flex flex-col flex-shrink-0 border-r"
        style={{ flexBasis: '360px', minWidth: 0 }}
      >
        {/* 新建案件（analyst+）：選產品/SKU → 建工序表 → 進入編輯情境 */}
        {canEdit(me) && (
          <div className="border-b px-3 py-2 bg-slate-50">
            <button
              onClick={() => setShowNewCase(true)}
              className="w-full px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
            >
              ＋ 新建案件
            </button>
          </div>
        )}
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
