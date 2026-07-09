// Tab 3: 製程途程工作區 (ProcessWorkspace) — F-03 三層組裝 L3 + E-06/E-07
// F-03b §3: apply-back（從工序表行發布模組新版本，真實對接後端）
// Two-panel layout:
//   [WI 選取器 (Compact WI Picker)] | [製程大綱 (ProcessOutline)]
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  useWiTemplates,
  useInstantiateToWorksheet,
  useVersionFromRows,
  type MotionModuleSummary,
  type ApplyBackRowIn,
} from './api'
import { useWorkbenchV3Store } from './store'
import { useWorkspace } from '../../shared/workspace'
import { useWorksheet } from '../wi-workbench/api'
import type { WsReadRow } from '../wi-workbench/api'

// ── Toast ─────────────────────────────────────────────────────────────────────
interface ToastState { msg: string; type: 'ok' | 'err' | 'warn' }

function Toast({ toast }: { toast: ToastState | null }) {
  if (!toast) return null
  const bg =
    toast.type === 'ok' ? 'bg-emerald-600'
    : toast.type === 'warn' ? 'bg-amber-500'
    : 'bg-red-600'
  return (
    <div className={`fixed bottom-6 right-6 z-50 px-4 py-2 rounded shadow-lg text-white text-sm transition-all ${bg}`}>
      {toast.msg}
    </div>
  )
}

// ── Apply-back 確認對話框（F-03b §3.3）────────────────────────────────────────
interface ApplyBackDialogProps {
  moduleName: string
  moduleVersion: number
  rowCount: number
  isPending: boolean
  onConfirm: () => void
  onCancel: () => void
}

function ApplyBackDialog({ moduleName, moduleVersion, rowCount, isPending, onConfirm, onCancel }: ApplyBackDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4">
        <h3 className="font-semibold text-sm mb-3">確認發布新版本</h3>
        <p className="text-sm text-slate-700 mb-1">
          將從目前工序表內容建立新版本：
        </p>
        <p className="text-sm font-medium text-blue-700 mb-4 truncate" title={moduleName}>
          {moduleName} <span className="text-slate-400 font-normal">v{moduleVersion}</span>
        </p>
        <p className="text-xs text-slate-500 mb-3">
          共 {rowCount} 列將同步回模組庫
        </p>
        <div className="text-xs text-slate-500 bg-slate-50 rounded p-3 mb-5 space-y-1">
          <p>現有流程繼續使用快照，不受影響</p>
          <p>模組版本將升為新版本（舊版本保留可查）</p>
          <p>其他流程將顯示「來源有新版本可用」提示</p>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            disabled={isPending}
            className="px-3 py-1.5 text-sm border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-40"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40"
          >
            {isPending ? '發布中…' : '確認發布'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Row item in ProcessOutline ─────────────────────────────────────────────────
interface RowItemProps {
  row: WsReadRow
  index: number
  total: number
  onMoveUp: () => void
  onMoveDown: () => void
  onDelete: () => void
  /** 不為 undefined 代表此列可 apply-back（有 source_module_id） */
  onApplyBack?: () => void
}

function RowItem({ row, index, total, onMoveUp, onMoveDown, onDelete, onApplyBack }: RowItemProps) {
  const tmu = row.cycle?.total_tmu ?? 0

  return (
    <div className="flex items-center gap-2 p-2 rounded border border-slate-200 bg-slate-50 text-sm">
      <span className="text-slate-400 text-xs w-5 text-right flex-shrink-0">
        {index + 1}.
      </span>
      <div className="flex-1 min-w-0">
        <p className="truncate text-slate-700" title={row.cycle?.narrative ?? undefined}>
          {row.cycle?.narrative ?? `列 ${row.seq_no}`}
        </p>
        {row.source_module_id && (
          <span className="text-[10px] text-slate-400 bg-slate-200 px-1 py-0.5 rounded">
            來自模組
          </span>
        )}
      </div>
      <b className="text-sm flex-shrink-0" style={{ color: '#1a73e8' }}>{tmu}T</b>
      <div className="flex gap-0.5 flex-shrink-0 items-center">
        {onApplyBack && (
          <button
            onClick={onApplyBack}
            className="text-blue-500 hover:text-blue-700 px-1 leading-none text-[10px] font-medium border border-blue-200 rounded"
            title="套用為新版本（同步回模組庫）"
          >
            回
          </button>
        )}
        <button
          onClick={onMoveUp}
          disabled={index === 0}
          className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5 leading-none"
          title="上移"
        >
          ↑
        </button>
        <button
          onClick={onMoveDown}
          disabled={index >= total - 1}
          className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5 leading-none"
          title="下移"
        >
          ↓
        </button>
        <button
          onClick={onDelete}
          className="text-red-400 hover:text-red-600 px-0.5 leading-none"
          title="刪除"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

// ── Apply-back 待確認狀態 ──────────────────────────────────────────────────────
interface ApplyBackPending {
  moduleId: string
  moduleVersion: number
  moduleName: string
  rows: ApplyBackRowIn[]
  ruleSetId: string
}

// ── ProcessWorkspace ───────────────────────────────────────────────────────────
export function ProcessWorkspace() {
  const activeWs = useWorkspace(s => s.activeWs)

  // WI template list (same data as Tab 2 WI Pool)
  const { data: wiTemplates = [], isLoading: wiLoading } = useWiTemplates()

  // Current worksheet rows (for ProcessOutline panel)
  const { data: wsData } = useWorksheet(activeWs ?? '')

  // Instantiate mutation
  const instantiate = useInstantiateToWorksheet()

  // Apply-back mutation (F-03b §3)
  const versionFromRows = useVersionFromRows()

  // Cross-tab store
  const { clearPendingWiIds } = useWorkbenchV3Store()

  // Panel 1: WI Selector state
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')

  // Panel 2: local display order (mirrors DB seq_no; reorder is local-only per spec)
  const apiRows: WsReadRow[] = useMemo(() => wsData?.rows ?? [], [wsData])
  const [localOrder, setLocalOrder] = useState<WsReadRow[]>([])

  // Keep localOrder in sync when DB rows change (e.g. after instantiate)
  useEffect(() => {
    setLocalOrder(apiRows)
  }, [apiRows])

  // Toast
  const [toast, setToast] = useState<ToastState | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  function showToast(msg: string, type: ToastState['type'] = 'ok') {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg, type })
    toastTimer.current = setTimeout(() => setToast(null), 3500)
  }

  // Apply-back confirmation state
  const [applyBackPending, setApplyBackPending] = useState<ApplyBackPending | null>(null)

  // Consume pendingWiIds from store on mount (F-03 跨層傳送 Tab2→Tab3, E-07)
  const consumedRef = useRef(false)
  useEffect(() => {
    if (consumedRef.current) return
    consumedRef.current = true
    const pending = useWorkbenchV3Store.getState().pendingWiIds
    if (pending.length > 0) {
      setSelected(new Set(pending))
      clearPendingWiIds()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Panel 1: filtered WI templates (client-side search)
  const filteredWi = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return wiTemplates
    return wiTemplates.filter((m: MotionModuleSummary) => m.name_zh.toLowerCase().includes(q))
  }, [wiTemplates, search])

  // Panel 1 handlers
  function toggleSelect(id: string) {
    setSelected(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  async function handleAddToProcess() {
    if (!activeWs) {
      showToast('請先在工作台選取工序表', 'err')
      return
    }
    if (selected.size === 0) return

    const ids = [...selected]
    let successCount = 0
    let hasDrift = false
    const errors: string[] = []

    for (const id of ids) {
      try {
        const result = await instantiate.mutateAsync({ worksheetId: activeWs, moduleId: id })
        successCount++
        if (result.tmu_drift && result.tmu_drift.length > 0) {
          hasDrift = true
        }
      } catch (err) {
        errors.push((err as Error).message)
      }
    }

    setSelected(new Set())

    if (successCount > 0) {
      showToast(`已加入 ${successCount} 個 WI`, 'ok')
    }
    if (hasDrift) {
      // Show drift warning after brief delay so it doesn't overlap
      setTimeout(() => showToast('部分 WI TMU 因規則集不同已調整', 'warn'), 400)
    }
    if (errors.length > 0) {
      setTimeout(
        () => showToast(`${errors.length} 個 WI 加入失敗：${errors[0]}`, 'err'),
        hasDrift ? 800 : 400,
      )
    }
  }

  // Panel 2 handlers (local reorder only — no API call per spec)
  function moveUp(index: number) {
    if (index <= 0) return
    setLocalOrder(prev => {
      const next = [...prev]
      ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
      return next
    })
  }

  function moveDown(index: number) {
    setLocalOrder(prev => {
      if (index >= prev.length - 1) return prev
      const next = [...prev]
      ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
      return next
    })
  }

  function handleDelete(_index: number) {
    showToast('功能即將推出', 'warn')
  }

  // Apply-back: prepare confirmation state (F-03b §3.2 Step 2-3)
  // Fix-B: dual-key (sourceModuleId, sourceModuleVersion) prevents mixing rows from different
  //        instantiations of the same module.
  function handlePrepareApplyBack(sourceModuleId: string, sourceModuleVersion: number) {
    // Collect all rows sharing the same (source_module_id, source_module_version) pair
    const sourceRows = localOrder.filter(r =>
      r.source_module_id === sourceModuleId &&
      r.source_module_version === sourceModuleVersion
    )
    if (sourceRows.length === 0) return

    // Get rule_set_id from first row with a cycle (all rows from same module share rule set)
    const ruleSetId = sourceRows.find(r => r.cycle?.rule_set_id)?.cycle?.rule_set_id
    if (!ruleSetId) {
      showToast('無法取得規則集 ID，請重新載入', 'err')
      return
    }

    // Map WsReadRow → ApplyBackRowIn
    // slot_inputs IS the CycleIn JSON (stored via cycle.model_dump(mode="json"))
    // Fix-A: reconstruct vocab_refs from existing row fields so the backend
    //        instantiate_to_worksheet does not silently skip rows with empty vocab_refs.
    const rows: ApplyBackRowIn[] = sourceRows.map(r => ({
      sub_activity: r.sub_activity ?? null,
      hand: r.hand ?? 'BH',
      frequency: Math.max(1, Math.round(r.frequency)),
      simo_pair_index: null,
      vocab_refs: {
        ...(r.object_vocab_id ? { object_vocab_id: r.object_vocab_id } : {}),
        ...(r.from_vocab_id   ? { from_vocab_id:   r.from_vocab_id  } : {}),
        ...(r.to_vocab_id     ? { to_vocab_id:     r.to_vocab_id    } : {}),
        ...(r.tool_vocab_id   ? { tool_vocab_id:   r.tool_vocab_id  } : {}),
      },
      cycle: r.cycle?.slot_inputs,
    }))

    // Resolve module name from WI template list (best-effort; fallback to short ID)
    const module = wiTemplates.find((m: MotionModuleSummary) => m.id === sourceModuleId)
    const moduleName = module?.name_zh ?? `模組 ${sourceModuleId.slice(0, 8)}`

    setApplyBackPending({ moduleId: sourceModuleId, moduleVersion: sourceModuleVersion, moduleName, rows, ruleSetId })
  }

  // Apply-back: actually call the API (F-03b §3.2 Step 4+)
  async function handleApplyBackConfirm() {
    if (!applyBackPending) return
    try {
      const result = await versionFromRows.mutateAsync({
        moduleId: applyBackPending.moduleId,
        rows: applyBackPending.rows,
        ruleSetId: applyBackPending.ruleSetId,
      })
      setApplyBackPending(null)
      showToast(`已建立版本 v${result.version_no}`, 'ok')
    } catch (err) {
      // 409 / 422 / 403 detail 由 apiPost 解開為 Error.message
      showToast((err as Error).message, 'err')
    }
  }

  // Process stats
  const totalRows = localOrder.length
  const totalTmu = useMemo(
    () => localOrder.reduce((s, r) => s + (r.cycle?.total_tmu ?? 0), 0),
    [localOrder],
  )
  const totalSec = (totalTmu * 0.036).toFixed(2)

  const isAdding = instantiate.isPending

  return (
    <>
      <Toast toast={toast} />

      {/* Apply-back 確認對話框（F-03b §3.3）*/}
      {applyBackPending && (
        <ApplyBackDialog
          moduleName={applyBackPending.moduleName}
          moduleVersion={applyBackPending.moduleVersion}
          rowCount={applyBackPending.rows.length}
          isPending={versionFromRows.isPending}
          onConfirm={handleApplyBackConfirm}
          onCancel={() => setApplyBackPending(null)}
        />
      )}

      <div className="flex gap-3 h-full min-h-0">

        {/* ── Panel 1: WI 選取器 ─────────────────────────────────────────── */}
        <div className="w-72 flex-shrink-0 flex flex-col bg-white rounded-xl border">
          <div className="p-3 border-b">
            <h2 className="font-semibold text-sm mb-2">WI 選取器</h2>
            <input
              className="border rounded px-2 py-1 text-xs w-full"
              placeholder="搜尋 WI 名稱…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1" style={{ maxHeight: '45vh' }}>
            {wiLoading && (
              <p className="text-xs text-slate-400 text-center py-4">載入中…</p>
            )}
            {!wiLoading && filteredWi.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-4 leading-relaxed">
                {search ? '無相符 WI' : '尚無 WI 模板，請先至 Tab 2 建立'}
              </p>
            )}
            {filteredWi.map((mod: MotionModuleSummary) => {
              const isChecked = selected.has(mod.id)
              const tmu = mod.total_tmu ?? 0
              return (
                <label
                  key={mod.id}
                  className={`flex items-center gap-2 p-2 rounded cursor-pointer text-xs border transition-colors ${
                    isChecked
                      ? 'border-[#409eff] bg-[#ecf5ff]'
                      : 'border-transparent hover:bg-slate-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleSelect(mod.id)}
                    className="flex-shrink-0 cursor-pointer"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="truncate font-medium text-slate-700" title={mod.name_zh}>
                      {mod.name_zh}
                    </p>
                    <p className="text-slate-400">
                      {mod.rows.length} 模組
                      {' · '}
                      <b style={{ color: '#1a73e8' }}>{tmu}</b>T
                    </p>
                  </div>
                </label>
              )
            })}
          </div>

          <div className="p-2 border-t">
            <button
              onClick={handleAddToProcess}
              disabled={selected.size === 0 || isAdding}
              className="w-full px-2 py-1.5 bg-blue-600 text-white rounded text-xs font-medium disabled:opacity-40 hover:bg-blue-700"
            >
              {isAdding
                ? '加入中…'
                : selected.size > 0
                  ? `加入流程 (${selected.size})`
                  : '加入流程'}
            </button>
          </div>
        </div>

        {/* ── Panel 2: 製程大綱 ──────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 flex flex-col bg-white rounded-xl border">
          <div className="p-3 border-b">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-sm">製程大綱</h2>
              {activeWs && (
                <span className="text-xs text-slate-400 font-mono truncate max-w-xs" title={activeWs}>
                  {activeWs.slice(0, 8)}…
                </span>
              )}
            </div>
            {totalRows > 0 && (
              <p className="text-xs text-slate-500 mt-1">
                {totalRows} 個列
                {' · '}
                <b style={{ color: '#1a73e8' }}>{totalTmu}</b>T
                {' · '}
                {totalSec}s
              </p>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1.5 min-h-0">
            {!activeWs && (
              <div className="flex flex-col items-center justify-center h-40 gap-2 text-slate-400">
                <span className="text-2xl">📋</span>
                <p className="text-sm">請先選取工序表</p>
              </div>
            )}
            {activeWs && localOrder.length === 0 && (
              <div className="flex flex-col items-center justify-center h-40 gap-2 text-slate-400">
                <span className="text-2xl">＋</span>
                <p className="text-sm">從左側選取 WI 模板並加入流程</p>
              </div>
            )}
            {localOrder.map((row, i) => (
              <RowItem
                key={row.wi_row_id}
                row={row}
                index={i}
                total={localOrder.length}
                onMoveUp={() => moveUp(i)}
                onMoveDown={() => moveDown(i)}
                onDelete={() => handleDelete(i)}
                // graceful degrade: onApplyBack 僅在有 source_module_id + source_module_version 時傳入 (F-03b §3)
                // Fix-B: pass version so dual-key filter works correctly
                onApplyBack={
                  row.source_module_id && row.source_module_version != null
                    ? () => handlePrepareApplyBack(row.source_module_id!, row.source_module_version!)
                    : undefined
                }
              />
            ))}
          </div>
        </div>

      </div>
    </>
  )
}
