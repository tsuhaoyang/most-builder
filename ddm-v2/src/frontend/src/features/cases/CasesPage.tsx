// Cases page — G-01 案件清單 + G-02 詳情面板 (L-04 SOP tab 取代)
// ADR-021：匯出動作（wi-preview / excel / lb-csv / report.xlsx）併入案件詳情操作區
import { useEffect, useRef, useState } from 'react'
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
  type CaseVersionBrief,
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

/**
 * 代表版（最新版）的版本摘要。後端 `versions[]` 必含代表版；
 * 若某案件歷史為空（僅平面欄位可用）則由平面欄位還原，語意等價。
 */
function repVersionOf(item: CaseOut): CaseVersionBrief {
  const found = item.versions.find((v) => v.process_version_id === item.process_version_id)
  return (
    found ?? {
      process_version_id: item.process_version_id,
      worksheet_id: item.worksheet_id,
      version_no: item.version_no,
      status: item.status,
      total_tmu: item.total_tmu,
      created_at: item.created_at,
      approved_at: item.approved_at,
    }
  )
}

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('zh-TW')

interface CaseItemProps {
  item: CaseOut
  /** 此案件被選取（右側詳情正顯示它的某一版） */
  selected: boolean
  expanded: boolean
  /** 目前檢視版本的 process_version_id（未選取此案件時為 null） */
  viewingVersionId: string | null
  onSelect: () => void
  onToggleExpand: () => void
  onSelectVersion: (v: CaseVersionBrief) => void
}

/**
 * 一列＝一個**案件**（非一版，守則 §6/§7-2）。
 * 摘要顯示代表版；version_count > 1 時給「N 版」徽章＋展開鈕，展開後可點選歷史版。
 */
function CaseItem({
  item, selected, expanded, viewingVersionId, onSelect, onToggleExpand, onSelectVersion,
}: CaseItemProps) {
  const multi = item.version_count > 1
  return (
    <div
      className={`border-b ${
        selected ? 'bg-sky-50 border-l-2 border-l-sky-500' : 'border-l-2 border-l-transparent'
      }`}
      data-testid="case-row"
    >
      <div className="flex items-stretch">
        <button onClick={onSelect} className="flex-1 min-w-0 text-left px-3 py-2.5 hover:bg-slate-100/60 transition-colors">
          <div className="flex items-start justify-between gap-2">
            <span className="font-medium text-sm text-slate-800 leading-tight truncate flex-1">
              {item.process_name}
              {item.model_label && (
                <span className="ml-1 font-normal text-slate-500">· {item.model_label}</span>
              )}
            </span>
            <StatusBadge status={item.status} />
          </div>
          <div className="mt-0.5 text-xs text-slate-500 truncate">
            {item.product_name} / {item.sku_name}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
            <span>最新 {item.version_no}</span>
            {item.total_tmu != null && (
              <span className="text-emerald-600 font-medium">{item.total_tmu} TMU</span>
            )}
            {multi && (
              <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">
                {item.version_count} 版
              </span>
            )}
          </div>
        </button>
        {multi && (
          <button
            onClick={onToggleExpand}
            aria-expanded={expanded}
            aria-label={expanded ? '收合版本歷史' : '展開版本歷史'}
            title={expanded ? '收合版本歷史' : '展開版本歷史'}
            className="px-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            {expanded ? '▾' : '▸'}
          </button>
        )}
      </div>

      {multi && expanded && (
        <ul className="bg-slate-50/80 border-t" data-testid="case-versions">
          {item.versions.map((v) => {
            const isViewing = selected && viewingVersionId === v.process_version_id
            const isLatest = v.process_version_id === item.process_version_id
            return (
              <li key={v.process_version_id}>
                <button
                  onClick={() => onSelectVersion(v)}
                  className={`w-full flex items-center gap-2 pl-6 pr-3 py-1.5 text-xs text-left hover:bg-slate-100 transition-colors ${
                    isViewing ? 'bg-sky-100/70 font-medium' : ''
                  }`}
                >
                  <span className="text-slate-700 w-12 shrink-0">{v.version_no}</span>
                  <StatusBadge status={v.status} />
                  <span className="text-emerald-600 w-20 shrink-0">
                    {v.total_tmu != null ? `${v.total_tmu} TMU` : '—'}
                  </span>
                  <span className="text-slate-400 flex-1 text-right truncate">{fmtDate(v.created_at)}</span>
                  {isLatest && <span className="text-sky-600 shrink-0">最新</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
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
        <div className="mt-2 space-y-2" data-testid="wi-preview-rows">
          <p className="text-sm text-slate-600">
            共 {preview.rows.length} 列 · 合計{' '}
            <b className="text-emerald-600">{preview.total_tmu}</b> TMU
            （≈ {(preview.total_tmu * TMU_SEC).toFixed(2)} 秒）· 狀態 {preview.status}
          </p>
          {preview.rows.length > 0 && (
            <div className="max-h-72 overflow-auto border-y">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-100 text-left text-slate-500">
                  <tr>
                    <th className="w-12 px-2 py-1.5">步驟</th>
                    <th className="px-2 py-1.5">WI / 動作內容</th>
                    <th className="px-2 py-1.5">METHOD</th>
                    <th className="w-20 px-2 py-1.5 text-right">TMU</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, index) => (
                    <tr key={`${row.seq_no ?? index}-${index}`} className="border-t align-top">
                      <td className="px-2 py-1.5 text-slate-400">{row.seq_no ?? index + 1}</td>
                      <td className="px-2 py-1.5 text-slate-700">{row.sub_activity || '—'}</td>
                      <td className="px-2 py-1.5 text-slate-500">{row.method || '—'}</td>
                      <td className="px-2 py-1.5 text-right font-medium text-emerald-700">
                        {row.tmu ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      {lbResult && (
        <pre className="mt-2 font-mono text-xs bg-slate-50 p-2 rounded max-h-72 overflow-auto">{lbResult}</pre>
      )}
    </div>
  )
}

interface DetailPanelProps {
  item: CaseOut
  /** 目前檢視的版本（預設＝代表版，可由左側展開列指定歷史版） */
  view: CaseVersionBrief
  onOpenWorkbench: (item: CaseOut, view: CaseVersionBrief) => void
}

/**
 * 案件詳情：所有操作（核准/退役/編輯工時表/匯出/簽核歷程）都綁**目前檢視版本**的
 * worksheet_id / process_version_id，不固定用代表版。
 * 可用性仍沿用既有 status 規則（歷史版通常非 draft/approved 代表版狀態，自然不可操作），
 * 不自創權限。
 */
function DetailPanel({ item, view, onOpenWorkbench }: DetailPanelProps) {
  const { data: me } = useMe()
  const approve = useApproveWorksheet(view.worksheet_id)
  const retire = useRetireWorksheet(view.worksheet_id)
  const userCanPublish = canPublish(me)
  const { data: auditData, isLoading: auditLoading } = useCaseAuditLog(
    view.process_version_id,
    userCanPublish,
  )

  const isLatest = view.process_version_id === item.process_version_id
  // 守則 §1「案件＝單一當前狀態」：狀態流轉只允許在**代表版（最新版）**上進行。
  // 否則核准一個歷史 draft 會讓同一條版本鏈出現兩個 approved（案件當前狀態不再唯一）。
  const canApprove = view.status === 'draft' && userCanPublish && isLatest
  const canRetire = view.status === 'approved' && isAdmin(me) && isLatest

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-2">
        <h2 className="text-lg font-semibold text-slate-800 flex-1">
          {item.process_name}
          {item.model_label && <span className="ml-1 text-base font-normal text-slate-500">· {item.model_label}</span>}
        </h2>
        <StatusBadge status={view.status} />
      </div>

      {/* 目前檢視版本（C-1：詳情頂部標示是哪一版） */}
      <div
        className={`flex flex-wrap items-center gap-2 text-sm rounded-lg px-3 py-2 ${
          isLatest ? 'bg-sky-50 text-sky-800' : 'bg-amber-50 text-amber-800'
        }`}
        data-testid="viewing-version"
      >
        <span className="font-semibold">{view.version_no}</span>
        <span>· {isLatest ? '最新' : '歷史'}</span>
        <span className="text-xs opacity-75">（共 {item.version_count} 版）</span>
        {!isLatest && (
          <span className="text-xs">歷史版本唯讀：不可編輯，狀態流轉請回到最新版</span>
        )}
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
        <span className="font-medium">{view.version_no}</span>
        <span className="text-slate-500">總 TMU</span>
        <span className="font-medium text-emerald-600">
          {view.total_tmu != null ? `${view.total_tmu} TMU` : '—'}
        </span>
        <span className="text-slate-500">建立時間</span>
        <span className="font-medium">{new Date(view.created_at).toLocaleString('zh-TW')}</span>
        {view.approved_at && (
          <>
            <span className="text-slate-500">核准時間</span>
            <span className="font-medium">{new Date(view.approved_at).toLocaleString('zh-TW')}</span>
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
        {/* 歷史版唯讀：直接停用入口，而非讓使用者編輯到存檔才撞後端 NotEditable */}
        <button
          disabled={!isLatest}
          onClick={() => onOpenWorkbench(item, view)}
          title={isLatest ? undefined : '歷史版本唯讀，請切換到最新版再編輯'}
          className="px-3 py-1.5 bg-violet-600 text-white rounded text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-violet-700 transition-colors"
        >
          編輯工時表
        </button>
        {!isLatest && (
          <span className="self-center text-xs text-slate-500">歷史版本唯讀，請切換到最新版再編輯</span>
        )}
      </div>

      {/* Mutation error feedback */}
      {approve.isError && (
        <p className="text-sm text-red-600">核准失敗：{(approve.error as Error).message}</p>
      )}
      {retire.isError && (
        <p className="text-sm text-red-600">退役失敗：{(retire.error as Error).message}</p>
      )}

      {/* Export actions (ADR-021: absorbed from top-level 匯出 tab)；匯出目前檢視版本 */}
      <ExportActions key={view.worksheet_id} worksheetId={view.worksheet_id} />

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
  // 案件識別＝代表版 worksheet_id；檢視版本另存（預設代表版）
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [viewVersionId, setViewVersionId] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<string[]>([])
  const [showNewCase, setShowNewCase] = useState(false)
  const activeWs = useWorkspace((s) => s.activeWs)
  const setActiveCase = useWorkspace((s) => s.setActiveCase)
  const selectedActiveWs = useRef<string | null>(null)

  const { data, isLoading, error } = useCases({ status: statusFilter })

  const selectedItem = data?.items.find((i) => i.worksheet_id === selectedId) ?? null
  // 目前檢視版本：展開列指定者，否則代表版
  const viewedVersion = selectedItem
    ? selectedItem.versions.find((v) => v.process_version_id === viewVersionId)
      ?? repVersionOf(selectedItem)
    : null

  useEffect(() => {
    if (!data || !activeWs || selectedActiveWs.current === activeWs) return
    const item = data.items.find((candidate) =>
      candidate.versions.some((version) => version.worksheet_id === activeWs),
    )
    if (!item) return
    const version = item.versions.find((candidate) => candidate.worksheet_id === activeWs)
    setSelectedId(item.worksheet_id)
    setViewVersionId(version?.process_version_id ?? item.process_version_id)
    selectedActiveWs.current = activeWs
  }, [activeWs, data])

  const selectCase = (item: CaseOut) => {
    setSelectedId(item.worksheet_id)
    setViewVersionId(item.process_version_id)
  }
  const selectVersion = (item: CaseOut, v: CaseVersionBrief) => {
    setSelectedId(item.worksheet_id)
    setViewVersionId(v.process_version_id)
  }
  const toggleExpand = (id: string) =>
    setExpandedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  // 「編輯工時表」（ADR-021 Phase 3）：寫入 activeWs＋案件情境 meta（CaseContextBar 用），
  // 再切到 wi tab（WiWorkbench 工時表編輯器）。custom event 讓 App.tsx 切 tab，免 prop drilling。
  // C-1：帶**目前檢視版本**的 worksheet_id，不固定用代表版。
  const handleOpenWorkbench = (item: CaseOut, view: CaseVersionBrief) => {
    setActiveCase(view.worksheet_id, {
      processName: item.process_name,
      productName: item.product_name,
      skuName: item.sku_name,
      versionNo: view.version_no,
      status: view.status,
    })
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'wi' }))
  }

  // 「新建案件」（ADR-021 Phase 3，原 WorksheetBar ＋新建工序表流程）：
  // 建立成功、或從引導區塊選「繼續編輯現有草稿」，都直接進入該工序表的編輯情境
  const handleOpenWorksheet = (worksheetId: string, meta: ActiveCaseMeta) => {
    setShowNewCase(false)
    setActiveCase(worksheetId, meta)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'wi' }))
  }

  return (
    <div className="bg-white rounded-xl border flex h-full overflow-hidden" style={{ minHeight: 0 }}>
      {showNewCase && <NewCaseModal onClose={() => setShowNewCase(false)} onOpenWorksheet={handleOpenWorksheet} />}
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
              onClick={() => { setStatusFilter(t.value); setSelectedId(null); setViewVersionId(null) }}
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
              expanded={expandedIds.includes(item.worksheet_id)}
              viewingVersionId={selectedId === item.worksheet_id ? viewVersionId : null}
              onSelect={() => selectCase(item)}
              onToggleExpand={() => toggleExpand(item.worksheet_id)}
              onSelectVersion={(v) => selectVersion(item, v)}
            />
          ))}
        </div>

        {/* Footer count（P1-A：total 語意＝案件數，非版本數） */}
        {data != null && (
          <div className="border-t px-3 py-1.5 text-xs text-slate-400">
            共 {data.total} 件案件
          </div>
        )}
      </div>

      {/* ── Right detail panel ── */}
      <div className="flex-1 overflow-hidden" style={{ minWidth: 0 }}>
        {selectedItem && viewedVersion ? (
          <DetailPanel item={selectedItem} view={viewedVersion} onOpenWorkbench={handleOpenWorkbench} />
        ) : (
          <div className="h-full flex items-center justify-center text-slate-400 text-sm">
            ← 從左側選擇一個案件
          </div>
        )}
      </div>
    </div>
  )
}
