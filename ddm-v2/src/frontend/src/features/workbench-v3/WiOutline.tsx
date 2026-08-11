// WiOutlineSection — WI 大綱（ADR-022 批次 B-3；對照 v3 WiOutline.vue）
// 動作清單下方區塊：列出 category='wi-template' 的 WI；
//   列：名稱｜N 動作｜total TMU·秒｜「已微調」badge（版本>1）｜刪除（confirm）
//   展開子列：narrative/sub_activity、hand、freq、computed.total_tmu/eff_tmu、SIMO 標記
//   子列操作：點列開 WiItemInspector（父層）、上移/下移（reorder）、刪除（DELETE row）
// 所有數字來自後端持久化 computed（ADR-022 A-1）；前端不算 TMU。
import { useEffect, useMemo, useState } from 'react'
import { TMU_SEC } from '../../shared/config'
import {
  useWiTemplates,
  useMotionModuleDetail,
  useUpdateModule,
  useDeleteWiTemplate,
  useReorderModuleRows,
  useDeleteModuleRow,
  type MotionModuleSummary,
  type MotionModuleRow,
} from './api'

const HAND_NAME: Record<string, string> = { RH: '右手', LH: '左手', BH: '雙手' }

export interface WiOutlineSectionProps {
  onInspect: (wi: MotionModuleSummary, rowIndex: number, row: MotionModuleRow) => void
  showToast: (msg: string, type?: 'ok' | 'err') => void
  /** Inspector 目前開啟的目標（高亮子列用） */
  activeTarget?: { moduleId: string; rowIndex: number } | null
}

export function WiOutlineSection({ onInspect, showToast, activeTarget }: WiOutlineSectionProps) {
  const { data: wis = [], isLoading } = useWiTemplates()
  const updateModule = useUpdateModule()
  const deleteWi = useDeleteWiTemplate()
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [orderedWiIds, setOrderedWiIds] = useState<string[]>([])
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')

  useEffect(() => {
    setOrderedWiIds(prev => {
      const ids = wis.map(w => w.id)
      const known = prev.filter(id => ids.includes(id))
      const appended = ids.filter(id => !known.includes(id))
      return [...known, ...appended]
    })
  }, [wis])

  const orderedWis = useMemo(() => {
    if (wis.length === 0) return [] as MotionModuleSummary[]
    const byId = new Map(wis.map(w => [w.id, w] as const))
    const ordered: MotionModuleSummary[] = []
    orderedWiIds.forEach(id => {
      const wi = byId.get(id)
      if (wi) ordered.push(wi)
    })
    return ordered
  }, [wis, orderedWiIds])

  function toggleExpand(id: string) {
    setExpandedIds(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  async function handleDeleteWi(id: string, name: string) {
    if (!window.confirm(`確認刪除 WI「${name}」？`)) return
    try {
      await deleteWi.mutateAsync(id)
      showToast('已刪除 WI：' + name, 'ok')
    } catch (err) {
      showToast('刪除失敗：' + (err as Error).message, 'err')
    }
  }

  function beginRename(wi: MotionModuleSummary) {
    if (wi.status !== 'draft') {
      showToast('目前後端僅允許 draft WI 改名', 'err')
      return
    }
    setRenamingId(wi.id)
    setRenameDraft(wi.name_zh)
  }

  function cancelRename() {
    setRenamingId(null)
    setRenameDraft('')
  }

  async function saveRename(wi: MotionModuleSummary) {
    const name = renameDraft.trim().slice(0, 200)
    if (!name) {
      showToast('WI 名稱不可為空', 'err')
      return
    }
    if (name === wi.name_zh) {
      cancelRename()
      return
    }
    try {
      await updateModule.mutateAsync({ id: wi.id, body: { name_zh: name } })
      showToast(`已改名 WI：${name}`, 'ok')
      cancelRename()
    } catch (err) {
      showToast('改名失敗：' + (err as Error).message, 'err')
    }
  }

  function shiftOutlineWi(wiId: string, direction: -1 | 1) {
    setOrderedWiIds(prev => {
      const from = prev.indexOf(wiId)
      if (from < 0) return prev
      const to = from + direction
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      const [item] = next.splice(from, 1)
      next.splice(to, 0, item)
      return next
    })
  }

  const totalActions = orderedWis.reduce((s, w) => s + (w.action_count ?? 0), 0)

  return (
    <div className="bg-white rounded-xl border p-4 space-y-3" data-testid="wi-outline">
      <div className="flex items-baseline gap-2">
        <h2 className="font-semibold text-base">WI 大綱</h2>
        <span className="text-xs text-slate-400">
          {orderedWis.length} 筆 WI · {totalActions} 筆動作
        </span>
      </div>

      {isLoading && <p className="text-sm text-slate-400 text-center py-4">載入中…</p>}
      {!isLoading && orderedWis.length === 0 && (
        <p className="text-sm text-slate-400 text-center py-4">
          尚無 WI，請在上方動作清單勾選動作後建立 WI。
        </p>
      )}

      <div className="space-y-1.5 max-h-[42vh] overflow-y-auto pr-1">
        {orderedWis.map((wi, idx) => (
          <WiOutlineCard
            key={wi.id}
            wi={wi}
            index={idx}
            total={orderedWis.length}
            renaming={renamingId === wi.id}
            renameDraft={renameDraft}
            expanded={expandedIds.has(wi.id)}
            onToggle={() => toggleExpand(wi.id)}
            onDelete={() => handleDeleteWi(wi.id, wi.name_zh)}
            onMoveUp={() => shiftOutlineWi(wi.id, -1)}
            onMoveDown={() => shiftOutlineWi(wi.id, 1)}
            onStartRename={() => beginRename(wi)}
            onRenameDraftChange={setRenameDraft}
            onRenameCancel={cancelRename}
            onRenameSave={() => saveRename(wi)}
            renameBusy={updateModule.isPending}
            deleteDisabled={deleteWi.isPending}
            onInspect={onInspect}
            showToast={showToast}
            activeTarget={activeTarget}
          />
        ))}
      </div>
    </div>
  )
}

// ── 單一 WI 卡（展開時 lazy fetch detail） ─────────────────────────────────────
interface WiOutlineCardProps {
  wi: MotionModuleSummary
  index: number
  total: number
  renaming: boolean
  renameDraft: string
  expanded: boolean
  onToggle: () => void
  onDelete: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  onStartRename: () => void
  onRenameDraftChange: (value: string) => void
  onRenameCancel: () => void
  onRenameSave: () => void
  renameBusy: boolean
  deleteDisabled: boolean
  onInspect: WiOutlineSectionProps['onInspect']
  showToast: WiOutlineSectionProps['showToast']
  activeTarget?: { moduleId: string; rowIndex: number } | null
}

function WiOutlineCard({
  wi, index, total, renaming, renameDraft, expanded, onToggle, onDelete, onMoveUp, onMoveDown,
  onStartRename, onRenameDraftChange, onRenameCancel, onRenameSave, renameBusy,
  deleteDisabled, onInspect, showToast, activeTarget,
}: WiOutlineCardProps) {
  const { data: detail, isLoading } = useMotionModuleDetail(wi.id, expanded)
  const reorderRows = useReorderModuleRows()
  const deleteRow = useDeleteModuleRow()
  const rows = detail?.current_version_detail?.rows ?? []

  const totalTmu = wi.total_tmu ?? null
  const totalSec = totalTmu != null ? (totalTmu * TMU_SEC).toFixed(3) : null
  // 「已微調」：微調過即發過新版 → 版本 > 1
  const modified = (wi.current_version ?? 1) > 1

  // 上移/下移：ordered_indexes = 0..n-1 完整排列（i 與 j 互換）
  async function move(i: number, dir: -1 | 1) {
    const j = i + dir
    if (j < 0 || j >= rows.length) return
    const order = rows.map((_, k) => k)
    ;[order[i], order[j]] = [order[j], order[i]]
    try {
      await reorderRows.mutateAsync({ id: wi.id, orderedIndexes: order })
      showToast('已調整順序（發布新版本）', 'ok')
    } catch (err) {
      showToast('調序失敗：' + (err as Error).message, 'err')
    }
  }

  async function handleDeleteRow(i: number, label: string) {
    if (!window.confirm(`確認刪除此 WI 的第 ${i + 1} 列「${label}」？`)) return
    try {
      await deleteRow.mutateAsync({ id: wi.id, rowIndex: i })
      showToast('已刪除子列（發布新版本）', 'ok')
    } catch (err) {
      // 422：EMPTY_ROWS（刪到 0 列）/ SIMO_PAIR_INVALID（刪被指向的主列）
      showToast('刪除失敗：' + (err as Error).message, 'err')
    }
  }

  const rowOpsPending = reorderRows.isPending || deleteRow.isPending

  return (
    <div className="border rounded-lg bg-white" data-testid="wi-outline-card">
      {/* WI header 列 */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-slate-50 select-none"
        onClick={onToggle}
      >
        <span className="text-slate-300 text-xs w-5 text-right">{index + 1}</span>
        <span className={`text-slate-400 text-xs transition-transform ${expanded ? 'rotate-90' : ''}`}>▶</span>
        {renaming ? (
          <input
            className="flex-1 min-w-0 border rounded px-2 py-1 text-sm"
            value={renameDraft}
            maxLength={200}
            onClick={e => e.stopPropagation()}
            onChange={e => onRenameDraftChange(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') onRenameSave()
              if (e.key === 'Escape') onRenameCancel()
            }}
            autoFocus
            data-testid="wi-outline-rename-input"
          />
        ) : (
          <span className="flex-1 min-w-0 text-sm font-medium text-slate-700 truncate" title={wi.name_zh}>
            {wi.name_zh}
          </span>
        )}
        <span className="text-xs text-slate-500 whitespace-nowrap">
          {totalTmu != null
            ? <><b style={{ color: '#1a73e8' }}>{totalTmu}</b> TMU · <b className="text-red-600">{totalSec}</b>s</>
            : '—'}
        </span>
        <span className="text-xs text-slate-400 whitespace-nowrap">{wi.action_count ?? '—'} 動作</span>
        {modified && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200 whitespace-nowrap"
            title="此 WI 已微調（發布過新版本），與原始動作快照不同"
          >已微調</span>
        )}
        <span className="flex items-center gap-0.5" onClick={e => e.stopPropagation()}>
          {renaming ? (
            <>
              <button
                onClick={onRenameSave}
                disabled={renameBusy}
                className="text-xs px-1.5 py-0.5 border rounded border-emerald-300 text-emerald-700 hover:bg-emerald-50 disabled:opacity-40"
                data-testid="wi-outline-rename-save"
              >存</button>
              <button
                onClick={onRenameCancel}
                disabled={renameBusy}
                className="text-xs px-1.5 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40"
                data-testid="wi-outline-rename-cancel"
              >取消</button>
            </>
          ) : (
            <button
              onClick={onStartRename}
              className="text-slate-400 hover:text-slate-600 px-0.5 disabled:opacity-30"
              title={wi.status === 'draft' ? '重新命名 WI' : '僅 draft 可改名'}
              disabled={wi.status !== 'draft'}
              data-testid="wi-outline-rename"
            >✎</button>
          )}
          <button
            onClick={onMoveUp}
            disabled={index === 0 || renaming}
            className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5"
            title="上移 WI"
            data-testid="wi-outline-move-up"
          >↑</button>
          <button
            onClick={onMoveDown}
            disabled={index === total - 1 || renaming}
            className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5"
            title="下移 WI"
            data-testid="wi-outline-move-down"
          >↓</button>
        </span>
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          disabled={deleteDisabled}
          className="text-xs px-2 py-0.5 border border-red-200 text-red-600 rounded hover:bg-red-50 disabled:opacity-40"
        >
          刪除
        </button>
      </div>

      {/* 展開：子列（每列權威 computed） */}
      {expanded && (
        <div className="border-t px-3 py-1.5">
          {isLoading && <p className="text-xs text-slate-400 py-2">載入明細…</p>}
          {!isLoading && rows.length === 0 && (
            <p className="text-xs text-slate-400 py-2">（此 WI 尚無已發布版本）</p>
          )}
          {rows.map((row, i) => {
            const seq = row.cycle?.['seq'] as string | undefined
            const isSimo = row.simo_pair_index != null
            const isActive = activeTarget?.moduleId === wi.id && activeTarget?.rowIndex === i
            const label = row.sub_activity ?? row.narrative_zh ?? `第 ${i + 1} 列`
            return (
              <div
                key={i}
                className={`flex items-center gap-2 py-1 px-1.5 rounded text-xs cursor-pointer ${
                  isActive ? 'bg-blue-50 border border-blue-200' : 'hover:bg-sky-50'
                }`}
                onClick={() => onInspect(wi, i, row)}
                title="點擊開啟右側檢視/微調"
              >
                <span className="text-slate-400 w-4 text-right shrink-0">{i + 1}.</span>
                {seq && (
                  <span className={`px-1 py-0.5 rounded font-medium shrink-0 ${
                    seq === 'GM' ? 'bg-green-100 text-green-700' : 'bg-purple-100 text-purple-700'
                  }`}>{seq}</span>
                )}
                <span className="text-slate-500 shrink-0">{HAND_NAME[row.hand] ?? row.hand}</span>
                <span className="flex-1 min-w-0 truncate text-slate-700" title={row.narrative_zh ?? label}>
                  {row.narrative_zh ?? label}
                </span>
                <span className="text-slate-400 shrink-0">×{row.frequency}</span>
                <span className="shrink-0">
                  Base <b style={{ color: '#1a73e8' }}>{row.computed?.total_tmu ?? '—'}</b>
                </span>
                <span className="shrink-0">
                  Eff <b className="text-red-600">{row.computed?.eff_tmu ?? '—'}</b>
                </span>
                {/* 納入（後端 contribution_tmu 權威）：SIMO 從屬列＝0 且劃線（ADR-020） */}
                <span className="shrink-0" title="納入 WI 合計的時間（SIMO 從屬列為 0）">
                  納入{' '}
                  {row.computed
                    ? (row.computed.contribution_tmu === 0
                        ? <b className="line-through text-slate-400">0</b>
                        : <b className="text-slate-700">{row.computed.contribution_tmu}</b>)
                    : <b className="text-slate-400">—</b>}
                </span>
                {isSimo && (
                  <span className="px-1 py-0.5 rounded bg-orange-100 text-orange-700 shrink-0"
                    title={`SIMO 從屬（主列 #${(row.simo_pair_index ?? 0) + 1}），貢獻 0`}>SIMO</span>
                )}
                <span className="flex items-center gap-0.5 shrink-0" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={() => onInspect(wi, i, row)}
                    disabled={rowOpsPending}
                    className="text-sky-500 hover:text-sky-700 disabled:opacity-20 px-0.5"
                    title="調整此列（含 SIMO / 次數）"
                    data-testid="wi-outline-open-inspector"
                  >✎</button>
                  <button
                    onClick={() => move(i, -1)}
                    disabled={i === 0 || rowOpsPending}
                    className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5"
                    title="上移（發布新版本）"
                  >↑</button>
                  <button
                    onClick={() => move(i, 1)}
                    disabled={i === rows.length - 1 || rowOpsPending}
                    className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5"
                    title="下移（發布新版本）"
                  >↓</button>
                  <button
                    onClick={() => handleDeleteRow(i, label)}
                    disabled={rowOpsPending}
                    className="text-red-400 hover:text-red-600 disabled:opacity-20 px-0.5"
                    title="刪除此列（發布新版本）"
                  >✕</button>
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
