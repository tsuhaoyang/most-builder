/**
 * F-04 WISetBuilderPage — WI 專案建立 (complete rewrite)
 *
 * Sections:
 *   A — 專案資訊 (ProjectMetadataForm)
 *   B — WI 庫搜尋 (WIPoolSearch, fetch-once + client-side filter, lazy expand)
 *   C — 已選 WI 清單 (SelectedWISetTable, HTML5 DnD + ↑↓ + multi-select remove)
 *   D — 彙總 (WISetSummary, 5 stat cards)
 *   E — 操作按鈕 (save/create, duplicate, delete)
 *
 * Rules:
 *   - All numbers/sentences from backend API (DISC-02/07)
 *   - No hardcoded defaults (DISC-06)
 *   - TanStack Query for all async — no local data fabrication
 */
import React, { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete } from '../../shared/api/client'
import { TMU_SEC } from '../../shared/config'
import { useMe, canEdit } from '../../shared/auth/useMe'

// ─── Domain types ──────────────────────────────────────────────────────────────

interface PoolModuleRow {
  hand: string
  frequency: number
  cycle: Record<string, unknown>
  sub_activity: string | null
  /** 後端組句（DISC-02/07：前端不組句）；舊版本資料可能缺 → fallback sub_activity */
  narrative_zh?: string | null
  /** ADR-020：非 null = SIMO 從屬列（宣告者），貢獻 0 */
  simo_pair_index?: number | null
  /** ADR-022 批次 A：publish 時引擎算好持久化；舊資料缺 → UI 顯示 '—'，不假造 */
  computed?: {
    total_tmu: number
    total_seconds: number
    eff_tmu: number
    contribution_tmu: number
  } | null
}

/**
 * Shape returned by GET /api/v2/motion-modules?category=wi-template
 *
 * 合約（audit §0.1 更正版）：rows 巢狀於 current_version_detail —— list 端點
 * 該欄=null，detail (GET /{id}) 才有；top-level total_tmu / action_count 為
 * 後端摘要欄（無已發布版本時為 null → UI 顯示 '—'，不得假裝是 0）。
 * ADR-022 §WI 專案建立：庫只列 category='wi-template'（純 WI 級，對齊 v3）。
 */
interface PoolModule {
  id: string
  name_zh: string
  status: string
  total_tmu?: number | null
  action_count?: number | null
  created_at: string
  current_version_detail?: {
    version_no: number
    rows: PoolModuleRow[]
    total_tmu: number
    total_seconds?: number
    narrative_zh?: string | null
  } | null
}

interface WiSetItemOut {
  id: string
  project_id: string
  seq_no: number
  wi_template_id: string | null
  wi_code_snapshot: string | null
  wi_name_snapshot: string
  action_count_snapshot: number
  total_tmu_snapshot: number
  total_seconds_snapshot: number
  notes: string | null
  created_at: string
  updated_at: string
}

interface WiSetProjectOut {
  id: string
  project_code: string
  name: string
  site: string | null
  bu: string | null
  process: string | null
  family: string | null
  model: string | null
  description: string | null
  status: string
  created_by: string
  items: WiSetItemOut[]
  created_at: string
  updated_at: string
}

interface ProjectForm {
  project_code: string
  name: string
  site: string
  bu: string
  process: string
  family: string
  model: string
  description: string
}

const EMPTY_FORM: ProjectForm = {
  project_code: '',
  name: '',
  site: '',
  bu: '',
  process: '',
  family: '',
  model: '',
  description: '',
}

const SITE_OPTIONS = ['TAO', 'IPT', 'SQT', 'ITE', 'IMX', 'ICZ'] as const

// ─── Status helpers ────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  active: 'bg-blue-100 text-blue-700',
  archived: 'bg-amber-100 text-amber-700',
}

const STATUS_ZH: Record<string, string> = {
  draft: '草稿',
  active: '作用中',
  archived: '已封存',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium ${
        STATUS_BADGE[status] ?? 'bg-slate-100 text-slate-500'
      }`}
    >
      {STATUS_ZH[status] ?? status}
    </span>
  )
}

// ─── Query keys ────────────────────────────────────────────────────────────────

const QK_PROJECTS = 'wi-set-projects' as const
const QK_POOL = 'wi-pool-modules' as const
const QK_MODULE_DETAIL = 'wi-pool-module-detail' as const

// ─── API hooks ─────────────────────────────────────────────────────────────────

function useProjectList() {
  return useQuery<WiSetProjectOut[]>({
    queryKey: [QK_PROJECTS],
    queryFn: () => apiGet<WiSetProjectOut[]>('/api/v2/wi-set-projects'),
    staleTime: 30_000,
  })
}

function useProject(id: string | null) {
  return useQuery<WiSetProjectOut>({
    queryKey: [QK_PROJECTS, id],
    queryFn: () => apiGet<WiSetProjectOut>(`/api/v2/wi-set-projects/${id}`),
    enabled: !!id,
    staleTime: 10_000,
  })
}

function usePoolModules() {
  return useQuery<PoolModule[]>({
    queryKey: [QK_POOL],
    // ADR-022 §WI 專案建立：庫過濾為純 WI 級（category='wi-template'），
    // 單動作素材（category='action'）與 null-category 範本不再混入。
    queryFn: () =>
      apiGet<PoolModule[]>('/api/v2/motion-modules?category=wi-template'),
    staleTime: 120_000,
  })
}

function useModuleDetail(id: string | null) {
  return useQuery<PoolModule>({
    queryKey: [QK_MODULE_DETAIL, id],
    queryFn: () => apiGet<PoolModule>(`/api/v2/motion-modules/${id}`),
    enabled: !!id,
    staleTime: 300_000,
  })
}

interface CreateProjectPayload { form: ProjectForm }
interface UpdateProjectPayload { id: string; form: ProjectForm }

function useCreateProject() {
  const qc = useQueryClient()
  return useMutation<WiSetProjectOut, Error, CreateProjectPayload>({
    mutationFn: ({ form }) =>
      apiPost<WiSetProjectOut>('/api/v2/wi-set-projects', {
        project_code: form.project_code.trim() || `WIS-${Date.now()}`,
        name: form.name.trim() || '未命名專案',
        site: form.site || null,
        bu: form.bu.trim() || null,
        process: form.process.trim() || null,
        family: form.family.trim() || null,
        model: form.model.trim() || null,
        description: form.description.trim() || null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK_PROJECTS] }),
  })
}

function useUpdateProject() {
  const qc = useQueryClient()
  return useMutation<WiSetProjectOut, Error, UpdateProjectPayload>({
    mutationFn: ({ id, form }) =>
      apiPut<WiSetProjectOut>(`/api/v2/wi-set-projects/${id}`, {
        project_code: form.project_code.trim() || undefined,
        name: form.name.trim() || undefined,
        site: form.site || null,
        bu: form.bu.trim() || null,
        process: form.process.trim() || null,
        family: form.family.trim() || null,
        model: form.model.trim() || null,
        description: form.description.trim() || null,
      }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: [QK_PROJECTS] })
      qc.invalidateQueries({ queryKey: [QK_PROJECTS, vars.id] })
    },
  })
}

/**
 * POST /wi-set-projects/{pid}/items 只送 {wi_template_id, notes?}——
 * 快照欄（wi_code/name/action_count/total_tmu/total_seconds）由伺服器
 * 依模組當前版本回填（審查 8.2：前端不得自算快照）。
 */
interface AddItemPayload {
  projectId: string
  wi_template_id: string
  notes: string | null
}

function useAddItem() {
  const qc = useQueryClient()
  return useMutation<WiSetItemOut, Error, AddItemPayload>({
    mutationFn: ({ projectId, ...body }) =>
      apiPost<WiSetItemOut>(`/api/v2/wi-set-projects/${projectId}/items`, body),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: [QK_PROJECTS, vars.projectId] }),
  })
}

function useRemoveItem() {
  const qc = useQueryClient()
  return useMutation<void, Error, { projectId: string; itemId: string }>({
    mutationFn: ({ projectId, itemId }) =>
      apiDelete(`/api/v2/wi-set-projects/${projectId}/items/${itemId}`),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: [QK_PROJECTS, vars.projectId] }),
  })
}

function useReorderItems() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, { projectId: string; orderedIds: string[] }>({
    mutationFn: ({ projectId, orderedIds }) =>
      apiPut(`/api/v2/wi-set-projects/${projectId}/items/reorder`, {
        ordered_ids: orderedIds,
      }),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: [QK_PROJECTS, vars.projectId] }),
  })
}

function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiDelete(`/api/v2/wi-set-projects/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK_PROJECTS] }),
  })
}

function useDuplicateProject() {
  const qc = useQueryClient()
  return useMutation<WiSetProjectOut, Error, string>({
    mutationFn: (id) =>
      apiPost<WiSetProjectOut>(`/api/v2/wi-set-projects/${id}/duplicate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [QK_PROJECTS] }),
  })
}

// ─── Section A: ProjectMetadataForm ───────────────────────────────────────────

const INP =
  'border rounded px-2 py-1 text-sm w-full disabled:bg-slate-50 focus:outline-none focus:ring-1 focus:ring-blue-400'

interface ProjectMetadataFormProps {
  form: ProjectForm
  status?: string
  onChange: (f: ProjectForm) => void
  editable: boolean
}

function ProjectMetadataForm({ form, status, onChange, editable }: ProjectMetadataFormProps) {
  const autoCode = [form.site, form.bu, form.process, form.family, form.model]
    .filter(Boolean)
    .join('-')

  return (
    <div className="bg-white rounded-xl border p-4">
      <h2 className="font-semibold text-sm mb-3 text-slate-700">A — 專案資訊</h2>

      {/* Row 1: project_code | name | status */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          專案代碼
          <div className="flex gap-1">
            <input
              className={INP + ' flex-1 min-w-0'}
              value={form.project_code}
              disabled={!editable}
              onChange={(e) => onChange({ ...form, project_code: e.target.value })}
              placeholder="e.g. TAO-BU1-L10"
            />
            <button
              type="button"
              disabled={!editable || !autoCode}
              onClick={() => onChange({ ...form, project_code: autoCode })}
              className="px-2 py-1 text-xs border rounded bg-slate-50 hover:bg-slate-100 disabled:opacity-40 whitespace-nowrap"
              title="自動填入 site-bu-process-family-model"
            >
              Auto
            </button>
          </div>
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-500">
          專案名稱 <span className="text-red-400">*</span>
          <input
            className={INP}
            value={form.name}
            disabled={!editable}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            placeholder="e.g. 組裝站 WI 組合"
          />
        </label>

        <div className="flex flex-col gap-1 text-xs text-slate-500">
          狀態
          <div className="mt-1.5">
            {status ? <StatusBadge status={status} /> : <span className="text-slate-300">—</span>}
          </div>
        </div>
      </div>

      {/* Row 2: site | bu | process | family */}
      <div className="grid grid-cols-4 gap-3 mb-3">
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          廠區 (Site)
          <select
            className={INP}
            value={form.site}
            disabled={!editable}
            onChange={(e) => onChange({ ...form, site: e.target.value })}
          >
            <option value="">— 選擇 —</option>
            {SITE_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-500">
          BU
          <input
            className={INP}
            value={form.bu}
            disabled={!editable}
            onChange={(e) => onChange({ ...form, bu: e.target.value })}
            placeholder="e.g. BU1"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-500">
          製程 (Process)
          <input
            className={INP}
            value={form.process}
            disabled={!editable}
            onChange={(e) => onChange({ ...form, process: e.target.value })}
            placeholder="e.g. L10_ASSY"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Family
          <input
            className={INP}
            value={form.family}
            disabled={!editable}
            onChange={(e) => onChange({ ...form, family: e.target.value })}
            placeholder="e.g. AMD"
          />
        </label>
      </div>

      {/* Row 3: model | description */}
      <div className="grid grid-cols-4 gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          機型 (Model)
          <input
            className={INP}
            value={form.model}
            disabled={!editable}
            onChange={(e) => onChange({ ...form, model: e.target.value })}
            placeholder="e.g. M123"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-500 col-span-3">
          說明
          <textarea
            className={INP + ' resize-none'}
            rows={2}
            value={form.description}
            disabled={!editable}
            onChange={(e) => onChange({ ...form, description: e.target.value })}
            placeholder="用途、製程說明…"
          />
        </label>
      </div>
    </div>
  )
}

// ─── Section B: WIPoolSearch ───────────────────────────────────────────────────

/** 主表欄數（checkbox + WI Code + 名稱 + 動作數 + Total TMU + CT + 建立日 + 展開） */
const POOL_COL_SPAN = 8

/**
 * Lazy-loaded expand sub-table（ADR-022 §WI 專案建立，對照 v3 展開子列）：
 * #｜動作句（narrative_zh ?? sub_activity）｜手｜Base TMU｜頻率｜Eff TMU｜SIMO。
 * 數值全吃後端持久化的 rows.computed（批次 A）——缺 computed 的舊資料顯示 '—'，不假造。
 * SIMO 從屬列（simo_pair_index != null）：Y 標記＋Eff TMU 劃線（貢獻 0，ADR-020）。
 */
function ExpandedRows({ moduleId }: { moduleId: string }) {
  const { data, isLoading } = useModuleDetail(moduleId)
  const rows = data?.current_version_detail?.rows

  if (isLoading) {
    return (
      <tr>
        <td colSpan={POOL_COL_SPAN} className="px-10 py-2 text-xs text-slate-400 bg-slate-50">
          載入動作明細…
        </td>
      </tr>
    )
  }

  if (!rows?.length) {
    return (
      <tr>
        <td colSpan={POOL_COL_SPAN} className="px-10 py-2 text-xs text-slate-400 bg-slate-50">
          無動作行
        </td>
      </tr>
    )
  }

  return (
    <tr className="bg-blue-50/60">
      <td colSpan={POOL_COL_SPAN} className="p-0">
        <div className="pl-8 pr-3 py-1.5">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] text-slate-400 text-left">
                <th className="p-1 w-8 font-medium">#</th>
                <th className="p-1 font-medium">動作句</th>
                <th className="p-1 w-12 font-medium">手</th>
                <th className="p-1 text-right w-20 font-medium">Base TMU</th>
                <th className="p-1 text-right w-14 font-medium">頻率</th>
                <th className="p-1 text-right w-20 font-medium">Eff TMU</th>
                <th className="p-1 text-center w-14 font-medium">SIMO</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const isSimoFollower = row.simo_pair_index != null
                return (
                  <tr key={i} className="border-t border-blue-100">
                    <td className="p-1 text-slate-400">{i + 1}</td>
                    <td className="p-1 text-slate-600">
                      {row.narrative_zh ?? row.sub_activity ?? '—'}
                    </td>
                    <td className="p-1 text-slate-500">{row.hand}</td>
                    <td className="p-1 text-right font-mono text-slate-700">
                      {row.computed != null ? row.computed.total_tmu.toFixed(1) : '—'}
                    </td>
                    <td className="p-1 text-right text-slate-500">{row.frequency}</td>
                    <td
                      className={`p-1 text-right font-mono ${
                        isSimoFollower ? 'line-through text-slate-400' : 'text-slate-700'
                      }`}
                      title={isSimoFollower ? 'SIMO 從屬列，貢獻 0' : undefined}
                    >
                      {row.computed != null ? row.computed.eff_tmu.toFixed(1) : '—'}
                    </td>
                    <td className="p-1 text-center">
                      {isSimoFollower ? (
                        <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-medium">
                          Y
                        </span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </td>
    </tr>
  )
}

interface WIPoolSearchProps {
  onAdd: (modules: PoolModule[]) => void
  adding: boolean
}

function WIPoolSearch({ onAdd, adding }: WIPoolSearchProps) {
  const { data: allModules = [], isLoading } = usePoolModules()
  const [raw, setRaw] = useState('')
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Debounce 350 ms
  useEffect(() => {
    const t = setTimeout(() => setQ(raw.toLowerCase().trim()), 350)
    return () => clearTimeout(t)
  }, [raw])

  const filtered =
    q
      ? allModules.filter(
          (m) =>
            m.name_zh.toLowerCase().includes(q) || m.id.toLowerCase().includes(q),
        )
      : allModules

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const toggleAll = () => {
    if (selected.size === filtered.length && filtered.length > 0) {
      setSelected(new Set())
    } else {
      setSelected(new Set(filtered.map((m) => m.id)))
    }
  }

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const handleAdd = () => {
    if (selected.size === 0) return
    const modules = allModules.filter((m) => selected.has(m.id))
    onAdd(modules)
    setSelected(new Set())
  }

  const allSelected = filtered.length > 0 && selected.size === filtered.length

  return (
    <div className="bg-white rounded-xl border p-4">
      <h2 className="font-semibold text-sm mb-3 text-slate-700">B — WI 庫搜尋</h2>

      <div className="flex gap-2 mb-3 items-center">
        <input
          className="border rounded px-2 py-1 text-sm flex-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder="輸入關鍵字搜尋 WI 名稱…"
        />
        {isLoading && (
          <span className="text-xs text-slate-400 whitespace-nowrap">載入中…</span>
        )}
        <button
          disabled={selected.size === 0 || adding}
          onClick={handleAdd}
          className="px-3 py-1 text-sm bg-blue-600 text-white rounded disabled:opacity-40 hover:bg-blue-700 whitespace-nowrap"
        >
          {adding
            ? '加入中…'
            : `加入 WI Set${selected.size > 0 ? ` (${selected.size})` : ''}`}
        </button>
      </div>

      <div className="overflow-auto max-h-80 border rounded">
        {/* 欄序對齊 v3 WI Set 庫：WI Code｜WI 名稱｜動作數｜Total TMU｜CT(秒)｜建立日｜展開 */}
        <table className="w-full text-sm min-w-[680px]">
          <thead className="bg-slate-50 sticky top-0 z-10">
            <tr className="text-xs text-slate-500 text-left">
              <th className="p-2 w-8">
                <input type="checkbox" checked={allSelected} onChange={toggleAll} />
              </th>
              <th className="p-2 w-24">WI Code</th>
              <th className="p-2">WI 名稱</th>
              <th className="p-2 text-right w-16">動作數</th>
              <th className="p-2 text-right w-24">Total TMU</th>
              <th className="p-2 text-right w-24">CT(秒)</th>
              <th className="p-2 w-24">建立日</th>
              <th className="p-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td
                  colSpan={POOL_COL_SPAN}
                  className="p-6 text-center text-slate-400 text-xs"
                >
                  {q ? '無符合結果' : '尚無 WI 模組'}
                </td>
              </tr>
            )}
            {filtered.map((m) => (
              <React.Fragment key={m.id}>
                <tr
                  className={`border-t hover:bg-slate-50 ${
                    selected.has(m.id) ? 'bg-blue-50' : ''
                  }`}
                >
                  <td className="p-2">
                    <input
                      type="checkbox"
                      checked={selected.has(m.id)}
                      onChange={() => toggleSelect(m.id)}
                    />
                  </td>
                  {/* WI Code：motion_modules 尚無 code 欄（後端 wi_set.py 註記），不得假造 → '—' */}
                  <td className="p-2 text-xs text-slate-400 font-mono">—</td>
                  <td className="p-2 font-medium text-slate-800">{m.name_zh}</td>
                  {/* 後端摘要欄 total_tmu / action_count；null（無已發布版本）→ '—'，不得假裝是 0 */}
                  <td className="p-2 text-right text-slate-500">{m.action_count ?? '—'}</td>
                  <td className="p-2 text-right font-mono">
                    {m.total_tmu != null ? m.total_tmu.toFixed(1) : '—'}
                  </td>
                  <td className="p-2 text-right font-mono text-slate-600">
                    {m.total_tmu != null ? (m.total_tmu * TMU_SEC).toFixed(3) : '—'}
                  </td>
                  <td className="p-2 text-xs text-slate-500 font-mono">
                    {m.created_at ? m.created_at.slice(0, 10) : '—'}
                  </td>
                  <td className="p-2">
                    <button
                      onClick={() => toggleExpand(m.id)}
                      className="text-slate-400 hover:text-slate-700 text-xs px-1"
                      title="展開動作明細"
                    >
                      {expanded.has(m.id) ? '▲' : '▼'}
                    </button>
                  </td>
                </tr>
                {expanded.has(m.id) && <ExpandedRows moduleId={m.id} />}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-1.5 text-xs text-slate-400">
        顯示 {filtered.length} / {allModules.length} 筆
      </div>
    </div>
  )
}

// ─── Section C: SelectedWISetTable ────────────────────────────────────────────

interface SelectedWISetTableProps {
  projectId: string | null
  items: WiSetItemOut[]
  editable: boolean
}

function SelectedWISetTable({ projectId, items, editable }: SelectedWISetTableProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null)
  const [localNotes, setLocalNotes] = useState<Record<string, string>>({})

  const removeItem = useRemoveItem()
  const reorderItems = useReorderItems()

  // Sort items by seq_no once
  const sorted = [...items].sort((a, b) => a.seq_no - b.seq_no)

  // Sync notes from API whenever items change
  useEffect(() => {
    setLocalNotes((prev) => {
      const next: Record<string, string> = {}
      for (const item of items) {
        next[item.id] = prev[item.id] ?? item.notes ?? ''
      }
      return next
    })
  }, [items])

  // ── selection ──────────────────────────────────────────────────────────────

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === sorted.length && sorted.length > 0) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(sorted.map((i) => i.id)))
    }
  }

  const handleRemoveSelected = async () => {
    if (!projectId || selectedIds.size === 0) return
    for (const itemId of selectedIds) {
      await removeItem.mutateAsync({ projectId, itemId })
    }
    setSelectedIds(new Set())
  }

  const handleRemoveOne = (itemId: string) => {
    if (!projectId) return
    if (!confirm('確定移除此 WI？')) return
    removeItem.mutate({ projectId, itemId })
  }

  // ── reorder helpers ────────────────────────────────────────────────────────

  const doReorder = useCallback(
    (newOrder: WiSetItemOut[]) => {
      if (!projectId) return
      reorderItems.mutate({ projectId, orderedIds: newOrder.map((i) => i.id) })
    },
    [projectId, reorderItems],
  )

  const handleMoveUp = (idx: number) => {
    if (idx <= 0) return
    const next = [...sorted]
    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
    doReorder(next)
  }

  const handleMoveDown = (idx: number) => {
    if (idx >= sorted.length - 1) return
    const next = [...sorted]
    ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
    doReorder(next)
  }

  // ── HTML5 DnD ─────────────────────────────────────────────────────────────

  const onDragStart = (e: React.DragEvent<HTMLTableRowElement>, idx: number) => {
    setDragIdx(idx)
    setDragOverIdx(idx)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(idx))
  }

  const onDragOver = (e: React.DragEvent<HTMLTableRowElement>, idx: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOverIdx !== idx) setDragOverIdx(idx)
  }

  const onDrop = (e: React.DragEvent<HTMLTableRowElement>, targetIdx: number) => {
    e.preventDefault()
    if (dragIdx === null || dragIdx === targetIdx) {
      setDragIdx(null)
      setDragOverIdx(null)
      return
    }
    const next = [...sorted]
    const [moved] = next.splice(dragIdx, 1)
    next.splice(targetIdx, 0, moved)
    doReorder(next)
    setDragIdx(null)
    setDragOverIdx(null)
  }

  const onDragEnd = () => {
    setDragIdx(null)
    setDragOverIdx(null)
  }

  // ── empty state ────────────────────────────────────────────────────────────

  if (sorted.length === 0) {
    return (
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold text-sm mb-3 text-slate-700">C — 已選 WI 清單</h2>
        <div className="p-8 text-center text-slate-400 text-sm border rounded-lg border-dashed">
          尚未加入任何 WI —— 從上方搜尋後勾選並加入
        </div>
      </div>
    )
  }

  const allSelected = selectedIds.size === sorted.length

  return (
    <div className="bg-white rounded-xl border p-4">
      <h2 className="font-semibold text-sm mb-3 text-slate-700">C — 已選 WI 清單</h2>

      {/* Toolbar */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-slate-500">
          已選{' '}
          <span className="text-blue-600 font-semibold">{sorted.length}</span> 筆
        </span>
        {editable && (
          <button
            disabled={selectedIds.size === 0 || removeItem.isPending}
            onClick={handleRemoveSelected}
            className="px-2 py-1 text-xs border border-red-300 text-red-600 rounded hover:bg-red-50 disabled:opacity-40"
          >
            移除選取 ({selectedIds.size})
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-auto border rounded" style={{ maxHeight: 400 }}>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 sticky top-0 z-10">
            <tr className="text-xs text-slate-500 text-left">
              {editable && (
                <th className="p-2 w-8">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                </th>
              )}
              <th className="p-2 w-16">⠿ #</th>
              <th className="p-2 w-28">WI Code</th>
              <th className="p-2">WI 名稱</th>
              <th className="p-2 text-right w-16">動作數</th>
              <th className="p-2 text-right w-20">TMU</th>
              <th className="p-2 text-right w-24">CT(秒)</th>
              <th className="p-2 w-36">備註</th>
              {editable && <th className="p-2 w-24">操作</th>}
            </tr>
          </thead>
          <tbody>
            {sorted.map((item, idx) => {
              const isDragging = dragIdx === idx
              const isTarget =
                dragOverIdx === idx && dragIdx !== null && dragIdx !== idx
              const dropAbove = isTarget && dragIdx !== null && idx < dragIdx
              const dropBelow = isTarget && dragIdx !== null && idx > dragIdx

              return (
                <tr
                  key={item.id}
                  draggable={editable}
                  onDragStart={(e) => onDragStart(e, idx)}
                  onDragOver={(e) => onDragOver(e, idx)}
                  onDrop={(e) => onDrop(e, idx)}
                  onDragEnd={onDragEnd}
                  className={[
                    'border-t',
                    isDragging ? 'opacity-40 bg-blue-50' : '',
                    dropAbove ? 'border-t-2 border-t-blue-500' : '',
                    dropBelow ? 'border-b-2 border-b-blue-500' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  {editable && (
                    <td className="p-2">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggleSelect(item.id)}
                      />
                    </td>
                  )}
                  <td
                    className="p-2 select-none text-slate-400 font-mono text-xs"
                    style={{ cursor: editable ? 'grab' : 'default' }}
                  >
                    <span className="mr-0.5">⠿</span>
                    {idx + 1}
                  </td>
                  <td className="p-2 text-xs text-slate-500 font-mono truncate max-w-[7rem]">
                    {item.wi_code_snapshot ?? '—'}
                  </td>
                  <td className="p-2 font-medium text-slate-800 max-w-xs truncate">
                    {item.wi_name_snapshot}
                  </td>
                  <td className="p-2 text-right text-slate-500">
                    {item.action_count_snapshot}
                  </td>
                  <td className="p-2 text-right font-mono">
                    {item.total_tmu_snapshot.toFixed(1)}
                  </td>
                  <td className="p-2 text-right font-mono text-slate-600">
                    {item.total_seconds_snapshot.toFixed(3)}
                  </td>
                  <td className="p-2">
                    <input
                      className="border rounded px-1 py-0.5 text-xs w-full focus:outline-none focus:ring-1 focus:ring-blue-300"
                      value={localNotes[item.id] ?? ''}
                      onChange={(e) =>
                        setLocalNotes((prev) => ({ ...prev, [item.id]: e.target.value }))
                      }
                      placeholder="備注…"
                    />
                  </td>
                  {editable && (
                    <td className="p-2">
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleMoveUp(idx)}
                          disabled={idx === 0 || reorderItems.isPending}
                          className="px-1.5 py-0.5 text-xs border rounded disabled:opacity-30 hover:bg-slate-100"
                        >
                          ↑
                        </button>
                        <button
                          onClick={() => handleMoveDown(idx)}
                          disabled={
                            idx === sorted.length - 1 || reorderItems.isPending
                          }
                          className="px-1.5 py-0.5 text-xs border rounded disabled:opacity-30 hover:bg-slate-100"
                        >
                          ↓
                        </button>
                        <button
                          onClick={() => handleRemoveOne(item.id)}
                          disabled={removeItem.isPending}
                          className="px-1.5 py-0.5 text-xs border rounded text-red-600 hover:bg-red-50 disabled:opacity-30"
                        >
                          ✕
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Section D: WISetSummary ──────────────────────────────────────────────────

function WISetSummary({ items }: { items: WiSetItemOut[] }) {
  const totalTmu = items.reduce((s, i) => s + i.total_tmu_snapshot, 0)
  const totalSec = items.reduce((s, i) => s + i.total_seconds_snapshot, 0)
  const totalActions = items.reduce((s, i) => s + i.action_count_snapshot, 0)
  const totalMin = totalSec / 60

  const cards: { label: string; value: string; color: string }[] = [
    { label: 'WI 數', value: String(items.length), color: 'text-blue-600' },
    { label: '總動作數', value: String(totalActions), color: 'text-slate-700' },
    { label: '總 TMU', value: totalTmu.toFixed(1), color: 'text-emerald-600' },
    { label: '總 CT(秒)', value: totalSec.toFixed(3), color: 'text-amber-600' },
    { label: '總 CT(分)', value: totalMin.toFixed(3), color: 'text-violet-600' },
  ]

  return (
    <div className="bg-white rounded-xl border p-4">
      <h2 className="font-semibold text-sm mb-3 text-slate-700">D — 彙總</h2>
      <div className="grid grid-cols-5 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="bg-slate-50 rounded-lg p-3 text-center">
            <div className="text-xs text-slate-500 mb-1">{c.label}</div>
            <div className={`text-xl font-bold ${c.color}`}>{c.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function WISetBuilderPage() {
  const { data: me } = useMe()
  const editable = canEdit(me)

  // ── page-level state ───────────────────────────────────────────────────────
  const [projectId, setProjectId] = useState<string | null>(null)
  const [form, setForm] = useState<ProjectForm>(EMPTY_FORM)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  // ── queries ────────────────────────────────────────────────────────────────
  const { data: projectList = [] } = useProjectList()
  const { data: projectData, refetch: refetchProject } = useProject(projectId)

  // ── mutations ──────────────────────────────────────────────────────────────
  const createProject = useCreateProject()
  const updateProject = useUpdateProject()
  const deleteProject = useDeleteProject()
  const duplicateProject = useDuplicateProject()
  const addItem = useAddItem()

  // ── sync form when project loads ───────────────────────────────────────────
  useEffect(() => {
    if (!projectData) return
    setForm({
      project_code: projectData.project_code ?? '',
      name: projectData.name ?? '',
      site: projectData.site ?? '',
      bu: projectData.bu ?? '',
      process: projectData.process ?? '',
      family: projectData.family ?? '',
      model: projectData.model ?? '',
      description: projectData.description ?? '',
    })
  }, [projectData])

  // auto-dismiss flash messages
  useEffect(() => {
    if (!successMsg) return
    const t = setTimeout(() => setSuccessMsg(null), 3000)
    return () => clearTimeout(t)
  }, [successMsg])

  // ── helpers ────────────────────────────────────────────────────────────────

  const flash = (msg: string) => {
    setErrorMsg(null)
    setSuccessMsg(msg)
  }

  const flashError = (msg: string) => {
    setSuccessMsg(null)
    setErrorMsg(msg)
  }

  const resetForm = () => {
    setProjectId(null)
    setForm(EMPTY_FORM)
    setErrorMsg(null)
    setSuccessMsg(null)
  }

  const handleSelectProject = (id: string) => {
    if (id) {
      setProjectId(id)
      setErrorMsg(null)
    } else {
      resetForm()
    }
  }

  // ── Section B handler: add WIs to project ─────────────────────────────────

  const handleAddModules = async (modules: PoolModule[]) => {
    if (modules.length === 0) return
    setAdding(true)
    setErrorMsg(null)

    try {
      let pid = projectId

      // Auto-create project if none loaded
      if (!pid) {
        if (!form.name.trim()) {
          flashError('請先填寫專案名稱，或建立專案後再加入 WI')
          setAdding(false)
          return
        }
        const created = await createProject.mutateAsync({ form })
        pid = created.id
        setProjectId(pid)
        setForm((prev) => ({ ...prev, project_code: created.project_code }))
        flash('已自動建立專案')
      }

      // POST each WI as an item — 只送 wi_template_id，快照由伺服器回填（審查 8.2）
      let addedCount = 0
      for (const m of modules) {
        await addItem.mutateAsync({
          projectId: pid,
          wi_template_id: m.id,
          notes: null,
        })
        addedCount++
      }

      flash(`已加入 ${addedCount} 筆 WI`)
      await refetchProject()
    } catch (err) {
      flashError(`加入失敗：${(err as Error).message}`)
    } finally {
      setAdding(false)
    }
  }

  // ── Section E: save / create ───────────────────────────────────────────────

  const handleSave = async () => {
    if (!form.name.trim()) {
      flashError('專案名稱為必填')
      return
    }
    if (!form.project_code.trim()) {
      flashError('專案代碼為必填')
      return
    }
    setErrorMsg(null)
    try {
      if (projectId) {
        const updated = await updateProject.mutateAsync({ id: projectId, form })
        setForm((prev) => ({ ...prev, project_code: updated.project_code }))
        flash('已儲存')
      } else {
        const created = await createProject.mutateAsync({ form })
        setProjectId(created.id)
        setForm((prev) => ({ ...prev, project_code: created.project_code }))
        flash('已建立')
      }
    } catch (err) {
      flashError(`儲存失敗：${(err as Error).message}`)
    }
  }

  const handleDuplicate = async () => {
    if (!projectId) return
    setErrorMsg(null)
    try {
      const copy = await duplicateProject.mutateAsync(projectId)
      setProjectId(copy.id)
      flash(`已複製為新專案 ${copy.project_code}`)
    } catch (err) {
      flashError(`複製失敗：${(err as Error).message}`)
    }
  }

  const handleDelete = async () => {
    if (!projectId) return
    if (projectData?.status !== 'draft') {
      flashError('只有草稿狀態的專案可刪除')
      return
    }
    if (!confirm(`確定刪除專案「${projectData?.name}」？此操作不可復原。`)) return
    setErrorMsg(null)
    try {
      await deleteProject.mutateAsync(projectId)
      flash('已刪除')
      resetForm()
    } catch (err) {
      flashError(`刪除失敗：${(err as Error).message}`)
    }
  }

  // ── derived ────────────────────────────────────────────────────────────────

  const items = projectData?.items ?? []
  const isBusy =
    createProject.isPending ||
    updateProject.isPending ||
    deleteProject.isPending ||
    duplicateProject.isPending ||
    adding

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-4 overflow-y-auto pb-6">
      {/* ── Page header ── */}
      <div className="bg-white rounded-xl border px-5 py-3 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-semibold text-base">WI 專案建立</h1>
          <p className="text-xs text-slate-400">
            從 WI 庫搜尋並組合 WI 集合，快照版本、排序、彙總
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Project selector */}
          <select
            className="border rounded px-2 py-1 text-sm max-w-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
            value={projectId ?? ''}
            onChange={(e) => handleSelectProject(e.target.value)}
          >
            <option value="">— 選擇現有專案 —</option>
            {projectList.map((p) => (
              <option key={p.id} value={p.id}>
                {p.project_code} — {p.name} ({STATUS_ZH[p.status] ?? p.status})
              </option>
            ))}
          </select>

          <button
            onClick={resetForm}
            className="px-3 py-1 text-sm border rounded bg-white hover:bg-slate-50"
          >
            新增專案
          </button>
        </div>
      </div>

      {/* Flash messages */}
      {errorMsg && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-2 flex justify-between">
          <span>{errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="text-red-400 hover:text-red-600 ml-4">
            ✕
          </button>
        </div>
      )}
      {successMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl px-4 py-2 flex justify-between">
          <span>{successMsg}</span>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-600 ml-4">
            ✕
          </button>
        </div>
      )}

      {/* Section A */}
      <ProjectMetadataForm
        form={form}
        status={projectData?.status}
        onChange={setForm}
        editable={editable}
      />

      {/* Section B */}
      {editable && (
        <WIPoolSearch onAdd={handleAddModules} adding={adding} />
      )}

      {/* Section C */}
      <SelectedWISetTable
        projectId={projectId}
        items={items}
        editable={editable}
      />

      {/* Section D */}
      <WISetSummary items={items} />

      {/* Section E */}
      {editable && (
        <div className="bg-white rounded-xl border p-4">
          <h2 className="font-semibold text-sm mb-3 text-slate-700">E — 操作</h2>
          <div className="flex flex-wrap gap-2">
            {/* Save / Create */}
            <button
              disabled={isBusy}
              onClick={handleSave}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40"
            >
              {isBusy && !adding
                ? '處理中…'
                : projectId
                ? '儲存專案'
                : '建立專案'}
            </button>

            {/* Duplicate */}
            <button
              disabled={!projectId || isBusy}
              onClick={handleDuplicate}
              className="px-4 py-1.5 text-sm border rounded hover:bg-slate-50 disabled:opacity-40"
            >
              複製專案
            </button>

            {/* Delete — only draft */}
            <button
              disabled={!projectId || projectData?.status !== 'draft' || isBusy}
              onClick={handleDelete}
              className="px-4 py-1.5 text-sm border border-red-300 text-red-600 rounded hover:bg-red-50 disabled:opacity-40"
              title={
                projectData?.status !== 'draft' ? '只有草稿狀態可刪除' : undefined
              }
            >
              刪除專案
            </button>

            {projectData?.status !== 'draft' && projectId && (
              <span className="self-center text-xs text-slate-400">
                （非草稿狀態不可刪除）
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
