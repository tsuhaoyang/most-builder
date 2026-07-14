// SlotBuilder — v3 交錯句型列（SequenceSlotBuilder.vue 對等）＋slot modal 選值區塊
// 受控元件：value=CycleState、onChange(patch)；抽自 WiWorkbench 的 slot 色塊＋modal 區塊
// （aBlock…iBlock）。GM＝使用手｜從哪裡｜A1｜B1｜G｜目標物｜元件｜A2｜B2｜P｜到哪裡｜A3；
// CM＝使用手｜從哪裡｜A1｜B1｜G｜目標物｜元件｜M｜到哪裡｜X｜I｜哪裡｜A3。
// 前端不算 TMU（DISC-02）：tmu/tech 由呼叫端從後端 calculate 取得後傳入（modal 預覽用）。
import { useState } from 'react'
import { ComboBox } from '../../shared/ui/ComboBox'
import { Hint } from '../../shared/ui/Hint'
import { aBandOpts, type CycleState, type ASlot, type ABand } from '../wi-workbench/cycle'
import type { RuleSetOptions, Vocab } from '../wi-workbench/api'

// ── shared types ──────────────────────────────────────────────────────────────
export type SlotKey = 'a0' | 'b1' | 'g' | 'a3' | 'b4' | 'p' | 'm' | 'x' | 'i' | 'a6'
type NvKey = 'obj' | 'from' | 'to' | 'component' | 'where'

const HANDS = [{ v: 'RH', l: '右手' }, { v: 'LH', l: '左手' }, { v: 'BH', l: '雙手' }]

// slot 色塊配色（與 WiWorkbench 相同的 param → 色彩對映）
const SLOT_COLORS: Record<string, { filled: string; empty: string }> = {
  A: { filled: 'bg-blue-600 text-white border-blue-600', empty: 'bg-blue-50 text-blue-500 border-blue-300 border-dashed' },
  B: { filled: 'bg-slate-500 text-white border-slate-500', empty: 'bg-slate-50 text-slate-400 border-slate-300 border-dashed' },
  G: { filled: 'bg-green-600 text-white border-green-600', empty: 'bg-green-50 text-green-500 border-green-300 border-dashed' },
  P: { filled: 'bg-amber-500 text-white border-amber-500', empty: 'bg-amber-50 text-amber-500 border-amber-300 border-dashed' },
  M: { filled: 'bg-amber-500 text-white border-amber-500', empty: 'bg-amber-50 text-amber-500 border-amber-300 border-dashed' },
  X: { filled: 'bg-purple-600 text-white border-purple-600', empty: 'bg-purple-50 text-purple-400 border-purple-300 border-dashed' },
  I: { filled: 'bg-teal-600 text-white border-teal-600', empty: 'bg-teal-50 text-teal-500 border-teal-300 border-dashed' },
}

// ── small select（琥珀底＝可調整數值格） ────────────────────────────────────────
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

// ── A-slot 顯示 helpers ────────────────────────────────────────────────────────
function aIdx(val: number, bands: ABand[]): number {
  if (val === 0) return 0
  for (const b of bands) {
    const bv = b.max_value == null ? 999 : b.max_value
    if (val === bv) return b.index
  }
  return 0
}

export function aAbbrev(slot: ASlot, aBands: { reach: ABand[]; twist: ABand[]; foot: ABand[] }): string {
  const m = Math.max(
    aIdx(slot.reach, aBands.reach),
    aIdx(slot.twist, aBands.twist),
    aIdx(slot.foot, aBands.foot),
  )
  return m > 0 ? `A${m}` : '—'
}

export function aIsFilled(slot: ASlot): boolean {
  return slot.reach > 0 || slot.twist > 0 || slot.foot > 0
}

// ── builder item 定義（交錯順序，v3 SequenceSlotBuilder.vue:35-82） ─────────────
interface ContextItem { type: 'context'; key: string; label: string; nvKey?: NvKey; kind?: string }
interface SlotItem { type: 'slot'; key: string; slotKey: SlotKey; param: string; caption: string }
type BuilderItem = ContextItem | SlotItem

const GM_ITEMS: BuilderItem[] = [
  { type: 'context', key: 'hand', label: '使用手' },
  { type: 'context', key: 'from', label: '從哪裡', nvKey: 'from', kind: 'from' },
  { type: 'slot', key: 'A1', slotKey: 'a0', param: 'A', caption: '距離(A)-取得' },
  { type: 'slot', key: 'B1', slotKey: 'b1', param: 'B', caption: '身體動作(B)-取得時' },
  { type: 'slot', key: 'G', slotKey: 'g', param: 'G', caption: '取得控制(G)' },
  { type: 'context', key: 'target', label: '目標物', nvKey: 'obj', kind: 'object' },
  { type: 'context', key: 'component', label: '元件', nvKey: 'component', kind: 'component' },
  { type: 'slot', key: 'A2', slotKey: 'a3', param: 'A', caption: '距離(A)-移動' },
  { type: 'slot', key: 'B2', slotKey: 'b4', param: 'B', caption: '身體動作(B)-移動時' },
  { type: 'slot', key: 'P', slotKey: 'p', param: 'P', caption: '放置(P)' },
  { type: 'context', key: 'to', label: '到哪裡', nvKey: 'to', kind: 'to' },
  { type: 'slot', key: 'A3', slotKey: 'a6', param: 'A', caption: '距離(A)-返回' },
]

const CM_ITEMS: BuilderItem[] = [
  { type: 'context', key: 'hand', label: '使用手' },
  { type: 'context', key: 'from', label: '從哪裡', nvKey: 'from', kind: 'from' },
  { type: 'slot', key: 'A1', slotKey: 'a0', param: 'A', caption: '距離(A)-取得' },
  { type: 'slot', key: 'B1', slotKey: 'b1', param: 'B', caption: '身體動作(B)-取得時' },
  { type: 'slot', key: 'G', slotKey: 'g', param: 'G', caption: '取得控制(G)' },
  { type: 'context', key: 'target', label: '目標物', nvKey: 'obj', kind: 'object' },
  { type: 'context', key: 'component', label: '元件', nvKey: 'component', kind: 'component' },
  { type: 'slot', key: 'M', slotKey: 'm', param: 'M', caption: '控制移動(M)' },
  { type: 'context', key: 'to', label: '到哪裡', nvKey: 'to', kind: 'to' },
  { type: 'slot', key: 'X', slotKey: 'x', param: 'X', caption: '製程時間(X)' },
  { type: 'slot', key: 'I', slotKey: 'i', param: 'I', caption: '對準/檢查(I)' },
  // 「哪裡」沿用 to 詞彙庫（位置類詞彙），僅入敘述/顯示
  { type: 'context', key: 'where', label: '哪裡', nvKey: 'where', kind: 'to' },
  { type: 'slot', key: 'A3', slotKey: 'a6', param: 'A', caption: '距離(A)-返回' },
]

const SLOT_MODAL_LABELS: Record<SlotKey, string> = {
  a0: 'A 移動 — 取得段',
  b1: 'B 身體動作 — 取得段',
  g: 'G 取得',
  a3: 'A 移動 — 放置段',
  b4: 'B 身體動作 — 放置段',
  p: 'P 放置',
  m: 'M 控制移動',
  x: 'X 製程時間',
  i: 'I 對準/檢查',
  a6: 'A 移動 — 返回段',
}

// ── AI badge（F-05 四態）樣式 ──────────────────────────────────────────────────
function badgeCls(text: string): string {
  if (text.includes('推斷')) return 'bg-emerald-50 text-emerald-600 border-emerald-200'
  if (text.includes('預設')) return 'bg-amber-50 text-amber-600 border-amber-200'
  if (text.includes('待確認')) return 'bg-red-50 text-red-500 border-red-200'
  return 'bg-blue-50 text-blue-600 border-blue-200' // 明確
}

// ── SlotBuilder ───────────────────────────────────────────────────────────────
export interface SlotBuilderProps {
  value: CycleState
  onChange: (patch: Partial<CycleState>) => void
  opts: RuleSetOptions
  vocab: Vocab[]
  /** 詞彙不存在時新增；assign 回填新 vocab id 至對應 nv 欄 */
  onCreateVocab?: (kind: string, name: string, assign: (id: string) => void) => void
  showHandInMi: boolean
  onShowHandInMiChange: (v: boolean) => void
  /** modal 內即時 TMU 預覽（後端 calculate 回傳；前端不自算） */
  tmu?: number | null
  tech?: string
  /** AI badge（F-05 四態）：key = A1|B1|G|A2|B2|P|A3|M|X|I */
  slotBadges?: Record<string, string>
}

export function SlotBuilder({
  value: cur, onChange, opts, vocab, onCreateVocab,
  showHandInMi, onShowHandInMiChange, tmu, tech, slotBadges,
}: SlotBuilderProps) {
  const [activeSlot, setActiveSlot] = useState<SlotKey | null>(null)
  const set = (patch: Partial<CycleState>) => onChange(patch)
  const gm = cur.seq === 'GM'

  const vopts = (kind: string) =>
    vocab.filter(v => v.kind === kind).map(v => ({ v: v.id, l: v.name_zh }))

  // ── context 米黃格（詞彙 ComboBox） ─────────────────────────────────────────
  const contextBlock = (item: ContextItem) => (
    <div
      key={item.key}
      className="flex flex-col rounded-md border px-1.5 pt-1 pb-1.5"
      style={{ background: '#fdf8e8', borderColor: '#e0d8c0', minWidth: '7.5rem' }}
    >
      <span className="text-[10px] text-slate-500 text-center mb-0.5">{item.label}</span>
      <ComboBox
        options={vopts(item.kind!)}
        value={cur.nv[item.nvKey!]}
        placeholder={item.label}
        onPick={id => set({ nv: { ...cur.nv, [item.nvKey!]: id } })}
        onCreate={onCreateVocab
          ? name => onCreateVocab(item.kind!, name, id => set({ nv: { ...cur.nv, [item.nvKey!]: id } }))
          : undefined}
      />
    </div>
  )

  // ── 使用手 紫底格 ────────────────────────────────────────────────────────────
  const handBlock = () => (
    <div
      key="hand"
      className="flex flex-col rounded-md border px-1.5 pt-1 pb-1.5"
      style={{ background: '#f0e6ff', borderColor: '#c4a8e8', minWidth: '6rem' }}
    >
      <span className="text-[10px] text-slate-500 text-center mb-0.5">使用手</span>
      <Sel
        value={cur.handCode}
        onChange={v => set({ handCode: v })}
        opts={HANDS}
        cls="border rounded px-1 py-0.5 text-sm bg-white"
      />
      <label className="flex items-center gap-1 mt-1 text-[10px] text-slate-600 cursor-pointer">
        <input
          type="checkbox"
          checked={showHandInMi}
          onChange={e => onShowHandInMiChange(e.target.checked)}
        />
        顯示於MI
      </label>
    </div>
  )

  // ── slot 摘要（色塊上的縮寫） ────────────────────────────────────────────────
  function slotState(key: SlotKey): { filled: boolean; abbrev: string } {
    switch (key) {
      case 'a0': return { filled: aIsFilled(cur.a0), abbrev: aAbbrev(cur.a0, opts.a_bands) }
      case 'a3': return { filled: aIsFilled(cur.a3), abbrev: aAbbrev(cur.a3, opts.a_bands) }
      case 'a6': return { filled: aIsFilled(cur.a6), abbrev: aAbbrev(cur.a6, opts.a_bands) }
      case 'b1': return { filled: !!cur.b1, abbrev: cur.b1 ? (opts.b.find(b => b.code === cur.b1)?.label.slice(0, 4) ?? 'B?') : '—' }
      case 'b4': return { filled: !!cur.b4, abbrev: cur.b4 ? (opts.b.find(b => b.code === cur.b4)?.label.slice(0, 4) ?? 'B?') : '—' }
      case 'g': return { filled: !!cur.g, abbrev: cur.g ? (opts.g.find(g => g.code === cur.g)?.label.slice(0, 4) ?? 'G?') : '—' }
      case 'p': return { filled: !!cur.p_base, abbrev: cur.p_base ? (opts.p_bases.find(p => p.code === cur.p_base)?.label.slice(0, 4) ?? 'P?') : '—' }
      case 'm': return { filled: !!cur.m.verb, abbrev: cur.m.verb ? (opts.m_verbs.find(m => m.code === cur.m.verb)?.label.slice(0, 4) ?? 'M?') : '—' }
      case 'x': return { filled: cur.x !== 'x_none', abbrev: cur.x !== 'x_none' ? (opts.x.find(x => x.code === cur.x)?.label.slice(0, 4) ?? 'X?') : '—' }
      case 'i': return { filled: cur.i !== 'i_none', abbrev: cur.i !== 'i_none' ? (opts.i.find(i => i.code === cur.i)?.label.slice(0, 4) ?? 'I?') : '—' }
    }
  }

  const slotBlock = (item: SlotItem) => {
    const clr = SLOT_COLORS[item.param] ?? SLOT_COLORS['A']
    const st = slotState(item.slotKey)
    const badge = slotBadges?.[item.key]
    return (
      <div key={item.key} className="relative flex">
        <button
          className={`flex flex-col items-center justify-center min-w-[84px] px-2 py-1.5 rounded-lg border-2
            cursor-pointer transition-all select-none hover:opacity-80 active:scale-95
            ${st.filled ? clr.filled : clr.empty}`}
          onClick={() => setActiveSlot(item.slotKey)}
          title={SLOT_MODAL_LABELS[item.slotKey]}
        >
          <span className="text-[10px] font-semibold opacity-80 leading-none mb-1">{item.key}</span>
          <span className="font-bold text-sm leading-none">{st.abbrev}</span>
          <span className="text-[9px] opacity-70 leading-none mt-1 whitespace-nowrap">{item.caption}</span>
        </button>
        {badge && (
          <span className={`absolute -bottom-1.5 left-1/2 -translate-x-1/2 text-[9px] leading-none px-1 py-0.5 rounded border whitespace-nowrap z-10 ${badgeCls(badge)}`}>
            {badge}
          </span>
        )}
      </div>
    )
  }

  // ── modal 內的選值區塊（抽自 WiWorkbench aBlock…iBlock） ─────────────────────
  const aBlock = (slot: ASlot, onSlot: (s: ASlot) => void) => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle px-1 bg-blue-50 border border-blue-200 rounded">
      <Hint tip="A 移動/伸手：取 伸手、手度(扭轉)、腳步 三者分級的最大值；距離越大分數越高。" />
      {(['reach', 'twist', 'foot'] as const).map(comp => (
        <Sel key={comp} value={String(slot[comp] || 0)}
          opts={aBandOpts(opts.a_bands[comp], comp).map(o => ({ v: String(o.v), l: o.l }))}
          onChange={v => onSlot({ ...slot, [comp]: parseFloat(v) || 0 })} />
      ))}
    </span>
  )
  const bBlock = (key: 'b1' | 'b4') => (
    <span className="inline-flex items-center align-middle">
      <Hint tip="B 身體動作：彎腰/起身/站坐等輔助動作（無=0）。" />
      <Sel value={cur[key] ?? ''} onChange={v => set({ [key]: v || null } as Partial<CycleState>)}
        opts={[{ v: '', l: '身體:無' }, ...opts.b.filter(b => b.code !== 'b_none').map(b => ({ v: b.code, l: b.label }))]} />
    </span>
  )
  const gBlock = () => {
    const g = opts.g.find(x => x.code === cur.g)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="G 取得：抓握/接觸/拿取等方式；部分方式需勾修飾子，否則計 0。" />
        <Sel value={cur.g} onChange={v => set({ g: v, gMod: {} })}
          opts={[{ v: '', l: '—取得方式—' }, ...opts.g.map(o => ({ v: o.code, l: o.label }))]} />
        {g?.requires_modifier && g.modifier_key && (
          <Sel value={cur.gMod[g.modifier_key] ? '1' : '0'}
            onChange={v => set({ gMod: { ...cur.gMod, [g.modifier_key!]: v === '1' } })}
            opts={[{ v: '0', l: `—${g.modifier_key} 未勾—` }, { v: '1', l: `✓ ${g.modifier_key}` }]} />
        )}
      </span>
    )
  }
  const pBlock = () => (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle">
      <Hint tip="P 放置：放/組/保持等 + 最多 2 個附加（對準、插入、壓合…）。選「對準」須再勾精度(<4mm)。" />
      <Sel value={cur.p_base} onChange={v => set({ p_base: v })}
        opts={[{ v: '', l: '—放置—' }, ...opts.p_bases.map(o => ({ v: o.code, l: o.label }))]} />
      {[0, 1].map(i => (
        <Sel key={i} value={cur.p_addons[i] ?? ''}
          onChange={v => { const a = cur.p_addons.filter((_, j) => j !== i); if (v) a.splice(i, 0, v); set({ p_addons: a.slice(0, 2) }) }}
          opts={[{ v: '', l: '—附加—' }, ...opts.p_addons.map(o => ({ v: o.code, l: o.label }))]} />
      ))}
      {cur.p_addons.some(c => opts.p_addons.find(a => a.code === c)?.needs_precision) && (
        <Sel value={cur.precision ? '1' : '0'} onChange={v => set({ precision: v === '1' })}
          opts={[{ v: '0', l: '精度未勾' }, { v: '1', l: '精度<4mm' }]} />
      )}
    </span>
  )
  const mVerbBlock = () => {
    const mv = opts.m_verbs.find(x => x.code === cur.m.verb)
    const k = mv?.pricing_kind
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="M 控制移動：推/拉/旋轉/鎖附等受控動作；依動詞種類自動要距離、角度或圈數。" />
        <Sel value={cur.m.verb} onChange={v => set({ m: { ...cur.m, verb: v } })}
          opts={[{ v: '', l: '—控制動詞—' }, ...opts.m_verbs.map(o => ({ v: o.code, l: o.label }))]} />
        {(k === 'ladder' || k === 'foot' || k === 'distance_ladder') && (
          <Sel value={String(cur.m.distance)} onChange={v => set({ m: { ...cur.m, distance: parseFloat(v) } })}
            opts={[4, 12, 18, 30, 45].map(d => ({ v: String(d), l: '距離 ' + d + 'cm' }))} />)}
        {(k === 'hand' || k === 'hand_twist') && (
          <Sel value={String(cur.m.angle)} onChange={v => set({ m: { ...cur.m, angle: parseFloat(v) } })}
            opts={[{ v: '90', l: '≤90度' }, { v: '180', l: '≤180度' }]} />)}
        {(k === 'rotate' || k === 'rotation_by_diameter') && (
          <Sel value={String(cur.m.rev)} onChange={v => set({ m: { ...cur.m, rev: parseInt(v) } })}
            opts={[1, 2, 3].map(r => ({ v: String(r), l: r + '圈' }))} />)}
      </span>
    )
  }
  const xBlock = () => {
    const xo = opts.x.find(o => o.code === cur.x)
    return (
      <span className="inline-flex flex-wrap items-center gap-1 align-middle">
        <Hint tip="X 製程時間：機器/製程造成的等待（熱壓、測試、掃描）；連續式需輸入秒數。" />
        <Sel value={cur.x} onChange={v => set({ x: v })} opts={opts.x.map(o => ({ v: o.code, l: o.label }))} />
        {xo?.mode === 'seconds' && (
          <input type="number" min={0} step={0.1}
            className="border-2 border-dashed border-slate-300 rounded w-20 px-1 text-sm bg-amber-50"
            value={cur.x_sec} onChange={e => set({ x_sec: parseFloat(e.target.value) || 0 })} placeholder="秒" />
        )}
      </span>
    )
  }
  const iBlock = () => (
    <span className="inline-flex items-center align-middle">
      <Hint tip="I 對準/檢查：定位對準或檢查確認動作的分級。" />
      <Sel value={cur.i} onChange={v => set({ i: v })} opts={opts.i.map(o => ({ v: o.code, l: o.label }))} />
    </span>
  )

  const items = gm ? GM_ITEMS : CM_ITEMS

  return (
    <div>
      {/* 交錯句型列：單一 flex-wrap 流，情境欄嵌在格位之間 */}
      <div className="flex flex-wrap gap-1.5 items-stretch py-1" data-testid="slot-builder-flow">
        {items.map(item => {
          if (item.type === 'context') {
            return item.key === 'hand' ? handBlock() : contextBlock(item)
          }
          return slotBlock(item)
        })}
      </div>

      {/* slot modal（點色塊開啟；即時 TMU 預覽由後端 calculate 提供） */}
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
              <h3 className="font-semibold text-base">{SLOT_MODAL_LABELS[activeSlot]}</h3>
              <button onClick={() => setActiveSlot(null)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none">✕</button>
            </div>
            <div className="py-1">
              {activeSlot === 'a0' && aBlock(cur.a0, s => set({ a0: s }))}
              {activeSlot === 'b1' && bBlock('b1')}
              {activeSlot === 'g' && gBlock()}
              {activeSlot === 'a3' && aBlock(cur.a3, s => set({ a3: s }))}
              {activeSlot === 'b4' && bBlock('b4')}
              {activeSlot === 'p' && pBlock()}
              {activeSlot === 'm' && mVerbBlock()}
              {activeSlot === 'x' && xBlock()}
              {activeSlot === 'i' && iBlock()}
              {activeSlot === 'a6' && aBlock(cur.a6, s => set({ a6: s }))}
            </div>
            <div className="text-xs text-slate-500 border-t pt-2">
              預覽 TMU: <b className="text-sky-700">{tmu ?? '計算中…'}</b>
              {tech && <span className="ml-2 font-mono text-slate-400">{tech}</span>}
            </div>
            <div className="flex justify-end">
              <button onClick={() => setActiveSlot(null)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">確認</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
