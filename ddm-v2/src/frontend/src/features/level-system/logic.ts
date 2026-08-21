import type { Row } from '../wi-workbench/store'

export interface LevelCell {
  coefficient: number; number: string; number_count: number | ''
  level: string; countersignature: string; machine_count: number; manpower: number
}
export interface GroupMeta { type: 'sub' | 'cub'; parent: string; seq: number }

export const blankCell = (i: number): LevelCell => ({
  coefficient: 1, number: '', number_count: '', level: String(i + 1),
  countersignature: '', machine_count: 1, manpower: 1,
})

export const wiIndex = (rows: Row[], id: string) => rows.findIndex(r => r.id === id)
export const cs = (lm: Record<string, LevelCell>, id: string) => (lm[id]?.countersignature || '').trim()
export const rowsIn = (rows: Row[], lm: Record<string, LevelCell>, label: string) =>
  rows.filter(r => cs(lm, r.id) === label)
export const subGroupsOf = (gm: Record<string, GroupMeta>, label: string) =>
  Object.keys(gm).filter(g => (gm[g].parent || '') === label)

export function firstIdx(rows: Row[], lm: Record<string, LevelCell>, gm: Record<string, GroupMeta>, label: string) {
  let mn = Infinity
  rows.forEach((r, i) => {
    const c = cs(lm, r.id)
    if (c === label || (gm[c] && (gm[c].parent || '') === label)) mn = Math.min(mn, i)
  })
  return mn === Infinity ? 1e6 + (gm[label]?.seq || 0) : mn
}

export interface LevelPayloadRow {
  content: string; raw_seconds: number; coefficient: number
  number: string | null; number_count: number | null
  ascription: string | null; level: string | null
  countersignature: string | null; parent_countersignature: string | null; order: number | null
}

// 由分組推導 ascription/order/level/parent（IE 不手填）；空母群組的子 cub 自動攤平 parent
//
// `narrOf`：本地新加的列 `row.narr` 是空的（敘述不入 state，見 store.ts），呼叫端傳
// `useRowNarr()` 進來即時重算；預設值只是讓純資料測試不必準備 rule-set 選項。
export function derive(
  rows: Row[], lm: Record<string, LevelCell>, gm: Record<string, GroupMeta>,
  narrOf: (r: Row) => string = (r) => r.narr,
): LevelPayloadRow[] {
  return rows.map((r, i) => {
    const m = lm[r.id] || blankCell(i)
    const c = (m.countersignature || '').trim()
    let ascription: string | null, order: number | null, level: string | null
    if (c) {
      const members = rowsIn(rows, lm, c)
      const idx = members.findIndex(x => x.id === r.id)
      order = idx + 1
      if (idx === 0) { ascription = 'main'; level = m.level?.trim() ? m.level : String(i + 1) }
      else { ascription = null; level = null }
    } else { ascription = 'main'; order = null; level = m.level?.trim() ? m.level : String(i + 1) }
    const par = c && gm[c]?.parent ? gm[c].parent : ''
    const parOk = !!par && rowsIn(rows, lm, par).length > 0
    return {
      content: narrOf(r), raw_seconds: r.seconds, coefficient: Number(m.coefficient) || 1,
      number: m.number?.trim() ? m.number.trim() : null,
      number_count: m.number_count === '' || m.number_count == null ? null : Number(m.number_count),
      ascription, level, countersignature: c || null, parent_countersignature: parOk ? par : null, order,
    }
  })
}

export function nbList(rows: Row[], lm: Record<string, LevelCell>) {
  const m: Record<string, { count: number; ids: string[] }> = {}
  rows.forEach(r => {
    const n = (lm[r.id]?.number || '').trim()
    if (n) (m[n] = m[n] || { count: Number(lm[r.id].number_count) || 1, ids: [] }).ids.push(r.id)
  })
  return m
}
