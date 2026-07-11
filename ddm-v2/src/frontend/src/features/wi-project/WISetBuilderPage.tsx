/**
 * F-04 WISetBuilderPage — WI 專案建立
 *
 * 功能：
 *   1. 建立 WI 組合專案（本地 state，project_code / name / description）
 *   2. 搜尋 MiStatement library（GET /api/v2/search?types=motion_module&q=）
 *   3. 從搜尋結果快照加入 WI（fetches detail for TMU data）
 *   4. 上下重排 + 逐項備註
 *   5. 彙總列（WI 數 / 總 TMU / CT 秒）
 */
import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../shared/api/client'
import { TMU_SEC } from '../../shared/config'
import { useMe, canEdit } from '../../shared/auth/useMe'

// ─── Types ────────────────────────────────────────────────────────────────────

interface SearchHit {
  doc_type: string
  ref_id: string
  score: number
  match_type: string
  snippet: string
}

interface ModuleDetail {
  id: string
  name_zh: string
  status: string
  current_version: number
  total_tmu: number
}

interface WiSetItem {
  id: string          // crypto.randomUUID() local key
  module_id: string
  module_name: string
  total_tmu: number
  version_no: number
  notes: string
}

interface ProjectForm {
  code: string
  name: string
  description: string
}

// ─── Search hook (debounced) ──────────────────────────────────────────────────

function useSearch(q: string) {
  return useQuery<{ hits: SearchHit[]; semantic: boolean }>({
    queryKey: ['wi-project-search', q],
    queryFn: () => apiGet(`/api/v2/search?types=motion_module&q=${encodeURIComponent(q)}&limit=20`),
    enabled: q.trim().length >= 1,
    staleTime: 30_000,
  })
}

function useModuleDetail(moduleId: string | null) {
  return useQuery<ModuleDetail>({
    queryKey: ['wi-module-detail', moduleId],
    queryFn: () => apiGet(`/api/v2/motion-modules/${moduleId}`),
    enabled: !!moduleId,
    staleTime: 60_000,
  })
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ProjectFormPanel({ form, onChange, editable }: {
  form: ProjectForm
  onChange: (f: ProjectForm) => void
  editable: boolean
}) {
  const inp = 'border rounded px-2 py-1 text-sm w-full disabled:bg-slate-50'
  return (
    <div className="bg-white rounded-xl border p-4">
      <h2 className="font-semibold mb-3">專案資訊</h2>
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          專案代碼
          <input className={inp} value={form.code} disabled={!editable}
            onChange={e => onChange({ ...form, code: e.target.value })} placeholder="e.g. WIS-2026-001" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          專案名稱
          <input className={inp} value={form.name} disabled={!editable}
            onChange={e => onChange({ ...form, name: e.target.value })} placeholder="e.g. 組裝站 WI 組合" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500 col-span-2">
          說明
          <input className={inp} value={form.description} disabled={!editable}
            onChange={e => onChange({ ...form, description: e.target.value })} placeholder="用途、製程、備注…" />
        </label>
      </div>
    </div>
  )
}

function AddByModuleId({ onAdd }: { onAdd: (id: string) => void }) {
  const [pending, setPending] = useState<string | null>(null)
  const { data, isFetching } = useModuleDetail(pending)

  useEffect(() => {
    if (data && pending) {
      onAdd(data.id)
      setPending(null)
    }
  }, [data, pending, onAdd])

  return { trigger: (id: string) => setPending(id), loading: isFetching && !!pending }
}

function SearchPanel({ onAddModule }: { onAddModule: (moduleId: string) => void }) {
  const [raw, setRaw] = useState('')
  const [q, setQ] = useState('')

  // Debounce
  useEffect(() => {
    const t = setTimeout(() => setQ(raw.trim()), 300)
    return () => clearTimeout(t)
  }, [raw])

  const { data, isFetching } = useSearch(q)
  const hits = data?.hits.filter(h => h.doc_type === 'motion_module') ?? []

  return (
    <div className="bg-white rounded-xl border p-4 flex flex-col gap-3">
      <h2 className="font-semibold">搜尋 WI 庫</h2>
      <input
        className="border rounded px-2 py-1 text-sm"
        value={raw}
        onChange={e => setRaw(e.target.value)}
        placeholder="輸入動作描述或代碼搜尋…"
      />
      {isFetching && <p className="text-xs text-slate-400">搜尋中…</p>}
      {!isFetching && q && hits.length === 0 && (
        <p className="text-xs text-slate-400">無結果</p>
      )}
      <ul className="divide-y max-h-80 overflow-y-auto">
        {hits.map(h => (
          <li key={h.ref_id} className="flex items-start gap-2 py-2">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{h.snippet || h.ref_id}</p>
              <p className="text-xs text-slate-400">{h.match_type} · score {h.score.toFixed(2)}</p>
            </div>
            <button
              onClick={() => onAddModule(h.ref_id)}
              className="flex-shrink-0 px-2 py-0.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              + 加入
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function WiSetList({ items, editable, onRemove, onMoveUp, onMoveDown, onNoteChange }: {
  items: WiSetItem[]
  editable: boolean
  onRemove: (id: string) => void
  onMoveUp: (id: string) => void
  onMoveDown: (id: string) => void
  onNoteChange: (id: string, note: string) => void
}) {
  if (items.length === 0) {
    return (
      <div className="bg-white rounded-xl border p-6 text-slate-400 text-sm text-center">
        尚未加入任何 WI —— 從右側搜尋後按「+ 加入」
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-100 text-left">
            <th className="p-2 w-8">#</th>
            <th className="p-2">WI 名稱</th>
            <th className="p-2 text-right">Base TMU</th>
            <th className="p-2 text-right">CT(秒)</th>
            <th className="p-2">備註</th>
            {editable && <th className="p-2 w-24">操作</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((item, idx) => (
            <tr key={item.id} className="border-t">
              <td className="p-2 text-slate-400">{idx + 1}</td>
              <td className="p-2">
                <span className="font-medium">{item.module_name}</span>
                <span className="ml-2 text-xs text-slate-400">v{item.version_no}</span>
              </td>
              <td className="p-2 text-right font-mono">{item.total_tmu}</td>
              <td className="p-2 text-right font-mono text-slate-600">
                {(item.total_tmu * TMU_SEC).toFixed(2)}
              </td>
              <td className="p-2">
                <input
                  className="border rounded px-1 py-0.5 text-xs w-full"
                  value={item.notes}
                  disabled={!editable}
                  onChange={e => onNoteChange(item.id, e.target.value)}
                  placeholder="備注…"
                />
              </td>
              {editable && (
                <td className="p-2">
                  <div className="flex gap-1">
                    <button onClick={() => onMoveUp(item.id)} disabled={idx === 0}
                      className="px-1.5 py-0.5 text-xs border rounded disabled:opacity-30 hover:bg-slate-100">↑</button>
                    <button onClick={() => onMoveDown(item.id)} disabled={idx === items.length - 1}
                      className="px-1.5 py-0.5 text-xs border rounded disabled:opacity-30 hover:bg-slate-100">↓</button>
                    <button onClick={() => onRemove(item.id)}
                      className="px-1.5 py-0.5 text-xs border rounded text-red-600 hover:bg-red-50">✕</button>
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SummaryBar({ items }: { items: WiSetItem[] }) {
  const totalTmu = items.reduce((s, i) => s + i.total_tmu, 0)
  const totalSec = totalTmu * TMU_SEC
  return (
    <div className="bg-slate-800 text-white rounded-xl px-5 py-3 flex gap-8 text-sm">
      <span>WI 數：<b className="text-blue-300 text-base ml-1">{items.length}</b></span>
      <span>總 TMU：<b className="text-emerald-300 text-base ml-1">{totalTmu.toFixed(1)}</b></span>
      <span>總 CT(秒)：<b className="text-amber-300 text-base ml-1">{totalSec.toFixed(2)}</b></span>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function WISetBuilderPage() {
  const { data: me } = useMe()
  const editable = canEdit(me)

  const [form, setForm] = useState<ProjectForm>({ code: '', name: '', description: '' })
  const [items, setItems] = useState<WiSetItem[]>([])
  const [pendingModuleId, setPendingModuleId] = useState<string | null>(null)

  const { data: pendingDetail, isFetching: fetching } = useModuleDetail(pendingModuleId)

  useEffect(() => {
    if (!pendingDetail || !pendingModuleId) return
    setItems(prev => {
      if (prev.some(i => i.module_id === pendingDetail.id)) return prev
      return [...prev, {
        id: crypto.randomUUID(),
        module_id: pendingDetail.id,
        module_name: pendingDetail.name_zh,
        total_tmu: pendingDetail.total_tmu,
        version_no: pendingDetail.current_version,
        notes: '',
      }]
    })
    setPendingModuleId(null)
  }, [pendingDetail, pendingModuleId])

  const handleAddModule = useCallback((moduleId: string) => {
    setPendingModuleId(moduleId)
  }, [])

  const handleRemove = useCallback((id: string) => {
    setItems(prev => prev.filter(i => i.id !== id))
  }, [])

  const handleMoveUp = useCallback((id: string) => {
    setItems(prev => {
      const idx = prev.findIndex(i => i.id === id)
      if (idx <= 0) return prev
      const next = [...prev]
      ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
      return next
    })
  }, [])

  const handleMoveDown = useCallback((id: string) => {
    setItems(prev => {
      const idx = prev.findIndex(i => i.id === id)
      if (idx < 0 || idx >= prev.length - 1) return prev
      const next = [...prev]
      ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
      return next
    })
  }, [])

  const handleNoteChange = useCallback((id: string, note: string) => {
    setItems(prev => prev.map(i => i.id === id ? { ...i, notes: note } : i))
  }, [])

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Header */}
      <div className="bg-white rounded-xl border px-5 py-3 flex items-center justify-between">
        <div>
          <h1 className="font-semibold text-base">WI 專案建立</h1>
          <p className="text-xs text-slate-400">從 WI 庫搜尋並組合 WI 集合，快照版本、排序、加備注</p>
        </div>
        {fetching && <span className="text-xs text-blue-500">載入模組資訊…</span>}
      </div>

      {/* Project form */}
      <ProjectFormPanel form={form} onChange={setForm} editable={editable} />

      {/* Main area: WI list + search */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Left: WI list */}
        <div className="flex-1 min-w-0 flex flex-col gap-3 overflow-y-auto">
          <WiSetList
            items={items}
            editable={editable}
            onRemove={handleRemove}
            onMoveUp={handleMoveUp}
            onMoveDown={handleMoveDown}
            onNoteChange={handleNoteChange}
          />
        </div>

        {/* Right: search panel (fixed 320px) */}
        {editable && (
          <div className="w-80 flex-shrink-0 overflow-y-auto">
            <SearchPanel onAddModule={handleAddModule} />
          </div>
        )}
      </div>

      {/* Summary bar */}
      <SummaryBar items={items} />
    </div>
  )
}
