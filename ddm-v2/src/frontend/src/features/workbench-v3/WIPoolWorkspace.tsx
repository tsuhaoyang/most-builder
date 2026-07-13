// Tab 2: WI 組成工作區 (WIPoolWorkspace) — F-03 三層組裝 L2
// Three-panel layout:
//   [Compact Module Picker] | [WI Composer] | [WI Pool]
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRuleSetOptions } from '../wi-workbench/api'
import { apiGet } from '../../shared/api/client'
import {
  useMotionModules,
  useMotionModuleDetail,
  usePublishModule,
  useCreateWiTemplate,
  useCloneWiTemplate,
  useDeleteWiTemplate,
  useWiTemplates,
  type MotionModuleSummary,
  type MotionModuleRow,
} from './api'
import { useWorkbenchV3Store } from './store'

// ── Toast ─────────────────────────────────────────────────────────────────────
interface ToastState { msg: string; type: 'ok' | 'err' }

function Toast({ toast }: { toast: ToastState | null }) {
  if (!toast) return null
  return (
    <div className={`fixed bottom-6 right-6 z-50 px-4 py-2 rounded shadow-lg text-white text-sm transition-all ${
      toast.type === 'ok' ? 'bg-emerald-600' : 'bg-red-600'
    }`}>
      {toast.msg}
    </div>
  )
}

// ── WI Card (Panel 3 item) ────────────────────────────────────────────────────
interface WiCardProps {
  mod: MotionModuleSummary
  isSelected: boolean
  onSelect: () => void
  onClone: () => void
  onDelete: () => void
  cloneDisabled: boolean
  deleteDisabled: boolean
}

function WiCard({ mod, isSelected, onSelect, onClone, onDelete, cloneDisabled, deleteDisabled }: WiCardProps) {
  const [expanded, setExpanded] = useState(false)
  // top-level total_tmu / action_count 為後端摘要欄；null（無已發布版本）→ 顯示 '—'
  const totalTmu = mod.total_tmu ?? null
  const totalSec = totalTmu != null ? (totalTmu * 0.036).toFixed(2) + 's' : '—'
  const moduleCount = mod.action_count ?? null
  // rows 巢狀於 current_version_detail（list 端點=null）→ 展開時 lazy fetch detail
  const { data: detail, isLoading: detailLoading } = useMotionModuleDetail(mod.id, expanded)
  const rows = detail?.current_version_detail?.rows ?? []

  return (
    <div className={`border rounded-lg transition-colors ${
      isSelected ? 'border-[#409eff] bg-[#ecf5ff]' : 'border-slate-200 hover:border-slate-300 bg-white'
    }`}>
      {/* Card header row */}
      <div className="flex items-center gap-1.5 p-2.5">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onSelect}
          className="flex-shrink-0 cursor-pointer"
        />
        <button
          onClick={() => setExpanded(e => !e)}
          className="text-slate-400 hover:text-slate-600 flex-shrink-0 w-4 text-center leading-none"
          title={expanded ? '折疊' : '展開'}
        >
          {expanded ? '▾' : '▸'}
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate" title={mod.name_zh}>
            {mod.name_zh}
          </p>
          <p className="text-xs text-slate-400">
            {moduleCount ?? '—'} 模組
            {' · '}
            <b style={{ color: '#1a73e8' }}>{totalTmu ?? '—'}</b>{totalTmu != null ? 'T' : ''}
            {' · '}
            {totalSec}
          </p>
        </div>
        <div className="flex gap-1 flex-shrink-0">
          <button
            onClick={onClone}
            disabled={cloneDisabled}
            className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40"
          >
            複製
          </button>
          <button
            onClick={onDelete}
            disabled={deleteDisabled}
            className="text-xs px-2 py-0.5 border border-red-200 text-red-600 rounded hover:bg-red-50 disabled:opacity-40"
          >
            刪除
          </button>
        </div>
      </div>

      {/* Expanded: sub-module rows（lazy fetch detail — rows 巢狀於 current_version_detail） */}
      {expanded && detailLoading && (
        <p className="text-xs text-slate-400 pl-9 pb-2">載入明細…</p>
      )}
      {expanded && !detailLoading && rows.length > 0 && (
        <div className="border-t py-1.5 pl-9 pr-2.5 space-y-1">
          {rows.map((row: MotionModuleRow, i: number) => {
            const rowSeq = row.cycle['seq'] as string | undefined
            const rowTmu = row.cycle['total_tmu'] as number | undefined
            return (
              <div key={i} className="flex items-center gap-2 text-xs text-slate-600 py-0.5">
                <span className="text-slate-400 w-4 text-right flex-shrink-0">{i + 1}.</span>
                {rowSeq && (
                  <span className={`px-1.5 py-0.5 rounded font-medium flex-shrink-0 ${
                    rowSeq === 'GM'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-purple-100 text-purple-700'
                  }`}>
                    {rowSeq}
                  </span>
                )}
                <span className="flex-1 truncate" title={row.sub_activity ?? ''}>
                  {row.sub_activity ?? '—'}
                </span>
                {rowTmu != null && (
                  <b className="flex-shrink-0" style={{ color: '#1a73e8' }}>{rowTmu}T</b>
                )}
              </div>
            )
          })}
        </div>
      )}
      {expanded && !detailLoading && rows.length === 0 && (
        <p className="text-xs text-slate-400 pl-9 pb-2">（無子模組）</p>
      )}
    </div>
  )
}

// ── WIPoolWorkspace ───────────────────────────────────────────────────────────
export function WIPoolWorkspace() {
  const { data: opts } = useRuleSetOptions()
  const qc = useQueryClient()

  // Cross-tab store
  const { pendingModules, clearPendingModules, setPendingWiIds, setActiveTab } =
    useWorkbenchV3Store()

  // API hooks
  const { data: l1Modules = [], isLoading: l1Loading } = useMotionModules({ scope: 'personal' })
  const { data: wiTemplates = [], isLoading: wiLoading } = useWiTemplates()
  const createWiTemplate = useCreateWiTemplate()
  const publishModule = usePublishModule()
  const cloneWiTemplate = useCloneWiTemplate()
  const deleteWiTemplate = useDeleteWiTemplate()

  // Panel 1: Compact Module Picker state
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerSelected, setPickerSelected] = useState<Set<string>>(new Set())

  // Panel 2: WI Composer state
  const [composerModules, setComposerModules] = useState<MotionModuleSummary[]>([])
  const [wiName, setWiName] = useState('')
  const [wiDesc, setWiDesc] = useState('')

  // Panel 3: WI Pool state
  const [poolSearch, setPoolSearch] = useState('')
  const [poolSelected, setPoolSelected] = useState<Set<string>>(new Set())
  const [savingWi, setSavingWi] = useState(false)

  // Toast
  const [toast, setToast] = useState<ToastState | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  function showToast(msg: string, type: 'ok' | 'err' = 'ok') {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg, type })
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }

  // Consume pendingModules from store on mount (F-03 跨層傳送 Tab1→Tab2)
  const consumedRef = useRef(false)
  useEffect(() => {
    if (!consumedRef.current && pendingModules.length > 0) {
      consumedRef.current = true
      setComposerModules(prev => [...prev, ...pendingModules])
      clearPendingModules()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Panel 1: filtered L1 modules (exclude wi-templates from picker)
  const filteredL1 = useMemo(() => {
    const base = l1Modules.filter(m => m.category !== 'wi-template')
    const q = pickerSearch.trim().toLowerCase()
    if (!q) return base
    return base.filter(m => m.name_zh.toLowerCase().includes(q))
  }, [l1Modules, pickerSearch])

  // Panel 3: filtered WI templates
  const filteredWi = useMemo(() => {
    const q = poolSearch.trim().toLowerCase()
    if (!q) return wiTemplates
    return wiTemplates.filter(m => m.name_zh.toLowerCase().includes(q))
  }, [wiTemplates, poolSearch])

  // Running total TMU for the composer — 任一模組缺 total_tmu（無已發布版本）
  // 時回 null，UI 顯示 '—'，不得把缺值假裝成 0
  const totalComposerTmu = useMemo(() => {
    if (composerModules.some(m => m.total_tmu == null)) return null
    return composerModules.reduce((s, m) => s + (m.total_tmu ?? 0), 0)
  }, [composerModules])

  // ── Panel 1 handlers ───────────────────────────────────────────────────────

  function togglePickerSelect(id: string) {
    setPickerSelected(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  function handleAddToComposer() {
    const toAdd = l1Modules.filter(m => pickerSelected.has(m.id))
    const unpublished = toAdd.filter(m => m.status !== 'standard')
    if (unpublished.length > 0) {
      showToast(
        `此模組尚未核定（非 standard），無法加入 WI：${unpublished.map(m => m.name_zh).join('、')}`,
        'err',
      )
    }
    const valid = toAdd.filter(m => m.status === 'standard')
    if (valid.length > 0) {
      setComposerModules(prev => [...prev, ...valid])
    }
    setPickerSelected(new Set())
  }

  // ── Panel 2 handlers ───────────────────────────────────────────────────────

  function moveUp(index: number) {
    if (index <= 0) return
    setComposerModules(prev => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]]
      return next
    })
  }

  function moveDown(index: number) {
    setComposerModules(prev => {
      if (index >= prev.length - 1) return prev
      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]]
      return next
    })
  }

  function removeFromComposer(index: number) {
    setComposerModules(prev => prev.filter((_, i) => i !== index))
  }

  function clearComposer() {
    setComposerModules([])
    setWiName('')
    setWiDesc('')
  }

  async function handleSaveWi() {
    if (!wiName.trim()) { showToast('請輸入 WI 名稱', 'err'); return }
    if (composerModules.length === 0) { showToast('請至少加入一個模組', 'err'); return }
    if (!opts) { showToast('rule-set 尚未載入', 'err'); return }

    setSavingWi(true)
    try {
      // Snapshot semantics: copy each module's rows at save time (F-03 §2.2)。
      // list 物件不含 rows（rows 巢狀於 current_version_detail）→ 逐一 fetch detail，
      // 保留 vocab_refs / simo_pair_index，不得用假預設值充數。
      const rows: MotionModuleRow[] = await Promise.all(
        composerModules.map(async mod => {
          const detail = await apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${mod.id}`)
          const srcRow = detail.current_version_detail?.rows?.[0]
          if (!srcRow) throw new Error(`模組「${mod.name_zh}」尚無已發布版本`)
          return { ...srcRow, sub_activity: mod.name_zh }
        }),
      )

      // 後端 MotionModuleCreate 無 rows 欄位；rows 由 publish 建立版本
      const created = await createWiTemplate.mutateAsync({
        name_zh: wiName.trim(),
        category: 'wi-template',
        keywords: [],
        scope: 'personal',
      })

      await publishModule.mutateAsync({
        id: created.id,
        body: { rows, rule_set_code: opts.code },
      })

      // Ensure WI pool refreshes after publish
      qc.invalidateQueries({ queryKey: ['wi-templates'] })

      clearComposer()
      showToast('WI 已儲存：' + wiName.trim(), 'ok')
    } catch (err) {
      showToast('儲存失敗：' + (err as Error).message, 'err')
    } finally {
      setSavingWi(false)
    }
  }

  // ── Panel 3 handlers ───────────────────────────────────────────────────────

  function togglePoolSelect(id: string) {
    setPoolSelected(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  async function handleCloneWi(id: string, name: string) {
    try {
      await cloneWiTemplate.mutateAsync(id)
      showToast('已複製：' + name, 'ok')
    } catch (err) {
      showToast('複製失敗：' + (err as Error).message, 'err')
    }
  }

  async function handleDeleteWi(id: string, name: string) {
    if (!window.confirm(`確認刪除 WI「${name}」？`)) return
    try {
      await deleteWiTemplate.mutateAsync(id)
      setPoolSelected(s => { const next = new Set(s); next.delete(id); return next })
      showToast('已刪除：' + name, 'ok')
    } catch (err) {
      showToast('刪除失敗：' + (err as Error).message, 'err')
    }
  }

  // F-03 跨層傳送 Tab2→Tab3
  function handleSendToProcess() {
    setPendingWiIds([...poolSelected])
    setActiveTab('tab3')
    setPoolSelected(new Set())
  }

  const isSaving = savingWi || createWiTemplate.isPending || publishModule.isPending

  return (
    <>
      <Toast toast={toast} />
      <div className="flex gap-3 h-full min-h-0">

        {/* ── Panel 1: Compact Module Picker ────────────────────────────────── */}
        <div className="w-56 flex-shrink-0 flex flex-col bg-white rounded-xl border">
          <div className="p-3 border-b">
            <h2 className="font-semibold text-sm mb-2">模組選取器</h2>
            <input
              className="border rounded px-2 py-1 text-xs w-full"
              placeholder="搜尋模組…"
              value={pickerSearch}
              onChange={e => setPickerSearch(e.target.value)}
            />
          </div>

          {/* Module list — max-height: 45vh per UX spec */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1" style={{ maxHeight: '45vh' }}>
            {l1Loading && (
              <p className="text-xs text-slate-400 text-center py-4">載入中…</p>
            )}
            {!l1Loading && filteredL1.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-4">
                {pickerSearch ? '無相符模組' : '尚無個人模組'}
              </p>
            )}
            {filteredL1.map(mod => {
              const isChecked = pickerSelected.has(mod.id)
              // total_tmu = 後端摘要欄；null → '—'。seq 優先讀 top-level seq_kind 摘要欄，
              // fallback current_version_detail 第一列；都沒有就不顯示 badge
              const modTmu = mod.total_tmu ?? null
              const modSeq =
                mod.seq_kind ??
                (mod.current_version_detail?.rows?.[0]?.cycle['seq'] as string | undefined)
              return (
                <label
                  key={mod.id}
                  className={`flex items-center gap-1.5 p-1.5 rounded cursor-pointer text-xs ${
                    isChecked
                      ? 'bg-blue-50 border border-blue-200'
                      : 'hover:bg-slate-50 border border-transparent'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => togglePickerSelect(mod.id)}
                    className="flex-shrink-0 cursor-pointer"
                  />
                  {modSeq && (
                    <span className={`px-1 py-0.5 rounded text-[10px] font-medium flex-shrink-0 ${
                      modSeq === 'GM'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-purple-100 text-purple-700'
                    }`}>
                      {modSeq}
                    </span>
                  )}
                  <span className="flex-1 truncate" title={mod.name_zh}>{mod.name_zh}</span>
                  <b className="flex-shrink-0 text-[11px]" style={{ color: '#1a73e8' }}>
                    {modTmu != null ? `${modTmu}T` : '—'}
                  </b>
                </label>
              )
            })}
          </div>

          <div className="p-2 border-t">
            <button
              onClick={handleAddToComposer}
              disabled={pickerSelected.size === 0}
              className="w-full px-2 py-1.5 bg-blue-600 text-white rounded text-xs font-medium disabled:opacity-40 hover:bg-blue-700"
            >
              {pickerSelected.size > 0
                ? `加入組成器 (${pickerSelected.size})`
                : '加入組成器'}
            </button>
          </div>
        </div>

        {/* ── Panel 2: WI Composer ──────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 flex flex-col bg-white rounded-xl border">
          <div className="p-3 border-b flex items-center justify-between">
            <h2 className="font-semibold text-sm">WI 組成器</h2>
            {composerModules.length > 0 && (
              <span className="text-xs text-slate-500">
                共{' '}
                <b style={{ color: '#1a73e8' }}>{totalComposerTmu ?? '—'}</b>
                {totalComposerTmu != null ? 'T' : ''}
                {' · '}
                {totalComposerTmu != null ? (totalComposerTmu * 0.036).toFixed(2) + 's' : '—'}
              </span>
            )}
          </div>

          {/* Ordered module list */}
          <div className="flex-1 overflow-y-auto p-3 space-y-1 min-h-0">
            {composerModules.length === 0 && (
              <div className="flex items-center justify-center h-28 text-slate-400 text-sm">
                從左側選取模組，或從 Tab 1 傳送至此
              </div>
            )}
            {composerModules.map((mod, i) => {
              const modTmu = mod.total_tmu ?? null
              const isUnpublished = mod.status !== 'standard'
              return (
                <div
                  key={`${mod.id}-${i}`}
                  className={`flex items-center gap-2 p-2 rounded border text-sm ${
                    isUnpublished
                      ? 'border-orange-200 bg-orange-50'
                      : 'border-slate-200 bg-slate-50'
                  }`}
                >
                  <span className="text-slate-400 text-xs w-5 text-right flex-shrink-0">
                    {i + 1}.
                  </span>
                  <span className="flex-1 truncate" title={mod.name_zh}>{mod.name_zh}</span>
                  {isUnpublished && (
                    <span className="text-xs text-orange-600 flex-shrink-0 whitespace-nowrap">
                      未發布
                    </span>
                  )}
                  <b className="text-sm flex-shrink-0" style={{ color: '#1a73e8' }}>
                    {modTmu != null ? `${modTmu}T` : '—'}
                  </b>
                  <div className="flex gap-0.5 flex-shrink-0 items-center">
                    <button
                      onClick={() => moveUp(i)}
                      disabled={i === 0}
                      className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5 leading-none"
                      title="上移"
                    >
                      ↑
                    </button>
                    <button
                      onClick={() => moveDown(i)}
                      disabled={i === composerModules.length - 1}
                      className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5 leading-none"
                      title="下移"
                    >
                      ↓
                    </button>
                    <button
                      onClick={() => removeFromComposer(i)}
                      className="text-red-400 hover:text-red-600 px-0.5 leading-none"
                      title="移除"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )
            })}
          </div>

          {/* WI form + actions */}
          <div className="p-3 border-t space-y-2">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">WI 名稱</label>
              <input
                className="border rounded px-2 py-1.5 text-sm w-full"
                placeholder="請輸入 WI 名稱（必填）"
                value={wiName}
                onChange={e => setWiName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">描述 / 備注</label>
              <input
                className="border rounded px-2 py-1.5 text-sm w-full"
                placeholder="選填"
                value={wiDesc}
                onChange={e => setWiDesc(e.target.value)}
              />
            </div>
            <div className="flex gap-2 pt-1">
              <button
                onClick={clearComposer}
                className="px-3 py-1.5 border rounded text-sm text-slate-600 hover:bg-slate-50"
              >
                清空
              </button>
              <button
                onClick={handleSaveWi}
                disabled={isSaving || !wiName.trim() || composerModules.length === 0}
                className="flex-1 px-4 py-1.5 bg-blue-600 text-white rounded text-sm font-medium disabled:opacity-40 hover:bg-blue-700"
              >
                {isSaving ? '儲存中…' : '儲存為 WI'}
              </button>
            </div>
          </div>
        </div>

        {/* ── Panel 3: WI Pool ──────────────────────────────────────────────── */}
        <div className="w-80 flex-shrink-0 flex flex-col bg-white rounded-xl border">
          <div className="p-3 border-b">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-semibold text-sm">WI Pool</h2>
              <span className="text-xs text-slate-400">{wiTemplates.length} 筆</span>
            </div>
            <input
              className="border rounded px-2 py-1 text-xs w-full"
              placeholder="搜尋 WI 名稱…"
              value={poolSearch}
              onChange={e => setPoolSearch(e.target.value)}
            />
          </div>

          {/* WI card list — max-height: 40vh per UX spec */}
          <div
            className="flex-1 overflow-y-auto p-2 space-y-2 min-h-0"
            style={{ maxHeight: '40vh' }}
          >
            {wiLoading && (
              <p className="text-xs text-slate-400 text-center py-4">載入中…</p>
            )}
            {!wiLoading && filteredWi.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-4 leading-relaxed">
                {poolSearch
                  ? '無相符 WI'
                  : '尚無 WI 模板，請先組合動作模組並儲存'}
              </p>
            )}
            {filteredWi.map(mod => (
              <WiCard
                key={mod.id}
                mod={mod}
                isSelected={poolSelected.has(mod.id)}
                onSelect={() => togglePoolSelect(mod.id)}
                onClone={() => handleCloneWi(mod.id, mod.name_zh)}
                onDelete={() => handleDeleteWi(mod.id, mod.name_zh)}
                cloneDisabled={cloneWiTemplate.isPending}
                deleteDisabled={deleteWiTemplate.isPending}
              />
            ))}
          </div>

          {/* Multi-select bottom bar — F-03 跨層傳送 Tab2→Tab3 */}
          {poolSelected.size > 0 && (
            <div className="border-t p-3 flex items-center justify-between gap-2">
              <span className="text-sm text-slate-600">已選 {poolSelected.size} 筆</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPoolSelected(new Set())}
                  className="text-xs px-2 py-1 border rounded text-slate-500 hover:bg-slate-50"
                >
                  清除
                </button>
                <button
                  onClick={handleSendToProcess}
                  className="text-xs px-3 py-1 bg-blue-600 text-white rounded font-medium hover:bg-blue-700"
                >
                  傳送至製程
                </button>
              </div>
            </div>
          )}
        </div>

      </div>
    </>
  )
}
