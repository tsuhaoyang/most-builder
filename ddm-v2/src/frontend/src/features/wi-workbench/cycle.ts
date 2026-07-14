// 精確編輯的 cycle 狀態 + 轉 CycleIn payload + 敘述（移植 html_con 的 payload()/shortNarr）
export interface ASlot { reach: number; twist: number; foot: number }
export interface CycleState {
  seq: 'GM' | 'CM'
  handCode: string
  freq: number
  simoGroup: string
  /** component / where 僅供敘述與顯示（交錯句型的情境欄）；buildPayload 不讀取 nv */
  nv: { obj: string; from: string; to: string; component: string; where: string }
  a0: ASlot; b1: string | null; g: string; gMod: Record<string, boolean>
  a3: ASlot; b4: string | null; p_base: string; p_addons: string[]; precision: boolean
  m: { verb: string; distance: number; angle: number; rev: number; dia: number }
  x: string; x_sec: number; i: string
  a6: ASlot
}

export const defaultCycle = (): CycleState => ({
  seq: 'GM', handCode: 'RH', freq: 1, simoGroup: '',
  nv: { obj: '', from: '', to: '', component: '', where: '' },
  a0: { reach: 0, twist: 0, foot: 0 }, b1: null, g: '', gMod: {},
  a3: { reach: 0, twist: 0, foot: 0 }, b4: null, p_base: '', p_addons: [], precision: false,
  m: { verb: '', distance: 30, angle: 90, rev: 1, dia: 10 }, x: 'x_none', x_sec: 0, i: 'i_none',
  a6: { reach: 0, twist: 0, foot: 0 },
})

export interface ABand { max_value: number | null; index: number }
export function aBandOpts(bands: ABand[], comp: 'reach' | 'twist' | 'foot') {
  const unit = comp === 'twist' ? '度' : '公分'
  const lead = comp === 'reach' ? '伸手' : comp === 'twist' ? '手度' : '腳步'
  const out = [{ v: 0, l: `${lead}：無` }]
  for (const b of bands) {
    const v = b.max_value == null ? 999 : b.max_value
    out.push({ v, l: `≤${b.max_value == null ? '更大' : b.max_value}${unit}(A${b.index})` })
  }
  return out
}

const A = (s: ASlot) => ({ reach_cm: s.reach || 0, twist_deg: s.twist || 0, foot_cm: s.foot || 0 })

export function buildPayload(c: CycleState, ruleSetCode: string): Record<string, unknown> {
  const gm = c.seq === 'GM'
  const p: Record<string, unknown> = {
    seq: c.seq, rule_set_code: ruleSetCode,
    a0: A(c.a0), b1: { b_code: c.b1 }, g2: { g_code: c.g || null, modifiers: c.gMod || {} }, a6: A(c.a6),
  }
  if (gm) {
    p.a3 = A(c.a3); p.b4 = { b_code: c.b4 }
    p.p5 = { p_base_code: c.p_base || null, p_addon_codes: c.p_addons || [], precision: !!c.precision }
  } else {
    p.m3 = { m_components: c.m.verb ? [{ verb_code: c.m.verb, distance_cm: c.m.distance, angle_deg: c.m.angle, revolutions: c.m.rev, diameter_cm: c.m.dia }] : [] }
    p.x4 = { x_code: c.x || 'x_none', x_seconds: c.x_sec || 0 }
    p.i5 = { i_code: c.i || 'i_none' }
  }
  return p
}

// CycleIn payload → CycleState（範本插入用；buildPayload 的逆向）
export function payloadToState(p: Record<string, any>): CycleState { // eslint-disable-line @typescript-eslint/no-explicit-any
  const s = defaultCycle()
  s.seq = p.seq === 'CM' ? 'CM' : 'GM'
  const toA = (o: any): ASlot => ({ reach: o?.reach_cm || 0, twist: o?.twist_deg || 0, foot: o?.foot_cm || 0 }) // eslint-disable-line @typescript-eslint/no-explicit-any
  s.a0 = toA(p.a0); s.a6 = toA(p.a6)
  s.g = p.g2?.g_code || ''; s.gMod = p.g2?.modifiers || {}; s.b1 = p.b1?.b_code ?? null
  if (s.seq === 'GM') {
    s.a3 = toA(p.a3); s.b4 = p.b4?.b_code ?? null
    s.p_base = p.p5?.p_base_code || ''; s.p_addons = p.p5?.p_addon_codes || []; s.precision = !!p.p5?.precision
  } else {
    const m = (p.m3?.m_components || [])[0] || {}
    s.m = { verb: m.verb_code || '', distance: m.distance_cm || 30, angle: m.angle_deg || 90, rev: m.revolutions || 1, dia: m.diameter_cm || 10 }
    s.x = p.x4?.x_code || 'x_none'; s.x_sec = p.x4?.x_seconds || 0; s.i = p.i5?.i_code || 'i_none'
  }
  return s
}

const HAND_NAME: Record<string, string> = { RH: '右手', LH: '左手', BH: '雙手' }
// showHand=false 時省略使用手（「顯示於MI」checkbox 未勾）；component/where 為空時輸出與舊版完全一致
export function shortNarr(c: CycleState, label: (kind: string, code: string) => string, vname: (kind: string, id: string) => string, showHand = true): string {
  const hand = showHand ? (HAND_NAME[c.handCode] || '') : ''
  const g = label('g', c.g) || '［取得］'
  const act2 = c.seq === 'GM' ? (label('p_base', c.p_base) || '［放置］') : (label('m_verb', c.m.verb) || '［動作］')
  const comp = vname('component', c.nv.component || '')
  const obj = vname('object', c.nv.obj) || '［物］'
  const objPart = comp ? `${obj}的${comp}` : obj
  const base = `${hand ? hand + ' ' : ''}從${vname('from', c.nv.from) || '［自］'} ${g}「${objPart}」 ${act2} 至${vname('to', c.nv.to) || '［至］'}`
  const where = c.seq === 'CM' ? vname('to', c.nv.where || '') : ''
  return where ? `${base}（於${where}）` : base
}
