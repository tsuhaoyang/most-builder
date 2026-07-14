// Tab 1: 動作模組工作區 — v3 MostWorkbenchPage 單頁流（ADR-021 Phase 2）
// 由上而下：AI 快速建模列 → 摘要列（九欄） → 交錯句型列 → WI 語句 → 動作清單（Pool）
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRuleSetOptions, useVocab, useCalculate } from '../wi-workbench/api'
import { useCreateVocab } from '../master-data/api'
import type { VocabIn } from '../master-data/api'
import { defaultCycle, buildPayload, payloadToState, shortNarr, type CycleState } from '../wi-workbench/cycle'
import { TMU_SEC } from '../../shared/config'
import { apiGet, apiPost } from '../../shared/api/client'
import { SlotBuilder, aIsFilled } from './SlotBuilder'
import {
  nlDraftPatch, nlDraftPatchFillEmpty, sourceBadge, NL_FIELD_LABELS,
  type NlDraftRes,
} from './nlDraft'
import {
  useMotionModules,
  useCreateModule,
  useUpdateModule,
  useDeleteModule,
  useCloneModule,
  usePublishModule,
  type MotionModuleSummary,
} from './api'
import { useWorkbenchV3Store } from './store'

const HAND_NAME: Record<string, string> = { RH: '右手', LH: '左手', BH: '雙手' }

// ── 格位是否有內容（不含情境欄；存檔擋空與 NL 判斷共用） ───────────────────────
function hasSlotContent(c: CycleState): boolean {
  return aIsFilled(c.a0) || aIsFilled(c.a3) || aIsFilled(c.a6)
    || !!c.b1 || !!c.b4 || !!c.g || !!c.p_base || c.p_addons.length > 0
    || !!c.m.verb || c.x !== 'x_none' || c.i !== 'i_none'
}

// ── 編輯器是否有內容（NL 覆蓋/填空判斷，audit §1.13） ─────────────────────────
function hasEditorContent(c: CycleState): boolean {
  return hasSlotContent(c) || Object.values(c.nv).some(v => !!v)
}

// ── Simple Toast ──────────────────────────────────────────────────────────────
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

// ── ActionModuleWorkspace ─────────────────────────────────────────────────────
export function ActionModuleWorkspace() {
  const { data: opts } = useRuleSetOptions()
  const { data: vocab = [] } = useVocab()
  const calc = useCalculate()
  const createVocab = useCreateVocab()

  // Builder state
  const [cur, setCur] = useState<CycleState>(defaultCycle())
  const [wiSentence, setWiSentence] = useState('')       // WI 語句人工覆寫（audit §1.6）
  const [showHandInMi, setShowHandInMi] = useState(true) // 顯示於MI checkbox
  const [tmu, setTmu] = useState<number | null>(null)
  const [tech, setTech] = useState('')
  const [editingModuleId, setEditingModuleId] = useState<string | null>(null)
  const [source, setSource] = useState<'manual' | 'ai' | 'copied'>('manual')

  // NL Draft state（F-05）
  const [nlText, setNlText] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlResult, setNlResult] = useState<NlDraftRes | null>(null)
  const [nlAskOpen, setNlAskOpen] = useState(false)      // 覆蓋/填空兩鍵 modal

  // Toast
  const [toast, setToast] = useState<ToastState | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  function showToast(msg: string, type: 'ok' | 'err' = 'ok') {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg, type })
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }

  // Pool state
  const [searchQ, setSearchQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [loadingModuleId, setLoadingModuleId] = useState<string | null>(null)

  // Debounce searchQ → debouncedQ (300ms), then let API do the filtering
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(searchQ.trim()), 300)
    return () => clearTimeout(t)
  }, [searchQ])

  // API hooks
  const { data: modules = [], isLoading: modulesLoading } = useMotionModules(
    debouncedQ ? { scope: 'personal', q: debouncedQ } : { scope: 'personal' }
  )
  const createModule = useCreateModule()
  const updateModule = useUpdateModule()
  const deleteModule = useDeleteModule()
  const cloneModule = useCloneModule()
  const publishModule = usePublishModule()

  // Cross-tab store
  const { setPendingModules, setActiveTab } = useWorkbenchV3Store()

  // ── Debounced backend calculate (400ms)：前端不算 TMU（DISC-02） ─────────────
  const payload = useMemo(
    () => (opts ? buildPayload(cur, opts.code) : null),
    [cur, opts],
  )
  useEffect(() => {
    if (!payload) { setTmu(null); setTech(''); return }
    const id = setTimeout(() => {
      calc.mutate(payload, {
        onSuccess: r => { setTmu(r.total_tmu); setTech(r.tech_line) },
        onError: () => { setTmu(null); setTech('') },
      })
    }, 400)
    return () => clearTimeout(id)
  }, [JSON.stringify(payload)]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!opts) return (
    <div className="bg-white rounded-xl border p-6 text-slate-500">載入 rule-set…</div>
  )

  // ── helpers ───────────────────────────────────────────────────────────────
  const set = (patch: Partial<CycleState>) => setCur(c => ({ ...c, ...patch }))
  const gm = cur.seq === 'GM'

  const vname = (_kind: string, id: string) => vocab.find(v => v.id === id)?.name_zh ?? ''
  const label = (kind: string, code: string) => {
    const m: Record<string, { code: string; label: string }[]> = { g: opts.g, p_base: opts.p_bases, m_verb: opts.m_verbs }
    return m[kind]?.find(o => o.code === code)?.label ?? ''
  }

  // MI 語句：即時 shortNarr（顯示預覽；權威敘述由後端 narrative 產）
  const miSentence = shortNarr(cur, label, vname, showHandInMi)

  // 摘要列數值（eff = tmu × freq 為顯示用算術，非 TMU 規則計算）
  const effTmu = tmu != null ? Math.round(tmu * (cur.freq || 1) * 1000) / 1000 : null
  const ctSec = effTmu != null ? (effTmu * TMU_SEC).toFixed(3) : null
  const isSimo = (cur.simoGroup || '').trim() !== ''

  // NL 結果面板：option code → label
  function nlOptionLabel(field: string, code: string): string {
    if (field === 'g_code') return opts!.g.find(o => o.code === code)?.label ?? code
    if (field === 'b_code' || field === 'b_code2') return opts!.b.find(o => o.code === code)?.label ?? code
    if (field === 'p_base_code') return opts!.p_bases.find(o => o.code === code)?.label ?? code
    return code
  }

  // ── NL Draft（F-05：覆蓋/填空 + 結果面板，audit §1.13） ──────────────────────
  async function runNlDraft() {
    const text = nlText.trim()
    if (!text || !opts) return
    setNlLoading(true)
    try {
      const res = await apiPost<NlDraftRes>('/api/v2/worksheets/nl-draft', {
        text, rule_set_code: opts.code,
      })
      setNlResult(res)
      if (hasEditorContent(cur)) {
        setNlAskOpen(true)               // 編輯器有內容 → 詢問覆蓋/填空
      } else {
        applyNlDraft(res, 'overwrite')
      }
    } catch (err) {
      const e = err as Error
      if (e.message.startsWith('404') || e.message.startsWith('501')) {
        showToast('NL 解析功能尚未啟用', 'err')
      } else {
        showToast('NL 解析失敗：' + e.message, 'err')
      }
    } finally {
      setNlLoading(false)
    }
  }

  function applyNlDraft(res: NlDraftRes, mode: 'overwrite' | 'fill-empty') {
    const patch = mode === 'overwrite' ? nlDraftPatch(res) : nlDraftPatchFillEmpty(res, cur)
    if (Object.keys(patch).length > 0) {
      set(patch)
      setSource('ai')
      showToast(mode === 'overwrite' ? '已覆蓋填入 AI 建議' : '已填入空白欄位', 'ok')
    } else {
      showToast('無可套用的建議欄位', 'err')
    }
    setNlAskOpen(false)
  }

  // ── Reset builder ─────────────────────────────────────────────────────────
  function resetBuilder() {
    setCur(defaultCycle())
    setWiSentence('')
    setTmu(null)
    setTech('')
    setEditingModuleId(null)
    setSource('manual')
    setNlText('')
    setNlResult(null)
    setNlAskOpen(false)
  }

  // ── Save / update module（名稱＝WI 語句覆寫；空則自動命名） ────────────────────
  async function handleSave() {
    // 全空擋下：無 WI 語句且格位全空 → 沒有可命名/可計算的內容（reviewer #3）
    if (!wiSentence.trim() && !hasSlotContent(cur)) {
      showToast('請至少填一個格位或輸入 WI 語句', 'err'); return
    }
    if (!tmu || tmu <= 0) { showToast('TMU 必須 > 0，請確認格位設定', 'err'); return }
    if (!opts) return
    // 自動命名：情境欄有值 → 系統句；情境欄全空 → tech line 壓縮尾綴（去 0 值格，
    // 如「GM A6 G6 A10 P6」），避免佔位符（［自］［物］…）進名稱（reviewer #3）
    const contextFilled = !!(cur.nv.obj || cur.nv.from || cur.nv.to)
    const compactTech = tech.split(/\s+/).filter(t => t && !/^[A-Z]+0$/.test(t)).join(' ')
    const autoName = contextFilled || !compactTech ? miSentence : `${cur.seq} ${compactTech}`
    const name = wiSentence.trim() || autoName

    const row = {
      hand: cur.handCode,
      frequency: cur.freq,
      cycle: buildPayload(cur, opts.code),
      sub_activity: name,
      // 後端 ModuleRowIn.vocab_refs 合約鍵：object/from/to(/tool)_vocab_id；
      // component/where 無對應鍵不送（僅前端敘述/顯示用）— reviewer #1
      vocab_refs: {
        object_vocab_id: cur.nv.obj || null,
        from_vocab_id: cur.nv.from || null,
        to_vocab_id: cur.nv.to || null,
      },
    }

    try {
      if (editingModuleId) {
        // 後端 MotionModuleUpdate 無 rows/source 欄位；列內容變更走 publish（發新版本）
        await updateModule.mutateAsync({
          id: editingModuleId,
          body: { name_zh: name },
        })
        await publishModule.mutateAsync({
          id: editingModuleId,
          body: { rows: [row], rule_set_code: opts.code },
        })
        showToast('已更新模組：' + name, 'ok')
      } else {
        const created = await createModule.mutateAsync({
          name_zh: name,
          scope: 'personal',
          keywords: [],
        })
        await publishModule.mutateAsync({
          id: created.id,
          body: { rows: [row], rule_set_code: opts.code },
        })
        showToast('已新增動作：' + name, 'ok')
      }
      resetBuilder()
    } catch (err) {
      showToast('儲存失敗：' + (err as Error).message, 'err')
    }
  }

  // ── Load module into builder（列編輯迴路，audit §1.7） ────────────────────────
  async function loadModule(mod: MotionModuleSummary) {
    setLoadingModuleId(mod.id)
    try {
      const detail = await apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${mod.id}`)
      const row = detail.current_version_detail?.rows?.[0]
      if (!row) {
        showToast('此模組尚無已發布版本', 'err')
        return
      }
      const next = payloadToState(row.cycle)
      // vocab_refs 還原進情境欄（與存檔時的鍵對稱）— reviewer #1
      const refs = (row.vocab_refs ?? {}) as Record<string, unknown>
      const vid = (k: string) => (typeof refs[k] === 'string' ? refs[k] as string : '')
      setCur({
        ...next, handCode: row.hand, freq: row.frequency,
        nv: { ...next.nv, obj: vid('object_vocab_id'), from: vid('from_vocab_id'), to: vid('to_vocab_id') },
      })
      setWiSentence(mod.name_zh)
      setEditingModuleId(mod.id)
      setSource((detail.source as 'manual' | 'ai' | 'copied') ?? 'manual')
    } catch (err) {
      showToast('載入模組失敗：' + (err as Error).message, 'err')
    } finally {
      setLoadingModuleId(null)
    }
  }

  // ── Delete module（確認後刪除，audit §1.9） ──────────────────────────────────
  async function handleDelete(id: string, name: string) {
    if (!window.confirm(`確認刪除模組「${name}」？`)) return
    try {
      await deleteModule.mutateAsync(id)
      if (editingModuleId === id) resetBuilder()
      setSelectedIds(s => { const next = new Set(s); next.delete(id); return next })
      showToast('已刪除：' + name, 'ok')
    } catch (err) {
      showToast('刪除失敗：' + (err as Error).message, 'err')
    }
  }

  // ── Clone module ──────────────────────────────────────────────────────────
  async function handleClone(id: string, name: string) {
    try {
      await cloneModule.mutateAsync(id)
      showToast('已複製：' + name, 'ok')
    } catch (err) {
      showToast('複製失敗：' + (err as Error).message, 'err')
    }
  }

  // ── Multi-select ──────────────────────────────────────────────────────────
  function toggleSelect(id: string) {
    setSelectedIds(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  function handleSendToWi() {
    const selected = modules.filter(m => selectedIds.has(m.id))
    setPendingModules(selected)
    setActiveTab('tab2')
  }

  // ── Pool 摘要：合計走後端摘要欄加總；缺值顯示 —（audit §0.1） ─────────────────
  const tmuValues = modules.map(m => m.total_tmu).filter((v): v is number => v != null)
  const poolTotalTmu = tmuValues.length > 0
    ? Math.round(tmuValues.reduce((a, b) => a + b, 0) * 1000) / 1000
    : null

  function getModuleSeq(mod: MotionModuleSummary): string {
    if (typeof mod.seq_kind === 'string' && mod.seq_kind) return mod.seq_kind
    const seq = mod.current_version_detail?.rows?.[0]?.cycle?.seq
    return typeof seq === 'string' ? seq : '—'
  }

  function getModuleHand(mod: MotionModuleSummary): string {
    const hand = mod.hand ?? mod.current_version_detail?.rows?.[0]?.hand
    if (!hand) return '—'
    return HAND_NAME[hand] ?? hand
  }

  const isSaving = createModule.isPending || updateModule.isPending || publishModule.isPending

  // 摘要列九欄（v3 SequenceSummaryBar 對等）
  const summaryFields: Array<{ label: string; node: React.ReactNode; wide?: boolean }> = [
    {
      label: '動作類型',
      node: <span className="bg-blue-100 text-blue-700 rounded px-1.5 py-0.5 text-xs font-medium">{gm ? '一般移動' : '控制移動'}</span>,
    },
    { label: '使用手', node: <span>{HAND_NAME[cur.handCode] ?? cur.handCode}</span> },
    { label: '基礎 TMU', node: <b className="text-base" style={{ color: '#1a73e8' }}>{tmu ?? '—'}</b> },
    {
      label: '頻率',
      node: (
        <input
          type="number" min={1}
          className="border rounded w-14 px-1 py-0 text-sm"
          value={cur.freq}
          onChange={e => set({ freq: parseInt(e.target.value) || 1 })}
        />
      ),
    },
    { label: '有效 TMU', node: <b className="text-base text-red-600">{effTmu ?? '—'}</b> },
    { label: 'CT (秒)', node: <span>{ctSec ?? '—'}</span> },
    { label: 'SIMO', node: <span className={isSimo ? 'text-orange-600 font-bold' : ''}>{isSimo ? '是' : '否'}</span> },
    {
      label: '納入總時間',
      node: effTmu == null
        ? <span>—</span>
        : isSimo
          ? <span className="line-through text-slate-400">0</span>
          : <span>{effTmu}</span>,
    },
    { label: 'MI 語句', node: <span className="text-xs text-slate-600 truncate">{miSentence}</span>, wide: true },
  ]

  return (
    <>
      <Toast toast={toast} />
      <div className="space-y-3">

        {/* ═══ 建立器卡片：AI 列 → 摘要列 → 交錯句型 → WI 語句 ═══ */}
        <div className="bg-white rounded-xl border p-4 space-y-3">

          {/* 1. AI 快速建模列 */}
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-xs font-semibold text-white bg-slate-600 rounded px-2 py-1">AI 快速建模</span>
            <input
              className="flex-1 min-w-0 border rounded px-2 py-1.5 text-sm"
              placeholder="輸入動作描述，例：從料架上拿DIMM放至流水線"
              value={nlText}
              onChange={e => setNlText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !nlLoading) runNlDraft() }}
            />
            <button
              onClick={runNlDraft}
              disabled={nlLoading || !nlText.trim()}
              className="shrink-0 px-3 py-1.5 bg-blue-600 text-white rounded text-sm disabled:opacity-40"
            >
              {nlLoading ? '解析中…' : 'AI 預填'}
            </button>
          </div>

          {/* 1b. NL 結果面板（可關閉） */}
          {nlResult && (
            <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs space-y-1.5" data-testid="nl-result-panel">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`rounded px-1.5 py-0.5 font-medium ${
                  (nlResult.overall_confidence ?? 0) >= 0.7
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-amber-100 text-amber-700'
                }`}>
                  信心 {Math.round((nlResult.overall_confidence ?? 0) * 100)}%
                </span>
                {nlResult.suggested_seq && (
                  <span className="bg-slate-200 text-slate-700 rounded px-1.5 py-0.5">
                    建議：{nlResult.suggested_seq === 'GM' ? '一般移動 (GM)' : '控制移動 (CM)'}
                  </span>
                )}
                <button
                  onClick={() => setNlResult(null)}
                  className="ml-auto text-slate-400 hover:text-slate-600 leading-none"
                  aria-label="關閉 NL 結果"
                >✕</button>
              </div>
              {/* 逐 slot 命中/缺漏（badge 四態：明確/推斷/預設/待確認） */}
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {(nlResult.slots ?? []).map(s => (
                  <span key={s.field} className="inline-flex items-center gap-1">
                    <span className="text-slate-500">{NL_FIELD_LABELS[s.field] ?? s.field}</span>
                    {s.chosen ? (
                      <>
                        <span className={`rounded border px-1 py-0.5 leading-none ${
                          sourceBadge(s.chosen.source) === '明確' ? 'bg-blue-50 text-blue-600 border-blue-200'
                          : sourceBadge(s.chosen.source) === '預設' ? 'bg-amber-50 text-amber-600 border-amber-200'
                          : 'bg-emerald-50 text-emerald-600 border-emerald-200'
                        }`}>{sourceBadge(s.chosen.source)}</span>
                        <span className="text-slate-700">{nlOptionLabel(s.field, s.chosen.option_code)}</span>
                      </>
                    ) : (
                      <span className="rounded border px-1 py-0.5 leading-none bg-red-50 text-red-500 border-red-200">待確認</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 2. 動作類型 + 摘要列（九欄常駐） */}
          <div className="flex items-stretch gap-3">
            <select
              className="shrink-0 border rounded px-2 text-sm self-center py-1.5"
              value={cur.seq}
              onChange={e => set({ seq: e.target.value as 'GM' | 'CM' })}
              aria-label="動作類型"
            >
              <option value="GM">一般移動</option>
              <option value="CM">控制移動</option>
            </select>
            <div
              className="flex-1 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border px-4 py-2"
              style={{ background: 'linear-gradient(135deg,#f8fbff 0%,#f0f7ff 100%)', borderColor: '#d4e5f7' }}
              data-testid="summary-bar"
            >
              {summaryFields.map(f => (
                <div key={f.label} className={`flex flex-col ${f.wide ? 'flex-1 min-w-[200px]' : ''}`}>
                  <span className="text-[10px] text-slate-400 tracking-wide">{f.label}</span>
                  <span className="text-sm font-medium text-slate-700 leading-5">{f.node}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 3. 交錯句型列（共用 SlotBuilder） */}
          <SlotBuilder
            value={cur}
            onChange={set}
            opts={opts}
            vocab={vocab}
            onCreateVocab={(kind, name, assign) =>
              createVocab.mutate({ kind, name_zh: name } as VocabIn, {
                onSuccess: v => assign(v.id),
              })
            }
            showHandInMi={showHandInMi}
            onShowHandInMiChange={setShowHandInMi}
            tmu={tmu}
            tech={tech}
          />

          {/* tech line（後端權威技術列） */}
          <div className="text-xs font-mono text-slate-400">{tech || '—'}</div>

          {/* 4. WI 語句 + 新增動作/清空 */}
          <div className="flex items-center gap-2 pt-2 border-t">
            <span className="shrink-0 text-xs font-semibold text-slate-600 border rounded px-2 py-1 bg-slate-50">WI 語句</span>
            <input
              className="flex-1 min-w-0 border rounded px-2 py-1.5 text-sm"
              placeholder={miSentence}
              value={wiSentence}
              onChange={e => setWiSentence(e.target.value)}
            />
            {editingModuleId && (
              <span className="shrink-0 text-xs text-amber-700 bg-amber-50 border border-amber-300 rounded px-2 py-0.5">
                編輯中
              </span>
            )}
            {editingModuleId && (
              <button
                onClick={resetBuilder}
                className="shrink-0 px-2 py-1.5 border rounded text-slate-600 hover:bg-slate-50 text-sm"
              >
                取消編輯
              </button>
            )}
            <button
              disabled={isSaving || !tmu || tmu <= 0}
              onClick={handleSave}
              className="shrink-0 px-4 py-1.5 bg-emerald-600 text-white rounded-lg disabled:opacity-40 text-sm font-medium"
            >
              {isSaving ? '儲存中…' : editingModuleId ? '更新模組' : '新增動作'}
            </button>
            <button
              onClick={resetBuilder}
              className="shrink-0 px-3 py-1.5 border rounded-lg text-slate-600 hover:bg-slate-50 text-sm"
            >
              清空
            </button>
          </div>

          {source === 'ai' && (
            <p className="text-xs text-violet-600">AI badge：此動作由 NL 草稿自動填入</p>
          )}
        </div>

        {/* ═══ 動作清單（個人模組 Pool） ═══ */}
        <div className="bg-white rounded-xl border p-4 space-y-3">
          {/* 工具列：搜尋 + 筆數 + 合計 */}
          <div className="flex items-center gap-3 flex-wrap">
            <input
              className="border rounded px-2 py-1 text-sm w-52"
              placeholder="搜尋動作…"
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
            />
            <span className="text-sm text-slate-500">共 {modules.length} 筆</span>
            <span className="ml-auto text-sm text-slate-500">
              合計：{poolTotalTmu != null
                ? <><b style={{ color: '#1a73e8' }}>{poolTotalTmu}</b> TMU / <b className="text-red-600">{(poolTotalTmu * TMU_SEC).toFixed(3)}</b>s</>
                : '—'}
            </span>
          </div>

          {/* 動作清單表格 */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-100 text-left">
                  <th className="p-1.5 w-7 text-center">
                    <input
                      type="checkbox"
                      checked={modules.length > 0 && modules.every(m => selectedIds.has(m.id))}
                      onChange={e => {
                        if (e.target.checked) setSelectedIds(new Set(modules.map(m => m.id)))
                        else setSelectedIds(new Set())
                      }}
                    />
                  </th>
                  <th className="p-1.5 w-8">#</th>
                  <th className="p-1.5 w-14">手</th>
                  <th className="p-1.5">WI / 動作描述</th>
                  <th className="p-1.5 w-14">類型</th>
                  <th className="p-1.5 w-20 text-right">TMU</th>
                  <th className="p-1.5 w-20 text-right">CT(秒)</th>
                  <th className="p-1.5 w-16 text-right">動作數</th>
                  <th className="p-1.5 w-36 text-center">操作</th>
                </tr>
              </thead>
              <tbody>
                {modulesLoading && (
                  <tr><td colSpan={9} className="p-3 text-slate-400 text-center">載入中…</td></tr>
                )}
                {!modulesLoading && modules.length === 0 && (
                  <tr><td colSpan={9} className="p-3 text-slate-400 text-center">
                    {searchQ ? '無相符動作' : '尚無動作，請在上方建立器新增。'}
                  </td></tr>
                )}
                {modules.map((mod, i) => {
                  const isSelected = selectedIds.has(mod.id)
                  const modSeq = getModuleSeq(mod)
                  const modTmu = mod.total_tmu ?? null
                  const rowCls = [
                    'border-t',
                    editingModuleId === mod.id ? 'bg-amber-50' : isSelected ? 'bg-blue-50' : '',
                  ].filter(Boolean).join(' ')
                  return (
                    <tr key={mod.id} className={rowCls}>
                      <td className="p-1.5 text-center">
                        <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(mod.id)} />
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
                        {modTmu != null ? <b style={{ color: '#1a73e8' }}>{modTmu}</b> : '—'}
                      </td>
                      <td className="p-1.5 text-right">
                        {modTmu != null ? (modTmu * TMU_SEC).toFixed(3) : '—'}
                      </td>
                      <td className="p-1.5 text-right">{mod.action_count ?? '—'}</td>
                      <td className="p-1.5 text-center whitespace-nowrap">
                        <button
                          onClick={() => loadModule(mod)}
                          disabled={loadingModuleId !== null}
                          className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40"
                          title="載回建立器編輯"
                        >
                          {loadingModuleId === mod.id ? '載入中…' : '✏️ 編輯'}
                        </button>
                        <button
                          onClick={() => handleClone(mod.id, mod.name_zh)}
                          disabled={cloneModule.isPending}
                          className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40 ml-1"
                        >
                          📋 複製
                        </button>
                        <button
                          onClick={() => handleDelete(mod.id, mod.name_zh)}
                          disabled={deleteModule.isPending}
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

          {/* Multi-select bottom bar（F-03 跨層傳送） */}
          {selectedIds.size > 0 && (
            <div className="border-t pt-3 flex items-center justify-between gap-2">
              <span className="text-sm text-slate-600">已選 {selectedIds.size} 個</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setSelectedIds(new Set())}
                  className="text-xs px-2 py-1 border rounded text-slate-500 hover:bg-slate-50"
                >
                  清除
                </button>
                <button
                  onClick={handleSendToWi}
                  className="text-xs px-3 py-1 bg-blue-600 text-white rounded font-medium hover:bg-blue-700"
                >
                  傳送至 WI 工作區
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ═══ NL 覆蓋/填空對話框（audit §1.13） ═══ */}
      {nlAskOpen && nlResult && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setNlAskOpen(false)}
        >
          <div
            className="bg-white rounded-xl border shadow-2xl p-5 max-w-sm w-full mx-4 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <h3 className="font-semibold text-base">AI 預填</h3>
            <p className="text-sm text-slate-600">目前編輯區已有內容，AI 預填將如何處理？</p>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => applyNlDraft(nlResult, 'overwrite')}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium"
              >
                覆蓋目前欄位
              </button>
              <button
                onClick={() => applyNlDraft(nlResult, 'fill-empty')}
                className="px-4 py-2 border border-blue-300 text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-50"
              >
                只填空白欄位
              </button>
              <button
                onClick={() => setNlAskOpen(false)}
                className="px-4 py-1.5 text-slate-500 text-sm hover:text-slate-700"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
