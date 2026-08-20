/**
 * DictionariesPage — H-01/02 主數據管理
 *
 * 為什麼不叫「字典」：在 v2，「字典」只指 MOST 規則值（rule_sets ＋ 12 張子表，
 * 有版本、clone-on-write、須可回放），那是 features/dictionary/ 的「MOST 字典」頁。
 * 本頁是主數據——詞彙庫與範本庫是廠內現況（可從 MES/ERP/PLM 同步），無版本、跟隨現實，
 * 不影響工時計算結果。見 ADR-024。
 *
 * Tab 1「詞彙庫」: WorkVocabItem CRUD (viewer 唯讀；analyst+ 可新增/停用/啟用)
 * Tab 2「動作模組範本」: MotionTemplate list + promote (approver+ 才顯示升格按鈕)
 * Tab 3「英文覆核」: ADR-032 D6 待審清單 ＋ 逐條覆核／指派（本頁已由側欄
 *   minRole:'analyst' gating，見 features/layout/Sidebar.tsx——與 D6「誰看得到：
 *   analyst 以上」一致；**寫入入口另由 I18nReviewTab 自己用 canEdit(me) 再擋一層**，
 *   兩層擋的是不同的事：側欄擋「進得來嗎」、頁內擋「看得到寫入嗎」）
 */
import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useMe, canEdit, canPublish } from '../../shared/auth/useMe'
import {
  useVocabItems,
  useCreateVocabItem,
  usePatchVocabItem,
  useMotionTemplates,
  usePromoteTemplate,
  type VocabFilters,
  type TemplateFilters,
} from './api'
import { I18nReviewTab } from './I18nReviewTab'

// ── constants ─────────────────────────────────────────────────────────────────

const VOCAB_KINDS = ['object', 'component', 'tool', 'from', 'to', 'hand'] as const
type VocabKind = (typeof VOCAB_KINDS)[number]

const kindLabel: Record<string, string> = {
  object: '物件', component: '元件', tool: '器具', from: '來源', to: '目的地', hand: '手勢',
}

// ── simple debounce hook ──────────────────────────────────────────────────────

function useDebouncedState(delay = 300): [string, string, (v: string) => void] {
  const [raw, setRaw] = useState('')
  const [debounced, setDebounced] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const set = (v: string) => {
    setRaw(v)
    if (timer.current != null) clearTimeout(timer.current)
    timer.current = setTimeout(() => setDebounced(v), delay)
  }
  return [raw, debounced, set]
}

// ── Tab 1 ─────────────────────────────────────────────────────────────────────

function VocabTab() {
  const { data: me } = useMe()
  const canModify = canEdit(me)

  const [kindFilter, setKindFilter] = useState<string>('')
  const [rawQ, debouncedQ, setQ] = useDebouncedState(300)

  const filters: VocabFilters = { limit: 100, include_inactive: true }
  if (kindFilter) filters.kind = kindFilter
  if (debouncedQ) filters.q = debouncedQ

  const { data: items = [], isLoading, error } = useVocabItems(filters)
  const create = useCreateVocabItem()
  const patch = usePatchVocabItem()

  const [showForm, setShowForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [newKind, setNewKind] = useState<VocabKind>('object')
  const [formMsg, setFormMsg] = useState('')

  const handleCreate = () => {
    if (!newName.trim()) return
    create.mutate(
      { kind: newKind, name_zh: newName.trim() },
      {
        onSuccess: () => { setNewName(''); setShowForm(false); setFormMsg('') },
        onError: (e) => setFormMsg('建立失敗：' + (e as Error).message),
      },
    )
  }

  const handleToggleActive = (id: string, current: boolean) => {
    patch.mutate({ id, body: { is_active: !current } })
  }

  if (isLoading) return <div className="p-4 text-slate-500 text-sm">載入詞彙庫…</div>
  if (error) return <div className="p-4 text-red-600 text-sm">載入失敗：{(error as Error).message}</div>

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="border rounded px-2 py-1 text-sm w-44"
          placeholder="搜尋 name_zh…"
          value={rawQ}
          onChange={e => setQ(e.target.value)}
        />
        <select
          className="border rounded px-2 py-1 text-sm"
          value={kindFilter}
          onChange={e => setKindFilter(e.target.value)}
        >
          <option value="">全部 kind</option>
          {VOCAB_KINDS.map(k => (
            <option key={k} value={k}>{kindLabel[k] ?? k}</option>
          ))}
        </select>
        {canModify && (
          <button
            className="ml-auto px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-40"
            onClick={() => setShowForm(v => !v)}
          >
            {showForm ? '取消' : '+ 新增詞彙'}
          </button>
        )}
      </div>

      {/* Inline create form */}
      {showForm && canModify && (
        <div className="border rounded p-3 bg-slate-50 flex flex-wrap gap-2 items-end text-sm">
          <label className="flex flex-col gap-0.5">
            名稱
            <input
              className="border rounded px-2 py-1 w-44"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="中文詞彙名稱"
            />
          </label>
          <label className="flex flex-col gap-0.5">
            類別
            <select
              className="border rounded px-2 py-1"
              value={newKind}
              onChange={e => setNewKind(e.target.value as VocabKind)}
            >
              {VOCAB_KINDS.map(k => <option key={k} value={k}>{kindLabel[k] ?? k}</option>)}
            </select>
          </label>
          <button
            className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-40"
            disabled={!newName.trim() || create.isPending}
            onClick={handleCreate}
          >
            {create.isPending ? '建立中…' : '建立'}
          </button>
          {formMsg && <span className="text-red-600">{formMsg}</span>}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2">name_zh</th>
              <th className="px-3 py-2">kind</th>
              <th className="px-3 py-2">source_system</th>
              <th className="px-3 py-2">狀態</th>
              {canModify && <th className="px-3 py-2">操作</th>}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={canModify ? 5 : 4} className="px-3 py-6 text-center text-slate-400">
                  無符合條件的詞彙
                </td>
              </tr>
            )}
            {items.map(item => (
              <tr key={item.id} className={`border-t ${item.is_active ? '' : 'opacity-50'}`}>
                <td className="px-3 py-2 font-medium">{item.name_zh}</td>
                <td className="px-3 py-2">
                  <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-700">
                    {kindLabel[item.kind] ?? item.kind}
                  </span>
                </td>
                <td className="px-3 py-2 text-slate-500">{item.source_system}</td>
                <td className="px-3 py-2">
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${item.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>
                    {item.is_active ? '啟用' : '停用'}
                  </span>
                </td>
                {canModify && (
                  <td className="px-3 py-2">
                    <button
                      className={`px-2 py-0.5 rounded text-xs disabled:opacity-40 ${item.is_active ? 'bg-amber-100 text-amber-800 hover:bg-amber-200' : 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'}`}
                      disabled={patch.isPending}
                      onClick={() => handleToggleActive(item.id, item.is_active)}
                    >
                      {item.is_active ? '停用' : '啟用'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Tab 2 ─────────────────────────────────────────────────────────────────────

function TemplatesTab() {
  const { data: me } = useMe()
  const canPromote = canPublish(me)

  const [rawQ, debouncedQ, setQ] = useDebouncedState(300)
  const [statusFilter, setStatusFilter] = useState<string>('')

  const filters: TemplateFilters = {}
  if (statusFilter) filters.status = statusFilter
  if (debouncedQ) filters.q = debouncedQ

  const { data: templates = [], isLoading, error } = useMotionTemplates(filters)
  const promote = usePromoteTemplate()

  const [promoteMsg, setPromoteMsg] = useState<Record<string, string>>({})

  const handlePromote = (id: string) => {
    promote.mutate(id, {
      onSuccess: () => setPromoteMsg(prev => ({ ...prev, [id]: '' })),
      onError: (e) => setPromoteMsg(prev => ({ ...prev, [id]: (e as Error).message })),
    })
  }

  if (isLoading) return <div className="p-4 text-slate-500 text-sm">載入動作模組範本…</div>
  if (error) return <div className="p-4 text-red-600 text-sm">載入失敗：{(error as Error).message}</div>

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="border rounded px-2 py-1 text-sm w-44"
          placeholder="搜尋名稱/關鍵字…"
          value={rawQ}
          onChange={e => setQ(e.target.value)}
        />
        <select
          className="border rounded px-2 py-1 text-sm"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="">全部狀態</option>
          <option value="draft">草稿</option>
          <option value="standard">標準</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2">name_zh</th>
              <th className="px-3 py-2">seq_kind</th>
              <th className="px-3 py-2">狀態</th>
              <th className="px-3 py-2">擁有者</th>
              {canPromote && <th className="px-3 py-2">操作</th>}
            </tr>
          </thead>
          <tbody>
            {templates.length === 0 && (
              <tr>
                <td colSpan={canPromote ? 5 : 4} className="px-3 py-6 text-center text-slate-400">
                  無符合條件的範本
                </td>
              </tr>
            )}
            {templates.map(t => (
              <tr key={t.id} className="border-t">
                <td className="px-3 py-2 font-medium">{t.name_zh}</td>
                <td className="px-3 py-2">
                  <span className="px-1.5 py-0.5 rounded text-xs bg-blue-100 text-blue-800">{t.seq_kind}</span>
                </td>
                <td className="px-3 py-2">
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${t.status === 'standard' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                    {t.status === 'standard' ? '廠標準' : '草稿'}
                  </span>
                </td>
                <td className="px-3 py-2 text-slate-500">{t.owner ?? '—'}</td>
                {canPromote && (
                  <td className="px-3 py-2">
                    {t.status === 'draft' ? (
                      <div className="flex items-center gap-1">
                        <button
                          className="px-2 py-0.5 rounded text-xs bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40"
                          disabled={promote.isPending}
                          onClick={() => handlePromote(t.id)}
                        >
                          升格 standard
                        </button>
                        {promoteMsg[t.id] && (
                          <span className="text-xs text-red-600">{promoteMsg[t.id]}</span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">已是廠標準</span>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── DictionariesPage ──────────────────────────────────────────────────────────

type DictTab = 'vocab' | 'templates' | 'i18n-review'

export function DictionariesPage() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const [activeTab, setActiveTab] = useState<DictTab>('vocab')

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold">主數據管理</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          管理工作詞彙（WorkVocabItem）、動作模組範本（MotionTemplate）與英文覆核進度（ADR-032 D6）。
          身分：{me?.employee_no}（{me?.roles?.join(' · ') || 'viewer'}）
        </p>
      </div>

      {/* Tab bar */}
      {/* S8（一併修，便宜）：'vocab'／'templates' 的標籤目前硬編中文，未走 i18n key——
          Phase A 的字串外部化只做了「側欄／標頭／共用元件」第一批（ADR-032 §5），
          這兩個分頁標籤還沒排到。已知缺口，非本輪漏改；下一個做 Phase A 外部化的人
          補上 `nav.vocab`／`nav.templates`（或等價 key）即可，不要誤以為這裡是新債。 */}
      <div className="flex border-b bg-white rounded-t-xl overflow-hidden">
        {([
          ['vocab', '詞彙庫'],
          ['templates', '動作模組範本'],
          ['i18n-review', t('i18nReview.tabLabel')],
        ] as [DictTab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === id
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div>
        {activeTab === 'vocab' && <VocabTab />}
        {activeTab === 'templates' && <TemplatesTab />}
        {activeTab === 'i18n-review' && <I18nReviewTab />}
      </div>
    </div>
  )
}
