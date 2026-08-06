import { TMU_SEC } from '../../shared/config'
import type { MotionModuleSummary } from './api'

interface MiCompositionTableProps {
  modules: MotionModuleSummary[]
  modulesLoading: boolean
  searchQ: string
  selectedIds: Set<string>
  selectedSimoPairs: Record<string, string>
  editingModuleId: string | null
  draggingId: string | null
  loadingModuleId: string | null
  freqDraft: Record<string, string>
  freqSavingIds: Set<string>
  clonePending: boolean
  deletePending: boolean
  getModuleSeq: (mod: MotionModuleSummary) => string
  getModuleHand: (mod: MotionModuleSummary) => string
  onSelectAll: (checked: boolean) => void
  onToggleSelect: (id: string) => void
  onShiftOrderedModule: (id: string, direction: -1 | 1) => void
  onDropReorder: (sourceId: string, targetId: string) => void
  onDragStart: (id: string) => void
  onDragEnd: () => void
  onFreqInput: (mod: MotionModuleSummary, raw: string) => void
  onToggleListSimo: (moduleId: string, enabled: boolean) => void
  onSetListSimoPair: (moduleId: string, leaderId: string | null) => void
  onLoadModule: (mod: MotionModuleSummary) => void
  onReworkModule: (mod: MotionModuleSummary) => void
  onCloneModule: (id: string, name: string) => void
  onDeleteModule: (id: string, name: string) => void
}

export function MiCompositionTable({
  modules,
  modulesLoading,
  searchQ,
  selectedIds,
  selectedSimoPairs,
  editingModuleId,
  draggingId,
  loadingModuleId,
  freqDraft,
  freqSavingIds,
  clonePending,
  deletePending,
  getModuleSeq,
  getModuleHand,
  onSelectAll,
  onToggleSelect,
  onShiftOrderedModule,
  onDropReorder,
  onDragStart,
  onDragEnd,
  onFreqInput,
  onToggleListSimo,
  onSetListSimoPair,
  onLoadModule,
  onReworkModule,
  onCloneModule,
  onDeleteModule,
}: MiCompositionTableProps) {
  return (
    <div className="overflow-x-auto">
      <div className="max-h-[42vh] overflow-y-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 text-left">
              <th className="p-1.5 w-12 text-center">排序</th>
              <th className="p-1.5 w-7 text-center">
                <input
                  type="checkbox"
                  checked={modules.length > 0 && modules.every(m => selectedIds.has(m.id))}
                  onChange={e => onSelectAll(e.target.checked)}
                />
              </th>
              <th className="p-1.5 w-8">#</th>
              <th className="p-1.5 w-14">手</th>
              <th className="p-1.5">WI / 動作描述</th>
              <th className="p-1.5 w-14">類型</th>
              <th className="p-1.5 w-20 text-right">Base TMU</th>
              <th className="p-1.5 w-14 text-right">頻率</th>
              <th className="p-1.5 w-36">SIMO</th>
              <th className="p-1.5 w-20 text-right">Eff TMU</th>
              <th className="p-1.5 w-20 text-right">CT(秒)</th>
              <th className="p-1.5 w-36 text-center">操作</th>
            </tr>
          </thead>
          <tbody>
            {modulesLoading && (
              <tr><td colSpan={12} className="p-3 text-slate-400 text-center">載入中…</td></tr>
            )}
            {!modulesLoading && modules.length === 0 && (
              <tr><td colSpan={12} className="p-3 text-slate-400 text-center">
                {searchQ ? '無相符動作' : '尚無動作，請在上方建立器新增。'}
              </td></tr>
            )}
            {modules.map((mod, i) => {
              const isSelected = selectedIds.has(mod.id)
              const modSeq = getModuleSeq(mod)
              const baseTmu = mod.base_tmu ?? null
              const rowFreq = mod.frequency ?? null
              const effTmuRow = mod.total_tmu ?? null
              const freqSaving = freqSavingIds.has(mod.id)
              const isMainRow = Object.values(selectedSimoPairs).includes(mod.id)
              const simoEnabled = Object.prototype.hasOwnProperty.call(selectedSimoPairs, mod.id)
              const simoPair = selectedSimoPairs[mod.id] ?? ''
              const leaderName = simoPair ? modules.find(candidate => candidate.id === simoPair)?.name_zh ?? '已選主列' : ''
              const simoCandidates = modules.filter(candidate =>
                selectedIds.has(candidate.id)
                && candidate.id !== mod.id
                && !selectedSimoPairs[candidate.id],
              )
              const rowCls = [
                'border-t',
                editingModuleId === mod.id ? 'bg-amber-50' : isSelected ? 'bg-blue-50' : '',
                draggingId === mod.id ? 'opacity-50' : '',
              ].filter(Boolean).join(' ')
              return (
                <tr
                  key={mod.id}
                  className={rowCls}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => {
                    e.preventDefault()
                    const sourceId = e.dataTransfer.getData('text/plain') || draggingId
                    if (sourceId) onDropReorder(sourceId, mod.id)
                    onDragEnd()
                  }}
                >
                  <td className="p-1.5 text-center whitespace-nowrap">
                    <button
                      onClick={() => onShiftOrderedModule(mod.id, -1)}
                      disabled={i === 0}
                      className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5"
                      title="上移"
                      data-testid="action-row-move-up"
                    >↑</button>
                    <button
                      onClick={() => onShiftOrderedModule(mod.id, 1)}
                      disabled={i === modules.length - 1}
                      className="text-slate-400 hover:text-slate-600 disabled:opacity-20 px-0.5"
                      title="下移"
                      data-testid="action-row-move-down"
                    >↓</button>
                    <button
                      draggable
                      onDragStart={e => {
                        e.dataTransfer.setData('text/plain', mod.id)
                        onDragStart(mod.id)
                      }}
                      onDragEnd={onDragEnd}
                      className="cursor-grab text-slate-400 hover:text-slate-600 px-0.5"
                      title="拖曳排序"
                      data-testid="action-row-drag-handle"
                    >⋮⋮</button>
                  </td>
                  <td className="p-1.5 text-center">
                    <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(mod.id)} />
                  </td>
                  <td className="p-1.5">{i + 1}</td>
                  <td className="p-1.5">{getModuleHand(mod)}</td>
                  <td className="p-1.5 max-w-md">
                    <span className="truncate block" title={mod.name_zh}>{mod.name_zh}</span>
                    {mod.source === 'ai' && (
                      <span className="text-[10px] px-1 py-0.5 rounded bg-violet-100 text-violet-700">AI</span>
                    )}
                  </td>
                  <td className="p-1.5">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                      modSeq === 'GM' ? 'bg-green-100 text-green-700'
                      : modSeq === 'CM' ? 'bg-purple-100 text-purple-700'
                      : 'bg-slate-100 text-slate-500'
                    }`}>{modSeq}</span>
                  </td>
                  <td className="p-1.5 text-right">
                    {baseTmu != null ? <span>{baseTmu}</span> : '—'}
                  </td>
                  <td className="p-1.5 text-right">
                    {rowFreq == null ? '—' : (
                      <input
                        type="number" min={1}
                        className="border rounded w-14 px-1 py-0.5 text-sm text-right"
                        value={freqDraft[mod.id] ?? String(rowFreq)}
                        onChange={e => onFreqInput(mod, e.target.value)}
                        aria-label={`${mod.name_zh} 頻率`}
                        data-testid="action-row-freq"
                      />
                    )}
                  </td>
                  <td className="p-1.5">
                    {isSelected ? (
                      <div className="space-y-1">
                        <label className="flex items-center gap-1 text-xs text-slate-600">
                          <input
                            type="checkbox"
                            checked={simoEnabled}
                            disabled={isMainRow}
                            onChange={e => onToggleListSimo(mod.id, e.target.checked)}
                            data-testid="action-row-simo-checkbox"
                          />
                          <span>{isMainRow ? 'SIMO 主列' : '設為 SIMO 從屬'}</span>
                        </label>
                        <select
                          className="w-full rounded border px-2 py-1 text-xs disabled:bg-slate-100"
                          value={simoPair}
                          disabled={isMainRow || !simoEnabled}
                          onChange={e => onSetListSimoPair(mod.id, e.target.value || null)}
                          data-testid="action-row-simo"
                        >
                          <option value="">請選主列</option>
                          {simoCandidates.map(candidate => (
                            <option key={candidate.id} value={candidate.id}>
                              同動於：{candidate.name_zh}
                            </option>
                          ))}
                        </select>
                        {isMainRow && <span className="text-[10px] text-sky-600">SIMO 主列</span>}
                        {!isMainRow && leaderName && <span className="text-[10px] text-orange-600">從屬列 → {leaderName}</span>}
                        {!isMainRow && simoEnabled && !leaderName && <span className="text-[10px] text-amber-600">請再選一個主列</span>}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-300">—</span>
                    )}
                  </td>
                  <td className="p-1.5 text-right">
                    {freqSaving
                      ? <span className="text-xs text-slate-400">計算中…</span>
                      : effTmuRow != null
                        ? <b style={{ color: '#1a73e8' }}>{effTmuRow}</b>
                        : '—'}
                  </td>
                  <td className="p-1.5 text-right">
                    {freqSaving ? '…' : effTmuRow != null ? (effTmuRow * TMU_SEC).toFixed(3) : '—'}
                  </td>
                  <td className="p-1.5 text-center whitespace-nowrap">
                    <button
                      onClick={() => onLoadModule(mod)}
                      disabled={loadingModuleId !== null}
                      className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40"
                      title="載回建立器編輯"
                    >
                      {loadingModuleId === mod.id ? '載入中…' : '✏️ 編輯'}
                    </button>
                    <button
                      onClick={() => onReworkModule(mod)}
                      disabled={loadingModuleId !== null}
                      className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40 ml-1"
                      title="載入為新動作"
                    >
                      ↺ 再做一份
                    </button>
                    <button
                      onClick={() => onCloneModule(mod.id, mod.name_zh)}
                      disabled={clonePending}
                      className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40 ml-1"
                    >
                      📋 複製
                    </button>
                    <button
                      onClick={() => onDeleteModule(mod.id, mod.name_zh)}
                      disabled={deletePending}
                      className="text-xs px-2 py-0.5 border border-red-200 text-red-600 rounded hover:bg-red-50 disabled:opacity-40 ml-1"
                    >
                      ✕ 刪除
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}