// Tab 1: 動作模組工作區
// 左側 Builder — 槽位編輯 + NL Draft；右側 Pool — 個人模組列表 + 多選傳送
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRuleSetOptions, useVocab, useCalculate } from '../wi-workbench/api'
import { useCreateVocab } from '../master-data/api'
import type { VocabIn } from '../master-data/api'
import {
  defaultCycle, buildPayload, payloadToState, aBandOpts,
  type CycleState, type ASlot,
} from '../wi-workbench/cycle'
import { ComboBox } from '../../shared/ui/ComboBox'
import { Hint } from '../../shared/ui/Hint'
import { apiGet, apiPost } from '../../shared/api/client'
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

const HANDS = [{ v: 'RH', l: '右手' }, { v: 'LH', l: '左手' }, { v: 'BH', l: '雙手' }]
const HAND_NAME: Record<string, string> = { RH: '右手', LH: '左手', BH: '雙手' }

// ── Local Sel component (琥珀底表示可調整的數值格) ─────────────────────────────
function Sel({
  value, onChange, opts, cls,
}: {
  value: string
  onChange: (v: string) => void
  opts: { v: string; l: string }[]
  cls?: string
}) {
  return (
    <select
      className={cls ?? 'border-2 border-dashed border-slate-300 rounded px-1 py-0.5 text-sm bg-amber-50'}
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      {opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
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
  const [moduleNameZh, setModuleNameZh] = useState('')
  const [tmu, setTmu] = useState<number | null>(null)
  const [tech, setTech] = useState('')
  const [editingModuleId, setEditingModuleId] = useState<string | null>(null)
  const [source, setSource] = useState<'manual' | 'ai' | 'copied'>('manual')

  // NL Draft state
  const [nlDraft, setNlDraft] = useState('')
  const [nlLoading, setNlLoading] = useState(false)

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

  // ── Debounced backend calculate (400ms) ──────────────────────────────────────
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

  // ── Slot editing helpers (same pattern as WiWorkbench) ───────────────────────
  const set = (patch: Partial<CycleState>) => setCur(c => ({ ...c, ...patch }))
  const gm = cur.seq === 'GM'

  const vopts = (kind: string) =>
    vocab.filter(v => v.kind === kind).map(v => ({ v: v.id, l: v.name_zh }))

  const mkVocab = (kind: string, nvKey: 'obj' | 'from' | 'to', ph: string) => (
    <ComboBox
      options={vopts(kind)}
      value={cur.nv[nvKey]}
      placeholder={ph}
      onPick={id => set({ nv: { ...cur.nv, [nvKey]: id } })}
      onCreate={(name) =>
        createVocab.mutate({ kind, name_zh: name } as VocabIn, {
          onSuccess: v => setCur(c => ({ ...c, nv: { ...c.nv, [nvKey]: v.id } })),
        })
      }
    />
  )

  const aBlock = (slot: ASlot, onSlot: (s: ASlot) => void) => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle px-1 bg-blue-50 border border-blue-200 rounded">
      <Hint tip="A 移動/伸手：取 伸手、手度(扭轉)、腳步 三者分級的最大值；距離越大分數越高。" />
      {(['reach', 'twist', 'foot'] as const).map(comp => (
        <Sel
          key={comp}
          value={String(slot[comp] || 0)}
          opts={aBandOpts(opts.a_bands[comp], comp).map(o => ({ v: String(o.v), l: o.l }))}
          onChange={v => onSlot({ ...slot, [comp]: parseFloat(v) || 0 })}
        />
      ))}
    </span>
  )

  const bBlock = (key: 'b1' | 'b4') => (
    <span className="inline-flex items-center align-middle">
      <Hint tip="B 身體動作：彎腰/起身/站坐等輔助動作（無=0）。" />
      <Sel
        value={cur[key] ?? ''}
        onChange={v => set({ [key]: v || null } as Partial<CycleState>)}
        opts={[{ v: '', l: '身體:無' }, ...opts.b.filter(b => b.code !== 'b_none').map(b => ({ v: b.code, l: b.label }))]}
      />
    </span>
  )

  const gBlock = () => {
    const g = opts.g.find(x => x.code === cur.g)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="G 取得：抓握/接觸/拿取等方式；部分方式需勾修飾子，否則計 0。" />
        <Sel
          value={cur.g}
          onChange={v => set({ g: v, gMod: {} })}
          opts={[{ v: '', l: '—取得方式—' }, ...opts.g.map(o => ({ v: o.code, l: o.label }))]}
        />
        {g?.requires_modifier && g.modifier_key && (
          <Sel
            value={cur.gMod[g.modifier_key] ? '1' : '0'}
            onChange={v => set({ gMod: { ...cur.gMod, [g.modifier_key!]: v === '1' } })}
            opts={[{ v: '0', l: `—${g.modifier_key} 未勾—` }, { v: '1', l: `✓ ${g.modifier_key}` }]}
          />
        )}
      </span>
    )
  }

  const pBlock = () => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle">
      <Hint tip="P 放置：放/組/保持等 + 最多 2 個附加（對準、插入、壓合…）。選「對準」須再勾精度(<4mm)。" />
      <Sel
        value={cur.p_base}
        onChange={v => set({ p_base: v })}
        opts={[{ v: '', l: '—放置—' }, ...opts.p_bases.map(o => ({ v: o.code, l: o.label }))]}
      />
      {[0, 1].map(i => (
        <Sel
          key={i}
          value={cur.p_addons[i] ?? ''}
          onChange={v => {
            const a = cur.p_addons.filter((_, j) => j !== i)
            if (v) a.splice(i, 0, v)
            set({ p_addons: a.slice(0, 2) })
          }}
          opts={[{ v: '', l: '—附加—' }, ...opts.p_addons.map(o => ({ v: o.code, l: o.label }))]}
        />
      ))}
      {cur.p_addons.some(c => opts.p_addons.find(a => a.code === c)?.needs_precision) && (
        <Sel
          value={cur.precision ? '1' : '0'}
          onChange={v => set({ precision: v === '1' })}
          opts={[{ v: '0', l: '精度未勾' }, { v: '1', l: '精度<4mm' }]}
        />
      )}
    </span>
  )

  const mBlock = () => {
    const mv = opts.m_verbs.find(x => x.code === cur.m.verb)
    const k = mv?.pricing_kind
    const xo = opts.x.find(o => o.code === cur.x)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="M 控制移動：推/拉/旋轉/鎖附等受控動作；依動詞種類自動要距離、角度或圈數。" />
        <Sel
          value={cur.m.verb}
          onChange={v => set({ m: { ...cur.m, verb: v } })}
          opts={[{ v: '', l: '—控制動詞—' }, ...opts.m_verbs.map(o => ({ v: o.code, l: o.label }))]}
        />
        {(k === 'ladder' || k === 'foot' || k === 'distance_ladder') && (
          <Sel
            value={String(cur.m.distance)}
            onChange={v => set({ m: { ...cur.m, distance: parseFloat(v) } })}
            opts={[4, 12, 18, 30, 45].map(d => ({ v: String(d), l: '距離 ' + d + 'cm' }))}
          />
        )}
        {(k === 'hand' || k === 'hand_twist') && (
          <Sel
            value={String(cur.m.angle)}
            onChange={v => set({ m: { ...cur.m, angle: parseFloat(v) } })}
            opts={[{ v: '90', l: '≤90度' }, { v: '180', l: '≤180度' }]}
          />
        )}
        {(k === 'rotate' || k === 'rotation_by_diameter') && (
          <Sel
            value={String(cur.m.rev)}
            onChange={v => set({ m: { ...cur.m, rev: parseInt(v) } })}
            opts={[1, 2, 3].map(r => ({ v: String(r), l: r + '圈' }))}
          />
        )}
        <Hint tip="X 製程時間：機器/製程造成的等待（熱壓、測試、掃描）；連續式需輸入秒數。" />
        <Sel value={cur.x} onChange={v => set({ x: v })} opts={opts.x.map(o => ({ v: o.code, l: o.label }))} />
        {xo?.mode === 'seconds' && (
          <input
            type="number" min={0} step={0.1}
            className="border-2 border-dashed border-slate-300 rounded w-20 px-1 text-sm bg-amber-50"
            value={cur.x_sec}
            onChange={e => set({ x_sec: parseFloat(e.target.value) || 0 })}
            placeholder="秒"
          />
        )}
        <Hint tip="I 對準/檢查：定位對準或檢查確認動作的分級。" />
        <Sel value={cur.i} onChange={v => set({ i: v })} opts={opts.i.map(o => ({ v: o.code, l: o.label }))} />
      </span>
    )
  }

  // ── NL Draft ──────────────────────────────────────────────────────────────────
  async function handleNlDraft() {
    if (!nlDraft.trim()) return
    setNlLoading(true)
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = await apiPost<any>('/api/v2/minimost/nl-draft', { text: nlDraft.trim() })
      const next = payloadToState(res as Record<string, unknown>)
      setCur(c => ({ ...next, handCode: c.handCode, freq: c.freq, simoGroup: c.simoGroup, nv: c.nv }))
      setSource('ai')
      showToast('已從口語描述自動填入格位', 'ok')
    } catch (err) {
      const e = err as Error
      // 404 / 501 → feature not enabled
      if (e.message.startsWith('404') || e.message.startsWith('501')) {
        showToast('NL 解析功能尚未啟用', 'err')
      } else {
        showToast('NL 解析失敗：' + e.message, 'err')
      }
    } finally {
      setNlLoading(false)
    }
  }

  // ── Reset builder ─────────────────────────────────────────────────────────────
  function resetBuilder() {
    setCur(defaultCycle())
    setModuleNameZh('')
    setTmu(null)
    setTech('')
    setEditingModuleId(null)
    setSource('manual')
    setNlDraft('')
  }

  // ── Save / update module ──────────────────────────────────────────────────────
  async function handleSave() {
    if (!moduleNameZh.trim()) { showToast('請輸入動作模組名稱', 'err'); return }
    if (!tmu || tmu <= 0) { showToast('TMU 必須 > 0，請確認格位設定', 'err'); return }
    if (!opts) return

    const row = {
      hand: cur.handCode,
      frequency: cur.freq,
      cycle: buildPayload(cur, opts.code),
      sub_activity: moduleNameZh.trim(),
    }

    try {
      if (editingModuleId) {
        // 後端 MotionModuleUpdate 無 rows/source 欄位；列內容變更走 publish（發新版本）
        await updateModule.mutateAsync({
          id: editingModuleId,
          body: { name_zh: moduleNameZh.trim() },
        })
        await publishModule.mutateAsync({
          id: editingModuleId,
          body: { rows: [row], rule_set_code: opts.code },
        })
        showToast('已更新模組：' + moduleNameZh.trim(), 'ok')
      } else {
        // 後端 MotionModuleCreate 無 rows/status/source 欄位；rows 由 publish 建立版本
        const created = await createModule.mutateAsync({
          name_zh: moduleNameZh.trim(),
          scope: 'personal',
          keywords: [],
        })
        // Publish after creation
        await publishModule.mutateAsync({
          id: created.id,
          body: { rows: [row], rule_set_code: opts.code },
        })
        showToast('已新增至 Pool：' + moduleNameZh.trim(), 'ok')
      }
      resetBuilder()
    } catch (err) {
      showToast('儲存失敗：' + (err as Error).message, 'err')
    }
  }

  // ── Load module into builder ──────────────────────────────────────────────────
  // list 端點不含 rows（rows 巢狀於 detail 的 current_version_detail）→ 先 fetch detail
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
      setCur({ ...next, handCode: row.hand, freq: row.frequency })
      setModuleNameZh(mod.name_zh)
      setEditingModuleId(mod.id)
      setSource((detail.source as 'manual' | 'ai' | 'copied') ?? 'manual')
    } catch (err) {
      showToast('載入模組失敗：' + (err as Error).message, 'err')
    } finally {
      setLoadingModuleId(null)
    }
  }

  // ── Delete module ─────────────────────────────────────────────────────────────
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

  // ── Clone module ──────────────────────────────────────────────────────────────
  async function handleClone(id: string, name: string) {
    try {
      await cloneModule.mutateAsync(id)
      showToast('已複製：' + name, 'ok')
    } catch (err) {
      showToast('複製失敗：' + (err as Error).message, 'err')
    }
  }

  // ── Multi-select ──────────────────────────────────────────────────────────────
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

  // ── Module card helpers ───────────────────────────────────────────────────────
  // seq/hand 優先讀後端 top-level 摘要欄（list 端點也有），fallback
  // current_version_detail 第一列；都拿不到顯示 '—'，不得假裝是 0（audit §0.1）
  function getModuleSeq(mod: MotionModuleSummary): string {
    if (typeof mod.seq_kind === 'string' && mod.seq_kind) return mod.seq_kind
    const seq = mod.current_version_detail?.rows?.[0]?.cycle?.seq
    return typeof seq === 'string' ? seq : '—'
  }

  /** TMU 摘要走 top-level total_tmu；null（無已發布版本）→ 回 null 讓 UI 顯示 '—' */
  function getModuleTmu(mod: MotionModuleSummary): number | null {
    return mod.total_tmu ?? null
  }

  function getModuleHand(mod: MotionModuleSummary): string {
    const hand = mod.hand ?? mod.current_version_detail?.rows?.[0]?.hand
    if (!hand) return '—'
    return HAND_NAME[hand] ?? hand
  }

  // ── Sentence line style ───────────────────────────────────────────────────────
  const line = 'sentence-line p-2 rounded-lg bg-slate-50 border border-slate-100 leading-9 text-sm'

  const isSaving = createModule.isPending || updateModule.isPending || publishModule.isPending

  return (
    <>
      <Toast toast={toast} />
      <div className="flex gap-4 h-full min-h-0">

        {/* ── Left: Builder panel ─────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 space-y-3">
          <div className="bg-white rounded-xl border p-4 space-y-3">
            <h2 className="font-semibold text-base">動作模組編輯器</h2>

            {/* Module name */}
            <div className="flex items-center gap-2">
              <label className="text-sm text-slate-600 whitespace-nowrap">模組名稱</label>
              <input
                className="flex-1 border rounded px-2 py-1 text-sm"
                placeholder="例：右手伸取 M4 螺絲（必填）"
                value={moduleNameZh}
                onChange={e => setModuleNameZh(e.target.value)}
              />
              {editingModuleId && (
                <span className="text-xs text-blue-600 bg-blue-50 border border-blue-200 rounded px-2 py-0.5">
                  編輯中
                </span>
              )}
            </div>

            {/* NL Draft input — Tab 1 only (F-01) */}
            <div className="flex gap-2 items-start">
              <textarea
                className="flex-1 border rounded px-2 py-1 text-sm resize-none"
                rows={2}
                placeholder="用口語描述動作，系統自動填入格位（例：右手從料架取 M4 螺絲放到治具孔）"
                value={nlDraft}
                onChange={e => setNlDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleNlDraft() }}
              />
              <button
                onClick={handleNlDraft}
                disabled={nlLoading || !nlDraft.trim()}
                className="px-3 py-1.5 bg-violet-600 text-white rounded text-sm disabled:opacity-40 whitespace-nowrap"
              >
                {nlLoading ? '解析中…' : '自動填入'}
              </button>
            </div>

            {/* GM / CM selector */}
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <label className="flex items-center gap-1 cursor-pointer">
                <input type="radio" checked={gm} onChange={() => set({ seq: 'GM' })} />
                <span>一般移動 (GM)</span>
              </label>
              <label className="flex items-center gap-1 cursor-pointer">
                <input type="radio" checked={!gm} onChange={() => set({ seq: 'CM' })} />
                <span>控制移動 (CM)</span>
              </label>
              <div className="ml-auto flex items-center gap-2 text-slate-500">
                <span>使用手</span>
                <Sel
                  value={cur.handCode}
                  onChange={v => set({ handCode: v })}
                  opts={HANDS}
                  cls="border rounded px-1 py-0.5 text-sm"
                />
                <span>次數</span>
                <input
                  type="number" min={1}
                  className="border rounded w-14 px-1 py-0.5 text-sm"
                  value={cur.freq}
                  onChange={e => set({ freq: parseInt(e.target.value) || 1 })}
                />
              </div>
            </div>

            {/* Slot strip — sentence-based (same pattern as WiWorkbench) */}
            <div className="space-y-2">
              <p className={line}>
                {<Sel value={cur.handCode} onChange={v => set({ handCode: v })} opts={HANDS} cls="border rounded px-1 py-0.5 text-sm" />}
                {' 從 '}{mkVocab('from', 'from', '—來源—')}{' ，'}
                {aBlock(cur.a0, s => set({ a0: s }))}{' '}{bBlock('b1')}
                {' 以 '}{gBlock()}{' 取得「'}{mkVocab('object', 'obj', '—物件—')}{'」。'}
              </p>
              {gm ? (
                <p className={line}>
                  {'隨後 '}{aBlock(cur.a3, s => set({ a3: s }))}{' '}{bBlock('b4')}
                  {' 到 '}{mkVocab('to', 'to', '—目的地—')}{' ，以 '}{pBlock()}{' 放置。'}
                </p>
              ) : (
                <p className={line}>
                  {'在 '}{mkVocab('to', 'to', '—地點—')}{' ，'}{mBlock()}{' 實施控制移動。'}
                </p>
              )}
              <p className={line}>{'最後 '}{aBlock(cur.a6, s => set({ a6: s }))}{' 返回。'}</p>
            </div>

            {/* TMU preview + action */}
            <div className="flex flex-wrap items-center gap-3 pt-3 border-t text-sm">
              <span className="font-mono text-slate-500 text-xs">{tech || '—'}</span>
              <span className="ml-auto">
                TMU <b className="text-sky-700 text-lg">{tmu ?? '—'}</b>
                {tmu != null && <span className="text-slate-500 ml-1">≈ {(tmu * 0.036).toFixed(2)} 秒</span>}
              </span>
              {editingModuleId && (
                <button
                  onClick={resetBuilder}
                  className="px-2 py-1.5 border rounded text-slate-600 hover:bg-slate-50 text-sm"
                >
                  取消編輯
                </button>
              )}
              <button
                disabled={isSaving || !moduleNameZh.trim() || !tmu || tmu <= 0}
                onClick={handleSave}
                className="px-4 py-1.5 bg-blue-600 text-white rounded-lg disabled:opacity-40 text-sm font-medium"
              >
                {isSaving ? '儲存中…' : editingModuleId ? '更新模組' : '新增到 Pool'}
              </button>
            </div>

            {/* Source indicator */}
            {source === 'ai' && (
              <p className="text-xs text-violet-600">AI badge：此模組由 NL 草稿自動填入</p>
            )}
          </div>
        </div>

        {/* ── Right: ActionModulePool ─────────────────────────────────────────── */}
        <div className="w-80 flex-shrink-0 flex flex-col gap-3">
          <div className="bg-white rounded-xl border p-4 flex flex-col gap-3 h-full">
            <h2 className="font-semibold text-base">動作模組池</h2>

            {/* Search */}
            <input
              className="border rounded px-2 py-1 text-sm w-full"
              placeholder="搜尋模組名稱…"
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
            />

            {/* Module list */}
            <div className="flex-1 overflow-y-auto space-y-2 min-h-0">
              {modulesLoading && (
                <p className="text-slate-400 text-sm text-center py-4">載入中…</p>
              )}
              {!modulesLoading && modules.length === 0 && (
                <p className="text-slate-400 text-sm text-center py-4">
                  {searchQ ? '無相符模組' : '尚無個人模組，請在左側新增。'}
                </p>
              )}
              {modules.map(mod => {
                const isSelected = selectedIds.has(mod.id)
                const modSeq = getModuleSeq(mod)
                const modTmu = getModuleTmu(mod)
                return (
                  <div
                    key={mod.id}
                    className={`border rounded-lg p-2.5 transition-colors ${
                      isSelected
                        ? 'border-blue-400 bg-blue-50'
                        : editingModuleId === mod.id
                        ? 'border-amber-400 bg-amber-50'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(mod.id)}
                        className="mt-0.5 flex-shrink-0 cursor-pointer"
                      />
                      <div className="flex-1 min-w-0">
                        {/* Tags row */}
                        <div className="flex items-center gap-1 mb-1 flex-wrap">
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                            modSeq === 'GM'
                              ? 'bg-green-100 text-green-700'
                              : modSeq === 'CM'
                              ? 'bg-purple-100 text-purple-700'
                              : 'bg-slate-100 text-slate-500'
                          }`}>
                            {modSeq}
                          </span>
                          <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                            {getModuleHand(mod)}
                          </span>
                          {mod.source === 'ai' && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-violet-100 text-violet-700">
                              AI
                            </span>
                          )}
                          {mod.source === 'copied' && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-orange-100 text-orange-700">
                              複製
                            </span>
                          )}
                        </div>
                        {/* Name + TMU */}
                        <div className="flex items-baseline gap-1">
                          <span className="text-sm font-medium truncate flex-1" title={mod.name_zh}>
                            {mod.name_zh}
                          </span>
                          <b className="text-sm flex-shrink-0" style={{ color: '#1a73e8' }}>
                            {modTmu != null ? `${modTmu}T` : '—'}
                          </b>
                        </div>
                      </div>
                    </div>
                    {/* Action buttons */}
                    <div className="flex gap-1 mt-2">
                      <button
                        onClick={() => loadModule(mod)}
                        disabled={loadingModuleId !== null}
                        className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40"
                      >
                        {loadingModuleId === mod.id ? '載入中…' : '編輯'}
                      </button>
                      <button
                        onClick={() => handleClone(mod.id, mod.name_zh)}
                        disabled={cloneModule.isPending}
                        className="text-xs px-2 py-0.5 border rounded hover:bg-slate-50 disabled:opacity-40"
                      >
                        複製
                      </button>
                      <button
                        onClick={() => handleDelete(mod.id, mod.name_zh)}
                        disabled={deleteModule.isPending}
                        className="text-xs px-2 py-0.5 border border-red-200 text-red-600 rounded hover:bg-red-50 disabled:opacity-40"
                      >
                        刪除
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Multi-select bottom bar (F-03 跨層傳送) */}
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

      </div>
    </>
  )
}
