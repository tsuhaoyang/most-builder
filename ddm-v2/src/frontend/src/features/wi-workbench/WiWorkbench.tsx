import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRuleSetOptions, useVocab, useCalculate, useSaveWorksheet, type DefaultRuleSetInfo } from './api'
import { useWiStore, type Row } from './store'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { useWorkspace } from '../../shared/workspace'
import { TMU_SEC } from '../../shared/config'
import { useActiveRuleSet } from '../../shared/api/useActiveRuleSet'
import { RuleSetUnavailable } from '../../shared/ui/RuleSetUnavailable'
import { apiPost } from '../../shared/api/client'
import { ComboBox } from '../../shared/ui/ComboBox'
import { Hint } from '../../shared/ui/Hint'
import { useCreateVocab, type VocabIn } from '../master-data/api'
import {
  defaultCycle, buildPayload, aBandOpts, payloadToState,
  type CycleState, type ASlot, type ABand,
} from './cycle'
import { AiDraftPanel } from './AiDraftPanel'
import { useLevelStore } from '../level-system/store'
import { derive } from '../level-system/logic'
import { useWorksheetWorkspace } from './useWorksheetWorkspace'
import { useRowNarr } from './useRowNarr'
import {
  useWiTemplates, useInstantiateToWorksheet,
  type MotionModuleSummary,
} from '../workbench-v3/api'
import { DsxA3Suggestion } from '../workbench-v3/DsxA3Suggestion'
import { DsxUiEntry } from '../workbench-v3/DsxUiViewer'
import { Trans, useTranslation } from 'react-i18next'

// ─── Local types ───────────────────────────────────────────────────────────────
interface WiGroup { id: string; name: string; rowIds: string[] }
type SlotKey = 'a0' | 'b1' | 'g' | 'a3' | 'b4' | 'p' | 'm' | 'x' | 'i' | 'a6'

const HAND_CODES = ['RH', 'LH', 'BH'] as const

// ── [ADR-022 E-4] Toast（插入 WI 結果回饋）──────────────────────────────────────
interface WiToastState { msg: string; type: 'ok' | 'warn' | 'err' }

function WiToast({ toast }: { toast: WiToastState | null }) {
  if (!toast) return null
  const bg = toast.type === 'ok' ? 'bg-emerald-600' : toast.type === 'warn' ? 'bg-amber-500' : 'bg-red-600'
  return (
    <div className={`fixed bottom-6 right-6 z-50 px-4 py-2 rounded shadow-lg text-white text-sm ${bg}`}>
      {toast.msg}
    </div>
  )
}

// ── [ADR-022 E-4] 從 WI 庫插入 modal ───────────────────────────────────────────
// 列 category='wi-template' 可見清單（後端已做能見度過濾）；名稱/動作數/TMU＋搜尋。
// 選一筆 → 呼叫既有實體化端點 POST /worksheets/{wid}/rows/from-module（instantiate）。
// 獨立元件：只在 modal 開啟（掛載）時才發 list 查詢。
function InsertWiModal({ onClose, onInsert, inserting }: {
  onClose: () => void
  onInsert: (mod: MotionModuleSummary) => void
  inserting: boolean
}) {
  const { t } = useTranslation()
  const { data: wis = [], isLoading } = useWiTemplates()
  const [q, setQ] = useState('')
  const filtered = q.trim()
    ? wis.filter(w => w.name_zh.toLowerCase().includes(q.trim().toLowerCase()))
    : wis
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-xl border shadow-2xl p-5 max-w-2xl w-full mx-4 space-y-3"
        onClick={e => e.stopPropagation()}
        data-testid="insert-wi-modal"
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">{t('workbench.wiEditor.insertTitle')}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg leading-none" aria-label={t('workbench.wiEditor.closeAria')}>✕</button>
        </div>
        <input
          className="w-full border rounded px-2 py-1.5 text-sm"
          placeholder={t('workbench.wiEditor.searchPlaceholder')}
          value={q}
          onChange={e => setQ(e.target.value)}
          autoFocus
        />
        <div className="max-h-80 overflow-y-auto border rounded">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-slate-100">
              <tr className="text-left">
                <th className="p-2">{t('workbench.wiEditor.colName')}</th>
                <th className="p-2 w-20 text-right">{t('workbench.wiEditor.colActions')}</th>
                <th className="p-2 w-24 text-right">TMU</th>
                <th className="p-2 w-20"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={4} className="p-3 text-slate-400 text-center">{t('workbench.wiEditor.loading')}</td></tr>
              )}
              {!isLoading && filtered.length === 0 && (
                <tr><td colSpan={4} className="p-3 text-slate-400 text-center">
                  {q ? t('workbench.wiEditor.noMatch') : t('workbench.wiEditor.empty')}
                </td></tr>
              )}
              {filtered.map(w => (
                <tr key={w.id} className="border-t hover:bg-slate-50">
                  <td className="p-2 max-w-sm"><span className="truncate block" title={w.name_zh}>{w.name_zh}</span></td>
                  <td className="p-2 text-right">{w.action_count ?? '—'}</td>
                  <td className="p-2 text-right">
                    {w.total_tmu != null ? <b className="text-blue-700">{w.total_tmu}</b> : '—'}
                  </td>
                  <td className="p-2 text-right">
                    <button
                      onClick={() => onInsert(w)}
                      disabled={inserting || !w.current_version}
                      title={!w.current_version ? t('workbench.wiEditor.noVersionTitle') : undefined}
                      className="text-xs px-2.5 py-1 bg-blue-600 text-white rounded disabled:opacity-40"
                    >
                      {inserting ? t('workbench.wiEditor.inserting') : t('workbench.wiEditor.insert')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── [ADR-023 §3.4-4] 使用已下架規則版本的警示徽章 ──────────────────────────────
// 純提示：本工序表基於已下架的 rule-set 版本；值仍為原版回放（正確），只是重新分析時
// 建議改用啟用中版本。只讀後端 status，前端不自行判斷版本新舊（守則）。
// 非 retired（published/draft）或 default_rule_set===null → 不顯示（不誤報）。
function RetiredRuleSetBadge({ drs }: { drs: DefaultRuleSetInfo | null | undefined }) {
  if (!drs || drs.status !== 'retired') return null
  // 只有 <Trans>，不需要 t()
  return (
    <div
      data-testid="worksheet-retired-ruleset-badge"
      className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 flex items-start gap-2"
    >
      <span aria-hidden className="mt-0.5">⚠</span>
      <span>
        <Trans
          i18nKey="workbench.wiEditor.retiredBadge"
          values={{ code: drs.code }}
          components={{ code: <span className="font-mono" /> }}
        />
      </span>
    </div>
  )
}

const SLOT_COLORS: Record<string, { filled: string; empty: string }> = {
  A: { filled: 'bg-blue-600 text-white border-blue-600', empty: 'bg-blue-50 text-blue-400 border-blue-200 border-dashed' },
  B: { filled: 'bg-slate-500 text-white border-slate-500', empty: 'bg-slate-50 text-slate-400 border-slate-200 border-dashed' },
  G: { filled: 'bg-green-600 text-white border-green-600', empty: 'bg-green-50 text-green-400 border-green-200 border-dashed' },
  P: { filled: 'bg-amber-500 text-white border-amber-500', empty: 'bg-amber-50 text-amber-400 border-amber-200 border-dashed' },
  M: { filled: 'bg-amber-500 text-white border-amber-500', empty: 'bg-amber-50 text-amber-400 border-amber-200 border-dashed' },
  X: { filled: 'bg-purple-600 text-white border-purple-600', empty: 'bg-purple-50 text-purple-400 border-purple-200 border-dashed' },
  I: { filled: 'bg-teal-600 text-white border-teal-600', empty: 'bg-teal-50 text-teal-400 border-teal-200 border-dashed' },
}

// ─── Sel: small native select (amber-bg) ───────────────────────────────────────
function Sel({ value, onChange, opts, cls }: {
  value: string; onChange: (v: string) => void
  opts: { v: string; l: string }[]; cls?: string
}) {
  return (
    <select
      className={cls ?? 'border-2 border-dashed border-slate-300 rounded px-1 py-0.5 text-sm bg-amber-50'}
      value={value} onChange={e => onChange(e.target.value)}
    >
      {opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
}

// ─── A-slot helpers ────────────────────────────────────────────────────────────
function aIdx(val: number, bands: ABand[]): number {
  if (val === 0) return 0
  for (const b of bands) {
    const bv = b.max_value == null ? 999 : b.max_value
    if (val === bv) return b.index
  }
  return 0
}

function aAbbrev(slot: ASlot, aBands: { reach: ABand[]; twist: ABand[]; foot: ABand[] }): string {
  const m = Math.max(
    aIdx(slot.reach, aBands.reach),
    aIdx(slot.twist, aBands.twist),
    aIdx(slot.foot, aBands.foot),
  )
  return m > 0 ? `A${m}` : '—'
}

function aIsFilled(slot: ASlot): boolean {
  return slot.reach > 0 || slot.twist > 0 || slot.foot > 0
}

// ─── Main component ────────────────────────────────────────────────────────────
export function WiWorkbench() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const active = useActiveRuleSet()
  const { data: opts, error: optsErr } = useRuleSetOptions(active.data?.code)
  const { data: vocab = [] } = useVocab()
  const rowNarr = useRowNarr()   // 顯示時重算，不入 state（切語言後舊列才會跟著變）
  const calc = useCalculate()
  const createVocab = useCreateVocab()
  const activeWs = useWorkspace(s => s.activeWs)
  const save = useSaveWorksheet(activeWs)
  const qc = useQueryClient()
  const { data: wsData } = useWorksheetWorkspace(activeWs)
  const { rows, addRow, delRow, setRows, totalTmu } = useWiStore()

  // ── existing editor state ──────────────────────────────────────────────────
  const [cur, setCur] = useState<CycleState>(defaultCycle())
  const [tmu, setTmu] = useState<number | null>(null)
  const [tech, setTech] = useState('')
  const [saveMsg, setSaveMsg] = useState('')
  const editable = canEdit(me)

  // ── [D] drag state ──────────────────────────────────────────────────────────
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null)

  // ── [D] multi-select ────────────────────────────────────────────────────────
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set())

  // ── [E] WI groups state ────────────────────────────────────────────────────
  const [wiGroups, setWiGroups] = useState<WiGroup[]>([])
  const [wiNameInput, setWiNameInput] = useState('')
  const [expandedWiIds, setExpandedWiIds] = useState<Set<string>>(new Set())
  const [highlightedRowIds, setHighlightedRowIds] = useState<Set<string>>(new Set())

  // ── [C] slot modal ─────────────────────────────────────────────────────────
  const [activeSlot, setActiveSlot] = useState<SlotKey | null>(null)

  // ── [ADR-022 E-4] 從 WI 庫插入（實體化搬進案件編輯情境）────────────────────────
  const [insertWiOpen, setInsertWiOpen] = useState(false)
  const instantiate = useInstantiateToWorksheet()
  const [wiToast, setWiToast] = useState<WiToastState | null>(null)
  const wiToastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  function showWiToast(msg: string, type: WiToastState['type'] = 'ok') {
    if (wiToastTimer.current) clearTimeout(wiToastTimer.current)
    setWiToast({ msg, type })
    wiToastTimer.current = setTimeout(() => setWiToast(null), 3500)
  }

  async function insertWiFromLibrary(mod: MotionModuleSummary) {
    if (!activeWs) { showWiToast(t('workbench.wiEditor.needWorksheet'), 'err'); return }
    try {
      // 既有實體化端點：POST /api/v2/worksheets/{wid}/rows/from-module（body: module_id）。
      // hook onSuccess 會 invalidate ['worksheet', wid] → wsData refetch → 上方 effect
      // setRows 重灌工時表（後端已算好每列 TMU，前端不自算）。
      const result = await instantiate.mutateAsync({
        worksheetId: activeWs,
        moduleId: mod.id,
        baseRevision: useWiStore.getState().revisionNo,
      })
      if (typeof result.revision_no === 'number') {
        useWiStore.getState().setRevisionMeta({
          revisionNo: result.revision_no,
          contentHash: result.content_hash ?? null,
        })
      }
      setInsertWiOpen(false)
      showWiToast(t('workbench.wiEditor.inserted', { name: mod.name_zh, count: result.new_rows.length }), 'ok')
      // TMU 漂移警告（沿 ProcessWorkspace 既有機制：instantiate 回應內 tmu_drift）
      if (result.tmu_drift && result.tmu_drift.length > 0) {
        setTimeout(() => showWiToast(t('workbench.wiEditor.insertedRecalc'), 'warn'), 1500)
      }
    } catch (e) {
      const err = e as Error & { code?: string | null; humanMessage?: string; status?: number }
      if (err.status === 409 && err.code === 'WORKSHEET_REVISION_CONFLICT') {
        showWiToast(t('workbench.wiEditor.insertConflict'), 'err')
        qc.invalidateQueries({ queryKey: ['worksheet', activeWs] })
      } else {
        showWiToast(t('workbench.wiEditor.insertFailed', { message: err.humanMessage || err.message }), 'err')
      }
    }
  }

  // ── debounced backend calculate ───────────────────────────────────────────
  const payload = useMemo(() => (opts ? buildPayload(cur, opts.code) : null), [cur, opts])
  useEffect(() => {
    if (!payload) { setTmu(null); setTech(''); return }
    const id = setTimeout(() => calc.mutate(payload, {
      onSuccess: r => { setTmu(r.total_tmu); setTech(r.tech_line) },
      onError: () => { setTmu(null); setTech('') },
    }), 250)
    return () => clearTimeout(id)
  }, [JSON.stringify(payload)]) // eslint-disable-line react-hooks/exhaustive-deps

  // 錯誤態必須與載入態可分（否則設定錯誤會永遠停在 spinner）
  const ruleSetErr = active.error ?? optsErr
  if (ruleSetErr) return <div className="bg-white rounded-xl border p-6"><RuleSetUnavailable error={ruleSetErr} /></div>
  if (!opts) return <div className="bg-white rounded-xl border p-6 text-slate-500">{t('workbench.loadingRuleSet')}</div>

  // ── helpers ───────────────────────────────────────────────────────────────
  const set = (patch: Partial<CycleState>) => setCur(c => ({ ...c, ...patch }))
  const gm = cur.seq === 'GM'
  const vopts = (kind: string) => vocab.filter(v => v.kind === kind).map(v => ({ v: v.id, l: v.name_zh }))
  const vname = (_kind: string, id: string) => vocab.find(v => v.id === id)?.name_zh ?? ''
  const label = (kind: string, code: string) => {
    const m: Record<string, { code: string; label: string }[]> = { g: opts.g, p_base: opts.p_bases, m_verb: opts.m_verbs }
    return m[kind]?.find(o => o.code === code)?.label ?? ''
  }
  const mkVocab = (kind: string, nvKey: 'obj' | 'from' | 'to', ph: string) => (
    <ComboBox options={vopts(kind)} value={cur.nv[nvKey]} placeholder={ph}
      onPick={id => set({ nv: { ...cur.nv, [nvKey]: id } })}
      onCreate={editable ? (name) => createVocab.mutate({ kind, name_zh: name } as VocabIn,
        { onSuccess: v => setCur(c => ({ ...c, nv: { ...c.nv, [nvKey]: v.id } })) }) : undefined} />
  )

  // ── slot builder helpers (used in modal) ───────────────────────────────────
  const aBlock = (slot: ASlot, onSlot: (s: ASlot) => void) => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle px-1 bg-blue-50 border border-blue-200 rounded">
      <Hint tip={t('workbench.wiEditor.aHint')} />
      {(['reach', 'twist', 'foot'] as const).map(comp => (
        <Sel key={comp} value={String(slot[comp] || 0)}
          opts={aBandOpts(opts.a_bands[comp], comp).map(o => ({ v: String(o.v), l: o.l }))}
          onChange={v => onSlot({ ...slot, [comp]: parseFloat(v) || 0 })} />
      ))}
    </span>
  )
  const bBlock = (key: 'b1' | 'b4') => (
    <span className="inline-flex items-center align-middle">
      <Hint tip={t('workbench.slot.b.hint')} />
      <Sel value={cur[key] ?? ''} onChange={v => set({ [key]: v || null } as Partial<CycleState>)}
        opts={[{ v: '', l: t('workbench.slot.b.none') }, ...opts.b.filter(b => b.code !== 'b_none').map(b => ({ v: b.code, l: b.label }))]} />
    </span>
  )
  const gBlock = () => {
    const g = opts.g.find(x => x.code === cur.g)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip={t('workbench.slot.g.hint')} />
        <Sel value={cur.g} onChange={v => set({ g: v, gMod: {} })}
          opts={[{ v: '', l: t('workbench.wiEditor.gPick') }, ...opts.g.map(o => ({ v: o.code, l: o.label }))]} />
        {g?.requires_modifier && g.modifier_key && (
          <Sel value={cur.gMod[g.modifier_key] ? '1' : '0'}
            onChange={v => set({ gMod: { ...cur.gMod, [g.modifier_key!]: v === '1' } })}
            opts={[
              { v: '0', l: t('workbench.slot.g.modifierOff', { key: g.modifier_key }) },
              { v: '1', l: `✓ ${g.modifier_key}` },
            ]} />
        )}
      </span>
    )
  }
  const pBlock = () => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle">
      <Hint tip={t('workbench.slot.p.hint')} />
      <Sel value={cur.p_base} onChange={v => set({ p_base: v })}
        opts={[{ v: '', l: t('workbench.wiEditor.pPick') }, ...opts.p_bases.map(o => ({ v: o.code, l: o.label }))]} />
      {[0, 1].map(i => (
        <Sel key={i} value={cur.p_addons[i] ?? ''}
          onChange={v => { const a = cur.p_addons.filter((_, j) => j !== i); if (v) a.splice(i, 0, v); set({ p_addons: a.slice(0, 2) }) }}
          opts={[{ v: '', l: t('workbench.wiEditor.pAddon') }, ...opts.p_addons.map(o => ({ v: o.code, l: o.label }))]} />
      ))}
      {cur.p_addons.some(c => opts.p_addons.find(a => a.code === c)?.needs_precision) && (
        <Sel value={cur.precision ? '1' : '0'} onChange={v => set({ precision: v === '1' })}
          opts={[{ v: '0', l: t('workbench.slot.p.precisionOff') }, { v: '1', l: t('workbench.slot.p.precisionOn') }]} />
      )}
    </span>
  )
  // CM sub-blocks (used in modal for M/X/I separately)
  const mVerbBlock = () => {
    const mv = opts.m_verbs.find(x => x.code === cur.m.verb)
    const k = mv?.pricing_kind
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip={t('workbench.slot.m.hint')} />
        <Sel value={cur.m.verb} onChange={v => set({ m: { ...cur.m, verb: v } })}
          opts={[{ v: '', l: t('workbench.slot.m.verbNone') }, ...opts.m_verbs.map(o => ({ v: o.code, l: o.label }))]} />
        {(k === 'ladder' || k === 'foot' || k === 'distance_ladder') && (
          <Sel value={String(cur.m.distance)} onChange={v => set({ m: { ...cur.m, distance: parseFloat(v) } })}
            opts={[4, 12, 18, 30, 45].map(d => ({ v: String(d), l: t('workbench.slot.m.distance', { cm: d }) }))} />)}
        {(k === 'hand' || k === 'hand_twist') && (
          <Sel value={String(cur.m.angle)} onChange={v => set({ m: { ...cur.m, angle: parseFloat(v) } })}
            opts={[{ v: '90', l: t('workbench.slot.m.angle90') }, { v: '180', l: t('workbench.slot.m.angle180') }]} />)}
        {(k === 'rotate' || k === 'rotation_by_diameter') && (
          <Sel value={String(cur.m.rev)} onChange={v => set({ m: { ...cur.m, rev: parseInt(v) } })}
            opts={[1, 2, 3].map(r => ({ v: String(r), l: t('workbench.slot.m.revolutions', { count: r }) }))} />)}
      </span>
    )
  }
  const xBlock = () => {
    const xo = opts.x.find(o => o.code === cur.x)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip={t('workbench.slot.x.hint')} />
        <Sel value={cur.x} onChange={v => set({ x: v })} opts={opts.x.map(o => ({ v: o.code, l: o.label }))} />
        {xo?.mode === 'seconds' && (
          <input type="number" min={0} step={0.1}
            className="border-2 border-dashed border-slate-300 rounded w-20 px-1 text-sm bg-amber-50"
            value={cur.x_sec} onChange={e => set({ x_sec: parseFloat(e.target.value) || 0 })} placeholder={t('workbench.slot.x.secondsPlaceholder')} />
        )}
      </span>
    )
  }
  const iBlock = () => (
    <span className="inline-flex items-center align-middle">
      <Hint tip={t('workbench.slot.i.hint')} />
      <Sel value={cur.i} onChange={v => set({ i: v })} opts={opts.i.map(o => ({ v: o.code, l: o.label }))} />
    </span>
  )

  // ── [C] slot block definitions ─────────────────────────────────────────────
  const gmSlots: Array<{ key: SlotKey; label: string; param: string; isFilled: boolean; abbrev: string }> = [
    {
      key: 'a0', label: t('workbench.wiEditor.slotLabel.aGet'), param: 'A',
      isFilled: aIsFilled(cur.a0),
      abbrev: aAbbrev(cur.a0, opts.a_bands),
    },
    {
      key: 'b1', label: 'B1', param: 'B',
      isFilled: !!cur.b1,
      abbrev: cur.b1 ? (opts.b.find(b => b.code === cur.b1)?.label.slice(0, 4) ?? 'B?') : '—',
    },
    {
      key: 'g', label: t('workbench.wiEditor.slotLabel.g'), param: 'G',
      isFilled: !!cur.g,
      abbrev: cur.g ? (opts.g.find(g => g.code === cur.g)?.label.slice(0, 4) ?? 'G?') : '—',
    },
    {
      key: 'a3', label: t('workbench.wiEditor.slotLabel.aPlace'), param: 'A',
      isFilled: aIsFilled(cur.a3),
      abbrev: aAbbrev(cur.a3, opts.a_bands),
    },
    {
      key: 'b4', label: 'B4', param: 'B',
      isFilled: !!cur.b4,
      abbrev: cur.b4 ? (opts.b.find(b => b.code === cur.b4)?.label.slice(0, 4) ?? 'B?') : '—',
    },
    {
      key: 'p', label: t('workbench.wiEditor.slotLabel.p'), param: 'P',
      isFilled: !!cur.p_base,
      abbrev: cur.p_base ? (opts.p_bases.find(p => p.code === cur.p_base)?.label.slice(0, 4) ?? 'P?') : '—',
    },
    {
      key: 'a6', label: t('workbench.wiEditor.slotLabel.aReturn'), param: 'A',
      isFilled: aIsFilled(cur.a6),
      abbrev: aAbbrev(cur.a6, opts.a_bands),
    },
  ]
  const cmSlots: Array<{ key: SlotKey; label: string; param: string; isFilled: boolean; abbrev: string }> = [
    {
      key: 'a0', label: t('workbench.wiEditor.slotLabel.aGet'), param: 'A',
      isFilled: aIsFilled(cur.a0),
      abbrev: aAbbrev(cur.a0, opts.a_bands),
    },
    {
      key: 'b1', label: 'B1', param: 'B',
      isFilled: !!cur.b1,
      abbrev: cur.b1 ? (opts.b.find(b => b.code === cur.b1)?.label.slice(0, 4) ?? 'B?') : '—',
    },
    {
      key: 'g', label: t('workbench.wiEditor.slotLabel.g'), param: 'G',
      isFilled: !!cur.g,
      abbrev: cur.g ? (opts.g.find(g => g.code === cur.g)?.label.slice(0, 4) ?? 'G?') : '—',
    },
    {
      key: 'm', label: t('workbench.wiEditor.slotLabel.m'), param: 'M',
      isFilled: !!cur.m.verb,
      abbrev: cur.m.verb ? (opts.m_verbs.find(m => m.code === cur.m.verb)?.label.slice(0, 4) ?? 'M?') : '—',
    },
    {
      key: 'x', label: t('workbench.wiEditor.slotLabel.x'), param: 'X',
      isFilled: cur.x !== 'x_none',
      abbrev: cur.x !== 'x_none' ? (opts.x.find(x => x.code === cur.x)?.label.slice(0, 4) ?? 'X?') : '—',
    },
    {
      key: 'i', label: t('workbench.wiEditor.slotLabel.i'), param: 'I',
      isFilled: cur.i !== 'i_none',
      abbrev: cur.i !== 'i_none' ? (opts.i.find(i => i.code === cur.i)?.label.slice(0, 4) ?? 'I?') : '—',
    },
    {
      key: 'a6', label: t('workbench.wiEditor.slotLabel.aReturn'), param: 'A',
      isFilled: aIsFilled(cur.a6),
      abbrev: aAbbrev(cur.a6, opts.a_bands),
    },
  ]
  const currentSlots = gm ? gmSlots : cmSlots

  // Modal label per slot
  // 與 workbench-v3/SlotBuilder 的格位 modal 抬頭逐字相同 → 共用同一組 key，
  // 不再各抄一份（同一個格位在兩個編輯器叫不同名字是遲早會發生的漂移）。
  const slotModalLabel = (k: SlotKey) => t(`workbench.slot.modalTitle.${k}`)

  // ── [D] DnD handlers ───────────────────────────────────────────────────────
  function onDragStart(idx: number, e: React.DragEvent) {
    setDragIdx(idx)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(idx))
  }
  function onDragOver(idx: number, e: React.DragEvent) {
    e.preventDefault()
    setDragOverIdx(idx)
  }
  function onDrop(idx: number, e: React.DragEvent) {
    e.preventDefault()
    if (dragIdx !== null && dragIdx !== idx) {
      const arr = [...rows]
      const [item] = arr.splice(dragIdx, 1)
      arr.splice(idx, 0, item)
      setRows(arr)
    }
    setDragIdx(null)
    setDragOverIdx(null)
  }
  function onDragEnd() { setDragIdx(null); setDragOverIdx(null) }

  // ── helper: update individual row ──────────────────────────────────────────
  function updateRow(id: string, patch: Partial<Row>) {
    setRows(rows.map(r => r.id === id ? { ...r, ...patch } : r))
  }

  // ── [D-2] toggle row selection ─────────────────────────────────────────────
  function toggleSelect(id: string) {
    const next = new Set(selectedRowIds)
    if (next.has(id)) next.delete(id); else next.add(id)
    setSelectedRowIds(next)
  }

  // ── [E] WI group handlers ──────────────────────────────────────────────────
  function addToWi() {
    if (selectedRowIds.size === 0 || !wiNameInput.trim()) return
    setWiGroups(g => [...g, { id: crypto.randomUUID(), name: wiNameInput.trim(), rowIds: [...selectedRowIds] }])
    setSelectedRowIds(new Set())
    setWiNameInput('')
  }
  function toggleWiExpand(id: string) {
    const n = new Set(expandedWiIds)
    if (n.has(id)) n.delete(id); else n.add(id)
    setExpandedWiIds(n)
  }
  function selectWiGroup(group: WiGroup) {
    setHighlightedRowIds(new Set(group.rowIds))
  }
  function deleteWiGroup(id: string) {
    setWiGroups(g => g.filter(w => w.id !== id))
    setHighlightedRowIds(new Set())
  }
  function wiGroupTmu(group: WiGroup): number {
    // ADR-020：SIMO 標記列（simoGroup 非空）貢獻 0，其餘 Σ(tmu × freq)
    return rows.filter(r => group.rowIds.includes(r.id) && !(r.simoGroup || '').trim())
      .reduce((sum, r) => sum + (r.tmu * (r.freq || 1)), 0)
  }

  // ── existing add/save functions ────────────────────────────────────────────
  function add() {
    if (tmu == null) return
    addRow({
      id: crypto.randomUUID(), seq: cur.seq, handCode: cur.handCode, freq: cur.freq, simoGroup: cur.simoGroup,
      // narr 留空＝「還沒有後端敘述」；預覽句由 useRowNarr 在顯示時重算
      nv: { ...cur.nv }, narr: '', tmu, seconds: tmu * TMU_SEC, payload,
    } as Row)
  }

  async function saveAsTemplate() {
    if (!opts) return
    const name = window.prompt(t('workbench.wiEditor.templateNamePrompt')); if (!name) return
    const kw = window.prompt(t('workbench.wiEditor.templateKeywordsPrompt'), '') || ''
    try {
      await apiPost('/api/v2/motion-templates', {
        name_zh: name, seq_kind: cur.seq,
        keywords: kw.split(/[,，]/).map(s => s.trim()).filter(Boolean), cycle_template: buildPayload(cur, opts.code),
      })
      qc.invalidateQueries({ queryKey: ['templates'] })
      setSaveMsg(t('workbench.wiEditor.templateSaved', { name }))
    } catch (e) { setSaveMsg(t('workbench.wiEditor.templateSaveFailed', { message: (e as Error).message })) }
  }

  async function doSave() {
    setSaveMsg(t('workbench.wiEditor.saving'))
    const lv = useLevelStore.getState()
    const d = derive(rows, lv.levelMap, lv.groupMeta, rowNarr)
    const baseRevision = useWiStore.getState().revisionNo
    const body = {
      base_revision: baseRevision ?? undefined,
      rows: rows.map((r, i) => {
        const e = d[i] || {}
        return {
          id: r.id, seq_no: i + 1, hand: r.handCode,
          object_vocab_id: r.nv.obj || null,
          from_vocab_id: r.nv.from || null, to_vocab_id: r.nv.to || null,
          frequency: r.freq, simo_group_id: r.simoGroup || null, narrative: rowNarr(r), cycle: r.payload,
          level: {
            coefficient: e.coefficient ?? 1, ascription: e.ascription ?? 'main', level: e.level ?? String(i + 1),
            countersignature: e.countersignature ?? null, parent_countersignature: e.parent_countersignature ?? null,
            order: e.order ?? null, number: e.number ?? null, number_count: e.number_count ?? null,
            machine_count: 1, manpower: 1,
          },
        }
      }),
    }
    try {
      const res = await save.mutateAsync(body)
      if (typeof res.revision_no === 'number') {
        useWiStore.getState().setRevisionMeta({
          revisionNo: res.revision_no,
          contentHash: res.content_hash ?? null,
        })
      }
      qc.invalidateQueries({ queryKey: ['wi-preview'] })
      qc.invalidateQueries({ queryKey: ['versions'] })
      qc.invalidateQueries({ queryKey: ['worksheet', activeWs] })
      setSaveMsg(t('workbench.wiEditor.saved', {
        rows: res.rows.length,
        tmu: res.total_tmu,
        seconds: (res.total_tmu * TMU_SEC).toFixed(2),
        rev: res.revision_no ?? '?',
      }))
    } catch (e) {
      const err = e as Error & { code?: string | null; humanMessage?: string; status?: number }
      if (err.status === 409 && err.code === 'WORKSHEET_REVISION_CONFLICT') {
        setSaveMsg(t('workbench.wiEditor.saveConflict'))
        qc.invalidateQueries({ queryKey: ['worksheet', activeWs] })
      } else {
        setSaveMsg(t('workbench.wiEditor.saveFailed', { message: err.humanMessage || err.message }))
      }
    }
  }

  const total = totalTmu()

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">

      {/* ═══ [ADR-023 §3.4-4] 下架規則版本警示（工序表情境頂部）═══ */}
      <RetiredRuleSetBadge drs={wsData?.default_rule_set} />

      {/* ═══ Editor section ═══ */}
      <div className="bg-white rounded-xl border p-4 space-y-3">

        {/* [F] AI Draft panel（取代舊 NL 預填） */}
        <AiDraftPanel
          ruleSetCode={opts?.code}
          worksheetId={activeWs || null}
          canWriteReviews={editable}
          onAdoptCycle={(cycle) => {
            setCur((c) => {
              const next = payloadToState(cycle)
              // 保留手別／語彙情境，不整頁清空
              return { ...next, handCode: c.handCode || next.handCode, nv: { ...c.nv } }
            })
          }}
          onLegacyFill={(patch) => setCur((c) => ({ ...c, ...patch }))}
        />

        {/* Sequence type + hand */}
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">{t('workbench.wiEditor.editorTitle')}</h2>
          <label className="text-sm flex items-center gap-1">
            <input type="radio" checked={gm} onChange={() => set({ seq: 'GM' })} /> {t('workbench.wiEditor.seqGm')}
          </label>
          <label className="text-sm flex items-center gap-1">
            <input type="radio" checked={!gm} onChange={() => set({ seq: 'CM' })} /> {t('workbench.wiEditor.seqCm')}
          </label>
          <div className="flex items-center gap-1 ml-2">
            <span className="text-sm text-slate-500">{t('workbench.wiEditor.handLabel')}</span>
            <Sel value={cur.handCode} onChange={v => set({ handCode: v })}
              opts={HAND_CODES.map(code => ({ v: code, l: t(`workbench.hand.${code}`) }))}
              cls="border rounded px-1 py-0.5 text-sm" />
          </div>
        </div>

        {/* Context fields (vocabulary) */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">{t('workbench.wiEditor.fromLabel')}</span>{mkVocab('from', 'from', t('workbench.wiEditor.vocabFrom'))}
          <span className="text-slate-500">{t('workbench.wiEditor.getLabel')}</span>{mkVocab('object', 'obj', t('workbench.wiEditor.vocabObject'))}
          {gm && <><span className="text-slate-500">{t('workbench.wiEditor.toLabel')}</span>{mkVocab('to', 'to', t('workbench.wiEditor.vocabTo'))}</>}
          {!gm && <><span className="text-slate-500">{t('workbench.wiEditor.atLabel')}</span>{mkVocab('to', 'to', t('workbench.wiEditor.vocabWhere'))}</>}
        </div>

        {/* [C] Visual slot blocks */}
        <div className="flex flex-wrap gap-2 py-1">
          {currentSlots.map(slot => {
            const clr = SLOT_COLORS[slot.param] ?? SLOT_COLORS['A']
            const cls = `flex flex-col items-center justify-center min-w-[72px] px-2 py-2 rounded-lg border-2
              cursor-pointer transition-all select-none hover:opacity-80 active:scale-95
              ${slot.isFilled ? clr.filled : clr.empty}`
            return (
              <button key={slot.key} className={cls} onClick={() => setActiveSlot(slot.key)}
                title={slotModalLabel(slot.key)}>
                <span className="text-[10px] font-medium opacity-70 leading-none mb-1">{slot.label}</span>
                <span className="font-bold text-sm leading-none">{slot.abbrev}</span>
                <span className={`w-2 h-2 rounded-full mt-1.5 ${slot.isFilled ? 'bg-green-400' : 'bg-gray-300'}`} />
              </button>
            )
          })}
        </div>

        {/* Tech line + TMU + controls */}
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t text-sm">
          <span className="text-slate-500">{t('workbench.wiEditor.freqLabel')}</span>
          <input type="number" min={1} className="border rounded w-16 px-1 py-0.5"
            value={cur.freq} onChange={e => set({ freq: parseInt(e.target.value) || 1 })} />
          <span className="text-slate-500">{t('workbench.wiEditor.simoLabel')}</span>
          <input className="border rounded w-20 px-1 py-0.5" value={cur.simoGroup}
            onChange={e => set({ simoGroup: e.target.value })} placeholder={t('workbench.wiEditor.simoPlaceholder')} />
          <span className="font-mono text-slate-500 text-xs">{tech || '—'}</span>
          <span className="ml-auto">
            <Trans
              i18nKey="workbench.wiEditor.rowTmu"
              values={{ tmu: tmu ?? '—', seconds: tmu != null ? (tmu * TMU_SEC).toFixed(2) : '—' }}
              components={{ tmu: <b className="text-sky-700 text-lg" /> }}
            />
          </span>
          {editable && <button onClick={saveAsTemplate} className="px-2 py-1.5 border rounded">{t('workbench.wiEditor.saveAsTemplate')}</button>}
          <button disabled={!editable || tmu == null} onClick={add}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg disabled:opacity-40">{t('workbench.wiEditor.addToWorksheet')}</button>
        </div>
        {!editable && <p className="text-xs text-amber-600">{t('workbench.wiEditor.noEditPermission')}</p>}
      </div>

      {/* ═══ Table section ═══ */}
      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold">{t('workbench.wiEditor.worksheetTitle')}</h2>
            {/* [ADR-022 E-4] 從 WI 庫插入（實體化；需編輯權限＋已開啟工時表） */}
            {editable && activeWs && (
              <button
                onClick={() => setInsertWiOpen(true)}
                className="text-sm px-3 py-1 border border-blue-300 text-blue-700 rounded-lg hover:bg-blue-50"
                data-testid="insert-wi-btn"
              >
                {t('workbench.wiEditor.insertFromWi')}
              </button>
            )}
            {/* DSX 3D 擺放介面入口：內部／工程用，非正式功能，故用低調樣式跟主要
                動作按鈕區隔。見 DsxUiViewer.tsx 檔頭註——單一觀看者限制反映在開啟前
                的確認對話框裡，不在這裡處理。
                editable 門檻：這會搶走唯一的 WebRTC 觀看者名額，不該讓最低權限的人
                （包含唯讀模式下看歷史版工時表的 viewer）有能力把正在工作的人踢下線——
                跟旁邊「從 WI 庫插入」一致，後端端點維持 current_user 不用改（純讀取，
                升級門檻換不到實質保護）。 */}
            {editable && <DsxUiEntry />}
          </div>
          <div className="text-sm">
            <Trans
              i18nKey="workbench.wiEditor.totalTmu"
              values={{ tmu: total, seconds: (total * TMU_SEC).toFixed(2) }}
              components={{ tmu: <b className="text-emerald-600 text-lg" />, sec: <b className="text-emerald-600" /> }}
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-100 text-left">
                {/* D-1 drag handle */}
                <th className="p-1 w-6 text-center"></th>
                {/* D-2 checkbox */}
                <th className="p-1 w-7 text-center">
                  <input type="checkbox"
                    checked={rows.length > 0 && rows.every(r => selectedRowIds.has(r.id))}
                    onChange={e => {
                      if (e.target.checked) setSelectedRowIds(new Set(rows.map(r => r.id)))
                      else setSelectedRowIds(new Set())
                    }} />
                </th>
                <th className="p-1">#</th>
                <th className="p-1">{t('workbench.wiEditor.colHand')}</th>
                <th className="p-1">{t('workbench.wiEditor.colNarrative')}</th>
                <th className="p-1">Base TMU</th>
                {/* D-3 freq input */}
                <th className="p-1">{t('workbench.wiEditor.colFreq')}</th>
                <th className="p-1">Eff TMU</th>
                <th className="p-1">{t('workbench.wiEditor.colCt')}</th>
                {/* D-4 simo checkbox */}
                <th className="p-1">SIMO</th>
                {/* D-5 納入TMU */}
                <th className="p-1">{t('workbench.wiEditor.colIncluded')}</th>
                <th className="p-1"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const effTmu = r.tmu != null ? r.tmu * (r.freq || 1) : null
                const ctSec = effTmu != null ? (effTmu * TMU_SEC).toFixed(2) : '—'
                const isSimo = (r.simoGroup || '').trim() !== ''
                const isDragging = dragIdx === i
                const isOver = dragOverIdx === i
                const isSelected = selectedRowIds.has(r.id)
                const isHighlighted = highlightedRowIds.has(r.id)
                const rowCls = [
                  'border-t',
                  isDragging ? 'opacity-40' : '',
                  isOver ? 'border-t-2 border-t-sky-400' : '',
                  isSelected ? 'bg-blue-50' : '',
                  isHighlighted ? 'bg-amber-50' : '',
                ].filter(Boolean).join(' ')
                return (
                  <tr key={r.id} className={rowCls}
                    onDragOver={e => onDragOver(i, e)}
                    onDrop={e => onDrop(i, e)}>
                    {/* D-1 drag handle */}
                    <td className="p-1 text-center">
                      <span
                        className="cursor-grab text-slate-400 hover:text-slate-600 select-none text-base leading-none"
                        draggable
                        onDragStart={e => onDragStart(i, e)}
                        onDragEnd={onDragEnd}
                        title={t('workbench.wiEditor.dragTitle')}
                      >⠿</span>
                    </td>
                    {/* D-2 checkbox */}
                    <td className="p-1 text-center">
                      <input type="checkbox" checked={isSelected}
                        onChange={() => toggleSelect(r.id)} />
                    </td>
                    <td className="p-1">{i + 1}</td>
                    <td className="p-1">{r.handCode}</td>
                    <td className="p-1 max-w-xs truncate">{rowNarr(r)}</td>
                    <td className="p-1"><b>{r.tmu}</b></td>
                    {/* D-3 freq input */}
                    <td className="p-1">
                      <input type="number" min={1}
                        className="border rounded w-14 px-1 py-0.5 text-center"
                        value={r.freq}
                        onChange={e => {
                          const v = parseInt(e.target.value) || 1
                          updateRow(r.id, { freq: v, seconds: r.tmu * v * TMU_SEC })
                        }}
                        disabled={!editable} />
                    </td>
                    <td className="p-1"><b className="text-blue-700">{effTmu ?? '—'}</b></td>
                    <td className="p-1">{ctSec}</td>
                    {/* D-4 simo checkbox */}
                    <td className="p-1 text-center">
                      <input type="checkbox" checked={isSimo}
                        disabled={!editable}
                        onChange={e => updateRow(r.id, { simoGroup: e.target.checked ? 'simo-1' : '' })}
                        title={r.simoGroup || undefined} />
                    </td>
                    {/* D-5 納入TMU */}
                    <td className="p-1 text-right">
                      {isSimo
                        ? <span className="line-through text-slate-400">0</span>
                        : <span>{effTmu ?? '—'}</span>
                      }
                    </td>
                    <td className="p-1">
                      {editable && (
                        <button className="text-red-600 underline" onClick={() => {
                          delRow(r.id)
                          const n = new Set(selectedRowIds); n.delete(r.id); setSelectedRowIds(n)
                          const h = new Set(highlightedRowIds); h.delete(r.id); setHighlightedRowIds(h)
                        }}>{t('workbench.wiEditor.rowDelete')}</button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 && (
                <tr><td colSpan={12} className="p-3 text-slate-400">{t('workbench.wiEditor.noRows')}</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* [E-1] Floating action bar */}
        {selectedRowIds.size > 0 && (
          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg flex flex-wrap items-center gap-3">
            <span className="text-sm text-blue-700 font-medium">{t('workbench.wiEditor.selectedActions', { count: selectedRowIds.size })}</span>
            <span className="text-sm text-slate-500">{t('workbench.wiEditor.wiNameLabel')}</span>
            <input
              className="border rounded px-2 py-1 text-sm flex-1 min-w-0"
              placeholder={t('workbench.wiEditor.wiNamePlaceholder')}
              value={wiNameInput}
              onChange={e => setWiNameInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addToWi() }}
            />
            <button
              onClick={addToWi}
              disabled={!wiNameInput.trim()}
              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded disabled:opacity-40 shrink-0"
            >{t('workbench.wiEditor.addToWi')}</button>
            <button onClick={() => setSelectedRowIds(new Set())}
              className="text-xs text-slate-500 underline shrink-0">{t('workbench.wiEditor.clearSelection')}</button>
          </div>
        )}

        <div className="flex gap-2 mt-3 items-center">
          <button disabled={!editable || !rows.length || save.isPending} onClick={doSave}
            className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg disabled:opacity-40">{t('workbench.wiEditor.save')}</button>
          <span className="text-xs text-slate-500">{saveMsg}</span>
        </div>
      </div>

      {/* ═══ [E-2] WI Outline ═══ */}
      {wiGroups.length > 0 && (
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">{t('workbench.wiEditor.outlineTitle', { count: wiGroups.length })}</h2>
          </div>
          <div className="space-y-2">
            {wiGroups.map(group => {
              const grpTmu = wiGroupTmu(group)
              const isExpanded = expandedWiIds.has(group.id)
              const groupRows = rows.filter(r => group.rowIds.includes(r.id))
              return (
                <div key={group.id}
                  className="border rounded-lg overflow-hidden hover:shadow-sm transition-shadow">
                  {/* WI group header */}
                  <div
                    className="flex items-center gap-3 px-3 py-2 bg-slate-50 cursor-pointer select-none"
                    onClick={() => { selectWiGroup(group); toggleWiExpand(group.id) }}
                  >
                    <span className="text-slate-400 text-lg leading-none">{isExpanded ? '▾' : '▸'}</span>
                    <span className="font-medium text-sm flex-1 truncate">{group.name}</span>
                    <span className="text-xs text-slate-500 shrink-0">{t('workbench.wiEditor.groupActions', { count: group.rowIds.length })}</span>
                    <span className="text-sm shrink-0">
                      <b className="text-blue-700">{grpTmu.toFixed(1)}</b>
                      <span className="text-slate-400"> TMU ≈ </span>
                      <b className="text-emerald-600">{(grpTmu * TMU_SEC).toFixed(3)}</b>
                      <span className="text-slate-400">{t('workbench.wiEditor.seconds')}</span>
                    </span>
                    <button
                      onClick={e => { e.stopPropagation(); deleteWiGroup(group.id) }}
                      className="text-red-400 hover:text-red-600 text-xs ml-2 shrink-0"
                    >{t('workbench.wiEditor.groupDelete')}</button>
                  </div>
                  {/* Expanded: list action rows */}
                  {isExpanded && (
                    <div className="divide-y">
                      {groupRows.length === 0 && (
                        <div className="px-3 py-2 text-xs text-slate-400">{t('workbench.wiEditor.allDeleted')}</div>
                      )}
                      {groupRows.map((r, idx) => (
                        <div key={r.id} className="flex items-center gap-3 px-4 py-1.5 text-sm hover:bg-slate-50">
                          <span className="text-xs text-slate-400 w-5 shrink-0">{idx + 1}.</span>
                          <span className="text-xs text-slate-500 shrink-0">{r.handCode}</span>
                          <span className="flex-1 truncate text-xs">{rowNarr(r)}</span>
                          <span className="text-xs text-blue-600 shrink-0">{r.tmu} TMU</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ═══ [ADR-022 E-4] 從 WI 庫插入 modal + toast ═══ */}
      <WiToast toast={wiToast} />
      {insertWiOpen && (
        <InsertWiModal
          onClose={() => setInsertWiOpen(false)}
          onInsert={insertWiFromLibrary}
          inserting={instantiate.isPending}
        />
      )}

      {/* ═══ [C] Slot Modal ═══ */}
      {activeSlot && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setActiveSlot(null)}
        >
          <div
            className="bg-white rounded-xl border shadow-2xl p-5 max-w-lg w-full mx-4 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-base">{slotModalLabel(activeSlot)}</h3>
              <button onClick={() => setActiveSlot(null)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none">✕</button>
            </div>
            <div className="py-1">
              {activeSlot === 'a0' && aBlock(cur.a0, s => set({ a0: s }))}
              {activeSlot === 'b1' && bBlock('b1')}
              {activeSlot === 'g' && gBlock()}
              {activeSlot === 'a3' && (
                <>
                  {aBlock(cur.a3, s => set({ a3: s }))}
                  {/* DSX 建議距離（MVP，契約草案 §1.1／§3.1 掛載點更正）：只在 a3（from→to
                      物件間移動）出現，不做 a0／a6（§0.2）。這個面板組的是尚未存檔的新列，
                      wi_row_id 選填不帶——D4：建議值，never 自動寫入，需使用者明確點選填入。
                      reach／foot 兩顆填入按鈕各自獨立（2026-08-24 拿掉互斥：MOST 引擎算
                      TMU 對 A 格取 max(reach_index, foot_index, twist_index)，同一格
                      reach_cm／foot_cm 本來就允許同時有值）。onFillReach/onFillFoot 仍用
                      setCur 的 functional updater 而非 `set` helper——`set` helper 的 patch
                      是呼叫當下用閉包裡的 cur.a3 算好的，若使用者快速連續操作、兩次 setCur
                      排進同一輪 React 更新，用 c => ({ ...c, a3: { ...c.a3, ... } }) 才能保證
                      讀到佇列裡最新的 a3、疊加而不是互相蓋掉。 */}
                  <DsxA3Suggestion
                    fromVocabId={cur.nv.from}
                    toVocabId={cur.nv.to}
                    bandsReach={opts.a_bands.reach}
                    bandsFoot={opts.a_bands.foot}
                    onFillReach={cm => setCur(c => ({ ...c, a3: { ...c.a3, reach: cm } }))}
                    onFillFoot={cm => setCur(c => ({ ...c, a3: { ...c.a3, foot: cm } }))}
                  />
                </>
              )}
              {activeSlot === 'b4' && bBlock('b4')}
              {activeSlot === 'p' && pBlock()}
              {activeSlot === 'm' && mVerbBlock()}
              {activeSlot === 'x' && xBlock()}
              {activeSlot === 'i' && iBlock()}
              {activeSlot === 'a6' && aBlock(cur.a6, s => set({ a6: s }))}
            </div>
            {/* Live TMU preview in modal */}
            <div className="text-xs text-slate-500 border-t pt-2">
              {t('workbench.slot.previewTmu')} <b className="text-sky-700">{tmu ?? t('workbench.slot.computing')}</b>
              {tech && <span className="ml-2 font-mono text-slate-400">{tech}</span>}
            </div>
            <div className="flex justify-end">
              <button onClick={() => setActiveSlot(null)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">{t('workbench.slot.confirm')}</button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
